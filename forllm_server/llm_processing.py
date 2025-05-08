import requests
import json
import time
import sqlite3
from .config import DATABASE, OLLAMA_GENERATE_URL, DEFAULT_MODEL, CURRENT_USER_ID

def process_llm_request(request_details):
    """Handles the actual LLM interaction for a given request."""
    request_id = request_details['request_id']
    post_id = request_details['post_id']
    # Get the currently selected model from settings
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row # Ensure dictionary-like rows
    settings_cursor = db_conn.cursor()
    settings_cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
    model_setting = settings_cursor.fetchone()
    db_conn.close()
    model = model_setting['setting_value'] if model_setting else DEFAULT_MODEL # Access by name

    # Persona handling remains basic for now
    persona = request_details.get('persona', 'default_persona')
    print(f"Processing request {request_id} for post {post_id} with selected model '{model}' and persona '{persona}'...")

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row # Ensure dictionary-like rows
    cursor = db.cursor()

    try:
        # 1. Get the content of the post to respond to (and maybe context)
        cursor.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,))
        original_post = cursor.fetchone()
        if not original_post:
            raise ValueError(f"Original post {post_id} not found.")

        prompt_content = f"User wrote: {original_post['content']}\n\nRespond to this post."
        # TODO: Add persona instructions and potentially more thread context later

        # 2. Call Ollama API
        print(f"Sending prompt to Ollama ({OLLAMA_GENERATE_URL}) for model '{model}'...")
        full_response_content = "" # Initialize before the try block for communication
        try:
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
            """, (CURRENT_USER_ID, post_id, full_response_content, model, persona, post_id))
            new_post_id = cursor.lastrowid
            print(f"Saved LLM response as post {new_post_id}")

            # 4. Update the status in llm_requests table to 'complete'
            cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            db.commit()
            print(f"Request {request_id} marked as complete.")

        except requests.exceptions.Timeout:
            print(f"Ollama API connection timed out after {initial_connection_timeout} seconds for request {request_id}.")
            raise Exception(f"Failed to connect to Ollama API within {initial_connection_timeout} seconds.")
        except requests.exceptions.RequestException as req_err:
            print(f"Ollama API request failed for request {request_id}: {req_err}")
            raise Exception(f"Failed to communicate with Ollama API: {req_err}") from req_err
        except TimeoutError as stream_timeout_err:
            print(f"Ollama streaming error for request {request_id}: {stream_timeout_err}")
            raise Exception(f"Ollama stream timed out: {stream_timeout_err}") from stream_timeout_err
        except json.JSONDecodeError as json_err:
             print(f"Error decoding JSON from Ollama stream for request {request_id}: {json_err}")
             raise Exception(f"Invalid JSON received from Ollama stream: {json_err}") from json_err
        except ValueError as val_err:
             print(f"Value error during Ollama processing for request {request_id}: {val_err}")
             raise Exception(f"Data error during Ollama processing: {val_err}") from val_err

    except Exception as e:
        print(f"Error processing request {request_id}: {e}")
        cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (str(e), request_id))
        db.commit()
    finally:
        db.close()