import sqlite3
from flask import Blueprint, request, jsonify
from ..database import (
    list_personas, get_persona, create_persona, update_persona, soft_delete_persona,
    revert_persona_to_version, list_persona_versions, get_global_default_persona_id, set_global_default_persona_id
)
from ..config import CURRENT_USER_ID, DEFAULT_MODEL
from ..database import get_db

settings_bp = Blueprint('settings', __name__, url_prefix='/api')

@settings_bp.route('/settings', methods=['GET', 'PUT'])
def handle_settings():
    db = get_db()
    cursor = db.cursor()

    # Define known setting keys and their default values for GET requests
    # These are also used to validate keys for PUT requests.
    # Default values match those in database.py and llm_processing.py fallbacks.
    known_settings_with_defaults = {
        'selectedModel': DEFAULT_MODEL,
        'llmLinkSecurity': 'true',
        'default_llm_context_window': '4096',
        'ch_max_ambient_posts': '5',
        'ch_max_posts_per_sibling_branch': '2',
        'ch_primary_history_budget_ratio': '0.7'
    }

    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No settings data provided'}), 400
        try:
            for key, value in data.items():
                processed_value = None
                if key not in known_settings_with_defaults:
                    print(f"Warning: Ignoring unknown setting key during update: {key}")
                    continue

                if key == 'llmLinkSecurity':
                    processed_value = 'true' if str(value).strip().lower() in ['true', '1', 'yes', 'on'] else 'false'
                elif key == 'selectedModel':
                    processed_value = str(value).strip()
                    if not processed_value:
                        print(f"Warning: Attempted to save empty string for selectedModel. Skipping.")
                        continue
                elif key == 'default_llm_context_window' or key == 'ch_max_ambient_posts' or key == 'ch_max_posts_per_sibling_branch':
                    try:
                        int_value = int(value)
                        if key.startswith('ch_') and int_value < 0:
                            print(f"Warning: Invalid negative value for {key}: {int_value}. Skipping.")
                            continue
                        processed_value = str(int_value)
                    except ValueError:
                        print(f"Warning: Invalid integer value for {key}: {value}. Skipping.")
                        continue
                elif key == 'ch_primary_history_budget_ratio':
                    try:
                        float_value = float(value)
                        if not (0.0 <= float_value <= 1.0):
                            print(f"Warning: Value for {key} ({float_value}) out of range [0.0, 1.0]. Skipping.")
                            continue
                        processed_value = str(float_value)
                    except ValueError:
                        print(f"Warning: Invalid float value for {key}: {value}. Skipping.")
                        continue
                else: # Should not be reached if all known_settings are handled above
                    print(f"Warning: Unhandled known setting key: {key}. This is a bug.")
                    continue

                if processed_value is not None:
                    cursor.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, processed_value))

            db.commit()

            # Fetch all settings again to return the current state
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

            # Ensure all known settings have a value in the response, applying defaults if somehow missing
            for s_key, s_default in known_settings_with_defaults.items():
                if s_key not in settings:
                    settings[s_key] = s_default

            return jsonify(settings)
        except Exception as e:
            db.rollback()
            print(f"Error updating settings: {e}")
            return jsonify({'error': f'Failed to update settings: {e}'}), 500
    else: # GET
        try:
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            # Ensure all known settings have a value, applying defaults if missing
            # This is important if the DB was somehow cleared or a new setting was added
            # and not yet saved by a PUT.
            for s_key, s_default in known_settings_with_defaults.items():
                if s_key not in settings:
                    settings[s_key] = s_default
            return jsonify(settings)
        except Exception as e:
            print(f"Error fetching settings: {e}")
            return jsonify({'error': f'Failed to fetch settings: {e}'}), 500

