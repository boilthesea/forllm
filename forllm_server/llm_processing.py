import requests
import json
import time
import sqlite3
import os
from flask import current_app
from requests.exceptions import ConnectionError, RequestException
from datetime import datetime
import logging
from forllm_server.tokenizer_utils import count_tokens

# Configure logging
logger = logging.getLogger(__name__)

from .config import DATABASE, OLLAMA_GENERATE_URL, DEFAULT_MODEL, CURRENT_USER_ID, UPLOAD_FOLDER
from .database import get_persona, get_post_ancestors, get_sibling_branch_roots, get_recent_posts_from_branch
from .ollama_utils import get_model_context_window

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
            model_name = post.get('llm_model_name', post.get('llm_model_id', 'LLM'))
            history_str_parts.append(f"LLM ({persona_name}/{model_name}): {post.get('content', '')}")
        else:
            history_str_parts.append(f"User: {post.get('content', '')}")

    return "\n".join(history_str_parts)


def _get_raw_history_strings(post_id_to_respond_to: int, db_conn: sqlite3.Connection, current_post_topic_id: int = None):
    """
    Fetches and formats raw primary and ambient history content, without headers.
    """
    raw_primary_history_content = ""
    raw_ambient_history_content = ""
    primary_thread_post_ids_for_ambient_exclusion = []

    if not post_id_to_respond_to:
        return "", ""

    ancestors = get_post_ancestors(post_id_to_respond_to, db_conn)
    if ancestors:
        raw_primary_history_content = format_linear_history(ancestors, db_conn)
        primary_thread_post_ids_for_ambient_exclusion = [p['post_id'] for p in ancestors]
        primary_thread_post_ids_for_ambient_exclusion.append(post_id_to_respond_to)

    topic_id_for_ambient = current_post_topic_id
    if not topic_id_for_ambient:
        cursor = db_conn.cursor()
        cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id_to_respond_to,))
        topic_info = cursor.fetchone()
        if topic_info:
            topic_id_for_ambient = topic_info['topic_id']
        else:
            logger.error(f"Could not fetch topic_id for post {post_id_to_respond_to} for ambient history.")
            return raw_primary_history_content, ""

    if topic_id_for_ambient:
        ch_settings = get_chat_history_settings(db_conn)
        max_posts_per_sibling = ch_settings['max_posts_per_sibling_branch']
        max_total_ambient = ch_settings['max_total_ambient_posts']

        sibling_branch_roots = get_sibling_branch_roots(topic_id_for_ambient, primary_thread_post_ids_for_ambient_exclusion, db_conn)

        all_candidate_ambient_posts = []
        if max_total_ambient > 0 and max_posts_per_sibling > 0:
            for root in sibling_branch_roots:
                recent_from_branch = get_recent_posts_from_branch(root['post_id'], db_conn, max_posts=max_posts_per_sibling)
                all_candidate_ambient_posts.extend(recent_from_branch)

            all_candidate_ambient_posts.sort(key=lambda x: x['created_at'], reverse=True)
            selected_ambient_posts = all_candidate_ambient_posts[:max_total_ambient]
            selected_ambient_posts.reverse()
        else:
            selected_ambient_posts = []

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
    primary_header_template: str,
    ambient_header_template: str,
    request_id_for_logging: str
) -> dict:
    """
    Prunes primary and ambient history content to fit within token budgets.
    """
    actual_primary_header_tokens = count_tokens(primary_header_template) if raw_primary_content else 0
    actual_ambient_header_tokens = count_tokens(ambient_header_template) if raw_ambient_content else 0

    primary_content_budget = int(available_tokens_for_history * primary_history_budget_ratio) - actual_primary_header_tokens
    primary_content_budget = max(0, primary_content_budget)
    pruned_primary_content_str = _prune_history_string(raw_primary_content, primary_content_budget, "[PrimaryPrune]", request_id_for_logging)

    final_primary_history_tokens_inc_header = 0
    formatted_primary_history_string_with_header = ""
    if pruned_primary_content_str:
        formatted_primary_history_string_with_header = f"{primary_header_template}{pruned_primary_content_str}"
        final_primary_history_tokens_inc_header = count_tokens(formatted_primary_history_string_with_header)
    else:
        actual_primary_header_tokens = 0

    logger.info(f"Request {request_id_for_logging}: Primary content budget: {primary_content_budget}. Pruned primary content tokens (excl header): {count_tokens(pruned_primary_content_str)}. With header: {final_primary_history_tokens_inc_header}")

    tokens_used_by_primary_section_final = final_primary_history_tokens_inc_header
    ambient_content_budget = available_tokens_for_history - tokens_used_by_primary_section_final - actual_ambient_header_tokens
    ambient_content_budget = max(0, ambient_content_budget)
    pruned_ambient_content_str = _prune_history_string(raw_ambient_content, ambient_content_budget, "[AmbientPrune]", request_id_for_logging)

    final_ambient_history_tokens_inc_header = 0
    formatted_ambient_history_string_with_header = ""
    if pruned_ambient_content_str:
        formatted_ambient_history_string_with_header = f"{ambient_header_template}{pruned_ambient_content_str}"
        final_ambient_history_tokens_inc_header = count_tokens(formatted_ambient_history_string_with_header)
    else:
        actual_ambient_header_tokens = 0

    logger.info(f"Request {request_id_for_logging}: Ambient content budget: {ambient_content_budget}. Pruned ambient content tokens (excl header): {count_tokens(pruned_ambient_content_str)}. With header: {final_ambient_history_tokens_inc_header}")

    return {
        "pruned_primary_content_str": pruned_primary_content_str,
        "pruned_ambient_content_str": pruned_ambient_content_str,
        "final_primary_history_tokens": final_primary_history_tokens_inc_header,
        "final_ambient_history_tokens": final_ambient_history_tokens_inc_header,
        "primary_header_tokens": actual_primary_header_tokens,
        "ambient_header_tokens": actual_ambient_header_tokens,
        "formatted_primary_history_string_with_header": formatted_primary_history_string_with_header,
        "formatted_ambient_history_string_with_header": formatted_ambient_history_string_with_header,
    }


