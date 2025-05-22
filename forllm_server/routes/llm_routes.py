import sqlite3
import requests
from flask import Blueprint, request, jsonify
from ..database import get_db, get_effective_persona_for_subforum, get_persona # Import get_persona
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
        print(f"Queued LLM request {request_id} for post {post_id} using model {llm_model_to_use} and persona_id {persona_id_to_use}")
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
            lr.llm_persona, -- This is the persona_id
            p_orig.content AS post_snippet,
            pers.name AS persona_name -- Fetch persona name
        FROM llm_requests lr
        JOIN posts p_orig ON lr.post_id_to_respond_to = p_orig.post_id
        LEFT JOIN personas pers ON lr.llm_persona = pers.persona_id -- Use LEFT JOIN in case persona is null or ID is invalid
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
        cursor.execute("SELECT full_prompt_sent, post_id_to_respond_to, llm_persona FROM llm_requests WHERE request_id = ?", (request_id,))
        request_data = cursor.fetchone()

        # Assuming 'request_data' holds the row from "SELECT full_prompt_sent, ... FROM llm_requests WHERE request_id = ?"
        if request_data:
            # Safely access 'full_prompt_sent' and print a snippet
            prompt_val = request_data['full_prompt_sent']
            snippet = (prompt_val[:100] + '...' if prompt_val and len(prompt_val) > 100 else prompt_val) if prompt_val else "None"
            print(f"DEBUG: In get_queue_prompt for request {request_id}. Fetched full_prompt_sent: '{snippet}'")
        else:
            # This case is already handled by "No item with that key" error, but good for explicit logging
            print(f"DEBUG: In get_queue_prompt for request {request_id}. No request_data found by cursor.fetchone().")

        if not request_data:
            return jsonify(error=f"No item with that key: Request ID {request_id} not found."), 404

        full_prompt = request_data['full_prompt_sent']

        if full_prompt is not None and full_prompt != "":
            return jsonify(prompt=full_prompt)
        else:
            # Attempt to reconstruct for older records or if somehow still null
            print(f"Reconstructing prompt for request {request_id} as full_prompt_sent was empty.")
            post_id = request_data['post_id_to_respond_to']
            persona_id_for_reconstruction = request_data['llm_persona'] 

            cursor.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,))
            original_post_row = cursor.fetchone()
            if not original_post_row:
                return jsonify(error=f"Original post (ID: {post_id}) for request {request_id} not found for prompt reconstruction."), 404
            
            original_post_content = original_post_row['content']
            
            reconstructed_persona_instructions = "You are a helpful assistant." # Default
            if persona_id_for_reconstruction is not None: # Check if it's not None before trying to use it
                try:
                    # get_persona is already imported at the top of the file
                    persona_data_reconstruction = get_persona(int(persona_id_for_reconstruction))
                    if persona_data_reconstruction and persona_data_reconstruction['prompt_instructions']:
                        reconstructed_persona_instructions = persona_data_reconstruction['prompt_instructions']
                        print(f"Successfully fetched instructions for persona_id {persona_id_for_reconstruction} for prompt reconstruction of request {request_id}.")
                    else:
                        print(f"Warning: Could not fetch instructions for persona_id {persona_id_for_reconstruction} (or instructions were empty) during prompt reconstruction for request {request_id}. Using default instructions.")
                except (ValueError, TypeError):
                    print(f"Warning: Invalid persona_id '{persona_id_for_reconstruction}' during prompt reconstruction for request {request_id}. Using default instructions.")
                except Exception as e_rec: 
                    print(f"Error fetching persona for reconstruction for request {request_id}: {e_rec}. Using default instructions.")
            else:
                print(f"No persona_id found for request {request_id} during prompt reconstruction. Using default instructions.")

            reconstructed_prompt = f"{reconstructed_persona_instructions}\n\nUser wrote: {original_post_content}\n\nRespond to this post."
            print(f"Reconstructing prompt for request {request_id} (with persona) as full_prompt_sent was empty. Preview: {reconstructed_prompt[:200]}...")
            return jsonify(prompt=reconstructed_prompt, notice="Prompt reconstructed (with persona details) as it was not pre-stored.")

    except Exception as e:
        print(f"Error fetching prompt for request {request_id}: {e}")
        return jsonify({'error': f'Failed to fetch prompt: {str(e)}'}), 500

# --- Persona Override for LLM Request ---
@llm_api_bp.route('/subforums/<int:subforum_id>/effective-persona', methods=['GET'])
def api_get_effective_persona(subforum_id):
    override_persona_id = request.args.get('override_persona_id', type=int)
    persona = get_effective_persona_for_subforum(subforum_id, override_persona_id)
    if not persona:
        return jsonify({'error': 'No persona found'}), 404
    return jsonify(dict(persona))