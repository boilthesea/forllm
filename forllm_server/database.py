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
            'darkMode': 'false',
            'selectedModel': DEFAULT_MODEL,
            'llmLinkSecurity': 'true'
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


    db.commit() # Commit after ensuring all persona tables, indexes, and default data.
    print("Persona management tables and defaults verified/created.")

    print("Database initialization complete.")
    db.close()

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