def _prune_history_string(history_string: str, max_tokens: int, logger_prefix: str, request_id: int) -> str:
    """Prunes a history string to fit within a token budget by removing oldest entries."""
    history_content_stripped = history_string.strip()
    if not history_content_stripped or count_tokens(history_content_stripped) <= max_tokens:
        return history_content_stripped

    logger.info(f"{logger_prefix} Request {request_id}: History ({count_tokens(history_content_stripped)} tokens) exceeds budget ({max_tokens}). Pruning.")
    lines = history_content_stripped.split('\n')
    current_content = history_content_stripped
    while count_tokens(current_content) > max_tokens and lines:
        lines.pop(0)
        current_content = "\n".join(lines)

    final_tokens = count_tokens(current_content)
    if final_tokens > max_tokens:
        logger.warning(f"{logger_prefix} Request {request_id}: After removing lines, content ({final_tokens} tokens) might still be over budget ({max_tokens}), or became empty. Returning best effort.")
        if not lines:
             return ""

    logger.info(f"{logger_prefix} Request {request_id}: After pruning, history token count: {final_tokens}. Budget: {max_tokens}.")
    return current_content


def process_llm_request(request_details, flask_app):
    """Handles the actual LLM interaction for a given request."""
    request_id = request_details['request_id']
    post_id = request_details['post_id']
    
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row 
    cursor = db.cursor()

    try:
        requested_model = request_details.get('model')
        model_to_use = None
        if requested_model:
            model_to_use = requested_model
            print(f"Using model specified in LLM request: '{model_to_use}' for request {request_id}.")
        else:
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_setting = cursor.fetchone()
            if model_setting and model_setting['setting_value']:
                model_to_use = model_setting['setting_value']
                print(f"No model in request, using global setting: '{model_to_use}' for request {request_id}.")
            else:
                model_to_use = DEFAULT_MODEL
                print(f"No model in request or global setting, using hardcoded DEFAULT_MODEL: '{model_to_use}' for request {request_id}.")
        model = model_to_use

        effective_context_window = None
        model_specific_context = None
        logger.info(f"Request {request_id}: Attempting to fetch context window for model: {model} using ollama_utils...")
        with flask_app.app_context():
            model_specific_context = get_model_context_window(model, db)

        if model_specific_context is not None:
            effective_context_window = model_specific_context
            logger.info(f"Request {request_id}: Using model-specific context window for {model}: {effective_context_window} tokens.")
        else:
            logger.warning(f"Request {request_id}: Could not retrieve model-specific context window for {model}. Attempting fallback from settings.")
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'default_llm_context_window'")
            fallback_setting = cursor.fetchone()
            if fallback_setting and fallback_setting['setting_value']:
                try:
                    effective_context_window = int(fallback_setting['setting_value'])
                    logger.info(f"Request {request_id}: Using fallback default LLM context window from settings: {effective_context_window} tokens.")
                except ValueError:
                    logger.error(f"Request {request_id}: Could not parse default_llm_context_window value '{fallback_setting['setting_value']}' as integer. Using hardcoded fallback.")
                    effective_context_window = 2048
            else:
                logger.warning(f"Request {request_id}: default_llm_context_window not found in settings or value is null. Using hardcoded fallback.")
                effective_context_window = 2048

        logger.info(f"Request {request_id}: Final effective context window for model {model} is {effective_context_window} tokens.")

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

        persona_instructions = "You are a helpful assistant."
        with flask_app.app_context():
            if persona_id:
                persona_data = get_persona(persona_id)
                if persona_data and persona_data['prompt_instructions']:
                    persona_instructions = persona_data['prompt_instructions']
                    print(f"Successfully fetched instructions for persona_id {persona_id} for request {request_id}.")
                else:
                    print(f"Warning: Could not fetch instructions for persona_id {persona_id} (or instructions were empty) for request {request_id}. Using default instructions.")
            else:
                print(f"No valid persona_id provided or parsed for request {request_id}. Using default instructions.")

        cursor.execute("SELECT content, tagged_files_in_content FROM posts WHERE post_id = ?", (post_id,))
        original_post = cursor.fetchone()
        if not original_post:
            error_message = f"Original post {post_id} not found for request {request_id}."
            print(error_message)
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message, request_id))
            db.commit()
            return

        attachments_text_parts = []
        with flask_app.app_context():
            upload_folder_path = current_app.config.get('UPLOAD_FOLDER')
            if not upload_folder_path:
                print(f"Error: UPLOAD_FOLDER not configured in Flask app for request {request_id}. Cannot process attachments.")
            else:
                cursor.execute("SELECT filename, filepath, user_prompt FROM attachments WHERE post_id = ? ORDER BY order_in_post ASC", (post_id,))
                attachments_raw = cursor.fetchall()
                if attachments_raw:
                    for att in attachments_raw:
                        full_filepath = os.path.join(upload_folder_path, att['filepath'])
                        file_content = ""
                        try:
                            with open(full_filepath, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                        except Exception as e:
                            file_content = f"Error reading file: {str(e)}"
                        attachments_text_parts.append(
                            f"--- BEGIN ATTACHED FILE ---\nFilename: {att['filename']}\nUser prompt: {att['user_prompt'] or 'Associated file content.'}\nContent:\n{file_content}\n--- END ATTACHED FILE ---"
                        )
        
        attachments_string = "\n\n".join(attachments_text_parts)
        if attachments_string:
            attachments_string += "\n\n"

        tagged_files_string = ""
        tagged_files_json = original_post['tagged_files_in_content']
        if tagged_files_json:
            try:
                tagged_file_paths = json.loads(tagged_files_json)
                if tagged_file_paths:
                    tagged_files_parts = []
                    for file_path in tagged_file_paths:
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                file_content = f.read()
                            tagged_files_parts.append(
                                f"--- BEGIN INCLUDED FILE ---\nFile Path: {file_path}\nContent:\n{file_content}\n--- END INCLUDED FILE ---"
                            )
                        except Exception as e:
                            tagged_files_parts.append(f"--- ERROR: Could not read file at path {file_path}: {e} ---")
                    if tagged_files_parts:
                        tagged_files_string = "\n\n".join(tagged_files_parts) + "\n\n"
            except json.JSONDecodeError:
                logger.error(f"Request {request_id}: Could not decode tagged_files_in_content JSON: {tagged_files_json}")

        topic_id_for_history = None
        if post_id:
            cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id,))
            current_post_topic_info = cursor.fetchone()
            if current_post_topic_info:
                topic_id_for_history = current_post_topic_info['topic_id']
            else:
                logger.error(f"Request {request_id}: Could not fetch topic_id for current post {post_id} for history construction.")

        raw_primary_content, raw_ambient_content = _get_raw_history_strings(post_id, db, topic_id_for_history)
        logger.info(f"Request {request_id}: Raw primary history ({count_tokens(raw_primary_content)} tokens), Raw ambient history ({count_tokens(raw_ambient_content)} tokens)")

        safety_margin_percentage = 0.95
        max_allowed_tokens = int(effective_context_window * safety_margin_percentage)
        persona_prompt_tokens = count_tokens(persona_instructions)
        user_post_tokens = count_tokens(original_post['content'])
        attachments_token_count = count_tokens(attachments_string.strip())
        tagged_files_token_count = count_tokens(tagged_files_string.strip())
        user_post_content_for_count = original_post['content']
        final_instruction_tokens = count_tokens(FINAL_INSTRUCTION)

        fixed_elements_tokens = count_tokens(
           f"{attachments_string}"
           f"{tagged_files_string}"
           f"{persona_instructions}\n\n"
           f"User wrote: {user_post_content_for_count}\n\n"
           f"{FINAL_INSTRUCTION}"
        )
        logger.info(f"Request {request_id}: Fixed elements token count: {fixed_elements_tokens}")

        available_tokens_for_history_sections = max_allowed_tokens - fixed_elements_tokens
        available_tokens_for_history_sections = max(0, available_tokens_for_history_sections)
        logger.info(f"Request {request_id}: Max allowed: {max_allowed_tokens}. Available for history: {available_tokens_for_history_sections}")

        ch_settings_for_pruning = get_chat_history_settings(db)
        current_primary_history_budget_ratio = ch_settings_for_pruning['primary_history_budget_ratio']

        pruning_results = _prune_history_sections(
            raw_primary_content=raw_primary_content,
            raw_ambient_content=raw_ambient_content,
            available_tokens_for_history=available_tokens_for_history_sections,
            primary_history_budget_ratio=current_primary_history_budget_ratio,
            primary_header_template=f"{PRIMARY_HISTORY_HEADER}\n\n",
            ambient_header_template=f"{AMBIENT_HISTORY_HEADER}\n\n",
            request_id_for_logging=str(request_id)
        )

        formatted_primary_history_string_final = pruning_results["formatted_primary_history_string_with_header"]
        formatted_ambient_history_string_final = pruning_results["formatted_ambient_history_string_with_header"]

        prompt_parts = []
        if attachments_string: prompt_parts.append(attachments_string)
        if tagged_files_string: prompt_parts.append(tagged_files_string)
        prompt_parts.append(f"{persona_instructions}\n\n")
        if formatted_ambient_history_string_final:
            prompt_parts.append(formatted_ambient_history_string_final)
            if not formatted_ambient_history_string_final.endswith("\n\n"):
                prompt_parts.append("\n\n" if not formatted_ambient_history_string_final.endswith("\n") else "\n")
        if formatted_primary_history_string_final:
            prompt_parts.append(formatted_primary_history_string_final)
            if not formatted_primary_history_string_final.endswith("\n"):
                 prompt_parts.append("\n")
            prompt_parts.append("\n")
        prompt_parts.append(FINAL_INSTRUCTION)
        prompt_content = "".join(prompt_parts)

        actual_final_prompt_tokens = count_tokens(prompt_content)
        logger.info(f"Request {request_id}: Final prompt constructed. Total tokens: {actual_final_prompt_tokens}.")

        token_breakdown = {
            "persona_prompt_tokens": persona_prompt_tokens,
            "user_post_tokens": user_post_tokens,
            "attachments_token_count": attachments_token_count,
            "tagged_files_token_count": tagged_files_token_count,
            "primary_chat_history_tokens": count_tokens(pruning_results["pruned_primary_content_str"]),
            "ambient_chat_history_tokens": count_tokens(pruning_results["pruned_ambient_content_str"]),
            "headers_tokens": pruning_results["primary_header_tokens"] + pruning_results["ambient_header_tokens"],
            "final_instruction_tokens": final_instruction_tokens,
            "total_prompt_tokens": actual_final_prompt_tokens
        }
        token_breakdown_json = json.dumps(token_breakdown)

        cursor.execute("UPDATE llm_requests SET full_prompt_sent = ?, prompt_token_breakdown = ? WHERE request_id = ?", (prompt_content, token_breakdown_json, request_id))
        db.commit()
        logger.info(f"Request {request_id}: Stored final prompt and token breakdown.")

        if actual_final_prompt_tokens > max_allowed_tokens:
            error_message_for_db = f"Error: Prompt too long after assembly. Tokens: {actual_final_prompt_tokens}, Max Allowed: {max_allowed_tokens}."
            logger.error(f"Request {request_id}: {error_message_for_db}")
            cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message_for_db, request_id))
            db.commit()
            return

        try:
            print(f"Sending prompt to Ollama for model '{model}'...")
            full_response_content = ""
            last_chunk_time = time.time()
            inter_chunk_timeout = 300
            initial_connection_timeout = 300

            response = requests.post(
                OLLAMA_GENERATE_URL,
                json={'model': model, 'prompt': prompt_content, 'stream': True},
                headers={'Content-Type': 'application/json'},
                stream=True,
                timeout=initial_connection_timeout
            )
            response.raise_for_status()

            stream_done = False
            for line in response.iter_lines():
                if line:
                    current_time = time.time()
                    if current_time - last_chunk_time > inter_chunk_timeout:
                        raise TimeoutError(f"Ollama response timed out after {inter_chunk_timeout} seconds of inactivity.")
                    last_chunk_time = current_time
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        response_part = chunk.get('response', '')
                        full_response_content += response_part
                        if chunk.get('done', False):
                            stream_done = True
                            break
                    except json.JSONDecodeError:
                        print(f"Warning: Received non-JSON line from Ollama stream for request {request_id}: {line}")
                        continue

            if not stream_done:
                 print(f"Warning: Ollama stream ended for request {request_id} without receiving 'done': true.")
                 if not full_response_content:
                     raise ValueError("Ollama stream ended unexpectedly with no content and no 'done' flag.")

            cursor.execute("""
                INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id)
                SELECT topic_id, ?, ?, ?, TRUE, ?, ?
                FROM posts WHERE post_id = ?
            """, (CURRENT_USER_ID, post_id, full_response_content, model, persona_id, post_id))
            new_post_id = cursor.lastrowid

            cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            
            cursor.execute("""
                UPDATE llm_requests
                SET status = 'pending', post_id_to_respond_to = ?
                WHERE parent_request_id = ? AND status = 'pending_dependency'
            """, (new_post_id, request_id))
            
            if cursor.rowcount > 0:
                print(f"Request {request_id}: Activated {cursor.rowcount} dependent request(s).")

            db.commit()
            print(f"Request {request_id} marked as complete.")

        except (ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Ollama connection failed or timed out: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
            _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app)
        except requests.exceptions.RequestException as e:
            print(f"Ollama API request failed: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
            _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app)
        except Exception as e:
            raise Exception(f"Error during Ollama interaction: {e}") from e

    except Exception as e:
        print(f"Error in process_llm_request for request {request_id}: {e}")
        cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (f"Pre-processing error: {str(e)}", request_id))
        db.commit()
    finally:
        db.close()

