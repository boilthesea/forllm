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
from .database import get_persona, get_post_ancestors, get_sibling_branch_roots, get_recent_posts_from_branch # Added new imports
from .ollama_utils import get_model_context_window # Added import

# Constants for branch-aware history
MAX_POSTS_PER_SIBLING_BRANCH = 2
MAX_TOTAL_AMBIENT_POSTS = 5
PRIMARY_HISTORY_BUDGET_RATIO = 0.7 # 70% for primary thread, 30% for ambient
AMBIENT_HISTORY_HEADER = "--- Other Recent Discussions ---"
PRIMARY_HISTORY_HEADER = "--- Current Conversation Thread ---"
FINAL_INSTRUCTION = "Respond to this post."


def _prune_history_string(history_string: str, max_tokens: int, logger_prefix: str, request_id: int) -> str:
    """Prunes a history string to fit within a token budget by removing oldest entries."""
    history_content_stripped = history_string.strip()
    if not history_content_stripped or count_tokens(history_content_stripped) <= max_tokens:
        return history_content_stripped # Return stripped version

    logger.info(f"{logger_prefix} Request {request_id}: History ({count_tokens(history_content_stripped)} tokens) exceeds budget ({max_tokens}). Pruning.")

    lines = history_content_stripped.split('\n')
    current_content = history_content_stripped

    while count_tokens(current_content) > max_tokens and lines:
        lines.pop(0)  # Remove the oldest line (first in the list)
        current_content = "\n".join(lines)

    final_tokens = count_tokens(current_content)
    if final_tokens > max_tokens:
        # This case implies that even a single line might be over budget, or all lines were removed and it's still an issue (e.g. max_tokens = 0)
        logger.warning(f"{logger_prefix} Request {request_id}: After removing lines, content ({final_tokens} tokens) might still be over budget ({max_tokens}), or became empty. Returning best effort.")
        if not lines: # All lines were removed, and it's still over (or max_tokens is very small)
             return "" # Return empty string if all lines removed and still not fitting (e.g. max_tokens=0)


    logger.info(f"{logger_prefix} Request {request_id}: After pruning, history token count: {final_tokens}. Budget: {max_tokens}.")
    return current_content


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
            model_specific_context = get_model_context_window(model, db)

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

        # --- Fetch Primary and Sibling Thread Posts ---
        ancestors = []
        primary_thread_post_ids = []
        topic_id = None

        if post_id: # post_id is the post_id_to_respond_to
            ancestors = get_post_ancestors(post_id, db) # Use existing db connection
            if ancestors:
                primary_thread_post_ids = [p['post_id'] for p in ancestors]
                if original_post: # original_post was fetched earlier
                    # Attempt to get topic_id from original_post (which is the post being responded to)
                    # This requires original_post to have topic_id, which it should if fetched from posts table.
                    # We need to ensure original_post is fetched in a way that gives topic_id.
                    # Let's re-fetch original_post to include topic_id, or get it from ancestors.
                    if ancestors: # If ancestors were fetched, the first one is the root of the current post_id's chain.
                                  # Or the last one, depending on order. get_post_ancestors returns them chronologically.
                                  # The current post (post_id) is the last in 'ancestors' if it includes itself,
                                  # or original_post is the direct child.
                                  # For this logic, we need topic_id of the post_id we are responding to.
                        cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id,))
                        current_post_topic_info = cursor.fetchone()
                        if current_post_topic_info:
                            topic_id = current_post_topic_info['topic_id']
                        else: # Fallback, should not happen if post_id is valid
                            logger.error(f"Request {request_id}: Could not fetch topic_id for current post {post_id}.")
                            # Handle error or set topic_id to None if critical
                else: # Should not happen if original_post was fetched successfully
                    logger.error(f"Request {request_id}: original_post is None, cannot determine topic_id reliably for ambient history.")


        ambient_posts = []
        if topic_id and primary_thread_post_ids: # Ensure we have a topic and primary thread to find siblings for
            logger.info(f"Request {request_id}: Fetching sibling branch roots for topic_id {topic_id}, excluding {len(primary_thread_post_ids)} primary thread posts.")
            sibling_branch_roots = get_sibling_branch_roots(topic_id, primary_thread_post_ids, db)
            logger.info(f"Request {request_id}: Found {len(sibling_branch_roots)} sibling branch root(s).")

            all_candidate_ambient_posts = []
            for root in sibling_branch_roots:
                logger.info(f"Request {request_id}: Fetching recent posts from sibling branch starting with root_id {root['post_id']}.")
                recent_from_branch = get_recent_posts_from_branch(root['post_id'], db, max_posts=MAX_POSTS_PER_SIBLING_BRANCH)
                all_candidate_ambient_posts.extend(recent_from_branch)
                logger.info(f"Request {request_id}: Fetched {len(recent_from_branch)} posts from branch {root['post_id']}. Total candidates: {len(all_candidate_ambient_posts)}.")

            # Sort all collected ambient posts by creation date (most recent first for truncation)
            all_candidate_ambient_posts.sort(key=lambda x: x['created_at'], reverse=True)

            # Limit to max_total_ambient_posts
            ambient_posts = all_candidate_ambient_posts[:MAX_TOTAL_AMBIENT_POSTS]
            # Reverse again to have them in chronological order (oldest first) for the prompt
            ambient_posts.reverse()
            logger.info(f"Request {request_id}: Selected {len(ambient_posts)} ambient posts after sorting and truncation (max_total_ambient_posts: {MAX_TOTAL_AMBIENT_POSTS}).")

        # --- Format History Strings ---
        # Ambient History
        formatted_ambient_history_string = ""
        if ambient_posts:
            ambient_history_parts = [AMBIENT_HISTORY_HEADER]
            for post in ambient_posts:
                author_prefix = "User"
                if post.get('is_llm_response'):
                    persona_name = "LLMAssistant" # Default if no persona
                    if post.get('llm_persona_id'):
                        # Fetch persona name (simplified, ideally use a helper or ensure get_persona takes connection)
                        p_cursor = db.cursor()
                        p_cursor.execute("SELECT name FROM personas WHERE persona_id = ?", (post['llm_persona_id'],))
                        p_row = p_cursor.fetchone()
                        if p_row: persona_name = p_row['name']
                    author_prefix = f"LLM ({persona_name})"
                ambient_history_parts.append(f"[From other thread by {author_prefix}]: {post.get('content', '')}")
            formatted_ambient_history_string = "\n".join(ambient_history_parts) + "\n\n" # Add spacing

        # Primary History
        formatted_primary_history_string = ""
        if ancestors: # ancestors are already fetched
            primary_history_content = format_linear_history(ancestors, db)
            if primary_history_content:
                formatted_primary_history_string = f"{PRIMARY_HISTORY_HEADER}\n{primary_history_content}\n\n"

        # --- Token Counting and Pruning ---
        safety_margin_percentage = 0.95
        max_allowed_tokens = int(effective_context_window * safety_margin_percentage)

        persona_prompt_tokens = count_tokens(persona_instructions)
        user_post_tokens = count_tokens(original_post['content'])
        attachments_token_count = count_tokens(attachments_string.strip())

        # --- Token Counting and Pruning ---
        safety_margin_percentage = 0.95
        max_allowed_tokens = int(effective_context_window * safety_margin_percentage)

        persona_prompt_tokens = count_tokens(persona_instructions)
        # IMPORTANT: The "User wrote: " prefix is added during final prompt assembly.
        # For fixed token calculation, use the raw content and the fixed instruction.
        user_post_content_for_count = original_post['content']
        user_post_tokens = count_tokens(user_post_content_for_count) # Token for user's actual message
        attachments_token_count = count_tokens(attachments_string.strip())

        # Calculate tokens for elements that are fixed and always present around the history
        # This includes persona, the user's current post, attachments, and the final instruction.
        # Headers are handled separately as their inclusion depends on whether history content exists.
        fixed_elements_tokens = count_tokens(
            f"{attachments_string}" # attachments_string has its own trailing \n\n if not empty
            f"{persona_instructions}\n\n"
            f"User wrote: {user_post_content_for_count}\n\n" # Add "User wrote: " prefix here for accurate fixed count
            f"{FINAL_INSTRUCTION}"
        )
        logger.info(f"Request {request_id}: Fixed elements (attachments, persona, User wrote: + user_post, final instruction) token count: {fixed_elements_tokens}")

        available_tokens_for_history_sections = max_allowed_tokens - fixed_elements_tokens
        if available_tokens_for_history_sections < 0:
            available_tokens_for_history_sections = 0
            logger.warning(f"Request {request_id}: Negative available_tokens_for_history_sections. Max allowed tokens might be too small or fixed elements too large.")
        logger.info(f"Request {request_id}: Max allowed: {max_allowed_tokens}, Fixed elements: {fixed_elements_tokens}, Available for all history sections (incl headers): {available_tokens_for_history_sections}")

        # --- Primary History Pruning ---
        raw_primary_content = ""
        if ancestors: # ancestors are already fetched
            raw_primary_content = format_linear_history(ancestors, db) # This is just the content, no header

        primary_header_tokens = 0
        if raw_primary_content: # Only add header if there's content to show
            primary_header_tokens = count_tokens(f"{PRIMARY_HISTORY_HEADER}\n\n")

        primary_content_budget = int(available_tokens_for_history_sections * PRIMARY_HISTORY_BUDGET_RATIO) - primary_header_tokens
        if primary_content_budget < 0: primary_content_budget = 0

        pruned_primary_content = _prune_history_string(raw_primary_content, primary_content_budget, "[PrimaryPrune]", request_id)
        final_primary_history_tokens = count_tokens(pruned_primary_content) # Tokens of content only

        formatted_primary_history_string_final = ""
        if pruned_primary_content:
            formatted_primary_history_string_final = f"{PRIMARY_HISTORY_HEADER}\n{pruned_primary_content}\n\n"
            final_primary_history_tokens += primary_header_tokens # Add header tokens to total if content exists
        logger.info(f"Request {request_id}: Primary content budget: {primary_content_budget}. Actual primary content tokens: {count_tokens(pruned_primary_content)}. With header: {final_primary_history_tokens}")

        # --- Ambient History Pruning ---
        tokens_used_by_primary_history_section = 0
        if pruned_primary_content: # If there's primary content, account for its tokens (content + header)
            tokens_used_by_primary_history_section = final_primary_history_tokens

        raw_ambient_content = ""
        if ambient_posts: # ambient_posts were fetched and processed earlier
            ambient_history_parts = [] # No header here yet
            for post in ambient_posts: # ambient_posts is already sorted chronologically
                author_prefix = "User"
                if post.get('is_llm_response'):
                    persona_name = "LLMAssistant"
                    if post.get('llm_persona_id'):
                        p_cursor = db.cursor()
                        p_cursor.execute("SELECT name FROM personas WHERE persona_id = ?", (post['llm_persona_id'],))
                        p_row = p_cursor.fetchone()
                        if p_row: persona_name = p_row['name']
                    author_prefix = f"LLM ({persona_name})"
                ambient_history_parts.append(f"[From other thread by {author_prefix}]: {post.get('content', '')}")
            raw_ambient_content = "\n".join(ambient_history_parts)

        ambient_header_tokens = 0
        if raw_ambient_content: # Only add header if there's content
            ambient_header_tokens = count_tokens(f"{AMBIENT_HISTORY_HEADER}\n\n")

        ambient_content_budget = available_tokens_for_history_sections - tokens_used_by_primary_history_section - ambient_header_tokens
        if ambient_content_budget < 0: ambient_content_budget = 0

        pruned_ambient_content = _prune_history_string(raw_ambient_content, ambient_content_budget, "[AmbientPrune]", request_id)
        final_ambient_history_tokens = count_tokens(pruned_ambient_content) # Tokens of content only

        formatted_ambient_history_string_final = ""
        if pruned_ambient_content:
            formatted_ambient_history_string_final = f"{AMBIENT_HISTORY_HEADER}\n{pruned_ambient_content}\n\n"
            final_ambient_history_tokens += ambient_header_tokens # Add header tokens to total if content exists
        logger.info(f"Request {request_id}: Ambient content budget: {ambient_content_budget}. Actual ambient content tokens: {count_tokens(pruned_ambient_content)}. With header: {final_ambient_history_tokens}")

        # --- Construct final prompt ---
        prompt_content = (
            f"{attachments_string}"
            f"{persona_instructions}\n\n"
            f"{formatted_ambient_history_string_final}" # Already has header and trailing \n\n if not empty
            f"{formatted_primary_history_string_final}" # Already has header and trailing \n\n if not empty
            f"User wrote: {user_post_content_for_count}\n\n" # Use the same content as counted
            f"{FINAL_INSTRUCTION}"
        )
        actual_final_prompt_tokens = count_tokens(prompt_content)
        logger.info(f"Request {request_id}: Final prompt constructed. Total tokens: {actual_final_prompt_tokens}. (First 200 chars: {prompt_content[:200]}...)")

        # --- Store Token Breakdown ---
        # Recalculate headers_tokens based on what was actually included
        headers_token_count_final = 0
        if pruned_primary_content: headers_token_count_final += primary_header_tokens
        if pruned_ambient_content: headers_token_count_final += ambient_header_tokens

        token_breakdown = {
            "persona_prompt_tokens": persona_prompt_tokens,
            "user_post_tokens": user_post_tokens, # This is for user_post_content_for_count
            "attachments_token_count": attachments_token_count,
            "primary_chat_history_tokens": count_tokens(pruned_primary_content), # Content only
            "ambient_chat_history_tokens": count_tokens(pruned_ambient_content), # Content only
            "headers_tokens": headers_token_count_final,
            "final_instruction_tokens": count_tokens(FINAL_INSTRUCTION),
            "total_prompt_tokens": actual_final_prompt_tokens
        }
        token_breakdown_json = json.dumps(token_breakdown)

        # Store the constructed prompt (potentially pruned) and token breakdown
        cursor.execute(
            "UPDATE llm_requests SET full_prompt_sent = ?, prompt_token_breakdown = ? WHERE request_id = ?",
            (prompt_content, token_breakdown_json, request_id)
        )
        db.commit()
        logger.info(f"Request {request_id}: Stored final (potentially pruned) prompt and token breakdown. Token breakdown: {token_breakdown_json}")
        # print statement for DEBUG might be too verbose if prompt is huge, consider prompt_content[:100]
        print(f"DEBUG: Successfully committed final prompt for request {request_id}. Pruned prompt snippet: '{prompt_content[:100]}...'")

        # --- Pre-flight Check Logic (runs on potentially pruned prompt) ---
        # max_allowed_tokens is already defined above
        logger.info(f"Request {request_id}: Pre-flight check (on potentially pruned prompt): Actual tokens: {actual_final_prompt_tokens}, Max allowed (after {safety_margin_percentage*100}% safety margin): {max_allowed_tokens} (Context: {effective_context_window})")

        if actual_final_prompt_tokens > max_allowed_tokens:
            error_message_for_db = f"Error: Prompt too long after assembly. Tokens: {actual_final_prompt_tokens}, Max Allowed (after safety margin): {max_allowed_tokens} (Context: {effective_context_window})."
            logger.error(f"Request {request_id}: {error_message_for_db}")
            cursor.execute(
                "UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?",
                (error_message_for_db, request_id)
            )
            db.commit()
            return # Return early from the function

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


