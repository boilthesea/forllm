import json
import sqlite3
from flask import Blueprint, request, jsonify
from forllm_server.database import get_db
# CURRENT_USER_ID might be used later for ownership or logging, keep if part of standard imports
from forllm_server.config import CURRENT_USER_ID 
from forllm_server.config import DEFAULT_MODEL # Import for fallback

persona_routes_bp = Blueprint('persona_routes_bp', __name__, url_prefix='/api/personas')

@persona_routes_bp.route('/generate/from_details', methods=['POST'])
def generate_persona_from_details_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    name_hint = data.get('name_hint')
    description_hint = data.get('description_hint')
    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {}) # Added
    target_persona_name_override = data.get('target_persona_name_override', '') # Added

    if not description_hint: # Name hint can be optional
        return jsonify({"error": "description_hint is required"}), 400
    
    if not llm_model_for_generation:
        try:
            db = get_db() # Uses Flask's g for context-specific DB
            cursor = db.cursor()
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor.fetchone()
            if model_row and model_row['setting_value']:
                llm_model_for_generation = model_row['setting_value']
                print(f"Info: llm_model_for_generation not in request, using global default from DB: {llm_model_for_generation}")
            else:
                llm_model_for_generation = DEFAULT_MODEL
                print(f"Warning: llm_model_for_generation not in request or DB, using hardcoded DEFAULT_MODEL: {DEFAULT_MODEL}")
        except Exception as e:
            print(f"Error fetching default model for persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL # Fallback in case of DB error
            # Consider if this specific case should return an error to the user, e.g., if DB is expected to be reliable
            # return jsonify({"error": "Could not determine LLM model for generation due to DB error"}), 500


    # This is the payload that persona_generator.py and llm_queue.py will expect in request_params
    persona_generation_request_payload = {
        "generation_type": "from_name_and_description", 
        "input_details": {
            "name_hint": name_hint,
            "description_hint": description_hint
        },
        "output_preferences": output_preferences, # Updated
        "llm_model_for_generation": llm_model_for_generation,
        "target_persona_name_override": target_persona_name_override # Updated
    }
    request_params_json = json.dumps(persona_generation_request_payload)

    try:
        db = get_db() # Uses Flask's g
        cursor = db.cursor()
        
        # post_id_to_respond_to is NULL because this is not a reply to a post.
        # llm_persona is also NULL because we are generating a persona, not using one.
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        
        request_id = cursor.lastrowid
        db.commit()
        
        print(f"Persona generation request queued. Request ID: {request_id}, Model: {llm_model_for_generation}")
        return jsonify({"message": "Persona generation queued", "request_id": request_id}), 202
    except sqlite3.Error as e:
        print(f"Database error queuing persona generation: {e}")
        # db.rollback() is typically handled by the appcontext_teardown for g.db
        return jsonify({"error": "Failed to queue persona generation due to database error"}), 500
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"Unexpected error queuing persona generation: {e.__class__.__name__}: {e}")
        return jsonify({"error": "An unexpected error occurred while queuing persona generation"}), 500
