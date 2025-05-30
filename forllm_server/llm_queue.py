import threading
import queue
import time
import sqlite3
import json # Added
from .config import DATABASE, CURRENT_USER_ID # Added CURRENT_USER_ID
from .llm_processing import process_llm_request
from .scheduler import is_processing_time
from .persona_generator import generate_persona_from_details # Added
from .database import save_generated_persona # Added

llm_request_queue = queue.Queue()
processing_active = threading.Event() # To signal if processing is allowed by schedule

def _handle_persona_generation_request(request_id, request_params_json, flask_app):
    # This function manages its own DB connection for all its operations including final status updates.
    db_conn = None 
    try:
        db_conn = sqlite3.connect(DATABASE)
        cursor = db_conn.cursor()

        if not request_params_json:
            print(f"Error: request_params are missing for generate_persona request_id {request_id}")
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = 'Missing request_params', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            db_conn.commit()
            return

        request_params_dict = json.loads(request_params_json)
        
        generation_result = generate_persona_from_details(request_params_dict, flask_app)

        if generation_result and generation_result.get('status') == 'success':
            persona_name = generation_result['persona_name']
            prompt_instructions = generation_result['prompt_instructions']
            gen_type_from_params = request_params_dict.get('generation_type', 'unknown_type')
            generation_source = f"llm_generated_{gen_type_from_params}"
            input_details_json = json.dumps(request_params_dict.get('input_details', {}))

            with flask_app.app_context():
                new_persona_id = save_generated_persona(
                    persona_name,
                    prompt_instructions,
                    generation_source,
                    input_details_json,
                    CURRENT_USER_ID 
                )

            if new_persona_id:
                print(f"Persona '{persona_name}' (ID: {new_persona_id}) saved successfully for request {request_id}.")
                cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            else:
                print(f"Error: Failed to save generated persona for request {request_id}.")
                cursor.execute("UPDATE llm_requests SET status = 'error', error_message = 'Failed to save persona to DB', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        else:
            error_msg = generation_result.get('error_message', 'Persona generation failed (no specific error message)')
            print(f"Error: Persona generation failed for request {request_id}: {error_msg}")
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ? WHERE request_id = ?", (error_msg, request_id)) # Removed processed_at here, let it be set by processing update
        
        db_conn.commit()

    except json.JSONDecodeError as e:
        print(f"Error decoding request_params_json for request_id {request_id}: {e}")
        if db_conn: 
            cursor = db_conn.cursor() 
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Invalid JSON in request_params: {str(e)}", request_id))
            db_conn.commit()
    except Exception as e:
        print(f"Unhandled error during persona generation for request_id {request_id}: {e.__class__.__name__}: {e}")
        if db_conn: 
            cursor = db_conn.cursor() 
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Unhandled generation error: {str(e)}", request_id))
            db_conn.commit()
    finally:
        if db_conn:
            db_conn.close()

def llm_worker(flask_app): # Added flask_app parameter
    """Background worker thread to process LLM requests from the queue."""
    print(f"LLM Worker thread started. Received Flask app: {flask_app}") # Log the received app
    while True:
        if is_processing_time():
            processing_active.set() # Signal that processing is allowed
            print("Processing time active. Checking queue...")
            try:
                # Prioritize getting items from the software queue first
                request_details = llm_request_queue.get(timeout=5) # Wait 5 seconds for an item
                # Pass flask_app to process_llm_request (this is for requests from the software queue)
                process_llm_request(request_details, flask_app)
                llm_request_queue.task_done()
            except queue.Empty:
                print("Software queue empty, checking DB queue...")
                db_conn_poll = None 
                try:
                    db_conn_poll = sqlite3.connect(DATABASE)
                    db_conn_poll.row_factory = sqlite3.Row
                    cursor_poll = db_conn_poll.cursor()
                    
                    cursor_poll.execute("SELECT request_id, post_id_to_respond_to, llm_model, llm_persona, request_type, request_params FROM llm_requests WHERE status = 'pending' ORDER BY requested_at ASC LIMIT 1")
                    db_request_data = cursor_poll.fetchone()

                    if db_request_data:
                        request_id = db_request_data['request_id']
                        post_id_to_respond_to = db_request_data['post_id_to_respond_to']
                        llm_model_for_response = db_request_data['llm_model'] 
                        llm_persona_for_response = db_request_data['llm_persona']
                        
                        request_type = db_request_data['request_type'] if 'request_type' in db_request_data.keys() and db_request_data['request_type'] else 'respond_to_post'
                        request_params_json = db_request_data['request_params'] if 'request_params' in db_request_data.keys() and db_request_data['request_params'] else None

                        cursor_poll.execute("UPDATE llm_requests SET status = 'processing', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
                        db_conn_poll.commit()
                        
                        # Dispatching: handlers manage their own DB connections for final status updates.
                        if request_type == 'generate_persona':
                            print(f"LLM Worker: Delegating persona generation for request_id {request_id}")
                            _handle_persona_generation_request(request_id, request_params_json, flask_app)
                        elif request_type == 'respond_to_post' or request_type == 'respond_to_post_tag': # Modified condition
                            if post_id_to_respond_to is None:
                                print(f"Error: post_id_to_respond_to is missing for {request_type} request_id {request_id}. Marking as error.")
                                # This error case needs its own DB connection to update status
                                temp_db_err = sqlite3.connect(DATABASE)
                                temp_cur_err = temp_db_err.cursor()
                                temp_cur_err.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Missing post_id_to_respond_to for {request_type} type", request_id))
                                temp_db_err.commit()
                                temp_db_err.close()
                            else:
                                print(f"LLM Worker: Delegating {request_type} for request_id {request_id}")
                                process_llm_request({
                                    'request_id': request_id,
                                    'post_id': post_id_to_respond_to,
                                    'model': llm_model_for_response, # Keep as is, process_llm_request will handle default
                                    'persona': llm_persona_for_response
                                }, flask_app)
                        else:
                            print(f"Unknown request_type: {request_type} for request_id {request_id}. Marking as error.")
                            temp_db_err = sqlite3.connect(DATABASE)
                            temp_cur_err = temp_db_err.cursor()
                            temp_cur_err.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Unknown request_type: {request_type}", request_id))
                            temp_db_err.commit()
                            temp_db_err.close()
                    else: 
                        print("DB queue also empty. Sleeping...")
                        time.sleep(10) 
                
                except sqlite3.Error as e:
                    print(f"SQLite error in LLM worker (DB queue processing): {e}")
                    # Potentially add a longer sleep or specific error handling here
                    time.sleep(10) 
                except Exception as e:
                    # Catching generic Exception to log and prevent worker thread crash
                    print(f"General error in LLM worker (DB queue processing): {e.__class__.__name__}: {e}")
                    time.sleep(10) 
                finally:
                    if db_conn_poll:
                        db_conn_poll.close()
        else:
            processing_active.clear() # Signal that processing is paused
            print(f"Outside processing hours. Worker sleeping... (Will check again in 60s)")
            time.sleep(60) # Sleep longer when outside processing hours