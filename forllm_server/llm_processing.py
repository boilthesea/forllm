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


# This file now primarily contains history-building logic.
# The main request processing has been moved to the generator connectors.
