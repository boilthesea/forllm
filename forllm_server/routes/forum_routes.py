import sqlite3
import os
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from bs4 import BeautifulSoup # For link modification in LLM responses
from ..database import (
    get_db,
    assign_persona_to_subforum, unassign_persona_from_subforum, list_personas_for_subforum,
    set_subforum_default_persona, get_subforum_default_persona
)
from ..markdown_config import md
from ..config import CURRENT_USER_ID

forum_api_bp = Blueprint('forum_api', __name__, url_prefix='/api')

# Helper function to check for plain text
def is_plain_text(file_stream):
    """
    Checks if a file stream appears to be plain text.
    Reads a small portion, checks UTF-8 decoding, printable chars, and null bytes.
    """
    try:
        # Read a small chunk (e.g., 2KB)
        chunk_size = 2048
        original_position = file_stream.tell()
        chunk = file_stream.read(chunk_size)
        file_stream.seek(original_position) # Reset stream position

        if not chunk: # Empty file can be considered plain text or handled as an error by caller
            return True

        # Attempt to decode as UTF-8
        try:
            text_content = chunk.decode('utf-8')
        except UnicodeDecodeError:
            return False # Not valid UTF-8

        # Check for high percentage of printable characters
        printable_chars = sum(c.isprintable() or c.isspace() for c in text_content)
        total_chars = len(text_content)
        if total_chars == 0: # Should have been caught by 'if not chunk'
             return True 
        
        # Allow a very small number of non-printable chars, but mostly printable
        # Adjust threshold as needed. >85% printable seems reasonable.
        if (printable_chars / total_chars) < 0.85:
            return False

        # Check for null bytes (common in binary files)
        # Allow a very small tolerance for null bytes, e.g., in some text encodings or formats
        # For truly plain text, null bytes should be rare or absent.
        if b'\x00' in chunk:
            null_byte_count = chunk.count(b'\x00')
            # If more than, say, 2 null bytes in a 2KB chunk, or if they make up >1% of the chunk
            if null_byte_count > 2 or (null_byte_count / len(chunk)) > 0.01:
                 return False
        
        return True
    except Exception:
        # If any error occurs during the check, assume it's not plain text for safety
        return False

@forum_api_bp.route('/subforums', methods=['GET', 'POST'])
def handle_subforums():
    db = get_db()
    cursor = db.cursor()
    if request.method == 'POST':
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

