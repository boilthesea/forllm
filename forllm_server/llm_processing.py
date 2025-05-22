import requests
import json
import time
import sqlite3
from requests.exceptions import ConnectionError, RequestException
from datetime import datetime

# Removed sys.path manipulation and direct 'from forllm import app' import

from .config import DATABASE, OLLAMA_GENERATE_URL, DEFAULT_MODEL, CURRENT_USER_ID
from .database import get_persona 

def process_llm_request(request_details, flask_app): # Added flask_app parameter
    """Handles the actual LLM interaction for a given request."""
    request_id = request_details['request_id']
    post_id = request_details['post_id']
    
    # Establish DB connection for this request processing
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row 
    cursor = db.cursor()

    try:
        # --- Start of main logic block ---
        
        # Get selected model using local cursor
        cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
        model_setting = cursor.fetchone()
        model = model_setting['setting_value'] if model_setting else DEFAULT_MODEL

        # Persona ID handling (parsing)
        persona_id_str = request_details.get('persona')
        persona_id = None
        try:
            if persona_id_str is not None:
                persona_id = int(persona_id_str)
        except (ValueError, TypeError):
            print(f"Warning: Invalid persona_id ('{persona_id_str}') for request {request_id}. Using default fallback logic.")
            persona_id = None
        
        if persona_id is None and persona_id_str:
            print(f"Could not convert persona_id_str '{persona_id_str}' to int for request {request_id}. Default instructions will be used.")
        
        print(f"Processing request {request_id} for post {post_id} with selected model '{model}'. Attempting to use persona_id: '{persona_id_str}' (parsed as {persona_id}).")

        persona_instructions = "You are a helpful assistant." # Default
        
        # Fetch persona instructions *WITHIN APP CONTEXT* using flask_app
        with flask_app.app_context():
            if persona_id:
                persona_data = get_persona(persona_id) # get_persona uses Flask's g for DB
                if persona_data and persona_data['prompt_instructions']:
                    persona_instructions = persona_data['prompt_instructions']
                    print(f"Successfully fetched instructions for persona_id {persona_id} for request {request_id}.")
                else:
                    print(f"Warning: Could not fetch instructions for persona_id {persona_id} (or instructions were empty) for request {request_id}. Using default instructions.")
            else:
                print(f"No valid persona_id provided or parsed for request {request_id}. Using default instructions.")

        # Get original post content using local cursor
        cursor.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,))
        original_post = cursor.fetchone()
        if not original_post:
            # If original post not found, we need to log this and update request to error
            # This is a critical error before even trying Ollama or dummy.
            error_message = f"Original post {post_id} not found for request {request_id}."
            print(error_message)
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message, request_id))
            db.commit()
            return # Exit early, db will be closed in finally

        prompt_content = f"{persona_instructions}\n\nUser wrote: {original_post['content']}\n\nRespond to this post."
        print(f"Final prompt_content for request {request_id} (first 200 chars): {prompt_content[:200]}...")
        
        # Store the constructed prompt using local cursor
        cursor.execute("UPDATE llm_requests SET full_prompt_sent = ? WHERE request_id = ?", (prompt_content, request_id))
        db.commit()
        print(f"Stored full_prompt_sent for request_id {request_id}")
        print(f"DEBUG: Successfully committed full_prompt_sent for request {request_id}. Value snippet: '{prompt_content[:100]}...'")

        # --- Try/Except for Ollama connection and processing ---
        try:
            # 2. Call Ollama API
            print(f"Sending prompt to Ollama ({OLLAMA_GENERATE_URL}) for model '{model}'...")
            full_response_content = "" # Initialize before the try block for communication
            # Variables for streaming
            last_chunk_time = time.time()
            inter_chunk_timeout = 300 # Seconds between chunks before timeout
            initial_connection_timeout = 300 # Seconds for initial connection

            print(f"Sending streaming prompt to Ollama ({OLLAMA_GENERATE_URL}) for model '{model}'...")
            response = requests.post(
                OLLAMA_GENERATE_URL,
                json={'model': model, 'prompt': prompt_content, 'stream': True}, # Enable streaming
                headers={'Content-Type': 'application/json'},
                stream=True, # Required for iter_lines()
                timeout=initial_connection_timeout # Timeout for initial connection
            )
            response.raise_for_status() # Check for initial connection errors (4xx, 5xx)

            print(f"Connection established. Receiving stream for request {request_id}...")
            stream_done = False # Flag to track if 'done' was received
            for line in response.iter_lines():
                if line:
                    current_time = time.time()
                    # Check for inter-chunk timeout
                    if current_time - last_chunk_time > inter_chunk_timeout:
                        raise TimeoutError(f"Ollama response timed out after {inter_chunk_timeout} seconds of inactivity.")
                    last_chunk_time = current_time

                    try:
                        # Decode and parse the JSON chunk
                        chunk = json.loads(line.decode('utf-8'))
                        response_part = chunk.get('response', '')
                        full_response_content += response_part

                        if chunk.get('done', False):
                            print(f"Stream finished ('done': true) for request {request_id}.")
                            stream_done = True
                            break # Exit loop once Ollama signals completion
                    except json.JSONDecodeError:
                        print(f"Warning: Received non-JSON line from Ollama stream for request {request_id}: {line}")
                        continue

            if not stream_done:
                 print(f"Warning: Ollama stream ended for request {request_id} without receiving 'done': true.")
                 if not full_response_content:
                     raise ValueError("Ollama stream ended unexpectedly with no content and no 'done' flag.")
                 else:
                     print(f"Proceeding with content received ({len(full_response_content)} chars) despite missing 'done' flag.")

            print(f"Received complete response ({len(full_response_content)} chars) from Ollama for request {request_id}.")

            # 3. Save the LLM response to the posts table
            cursor.execute("""
                INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id)
                SELECT topic_id, ?, ?, ?, TRUE, ?, ?
                FROM posts WHERE post_id = ?
            """, (CURRENT_USER_ID, post_id, full_response_content, model, persona_id, post_id)) # Use persona_id here
            new_post_id = cursor.lastrowid
            print(f"Saved LLM response as post {new_post_id}")

            # 4. Update the status in llm_requests table to 'complete'
            cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            db.commit()
            print(f"Request {request_id} marked as complete.")

        except (ConnectionError, requests.exceptions.Timeout) as e: # Combined ConnectionError and Timeout
            print(f"Ollama connection failed or timed out: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
            _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app) # Pass flask_app
            # _dummy_llm_processor handles updating request status, so no 'raise' here unless _dummy_llm_processor itself fails
        except requests.exceptions.RequestException as e: # General RequestException
            print(f"Ollama API request failed: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
            _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app) # Pass flask_app
            # _dummy_llm_processor handles updating request status
        except TimeoutError as stream_timeout_err: # This is our custom timeout for stream inactivity
            print(f"Ollama streaming error for request {request_id}: {stream_timeout_err}")
            # For stream timeouts, we might still want to mark as error rather than use dummy,
            # as connection was made but stream broke. Or choose to use dummy. For now, let it be an error.
            raise Exception(f"Ollama stream timed out: {stream_timeout_err}") from stream_timeout_err
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON from Ollama stream for request {request_id}: {json_err}")
             raise Exception(f"Invalid JSON received from Ollama stream: {json_err}") from json_err
        except ValueError as val_err:
             print(f"Value error during Ollama processing for request {request_id}: {val_err}")
             raise Exception(f"Data error during Ollama processing: {val_err}") from val_err

    except Exception as e: # Outer catch for errors before Ollama/dummy call (e.g. DB error saving prompt)
        print(f"Error in process_llm_request before Ollama/dummy call for request {request_id}: {e}")
        # Update llm_requests to error status
        # db and cursor should still be valid here from the outer scope of process_llm_request
        cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Pre-processing error: {str(e)}", request_id))
        db.commit()
    finally:
        db.close()

