from flask import Blueprint, request, jsonify, current_app
from forllm_server.tokenizer_utils import count_tokens
from forllm_server.database import get_persona, get_db
from forllm_server.ollama_utils import get_model_context_window
from forllm_server.config import DEFAULT_MODEL, DATABASE
import sqlite3
import logging

utility_bp = Blueprint('utility_bp', __name__)
logger = logging.getLogger(__name__)

@utility_bp.route('/api/utils/count_tokens_for_text', methods=['POST'])
def count_tokens_for_text_route():
    try:
        data = request.get_json()
        text = data.get('text', '')
        if text is None: # Handle explicit null
            text = ''

        token_count = count_tokens(text)
        # Log the request and response for debugging
        # logger.debug(f"Counting tokens for text: '{text[:50]}...', count: {token_count}")
        return jsonify({'token_count': token_count})
    except Exception as e:
        logger.error(f"Error in /api/utils/count_tokens_for_text: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@utility_bp.route('/api/prompts/estimate_tokens', methods=['POST'])
def estimate_tokens_route():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload provided."}), 400

        current_post_text = data.get('current_post_text', '')
        selected_persona_id_str = data.get('selected_persona_id') # Keep as string for now
        attachments_text = data.get('attachments_text', '')
        # parent_post_id = data.get('parent_post_id') # Unused for now

        # Token Calculation
        post_content_tokens = count_tokens(current_post_text)
        attachments_tokens = count_tokens(attachments_text)
        chat_history_tokens = 0  # Placeholder
        system_prompt_tokens = 0 # Placeholder

        persona_prompt_tokens = 0
        persona_name = "Default / None Selected"

        selected_persona_id = None
        if selected_persona_id_str is not None:
            try:
                selected_persona_id = int(selected_persona_id_str)
            except ValueError:
                logger.warning(f"Invalid selected_persona_id format: {selected_persona_id_str}. Proceeding without a specific persona.")
                persona_name = "Invalid Persona ID"


        if selected_persona_id is not None:
            # get_persona needs app context, which is available in route handlers
            persona_data = get_persona(selected_persona_id)
            if persona_data:
                persona_prompt_tokens = count_tokens(persona_data['prompt_instructions'])
                persona_name = persona_data['name']
            else:
                logger.warning(f"Persona with ID {selected_persona_id} not found.")
                persona_name = f"Unknown Persona (ID: {selected_persona_id})"

        total_estimated_tokens = post_content_tokens + persona_prompt_tokens + attachments_tokens + chat_history_tokens + system_prompt_tokens

        # Context Window Determination
        current_selected_model_name = None
        effective_context_window_for_model = None

        db_conn_settings = None # For settings table
        try:
            # Use get_db() which is managed by Flask app context for settings
            # However, get_model_context_window also uses get_db().
            # For simplicity here, and since get_db() returns a g.db, we can use it if careful,
            # or open a new one for settings if preferred to avoid g conflicts if get_model_context_window also uses it heavily.
            # Let's try a separate connection for clarity for settings, then use app_context for ollama_utils.

            db_conn_settings = sqlite3.connect(DATABASE)
            db_conn_settings.row_factory = sqlite3.Row
            cursor = db_conn_settings.cursor()

            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_setting = cursor.fetchone()
            if model_setting and model_setting['setting_value']:
                current_selected_model_name = model_setting['setting_value']
            else:
                current_selected_model_name = DEFAULT_MODEL
                logger.info(f"No selectedModel in settings, using DEFAULT_MODEL: {DEFAULT_MODEL}")
        except sqlite3.Error as e:
            logger.error(f"Database error when fetching selectedModel: {e}", exc_info=True)
            current_selected_model_name = DEFAULT_MODEL # Fallback
        finally:
            if db_conn_settings:
                db_conn_settings.close()

        # get_model_context_window needs app context.
        # The route handler itself is already in an app context.
        db = get_db()
        model_specific_context = get_model_context_window(current_selected_model_name, db)

        if model_specific_context is not None:
            effective_context_window_for_model = model_specific_context
        else:
            logger.warning(f"Could not retrieve model-specific context for {current_selected_model_name}. Fetching default_llm_context_window setting.")
            db_conn_settings_fallback = None
            try:
                db_conn_settings_fallback = sqlite3.connect(DATABASE)
                db_conn_settings_fallback.row_factory = sqlite3.Row
                cursor_fallback = db_conn_settings_fallback.cursor()
                cursor_fallback.execute("SELECT setting_value FROM settings WHERE setting_key = 'default_llm_context_window'")
                fallback_setting = cursor_fallback.fetchone()
                if fallback_setting and fallback_setting['setting_value']:
                    try:
                        effective_context_window_for_model = int(fallback_setting['setting_value'])
                    except ValueError:
                        logger.error(f"Invalid format for default_llm_context_window: {fallback_setting['setting_value']}. Using hardcoded fallback.")
                        effective_context_window_for_model = 4096 # Hardcoded fallback
                else:
                    logger.warning("default_llm_context_window not found in settings. Using hardcoded fallback.")
                    effective_context_window_for_model = 4096 # Hardcoded fallback
            except sqlite3.Error as e:
                logger.error(f"Database error fetching default_llm_context_window: {e}. Using hardcoded fallback.", exc_info=True)
                effective_context_window_for_model = 4096 # Hardcoded fallback
            finally:
                if db_conn_settings_fallback:
                    db_conn_settings_fallback.close()

        return jsonify({
            "post_content_tokens": post_content_tokens,
            "persona_prompt_tokens": persona_prompt_tokens,
            "persona_name": persona_name,
            "system_prompt_tokens": system_prompt_tokens,
            "attachments_tokens": attachments_tokens,
            "chat_history_tokens": chat_history_tokens,
            "total_estimated_tokens": total_estimated_tokens,
            "model_context_window": effective_context_window_for_model,
            "model_name": current_selected_model_name
        })

    except Exception as e:
        logger.error(f"Error in /api/prompts/estimate_tokens: {e}", exc_info=True)
        return jsonify({'error': "An unexpected error occurred. Please check logs."}), 500
