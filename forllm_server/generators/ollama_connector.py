import requests
import json
import time
import sqlite3
import os
from flask import current_app
from requests.exceptions import ConnectionError, RequestException
import logging

from .base import BaseGenerator
from ..config import DATABASE, OLLAMA_GENERATE_URL, DEFAULT_MODEL, CURRENT_USER_ID, UPLOAD_FOLDER
from ..database import get_persona
from ..ollama_utils import get_model_context_window
from ..llm_processing import _get_raw_history_strings, _prune_history_sections, FINAL_INSTRUCTION, PRIMARY_HISTORY_HEADER, AMBIENT_HISTORY_HEADER, get_chat_history_settings
from ..tokenizer_utils import count_tokens

logger = logging.getLogger(__name__)

class OllamaConnector(BaseGenerator):
    """
    Generator for handling text generation requests via Ollama.
    """
    def generate(self, request_details: dict, flask_app) -> dict:
        """Handles the actual LLM interaction for a given request."""
        request_id = request_details['request_id']
        post_id = request_details.get('post_id_to_respond_to')

        if not post_id:
            return {'status': 'error', 'error_message': f"Request {request_id} is missing 'post_id_to_respond_to'."}

        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()

        try:
            requested_model = request_details.get('llm_model')
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

            persona_id_str = request_details.get('llm_persona')
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
                return {'status': 'error', 'error_message': error_message}

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
                                f"--- BEGIN ATTACHED FILE ---\nFilename: {att['filename']}\nUser prompt: {att['user_prompt'] or 'Associated file content.'}\nContent:\n{file_content}\n--- END ATTACHED FILE ---")
            
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
                                    f"--- BEGIN INCLUDED FILE ---\nFile Path: {file_path}\nContent:\n{file_content}\n--- END INCLUDED FILE ---")
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
            
            # --- Custom Instructions Logic ---
            custom_instructions_string = ""
            try:
                # 1. Get tagged instructions and sets from the post
                cursor.execute("SELECT tagged_custom_instructions_in_content, tagged_instruction_sets_in_content FROM posts WHERE post_id = ?", (post_id,))
                post_tags = cursor.fetchone()
                tagged_instruction_ids = set(json.loads(post_tags['tagged_custom_instructions_in_content'] or '[]'))
                tagged_set_ids = set(json.loads(post_tags['tagged_instruction_sets_in_content'] or '[]'))

                # 2. Expand sets
                if tagged_set_ids:
                    placeholders = ','.join('?' for _ in tagged_set_ids)
                    cursor.execute(f"SELECT instruction_id FROM instruction_set_items WHERE set_id IN ({placeholders})", list(tagged_set_ids))
                    for row in cursor.fetchall():
                        tagged_instruction_ids.add(row['instruction_id'])

                # 3. Get subforum defaults
                cursor.execute("SELECT instruction_id FROM subforum_instruction_defaults WHERE subforum_id = (SELECT subforum_id FROM topics WHERE topic_id = ?)", (topic_id_for_history,))
                for row in cursor.fetchall():
                    tagged_instruction_ids.add(row['instruction_id'])

                # 4. Get global defaults
                cursor.execute("SELECT id FROM custom_instructions WHERE is_global_default = 1")
                for row in cursor.fetchall():
                    tagged_instruction_ids.add(row['id'])

                # 5. Fetch, order, and apply
                if tagged_instruction_ids:
                    placeholders = ','.join('?' for _ in tagged_instruction_ids)
                    cursor.execute(f"SELECT prompt_text FROM custom_instructions WHERE id IN ({placeholders}) ORDER BY priority", list(tagged_instruction_ids))
                    custom_instructions_string = "\n".join(row['prompt_text'] for row in cursor.fetchall())
                    if custom_instructions_string:
                        custom_instructions_string += "\n\n"
            except Exception as e:
                logger.error(f"Request {request_id}: Error processing custom instructions: {e}")
            
            if custom_instructions_string:
                prompt_parts.append(custom_instructions_string)
            # --- End Custom Instructions Logic ---

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
                return {'status': 'error', 'error_message': error_message_for_db}

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

                cursor.execute(
                    """
                    INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id)
                    SELECT topic_id, ?, ?, ?, TRUE, ?, ?
                    FROM posts WHERE post_id = ?
                    """, (CURRENT_USER_ID, post_id, full_response_content, model, persona_id, post_id))
                new_post_id = cursor.lastrowid
                db.commit()
                
                return {'status': 'complete', 'result_object_id': new_post_id}

            except (ConnectionError, requests.exceptions.Timeout) as e:
                print(f"Ollama connection failed or timed out: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
                return self._dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app)
            except requests.exceptions.RequestException as e:
                print(f"Ollama API request failed: {type(e).__name__}. Using dummy LLM processor for request {request_id}.")
                return self._dummy_llm_processor(request_id, post_id, model, persona_id, prompt_content, DATABASE, flask_app)
            except Exception as e:
                raise Exception(f"Error during Ollama interaction: {e}") from e

        except Exception as e:
            logger.error(f"Error in OllamaConnector for request {request_id}: {e}", exc_info=True)
            return {'status': 'error', 'error_message': f"Pre-processing error: {str(e)}"}
        finally:
            db.close()

    def _dummy_llm_processor(self, request_id, post_id, model, persona_id, prompt_content, db_path, flask_app):
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
                return {'status': 'error', 'error_message': error_message}

            topic_id = original_post_topic['topic_id']
            dummy_cursor.execute(
                "INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id) VALUES (?, ?, ?, ?, TRUE, ?, ?)",
                (topic_id, CURRENT_USER_ID, post_id, dummy_response_content, model, persona_id)
            )
            new_post_id = dummy_cursor.lastrowid
            dummy_db.commit()
            return {'status': 'complete', 'result_object_id': new_post_id}
        except Exception as e:
            error_message = f"Error in dummy LLM processor for request {request_id}: {str(e)}"
            print(error_message)
            return {'status': 'error', 'error_message': error_message}
        finally:
            if dummy_db:
                dummy_db.close()