@forum_api_bp.route('/subforums/<int:subforum_id>/topics', methods=['GET', 'POST'])
def handle_topics(subforum_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT subforum_id FROM subforums WHERE subforum_id = ?", (subforum_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Subforum not found'}), 404

    if request.method == 'POST':
        data = request.get_json()
        title = data.get('title')
        content = data.get('content')
        if not title or not content:
            return jsonify({'error': 'Title and content are required for a new topic'}), 400
        try:
            cursor.execute('INSERT INTO topics (subforum_id, user_id, title) VALUES (?, ?, ?)',
                           (subforum_id, CURRENT_USER_ID, title))
            topic_id = cursor.lastrowid
            cursor.execute('INSERT INTO posts (topic_id, user_id, content) VALUES (?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, content))
            post_id = cursor.lastrowid
            db.commit()
            return jsonify({'topic_id': topic_id, 'title': title, 'initial_post_id': post_id}), 201
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Failed to create topic: {e}'}), 500
    else: # GET
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

@forum_api_bp.route('/topics/<int:topic_id>/posts', methods=['GET', 'POST'])
def handle_posts(topic_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT topic_id FROM topics WHERE topic_id = ?", (topic_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Topic not found'}), 404

    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content')
        parent_post_id = data.get('parent_post_id')
        if not content:
            return jsonify({'error': 'Content is required for a reply'}), 400
        if not parent_post_id:
             return jsonify({'error': 'Parent post ID is required for a reply'}), 400
        cursor.execute("SELECT post_id FROM posts WHERE post_id = ? AND topic_id = ?", (parent_post_id, topic_id))
        if not cursor.fetchone():
            return jsonify({'error': 'Parent post not found in this topic'}), 404
        try:
            cursor.execute('INSERT INTO posts (topic_id, user_id, parent_post_id, content) VALUES (?, ?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, parent_post_id, content))
            post_id = cursor.lastrowid
            db.commit()
            cursor.execute("SELECT p.*, u.username FROM posts p JOIN users u ON p.user_id = u.user_id WHERE p.post_id = ?", (post_id,))
            new_post = cursor.fetchone()
            return jsonify(dict(new_post)), 201
        except Exception as e:
            db.rollback()
            return jsonify({'error': f'Failed to create post: {e}'}), 500
    else: # GET
        cursor.execute("""
            WITH RECURSIVE ThreadCTE AS (
                SELECT
                    p.post_id, p.topic_id, p.user_id, u.username, p.parent_post_id, p.content, p.created_at,
                    p.is_llm_response, p.llm_model_id, p.llm_persona_id,
                    CAST(p.created_at AS TEXT) AS sort_key,
                    0 AS depth
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.topic_id = ? AND p.parent_post_id IS NULL
                UNION ALL
                SELECT
                    p2.post_id, p2.topic_id, p2.user_id, u2.username, p2.parent_post_id, p2.content, p2.created_at,
                    p2.is_llm_response, p2.llm_model_id, p2.llm_persona_id,
                    cte.sort_key || '_' || CAST(p2.created_at AS TEXT),
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
            
            # Fetch attachments for this post
            post_id = post_dict['post_id']
            cursor.execute("""
                SELECT attachment_id, filename, filepath, user_prompt, order_in_post
                FROM attachments
                WHERE post_id = ?
                ORDER BY order_in_post ASC
            """, (post_id,))
            attachments_raw = cursor.fetchall()
            attachments_list = [dict(att_row) for att_row in attachments_raw]
            post_dict['attachments'] = attachments_list

            html_content = md.render(post_dict['content'])
            if post_dict.get('is_llm_response'):
                try:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    links = soup.find_all('a')
                    if links:
                        link_modified = False
                        for link in links:
                            current_classes = link.get('class', [])
                            if 'llm-link' not in current_classes:
                                link['class'] = current_classes + ['llm-link']
                                link_modified = True
                        if link_modified:
                            html_content = str(soup)
                except Exception as e:
                    print(f"Error parsing or modifying HTML for LLM post {post_dict.get('post_id', 'N/A')}: {e}")
            post_dict['content'] = html_content
            processed_posts.append(post_dict)
        return jsonify(processed_posts)

# --- Persona Assignment Endpoints ---
@forum_api_bp.route('/subforums/<int:subforum_id>/personas', methods=['GET'])
def api_list_personas_for_subforum(subforum_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT persona_id, name FROM personas WHERE subforum_id = ?", (subforum_id,))
    personas = cursor.fetchall()
    return jsonify([dict(p) for p in personas])

@forum_api_bp.route('/subforums/<int:subforum_id>/personas', methods=['POST'])
def api_assign_persona_to_subforum(subforum_id):
    data = request.json
    persona_id = data.get('persona_id')
    is_default = bool(data.get('is_default', False))
    if not persona_id:
        return jsonify({'error': 'persona_id required'}), 400
    db = get_db()
    try:
        with db:
            assign_persona_to_subforum(subforum_id, persona_id, is_default)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@forum_api_bp.route('/subforums/<int:subforum_id>/personas/<int:persona_id>', methods=['DELETE'])
def api_unassign_persona_from_subforum(subforum_id, persona_id):
    db = get_db()
    try:
        with db:
            ok = unassign_persona_from_subforum(subforum_id, persona_id)
        if not ok:
            return jsonify({'error': 'Assignment not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@forum_api_bp.route('/subforums/<int:subforum_id>/personas/default', methods=['POST'])
def api_set_subforum_default_persona(subforum_id):
    data = request.json
    persona_id = data.get('persona_id')
    if not persona_id:
        return jsonify({'error': 'persona_id required'}), 400
    db = get_db()
    try:
        with db:
            ok = set_subforum_default_persona(subforum_id, persona_id)
        if not ok:
            return jsonify({'error': 'Failed to set default'}), 400
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@forum_api_bp.route('/subforums/<int:subforum_id>/personas/default', methods=['GET'])
def api_get_subforum_default_persona(subforum_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT persona_id, name FROM personas WHERE subforum_id = ? AND is_default = 1", (subforum_id,))
    p = cursor.fetchone()
    if not p:
        return jsonify({'error': 'No default persona'}), 404
    return jsonify(dict(p))

@forum_api_bp.route('/posts/<int:post_id>/attachments', methods=['POST'])
def upload_attachment(post_id):
    db = get_db()
    cursor = db.cursor()

    # Check if the post exists
    cursor.execute("SELECT post_id FROM posts WHERE post_id = ?", (post_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Post not found'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Validate if the file is plain text
        original_stream_pos = file.stream.tell()
        if not is_plain_text(file.stream):
            file.stream.seek(original_stream_pos) # Reset stream position
            return jsonify({'error': 'File does not appear to be plain text'}), 400
        file.stream.seek(original_stream_pos) # Reset stream position for saving

        # Create upload directory if it doesn't exist
        # UPLOAD_FOLDER is expected to be in app.config
        upload_folder_for_post = os.path.join(current_app.config['UPLOAD_FOLDER'], str(post_id))
        os.makedirs(upload_folder_for_post, exist_ok=True)
        
        # Relative path for database storage
        filepath_relative = os.path.join(str(post_id), filename)
        # Full path for saving the file
        filepath_full = os.path.join(current_app.config['UPLOAD_FOLDER'], filepath_relative)

        try:
            file.save(filepath_full)
        except Exception as e:
            return jsonify({'error': f'Failed to save file: {str(e)}'}), 500

        # Store attachment details in the database
        try:
            # Get current max order_in_post for this post_id
            cursor.execute("SELECT MAX(order_in_post) FROM attachments WHERE post_id = ?", (post_id,))
            max_order = cursor.fetchone()[0]
            current_order = 0
            if max_order is not None:
                current_order = max_order + 1

            cursor.execute('''
                INSERT INTO attachments (post_id, filename, filepath, order_in_post)
                VALUES (?, ?, ?, ?)
            ''', (post_id, filename, filepath_relative, current_order))
            db.commit()
            attachment_id = cursor.lastrowid
            
            return jsonify({
                'attachment_id': attachment_id,
                'filename': filename,
                'filepath': filepath_relative,
                'post_id': post_id,
                'order_in_post': current_order
            }), 201
        except sqlite3.Error as e:
            db.rollback()
            # Attempt to remove the saved file if DB insert fails
            try:
                os.remove(filepath_full)
            except OSError:
                pass # Log this error in a real app
            return jsonify({'error': f'Database error: {str(e)}'}), 500
        except Exception as e: # Catch any other unexpected errors
            db.rollback()
            try:
                os.remove(filepath_full)
            except OSError:
                pass
            return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500
            
    return jsonify({'error': 'File upload failed for an unknown reason'}), 500

@forum_api_bp.route('/attachments/<int:attachment_id>', methods=['PUT'])
def update_attachment(attachment_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_prompt = data.get('user_prompt')
    order_in_post = data.get('order_in_post')

    if user_prompt is None and order_in_post is None:
        return jsonify({'error': 'No updatable fields provided (user_prompt or order_in_post)'}), 400

    db = get_db()
    cursor = db.cursor()

    # Check if attachment exists
    cursor.execute("SELECT attachment_id FROM attachments WHERE attachment_id = ?", (attachment_id,))
    if not cursor.fetchone():
        return jsonify({'error': 'Attachment not found'}), 404

    fields_to_update = []
    params = []

    if user_prompt is not None:
        fields_to_update.append("user_prompt = ?")
        params.append(user_prompt)
    
    if order_in_post is not None:
        if not isinstance(order_in_post, int):
            return jsonify({'error': 'order_in_post must be an integer'}), 400
        fields_to_update.append("order_in_post = ?")
        params.append(order_in_post)

    if not fields_to_update: # Should be caught by earlier check, but as a safeguard
        return jsonify({'error': 'No valid fields to update'}), 400

    sql = f"UPDATE attachments SET {', '.join(fields_to_update)} WHERE attachment_id = ?"
    params.append(attachment_id)

    try:
        cursor.execute(sql, tuple(params))
        db.commit()
        if cursor.rowcount == 0:
             # Should not happen if we already checked for existence, but good for robustness
            return jsonify({'error': 'Attachment not found or no change made'}), 404
        return jsonify({'message': 'Attachment updated successfully'})
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@forum_api_bp.route('/attachments/<int:attachment_id>', methods=['DELETE'])
def delete_attachment(attachment_id):
    db = get_db()
    cursor = db.cursor()

    # Fetch filepath first
    cursor.execute("SELECT filepath FROM attachments WHERE attachment_id = ?", (attachment_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Attachment not found'}), 404
    
    filepath_relative = row['filepath']
    filepath_full = os.path.join(current_app.config['UPLOAD_FOLDER'], filepath_relative)

    try:
        # Delete the file
        try:
            os.remove(filepath_full)
        except FileNotFoundError:
            # Log this: print(f"File not found during deletion: {filepath_full}, proceeding to delete DB record.")
            pass # File already deleted, proceed to delete DB record
        except OSError as e:
            # Other OS errors (permissions, etc.), might be more serious
            # print(f"Error deleting file {filepath_full}: {e}")
            # Depending on policy, you might want to stop or continue. Here we continue.
            pass


        # Delete the database record
        cursor.execute("DELETE FROM attachments WHERE attachment_id = ?", (attachment_id,))
        db.commit()

        if cursor.rowcount == 0:
            # This might happen if the attachment was deleted by another request between fetching and deleting
            return jsonify({'error': 'Attachment record not found or already deleted'}), 404
            
        return jsonify({'message': 'Attachment deleted successfully'})
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e: # Catch any other unexpected errors
        # db.rollback() # Rollback may not be needed if the error is not from sqlite
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500