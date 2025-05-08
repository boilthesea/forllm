import sqlite3
from flask import Blueprint, request, jsonify
from ..database import get_db
from ..scheduler import get_current_status, get_next_schedule_info
from ..config import DAY_MAP

schedule_api_bp = Blueprint('schedule_api', __name__, url_prefix='/api') # Align prefix with other API blueprints

@schedule_api_bp.route('/schedules', methods=['GET']) # Full path for clarity
def get_schedules():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, start_hour, end_hour, days_active, enabled FROM schedule ORDER BY id")
        schedules = cursor.fetchall()
        return jsonify([dict(row) for row in schedules])
    except Exception as e:
        print(f"Error fetching schedules: {e}")
        return jsonify({'error': f'Failed to fetch schedules: {e}'}), 500

@schedule_api_bp.route('/schedules', methods=['POST']) # Full path for clarity
def add_schedule():
    db = get_db()
    cursor = db.cursor()
    data = request.get_json()
    start_hour = data.get('start_hour')
    end_hour = data.get('end_hour')
    days_active_list = data.get('days_active', [])
    enabled = data.get('enabled', True)

    if start_hour is None or end_hour is None:
        return jsonify({'error': 'Start and end hours are required'}), 400
    try:
        start_hour = int(start_hour)
        end_hour = int(end_hour)
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23): # end_hour can be 0 for midnight end of day
             raise ValueError("Hours must be between 0 and 23")
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid hour format. Hours must be integers between 0 and 23'}), 400
    if not isinstance(days_active_list, list) or not all(day in DAY_MAP.values() for day in days_active_list):
         return jsonify({'error': 'Invalid days_active format. Must be a list of valid day abbreviations (Mon, Tue, etc.)'}), 400
    days_active_str = ",".join(sorted(days_active_list, key=list(DAY_MAP.values()).index))

    try:
        cursor.execute("""
            INSERT INTO schedule (start_hour, end_hour, days_active, enabled)
            VALUES (?, ?, ?, ?)
        """, (start_hour, end_hour, days_active_str, bool(enabled)))
        new_id = cursor.lastrowid
        db.commit()
        cursor.execute("SELECT id, start_hour, end_hour, days_active, enabled FROM schedule WHERE id = ?", (new_id,))
        new_schedule = cursor.fetchone()
        return jsonify(dict(new_schedule)), 201
    except Exception as e:
        db.rollback()
        print(f"Error adding schedule: {e}")
        return jsonify({'error': f'Failed to add schedule: {e}'}), 500

@schedule_api_bp.route('/schedules/<int:schedule_id>', methods=['PUT']) # Full path for clarity
def update_schedule(schedule_id):
    db = get_db()
    cursor = db.cursor()
    data = request.get_json()
    cursor.execute("SELECT id FROM schedule WHERE id = ?", (schedule_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Schedule not found'}), 404

    updates = []
    params = []
    if 'start_hour' in data:
        try:
            start_hour = int(data['start_hour'])
            if not (0 <= start_hour <= 23): raise ValueError()
            updates.append("start_hour = ?")
            params.append(start_hour)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid start_hour format'}), 400
    if 'end_hour' in data:
        try:
            end_hour = int(data['end_hour'])
            if not (0 <= end_hour <= 23): raise ValueError() # end_hour can be 0
            updates.append("end_hour = ?")
            params.append(end_hour)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid end_hour format'}), 400
    if 'days_active' in data:
        days_list = data['days_active']
        if not isinstance(days_list, list) or not all(day in DAY_MAP.values() for day in days_list):
            return jsonify({'error': 'Invalid days_active format'}), 400
        days_str = ",".join(sorted(days_list, key=list(DAY_MAP.values()).index))
        updates.append("days_active = ?")
        params.append(days_str)
    if 'enabled' in data:
        updates.append("enabled = ?")
        params.append(bool(data['enabled']))

    if not updates:
        return jsonify({'error': 'No valid fields provided for update'}), 400
    params.append(schedule_id)
    sql = f"UPDATE schedule SET {', '.join(updates)} WHERE id = ?"
    try:
        cursor.execute(sql, tuple(params))
        db.commit()
        cursor.execute("SELECT id, start_hour, end_hour, days_active, enabled FROM schedule WHERE id = ?", (schedule_id,))
        updated_schedule = cursor.fetchone()
        return jsonify(dict(updated_schedule))
    except Exception as e:
        db.rollback()
        print(f"Error updating schedule {schedule_id}: {e}")
        return jsonify({'error': f'Failed to update schedule: {e}'}), 500

@schedule_api_bp.route('/schedules/<int:schedule_id>', methods=['DELETE']) # Full path for clarity
def delete_schedule(schedule_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM schedule WHERE id = ?", (schedule_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Schedule not found'}), 404
    try:
        cursor.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
        db.commit()
        return jsonify({'message': 'Schedule deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        print(f"Error deleting schedule {schedule_id}: {e}")
        return jsonify({'error': f'Failed to delete schedule: {e}'}), 500

@schedule_api_bp.route('/schedule/status', methods=['GET']) # Keep /schedule prefix for specific sub-routes
def get_schedule_status_api():
    return jsonify(get_current_status())

@schedule_api_bp.route('/schedule/next', methods=['GET']) # Keep /schedule prefix for specific sub-routes
def get_next_schedule_api():
    next_info = get_next_schedule_info()
    if next_info:
        return jsonify(next_info)
    else:
        return jsonify(None), 200