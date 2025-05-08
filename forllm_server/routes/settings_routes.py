import sqlite3
from flask import Blueprint, request, jsonify
from ..database import get_db
from ..config import DEFAULT_MODEL

settings_api_bp = Blueprint('settings_api', __name__, url_prefix='/api')

@settings_api_bp.route('/settings', methods=['GET', 'PUT'])
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