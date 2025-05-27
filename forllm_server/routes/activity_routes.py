from flask import Blueprint, jsonify
from ..config import CURRENT_USER_ID
from ..database import get_recent_topics, get_recent_replies, get_recent_personas

activity_bp = Blueprint('activity', __name__, url_prefix='/api/activity')

@activity_bp.route('/recent_topics', methods=['GET'])
def api_get_recent_topics():
    """
    API endpoint to fetch recent topics that are new to the current user.
    """
    # Assuming CURRENT_USER_ID is correctly populated (e.g., by a decorator or middleware if not hardcoded)
    # For this context, CURRENT_USER_ID is directly from config
    recent_topics_data = get_recent_topics(user_id=CURRENT_USER_ID)
    return jsonify(recent_topics_data)

@activity_bp.route('/recent_replies', methods=['GET'])
def api_get_recent_replies():
    """
    API endpoint to fetch recent replies that are new to the current user.
    """
    recent_replies_data = get_recent_replies(user_id=CURRENT_USER_ID)
    return jsonify(recent_replies_data)

@activity_bp.route('/recent_personas', methods=['GET'])
def api_get_recent_personas():
    """
    API endpoint to fetch the most recently created active personas.
    """
    # user_id is not needed for get_recent_personas as per current definition
    recent_personas_data = get_recent_personas()
    return jsonify(recent_personas_data)
