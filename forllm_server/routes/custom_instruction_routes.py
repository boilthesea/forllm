from flask import Blueprint, request, jsonify
from ..database import get_db, get_active_instructions_for_context

custom_instruction_routes = Blueprint('custom_instruction_routes', __name__)

@custom_instruction_routes.route('/api/custom-instructions', methods=['POST'])
def create_instruction():
    data = request.get_json()
    name = data.get('name')
    prompt_text = data.get('prompt_text')
    priority = data.get('priority', 0)
    is_global_default = data.get('is_global_default', False)

    if not name or not prompt_text:
        return jsonify({'error': 'Name and prompt text are required.'}), 400

    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO custom_instructions (name, prompt_text, priority, is_global_default) VALUES (?, ?, ?, ?)',
            (name, prompt_text, priority, is_global_default)
        )
        db.commit()
        return jsonify({'id': cursor.lastrowid, 'name': name, 'prompt_text': prompt_text, 'priority': priority, 'is_global_default': is_global_default}), 201
    except db.IntegrityError:
        return jsonify({'error': f"An instruction with the name '{name}' already exists."}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/custom-instructions', methods=['GET'])
def get_instructions():
    db = get_db()
    cursor = db.execute('SELECT * FROM custom_instructions ORDER BY priority, name')
    instructions = [dict(row) for row in cursor.fetchall()]
    for inst in instructions:
        cursor = db.execute('''
            SELECT s.subforum_id, s.name 
            FROM subforum_instruction_defaults sid
            JOIN subforums s ON sid.subforum_id = s.subforum_id
            WHERE sid.instruction_id = ?
        ''', (inst['id'],))
        inst['subforum_defaults'] = [dict(row) for row in cursor.fetchall()]
    return jsonify(instructions)

@custom_instruction_routes.route('/api/custom-instructions/<int:instruction_id>', methods=['PUT'])
def update_instruction(instruction_id):
    data = request.get_json()
    name = data.get('name')
    prompt_text = data.get('prompt_text')
    priority = data.get('priority')
    is_global_default = data.get('is_global_default')

    if not name or not prompt_text or priority is None or is_global_default is None:
        return jsonify({'error': 'All fields are required.'}), 400

    db = get_db()
    try:
        db.execute(
            'UPDATE custom_instructions SET name = ?, prompt_text = ?, priority = ?, is_global_default = ? WHERE id = ?',
            (name, prompt_text, priority, is_global_default, instruction_id)
        )
        db.commit()
        return jsonify({'message': 'Instruction updated successfully.'})
    except db.IntegrityError:
        return jsonify({'error': f"An instruction with the name '{name}' already exists."}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/custom-instructions/<int:instruction_id>', methods=['DELETE'])
def delete_instruction(instruction_id):
    db = get_db()
    try:
        db.execute('DELETE FROM custom_instructions WHERE id = ?', (instruction_id,))
        db.commit()
        return jsonify({'message': 'Instruction deleted successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/custom-instructions/autocomplete', methods=['GET'])
def autocomplete_instructions_and_sets():
    """
    Provides a list of active instructions and sets for autocomplete.
    Filters out instructions that are already active by default in the given context.
    """
    subforum_id = request.args.get('subforum_id', type=int)
    db = get_db()

    # Get the IDs of instructions that are already active by default
    active_defaults = get_active_instructions_for_context(subforum_id)
    active_default_ids = set(item['id'] for item in active_defaults['global'])
    active_default_ids.update(item['id'] for item in active_defaults['subforum'])

    # Get all instructions
    cursor = db.execute('SELECT id, name FROM custom_instructions ORDER BY name')
    all_instructions = [dict(row) for row in cursor.fetchall()]

    # Filter out the active defaults
    filtered_instructions = [
        {'id': inst['id'], 'name': inst['name'], 'type': 'instruction'}
        for inst in all_instructions if inst['id'] not in active_default_ids
    ]

    # Get all sets (sets are never "default", so no filtering needed)
    cursor = db.execute('SELECT id, name FROM instruction_sets ORDER BY name')
    sets = [{'id': row['id'], 'name': row['name'], 'type': 'set'} for row in cursor.fetchall()]
    
    return jsonify(filtered_instructions + sets)

@custom_instruction_routes.route('/api/instruction-sets', methods=['POST'])
def create_instruction_set():
    data = request.get_json()
    name = data.get('name')
    instruction_ids = data.get('instruction_ids', [])

    if not name:
        return jsonify({'error': 'Set name is required.'}), 400

    db = get_db()
    try:
        cursor = db.execute('INSERT INTO instruction_sets (name) VALUES (?)', (name,))
        set_id = cursor.lastrowid
        if instruction_ids:
            for instruction_id in instruction_ids:
                db.execute('INSERT INTO instruction_set_items (set_id, instruction_id) VALUES (?, ?)', (set_id, instruction_id))
        db.commit()
        return jsonify({'id': set_id, 'name': name, 'instruction_ids': instruction_ids}), 201
    except db.IntegrityError:
        return jsonify({'error': f"A set with the name '{name}' already exists."}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/instruction-sets', methods=['GET'])
def get_instruction_sets():
    db = get_db()
    cursor = db.execute('SELECT * FROM instruction_sets ORDER BY name')
    sets = [dict(row) for row in cursor.fetchall()]
    for s in sets:
        cursor = db.execute('SELECT instruction_id FROM instruction_set_items WHERE set_id = ?', (s['id'],))
        s['instruction_ids'] = [row['instruction_id'] for row in cursor.fetchall()]
    return jsonify(sets)

@custom_instruction_routes.route('/api/instruction-sets/<int:set_id>', methods=['PUT'])
def update_instruction_set(set_id):
    data = request.get_json()
    name = data.get('name')
    instruction_ids = data.get('instruction_ids')

    if not name or instruction_ids is None:
        return jsonify({'error': 'Set name and instruction IDs are required.'}), 400

    db = get_db()
    try:
        db.execute('UPDATE instruction_sets SET name = ? WHERE id = ?', (name, set_id))
        db.execute('DELETE FROM instruction_set_items WHERE set_id = ?', (set_id,))
        for instruction_id in instruction_ids:
            db.execute('INSERT INTO instruction_set_items (set_id, instruction_id) VALUES (?, ?)', (set_id, instruction_id))
        db.commit()
        return jsonify({'message': 'Instruction set updated successfully.'})
    except db.IntegrityError:
        return jsonify({'error': f"A set with the name '{name}' already exists."}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/instruction-sets/<int:set_id>', methods=['DELETE'])
def delete_instruction_set(set_id):
    db = get_db()
    try:
        db.execute('DELETE FROM instruction_sets WHERE id = ?', (set_id,))
        db.commit()
        return jsonify({'message': 'Instruction set deleted successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@custom_instruction_routes.route('/api/custom-instructions/<int:instruction_id>/subforum-defaults', methods=['POST'])
def add_subforum_default(instruction_id):
    data = request.get_json()
    subforum_id = data.get('subforum_id')

    if not subforum_id:
        return jsonify({'error': 'Subforum ID is required.'}), 400

    db = get_db()
    try:
        db.execute('INSERT INTO subforum_instruction_defaults (instruction_id, subforum_id) VALUES (?, ?)', (instruction_id, subforum_id))
        db.commit()
        return jsonify({'message': 'Subforum default added successfully.'}), 201
    except db.IntegrityError:
        return jsonify({'error': 'This instruction is already a default for this subforum.'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/custom-instructions/<int:instruction_id>/subforum-defaults/<int:subforum_id>', methods=['DELETE'])
def remove_subforum_default(instruction_id, subforum_id):
    db = get_db()
    try:
        db.execute('DELETE FROM subforum_instruction_defaults WHERE instruction_id = ? AND subforum_id = ?', (instruction_id, subforum_id))
        db.commit()
        return jsonify({'message': 'Subforum default removed successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@custom_instruction_routes.route('/api/instructions/active-for-context', methods=['GET'])
def get_active_instructions_for_context_route():
    subforum_id = request.args.get('subforum_id', type=int)
    instructions = get_active_instructions_for_context(subforum_id)
    return jsonify(instructions)