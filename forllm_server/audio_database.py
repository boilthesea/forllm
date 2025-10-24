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

def add_audiobook(title, author, cover_image_path, source_file_hash, status):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audiobooks (title, author, cover_image_path, source_file_hash, status) VALUES (?, ?, ?, ?, ?)",
        (title, author, cover_image_path, source_file_hash, status)
    )
    book_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return book_id

def add_chapter(book_id, chapter_index, title, extracted_text):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audiobook_chapters (book_id, chapter_index, title, extracted_text) VALUES (?, ?, ?, ?)",
        (book_id, chapter_index, title, extracted_text)
    )
    chapter_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return chapter_id

def get_chapters_for_book(book_id):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audiobook_chapters WHERE book_id = ?", (book_id,))
    chapters = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return chapters

def update_audiobook_status(book_id, status, output_file_path=None):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    if output_file_path:
        cursor.execute("UPDATE audiobooks SET status = ?, output_file_path = ? WHERE book_id = ?", (status, output_file_path, book_id))
    else:
        cursor.execute("UPDATE audiobooks SET status = ? WHERE book_id = ?", (status, book_id))
    conn.commit()
    conn.close()

def get_completed_audiobooks():
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audiobooks WHERE status = 'completed'")
    audiobooks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return audiobooks

def get_audiobook_by_id(book_id):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audiobooks WHERE book_id = ?", (book_id,))
    row = cursor.fetchone()
    audiobook = dict(row) if row else None
    if audiobook:
        audiobook['chapters'] = get_chapters_for_book(book_id)
    conn.close()
    return audiobook

def get_chapter_by_id(chapter_id):
    conn = get_audio_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audiobook_chapters WHERE chapter_id = ?", (chapter_id,))
    row = cursor.fetchone()
    chapter = dict(row) if row else None
    conn.close()
    return chapter



if __name__ == '__main__':

    init_audio_db()

    print("Audiobook database initialized.")