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

# Default constants for branch-aware history (used as fallbacks)
DEFAULT_MAX_POSTS_PER_SIBLING_BRANCH = 2
DEFAULT_MAX_TOTAL_AMBIENT_POSTS = 5
DEFAULT_PRIMARY_HISTORY_BUDGET_RATIO = 0.7 # 70% for primary thread, 30% for ambient

AMBIENT_HISTORY_HEADER = "--- Other Recent Discussions ---"
PRIMARY_HISTORY_HEADER = "--- Current Conversation Thread ---"
FINAL_INSTRUCTION = "Respond to this post."


def get_chat_history_settings(db_conn: sqlite3.Connection) -> dict:
    """
    Fetches chat history configuration from the settings table.
    Uses hardcoded defaults if settings are not found or invalid.
    """
    settings = {
        'max_posts_per_sibling_branch': DEFAULT_MAX_POSTS_PER_SIBLING_BRANCH,
        'max_total_ambient_posts': DEFAULT_MAX_TOTAL_AMBIENT_POSTS,
        'primary_history_budget_ratio': DEFAULT_PRIMARY_HISTORY_BUDGET_RATIO,
    }
    try:
        cursor = db_conn.cursor()
        keys = [
            'ch_max_posts_per_sibling_branch',
            'ch_max_ambient_posts',
            'ch_primary_history_budget_ratio'
        ]
        placeholders = ','.join('?' for _ in keys)
        query = f"SELECT setting_key, setting_value FROM settings WHERE setting_key IN ({placeholders})"
        cursor.execute(query, tuple(keys))
        db_settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

        # Process ch_max_posts_per_sibling_branch
        raw_val = db_settings.get('ch_max_posts_per_sibling_branch')
        if raw_val is not None:
            try:
                settings['max_posts_per_sibling_branch'] = int(raw_val)
                if settings['max_posts_per_sibling_branch'] < 0:
                    settings['max_posts_per_sibling_branch'] = DEFAULT_MAX_POSTS_PER_SIBLING_BRANCH
                    logger.warning("Fetched 'ch_max_posts_per_sibling_branch' is negative, using default.")
            except ValueError:
                logger.warning(f"Invalid value for 'ch_max_posts_per_sibling_branch': {raw_val}. Using default.")

        # Process ch_max_ambient_posts
        raw_val = db_settings.get('ch_max_ambient_posts')
        if raw_val is not None:
            try:
                settings['max_total_ambient_posts'] = int(raw_val)
                if settings['max_total_ambient_posts'] < 0:
                    settings['max_total_ambient_posts'] = DEFAULT_MAX_TOTAL_AMBIENT_POSTS
                    logger.warning("Fetched 'ch_max_ambient_posts' is negative, using default.")
            except ValueError:
                logger.warning(f"Invalid value for 'ch_max_ambient_posts': {raw_val}. Using default.")

        # Process ch_primary_history_budget_ratio
        raw_val = db_settings.get('ch_primary_history_budget_ratio')
        if raw_val is not None:
            try:
                ratio = float(raw_val)
                if 0.0 <= ratio <= 1.0:
                    settings['primary_history_budget_ratio'] = ratio
                else:
                    logger.warning(f"Fetched 'ch_primary_history_budget_ratio' ({ratio}) out of range [0,1], using default.")
            except ValueError:
                logger.warning(f"Invalid value for 'ch_primary_history_budget_ratio': {raw_val}. Using default.")

    except sqlite3.Error as e:
        logger.error(f"Database error fetching chat history settings: {e}. Using defaults.")

    logger.info(f"Chat history settings loaded: {settings}")
    return settings


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
            persona_name = "Unknown Persona" # Default if no persona
            llm_persona_id = post.get('llm_persona_id')
            if llm_persona_id:
                cursor = db_connection.cursor()
                cursor.execute("SELECT name FROM personas WHERE persona_id = ?", (llm_persona_id,))
                persona_row = cursor.fetchone()
                if persona_row and persona_row['name']:
                    persona_name = persona_row['name']

            # llm_model_name is not directly available in 'posts' from get_post_ancestors or get_recent_posts_from_branch
            # It usually comes from llm_requests or by joining with posts that are LLM responses.
            # For history formatting, we might need to adjust what's passed or how it's fetched.
            # Assuming 'llm_model_id' might be available and we can fetch name, or use a placeholder.
            # For now, let's use a placeholder if 'llm_model_name' isn't directly in post dict.
            model_name = post.get('llm_model_name', post.get('llm_model_id', 'LLM')) # Use llm_model_id as fallback
            history_str_parts.append(f"LLM ({persona_name}/{model_name}): {post.get('content', '')}")
        else:
            # Non-LLM posts are assumed to be from 'User'
            # User's name/alias is not stored per-post in a simple way in the current schema.
            # Using a generic "User" for now.
            history_str_parts.append(f"User: {post.get('content', '')}")

    return "\n".join(history_str_parts)


