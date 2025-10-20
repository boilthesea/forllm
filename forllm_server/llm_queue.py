import threading
import queue
import time
import sqlite3
import json
from .config import DATABASE, CURRENT_USER_ID
from .scheduler import is_processing_time
from .persona_generator import generate_persona_from_details
from .database import save_generated_persona

# Generator Imports
from .generators.ollama_connector import OllamaConnector
from .generators.tts_connector import TTSConnector
# from .generators.diffusers_connector import DiffusersConnector # Placeholder
# from .generators.music_connector import MusicConnector # Placeholder
# from .generators.video_connector import VideoConnector # Placeholder

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

            if persona_name.lower() == 'optimize':
               print(f"Error: Attempted to create a persona with the reserved name 'optimize' for request {request_id}.")
               cursor.execute("UPDATE llm_requests SET status = 'error', error_message = 'Cannot create a persona with the reserved name ''optimize''.' WHERE request_id = ?", (request_id,))
               db_conn.commit()
               return

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
                cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP, result_object_id = ? WHERE request_id = ?", (new_persona_id, request_id,))
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

def llm_worker(flask_app):
    """Background worker thread to process LLM requests from the queue."""
    print(f"LLM Worker thread started. Received Flask app: {flask_app}")

    generator_map = {
        'respond_to_post': OllamaConnector,
        'respond_to_post_tag': OllamaConnector,
        'optimize_prompt': OllamaConnector,
        'generate_audiobook_chapter': TTSConnector,
        # 'generate_image': DiffusersConnector, # Placeholder
        # 'generate_tts': TTSConnector, # Placeholder
        # 'generate_music': MusicConnector, # Placeholder
        # 'generate_video': VideoConnector, # Placeholder
    }

    while True:
        if not is_processing_time():
            processing_active.clear()
            print("Outside processing hours. Worker sleeping... (Will check again in 60s)")
            time.sleep(60)
            continue

        processing_active.set()
        db_conn = None
        try:
            db_conn = sqlite3.connect(DATABASE)
            db_conn.row_factory = sqlite3.Row
            cursor = db_conn.cursor()

            cursor.execute("SELECT * FROM llm_requests WHERE status = 'pending' ORDER BY requested_at ASC LIMIT 1")
            request_data = cursor.fetchone()

            if not request_data:
                time.sleep(5)
                continue

            request_id = request_data['request_id']
            request_type = request_data['request_type'] or 'respond_to_post'
            
            cursor.execute("UPDATE llm_requests SET status = 'processing', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            db_conn.commit()

            result = None
            if request_type == 'generate_persona':
                print(f"LLM Worker: Delegating persona generation for request_id {request_id}")
                _handle_persona_generation_request(request_id, request_data['request_params'], flask_app)
            
            elif request_type in generator_map:
                generator_class = generator_map[request_type]
                generator_instance = generator_class()
                print(f"LLM Worker: Dispatching request {request_id} to {generator_class.__name__}")
                result = generator_instance.generate(dict(request_data), flask_app)
            
            else:
                print(f"Unknown request_type: {request_type} for request_id {request_id}. Marking as error.")
                result = {'status': 'error', 'error_message': f"Unknown request_type: {request_type}"}

            if result:
                if result.get('status') == 'success':
                    cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP, result_text = ? WHERE request_id = ?", (json.dumps(result), request_id))
                    db_conn.commit()

                    parent_request_id = request_data.get('parent_request_id')
                    if parent_request_id:
                        cursor.execute("SELECT COUNT(*) FROM llm_requests WHERE parent_request_id = ? AND status != 'complete'", (parent_request_id,))
                        incomplete_children = cursor.fetchone()

                        if incomplete_children == 0:
                            cursor.execute("UPDATE llm_requests SET status = 'pending' WHERE request_id = ? AND request_type = 'generate_audiobook_parent'", (parent_request_id,))
                            db_conn.commit()
                            print(f"All children for parent {parent_request_id} are complete. Queuing parent for assembly.")

                elif result.get('status') == 'error':
                    cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (result.get('error_message', 'Unknown error'), request_id))
                    db_conn.commit()

        except sqlite3.Error as e:
            print(f"SQLite error in LLM worker: {e}")
            time.sleep(10)
        except Exception as e:
            print(f"General error in LLM worker: {e.__class__.__name__}: {e}")
            # If a request was being processed, mark it as an error
            if 'request_id' in locals():
                try:
                    err_db_conn = sqlite3.connect(DATABASE)
                    err_cursor = err_db_conn.cursor()
                    err_cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ? WHERE request_id = ?", (f"Worker crash: {str(e)}", request_id))
                    err_db_conn.commit()
                    err_db_conn.close()
                except Exception as db_e:
                    print(f"Could not mark request {request_id} as error after worker crash: {db_e}")
            time.sleep(10)
        finally:
            if db_conn:
                db_conn.close()