def _dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, db_path, flask_app):
    print(f"Dummy LLM processing request {request_id} for post {post_id}.")
    dummy_response_content = f"This is a dummy LLM response for post {post_id} using model {model} and persona_id {persona_id}. The intended prompt was: {prompt_content}"
    dummy_db = None
    try:
        dummy_db = sqlite3.connect(db_path)
        dummy_db.row_factory = sqlite3.Row 
        dummy_cursor = dummy_db.cursor()
        dummy_cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (post_id,))
        original_post_topic = dummy_cursor.fetchone()
        if not original_post_topic:
            error_message = f"Dummy LLM: Original post {post_id} not found."
            dummy_cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (error_message, request_id))
            dummy_db.commit()
            return
        topic_id = original_post_topic['topic_id']
        dummy_cursor.execute(
            "INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id) VALUES (?, ?, ?, ?, TRUE, ?, ?)",
            (topic_id, CURRENT_USER_ID, post_id, dummy_response_content, model, persona_id) 
        )
        dummy_cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        dummy_db.commit()
    except Exception as e:
        error_message = f"Error in dummy LLM processor for request {request_id}: {str(e)}"
        print(error_message)
        if dummy_db: 
            try:
                error_cursor = dummy_db.cursor()
                error_cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ? WHERE request_id = ?", (error_message, request_id))
                dummy_db.commit()
            except Exception as db_error:
                print(f"Could not update LLM request status to error after dummy processor failure: {db_error}")
    finally:
        if dummy_db:
            dummy_db.close()