def _get_raw_history_strings(post_id_to_respond_to: int, db_conn: sqlite3.Connection, current_post_topic_id: int = None):
    """
    Fetches and formats raw primary and ambient history content, without headers.
    Args:
        post_id_to_respond_to: The ID of the post for which history is being constructed.
                               If None, implies a new topic (empty history).
        db_conn: Active database connection.
        current_post_topic_id: Optional. The topic_id of the post_id_to_respond_to.
                               If not provided, it will be fetched.
    Returns:
        A tuple (raw_primary_history_content_str, raw_ambient_history_content_str)
    """
    raw_primary_history_content = ""
    raw_ambient_history_content = ""
    primary_thread_post_ids_for_ambient_exclusion = [] # Store IDs of posts in the primary thread

    if not post_id_to_respond_to: # New topic or no parent
        return "", ""

    # 1. Primary History
    ancestors = get_post_ancestors(post_id_to_respond_to, db_conn)
    if ancestors:
        raw_primary_history_content = format_linear_history(ancestors, db_conn)
        primary_thread_post_ids_for_ambient_exclusion = [p['post_id'] for p in ancestors]
        # Also include the current post being responded to, as it's part of the "primary thread" contextually.
        primary_thread_post_ids_for_ambient_exclusion.append(post_id_to_respond_to)


    # 2. Ambient History
    topic_id_for_ambient = current_post_topic_id
    if not topic_id_for_ambient:
        cursor = db_conn.cursor()
        cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id_to_respond_to,))
        topic_info = cursor.fetchone()
        if topic_info:
            topic_id_for_ambient = topic_info['topic_id']
        else:
            logger.error(f"Could not fetch topic_id for post {post_id_to_respond_to} for ambient history.")
            return raw_primary_history_content, "" # Return what we have

    if topic_id_for_ambient:
        # Fetch chat history settings
        ch_settings = get_chat_history_settings(db_conn)
        max_posts_per_sibling = ch_settings['max_posts_per_sibling_branch']
        max_total_ambient = ch_settings['max_total_ambient_posts']

        # Exclude all posts from the direct ancestral line AND the current post itself
        # from being considered as roots for "ambient" branches.
        sibling_branch_roots = get_sibling_branch_roots(topic_id_for_ambient, primary_thread_post_ids_for_ambient_exclusion, db_conn)

        all_candidate_ambient_posts = []
        if max_total_ambient > 0 and max_posts_per_sibling > 0: # Only fetch if settings allow
            for root in sibling_branch_roots:
                recent_from_branch = get_recent_posts_from_branch(root['post_id'], db_conn, max_posts=max_posts_per_sibling)
                all_candidate_ambient_posts.extend(recent_from_branch)

            all_candidate_ambient_posts.sort(key=lambda x: x['created_at'], reverse=True)
            selected_ambient_posts = all_candidate_ambient_posts[:max_total_ambient]
            selected_ambient_posts.reverse() # Chronological order for prompt
        else:
            selected_ambient_posts = [] # Ensure it's an empty list if ambient history is disabled by settings

        if selected_ambient_posts:
            ambient_history_parts = []
            for post in selected_ambient_posts:
                author_prefix = "User"
                if post.get('is_llm_response'):
                    persona_name = "LLMAssistant"
                    if post.get('llm_persona_id'):
                        p_cursor = db_conn.cursor()
                        p_cursor.execute("SELECT name FROM personas WHERE persona_id = ?", (post['llm_persona_id'],))
                        p_row = p_cursor.fetchone()
                        if p_row: persona_name = p_row['name']
                    # Similar to format_linear_history, model name might not be directly available
                    model_name = post.get('llm_model_name', post.get('llm_model_id', 'LLM'))
                    author_prefix = f"LLM ({persona_name}/{model_name})"
                ambient_history_parts.append(f"[From other thread by {author_prefix}]: {post.get('content', '')}")
            raw_ambient_history_content = "\n".join(ambient_history_parts)

    return raw_primary_history_content, raw_ambient_history_content


