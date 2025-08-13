from flask import Blueprint, request, jsonify, current_app
from forllm_server.tokenizer_utils import count_tokens
from forllm_server.database import get_persona, get_db, get_post_ancestors, get_sibling_branch_roots, get_recent_posts_from_branch # Added for history functions called by helpers
from forllm_server.ollama_utils import get_model_context_window
from forllm_server.config import DEFAULT_MODEL, DATABASE # SAFETY_MARGIN_PERCENTAGE might be here or defined locally
from forllm_server.llm_processing import ( # Import refactored helpers and constants
    _get_raw_history_strings,
    _prune_history_sections,
    _prune_history_string, # _prune_history_sections calls this
    format_linear_history, # _get_raw_history_strings calls this
    get_chat_history_settings, # Import the new settings fetcher
    FINAL_INSTRUCTION,
    PRIMARY_HISTORY_HEADER,
    AMBIENT_HISTORY_HEADER
    # PRIMARY_HISTORY_BUDGET_RATIO, MAX_POSTS_PER_SIBLING_BRANCH, MAX_TOTAL_AMBIENT_POSTS are no longer needed here
    # as they are handled internally by the helper functions or fetched via get_chat_history_settings
)
import sqlite3
import logging
import tkinter as tk
from tkinter import filedialog

utility_bp = Blueprint('utility_bp', __name__)
logger = logging.getLogger(__name__)

