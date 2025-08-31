import json
import sqlite3
import os
from flask import Blueprint, request, jsonify
from forllm_server.database import get_db, list_personas, get_subforum_details
from forllm_server.config import CURRENT_USER_ID 
from forllm_server.config import DEFAULT_MODEL

persona_routes_bp = Blueprint('persona_routes_bp', __name__, url_prefix='/api/personas')

def _prepare_persona_generation_prompts(payload):
    """
    Loads templates, constructs stage 1 prompt, and adds them to the payload.
    Returns the modified payload or raises an exception.
    """
    generation_type = payload.get('generation_type')
    input_details = payload.get('input_details', {})

    if generation_type == "from_name_and_description":
        expansion_template_name = "from_name_and_description.txt"
        refinement_template_name = "from_name_and_description.txt"
        name_hint = input_details.get('name_hint', '')
        description_hint = input_details.get('description_hint', '')
    elif generation_type == "subforum_expert":
        expansion_template_name = "subforum_expert.txt"
        refinement_template_name = "subforum_expert.txt"
        subforum_id = input_details.get('subforum_id')
        if not subforum_id:
            raise ValueError("subforum_id is required for subforum_expert prompt generation.")
        
        sf_details = get_subforum_details(subforum_id)
        if not sf_details:
            raise ValueError(f"Could not retrieve details for subforum_id {subforum_id}.")
        
        subforum_name = sf_details['name']
        subforum_description = sf_details['description']
        additional_directives = input_details.get('additional_directives', '')
    else:
        raise ValueError(f"Unsupported generation_type: {generation_type}")

    # Load Stage 1 Template and construct prompt
    expansion_template_path = os.path.join(
        os.path.dirname(__file__), '..', 'persona_prompt_templates', 'expansion', expansion_template_name
    )
    with open(expansion_template_path, 'r', encoding='utf-8') as f:
        expansion_template = f.read()
    
    if generation_type == "from_name_and_description":
        stage1_full_prompt = expansion_template.replace("{{name_hint}}", name_hint or '').replace("{{description_hint}}", description_hint or '')
    else: # subforum_expert
        stage1_full_prompt = expansion_template.replace("{{subforum_name}}", subforum_name or '')
        stage1_full_prompt = stage1_full_prompt.replace("{{subforum_description}}", subforum_description or '')
        stage1_full_prompt = stage1_full_prompt.replace("{{additional_directives}}", additional_directives or '')

    payload['stage1_full_prompt'] = stage1_full_prompt

    # Load Stage 2 Template
    refinement_template_path = os.path.join(
        os.path.dirname(__file__), '..', 'persona_prompt_templates', 'refinement', refinement_template_name
    )
    with open(refinement_template_path, 'r', encoding='utf-8') as f:
        stage2_prompt_template = f.read()
    payload['stage2_prompt_template'] = stage2_prompt_template
    
    return payload

@persona_routes_bp.route('/generate/from_details', methods=['POST'])
def generate_persona_from_details_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    name_hint = data.get('name_hint')
    description_hint = data.get('description_hint')
    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})
    target_persona_name_override = data.get('target_persona_name_override', '')

    if not description_hint:
        return jsonify({"error": "description_hint is required"}), 400
    
    if not llm_model_for_generation:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor.fetchone()
            if model_row and model_row['setting_value']:
                llm_model_for_generation = model_row['setting_value']
            else:
                llm_model_for_generation = DEFAULT_MODEL
        except Exception as e:
            print(f"Error fetching default model for persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL

    persona_generation_request_payload = {
        "generation_type": "from_name_and_description", 
        "input_details": {
            "name_hint": name_hint,
            "description_hint": description_hint
        },
        "output_preferences": output_preferences,
        "llm_model_for_generation": llm_model_for_generation,
        "target_persona_name_override": target_persona_name_override
    }
    
    try:
        persona_generation_request_payload = _prepare_persona_generation_prompts(persona_generation_request_payload)
        request_params_json = json.dumps(persona_generation_request_payload)
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        
        request_id = cursor.lastrowid
        db.commit()
        
        return jsonify({"message": "Persona generation queued", "request_id": request_id}), 202
    except (sqlite3.Error, ValueError, FileNotFoundError) as e:
        print(f"Error queuing persona generation: {e}")
        return jsonify({"error": "Failed to queue persona generation due to server error"}), 500

@persona_routes_bp.route('/generate/subforum_expert', methods=['POST'])
def generate_subforum_expert_persona_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    input_details = data.get('input_details', {})
    subforum_id = input_details.get('subforum_id')
    additional_directives = input_details.get('additional_directives', '')
    name_hint = input_details.get('name_hint', '')

    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})
    target_persona_name_override = data.get('target_persona_name_override', '')

    if not subforum_id or not isinstance(subforum_id, int):
        return jsonify({"error": "A valid integer input_details.subforum_id is required"}), 400

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

    try:
        persona_generation_request_payload = _prepare_persona_generation_prompts(persona_generation_request_payload)
        request_params_json = json.dumps(persona_generation_request_payload)
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        request_id = cursor.lastrowid
        db.commit()
        
        return jsonify({"message": "Subforum expert persona generation queued", "request_id": request_id}), 202
    except (sqlite3.Error, ValueError, FileNotFoundError) as e:
        print(f"Error queuing subforum expert persona generation: {e}")
        return jsonify({"error": "Failed to queue subforum expert persona generation due to server error"}), 500

