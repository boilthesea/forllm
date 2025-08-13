import os
import threading
import argparse
from flask import Flask
from waitress import serve

# Import functionalities from the new forllm_server package
from forllm_server.config import DATABASE, UPLOAD_FOLDER
from forllm_server.database import init_db, close_db, update_setting
from forllm_server.llm_queue import llm_worker
from forllm_server.file_indexer import scan_and_cache_files

# Import Blueprints
from forllm_server.routes.main_routes import main_bp
from forllm_server.routes.forum_routes import forum_api_bp
from forllm_server.routes.llm_routes import llm_api_bp
from forllm_server.routes.schedule_routes import schedule_api_bp
from forllm_server.routes.settings_routes import settings_api_bp
from forllm_server.routes.persona_routes import persona_routes_bp # Added
from forllm_server.routes.activity_routes import activity_bp # Added for activity page
from forllm_server.routes.utility_routes import utility_bp # Added for utility routes
from forllm_server.routes.file_routes import file_routes

# --- Flask App Initialization ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.urandom(24) # For potential future session use
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER # Set UPLOAD_FOLDER in app.config

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(forum_api_bp) # Default prefix is /api
app.register_blueprint(llm_api_bp)   # Default prefix is /api
app.register_blueprint(schedule_api_bp) # Prefix is /api/schedule
app.register_blueprint(settings_api_bp) # Default prefix is /api
app.register_blueprint(persona_routes_bp) # Added
app.register_blueprint(activity_bp) # Added for activity page
app.register_blueprint(utility_bp) # Added for utility routes
app.register_blueprint(file_routes)


# Register database close function
@app.teardown_appcontext
def teardown_db(error):
    close_db(error)

# --- Helper Functions ---
def reset_theme_to_default():
    """Resets the theme setting in the database to the default."""
    with app.app_context():
        print("Resetting theme to default 'theme-silvery'...")
        update_setting('theme', 'theme-silvery')
        print("Theme has been reset.")

# --- Main Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run the forllm server.")
    parser.add_argument('--reset-theme', action='store_true', help="Reset the application theme to the default 'silvery' and exit.")
    parser.add_argument('--debug', action='store_true', help="Run the application in Flask's debug mode.")
    args = parser.parse_args()

    if args.reset_theme:
        reset_theme_to_default()
        exit()
        
    # Create upload folder if it doesn't exist
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print(f"Upload folder '{app.config['UPLOAD_FOLDER']}' is ready.")
    except OSError as e:
        print(f"Error creating upload folder '{app.config['UPLOAD_FOLDER']}': {e}")
        # Depending on the severity, you might want to exit or handle this error
        # For now, we'll print the error and continue.

    print("Initializing database...")
    init_db() # Ensure DB exists and schema is created/verified

    print("Starting LLM Worker thread...")
    # Pass the Flask 'app' instance to the llm_worker thread
    worker_thread = threading.Thread(target=llm_worker, args=(app,), daemon=True)
    worker_thread.start()

    # Initial file indexing on startup
    with app.app_context():
       print("Performing initial file indexing on startup...")
       scan_and_cache_files()
       print("Initial file indexing complete.")

    if args.debug:
        print("Starting Flask development server in debug mode...")
        # Host 0.0.0.0 makes it accessible on the network
        # use_reloader=False is important for background threads
        app.run(debug=True, host='0.0.0.0', port=4773, use_reloader=False)
    else:
        print("Starting production server with Waitress...")
        # Host 0.0.0.0 makes it accessible on the network
        serve(app, host='0.0.0.0', port=4773)