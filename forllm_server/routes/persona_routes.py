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

@persona_routes_bp.route('/generate/subforum_expert', methods=['POST'])
def generate_subforum_expert_persona_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    input_details = data.get('input_details', {})
    subforum_id = input_details.get('subforum_id')
    additional_directives = input_details.get('additional_directives', '')
    name_hint = input_details.get('name_hint', '') # Optional name hint for subforum expert

    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})
    target_persona_name_override = data.get('target_persona_name_override', '')

    if not subforum_id:
        return jsonify({"error": "input_details.subforum_id is required"}), 400
    
    # Validate subforum_id (basic check, DB check could be added if necessary here or relied upon in generator)
    if not isinstance(subforum_id, int):
        return jsonify({"error": "input_details.subforum_id must be an integer"}), 400

    if not llm_model_for_generation:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor.fetchone()
            llm_model_for_generation = (model_row['setting_value'] if model_row and model_row['setting_value'] else DEFAULT_MODEL)
        except Exception as e:
            print(f"Error fetching default model for subforum expert persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL

    persona_generation_request_payload = {
        "generation_type": "subforum_expert",
        "input_details": {
            "subforum_id": subforum_id,
            "additional_directives": additional_directives,
            "name_hint": name_hint 
        },
        "output_preferences": output_preferences,
        "llm_model_for_generation": llm_model_for_generation,
        "target_persona_name_override": target_persona_name_override
    }
    request_params_json = json.dumps(persona_generation_request_payload)

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        request_id = cursor.lastrowid
        db.commit()
        
        print(f"Subforum expert persona generation queued. Request ID: {request_id}, Subforum ID: {subforum_id}, Model: {llm_model_for_generation}")
        return jsonify({"message": "Subforum expert persona generation queued", "request_id": request_id}), 202
    except sqlite3.Error as e:
        print(f"Database error queuing subforum expert persona generation: {e}")
        return jsonify({"error": "Failed to queue subforum expert persona generation due to database error"}), 500
    except Exception as e:
        print(f"Unexpected error queuing subforum expert persona generation: {e.__class__.__name__}: {e}")
        return jsonify({"error": "An unexpected error occurred while queuing subforum expert persona generation"}), 500

@persona_routes_bp.route('/subforums/<int:subforum_id>/generate_expert_persona', methods=['POST'])
def generate_expert_persona_for_subforum_api(subforum_id):
    data = request.get_json()
    if not data: # Data can be empty if only using path subforum_id and defaults
        data = {}

    input_details_from_body = data.get('input_details', {})
    additional_directives = input_details_from_body.get('additional_directives', '')
    name_hint = input_details_from_body.get('name_hint', '')

    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})
    target_persona_name_override = data.get('target_persona_name_override', '')
    
    if not llm_model_for_generation:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor.fetchone()
            llm_model_for_generation = (model_row['setting_value'] if model_row and model_row['setting_value'] else DEFAULT_MODEL)
        except Exception as e:
            print(f"Error fetching default model for subforum expert persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL

    persona_generation_request_payload = {
        "generation_type": "subforum_expert",
        "input_details": {
            "subforum_id": subforum_id, # From path
            "additional_directives": additional_directives,
            "name_hint": name_hint
        },
        "output_preferences": output_preferences,
        "llm_model_for_generation": llm_model_for_generation,
        "target_persona_name_override": target_persona_name_override
    }
    request_params_json = json.dumps(persona_generation_request_payload)

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        request_id = cursor.lastrowid
        db.commit()
        
        print(f"Subforum expert persona generation queued via path. Request ID: {request_id}, Subforum ID: {subforum_id}, Model: {llm_model_for_generation}")
        return jsonify({"message": "Subforum expert persona generation queued", "request_id": request_id}), 202
    except sqlite3.Error as e:
        print(f"Database error queuing subforum expert persona generation (path): {e}")
        return jsonify({"error": "Failed to queue subforum expert persona generation due to database error"}), 500
    except Exception as e:
        print(f"Unexpected error queuing subforum expert persona generation (path): {e.__class__.__name__}: {e}")
        return jsonify({"error": "An unexpected error occurred while queuing subforum expert persona generation"}), 500

@persona_routes_bp.route('/generate/subforum_experts_batch', methods=['POST'])
def generate_subforum_experts_batch_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subforum_id = data.get('subforum_id')
    number_to_generate = data.get('number_to_generate')
    input_details_base = data.get('input_details', {}) # Base for additional_directives, name_hint
    additional_directives = input_details_base.get('additional_directives', '')
    name_hint_base = input_details_base.get('name_hint', '') # Base name hint, can be augmented if desired

    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})
    # target_persona_name_override is intentionally NOT read from request for batch,
    # as each persona should have a unique, generated name.

    if not subforum_id:
        return jsonify({"error": "subforum_id is required"}), 400
    if not isinstance(subforum_id, int):
        return jsonify({"error": "subforum_id must be an integer"}), 400
    
    if not number_to_generate:
        return jsonify({"error": "number_to_generate is required"}), 400
    if not isinstance(number_to_generate, int) or number_to_generate <= 0:
        return jsonify({"error": "number_to_generate must be a positive integer"}), 400
    if number_to_generate > 10: # Safety limit
        return jsonify({"error": "number_to_generate cannot exceed 10 for a single batch request"}), 400


    if not llm_model_for_generation:
        try:
            db_temp = get_db() # Temporary for this block
            cursor_temp = db_temp.cursor()
            cursor_temp.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor_temp.fetchone()
            llm_model_for_generation = (model_row['setting_value'] if model_row and model_row['setting_value'] else DEFAULT_MODEL)
        except Exception as e:
            print(f"Error fetching default model for batch persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL
    
    queued_request_ids = []
    db = get_db() # Get DB connection for the transaction
    cursor = db.cursor()

    try:
        for i in range(number_to_generate):
            # For batch, ensure target_persona_name_override is empty so names are generated.
            # A slight variation to name_hint could be added per iteration if desired, e.g., f"{name_hint_base} #{i+1}"
            # For now, using the same name_hint for all in the batch.
            current_name_hint = name_hint_base # Potentially f"{name_hint_base} Variant {i+1}" 

            persona_generation_request_payload = {
                "generation_type": "subforum_expert",
                "input_details": {
                    "subforum_id": subforum_id,
                    "additional_directives": additional_directives,
                    "name_hint": current_name_hint 
                },
                "output_preferences": output_preferences,
                "llm_model_for_generation": llm_model_for_generation,
                "target_persona_name_override": "" # Ensure empty so generator creates name
            }
            request_params_json = json.dumps(persona_generation_request_payload)

            cursor.execute("""
                INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
            queued_request_ids.append(cursor.lastrowid)
        
        db.commit() # Commit all inserts as a transaction
        
        print(f"Batch subforum expert persona generation queued. Count: {number_to_generate}, Subforum ID: {subforum_id}, Request IDs: {queued_request_ids}")
        return jsonify({
            "message": f"{number_to_generate} subforum expert persona generation requests queued.",
            "request_ids": queued_request_ids,
            "subforum_id": subforum_id
        }), 202

    except sqlite3.Error as e:
        db.rollback() # Rollback on any DB error during the loop
        print(f"Database error during batch persona generation: {e}")
        return jsonify({"error": "Failed to queue batch persona generation due to database error"}), 500
    except Exception as e:
        db.rollback() # Rollback on any other error
        print(f"Unexpected error during batch persona generation: {e.__class__.__name__}: {e}")
        return jsonify({"error": "An unexpected error occurred while queuing batch persona generation"}), 500
    # No finally block needed to close db, as Flask handles g.db