@persona_routes_bp.route('/subforums/<int:subforum_id>/generate_expert_persona', methods=['POST'])
def generate_expert_persona_for_subforum_api(subforum_id):
    data = request.get_json() or {}

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
            "subforum_id": subforum_id,
            "additional_directives": additional_directives,
            "name_hint": name_hint
        },
        "output_preferences": output_preferences,
        "llm_model_for_generation": llm_model_for_generation,
        "target_persona_name_override": target_persona_name_override
    }

    try:
        persona_generation_request_payload = _prepare_persona_generation_prompts(persona_generation_request_payload)
        request_params_json = json.dumps(persona_generation_request_payload)
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
        request_id = cursor.lastrowid
        db.commit()
        
        return jsonify({"message": "Subforum expert persona generation queued", "request_id": request_id}), 202
    except (sqlite3.Error, ValueError, FileNotFoundError) as e:
        print(f"Error queuing subforum expert persona generation: {e}")
        return jsonify({"error": "Failed to queue subforum expert persona generation due to server error"}), 500

@persona_routes_bp.route('/generate/subforum_experts_batch', methods=['POST'])
def generate_subforum_experts_batch_api():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subforum_id = data.get('subforum_id')
    number_to_generate = data.get('number_to_generate')
    input_details_base = data.get('input_details', {})
    additional_directives = input_details_base.get('additional_directives', '')
    name_hint_base = input_details_base.get('name_hint', '')

    llm_model_for_generation = data.get('llm_model_for_generation')
    output_preferences = data.get('output_preferences', {})

    if not subforum_id or not isinstance(subforum_id, int):
        return jsonify({"error": "A valid integer subforum_id is required"}), 400
    
    if not number_to_generate or not isinstance(number_to_generate, int) or not 0 < number_to_generate <= 10:
        return jsonify({"error": "number_to_generate must be an integer between 1 and 10"}), 400

    if not llm_model_for_generation:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
            model_row = cursor.fetchone()
            llm_model_for_generation = (model_row['setting_value'] if model_row and model_row['setting_value'] else DEFAULT_MODEL)
        except Exception as e:
            print(f"Error fetching default model for batch persona generation: {e}")
            llm_model_for_generation = DEFAULT_MODEL
    
    queued_request_ids = []
    db = get_db()
    cursor = db.cursor()

    try:
        for i in range(number_to_generate):
            current_name_hint = name_hint_base

            persona_generation_request_payload = {
                "generation_type": "subforum_expert",
                "input_details": {
                    "subforum_id": subforum_id,
                    "additional_directives": additional_directives,
                    "name_hint": current_name_hint 
                },
                "output_preferences": output_preferences,
                "llm_model_for_generation": llm_model_for_generation,
                "target_persona_name_override": ""
            }
            
            final_payload = _prepare_persona_generation_prompts(persona_generation_request_payload)
            request_params_json = json.dumps(final_payload)

            cursor.execute("""
                INSERT INTO llm_requests (request_type, request_params, status, llm_model, post_id_to_respond_to, llm_persona)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('generate_persona', request_params_json, 'pending', llm_model_for_generation, None, None))
            queued_request_ids.append(cursor.lastrowid)
        
        db.commit()
        
        return jsonify({
            "message": f"{number_to_generate} subforum expert persona generation requests queued.",
            "request_ids": queued_request_ids,
            "subforum_id": subforum_id
        }), 202

    except (sqlite3.Error, ValueError, FileNotFoundError) as e:
        db.rollback()
        print(f"Error during batch persona generation: {e}")
        return jsonify({"error": "Failed to queue batch persona generation due to server error"}), 500

@persona_routes_bp.route('/list_active', methods=['GET'])
def list_active_personas_api():
    try:
        active_personas_rows = list_personas(active_only=True)

        if active_personas_rows is None:
            print("Error fetching active personas: list_personas returned None.")
            return jsonify({"error": "Failed to retrieve personas due to a database error"}), 500

        personas_list = [{"persona_id": row["persona_id"], "name": row["name"]} for row in active_personas_rows]
        personas_list.sort(key=lambda x: x['name'])
        
        return jsonify(personas_list), 200

    except sqlite3.Error as e:
        print(f"Database error in list_active_personas_api: {e}")
        return jsonify({"error": "A database error occurred while retrieving active personas."}), 500
    except Exception as e:
        print(f"Unexpected error in list_active_personas_api: {e.__class__.__name__}: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500
