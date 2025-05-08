import sqlite3
from flask import Blueprint, request, jsonify
from bs4 import BeautifulSoup # For link modification in LLM responses
from ..database import get_db
from ..markdown_config import md
from ..config import CURRENT_USER_ID

forum_api_bp = Blueprint('forum_api', __name__, url_prefix='/api')

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