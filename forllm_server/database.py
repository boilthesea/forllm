import sqlite3
import datetime
import logging # ADDED
from flask import g, current_app # Added current_app for logger access
from .config import DATABASE, CURRENT_USER_ID, CURRENT_USERNAME, DEFAULT_MODEL

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
    return g.db

def close_db(error=None): # Added error=None to match Flask's teardown_appcontext signature
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
        # Add 'tagged_personas_in_content' to 'posts'
        cursor.execute("PRAGMA table_info(posts)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'tagged_personas_in_content' not in columns:
            print("Updating posts table: Adding 'tagged_personas_in_content' column...")
            try:
                cursor.execute("ALTER TABLE posts ADD COLUMN tagged_personas_in_content TEXT") # JSON array of persona IDs
                db.commit()
                print("'tagged_personas_in_content' column added to posts.")
            except Exception as e:
                print(f"Error adding 'tagged_personas_in_content' column to posts: {e}")
                db.rollback()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_persona_tags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                persona_id INTEGER,
                tagged_by_user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(post_id) REFERENCES posts(post_id),
                FOREIGN KEY(persona_id) REFERENCES personas(persona_id),
                FOREIGN KEY(tagged_by_user_id) REFERENCES users(user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id_to_respond_to INTEGER, -- Made nullable
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, complete, error
                llm_model TEXT,
                llm_persona TEXT,
                processed_at TIMESTAMP,
                error_message TEXT,
                full_prompt_sent TEXT, -- Ensuring this column is part of the main definition
                request_type TEXT,     -- New field
                request_params TEXT,   -- New field
                requested_by_user_id INTEGER, -- New field for tracking who triggered the LLM
                FOREIGN KEY (post_id_to_respond_to) REFERENCES posts(post_id),
                FOREIGN KEY (requested_by_user_id) REFERENCES users(user_id)
            )
        ''')
        # Add 'requested_by_user_id' to 'llm_requests' if it doesn't exist (for existing databases)
        cursor.execute("PRAGMA table_info(llm_requests)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'requested_by_user_id' not in columns:
            print("Updating llm_requests table: Adding 'requested_by_user_id' column...")
            try:
                cursor.execute("ALTER TABLE llm_requests ADD COLUMN requested_by_user_id INTEGER REFERENCES users(user_id)")
                db.commit()
                print("'requested_by_user_id' column added to llm_requests.")
            except Exception as e:
                print(f"Error adding 'requested_by_user_id' column to llm_requests: {e}")
                db.rollback()

        # Add 'prompt_token_breakdown' to 'llm_requests' if it doesn't exist
        cursor.execute("PRAGMA table_info(llm_requests)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'prompt_token_breakdown' not in columns:
            print("Updating llm_requests table: Adding 'prompt_token_breakdown' column...")
            try:
                cursor.execute("ALTER TABLE llm_requests ADD COLUMN prompt_token_breakdown TEXT")
                db.commit()
                print("'prompt_token_breakdown' column added to llm_requests.")
            except Exception as e:
                print(f"Error adding 'prompt_token_breakdown' column to llm_requests: {e}")
                db.rollback()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attachments (
                attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                user_prompt TEXT,
                order_in_post INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
                UNIQUE (post_id, order_in_post)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                last_viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_type, item_id)
            )
        ''')

        # Check and add 'full_prompt_sent' to 'llm_requests'
        cursor.execute("PRAGMA table_info(llm_requests)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'full_prompt_sent' not in columns:
            print("Updating llm_requests table: Adding 'full_prompt_sent' column...")
            try:
                # Ensure this alter statement is applied to the correct 'db' connection cursor
                cursor.execute("ALTER TABLE llm_requests ADD COLUMN full_prompt_sent TEXT")
                db.commit() # Commit this specific change
                print("'full_prompt_sent' column added to llm_requests.")
            except Exception as e:
                print(f"Error adding 'full_prompt_sent' column to llm_requests: {e}")
                db.rollback() # Rollback if alter fails

        cursor.execute('''
             CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_hour INTEGER NOT NULL, -- 0-23
                end_hour INTEGER NOT NULL,   -- 0-23
                days_active TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun', -- Comma-separated e.g., "Mon,Wed,Fri"
                enabled BOOLEAN NOT NULL DEFAULT TRUE
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
        # Insert default settings if not present
        # Removed: cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('darkMode', 'false'))
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('selectedModel', DEFAULT_MODEL))
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('llmLinkSecurity', 'true')) # Added default
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('default_llm_context_window', '4096')) # Added default
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
            # Removed: cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('darkMode', 'false'))
            cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('selectedModel', DEFAULT_MODEL))
            cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('llmLinkSecurity', 'true')) # Added default
            print("Settings table created with defaults.")
            db.commit() # Commit after creating settings table
        else:
            print("Database found and settings table exists.") # Simplified message

        # --- Check/Update schedule table if DB already exists ---
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule'")
        schedule_table_exists = cursor.fetchone()
        if schedule_table_exists:
            # Check if 'days_active' column exists
            cursor.execute("PRAGMA table_info(schedule)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'days_active' not in columns:
                print("Updating schedule table: Adding 'days_active' column...")
                try:
                    cursor.execute("ALTER TABLE schedule ADD COLUMN days_active TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'")
                    print("'days_active' column added.")
                    db.commit()
                except Exception as e:
                    print(f"Error adding 'days_active' column: {e}")
                    db.rollback()
            # Check if 'id' column exists and 'schedule_id' doesn't (simple check for new schema)
            if 'id' not in columns and 'schedule_id' in columns:
                 print("Updating schedule table: Migrating from single schedule_id to multiple schedule rows...")
                 try:
                    # 1. Rename old table
                    cursor.execute("ALTER TABLE schedule RENAME TO schedule_old")
                    # 2. Create new table
                    cursor.execute('''
                        CREATE TABLE schedule (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            start_hour INTEGER NOT NULL,
                            end_hour INTEGER NOT NULL,
                            days_active TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun',
                            enabled BOOLEAN NOT NULL DEFAULT TRUE
                        )
                    ''')
                    # 3. Copy data (if any exists in old table)
                    cursor.execute("SELECT start_hour, end_hour, enabled FROM schedule_old LIMIT 1")
                    old_data = cursor.fetchone()
                    if old_data:
                        cursor.execute("""
                            INSERT INTO schedule (start_hour, end_hour, enabled, days_active)
                            VALUES (?, ?, ?, 'Mon,Tue,Wed,Thu,Fri,Sat,Sun')
                        """, (old_data[0], old_data[1], old_data[2]))
                    # 4. Drop old table
                    cursor.execute("DROP TABLE schedule_old")
                    print("Schedule table migrated to new schema.")
                    db.commit()
                 except Exception as e:
                    print(f"Error migrating schedule table: {e}")
                    db.rollback()
            elif 'id' not in columns and 'schedule_id' not in columns:
                 # If neither exists, something is wrong, recreate the table
                 print("Schedule table schema incorrect. Recreating...")
                 cursor.execute("DROP TABLE IF EXISTS schedule")
                 cursor.execute('''
                    CREATE TABLE schedule (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_hour INTEGER NOT NULL,
                        end_hour INTEGER NOT NULL,
                        days_active TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun',
                        enabled BOOLEAN NOT NULL DEFAULT TRUE
                    )
                 ''')
                 db.commit()
        else:
            # Schedule table doesn't exist, create it
            print("Schedule table missing. Creating schedule table...")
            cursor.execute('''
                 CREATE TABLE schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_hour INTEGER NOT NULL,
                    end_hour INTEGER NOT NULL,
                    days_active TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE
                )
            ''')
            db.commit()

        # --- Persona Management Tables (NEW) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personas (
                persona_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                prompt_instructions TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_user INTEGER,
                version INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                generation_source TEXT,                 -- New field
                generation_input_details TEXT,          -- New field
                FOREIGN KEY (created_by_user) REFERENCES users(user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS persona_versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                prompt_instructions TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_user INTEGER,
                version INTEGER NOT NULL,
                FOREIGN KEY (persona_id) REFERENCES personas(persona_id),
                FOREIGN KEY (updated_by_user) REFERENCES users(user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subforum_personas (
                subforum_persona_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subforum_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_default_for_subforum BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (subforum_id) REFERENCES subforums(subforum_id),
                FOREIGN KEY (persona_id) REFERENCES personas(persona_id)
            )
        ''')
        # Add indexes for fast persona lookup and assignment
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subforum_personas_subforum ON subforum_personas(subforum_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subforum_personas_persona ON subforum_personas(persona_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_personas_active ON personas(is_active)')
        # Add global default persona to settings if not present
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('globalDefaultPersonaId', '1'))
        # Add built-in fallback persona if not present (editable)
        cursor.execute("INSERT OR IGNORE INTO personas (persona_id, name, prompt_instructions, created_by_user, is_active) VALUES (?, ?, ?, ?, ?)", (1, 'fallback', 'You are a helpful assistant.', CURRENT_USER_ID, True))
        db.commit()

        # Ensure all default settings are present if the settings table already existed
        # This is a good place to add new settings with defaults if they are introduced later
        default_settings_to_check = {
            # Removed: 'darkMode': 'false',
            'selectedModel': DEFAULT_MODEL,
            'llmLinkSecurity': 'true',
            'default_llm_context_window': '4096' # Added this line
            # globalDefaultPersonaId is handled below
        }
        for key, default_value in default_settings_to_check.items():
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = ?", (key,))
            if cursor.fetchone() is None:
                print(f"Setting '{key}' missing. Adding with default value '{default_value}'.")
                cursor.execute("INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, default_value))
                db.commit() # Commit each missing setting individually

    # --- Persona Management Tables (Ensure these always exist and have defaults) ---
    # This section is now outside the initial if/else, so it runs every time.

    # --- Check and add 'tagged_personas_in_content' to 'posts' if DB already exists ---
    # This ensures the column is added if the table was created in a previous version
    # without this column.
    cursor.execute("PRAGMA table_info(posts)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'tagged_personas_in_content' not in columns:
        print("Updating posts table (post-initial check): Adding 'tagged_personas_in_content' column...")
        try:
            cursor.execute("ALTER TABLE posts ADD COLUMN tagged_personas_in_content TEXT") # JSON array of persona IDs
            db.commit()
            print("'tagged_personas_in_content' column added to posts (post-initial check).")
        except Exception as e:
            print(f"Error adding 'tagged_personas_in_content' column to posts (post-initial check): {e}")
            db.rollback()

    # --- Check and add 'requested_by_user_id' to 'llm_requests' if DB already exists ---
    cursor.execute("PRAGMA table_info(llm_requests)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'requested_by_user_id' not in columns:
        print("Updating llm_requests table (post-initial check): Adding 'requested_by_user_id' column...")
        try:
            cursor.execute("ALTER TABLE llm_requests ADD COLUMN requested_by_user_id INTEGER REFERENCES users(user_id)")
            db.commit()
            print("'requested_by_user_id' column added to llm_requests (post-initial check).")
        except Exception as e:
            print(f"Error adding 'requested_by_user_id' column to llm_requests (post-initial check): {e}")
            db.rollback()

    # --- Check and add 'prompt_token_breakdown' to 'llm_requests' if DB already exists ---
    cursor.execute("PRAGMA table_info(llm_requests)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'prompt_token_breakdown' not in columns:
        print("Updating llm_requests table (post-initial check): Adding 'prompt_token_breakdown' column...")
        try:
            cursor.execute("ALTER TABLE llm_requests ADD COLUMN prompt_token_breakdown TEXT")
            db.commit()
            print("'prompt_token_breakdown' column added to llm_requests (post-initial check).")
        except Exception as e:
            print(f"Error adding 'prompt_token_breakdown' column to llm_requests (post-initial check): {e}")
            db.rollback()

    print("Verifying/Creating Persona management tables and defaults...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS personas (
            persona_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            prompt_instructions TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by_user INTEGER,
            version INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            generation_source TEXT,                 -- New field
            generation_input_details TEXT,          -- New field
            FOREIGN KEY (created_by_user) REFERENCES users(user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS persona_versions (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            prompt_instructions TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by_user INTEGER,
            version INTEGER NOT NULL,
            FOREIGN KEY (persona_id) REFERENCES personas(persona_id),
            FOREIGN KEY (updated_by_user) REFERENCES users(user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subforum_personas (
            subforum_persona_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subforum_id INTEGER NOT NULL,
            persona_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_default_for_subforum BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (subforum_id) REFERENCES subforums(subforum_id),
            FOREIGN KEY (persona_id) REFERENCES personas(persona_id)
        )
    ''')
    # Add indexes for fast persona lookup and assignment
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subforum_personas_subforum ON subforum_personas(subforum_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subforum_personas_persona ON subforum_personas(persona_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_personas_active ON personas(is_active)')

    # Ensure settings table exists before trying to insert globalDefaultPersonaId (it should by this point)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
    if cursor.fetchone():
        # Add global default persona ID to settings if not present
        cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)", ('globalDefaultPersonaId', '1'))
    else:
        # This case should ideally not be reached if the preceding logic is correct.
        print("CRITICAL ERROR: Settings table does not exist when attempting to set globalDefaultPersonaId.")


    # Add built-in fallback persona (ID 1) if not present.
    cursor.execute("INSERT OR IGNORE INTO personas (persona_id, name, prompt_instructions, created_by_user, is_active) VALUES (?, ?, ?, ?, ?)",
                   (1, 'fallback', 'You are a helpful assistant.', CURRENT_USER_ID, True))
    # Also ensure its version 1 is in persona_versions (if persona_versions table is used for this)
    # Assuming the fallback persona (ID 1) should also have a corresponding version 1 entry.
    # If the persona was just inserted by IGNORE, this will also be ignored if it exists.
    # If the persona already existed, this ensures its version 1 is also there.
    cursor.execute("INSERT OR IGNORE INTO persona_versions (persona_id, version, name, prompt_instructions, updated_by_user) VALUES (?, ?, ?, ?, ?)",
                   (1, 1, 'fallback', 'You are a helpful assistant.', CURRENT_USER_ID))
    
    # --- Create post_persona_tags table (ensure it always exists) ---
    # This is outside the initial if/else, so it runs every time.
    print("Verifying/Creating post_persona_tags table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_persona_tags (
            tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            persona_id INTEGER,
            tagged_by_user_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(post_id) REFERENCES posts(post_id),
            FOREIGN KEY(persona_id) REFERENCES personas(persona_id),
            FOREIGN KEY(tagged_by_user_id) REFERENCES users(user_id)
        )
    ''')
    # Add indexes for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_persona_tags_post ON post_persona_tags(post_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_persona_tags_persona ON post_persona_tags(persona_id)')

    db.commit() # Commit after ensuring all persona tables, indexes, default data, and post_persona_tags table.
    print("Persona management tables, defaults, and post_persona_tags table verified/created.")

    # One-time cleanup of old darkMode setting
    try:
        cursor.execute("DELETE FROM settings WHERE setting_key = ?", ('darkMode',))
        db.commit() # Commit this deletion
        print("Cleaned up 'darkMode' setting from database if it existed.")
    except sqlite3.Error as e:
        print(f"Error during darkMode cleanup: {e}")
        # Potentially rollback if this commit is part of a larger transaction,
        # but since it's a cleanup at the end, a separate commit is fine.
        # db.rollback() # Only if part of a transaction that should be reverted entirely

    print("Database initialization complete.")

    # --- Create llm_model_metadata table (NEW) ---
    # This section is outside the initial if/else, so it runs every time to ensure table existence.
    print("Verifying/Creating llm_model_metadata table...")
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_model_metadata (
                model_name TEXT PRIMARY KEY,
                context_window INTEGER,
                last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.commit()
        print("llm_model_metadata table verified/created.")
    except sqlite3.Error as e:
        print(f"Error creating/verifying llm_model_metadata table: {e}")
        # No rollback needed here usually for CREATE IF NOT EXISTS, but good practice if part of larger transaction block
        # db.rollback()

    db.close()

# --- LLM Model Metadata Cache Logic ---

def get_cached_model_context_window(db, model_name: str) -> int | None:
    """
    Retrieves the cached context window size for a given model.
    Args:
        db: Database connection object.
        model_name: The name of the model.
    Returns:
        A tuple (bool, int | None) indicating (found_in_cache, value).
        Value is the context window size (int) or None if explicitly cached as not found/error.
    """
    logger = current_app.logger if current_app and hasattr(current_app, 'logger') else logging.getLogger(__name__)
    try:
        cursor = db.execute("SELECT context_window FROM llm_model_metadata WHERE model_name = ?", (model_name,))
        row = cursor.fetchone()
        if row:  # A row was found, meaning it's in the cache
            # The stored context_window can itself be NULL if we cached a "not found" state
            logger.info(f"Cache hit for {model_name}. Raw DB Value: {row['context_window']}")
            # Ensure conversion to int if it's not None, otherwise pass None as is.
            # This was previously handled by `if row and row[0] is not None: return int(row[0])`
            # Now, we return the raw value (which can be int or None) from the DB.
            db_value = row['context_window']
            # It's assumed the database stores INTEGER NULL, which sqlite3.Row correctly maps to Python's None.
            # If it's a non-None value, it should already be an int due to column type,
            # but explicit conversion here is safer if schema affinity is weird.
            # However, direct return is fine if schema is `context_window INTEGER`.
            return True, db_value # db_value can be int or None
        else:  # No row found, cache miss
            logger.info(f"Cache miss for {model_name}.")
            return False, None
    except sqlite3.Error as e:
        logger.error(f"Database error in get_cached_model_context_window for {model_name}: {e}")
        return False, None
    # ValueError should not occur here if db stores int/None correctly.
    # If it did, it would be from trying to int(None) or int("non-int-string"),
    # but we are now returning the direct DB value.


def cache_model_context_window(db, model_name: str, context_window: int | None):
    """
    Caches the context window size for a given model.
    The context_window can be None to indicate it's not found or an error occurred.
    Updates the last_checked timestamp automatically.
    Args:
        db: Database connection object.
        model_name: The name of the model.
        context_window: The context window size (int) or None to cache a "not found" state.
    """
    logger = current_app.logger if current_app and hasattr(current_app, 'logger') else logging.getLogger(__name__)
    if model_name is None: # context_window being None is now allowed
        logger.warning(f"Attempted to cache with None model_name.")
        return
    try:
        db.execute("""
            INSERT INTO llm_model_metadata (model_name, context_window, last_checked)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_name) DO UPDATE SET
                context_window = excluded.context_window,
                last_checked = CURRENT_TIMESTAMP;
        """, (model_name, context_window)) # context_window can be None here, SQLite handles it
        db.commit()
        logger.info(f"Cached context window for {model_name}: {context_window if context_window is not None else 'Not Found (None)'}")
    except sqlite3.Error as e:
        logger.error(f"Database error in cache_model_context_window for {model_name}: {e}")

# ------------------- PERSONA MANAGEMENT LOGIC -------------------

def create_persona(name, prompt_instructions, created_by_user):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT INTO personas (name, prompt_instructions, created_by_user, is_active)
            VALUES (?, ?, ?, 1)
        ''', (name, prompt_instructions, created_by_user))
        persona_id = cursor.lastrowid
        # Save initial version
        cursor.execute('''
            INSERT INTO persona_versions (persona_id, name, prompt_instructions, updated_by_user, version)
            VALUES (?, ?, ?, ?, 1)
        ''', (persona_id, name, prompt_instructions, created_by_user))
        db.commit()
        return persona_id
    except sqlite3.Error as e:
        print(f"Database error in create_persona: {e}")
        if db:
            db.rollback()
        return None

# ------------------- USER ACTIVITY LOGIC -------------------

def update_user_activity(user_id, item_type, item_id):
    """
    Inserts or replaces a user activity entry, updating the last_viewed_at timestamp.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO user_activity (user_id, item_type, item_id, last_viewed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, item_type, item_id))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error in update_user_activity: {e}")
        if db:
            db.rollback()
        return False

def get_last_viewed_timestamp(user_id, item_type, item_id):
    """
    Retrieves the last_viewed_at timestamp for a given user and item.
    Returns None if no entry is found.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            SELECT last_viewed_at FROM user_activity
            WHERE user_id = ? AND item_type = ? AND item_id = ?
        ''', (user_id, item_type, item_id))
        row = cursor.fetchone()
        if row:
            return row['last_viewed_at']
        return None
    except sqlite3.Error as e:
        print(f"Database error in get_last_viewed_timestamp: {e}")
        return None

def check_topic_unseen_status(topic_id, user_id, last_viewed_subforum_ts=None):
    """
    Checks if a topic has unseen posts or is itself new relative to subforum view.
    Returns True if unseen, False otherwise.
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Get topic creation time
        cursor.execute("SELECT created_at FROM topics WHERE topic_id = ?", (topic_id,))
        topic_row = cursor.fetchone()
        if not topic_row:
            return False # Topic not found

        # Timestamps are stored as strings, convert to datetime objects
        # SQLite's CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS'
        # Timestamps are stored as strings, convert to datetime objects
        # SQLite's CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS'
        # With detect_types=sqlite3.PARSE_DECLTYPES, it should already be a datetime object
        topic_created_at = topic_row['created_at']

        last_viewed_topic_ts_raw = get_last_viewed_timestamp(user_id, 'topic', topic_id)
        
        # Ensure last_viewed_topic_ts is a datetime object for comparison
        if last_viewed_topic_ts_raw:
            if isinstance(last_viewed_topic_ts_raw, str):
                 last_viewed_topic_ts = datetime.datetime.strptime(last_viewed_topic_ts_raw, '%Y-%m-%d %H:%M:%S')
            elif isinstance(last_viewed_topic_ts_raw, datetime.datetime):
                 last_viewed_topic_ts = last_viewed_topic_ts_raw
            else: # Fallback for unexpected types, treat as very old
                 last_viewed_topic_ts = datetime.datetime.fromtimestamp(0)
        else:
            last_viewed_topic_ts = datetime.datetime.fromtimestamp(0)

        # Ensure last_viewed_subforum_ts is a datetime object if provided
        if last_viewed_subforum_ts:
            if isinstance(last_viewed_subforum_ts, str):
                last_viewed_subforum_ts_dt = datetime.datetime.strptime(last_viewed_subforum_ts, '%Y-%m-%d %H:%M:%S')
            elif isinstance(last_viewed_subforum_ts, datetime.datetime):
                last_viewed_subforum_ts_dt = last_viewed_subforum_ts
            else: # Fallback for unexpected types
                last_viewed_subforum_ts_dt = datetime.datetime.fromtimestamp(0) # Or handle error

            if topic_created_at > last_viewed_subforum_ts_dt:
                return True # Topic is new since subforum was last viewed

        # Check for new posts (replies) in this topic since the topic was last viewed
        # We only care about replies, so parent_post_id IS NOT NULL.
        # However, the prompt for check_topic_unseen_status says "any post P ... has P.created_at > last_viewed_topic_ts"
        # This could include the initial post if the topic itself was never "viewed" (no entry in user_activity).
        # If a topic is created, and user_activity for this topic is None (epoch 0), then topic.created_at > epoch 0,
        # it implies the first post is also unseen.
        # Let's check any post. If the first post makes it true, and the topic itself wasn't marked "new" by subforum view, then it's still unseen.
        # Correction: Requirement is to check for REPLIES only.
        cursor.execute("""
            SELECT 1 FROM posts
            WHERE topic_id = ? AND parent_post_id IS NOT NULL AND created_at > ?
            LIMIT 1
        """, (topic_id, last_viewed_topic_ts.strftime('%Y-%m-%d %H:%M:%S')))
        if cursor.fetchone():
            return True

        return False
    except sqlite3.Error as e:
        print(f"Database error in check_topic_unseen_status for topic {topic_id}, user {user_id}: {e}")
        return False # Default to not unseen in case of error
    except ValueError as e:
        print(f"Timestamp format error in check_topic_unseen_status for topic {topic_id}, user {user_id}: {e}")
        return False


def check_subforum_unseen_status(subforum_id, user_id):
    """
    Checks if a subforum has unseen topics or posts within its topics.
    Returns True if unseen, False otherwise.
    """
    db = get_db()
    cursor = db.cursor()

    try:
        last_viewed_subforum_ts_raw = get_last_viewed_timestamp(user_id, 'subforum', subforum_id)
        
        if last_viewed_subforum_ts_raw:
            if isinstance(last_viewed_subforum_ts_raw, str):
                last_viewed_subforum_ts = datetime.datetime.strptime(last_viewed_subforum_ts_raw, '%Y-%m-%d %H:%M:%S')
            elif isinstance(last_viewed_subforum_ts_raw, datetime.datetime):
                last_viewed_subforum_ts = last_viewed_subforum_ts_raw
            else: # Fallback for unexpected types
                last_viewed_subforum_ts = datetime.datetime.fromtimestamp(0)
        else:
            last_viewed_subforum_ts = datetime.datetime.fromtimestamp(0)

        # Fetch all topics in this subforum
        cursor.execute("SELECT topic_id, created_at FROM topics WHERE subforum_id = ?", (subforum_id,))
        topics = cursor.fetchall()

        for topic_row in topics:
            topic_id = topic_row['topic_id']
            # Convert topic_created_at from string to datetime for comparison
            # Convert topic_created_at from string to datetime for comparison
            # With detect_types=sqlite3.PARSE_DECLTYPES, it should already be a datetime object
            topic_created_at = topic_row['created_at']

            if topic_created_at > last_viewed_subforum_ts:
                return True # New topic since subforum was last viewed

            # Check individual topic status (for new posts within that topic)
            # We don't pass last_viewed_subforum_ts here, as per interpretation of requirements.
            # check_topic_unseen_status will use the topic's own last_viewed_ts.
            if check_topic_unseen_status(topic_id, user_id): # Pass None or omit last_viewed_subforum_ts
                return True
        
        return False
    except sqlite3.Error as e:
        print(f"Database error in check_subforum_unseen_status for subforum {subforum_id}, user {user_id}: {e}")
        return False # Default to not unseen
    except ValueError as e:
        print(f"Timestamp format error in check_subforum_unseen_status for subforum {subforum_id}, user {user_id}: {e}")
        return False

def get_subforums_with_status(user_id):
    """
    Fetches all subforums and includes an 'has_unseen_content' status for each.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT subforum_id, name FROM subforums ORDER BY name")
        subforums_raw = cursor.fetchall()
        subforums_with_status = []
        for row in subforums_raw:
            subforum_dict = dict(row)
            subforum_dict['has_unseen_content'] = check_subforum_unseen_status(subforum_dict['subforum_id'], user_id)
            subforums_with_status.append(subforum_dict)
        return subforums_with_status
    except sqlite3.Error as e:
        print(f"Database error in get_subforums_with_status for user {user_id}: {e}")
        return [] # Return empty list on error

def get_topics_for_subforum_with_status(subforum_id, user_id):
    """
    Fetches all topics for a subforum and includes 'has_unseen_content' status for each.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        # Get the last time user viewed the subforum, to pass to check_topic_unseen_status
        last_viewed_subforum_ts_raw = get_last_viewed_timestamp(user_id, 'subforum', subforum_id)
        
        if last_viewed_subforum_ts_raw:
            if isinstance(last_viewed_subforum_ts_raw, str):
                last_viewed_subforum_ts = datetime.datetime.strptime(last_viewed_subforum_ts_raw, '%Y-%m-%d %H:%M:%S')
            elif isinstance(last_viewed_subforum_ts_raw, datetime.datetime): # if it's already datetime
                last_viewed_subforum_ts = last_viewed_subforum_ts_raw
            else: # fallback for unexpected types
                last_viewed_subforum_ts = datetime.datetime.fromtimestamp(0)
        else:
            last_viewed_subforum_ts = datetime.datetime.fromtimestamp(0)

        # Fetch topics (similar to handle_topics in forum_routes.py)
        # Adding more fields that are typically useful for topic lists
        cursor.execute("""
            SELECT t.topic_id, t.title, t.created_at, u.username as author_username,
                   (SELECT COUNT(*) FROM posts p WHERE p.topic_id = t.topic_id) as post_count,
                   (SELECT MAX(p.created_at) FROM posts p WHERE p.topic_id = t.topic_id) as last_post_at
            FROM topics t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.subforum_id = ?
            ORDER BY last_post_at DESC
        """, (subforum_id,))
        topics_raw = cursor.fetchall()
        
        topics_with_status = []
        for row in topics_raw:
            topic_dict = dict(row)
            # The requirement was 'has_unseen_replies' but my function is 'check_topic_unseen_status'
            # which covers new topics AND new replies. 'has_unseen_content' seems more fitting.
            topic_dict['has_unseen_content'] = check_topic_unseen_status(
                topic_dict['topic_id'], 
                user_id, 
                last_viewed_subforum_ts # Pass the subforum view timestamp here
            )
            topics_with_status.append(topic_dict)
        return topics_with_status
    except sqlite3.Error as e:
        print(f"Database error in get_topics_for_subforum_with_status for subforum {subforum_id}, user {user_id}: {e}")
        return []
    except ValueError as e: # Catch potential strptime errors if raw ts is malformed
        print(f"Timestamp format error in get_topics_for_subforum_with_status for subforum {subforum_id}, user {user_id}: {e}")
        return []

# ------------------- RECENT ACTIVITY PAGE LOGIC -------------------

def get_recent_topics(user_id, limit=10):
    """
    Fetches recent topics that are considered new to the user.
    A topic is new if its created_at is after the user's last_viewed_at for its parent subforum.
    Additionally, it filters out topics the user has explicitly viewed, unless new posts exist in that topic
    (this part is simplified here to: topic's own last_viewed_at is before topic.created_at, which means it was never truly "viewed" if it shows up).
    """
    db = get_db()
    cursor = db.cursor()
    try:
        # This query aims to find topics in subforums that are new since the subforum was last viewed,
        # or topics in subforums that were never viewed.
        # It also considers if the topic itself has been viewed.
        # A topic is considered "new" if:
        # 1. It was created after the subforum was last viewed by the user.
        #    (If subforum never viewed, all its topics are candidates here).
        # 2. The topic itself has either never been viewed by the user, or if it has,
        #    this specific query doesn't check for newer posts within it but relies on the topic's creation date
        #    vs its own last view date.
        #    A more sophisticated check (like check_topic_unseen_status) is not used here to keep it focused on "recent topics".
        
        # Using datetime.datetime.fromtimestamp(0).strftime('%Y-%m-%d %H:%M:%S') for epoch
        epoch_ts_str = datetime.datetime.fromtimestamp(0).strftime('%Y-%m-%d %H:%M:%S')

        query = """
            SELECT
                t.topic_id, t.title, t.created_at AS topic_created_at,
                s.subforum_id, s.name AS subforum_name
            FROM topics t
            JOIN subforums s ON t.subforum_id = s.subforum_id
            LEFT JOIN user_activity ua_subforum ON ua_subforum.item_type = 'subforum'
                AND ua_subforum.item_id = s.subforum_id AND ua_subforum.user_id = :user_id
            LEFT JOIN user_activity ua_topic ON ua_topic.item_type = 'topic'
                AND ua_topic.item_id = t.topic_id AND ua_topic.user_id = :user_id
            WHERE
                t.created_at > COALESCE(ua_subforum.last_viewed_at, :epoch_ts)
            AND
                (ua_topic.last_viewed_at IS NULL OR t.created_at > ua_topic.last_viewed_at)
            ORDER BY t.created_at DESC
            LIMIT :limit
        """
        # The condition `t.created_at > ua_topic.last_viewed_at` for an already viewed topic implies
        # that the topic was viewed *before* it was created, which is impossible.
        # This effectively means "if topic was viewed, it's not new by creation date alone".
        # A better condition for "new activity in an already viewed topic" would be to check posts.
        # However, the prompt focuses on "topics that are new".
        # If a topic is created at T1, subforum viewed at T0 (T0 < T1), topic viewed at T2 (T1 < T2).
        # If then a new post P1 is made at T3 (T2 < T3).
        # The current query would filter out this topic if T2 exists.
        # Re-evaluating: "only return topics that are 'new' to the user. A topic is new if its created_at is after user_activity.last_viewed_at for its parent subforum"
        # "Alternatively, or additionally, filter out topics the user has already explicitly viewed"
        # This means if ua_topic.last_viewed_at exists, it should NOT be shown.
        
        # Simpler interpretation: Show topics created after subforum view, UNLESS topic itself has been viewed.
        query_revised = """
            SELECT
                t.topic_id, t.title, t.created_at AS topic_created_at,
                s.subforum_id, s.name AS subforum_name
            FROM topics t
            JOIN subforums s ON t.subforum_id = s.subforum_id
            LEFT JOIN user_activity ua_subforum ON ua_subforum.item_type = 'subforum'
                AND ua_subforum.item_id = s.subforum_id AND ua_subforum.user_id = :user_id
            LEFT JOIN user_activity ua_topic ON ua_topic.item_type = 'topic'
                AND ua_topic.item_id = t.topic_id AND ua_topic.user_id = :user_id
            WHERE
                t.created_at > COALESCE(ua_subforum.last_viewed_at, :epoch_ts)
            AND
                ua_topic.last_viewed_at IS NULL  -- Only include topics that have no 'topic' view record for the user
            ORDER BY t.created_at DESC
            LIMIT :limit
        """

        cursor.execute(query_revised, {"user_id": user_id, "epoch_ts": epoch_ts_str, "limit": limit})
        recent_topics = [dict(row) for row in cursor.fetchall()]
        return recent_topics
    except sqlite3.Error as e:
        print(f"Database error in get_recent_topics for user {user_id}: {e}")
        return []

def get_recent_replies(user_id, limit=10):
    """
    Fetches recent replies (posts) that are new to the user.
    A reply is new if its created_at is after the user's last_viewed_at for its parent topic.
    """
    db = get_db()
    cursor = db.cursor()
    epoch_ts_str = datetime.datetime.fromtimestamp(0).strftime('%Y-%m-%d %H:%M:%S')
    try:
        query = """
            SELECT
                p.post_id, 
                SUBSTR(p.content, 1, 100) AS content_snippet, 
                p.created_at AS reply_created_at,
                t.topic_id, t.title AS topic_title,
                s.subforum_id, s.name AS subforum_name
            FROM posts p
            JOIN topics t ON p.topic_id = t.topic_id
            JOIN subforums s ON t.subforum_id = s.subforum_id
            LEFT JOIN user_activity ua_topic ON ua_topic.item_type = 'topic'
                AND ua_topic.item_id = t.topic_id AND ua_topic.user_id = :user_id
            WHERE 
                p.parent_post_id IS NOT NULL  -- Ensure it's a reply
            AND 
                p.created_at > COALESCE(ua_topic.last_viewed_at, :epoch_ts)
            ORDER BY p.created_at DESC
            LIMIT :limit
        """
        cursor.execute(query, {"user_id": user_id, "epoch_ts": epoch_ts_str, "limit": limit})
        recent_replies = [dict(row) for row in cursor.fetchall()]
        return recent_replies
    except sqlite3.Error as e:
        print(f"Database error in get_recent_replies for user {user_id}: {e}")
        return []

def get_recent_personas(limit=10):
    """
    Fetches the most recently created active personas.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        query = """
            SELECT persona_id, name, created_at
            FROM personas
            WHERE is_active = 1
            ORDER BY created_at DESC
            LIMIT :limit
        """
        cursor.execute(query, {"limit": limit})
        recent_personas = [dict(row) for row in cursor.fetchall()]
        return recent_personas
    except sqlite3.Error as e:
        print(f"Database error in get_recent_personas: {e}")
        return []

def get_subforum_details(subforum_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT name, description FROM subforums WHERE subforum_id = ?", (subforum_id,))
        row = cursor.fetchone()
        if row:
            return {"name": row["name"], "description": row["description"]}
        return None
    except sqlite3.Error as e:
        print(f"Database error in get_subforum_details for subforum_id {subforum_id}: {e}")
        return None

def get_persona(persona_id, active_only=True):
    try:
        db = get_db()
        cursor = db.cursor()
        q = 'SELECT * FROM personas WHERE persona_id = ?'
        if active_only:
            q += ' AND is_active = 1'
        cursor.execute(q, (persona_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Database error in get_persona: {e}")
        return None

def list_personas(active_only=True):
    try:
        db = get_db()
        cursor = db.cursor()
        q = 'SELECT * FROM personas'
        if active_only:
            q += ' WHERE is_active = 1'
        cursor.execute(q)
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error in list_personas: {e}")
        return None # Return None, route handler will check

def update_persona(persona_id, name, prompt_instructions, updated_by_user):
    db = get_db()
    cursor = db.cursor()
    try:
        # Get current version
        cursor.execute('SELECT version FROM personas WHERE persona_id = ?', (persona_id,))
        row = cursor.fetchone()
        if not row:
            # No need to rollback as no changes were made yet if persona not found
            return False 
        new_version = row['version'] + 1
        cursor.execute('''
            UPDATE personas SET name = ?, prompt_instructions = ?, updated_at = CURRENT_TIMESTAMP, version = ?
            WHERE persona_id = ?
        ''', (name, prompt_instructions, new_version, persona_id))
        # Save version
        cursor.execute('''
            INSERT INTO persona_versions (persona_id, name, prompt_instructions, updated_by_user, version)
            VALUES (?, ?, ?, ?, ?)
        ''', (persona_id, name, prompt_instructions, updated_by_user, new_version))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error in update_persona: {e}")
        if db:
            db.rollback()
        return False

def soft_delete_persona(persona_id):
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute('UPDATE personas SET is_active = 0 WHERE persona_id = ?', (persona_id,))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error in soft_delete_persona: {e}")
        if db: # Check if db object exists before rollback
            db.rollback()
        return False

def revert_persona_to_version(persona_id, version, updated_by_user):
    db = get_db() # Get DB connection for potential rollback
    try:
        cursor = db.cursor() # Use the same cursor throughout
        cursor.execute('''
            SELECT name, prompt_instructions FROM persona_versions
            WHERE persona_id = ? AND version = ?
        ''', (persona_id, version))
        row = cursor.fetchone()
        if not row:
            return False # Version not found, no DB change made here
        name, prompt_instructions = row['name'], row['prompt_instructions']
        # update_persona will handle its own commit or rollback
        return update_persona(persona_id, name, prompt_instructions, updated_by_user)
    except sqlite3.Error as e:
        # This except block handles errors from the SELECT query itself.
        # update_persona has its own try-except for its operations.
        print(f"Database error in revert_persona_to_version (during select): {e}")
        # No rollback needed here as only a select failed.
        return False

def list_persona_versions(persona_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT * FROM persona_versions WHERE persona_id = ? ORDER BY version DESC
        ''', (persona_id,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error in list_persona_versions: {e}")
        return None # Return None, route handler will check

# --- Persona Assignment Logic ---
def assign_persona_to_subforum(subforum_id, persona_id, is_default=False):
    db = get_db()
    cursor = db.cursor()
    # If is_default, unset previous default for this subforum
    if is_default:
        cursor.execute('''
            UPDATE subforum_personas SET is_default_for_subforum = 0 WHERE subforum_id = ?
        ''', (subforum_id,))
    # Insert or update assignment
    cursor.execute('''
        INSERT OR IGNORE INTO subforum_personas (subforum_id, persona_id, is_default_for_subforum)
        VALUES (?, ?, ?)
    ''', (subforum_id, persona_id, int(is_default)))
    # If already assigned, update default flag
    if not cursor.rowcount and is_default:
        cursor.execute('''
            UPDATE subforum_personas SET is_default_for_subforum = 1 WHERE subforum_id = ? AND persona_id = ?
        ''', (subforum_id, persona_id))
    db.commit()
    return True

def unassign_persona_from_subforum(subforum_id, persona_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        DELETE FROM subforum_personas WHERE subforum_id = ? AND persona_id = ?
    ''', (subforum_id, persona_id))
    db.commit()
    return cursor.rowcount > 0

def list_personas_for_subforum(subforum_id, active_only=True):
    db = get_db()
    cursor = db.cursor()
    q = '''
        SELECT p.*, sp.is_default_for_subforum FROM personas p
        JOIN subforum_personas sp ON p.persona_id = sp.persona_id
        WHERE sp.subforum_id = ?
    '''
    if active_only:
        q += ' AND p.is_active = 1'
    cursor.execute(q, (subforum_id,))
    return cursor.fetchall()

def set_subforum_default_persona(subforum_id, persona_id):
    db = get_db()
    cursor = db.cursor()
    # Unset all defaults for this subforum
    cursor.execute('''
        UPDATE subforum_personas SET is_default_for_subforum = 0 WHERE subforum_id = ?
    ''', (subforum_id,))
    # Set new default
    cursor.execute('''
        UPDATE subforum_personas SET is_default_for_subforum = 1 WHERE subforum_id = ? AND persona_id = ?
    ''', (subforum_id, persona_id))
    db.commit()
    return cursor.rowcount > 0

def get_subforum_default_persona(subforum_id, active_only=True):
    db = get_db()
    cursor = db.cursor()
    q = '''
        SELECT p.* FROM personas p
        JOIN subforum_personas sp ON p.persona_id = sp.persona_id
        WHERE sp.subforum_id = ? AND sp.is_default_for_subforum = 1
    '''
    if active_only:
        q += ' AND p.is_active = 1'
    cursor.execute(q, (subforum_id,))
    return cursor.fetchone()

def get_global_default_persona_id():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'globalDefaultPersonaId'")
        row = cursor.fetchone()
        if row and row['setting_value'] is not None:
            return int(row['setting_value'])
        print("Warning: globalDefaultPersonaId not found or NULL in settings, returning fallback 1.")
        return 1 # Fallback if not set or NULL
    except sqlite3.Error as e:
        print(f"Database error in get_global_default_persona_id: {e}")
        return None # Indicates error to caller
    except ValueError as e:
        print(f"ValueError for globalDefaultPersonaId, value: {row['setting_value'] if row else 'Not Found'}. Error: {e}. Returning fallback 1.")
        return 1 # Fallback if value is not a valid integer

def set_global_default_persona_id(persona_id):
    db = get_db()
    try:
        cursor = db.cursor()
        # Ensure the persona_id exists in the personas table before setting it as default
        cursor.execute("SELECT 1 FROM personas WHERE persona_id = ? AND is_active = 1", (persona_id,))
        if not cursor.fetchone():
            print(f"Attempted to set global default to non-existent or inactive persona_id: {persona_id}")
            return False

        cursor.execute("UPDATE settings SET setting_value = ? WHERE setting_key = 'globalDefaultPersonaId'", (str(persona_id),))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error in set_global_default_persona_id: {e}")
        if db:
            db.rollback()
        return False

def get_effective_persona_for_subforum(subforum_id, override_persona_id=None):
    """
    Returns the persona row to use for a subforum, following override > subforum default > global default > fallback.
    """
    db = get_db()
    cursor = db.cursor()
    # 1. If override_persona_id is provided and valid for this subforum, use it
    if override_persona_id:
        cursor.execute('''
            SELECT p.* FROM personas p
            JOIN subforum_personas sp ON p.persona_id = sp.persona_id
            WHERE sp.subforum_id = ? AND p.persona_id = ? AND p.is_active = 1
        ''', (subforum_id, override_persona_id))
        row = cursor.fetchone()
        if row:
            return row
    # 2. Subforum default
    row = get_subforum_default_persona(subforum_id)
    if row:
        return row
    # 3. Global default
    global_id = get_global_default_persona_id()
    row = get_persona(global_id)
    if row:
        return row
    # 4. Fallback (persona_id=1)
    return get_persona(1)

def save_generated_persona(persona_name, prompt_instructions, generation_source, generation_input_details, created_by_user):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT INTO personas (name, prompt_instructions, generation_source, generation_input_details, created_by_user, is_active, version)
            VALUES (?, ?, ?, ?, ?, 1, 1)
        ''', (persona_name, prompt_instructions, generation_source, generation_input_details, created_by_user))
        persona_id = cursor.lastrowid
        
        if persona_id: # Ensure persona_id is valid before inserting into versions
            cursor.execute('''
                INSERT INTO persona_versions (persona_id, name, prompt_instructions, updated_by_user, version)
                VALUES (?, ?, ?, ?, 1)
            ''', (persona_id, persona_name, prompt_instructions, created_by_user))
            db.commit()
            return persona_id
        else:
            # This case should ideally not happen if the first insert was successful and returned a valid rowid.
            # Adding a rollback and error message for robustness.
            print(f"Error: Failed to get lastrowid after inserting into personas table for '{persona_name}'.")
            if db:
                db.rollback()
            return None

    except sqlite3.Error as e:
        print(f"Database error in save_generated_persona for '{persona_name}': {e}")
        if db:
            db.rollback()
        return None