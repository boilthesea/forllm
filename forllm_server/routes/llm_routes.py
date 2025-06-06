import sqlite3
import requests
from flask import Blueprint, request, jsonify, current_app # Added current_app
from ..database import get_db, get_effective_persona_for_subforum, get_persona # Import get_persona
from ..config import OLLAMA_TAGS_URL, DEFAULT_MODEL, CURRENT_USER_ID # Added CURRENT_USER_ID
from ..ollama_utils import get_model_context_window # Changed import

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

@llm_api_bp.route('/llm/models/<path:model_name>/context_window', methods=['GET'])
def get_llm_model_context_window_route(model_name):
    """
    API endpoint to get the context window for a specific Ollama model.
    Uses caching mechanism.
    """
    if not model_name:
        return jsonify({"error": "Model name cannot be empty"}), 400

    current_app.logger.info(f"Route hit: /api/llm/models/{model_name}/context_window")
    db = get_db()

    # Get 'refresh' query parameter
    force_refresh_str = request.args.get('refresh', 'false')
    force_refresh = force_refresh_str.lower() == 'true'
    current_app.logger.info(f"Force refresh parameter: {force_refresh}")

    try:
        # Use the get_model_context_window function from ollama_utils
        # This function handles caching and fetching from Ollama, now with force_refresh
        context_window_value = get_model_context_window(model_name, db, force_refresh=force_refresh)

        if context_window_value is not None:
            current_app.logger.info(f"Successfully retrieved context window for {model_name} (force_refresh={force_refresh}): {context_window_value}")
            return jsonify({'context_window': context_window_value}), 200 # Adjusted success response
        else:
            # This means it wasn't in cache and couldn't be fetched from Ollama (e.g., model not found by Ollama)
            current_app.logger.warning(f"Context window not found for model {model_name} (neither in cache nor from Ollama).")
            # Adjusted error response to match request
            return jsonify({'context_window': None, 'error': 'Context window not found for model.'}), 404

    except Exception as e:
        current_app.logger.error(f"Error getting context window for model {model_name}: {e}")
        # It's good practice to avoid sending generic exception details to the client
        # For debugging, you might log e, but return a more generic error message.
        # Keeping generic error for 500, but the 404 is now specific as per request.
        return jsonify({"error": "An internal server error occurred while retrieving model context window."}), 500

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

@llm_api_bp.route('/posts/<int:post_id>/tag_persona', methods=['POST'])
def tag_persona_on_post(post_id):
    db = get_db()
    cursor = db.cursor()

    # 1. Get persona_id from request body
    data = request.get_json()
    if not data or 'persona_id' not in data:
        return jsonify({'error': 'persona_id is missing from request body'}), 400
    
    persona_id_to_tag = data['persona_id']
    try:
        persona_id_to_tag = int(persona_id_to_tag)
    except ValueError:
        return jsonify({'error': 'persona_id must be an integer'}), 400

    # 2. Get current user ID
    tagged_by_user_id = CURRENT_USER_ID # Relies on top-level import

    # 3. Validate post_id
    cursor.execute("SELECT post_id FROM posts WHERE post_id = ?", (post_id,))
    post_row = cursor.fetchone()
    if not post_row:
        return jsonify({'error': f'Post with ID {post_id} not found'}), 404

    # 4. Validate persona_id (exists and is active)
    # Using the existing get_persona function from database.py
    # Make sure get_persona is imported: from ..database import get_persona
    persona_row = get_persona(persona_id_to_tag, active_only=True)
    if not persona_row:
        return jsonify({'error': f'Active persona with ID {persona_id_to_tag} not found'}), 404

    try:
        # 5. Add record to post_persona_tags
        cursor.execute("""
            INSERT INTO post_persona_tags (post_id, persona_id, tagged_by_user_id)
            VALUES (?, ?, ?)
        """, (post_id, persona_id_to_tag, tagged_by_user_id))
        tag_id = cursor.lastrowid

        # 6. Create entry in llm_requests
        # request_type 'respond_to_post_tag' as used in previous task
        # llm_model is None, worker can decide
        cursor.execute("""
            INSERT INTO llm_requests 
            (post_id_to_respond_to, llm_persona, requested_by_user_id, request_type, status, llm_model)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (post_id, persona_id_to_tag, tagged_by_user_id, 'respond_to_post_tag', 'pending', None))
        request_id = cursor.lastrowid
        
        db.commit()
        
        return jsonify({
            'message': 'Persona tagged successfully and LLM request created.',
            'tag_id': tag_id,
            'llm_request_id': request_id,
            'post_id': post_id,
            'persona_id': persona_id_to_tag
        }), 201

    except sqlite3.IntegrityError as e:
        db.rollback()
        # This might happen if the combination of (post_id, persona_id, tagged_by_user_id) must be unique
        # or if other integrity constraints are violated.
        # The current post_persona_tags schema doesn't enforce such unique constraint on all three,
        # but a (post_id, persona_id) might be a sensible unique constraint to prevent duplicate tags by different users
        # (if that's the desired logic) or duplicate tags by the same user.
        # For now, assuming a generic integrity error.
        return jsonify({'error': f'Database integrity error: {str(e)}'}), 409 # 409 Conflict
    except Exception as e:
        db.rollback()
        # Log the exception e for debugging
        print(f"Unexpected error in tag_persona_on_post: {e}")
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500