from flask import Blueprint, jsonify
import os

tts_bp = Blueprint('tts_bp', __name__)

@tts_bp.route('/api/tts/voices', methods=['GET'])
def get_tts_voices():
    """
    Endpoint to retrieve the available TTS voices from a JSON file.
    """
    try:
        # Construct the path to the JSON file relative to the app's instance folder or a known location
        # For this project structure, it's in the forllm_server directory.
        json_path = os.path.join(os.path.dirname(__file__), '..', 'voice_options.json')
        if not os.path.exists(json_path):
            return jsonify({"error": "Voice options file not found."}), 404
        
        with open(json_path, 'r', encoding='utf-8') as f:
            voices_data = f.read()
        
        # The file is already a JSON string, so we can return it directly
        # by loading it into a Python object first.
        import json
        return jsonify(json.loads(voices_data))

    except Exception as e:
        return jsonify({"error": "Failed to load voice options.", "details": str(e)}), 500
