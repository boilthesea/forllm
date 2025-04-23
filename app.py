import os
import sqlite3
import threading
import queue
import time
import datetime
import requests
import json # For settings
from flask import Flask, request, jsonify, render_template, g, send_from_directory

# --- Configuration ---
DATABASE = 'forllm_data.db'
# Assume a single user for MVP
CURRENT_USER_ID = 1
CURRENT_USERNAME = "LocalUser"
# Placeholder for Ollama API endpoint
OLLAMA_BASE_URL = "http://localhost:11434" # Base Ollama URL
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags" # Endpoint to list local models
DEFAULT_MODEL = "llama3" # A sensible default

# --- Flask App Initialization ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.urandom(24) # For potential future session use

# --- Database Setup ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'db'):
        g.db.close()

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()

    # Check if users table exists (as a proxy for initial setup)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_table_exists = cursor.fetchone()

    if not users_table_exists:
        print("Database appears empty or incomplete. Creating/Verifying schema...")
        # Create tables based on the plan (idempotent creation)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subforums (
                subforum_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subforum_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subforum_id) REFERENCES subforums(subforum_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                parent_post_id INTEGER, -- NULL for top-level posts in a topic
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_llm_response BOOLEAN DEFAULT FALSE,
                llm_model_id TEXT,
                llm_persona_id TEXT,
                FOREIGN KEY (topic_id) REFERENCES topics(topic_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (parent_post_id) REFERENCES posts(post_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id_to_respond_to INTEGER NOT NULL,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, complete, error
                llm_model TEXT,
                llm_persona TEXT,
                processed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (post_id_to_respond_to) REFERENCES posts(post_id)
            )
        ''')
        cursor.execute('''
             CREATE TABLE IF NOT EXISTS schedule (
                schedule_id INTEGER PRIMARY KEY DEFAULT 1, -- Only one schedule row needed
                start_hour INTEGER DEFAULT 0, -- 0-23
                end_hour INTEGER DEFAULT 6,   -- 0-23
                enabled BOOLEAN DEFAULT TRUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
        ''')

        # Insert default user if not present
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (CURRENT_USER_ID, CURRENT_USERNAME))
        # Insert default schedule if not present
        cursor.execute("INSERT OR IGNORE INTO schedule (schedule_id, start_hour, end_hour, enabled) VALUES (1, 0, 6, TRUE)")
        # Insert default settings if not present
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('darkMode', 'false'))
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('selectedModel', DEFAULT_MODEL))
        print("Database schema verified/created.")
        db.commit() # Commit after initial schema creation/verification
    else:
        # --- Check specifically for the settings table if DB already exists ---
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        settings_table_exists = cursor.fetchone()
        if not settings_table_exists:
            print("Settings table missing. Creating settings table...")
            cursor.execute('''
                CREATE TABLE settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT
                )
            ''')
            # Insert default settings only if table was just created
            cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('darkMode', 'false'))
            cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('selectedModel', DEFAULT_MODEL))
            print("Settings table created with defaults.")
            db.commit() # Commit after creating settings table
        else:
            print("Database found and schema appears up-to-date.")

    # No need for final commit/close here if already done inside blocks
    db.close()

# --- LLM Processing Queue & Worker (Placeholders) ---
llm_request_queue = queue.Queue()
processing_active = threading.Event() # To signal if processing is allowed by schedule

def is_processing_time():
    """Checks if the current time is within the scheduled processing window."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row # Ensure dictionary-like rows
    cursor = db.cursor()
    cursor.execute('SELECT start_hour, end_hour, enabled FROM schedule WHERE schedule_id = 1')
    schedule = cursor.fetchone()
    db.close()

    if not schedule or not schedule['enabled']: # Access by name now
        return False

    start_hour, end_hour = schedule['start_hour'], schedule['end_hour'] # Access by name now
    now = datetime.datetime.now().time()
    start_time = datetime.time(start_hour, 0)
    end_time = datetime.time(end_hour, 0)

    if start_hour <= end_hour:
        # Schedule does not cross midnight (e.g., 9:00 to 17:00)
        return start_time <= now < end_time
    else:
        # Schedule crosses midnight (e.g., 22:00 to 6:00)
        return now >= start_time or now < end_time


def llm_worker():
    """Background worker thread to process LLM requests from the queue."""
    print("LLM Worker thread started.")
    while True:
        if is_processing_time():
            processing_active.set() # Signal that processing is allowed
            print("Processing time active. Checking queue...")
            try:
                # Prioritize getting items from the software queue first
                request_details = llm_request_queue.get(timeout=5) # Wait 5 seconds for an item
                process_llm_request(request_details)
                llm_request_queue.task_done()
            except queue.Empty:
                # If software queue is empty, check DB queue for pending items
                print("Software queue empty, checking DB queue...")
                db = sqlite3.connect(DATABASE)
                db.row_factory = sqlite3.Row # Ensure dictionary-like rows
                cursor = db.cursor()
                cursor.execute("SELECT request_id, post_id_to_respond_to, llm_model, llm_persona FROM llm_requests WHERE status = 'pending' ORDER BY requested_at ASC LIMIT 1")
                db_request = cursor.fetchone()
                if db_request:
                    # Access by column name now that row_factory is set
                    request_id = db_request['request_id']
                    post_id = db_request['post_id_to_respond_to']
                    model = db_request['llm_model']
                    persona = db_request['llm_persona']
                    print(f"Found pending request in DB: {request_id}")
                    # Mark as processing in DB immediately
                    cursor.execute("UPDATE llm_requests SET status = 'processing' WHERE request_id = ?", (request_id,))
                    db.commit()
                    db.close()
                    # Process the request found in the DB
                    process_llm_request({
                        'request_id': request_id,
                        'post_id': post_id,
                        'model': model or "default_model", # Use defaults if needed
                        'persona': persona or "default_persona"
                    })
                else:
                    db.close()
                    print("DB queue also empty. Sleeping...")
                    time.sleep(10) # Sleep longer if DB queue is also empty
        else:
            processing_active.clear() # Signal that processing is paused
            print(f"Outside processing hours. Worker sleeping... (Will check again in 60s)")
            time.sleep(60) # Sleep longer when outside processing hours


def process_llm_request(request_details):
    """Handles the actual LLM interaction for a given request."""
    request_id = request_details['request_id']
    post_id = request_details['post_id']
    # Get the currently selected model from settings
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row # Ensure dictionary-like rows
    settings_cursor = db_conn.cursor()
    settings_cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'selectedModel'")
    model_setting = settings_cursor.fetchone()
    db_conn.close()
    # Removed DEBUG print
    model = model_setting['setting_value'] if model_setting else DEFAULT_MODEL # Access by name

    # Persona handling remains basic for now
    persona = request_details.get('persona', 'default_persona')
    print(f"Processing request {request_id} for post {post_id} with selected model '{model}' and persona '{persona}'...")

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row # Ensure dictionary-like rows
    cursor = db.cursor()

    try:
        # 1. Get the content of the post to respond to (and maybe context)
        cursor.execute("SELECT content FROM posts WHERE post_id = ?", (post_id,))
        original_post = cursor.fetchone()
        if not original_post:
            raise ValueError(f"Original post {post_id} not found.")

        # Removed DEBUG print
        prompt_content = f"User wrote: {original_post['content']}\n\nRespond to this post." # Simple prompt for MVP - This should now work
        # TODO: Add persona instructions and potentially more thread context later

        # 2. Call Ollama API (Replace with actual call)
        print(f"Sending prompt to Ollama ({OLLAMA_GENERATE_URL}) for model '{model}'...")
        # --- Actual Ollama call ---
        try:
            response = requests.post(
                OLLAMA_GENERATE_URL,
                json={'model': model, 'prompt': prompt_content, 'stream': False},
                headers={'Content-Type': 'application/json'}, # Ensure correct header
                timeout=300 # Add a timeout (e.g., 5 minutes)
            )
            response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
            response_data = response.json()
            llm_response_content = response_data.get('response')
            if llm_response_content is None:
                 # Log the full response if the expected field is missing
                print(f"Warning: 'response' field missing in Ollama reply for request {request_id}. Full response: {response_data}")
                raise ValueError("Ollama response missing 'response' field.")
            print(f"Received response from Ollama for request {request_id}.")
        except requests.exceptions.RequestException as req_err:
            print(f"Ollama API request failed: {req_err}")
            raise ConnectionError(f"Failed to connect or communicate with Ollama API: {req_err}") from req_err
        # --------------------------

        # 3. Save the LLM response to the posts table
        cursor.execute("""
            INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id)
            SELECT topic_id, ?, ?, ?, TRUE, ?, ?
            FROM posts WHERE post_id = ?
        """, (CURRENT_USER_ID, post_id, llm_response_content, model, persona, post_id))
        new_post_id = cursor.lastrowid
        print(f"Saved LLM response as post {new_post_id}")

        # 4. Update the status in llm_requests table
        cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        db.commit()
        print(f"Request {request_id} marked as complete.")

    except Exception as e:
        print(f"Error processing request {request_id}: {e}")
        # Update status to 'error' in DB
        cursor.execute("UPDATE llm_requests SET status = 'error', error_message = ?, processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (str(e), request_id))
        db.commit()
    finally:
        db.close()


# --- Routes ---
@app.route('/')
def index():
    """Serves the main index.html page."""
    # For MVP, maybe pass initial data like subforums
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT subforum_id, name FROM subforums ORDER BY name")
    subforums = cursor.fetchall()
    return render_template('index.html', subforums=subforums)

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static files (CSS, JS)."""
    return send_from_directory(app.static_folder, filename)

# --- API Endpoints (Placeholders - To be implemented) ---

@app.route('/api/subforums', methods=['GET', 'POST'])
def handle_subforums():
    db = get_db()
    cursor = db.cursor()
    if request.method == 'POST':
        # Create new subforum
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Subforum name is required'}), 400
        try:
            cursor.execute('INSERT INTO subforums (name) VALUES (?)', (name,))
            db.commit()
            new_id = cursor.lastrowid
            return jsonify({'subforum_id': new_id, 'name': name}), 201
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Subforum name already exists'}), 409
    else: # GET
        cursor.execute("SELECT subforum_id, name FROM subforums ORDER BY name")
        subforums = cursor.fetchall()
        return jsonify([dict(row) for row in subforums])


@app.route('/api/subforums/<int:subforum_id>/topics', methods=['GET', 'POST'])
def handle_topics(subforum_id):
    db = get_db()
    cursor = db.cursor()
    # Check if subforum exists
    cursor.execute("SELECT subforum_id FROM subforums WHERE subforum_id = ?", (subforum_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Subforum not found'}), 404

    if request.method == 'POST':
        # Create new topic and its initial post
        data = request.get_json()
        title = data.get('title')
        content = data.get('content')
        if not title or not content:
            return jsonify({'error': 'Title and content are required for a new topic'}), 400

        try:
            # Create topic
            cursor.execute('INSERT INTO topics (subforum_id, user_id, title) VALUES (?, ?, ?)',
                           (subforum_id, CURRENT_USER_ID, title))
            topic_id = cursor.lastrowid

            # Create the initial post for the topic
            cursor.execute('INSERT INTO posts (topic_id, user_id, content) VALUES (?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, content))
            post_id = cursor.lastrowid

            db.commit()
            return jsonify({'topic_id': topic_id, 'title': title, 'initial_post_id': post_id}), 201
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Failed to create topic: {e}'}), 500
    else: # GET
        # List topics in the subforum
        cursor.execute("""
            SELECT t.topic_id, t.title, u.username, t.created_at,
                   (SELECT COUNT(*) FROM posts p WHERE p.topic_id = t.topic_id) as post_count,
                   (SELECT MAX(p.created_at) FROM posts p WHERE p.topic_id = t.topic_id) as last_post_at
            FROM topics t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.subforum_id = ?
            ORDER BY last_post_at DESC
        """, (subforum_id,))
        topics = cursor.fetchall()
        return jsonify([dict(row) for row in topics])


@app.route('/api/topics/<int:topic_id>/posts', methods=['GET', 'POST'])
def handle_posts(topic_id):
    db = get_db()
    cursor = db.cursor()
    # Check if topic exists
    cursor.execute("SELECT topic_id FROM topics WHERE topic_id = ?", (topic_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Topic not found'}), 404

    if request.method == 'POST':
        # Create a new reply post
        data = request.get_json()
        content = data.get('content')
        parent_post_id = data.get('parent_post_id') # ID of the post being replied to
        if not content:
            return jsonify({'error': 'Content is required for a reply'}), 400
        if not parent_post_id:
             return jsonify({'error': 'Parent post ID is required for a reply'}), 400

        # Verify parent post exists within this topic
        cursor.execute("SELECT post_id FROM posts WHERE post_id = ? AND topic_id = ?", (parent_post_id, topic_id))
        if not cursor.fetchone():
            return jsonify({'error': 'Parent post not found in this topic'}), 404

        try:
            cursor.execute('INSERT INTO posts (topic_id, user_id, parent_post_id, content) VALUES (?, ?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, parent_post_id, content))
            post_id = cursor.lastrowid
            db.commit()
            # Return the newly created post
            cursor.execute("SELECT p.*, u.username FROM posts p JOIN users u ON p.user_id = u.user_id WHERE p.post_id = ?", (post_id,))
            new_post = cursor.fetchone()
            return jsonify(dict(new_post)), 201
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Failed to create post: {e}'}), 500
    else: # GET
        # Get all posts for the topic, ordered for threaded display
        cursor.execute("""
            WITH RECURSIVE ThreadCTE AS (
                -- Anchor member: Top-level posts (no parent)
                SELECT
                    p.post_id, p.topic_id, p.user_id, u.username, p.parent_post_id, p.content, p.created_at,
                    p.is_llm_response, p.llm_model_id, p.llm_persona_id,
                    CAST(p.created_at AS TEXT) AS sort_key, -- Use created_at for top-level sort
                    0 AS depth
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.topic_id = ? AND p.parent_post_id IS NULL

                UNION ALL

                -- Recursive member: Replies to posts already in the CTE
                SELECT
                    p2.post_id, p2.topic_id, p2.user_id, u2.username, p2.parent_post_id, p2.content, p2.created_at,
                    p2.is_llm_response, p2.llm_model_id, p2.llm_persona_id,
                    cte.sort_key || '_' || CAST(p2.created_at AS TEXT), -- Append child's created_at for sorting within siblings
                    cte.depth + 1
                FROM posts p2
                JOIN users u2 ON p2.user_id = u2.user_id
                JOIN ThreadCTE cte ON p2.parent_post_id = cte.post_id
                WHERE p2.topic_id = ?
            )
            SELECT * FROM ThreadCTE ORDER BY sort_key;
        """, (topic_id, topic_id))
        posts = cursor.fetchall()
        return jsonify([dict(row) for row in posts])


@app.route('/api/posts/<int:post_id>/request_llm', methods=['POST'])
def request_llm_response(post_id):
    db = get_db()
    cursor = db.cursor()
    # Check if post exists and is not itself an LLM response
    cursor.execute("SELECT post_id FROM posts WHERE post_id = ? AND is_llm_response = FALSE", (post_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Post not found or is already an LLM response'}), 404

    # For MVP, use default model/persona
    default_model = "llama3" # Use a likely valid default model
    default_persona = "helpful_assistant" # Placeholder

    try:
        cursor.execute("""
            INSERT INTO llm_requests (post_id_to_respond_to, status, llm_model, llm_persona)
            VALUES (?, 'pending', ?, ?)
        """, (post_id, default_model, default_persona))
        request_id = cursor.lastrowid
        db.commit()

        # Optionally, add to the in-memory queue if worker is active?
        # For simplicity now, worker will poll DB.
        # if processing_active.is_set():
        #     llm_request_queue.put({'request_id': request_id, 'post_id': post_id, 'model': default_model, 'persona': default_persona})

        print(f"Queued LLM request {request_id} for post {post_id}")
        return jsonify({'message': 'LLM response requested successfully', 'request_id': request_id}), 202 # Accepted
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Failed to queue LLM request: {e}'}), 500

@app.route('/api/schedule', methods=['GET', 'PUT'])
def handle_schedule():
    db = get_db()
    cursor = db.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        start_hour = data.get('start_hour')
        end_hour = data.get('end_hour')
        enabled = data.get('enabled')

        updates = []
        params = []
        if start_hour is not None and 0 <= int(start_hour) <= 23:
            updates.append("start_hour = ?")
            params.append(int(start_hour))
        if end_hour is not None and 0 <= int(end_hour) <= 23:
            updates.append("end_hour = ?")
            params.append(int(end_hour))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(bool(enabled))

        if not updates:
            return jsonify({'error': 'No valid schedule parameters provided'}), 400

        params.append(1) # schedule_id = 1
        sql = f"UPDATE schedule SET {', '.join(updates)} WHERE schedule_id = ?"
        try:
            cursor.execute(sql, tuple(params))
            db.commit()
            # Fetch updated schedule to return
            cursor.execute("SELECT start_hour, end_hour, enabled FROM schedule WHERE schedule_id = 1")
            updated_schedule = cursor.fetchone()
            return jsonify(dict(updated_schedule))
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Failed to update schedule: {e}'}), 500
    else: # GET
        cursor.execute("SELECT start_hour, end_hour, enabled FROM schedule WHERE schedule_id = 1")
        schedule = cursor.fetchone()
        if not schedule:
             # Should have been created by init_db, but handle defensively
             return jsonify({'error': 'Schedule not configured'}), 404
        return jsonify(dict(schedule))

@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
    """Fetches the list of locally available models from Ollama."""
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=10)
        response.raise_for_status()
        models_data = response.json()
        # Extract just the model names
        model_names = [model['name'] for model in models_data.get('models', [])]
        return jsonify(model_names)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Ollama models: {e}")
        # Return default model if Ollama is unreachable
        return jsonify({'error': f"Could not connect to Ollama to fetch models: {e}", 'models': [DEFAULT_MODEL]}), 503
    except Exception as e:
        print(f"Unexpected error fetching Ollama models: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/api/settings', methods=['GET', 'PUT'])
def handle_settings():
    """Gets or updates application settings."""
    db = get_db()
    cursor = db.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No settings data provided'}), 400

        try:
            for key, value in data.items():
                # Basic validation/sanitization could go here
                if key in ['darkMode', 'selectedModel']: # Only allow known keys
                     # Convert boolean strings for darkMode
                    if key == 'darkMode':
                        value = str(value).lower() # Store as string 'true' or 'false'
                    cursor.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, value))
            db.commit()
            # Fetch updated settings to return
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            return jsonify(settings)
        except Exception as e:
            db.rollback()
            print(f"Error updating settings: {e}")
            return jsonify({'error': f'Failed to update settings: {e}'}), 500
    else: # GET
        try:
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            # Ensure defaults if somehow missing
            if 'darkMode' not in settings: settings['darkMode'] = 'false'
            if 'selectedModel' not in settings: settings['selectedModel'] = DEFAULT_MODEL
            return jsonify(settings)
        except Exception as e:
            print(f"Error fetching settings: {e}")
            return jsonify({'error': f'Failed to fetch settings: {e}'}), 500


# --- Main Execution ---
if __name__ == '__main__':
    init_db() # Ensure DB exists and schema is created

    # Start the background LLM worker thread
    worker_thread = threading.Thread(target=llm_worker, daemon=True)
    worker_thread.start()

    print("Starting Flask server...")
    app.run(debug=True, host='0.0.0.0', port=5000) # Run on port 5000, accessible on network