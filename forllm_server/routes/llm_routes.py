import sqlite3
import requests
from flask import Blueprint, request, jsonify
from ..database import get_db, get_effective_persona_for_subforum
from ..config import OLLAMA_TAGS_URL, DEFAULT_MODEL # Removed unused llm_request_queue, processing_active

llm_api_bp = Blueprint('llm_api', __name__, url_prefix='/api')

@llm_api_bp.route('/posts/<int:post_id>/request_llm', methods=['POST'])
def request_llm_response(post_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT post_id, topic_id FROM posts WHERE post_id = ? AND is_llm_response = FALSE", (post_id,))
    post_row = cursor.fetchone()
    if not post_row:
        return jsonify({'error': 'Post not found or is already an LLM response'}), 404
    topic_id = post_row['topic_id']

    # Fetch selected model from settings
    settings_cursor = db.cursor()
    settings_cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
    model_setting = settings_cursor.fetchone()
    llm_model_to_use = model_setting['setting_value'] if model_setting else DEFAULT_MODEL

    # Persona selection logic
    data = request.get_json(silent=True) or {}
    persona_id = data.get('persona_id')
    if persona_id:
        persona_row = get_effective_persona_for_subforum(topic_id, persona_id)
        persona_id_to_use = persona_row['persona_id'] if persona_row else 1
    else:
        persona_row = get_effective_persona_for_subforum(topic_id)
        persona_id_to_use = persona_row['persona_id'] if persona_row else 1

    try:
        cursor.execute("""
            INSERT INTO llm_requests (post_id_to_respond_to, status, llm_model, llm_persona)
            VALUES (?, 'pending', ?, ?)
        """, (post_id, llm_model_to_use, persona_id_to_use))
        request_id = cursor.lastrowid
        db.commit()
        print(f"Queued LLM request {request_id} for post {post_id} using model {llm_model_to_use} and persona {persona_id_to_use}")
        return jsonify({'message': 'LLM response requested successfully', 'request_id': request_id}), 202
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Failed to queue LLM request: {e}'}), 500

@llm_api_bp.route('/ollama/models', methods=['GET'])
def get_ollama_models():
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=10)
        response.raise_for_status()
        models_data = response.json()
        model_names = [model['name'] for model in models_data.get('models', [])]
        return jsonify(model_names)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Ollama models: {e}")
        return jsonify({'error': f"Could not connect to Ollama to fetch models: {e}", 'models': [DEFAULT_MODEL]}), 503
    except Exception as e:
        print(f"Unexpected error fetching Ollama models: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

# New route to get the list of queued requests
@llm_api_bp.route('/queue', methods=['GET'])
def get_queue():
    db = get_db()
    cursor = db.cursor()
    # Fetch llm_requests, joining with posts to get a snippet of the original post
    cursor.execute("""
        SELECT
            lr.request_id,
            lr.post_id_to_respond_to,
            lr.requested_at,
            lr.status,
            lr.llm_model,
            lr.llm_persona,
            p.content AS post_snippet
        FROM llm_requests lr
        JOIN posts p ON lr.post_id_to_respond_to = p.post_id
        ORDER BY lr.requested_at DESC
    """)
    queue_items = cursor.fetchall() # fetchall returns a list of Row objects (like dicts)

    # Convert Row objects to dictionaries for jsonify
    queue_list = [dict(item) for item in queue_items]

    return jsonify(queue_list)

# New route to get the full prompt for a specific queued request
@llm_api_bp.route('/queue/<int:request_id>/prompt', methods=['GET'])
def get_queue_prompt(request_id):
    db = get_db()
    cursor = db.cursor()

    try:
        # 1. Get the request details
        cursor.execute("SELECT post_id_to_respond_to, llm_model, llm_persona FROM llm_requests WHERE request_id = ?", (request_id,))
        request_details = cursor.fetchone()
        if not request_details:
            return jsonify({'error': f'Queue request {request_id} not found'}), 404

        post_id = request_details['post_id_to_respond_to']
        # model = request_details['llm_model'] # Not strictly needed for prompt construction based on current llm_processing.py
        # persona = request_details['llm_persona'] # Not strictly needed for prompt construction based on current llm_processing.py

        # 2. Get the content of the post to respond to
        cursor.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,))
        original_post = cursor.fetchone()
        if not original_post:
            # This should ideally not happen if llm_requests is consistent with posts
            return jsonify({'error': f'Original post {post_id} for request {request_id} not found'}), 404

        # 3. Construct the prompt (replicating logic from llm_processing.py)
        # TODO: Add persona instructions and potentially more thread context later, matching llm_processing.py
        prompt_content = f"User wrote: {original_post['content']}\n\nRespond to this post."

        return jsonify({'prompt': prompt_content})

    except Exception as e:
        print(f"Error fetching prompt for request {request_id}: {e}")
        return jsonify({'error': f'Failed to fetch prompt: {e}'}), 500

# --- Persona Override for LLM Request ---
@llm_api_bp.route('/subforums/<int:subforum_id>/effective-persona', methods=['GET'])
def api_get_effective_persona(subforum_id):
    override_persona_id = request.args.get('override_persona_id', type=int)
    persona = get_effective_persona_for_subforum(subforum_id, override_persona_id)
    if not persona:
        return jsonify({'error': 'No persona found'}), 404
    return jsonify(dict(persona))