def format_linear_history(posts: list, db_connection) -> str:
    """
    Formats a list of posts (e.g., from get_post_ancestors) into a linear string representation.

    Args:
        posts: A list of post dictionaries. Each post dictionary should have keys like
               'is_llm_response', 'content', 'llm_persona_id', 'llm_model_name'.
        db_connection: An active sqlite3 database connection.

    Returns:
        A string representing the formatted chat history.
    """
    history_str_parts = []
    for post in posts:
        if post.get('is_llm_response'):
            persona_name = "Unknown Persona"
            llm_persona_id = post.get('llm_persona_id')
            if llm_persona_id:
                # Fetch persona name using the provided db_connection
                # Assuming get_persona is adapted or a new function is created
                # that can use an existing connection.
                # For now, let's assume get_persona can be called if db_connection
                # is the one used by get_db() or if get_persona is modified.
                # This is a simplification for now.
                # A proper solution might involve get_persona(id, cursor=db_connection.cursor())
                # or passing g.db if in Flask context.
                # Direct use of db_connection with get_persona which uses g.db might conflict.
                # Let's make a direct query for simplicity here, assuming db_connection is usable.

                # Simpler approach: Direct query if get_persona is problematic with external db_connection
                cursor = db_connection.cursor()
                cursor.execute("SELECT name FROM personas WHERE persona_id = ?", (llm_persona_id,))
                persona_row = cursor.fetchone()
                if persona_row and persona_row['name']:
                    persona_name = persona_row['name']
                # No explicit close for cursor from passed connection

            model_name = post.get('llm_model_name', 'Unknown Model')
            history_str_parts.append(f"LLM ({persona_name}/{model_name}): {post.get('content', '')}")
        else:
            history_str_parts.append(f"User: {post.get('content', '')}")

    return "\n".join(history_str_parts)