# Define constants if not imported from a central config (mirroring llm_processing.py)
SAFETY_MARGIN_PERCENTAGE = 0.95
# PRIMARY_HISTORY_BUDGET_RATIO is imported
# FINAL_INSTRUCTION, PRIMARY_HISTORY_HEADER, AMBIENT_HISTORY_HEADER are imported

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
        selected_persona_id_str = data.get('selected_persona_id')
        attachments_text = data.get('attachments_text', '') # This is assumed to be pre-formatted by client or just raw
        parent_post_id = data.get('parent_post_id') # Expecting null or integer
        client_request_id = data.get('request_id', "estimate_tokens_unknown") # For logging in helpers

        # --- Basic Token Counts (excluding history for now) ---
        current_post_content_tokens = count_tokens(current_post_text) # This is the user's *new* message
        attachments_tokens = count_tokens(attachments_text) # Tokens for the attachment string provided

        persona_prompt_tokens = 0
        persona_instructions_for_calc = "You are a helpful assistant." # Default
        persona_name = "Default / None Selected"

        selected_persona_id = None
        if selected_persona_id_str is not None:
            try:
                selected_persona_id = int(selected_persona_id_str)
            except ValueError:
                logger.warning(f"Invalid selected_persona_id format: {selected_persona_id_str}. Proceeding without a specific persona.")
                persona_name = "Invalid Persona ID"


        if selected_persona_id is not None:
            persona_data = get_persona(selected_persona_id) # Uses g.db via get_db()
            if persona_data:
                persona_instructions_for_calc = persona_data['prompt_instructions']
                persona_name = persona_data['name']
            else:
                logger.warning(f"Persona with ID {selected_persona_id} not found for estimation.")
                persona_name = f"Unknown Persona (ID: {selected_persona_id})"
        persona_prompt_tokens = count_tokens(persona_instructions_for_calc)

        # --- Model and Context Window ---
        db = get_db() # Use Flask's g.db for all DB ops in this request
        cursor = db.cursor()

        cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
        model_setting = cursor.fetchone()
        current_selected_model_name = (model_setting['setting_value'] if model_setting and model_setting['setting_value'] else DEFAULT_MODEL)

        effective_context_window_for_model = get_model_context_window(current_selected_model_name, db)
        if effective_context_window_for_model is None:
            logger.warning(f"Estimator: Could not get model-specific context for {current_selected_model_name}. Using default from settings.")
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'default_llm_context_window'")
            fallback_setting = cursor.fetchone()
            if fallback_setting and fallback_setting['setting_value']:
                try:
                    effective_context_window_for_model = int(fallback_setting['setting_value'])
                except ValueError:
                    effective_context_window_for_model = 4096 # Hardcoded
            else:
                effective_context_window_for_model = 4096 # Hardcoded

        max_allowed_tokens_for_prompt = int(effective_context_window_for_model * SAFETY_MARGIN_PERCENTAGE)

        # --- Calculate Fixed Elements Tokens ---
        # This includes the current post (as "User wrote: ..."), persona, attachments, and final instruction.
        # The user's current message with "User wrote: " prefix and trailing newlines
        user_post_formatted_for_calc = f"User wrote: {current_post_text}\n\n"
        user_post_tokens_inc_formatting = count_tokens(user_post_formatted_for_calc)

        final_instruction_tokens = count_tokens(FINAL_INSTRUCTION)

        # Attachments string formatting (mirroring llm_processing.py for fixed calculation)
        # For estimation, we assume attachments_text is the content that would be inside the "--- BEGIN/END ATTACHED FILE ---" block.
        # The estimator doesn't have the full file path/details, so it relies on the client sending relevant text.
        # If attachments_text is not empty, add tokens for the surrounding markers.
        # This is a simplification; process_llm_request builds a more complex attachments_string.
        # For a more accurate estimate here, client should send the fully formatted attachments_string.
        # Assuming attachments_tokens is for the content only for now.
        # The fixed_elements_tokens in llm_processing counts `attachments_string` which has its own \n\n if not empty.
        # And then `persona_instructions\n\n`, then `User wrote: ...\n\n`, then `FINAL_INSTRUCTION`.

        fixed_elements_tokens = (
            attachments_tokens + # Assuming attachments_text is the full formatted string from client, or content to be wrapped
            count_tokens(f"{persona_instructions_for_calc}\n\n") +
            user_post_tokens_inc_formatting + # Already includes "User wrote: ..." and "\n\n"
            final_instruction_tokens
        )
        # If attachments_text is just content, and llm_processing adds wrappers, this will be an underestimation.
        # To be more precise, client should send attachments formatted as they'd be in the prompt,
        # or this endpoint needs to simulate that formatting.
        # For now, using `attachments_tokens` as is.

        available_tokens_for_history_sections = max_allowed_tokens_for_prompt - fixed_elements_tokens
        if available_tokens_for_history_sections < 0:
            available_tokens_for_history_sections = 0

        # --- Simulate History Construction and Pruning ---
        raw_primary_hist_content = ""
        raw_ambient_hist_content = ""
        pruned_primary_content_tokens = 0
        pruned_ambient_content_tokens = 0
        actual_headers_tokens = 0

        topic_id_for_history = None
        if parent_post_id:
            try:
                parent_post_id = int(parent_post_id)
                cursor.execute("SELECT topic_id FROM posts WHERE post_id = ?", (parent_post_id,))
                topic_info = cursor.fetchone()
                if topic_info:
                    topic_id_for_history = topic_info['topic_id']
                else:
                    logger.warning(f"Estimator: parent_post_id {parent_post_id} not found, cannot fetch topic_id for history.")

                if topic_id_for_history: # Only proceed if parent_post_id was valid and topic_id found
                    # Pass db connection (g.db) to helpers
                    raw_primary_hist_content, raw_ambient_hist_content = _get_raw_history_strings(parent_post_id, db, topic_id_for_history)
            except ValueError:
                logger.warning(f"Estimator: Invalid parent_post_id format: {parent_post_id}. Assuming no history.")
                parent_post_id = None # Ensure it's None if invalid

        if parent_post_id and topic_id_for_history : # Only prune if there was a basis for history
            # Fetch chat history settings to get the primary_history_budget_ratio
            ch_settings = get_chat_history_settings(db)
            current_primary_budget_ratio = ch_settings['primary_history_budget_ratio']

            pruning_results = _prune_history_sections(
                raw_primary_content=raw_primary_hist_content,
                raw_ambient_content=raw_ambient_hist_content,
                available_tokens_for_history=available_tokens_for_history_sections,
                primary_history_budget_ratio=current_primary_budget_ratio, # Use fetched ratio
                primary_header_template=f"{PRIMARY_HISTORY_HEADER}\n\n",
                ambient_header_template=f"{AMBIENT_HISTORY_HEADER}\n\n",
                request_id_for_logging=str(client_request_id)
            )
            pruned_primary_content_tokens = count_tokens(pruning_results["pruned_primary_content_str"])
            pruned_ambient_content_tokens = count_tokens(pruning_results["pruned_ambient_content_str"])
            actual_headers_tokens = pruning_results["primary_header_tokens"] + pruning_results["ambient_header_tokens"]

        # --- Final Token Summation ---
        total_estimated_tokens = (
            persona_prompt_tokens +
            attachments_tokens +    # As provided by client
            user_post_tokens_inc_formatting + # Current post being edited, with "User wrote: " etc.
            pruned_primary_content_tokens +
            pruned_ambient_content_tokens +
            actual_headers_tokens +
            final_instruction_tokens
        )

        # For the UI, `chat_history_tokens` is often displayed as a single number.
        # This will be the sum of pruned content and their headers.
        combined_chat_history_tokens = pruned_primary_content_tokens + pruned_ambient_content_tokens + actual_headers_tokens

        return jsonify({
            "post_content_tokens": current_post_content_tokens, # Tokens of just the text in editor
            "persona_prompt_tokens": persona_prompt_tokens,
            "persona_name": persona_name,
            "attachments_tokens": attachments_tokens, # Tokens of formatted attachment string from client

            "primary_chat_history_tokens": pruned_primary_content_tokens, # Content only
            "ambient_chat_history_tokens": pruned_ambient_content_tokens, # Content only
            "headers_tokens": actual_headers_tokens, # Tokens for primary and ambient headers if used
            "final_instruction_tokens": final_instruction_tokens,

            "chat_history_tokens": combined_chat_history_tokens, # Sum of primary, ambient, and their headers
            "system_prompt_tokens": 0, # Still a placeholder, not explicitly separated in llm_processing's final prompt structure beyond persona.
                                       # If persona_instructions is the "system prompt", it's covered.

            "total_estimated_tokens": total_estimated_tokens,
            "model_context_window": effective_context_window_for_model,
            "model_name": current_selected_model_name,
            "available_for_history": available_tokens_for_history_sections, # For debugging
            "fixed_elements_sum": fixed_elements_tokens # For debugging
        })

    except Exception as e:
        logger.error(f"Error in /api/prompts/estimate_tokens: {e}", exc_info=True)
        return jsonify({'error': "An unexpected error occurred. Please check logs."}), 500

@utility_bp.route('/api/utils/browse-folder', methods=['GET'])
def browse_folder():
    """
    Opens a native OS dialog to select a folder.
    This is intended to be called from the settings page to allow the user
    to select a directory on the server's local filesystem.
    """
    try:
        root = tk.Tk()
        root.withdraw()  # Hide the main Tkinter window
        folder_path = filedialog.askdirectory(
            title="Select a Folder to Index"
        )
        root.destroy() # Clean up the Tkinter instance

        if folder_path:
            # Return the selected path, normalized to use forward slashes
            return jsonify({"path": folder_path.replace('\\', '/')})
        else:
            # User cancelled the dialog
            return jsonify({"path": ""})
    except Exception as e:
        logger.error(f"Error opening folder browse dialog: {e}", exc_info=True)
        return jsonify({'error': 'Failed to open folder dialog. Check server logs. This may happen if the server is in an environment without a graphical interface.'}), 500