# Changed signature to accept flask_app
def _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, db_path, flask_app):
    print(f"Dummy LLM processing request {request_id} for post {post_id} with model '{model}' and persona_id '{persona_id}'. Flask_app: {flask_app}")
    # prompt_content already includes persona instructions from the caller (process_llm_request)
    dummy_response_content = f"This is a dummy LLM response for post {post_id} using model {model} and persona_id {persona_id}. The intended prompt was: {prompt_content}"

    # _dummy_llm_processor uses its own DB connection as it might be called standalone
    # or from contexts where the main processor's DB isn't available/safe.
    dummy_db = None
    try:
        dummy_db = sqlite3.connect(db_path)
        dummy_db.row_factory = sqlite3.Row 
        dummy_cursor = dummy_db.cursor()

        # Save the dummy LLM response to the posts table
        dummy_cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id,))
        original_post_topic = dummy_cursor.fetchone()
        if not original_post_topic:
            error_message = f"Dummy LLM: Original post {post_id} not found, cannot determine topic_id."
            print(error_message)
            # Update llm_requests to error
            dummy_cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message, request_id))
            dummy_db.commit()
            return
        topic_id = original_post_topic['topic_id']

        dummy_cursor.execute(
            """
            INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, TRUE, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (topic_id, CURRENT_USER_ID, post_id, dummy_response_content, model, persona_id) 
        )
        new_post_id = dummy_cursor.lastrowid
        print(f"Dummy LLM response saved as post {new_post_id} for request {request_id}.")

        # Update the llm_requests table status to 'complete'
        dummy_cursor.execute(
            "UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP, error_message = NULL WHERE request_id = ?",
            (request_id,)
        )
        dummy_db.commit()
        print(f"Dummy request {request_id} marked as complete.")

    except Exception as e:
        error_message = f"Error in dummy LLM processor for request {request_id}: {str(e)}"
        print(error_message)
        if dummy_db: 
            try:
                # Ensure cursor is available for error update
                error_cursor = dummy_db.cursor()
                error_cursor.execute(
                    "UPDATE llm_requests SET status = 'error', processed_at = CURRENT_TIMESTAMP, error_message = ? WHERE request_id = ?",
                    (error_message, request_id)
                )
                dummy_db.commit()
            except Exception as db_error:
                print(f"Could not update LLM request status to error after dummy processor failure: {db_error}")
        else:
            print(f"Database connection (dummy_db) failed in dummy processor. Could not update request {request_id} status.")
    finally:
        if dummy_db:
            dummy_db.close()