# --- Persona Management Endpoints ---
@settings_bp.route('/personas', methods=['GET'])
def api_list_personas():
    try:
        personas_data = list_personas()
        if personas_data is None:
            return jsonify({'error': 'Failed to retrieve personas due to a database error.'}), 500
        return jsonify([dict(p) for p in personas_data])
    except Exception as e:
        print(f"Unexpected error in api_list_personas: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>', methods=['GET'])
def api_get_persona(persona_id):
    try:
        p = get_persona(persona_id, active_only=False) # Allow fetching inactive to see details
        if p is None: # Could be not found or DB error
            # To distinguish, one might check logs or have get_persona return a specific error object
            # For now, assume None means "not found or error"
            # Check if it was a DB error by trying to get it as active to see if it exists
            # This is a bit convoluted, ideally get_persona would signal error type
            active_p = get_persona(persona_id, active_only=True)
            if active_p is None and get_persona(persona_id, active_only=False) is None : # Confirmed not found or db error during fetch
                 return jsonify({'error': 'Persona not found or database error during fetch.'}), 404 # Or 500 if we assume DB error
            elif active_p is None and get_persona(persona_id, active_only=False) is not None: # It exists but is inactive
                 return jsonify(dict(get_persona(persona_id, active_only=False))) # Return inactive persona
            else: # General not found
                 return jsonify({'error': 'Persona not found.'}), 404
        return jsonify(dict(p))
    except Exception as e:
        print(f"Unexpected error in api_get_persona for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas', methods=['POST'])
def api_create_persona():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided.'}), 400
        name = data.get('name')
        prompt_instructions = data.get('prompt_instructions')
        if not name or not prompt_instructions:
            return jsonify({'error': 'Name and prompt_instructions required'}), 400
        
        persona_id = create_persona(name, prompt_instructions, CURRENT_USER_ID)
        if persona_id is None:
            return jsonify({'error': 'Failed to create persona due to a database error.'}), 500
        return jsonify({'persona_id': persona_id}), 201
    except Exception as e:
        print(f"Unexpected error in api_create_persona: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>', methods=['PUT'])
def api_update_persona(persona_id):
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided.'}), 400
        name = data.get('name')
        prompt_instructions = data.get('prompt_instructions')
        if not name or not prompt_instructions:
            return jsonify({'error': 'Name and prompt_instructions required'}), 400
        
        # First check if persona exists to give a 404 if it doesn't
        existing_persona = get_persona(persona_id, active_only=False)
        if existing_persona is None:
             # This means it either doesn't exist or there was a DB error fetching it.
             # If logs show "Database error in get_persona", then it was a DB error.
            return jsonify({'error': 'Persona not found or database error checking existence.'}), 404

        success = update_persona(persona_id, name, prompt_instructions, CURRENT_USER_ID)
        if not success:
            # This could be due to the persona not being found by update_persona (already checked)
            # or a database error during the update itself.
            return jsonify({'error': 'Failed to update persona, possibly due to a database error.'}), 500
        return jsonify({'success': True})
    except Exception as e:
        print(f"Unexpected error in api_update_persona for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>', methods=['DELETE'])
def api_delete_persona(persona_id):
    try:
        # Check if persona exists to give a 404 if it doesn't before attempting delete
        existing_persona = get_persona(persona_id, active_only=False)
        if existing_persona is None:
            return jsonify({'error': 'Persona not found or database error checking existence.'}), 404
            
        success = soft_delete_persona(persona_id)
        if not success:
            # This implies a database error during the delete, as existence was checked.
            return jsonify({'error': 'Failed to delete persona due to a database error.'}), 500
        return jsonify({'success': True})
    except Exception as e:
        print(f"Unexpected error in api_delete_persona for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>/versions', methods=['GET'])
def api_list_persona_versions(persona_id):
    try:
        # Check if parent persona exists
        parent_persona = get_persona(persona_id, active_only=False)
        if parent_persona is None:
            return jsonify({'error': 'Parent persona not found or database error.'}), 404

        versions_data = list_persona_versions(persona_id)
        if versions_data is None:
            return jsonify({'error': 'Failed to retrieve persona versions due to a database error.'}), 500
        return jsonify([dict(v) for v in versions_data])
    except Exception as e:
        print(f"Unexpected error in api_list_persona_versions for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>/revert', methods=['POST'])
def api_revert_persona(persona_id):
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided.'}), 400
        version = data.get('version')
        if not isinstance(version, int): # Basic type check
            return jsonify({'error': 'Version required and must be an integer.'}), 400

        # Check if persona and version exist before attempting revert
        parent_persona = get_persona(persona_id, active_only=False)
        if parent_persona is None:
            return jsonify({'error': 'Persona not found or database error.'}), 404
        
        versions = list_persona_versions(persona_id)
        if versions is None: # DB error listing versions
             return jsonify({'error': 'Could not verify version due to database error.'}), 500
        if not any(v['version'] == version for v in versions):
            return jsonify({'error': f'Version {version} not found for persona {persona_id}.'}), 404

        success = revert_persona_to_version(persona_id, version, CURRENT_USER_ID)
        if not success:
            # This implies a database error during the revert operation itself.
            return jsonify({'error': 'Failed to revert persona version due to a database error.'}), 500
        return jsonify({'success': True})
    except Exception as e:
        print(f"Unexpected error in api_revert_persona for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/global-default', methods=['GET'])
def api_get_global_default_persona():
    try:
        persona_id = get_global_default_persona_id()
        if persona_id is None: # Indicates DB error from get_global_default_persona_id
            return jsonify({'error': 'Failed to retrieve global default persona due to a database error.'}), 500
        return jsonify({'globalDefaultPersonaId': persona_id})
    except Exception as e:
        print(f"Unexpected error in api_get_global_default_persona: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/global-default', methods=['PUT']) # Changed from POST to PUT
def api_set_global_default_persona():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided.'}), 400
            
        persona_id_str = data.get('globalDefaultPersonaId') # Match key from frontend
        if persona_id_str is None: # Check for missing key
            return jsonify({'error': 'globalDefaultPersonaId required'}), 400
        
        try:
            persona_id = int(persona_id_str)
        except ValueError:
            return jsonify({'error': 'Invalid persona_id format, must be an integer.'}), 400
            
        success = set_global_default_persona_id(persona_id)
        if not success:
            # This could be because the persona_id doesn't exist (checked in DB func),
            # or a DB error during the set operation.
            return jsonify({'error': 'Failed to set global default persona. It might be an invalid ID or a database issue.'}), 500
        return jsonify({'success': True})
    except Exception as e:
        print(f"Unexpected error in api_set_global_default_persona: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/<int:persona_id>/prompt-preview', methods=['POST']) # POST is fine for potentially complex input in future
def api_persona_prompt_preview(persona_id):
    try:
        # For now, just return the prompt_instructions as-is
        p = get_persona(persona_id) # Uses active_only=True by default
        if p is None:
            # Could be not found, inactive, or DB error.
            # Check if it exists at all (even if inactive) to give a more specific error.
            p_inactive_check = get_persona(persona_id, active_only=False)
            if p_inactive_check is None:
                 return jsonify({'error': 'Persona not found or database error.'}), 404
            else: # Exists but is inactive
                 return jsonify({'error': 'Persona is inactive and cannot be used for prompt preview.'}), 403 # Forbidden
        return jsonify({'prompt_preview': p['prompt_instructions']})
    except Exception as e:
        print(f"Unexpected error in api_persona_prompt_preview for ID {persona_id}: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@settings_bp.route('/personas/preview', methods=['POST'])
def api_persona_preview():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided.'}), 400

        name = data.get('name')
        prompt_instructions = data.get('prompt_instructions')

        # name can be empty string, but prompt_instructions must be present
        if prompt_instructions is None: 
            return jsonify({'error': 'prompt_instructions are required.'}), 400
        
        # If name is None (not provided) or an empty string, use a default for preview
        effective_name = name if name is not None and name.strip() != "" else "Unnamed Persona"

        # Simple formatting for the preview
        preview_text = f"Persona Name: {effective_name}\n\nInstructions:\n{prompt_instructions}"
        
        return jsonify({'preview_text': preview_text})

    except Exception as e:
        print(f"Error in api_persona_preview: {str(e)}")
        return jsonify({'error': 'An internal server error occurred while generating the preview.'}), 500

# Export for forllm.py compatibility
settings_api_bp = settings_bp