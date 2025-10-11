from flask import Blueprint, request, jsonify
import sqlite3
import json
from ..database import get_db
from ..config import CURRENT_USER_ID

generation_bp = Blueprint('generation_bp', __name__)

@generation_bp.route('/api/generation/queue_from_post', methods=['POST'])
def queue_from_post():
    """
    API endpoint to queue a generation request from a post.
    """
    data = request.get_json()
    post_id = data.get('post_id')
    generation_type = data.get('generation_type')
    prompt = data.get('prompt')
    params = data.get('params', {})

    if not all([post_id, generation_type, prompt]):
        return jsonify({'error': 'Missing required fields: post_id, generation_type, and prompt are required.'}), 400

    db = get_db()
    try:
        # Determine the request_type for the llm_requests table
        # This is a simple mapping for now, but can be expanded.
        request_type_mapping = {
            'image': 'generate_image',
            'video': 'generate_video',
            'tts': 'generate_tts',
            'music': 'generate_music'
        }
        request_type = request_type_mapping.get(generation_type)

        if not request_type:
            return jsonify({'error': f'Invalid generation_type: {generation_type}'}), 400

        # Here, we would also fetch the model associated with this generation type from settings
        # For now, we'll leave it null and let the dispatcher handle it.
        
        params['prompt'] = prompt # Ensure the prompt is part of the params blob

        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO llm_requests (post_id_to_respond_to, request_type, request_params, requested_by_user_id, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (post_id, request_type, json.dumps(params), CURRENT_USER_ID)
        )
        db.commit()
        request_id = cursor.lastrowid

        return jsonify({'success': True, 'message': 'Generation request queued.', 'request_id': request_id}), 202
    except sqlite3.Error as e:
        print(f"Database error in queue_from_post: {e}")
        return jsonify({'error': 'A database error occurred.'}), 500
    except Exception as e:
        print(f"Error in queue_from_post: {e}")
        return jsonify({'error': 'An unexpected error occurred.'}), 500