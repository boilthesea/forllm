import os
import threading
from flask import Flask

# Import functionalities from the new forllm_server package
from forllm_server.config import DATABASE # Though DATABASE is used in database.py, good to have if needed directly
from forllm_server.database import init_db, close_db
from forllm_server.llm_queue import llm_worker

# Import Blueprints
from forllm_server.routes.main_routes import main_bp
from forllm_server.routes.forum_routes import forum_api_bp
from forllm_server.routes.llm_routes import llm_api_bp
from forllm_server.routes.schedule_routes import schedule_api_bp
from forllm_server.routes.settings_routes import settings_api_bp

# --- Flask App Initialization ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.urandom(24) # For potential future session use

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(forum_api_bp) # Default prefix is /api
app.register_blueprint(llm_api_bp)   # Default prefix is /api
app.register_blueprint(schedule_api_bp) # Prefix is /api/schedule
app.register_blueprint(settings_api_bp) # Default prefix is /api


# Register database close function
@app.teardown_appcontext
def teardown_db(error):
    close_db(error)

# --- Main Execution ---
if __name__ == '__main__':
    print("Initializing database...")
    init_db() # Ensure DB exists and schema is created/verified

    print("Starting LLM Worker thread...")
    # Pass the Flask 'app' instance to the llm_worker thread
    worker_thread = threading.Thread(target=llm_worker, args=(app,), daemon=True)
    worker_thread.start()

    print("Starting Flask server...")
    # Host 0.0.0.0 makes it accessible on the network
    # Use_reloader=False is important when running background threads with Flask's dev server
    # to prevent the thread from being started twice.
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)