def _prune_history_sections(
    raw_primary_content: str,
    raw_ambient_content: str,
    available_tokens_for_history: int,
    primary_history_budget_ratio: float,
    primary_header_template: str, # e.g., "--- Primary ---\n\n"
    ambient_header_template: str, # e.g., "--- Ambient ---\n\n"
    request_id_for_logging: str # For logger messages
) -> dict:
    """
    Prunes primary and ambient history content to fit within token budgets.
    Calculates final token counts including headers.

    Returns a dictionary containing:
        - pruned_primary_content_str (str): Content only, after pruning.
        - pruned_ambient_content_str (str): Content only, after pruning.
        - final_primary_history_tokens (int): Tokens of content + header (if content exists).
        - final_ambient_history_tokens (int): Tokens of content + header (if content exists).
        - primary_header_tokens (int): Tokens for the primary header (0 if no primary content).
        - ambient_header_tokens (int): Tokens for the ambient header (0 if no ambient content).
        - formatted_primary_history_string_with_header (str): Header + content, or "" if no content.
        - formatted_ambient_history_string_with_header (str): Header + content, or "" if no content.
    """

    # 1. Calculate potential header tokens
    actual_primary_header_tokens = 0
    if raw_primary_content: # Only consider adding header if there's content
        actual_primary_header_tokens = count_tokens(primary_header_template)

    actual_ambient_header_tokens = 0
    if raw_ambient_content: # Only consider adding header if there's content
        actual_ambient_header_tokens = count_tokens(ambient_header_template)

    # 2. Primary History Pruning
    # Budget for primary content tokens = (total available * ratio) - tokens for its own header
    primary_content_budget = int(available_tokens_for_history * primary_history_budget_ratio) - actual_primary_header_tokens
    if primary_content_budget < 0:
        primary_content_budget = 0

    pruned_primary_content_str = _prune_history_string(raw_primary_content, primary_content_budget, "[PrimaryPrune]", request_id_for_logging)

    final_primary_history_tokens_inc_header = 0
    formatted_primary_history_string_with_header = ""
    if pruned_primary_content_str:
        formatted_primary_history_string_with_header = f"{primary_header_template}{pruned_primary_content_str}"
        # Ensure no double \n\n if header already ends with it.
        # The templates are expected to include their own desired spacing, e.g. "HEADER\n\n"
        final_primary_history_tokens_inc_header = count_tokens(formatted_primary_history_string_with_header)
    else: # No primary content after pruning (or initially)
        actual_primary_header_tokens = 0 # No header if no content

    logger.info(f"Request {request_id_for_logging}: Primary content budget: {primary_content_budget}. Pruned primary content tokens (excl header): {count_tokens(pruned_primary_content_str)}. With header: {final_primary_history_tokens_inc_header}")

    # 3. Ambient History Pruning
    # Budget for ambient content tokens = (total available - tokens actually used by primary section (content+header)) - tokens for its own header
    tokens_used_by_primary_section_final = final_primary_history_tokens_inc_header # This includes primary header if primary content exists

    ambient_content_budget = available_tokens_for_history - tokens_used_by_primary_section_final - actual_ambient_header_tokens
    if ambient_content_budget < 0:
        ambient_content_budget = 0

    pruned_ambient_content_str = _prune_history_string(raw_ambient_content, ambient_content_budget, "[AmbientPrune]", request_id_for_logging)

    final_ambient_history_tokens_inc_header = 0
    formatted_ambient_history_string_with_header = ""
    if pruned_ambient_content_str:
        formatted_ambient_history_string_with_header = f"{ambient_header_template}{pruned_ambient_content_str}"
        final_ambient_history_tokens_inc_header = count_tokens(formatted_ambient_history_string_with_header)
    else: # No ambient content
        actual_ambient_header_tokens = 0 # No header if no content

    logger.info(f"Request {request_id_for_logging}: Ambient content budget: {ambient_content_budget}. Pruned ambient content tokens (excl header): {count_tokens(pruned_ambient_content_str)}. With header: {final_ambient_history_tokens_inc_header}")

    return {
        "pruned_primary_content_str": pruned_primary_content_str,
        "pruned_ambient_content_str": pruned_ambient_content_str,
        "final_primary_history_tokens": final_primary_history_tokens_inc_header, # Content + Header
        "final_ambient_history_tokens": final_ambient_history_tokens_inc_header, # Content + Header
        "primary_header_tokens": actual_primary_header_tokens, # Just header tokens, if content exists
        "ambient_header_tokens": actual_ambient_header_tokens, # Just header tokens, if content exists
        "formatted_primary_history_string_with_header": formatted_primary_history_string_with_header,
        "formatted_ambient_history_string_with_header": formatted_ambient_history_string_with_header,
    }


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

        # --- Determine topic_id for ambient history if not already known ---
        # This is needed for _get_raw_history_strings
        topic_id_for_history = None
        if post_id: # post_id is the post_id_to_respond_to
            cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id,))
            current_post_topic_info = cursor.fetchone()
            if current_post_topic_info:
                topic_id_for_history = current_post_topic_info['topic_id']
            else:
                logger.error(f"Request {request_id}: Could not fetch topic_id for current post {post_id} for history construction.")
                # Handle error or proceed with topic_id_for_history as None (which _get_raw_history_strings can handle)

        # --- Get Raw History Strings ---
        # request_id is used for logging within _get_raw_history_strings if it's adapted to accept it,
        # or we rely on its internal logging. For now, it doesn't take request_id.
        raw_primary_content, raw_ambient_content = _get_raw_history_strings(post_id, db, topic_id_for_history)
        logger.info(f"Request {request_id}: Raw primary history ({count_tokens(raw_primary_content)} tokens), Raw ambient history ({count_tokens(raw_ambient_content)} tokens)")

        # --- Token Counting and Pruning --- (This section will be largely replaced by _prune_history_sections)
        safety_margin_percentage = 0.95
        max_allowed_tokens = int(effective_context_window * safety_margin_percentage)

        persona_prompt_tokens = count_tokens(persona_instructions)
        user_post_tokens = count_tokens(original_post['content'])
        attachments_token_count = count_tokens(attachments_string.strip())

        safety_margin_percentage = 0.95
        max_allowed_tokens = int(effective_context_window * safety_margin_percentage)

        persona_prompt_tokens = count_tokens(persona_instructions)
        user_post_content_for_count = original_post['content'] # Content of the post being responded to
        user_post_tokens = count_tokens(user_post_content_for_count)
        attachments_token_count = count_tokens(attachments_string.strip())
        final_instruction_tokens = count_tokens(FINAL_INSTRUCTION)

        # Calculate tokens for fixed elements (persona, current post, attachments, final instruction)
        # Note: The "User wrote: " prefix for the current post and the "\n\n" separators are part of this fixed budget.
        fixed_elements_tokens = count_tokens(
            f"{attachments_string}" # Has its own trailing \n\n if not empty
            f"{persona_instructions}\n\n"
            f"User wrote: {user_post_content_for_count}\n\n"
            f"{FINAL_INSTRUCTION}"
        )
        logger.info(f"Request {request_id}: Fixed elements (attachments, persona, current post with prefix, final instruction) token count: {fixed_elements_tokens}")

        available_tokens_for_history_sections = max_allowed_tokens - fixed_elements_tokens
        if available_tokens_for_history_sections < 0:
            available_tokens_for_history_sections = 0
            logger.warning(f"Request {request_id}: Negative available_tokens_for_history_sections. Max allowed: {max_allowed_tokens}, Fixed elements: {fixed_elements_tokens}.")

        logger.info(f"Request {request_id}: Max allowed (incl safety margin): {max_allowed_tokens}. Available for all history (content + headers): {available_tokens_for_history_sections}")

        # --- Prune History Sections ---
        # Fetch primary_history_budget_ratio from settings for this specific call
        # Note: _get_raw_history_strings already uses its part of ch_settings internally.
        # Here we need the ratio for _prune_history_sections.
        # process_llm_request's db connection `db` is passed as `cursor.connection` if cursor is used, or just `db` if it's the connection.
        # Assuming `db` is the connection object here.
        ch_settings_for_pruning = get_chat_history_settings(db)
        current_primary_history_budget_ratio = ch_settings_for_pruning['primary_history_budget_ratio']

        pruning_results = _prune_history_sections(
            raw_primary_content=raw_primary_content,
            raw_ambient_content=raw_ambient_content,
            available_tokens_for_history=available_tokens_for_history_sections,
            primary_history_budget_ratio=current_primary_history_budget_ratio, # Use fetched setting
            primary_header_template=f"{PRIMARY_HISTORY_HEADER}\n\n",
            ambient_header_template=f"{AMBIENT_HISTORY_HEADER}\n\n",
            request_id_for_logging=str(request_id) # Ensure request_id is string for logging consistency
        )

        formatted_primary_history_string_final = pruning_results["formatted_primary_history_string_with_header"]
        formatted_ambient_history_string_final = pruning_results["formatted_ambient_history_string_with_header"]

        # --- Construct final prompt ---
        # The "User wrote: ..." line is removed as per the bug fix.
        # It's assumed that the content of the current post (user_post_content_for_count)
        # is already included at the end of formatted_primary_history_string_final,
        # formatted as "User: {user_post_content_for_count}".
        prompt_content = (
            f"{attachments_string}"  # Already has \n\n if not empty
            f"{persona_instructions}\n\n"
            f"{formatted_ambient_history_string_final}" # From pruning_results, includes header and content if any
            f"{formatted_primary_history_string_final}" # From pruning_results, includes header and content if any
            # f"User wrote: {user_post_content_for_count}\n\n" # This line is removed.
            f"{FINAL_INSTRUCTION}"
        )
        # Ensure there's appropriate spacing if formatted_primary_history_string_final is not empty
        # and before FINAL_INSTRUCTION.
        # If formatted_primary_history_string_final ends with \n\n, this is fine.
        # If it ends with content then \n, we might need an extra \n.
        # Assuming formatted_primary_history_string_final provides its own appropriate trailing newlines if it has content.
        # If formatted_primary_history_string_final is empty, persona_instructions should have \n\n.
        # If both are empty, attachments_string should have \n\n.
        # The FINAL_INSTRUCTION is appended directly. If the preceding part ends correctly, this is fine.

        # Re-evaluating spacing:
        # persona_instructions is followed by \n\n.
        # formatted_ambient_history_string_final, if present, contains its header (e.g., "...\n\n") and content.
        # formatted_primary_history_string_final, if present, contains its header (e.g., "...\n\n") and content.
        # If primary history is present and contains the user's current post, it would be like:
        # ...
        # User: current post content
        # FINAL_INSTRUCTION
        # This needs a newline between "User: current post content" and "FINAL_INSTRUCTION".

        # Let's adjust:
        # The formatted history strings from _prune_history_sections are:
        # `formatted_primary_history_string_with_header` (Header + Content)
        # `formatted_ambient_history_string_with_header` (Header + Content)
        # `format_linear_history` joins posts with "\n".
        # So, the last line of `formatted_primary_history_string_final` (if it contains the user post)
        # will be "User: content" without a trailing newline.

        # Revised prompt construction:
        prompt_parts = []
        if attachments_string: # attachments_string includes its own trailing \n\n if not empty
            prompt_parts.append(attachments_string)
        
        prompt_parts.append(f"{persona_instructions}\n\n")

        if formatted_ambient_history_string_final: # This string includes its own header \n\n and content
            prompt_parts.append(formatted_ambient_history_string_final)
            if not formatted_ambient_history_string_final.endswith("\n\n"):
                # This case should ideally not happen if headers are defined with \n\n
                # and content is appended after. For safety:
                if formatted_ambient_history_string_final.endswith("\n"):
                    prompt_parts.append("\n") 
                else:
                    prompt_parts.append("\n\n")


        if formatted_primary_history_string_final: # This string includes its own header \n\n and content
            prompt_parts.append(formatted_primary_history_string_final)
            # If the primary history (which now contains the "User: current post") does not end with \n\n,
            # we need to add spacing before FINAL_INSTRUCTION.
            # format_linear_history joins lines with \n. So the last post will be "User: content"
            # and formatted_primary_history_string_final will be "HEADER\n\n...old content\nUser: current content"
            if not formatted_primary_history_string_final.endswith("\n"):
                 prompt_parts.append("\n") # Add one newline to separate from FINAL_INSTRUCTION
            prompt_parts.append("\n") # Add another newline for a blank line separation
        else:
            # If there's no primary history (e.g., first post in topic, and get_post_ancestors correctly returned current post)
            # then persona_instructions already added \n\n.
            # This 'else' might not be necessary if the assumption holds that formatted_primary_history_string_final
            # *will* contain the user's post.
            # If formatted_primary_history_string_final could be empty AND the user's post is NOT in it,
            # then removing "User wrote:" is a bug.
            # Given the task is to remove "User wrote:" and keep "User:", the assumption is strong.
            pass


        prompt_parts.append(FINAL_INSTRUCTION)
        prompt_content = "".join(prompt_parts)

        actual_final_prompt_tokens = count_tokens(prompt_content)
        logger.info(f"Request {request_id}: Final prompt constructed. Total tokens: {actual_final_prompt_tokens}. (First 200 chars: {prompt_content[:200]}...)")

        # --- Store Token Breakdown ---
        token_breakdown = {
            "persona_prompt_tokens": persona_prompt_tokens,
            "user_post_tokens": user_post_tokens,
            "attachments_token_count": attachments_token_count,
            "primary_chat_history_tokens": count_tokens(pruning_results["pruned_primary_content_str"]), # Content only
            "ambient_chat_history_tokens": count_tokens(pruning_results["pruned_ambient_content_str"]), # Content only
            "headers_tokens": pruning_results["primary_header_tokens"] + pruning_results["ambient_header_tokens"],
            "final_instruction_tokens": final_instruction_tokens,
            "total_prompt_tokens": actual_final_prompt_tokens
        }
        token_breakdown_json = json.dumps(token_breakdown)

        cursor.execute(
            "UPDATE llm_requests SET full_prompt_sent = ?, prompt_token_breakdown = ? WHERE request_id = ?",
            (prompt_content, token_breakdown_json, request_id)
        )
        db.commit()
        logger.info(f"Request {request_id}: Stored final prompt and token breakdown. Breakdown: {token_breakdown_json}")
        print(f"DEBUG: Successfully committed final prompt for request {request_id}. Snippet: '{prompt_content[:100]}...'")

        # --- Pre-flight Check Logic ---
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
