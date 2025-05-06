import os
import sqlite3
import threading
import queue
import time
import datetime
import requests
import json # For settings
from flask import Flask, request, jsonify, render_template, g, send_from_directory
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

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

# --- Markdown Setup ---
# Custom highlight function using Pygments
def pygments_highlight(code, lang, attrs):
    try:
        # Use get_lexer_by_name if language is specified, otherwise TextLexer
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        # Fallback to TextLexer if the language is unknown
        lexer = TextLexer()
    # Use the default HTML formatter
    formatter = HtmlFormatter()
    # Return the highlighted code HTML
    return highlight(code, lexer, formatter)

# Configure markdown-it with the custom highlighter
md = (
    MarkdownIt(
        'commonmark',
        {
            'breaks': True,     # Convert '\n' in paragraphs into <br>
            'html': False,      # Disable HTML tags in source
            'linkify': True,    # Autoconvert URL-like text to links
            'highlight': pygments_highlight # Use our Pygments function HERE, inside options
        }
        # highlight=pygments_highlight # Use our Pygments function <-- REMOVED FROM HERE
    )
    .enable('table') # Enable GFM tables
    # Add other plugins or rules as needed
)


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
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('llmLinkSecurity', 'true')) # Added default
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
            cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('llmLinkSecurity', 'true')) # Added default
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
        # --- Actual Ollama call ---
        full_response_content = "" # Initialize before the try block for communication
        try:
            # Variables for streaming
            last_chunk_time = time.time()
            inter_chunk_timeout = 300 # Seconds between chunks before timeout
            initial_connection_timeout = 300 # Seconds for initial connection

            print(f"Sending streaming prompt to Ollama ({OLLAMA_GENERATE_URL}) for model '{model}'...")
            response = requests.post(
                OLLAMA_GENERATE_URL,
                json={'model': model, 'prompt': prompt_content, 'stream': True}, # Enable streaming
                headers={'Content-Type': 'application/json'},
                stream=True, # Required for iter_lines()
                timeout=initial_connection_timeout # Timeout for initial connection
            )
            response.raise_for_status() # Check for initial connection errors (4xx, 5xx)

            print(f"Connection established. Receiving stream for request {request_id}...")
            stream_done = False # Flag to track if 'done' was received
            for line in response.iter_lines():
                if line:
                    current_time = time.time()
                    # Check for inter-chunk timeout
                    if current_time - last_chunk_time > inter_chunk_timeout:
                        raise TimeoutError(f"Ollama response timed out after {inter_chunk_timeout} seconds of inactivity.")
                    last_chunk_time = current_time

                    try:
                        # Decode and parse the JSON chunk
                        chunk = json.loads(line.decode('utf-8'))
                        response_part = chunk.get('response', '')
                        full_response_content += response_part

                        # Optional: Log progress
                        # print(f"Received chunk for request {request_id}: {len(response_part)} chars")

                        if chunk.get('done', False):
                            print(f"Stream finished ('done': true) for request {request_id}.")
                            stream_done = True
                            break # Exit loop once Ollama signals completion
                    except json.JSONDecodeError:
                        print(f"Warning: Received non-JSON line from Ollama stream for request {request_id}: {line}")
                        # Decide if this is critical. For now, we just skip it.
                        continue

            # After the loop, check if the stream completed properly
            if not stream_done:
                 print(f"Warning: Ollama stream ended for request {request_id} without receiving 'done': true.")
                 # If no content was received at all, treat it as an error.
                 if not full_response_content:
                     raise ValueError("Ollama stream ended unexpectedly with no content and no 'done' flag.")
                 else:
                     print(f"Proceeding with content received ({len(full_response_content)} chars) despite missing 'done' flag.")

            print(f"Received complete response ({len(full_response_content)} chars) from Ollama for request {request_id}.")

            # --- If communication successful, save the response ---
            # 3. Save the LLM response to the posts table (using the accumulated content)
            cursor.execute("""
                INSERT INTO posts (topic_id, user_id, parent_post_id, content, is_llm_response, llm_model_id, llm_persona_id)
                SELECT topic_id, ?, ?, ?, TRUE, ?, ?
                FROM posts WHERE post_id = ?
            """, (CURRENT_USER_ID, post_id, full_response_content, model, persona, post_id))
            new_post_id = cursor.lastrowid
            print(f"Saved LLM response as post {new_post_id}")

            # 4. Update the status in llm_requests table to 'complete'
            cursor.execute("UPDATE llm_requests SET status = 'complete', processed_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
            db.commit()
            print(f"Request {request_id} marked as complete.")

        # --- Exception Handling for Ollama Communication (catches errors from the 'try' block above) ---
        except requests.exceptions.Timeout:
            # This catches the initial connection timeout
            print(f"Ollama API connection timed out after {initial_connection_timeout} seconds for request {request_id}.")
            # Re-raise as a generic Exception to be caught by the outer handler
            raise Exception(f"Failed to connect to Ollama API within {initial_connection_timeout} seconds.")
        except requests.exceptions.RequestException as req_err:
            # Catches other connection/request errors (DNS, refused connection, etc.)
            print(f"Ollama API request failed for request {request_id}: {req_err}")
            raise Exception(f"Failed to communicate with Ollama API: {req_err}") from req_err
        except TimeoutError as stream_timeout_err:
            # Catches the inter-chunk timeout
            print(f"Ollama streaming error for request {request_id}: {stream_timeout_err}")
            raise Exception(f"Ollama stream timed out: {stream_timeout_err}") from stream_timeout_err
        except json.JSONDecodeError as json_err:
             # Should ideally be caught within the loop, but catch here as a fallback
             print(f"Error decoding JSON from Ollama stream for request {request_id}: {json_err}")
             raise Exception(f"Invalid JSON received from Ollama stream: {json_err}") from json_err
        except ValueError as val_err:
             # Catch specific ValueErrors raised (e.g., stream ended with no content)
             print(f"Value error during Ollama processing for request {request_id}: {val_err}")
             raise Exception(f"Data error during Ollama processing: {val_err}") from val_err
        # Note: Other unexpected errors will be caught by the outer try...except block (starting line 250)
        # which handles updating the llm_requests status to 'error'.

        # --------------------------

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
        posts_raw = cursor.fetchall()

        processed_posts = []
        for row in posts_raw:
            post_dict = dict(row)
            # Render markdown content to HTML
            html_content = md.render(post_dict['content']) # Render raw markdown first

            # Add security class to links if it's an LLM response
            if post_dict.get('is_llm_response'): # Use .get for safety
                try:
                    # Use html.parser for robustness, less dependencies than lxml
                    soup = BeautifulSoup(html_content, 'html.parser')
                    links = soup.find_all('a')
                    if links: # Only proceed if links are found
                        link_modified = False
                        for link in links:
                            # Ensure 'class' attribute exists and is a list
                            current_classes = link.get('class', [])
                            if 'llm-link' not in current_classes:
                                link['class'] = current_classes + ['llm-link']
                                link_modified = True
                        # Only convert back to string if modifications were made
                        if link_modified:
                            html_content = str(soup)
                except Exception as e:
                    # Log error but don't crash; use the originally rendered HTML
                    print(f"Error parsing or modifying HTML for LLM post {post_dict.get('post_id', 'N/A')}: {e}")

            # Replace original content TEXT with processed HTML string
            post_dict['content'] = html_content
            processed_posts.append(post_dict)

        return jsonify(processed_posts)


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
                # Only process known keys to prevent injection
                if key in ['darkMode', 'selectedModel', 'llmLinkSecurity']:
                    processed_value = value # Default to original value
                    # Convert boolean-like values to string 'true' or 'false' for DB consistency
                    if key == 'darkMode' or key == 'llmLinkSecurity':
                        if isinstance(value, bool):
                            processed_value = 'true' if value else 'false'
                        else:
                            # Handle common string representations of boolean
                            bool_val = str(value).strip().lower() in ['true', '1', 'yes', 'on']
                            processed_value = 'true' if bool_val else 'false'
                    elif key == 'selectedModel':
                        # Basic validation: ensure it's a non-empty string?
                        # More robust validation would check against available models if feasible here.
                        processed_value = str(value).strip()
                        if not processed_value:
                             # Handle empty model selection if needed, maybe revert to default or raise error
                             print(f"Warning: Attempted to save empty string for selectedModel.")
                             continue # Skip saving this key if invalid

                    # Use the processed_value for the database operation
                    cursor.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, processed_value))
                else:
                    print(f"Warning: Ignoring unknown setting key during update: {key}")
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
            # Ensure defaults are present if missing from DB
            if 'darkMode' not in settings:
                settings['darkMode'] = 'false'
            if 'selectedModel' not in settings:
                settings['selectedModel'] = DEFAULT_MODEL
            if 'llmLinkSecurity' not in settings:
                settings['llmLinkSecurity'] = 'true' # Ensure default is added if missing
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