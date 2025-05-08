from flask import Blueprint, render_template, send_from_directory, current_app
from ..database import get_db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Serves the main index.html page."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT subforum_id, name FROM subforums ORDER BY name")
    subforums = cursor.fetchall()
    return render_template('index.html', subforums=subforums)

@main_bp.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static files (CSS, JS)."""
    return send_from_directory(current_app.static_folder, filename)