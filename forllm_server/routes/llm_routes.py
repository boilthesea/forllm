import sqlite3
import requests
from flask import Blueprint, request, jsonify
from ..database import get_db
from ..config import OLLAMA_TAGS_URL, DEFAULT_MODEL # Removed unused llm_request_queue, processing_active

llm_api_bp = Blueprint('llm_api', __name__, url_prefix='/api')

@llm_api_bp.route('/posts/<int:post_id>/request_llm', methods=['POST'])
def request_llm_response(post_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT post_id FROM posts WHERE post_id = ? AND is_llm_response = FALSE", (post_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Post not found or is already an LLM response'}), 404

    # For MVP, use default model/persona from config or settings
    # Fetch selected model from settings
    settings_cursor = db.cursor() # Use the same db connection
    settings_cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
    model_setting = settings_cursor.fetchone()
    llm_model_to_use = model_setting['setting_value'] if model_setting else DEFAULT_MODEL

    default_persona = "helpful_assistant" # Placeholder, could also be a setting

    try:
        cursor.execute("""
            INSERT INTO llm_requests (post_id_to_respond_to, status, llm_model, llm_persona)
            VALUES (?, 'pending', ?, ?)
        """, (post_id, llm_model_to_use, default_persona))
        request_id = cursor.lastrowid
        db.commit()
        print(f"Queued LLM request {request_id} for post {post_id} using model {llm_model_to_use}")
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