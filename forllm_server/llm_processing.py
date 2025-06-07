import requests
import json
import time
import sqlite3
import os # Added os
from flask import current_app # Added current_app
from requests.exceptions import ConnectionError, RequestException
from datetime import datetime
import logging # Added logging
from forllm_server.tokenizer_utils import count_tokens # Added count_tokens import

# Configure logging
logger = logging.getLogger(__name__)

# Removed sys.path manipulation and direct 'from forllm import app' import

from .config import DATABASE, OLLAMA_GENERATE_URL, DEFAULT_MODEL, CURRENT_USER_ID, UPLOAD_FOLDER # UPLOAD_FOLDER might not be needed if current_app.config is used
from .database import get_persona
from .ollama_utils import get_model_context_window # Added import

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
        
        # --- Model Selection Logic ---
        # Priority:
        # 1. Model specified in the request_details (from llm_requests.llm_model)
        # 2. Global default model from settings
        # 3. Hardcoded DEFAULT_MODEL
        requested_model = request_details.get('model') # From llm_requests.llm_model
        model_to_use = None

        if requested_model:
            model_to_use = requested_model
            print(f"Using model specified in LLM request: '{model_to_use}' for request {request_id}.")
        else:
            # Get global selected model from settings using local cursor
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_setting = cursor.fetchone()
            if model_setting and model_setting['setting_value']:
                model_to_use = model_setting['setting_value']
                print(f"No model in request, using global setting: '{model_to_use}' for request {request_id}.")
            else:
                model_to_use = DEFAULT_MODEL
                print(f"No model in request or global setting, using hardcoded DEFAULT_MODEL: '{model_to_use}' for request {request_id}.")
        
        model = model_to_use # Use 'model' variable hereafter as it's used later in the function.

        # --- Determine Effective Context Window ---
        effective_context_window = None
        model_specific_context = None

        logger.info(f"Request {request_id}: Attempting to fetch context window for model: {model} using ollama_utils...")
        with flask_app.app_context(): # Ensure app context for get_model_context_window
            # get_model_context_window from ollama_utils uses get_db() which relies on app context
            model_specific_context = get_model_context_window(model)

        if model_specific_context is not None:
            effective_context_window = model_specific_context
            logger.info(f"Request {request_id}: Using model-specific context window for {model}: {effective_context_window} tokens.")
        else:
            logger.warning(f"Request {request_id}: Could not retrieve model-specific context window for {model}. Attempting fallback from settings.")
            # Fetch from settings table using the local cursor from process_llm_request's db connection
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'default_llm_context_window'")
            fallback_setting = cursor.fetchone()
            if fallback_setting and fallback_setting['setting_value']:
                try:
                    effective_context_window = int(fallback_setting['setting_value'])
                    logger.info(f"Request {request_id}: Using fallback default LLM context window from settings: {effective_context_window} tokens.")
                except ValueError:
                    logger.error(f"Request {request_id}: Could not parse default_llm_context_window value '{fallback_setting['setting_value']}' as integer. Using hardcoded fallback.")
                    effective_context_window = 2048 # Hardcoded ultimate fallback
            else:
                logger.warning(f"Request {request_id}: default_llm_context_window not found in settings or value is null. Using hardcoded fallback.")
                effective_context_window = 2048 # Hardcoded ultimate fallback

        logger.info(f"Request {request_id}: Final effective context window for model {model} is {effective_context_window} tokens.")

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
            error_message = f"Original post {post_id} not found for request {request_id}."
            print(error_message)
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message, request_id))
            db.commit()
            return

        # --- Fetch and format attachments ---
        attachments_text_parts = []
        # Need app_context to access current_app.config['UPLOAD_FOLDER']
        with flask_app.app_context():
            upload_folder_path = current_app.config.get('UPLOAD_FOLDER')
            if not upload_folder_path:
                print(f"Error: UPLOAD_FOLDER not configured in Flask app for request {request_id}. Cannot process attachments.")
            else:
                print(f"[DEBUG AttachmentFetch] Attempting to fetch attachments for post_id: {post_id}") # post_id here is post_id_to_respond_to
                cursor.execute("""
                    SELECT filename, filepath, user_prompt, order_in_post
                    FROM attachments
                    WHERE post_id = ?
                    ORDER BY order_in_post ASC
                """, (post_id,)) # post_id here is post_id_to_respond_to
                attachments_raw = cursor.fetchall()
                
                # Convert Row objects to dictionaries for easier logging/processing if needed, or just log raw
                attachments_list_for_log = [dict(row) for row in attachments_raw]
                print(f"[DEBUG AttachmentFetch] Found attachments for post_id {post_id}: {attachments_list_for_log}")


                if attachments_raw: # Check attachments_raw instead of attachments
                    print(f"Found {len(attachments_raw)} attachments for post {post_id} (request {request_id}). Processing...")
                    for att in attachments_raw: # Iterate over attachments_raw
                        attachment_filename = att['filename']
                        attachment_filepath_relative = att['filepath']
                        attachment_user_prompt = att['user_prompt'] if att['user_prompt'] else 'Associated file content.'
                        
                        full_filepath = os.path.join(upload_folder_path, attachment_filepath_relative)
                        file_content = ""
                        try:
                            with open(full_filepath, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                            print(f"Successfully read content of attachment: {attachment_filename} for post {post_id}.")
                        except FileNotFoundError:
                            file_content = "Error: File content not found."
                            print(f"Error: Attachment file not found at {full_filepath} for post {post_id}.")
                        except Exception as e:
                            file_content = f"Error reading file: {str(e)}"
                            print(f"Error reading attachment file {full_filepath} for post {post_id}: {e}")

                        attachments_text_parts.append(
                            f"--- BEGIN ATTACHED FILE ---\n"
                            f"Filename: {attachment_filename}\n"
                            f"User prompt: {attachment_user_prompt}\n"
                            f"Content:\n{file_content}\n"
                            f"--- END ATTACHED FILE ---"
                        )
                else:
                    print(f"No attachments found for post {post_id} (request {request_id}).")
        
        attachments_string = "\n\n".join(attachments_text_parts)
        if attachments_string:
            attachments_string += "\n\n" # Add trailing newlines if there were attachments

        # --- Construct final prompt ---
        # Attachments first, then persona instructions, then user's post
        prompt_content = f"{attachments_string}{persona_instructions}\n\nUser wrote: {original_post['content']}\n\nRespond to this post."
        print(f"Final prompt_content for request {request_id} (first 200 chars): {prompt_content[:200]}...")

        # Token counting and logging
        # Assuming no separate system prompt, persona_instructions acts as the main system/persona guidance
        persona_prompt_tokens = count_tokens(persona_instructions)
        logger.info(f"Request {request_id}: Persona instructions token count: {persona_prompt_tokens}")

        user_post_content = original_post['content']
        user_post_tokens = count_tokens(user_post_content)
        logger.info(f"Request {request_id}: User post content token count: {user_post_tokens}")

        attachments_token_count = 0
        if attachments_string: # Check if there's any text from attachments
            attachments_token_count = count_tokens(attachments_string)
            logger.info(f"Request {request_id}: Attachments text token count: {attachments_token_count}")

        # Log the token count of the actual final prompt string sent to the LLM
        actual_final_prompt_tokens = count_tokens(prompt_content)
        logger.info(f"Request {request_id}: Actual final prompt string token count: {actual_final_prompt_tokens}")
        
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