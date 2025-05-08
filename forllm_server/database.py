import sqlite3
from flask import g
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

        # Ensure all default settings are present if the settings table already existed
        # This is a good place to add new settings with defaults if they are introduced later
        default_settings_to_check = {
            'darkMode': 'false',
            'selectedModel': DEFAULT_MODEL,
            'llmLinkSecurity': 'true'
        }
        for key, default_value in default_settings_to_check.items():
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = ?", (key,))
            if cursor.fetchone() is None:
                print(f"Setting '{key}' missing. Adding with default value '{default_value}'.")
                cursor.execute("INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, default_value))
                db.commit()

    print("Database initialization complete.")
    db.close()