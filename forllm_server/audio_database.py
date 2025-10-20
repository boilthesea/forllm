import sqlite3

def get_audio_db_connection():
    conn = sqlite3.connect('forllm_audio.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_audio_db():
    conn = get_audio_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audiobooks (
        book_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT,
        cover_image_path TEXT,
        source_file_hash TEXT NOT NULL UNIQUE,
        output_file_path TEXT,
        status TEXT NOT NULL DEFAULT 'pending_extraction',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audiobook_chapters (
        chapter_id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        chapter_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        extracted_text TEXT NOT NULL,
        llm_request_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        FOREIGN KEY (book_id) REFERENCES audiobooks(book_id)
    );
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_audio_db()
    print("Audiobook database initialized.")