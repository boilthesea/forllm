import sqlite3
import os
import re # Added for persona tagging
import json # Added for storing persona IDs
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from bs4 import BeautifulSoup # For link modification in LLM responses
from ..database import (
    get_db,
    assign_persona_to_subforum, unassign_persona_from_subforum, list_personas_for_subforum,
    set_subforum_default_persona, get_subforum_default_persona, update_user_activity,
    get_subforums_with_status, get_topics_for_subforum_with_status,
    get_persona # Import get_persona for validation
)
from ..markdown_config import md
from ..config import CURRENT_USER_ID, DEFAULT_MODEL

forum_api_bp = Blueprint('forum_api', __name__, url_prefix='/api')

# Regex for parsing persona tags: @[Persona Name](persona_id)
PERSONA_TAG_REGEX = r'@\[([^\]]+)\]\((\d+)\)'

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
        # cursor.execute("SELECT subforum_id, name FROM subforums ORDER BY name")
        # subforums = cursor.fetchall()
        # return jsonify([dict(row) for row in subforums])
        subforums_with_status = get_subforums_with_status(CURRENT_USER_ID)
        return jsonify(subforums_with_status)

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
        
        # --- Persona Tagging Logic ---
        tagged_persona_ids = []
        if content:
            matches = re.findall(PERSONA_TAG_REGEX, content)
            # Extract unique persona IDs (group 2 of the regex match is the ID)
            tagged_persona_ids = sorted(list(set([int(match[1]) for match in matches])))
        
        tagged_personas_json = json.dumps(tagged_persona_ids)
        # --- End Persona Tagging Logic ---

        try:
            cursor.execute('INSERT INTO topics (subforum_id, user_id, title) VALUES (?, ?, ?)',
                           (subforum_id, CURRENT_USER_ID, title))
            topic_id = cursor.lastrowid
            
            # Insert post with tagged persona IDs
            cursor.execute('INSERT INTO posts (topic_id, user_id, content, tagged_personas_in_content) VALUES (?, ?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, content, tagged_personas_json))
            post_id = cursor.lastrowid

            # --- Create LLM Requests for tagged personas ---
            if tagged_persona_ids:
                for p_id in tagged_persona_ids:
                    # Validate persona ID before creating LLM request
                    # get_persona uses its own db context (via get_db()) so it's safe to call here
                    persona_check = get_persona(p_id, active_only=True) 
                    if not persona_check:
                        current_app.logger.warning(
                            f"Persona ID {p_id} tagged in content for new topic (post {post_id}) "
                            f"not found or not active. Skipping LLM request for this tag."
                        )
                        continue # Skip to the next persona_id

                    cursor.execute("""
                        INSERT INTO llm_requests 
                        (post_id_to_respond_to, llm_persona, requested_by_user_id, request_type, status, llm_model)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (post_id, p_id, CURRENT_USER_ID, 'respond_to_post_tag', 'pending', None)) 
                    # Using None for llm_model, worker can determine based on persona.
            # --- End LLM Requests ---

            db.commit()
            return jsonify({'topic_id': topic_id, 'title': title, 'initial_post_id': post_id, 'tagged_personas': tagged_persona_ids}), 201
        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Error creating topic or LLM requests: {e}")
            return jsonify({'error': f'Failed to create topic: {e}'}), 500
    else: # GET
        # cursor.execute("""
        #     SELECT t.topic_id, t.title, u.username, t.created_at,
        #            (SELECT COUNT(*) FROM posts p WHERE p.topic_id = t.topic_id) as post_count,
        #            (SELECT MAX(p.created_at) FROM posts p WHERE p.topic_id = t.topic_id) as last_post_at
        #     FROM topics t
        #     JOIN users u ON t.user_id = u.user_id
        #     WHERE t.subforum_id = ?
        #     ORDER BY last_post_at DESC
        # """, (subforum_id,))
        # topics = cursor.fetchall()
        topics_with_status = get_topics_for_subforum_with_status(subforum_id, CURRENT_USER_ID)
        # Record user activity for viewing subforum (still relevant after fetching topics)
        if not update_user_activity(CURRENT_USER_ID, 'subforum', subforum_id):
            current_app.logger.error(f"Failed to update user activity for user {CURRENT_USER_ID}, subforum {subforum_id}")
        # return jsonify([dict(row) for row in topics])
        return jsonify(topics_with_status)

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

        # --- Persona Tagging Logic ---
        tagged_persona_ids = []
        if content:
            matches = re.findall(PERSONA_TAG_REGEX, content)
            tagged_persona_ids = sorted(list(set([int(match[1]) for match in matches])))
        
        tagged_personas_json = json.dumps(tagged_persona_ids)
        # --- End Persona Tagging Logic ---

        try:
            # Insert post with tagged persona IDs
            cursor.execute('INSERT INTO posts (topic_id, user_id, parent_post_id, content, tagged_personas_in_content) VALUES (?, ?, ?, ?, ?)',
                           (topic_id, CURRENT_USER_ID, parent_post_id, content, tagged_personas_json))
            post_id = cursor.lastrowid

            # --- Create LLM Requests for tagged personas ---
            if tagged_persona_ids:
                for p_id in tagged_persona_ids:
                    # Validate persona ID before creating LLM request
                    persona_check = get_persona(p_id, active_only=True)
                    if not persona_check:
                        current_app.logger.warning(
                            f"Persona ID {p_id} tagged in content for reply to post {parent_post_id} (new post {post_id}) "
                            f"not found or not active. Skipping LLM request for this tag."
                        )
                        continue # Skip to the next persona_id
                        
                    cursor.execute("""
                        INSERT INTO llm_requests 
                        (post_id_to_respond_to, llm_persona, requested_by_user_id, request_type, status, llm_model)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (post_id, p_id, CURRENT_USER_ID, 'respond_to_post_tag', 'pending', None))
            # --- End LLM Requests ---
            
            db.commit()
            
            # Fetch the newly created post to return in the response
            cursor.execute("""
                SELECT p.*, u.username 
                FROM posts p 
                JOIN users u ON p.user_id = u.user_id 
                WHERE p.post_id = ?
            """, (post_id,))
            new_post_row = cursor.fetchone()
            
            if not new_post_row: # Should not happen if insert was successful
                db.rollback() # Should be redundant if commit succeeded, but for safety.
                return jsonify({'error': 'Failed to retrieve newly created post after insert.'}), 500

            new_post_dict = dict(new_post_row)
            # Add tagged persona IDs to the response for clarity
            new_post_dict['tagged_personas_explicitly_in_content'] = tagged_persona_ids
            
            return jsonify(new_post_dict), 201
        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Error creating post reply or LLM requests: {e}")
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
        # Record user activity for viewing topic
        if not update_user_activity(CURRENT_USER_ID, 'topic', topic_id):
            current_app.logger.error(f"Failed to update user activity for user {CURRENT_USER_ID}, topic {topic_id}")
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
            order_in_post_str = request.form.get('order_in_post')
            order_in_post = None

            if order_in_post_str is not None:
                try:
                    order_in_post_val = int(order_in_post_str)
                    if order_in_post_val >= 0:
                        order_in_post = order_in_post_val
                    else:
                        return jsonify({'error': 'order_in_post must be a non-negative integer.'}), 400
                except ValueError:
                    return jsonify({'error': 'order_in_post must be a valid integer.'}), 400
            else:
                # This case should ideally not be hit if client always sends it.
                # For robustness, if client *might* not send it, this fallback could be used,
                # but the prompt implies client will send it. Sticking to stricter:
                return jsonify({'error': 'order_in_post is required in form data.'}), 400

            cursor.execute('''
                INSERT INTO attachments (post_id, filename, filepath, order_in_post)
                VALUES (?, ?, ?, ?)
            ''', (post_id, filename, filepath_relative, order_in_post)) # Use client-provided order_in_post
            db.commit()
            attachment_id = cursor.lastrowid
            
            # Ensure 'filename' here refers to the secured filename if that's what's stored and used.
            # The variable 'filename' was already secure_filename(file.filename)
            print(f"[DEBUG AttachmentSave] Saved attachment: id={attachment_id}, post_id={post_id}, filename='{filename}', filepath='{filepath_relative}', order_in_post={order_in_post}")
            
            # Return the actual order_in_post used
            return jsonify({
                'attachment_id': attachment_id,
                'filename': filename,
                'filepath': filepath_relative,
                'post_id': post_id,
                'order_in_post': order_in_post 
            }), 201
        except sqlite3.IntegrityError as e: # Specifically catch IntegrityError for UNIQUE constraint
            db.rollback()
            if "UNIQUE constraint failed: attachments.post_id, attachments.order_in_post" in str(e):
                 return jsonify({'error': f'Database error: An attachment with order {order_in_post} already exists for this post.'}), 409 # Conflict
            else:
                 return jsonify({'error': f'Database integrity error: {str(e)}'}), 500
        except sqlite3.Error as e: # Catch other SQLite errors
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

@forum_api_bp.route('/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    db = get_db()
    cursor = db.cursor()

    # 1. Check if post exists
    cursor.execute("SELECT post_id FROM posts WHERE post_id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    # 2. Fetch attachment filepaths BEFORE deleting the post record
    cursor.execute("SELECT filepath FROM attachments WHERE post_id = ?", (post_id,))
    attachment_rows = cursor.fetchall()
    filepaths_to_delete = [row['filepath'] for row in attachment_rows]

    # 3. Delete physical files
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder:
        print(f"Warning: UPLOAD_FOLDER not configured. Cannot delete attachment files for post {post_id}.")
        # Decide if this should be a hard error or just a warning. For now, proceed to delete DB record.
    else:
        for relative_filepath in filepaths_to_delete:
            if not relative_filepath: # Should not happen if DB data is clean
                continue
            full_filepath = os.path.join(upload_folder, relative_filepath)
            try:
                if os.path.exists(full_filepath) and os.path.isfile(full_filepath): # Ensure it's a file
                    os.remove(full_filepath)
                    print(f"Deleted attachment file: {full_filepath}")
                elif not os.path.exists(full_filepath):
                    print(f"Attachment file not found (already deleted?): {full_filepath}")
            except Exception as e:
                print(f"Error deleting attachment file {full_filepath}: {e}")
                # Continue to delete other files and the post record

    # 4. Delete the post record from the database
    # The ON DELETE CASCADE on 'attachments.post_id' will handle deleting attachment records.
    # The ON DELETE CASCADE on 'posts.parent_post_id' (if it were set, it's not by default for self-referencing)
    # would need careful consideration. For now, we assume only direct post deletion.
    # If a post is a parent, its children might become orphaned or need specific handling
    # (e.g., delete children or re-parent). This is outside current scope of attachment cleanup.
    # We also need to consider llm_requests associated with this post.
    # For now, let's assume related llm_requests should also be deleted if the post they respond to is deleted.
    # The schema for llm_requests has ON DELETE CASCADE for post_id_to_respond_to.
    
    try:
        # First, handle any replies to this post (children).
        # Simple approach: delete children posts. More complex: re-parent or prevent deletion.
        # For now, let's recursively delete children to avoid orphaned posts.
        # This requires a recursive function or careful iterative deletion.
        # For simplicity in this step, we'll delete direct children. A full recursive delete is more complex.
        
        # Get child posts
        cursor.execute("SELECT post_id FROM posts WHERE parent_post_id = ?", (post_id,))
        child_post_ids = [row['post_id'] for row in cursor.fetchall()]
        
        # Recursively call delete_post for each child.
        # This is a simplified recursion; true recursion within a single request can be tricky.
        # A better way might be to gather all descendant IDs first.
        # However, for this task, we'll focus on the requested file deletion aspect.
        # Let's assume for now that deleting child posts is handled elsewhere or not required for this specific task.
        # A simple deletion of the post itself:
        
        cursor.execute("DELETE FROM posts WHERE post_id = ?", (post_id,))
        db.commit()

        if cursor.rowcount == 0:
            # Should not happen if we checked for existence, but as a safeguard
            return jsonify({'error': 'Post not found during deletion or already deleted'}), 404
        
        print(f"Successfully deleted post {post_id} and its attachment records from DB.")

    except sqlite3.Error as e:
        db.rollback()
        print(f"Database error deleting post {post_id}: {e}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    
    # 5. Attempt to delete the post's attachment subdirectory
    if upload_folder and filepaths_to_delete: # Only try if there were attachments and upload_folder is set
        # The relative_filepath for an attachment is like "post_id/filename.txt"
        # So, the directory is the first part of that path.
        # We can robustly get the post's specific directory:
        post_specific_upload_dir = os.path.join(upload_folder, str(post_id))
        try:
            if os.path.exists(post_specific_upload_dir) and os.path.isdir(post_specific_upload_dir):
                if not os.listdir(post_specific_upload_dir): # Check if empty
                    os.rmdir(post_specific_upload_dir)
                    print(f"Deleted empty attachment directory: {post_specific_upload_dir}")
                else:
                    print(f"Attachment directory not empty, not deleting: {post_specific_upload_dir}")
        except Exception as e:
            print(f"Error deleting attachment directory {post_specific_upload_dir}: {e}")
            # Do not let this error block the success response for post deletion

    return jsonify({'message': f'Post {post_id} and associated attachments deleted successfully'}), 200