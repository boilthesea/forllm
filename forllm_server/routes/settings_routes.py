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
    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No settings data provided'}), 400
        try:
            for key, value in data.items():
                if key in ['darkMode', 'selectedModel', 'llmLinkSecurity']:
                    processed_value = value
                    if key == 'darkMode' or key == 'llmLinkSecurity':
                        if isinstance(value, bool):
                            processed_value = 'true' if value else 'false'
                        else:
                            bool_val = str(value).strip().lower() in ['true', '1', 'yes', 'on']
                            processed_value = 'true' if bool_val else 'false'
                    elif key == 'selectedModel':
                        processed_value = str(value).strip()
                        if not processed_value:
                             print(f"Warning: Attempted to save empty string for selectedModel.")
                             continue # Skip saving this key if invalid
                    cursor.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, processed_value))
                else:
                    print(f"Warning: Ignoring unknown setting key during update: {key}")
            db.commit()
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            # Ensure defaults are applied if any known setting is somehow missing after update
            if 'darkMode' not in settings: settings['darkMode'] = 'false'
            if 'selectedModel' not in settings: settings['selectedModel'] = DEFAULT_MODEL
            if 'llmLinkSecurity' not in settings: settings['llmLinkSecurity'] = 'true'
            return jsonify(settings)
        except Exception as e:
            db.rollback()
            print(f"Error updating settings: {e}")
            return jsonify({'error': f'Failed to update settings: {e}'}), 500
    else: # GET
        try:
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            if 'darkMode' not in settings:
                settings['darkMode'] = 'false'
            if 'selectedModel' not in settings:
                settings['selectedModel'] = DEFAULT_MODEL
            if 'llmLinkSecurity' not in settings:
                settings['llmLinkSecurity'] = 'true'
            return jsonify(settings)
        except Exception as e:
            print(f"Error fetching settings: {e}")
            return jsonify({'error': f'Failed to fetch settings: {e}'}), 500

# --- Persona Management Endpoints ---
@settings_bp.route('/personas', methods=['GET'])
def api_list_personas():
    personas = list_personas()
    return jsonify([dict(p) for p in personas])

@settings_bp.route('/personas/<int:persona_id>', methods=['GET'])
def api_get_persona(persona_id):
    p = get_persona(persona_id, active_only=False)
    if not p:
        return jsonify({'error': 'Persona not found'}), 404
    return jsonify(dict(p))

@settings_bp.route('/personas', methods=['POST'])
def api_create_persona():
    data = request.json
    name = data.get('name')
    prompt_instructions = data.get('prompt_instructions')
    if not name or not prompt_instructions:
        return jsonify({'error': 'Name and prompt_instructions required'}), 400
    persona_id = create_persona(name, prompt_instructions, CURRENT_USER_ID)
    return jsonify({'persona_id': persona_id}), 201

@settings_bp.route('/personas/<int:persona_id>', methods=['PUT'])
def api_update_persona(persona_id):
    data = request.json
    name = data.get('name')
    prompt_instructions = data.get('prompt_instructions')
    if not name or not prompt_instructions:
        return jsonify({'error': 'Name and prompt_instructions required'}), 400
    ok = update_persona(persona_id, name, prompt_instructions, CURRENT_USER_ID)
    if not ok:
        return jsonify({'error': 'Persona not found'}), 404
    return jsonify({'success': True})

@settings_bp.route('/personas/<int:persona_id>', methods=['DELETE'])
def api_delete_persona(persona_id):
    ok = soft_delete_persona(persona_id)
    if not ok:
        return jsonify({'error': 'Persona not found'}), 404
    return jsonify({'success': True})

@settings_bp.route('/personas/<int:persona_id>/versions', methods=['GET'])
def api_list_persona_versions(persona_id):
    versions = list_persona_versions(persona_id)
    return jsonify([dict(v) for v in versions])

@settings_bp.route('/personas/<int:persona_id>/revert', methods=['POST'])
def api_revert_persona(persona_id):
    data = request.json
    version = data.get('version')
    if not version:
        return jsonify({'error': 'Version required'}), 400
    ok = revert_persona_to_version(persona_id, version, CURRENT_USER_ID)
    if not ok:
        return jsonify({'error': 'Version not found'}), 404
    return jsonify({'success': True})

@settings_bp.route('/personas/global-default', methods=['GET'])
def api_get_global_default_persona():
    persona_id = get_global_default_persona_id()
    return jsonify({'globalDefaultPersonaId': persona_id})

@settings_bp.route('/personas/global-default', methods=['POST'])
def api_set_global_default_persona():
    data = request.json
    persona_id = data.get('persona_id')
    if not persona_id:
        return jsonify({'error': 'persona_id required'}), 400
    ok = set_global_default_persona_id(persona_id)
    if not ok:
        return jsonify({'error': 'Failed to set global default'}), 400
    return jsonify({'success': True})

@settings_bp.route('/personas/<int:persona_id>/prompt-preview', methods=['POST'])
def api_persona_prompt_preview(persona_id):
    # For now, just return the prompt_instructions as-is (could expand to show full prompt context)
    p = get_persona(persona_id)
    if not p:
        return jsonify({'error': 'Persona not found'}), 404
    return jsonify({'prompt_preview': p['prompt_instructions']})

# Export for forllm.py compatibility
settings_api_bp = settings_bp