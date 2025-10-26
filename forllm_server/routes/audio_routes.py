from flask import Blueprint, request, jsonify
from forllm_server.calibre_handler import get_ebook_metadata
from forllm_server.audio_database import add_audiobook, add_chapter, get_chapters_for_book, update_audiobook_status, get_completed_audiobooks, get_audiobook_by_id, set_audio_setting, get_audio_setting
from forllm_server.database import add_llm_request
import hashlib
import json
import os
import shutil
 
audio_bp = Blueprint('audio_bp', __name__)

def find_executable(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)
    return None

@audio_bp.route('/api/audio/upload_ebook', methods=['POST'])
def upload_ebook():
    if 'ebook_file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['ebook_file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        # Read content for hashing
        file_content = file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Reset cursor for calibre_handler
        file.seek(0)

        ebook_data = get_ebook_metadata(file)
    if not ebook_data:
        return jsonify({"error": "Failed to process ebook"}), 500

    book_id = add_audiobook(
        title=ebook_data['title'],
        author=ebook_data['author'],
        cover_image_path=ebook_data['cover_path'],
        source_file_hash=file_hash,
        status='pending_user_review'
    )

    chapters_data = []
    for i, chapter in enumerate(ebook_data['chapters']):
        chapter_id = add_chapter(
            book_id=book_id,
            chapter_index=i,
            title=chapter['title'],
            extracted_text=chapter['text']
        )
        chapters_data.append({
            "chapter_id": chapter_id,
            "index": i,
            "title": chapter['title'],
            "text": chapter['text']
        })

    return jsonify({
        "book_id": book_id,
        "title": ebook_data['title'],
        "author": ebook_data['author'],
        "cover_path": ebook_data['cover_path'],
        "chapters": chapters_data
    })

@audio_bp.route('/api/audio/queue_audiobook', methods=['POST'])
def queue_audiobook():
    data = request.get_json()
    book_id = data.get('book_id')
    voice = data.get('voice') # Changed from voice_id to voice

    if not book_id or not voice:
        return jsonify({"error": "book_id and voice are required"}), 400

    chapters = get_chapters_for_book(book_id)
    if not chapters:
        return jsonify({"error": "No chapters found for this book"}), 404

    parent_request_params = {
        "book_id": book_id,
        "voice": voice,
        "chapter_count": len(chapters)
    }
    parent_request = add_llm_request(
        request_type='generate_audiobook_parent',
        params=parent_request_params,
        status='pending'
    )

    for chapter in chapters:
        child_request_params = {
            "book_id": book_id,
            "chapter_id": chapter['id'],
            "voice": voice
        }
        add_llm_request(
            request_type='generate_audiobook_chapter',
            params=child_request_params,
            parent_request_id=parent_request['id'],
            status='pending_dependency'
        )

    update_audiobook_status(book_id, 'queued')

    return jsonify({
        "message": "Audiobook generation queued successfully",
        "parent_request_id": parent_request['id']
    })

@audio_bp.route('/api/audio/audiobooks', methods=['GET'])
def get_all_audiobooks():
    audiobooks = get_completed_audiobooks()
    return jsonify(audiobooks)

@audio_bp.route('/api/audio/audiobooks/<int:book_id>', methods=['GET'])
def get_single_audiobook(book_id):
    audiobook = get_audiobook_by_id(book_id)
    if audiobook:
        return jsonify(audiobook)
    return jsonify({"error": "Audiobook not found"}), 404

@audio_bp.route('/api/audio/settings/calibre_path', methods=['GET', 'POST'])
def calibre_path():
    if request.method == 'POST':
        data = request.get_json()
        path = data.get('path')
        if not path or not os.path.isdir(path):
            return jsonify({"error": "Invalid path provided"}), 400

        executable_path = find_executable("ebook-convert.exe" if os.name == 'nt' else "ebook-convert", path)

        if executable_path:
            verified_path = os.path.dirname(executable_path)
            set_audio_setting('calibre_path', verified_path)
            return jsonify({"message": "Calibre path verified and saved.", "path": verified_path})
        else:
            return jsonify({"error": "'ebook-convert' not found in the specified path."}), 404
    else: # GET
        path = get_audio_setting('calibre_path')
        return jsonify({"path": path})

@audio_bp.route('/api/audio/status/calibre', methods=['GET'])
def calibre_status():
    # Check system PATH
    path_status = "found" if shutil.which("ebook-convert") else "not_found"

    # Check manual path
    manual_path = get_audio_setting('calibre_path')
    manual_path_status = "not_found"
    if manual_path:
        executable_name = "ebook-convert.exe" if os.name == 'nt' else "ebook-convert"
        if os.path.exists(os.path.join(manual_path, executable_name)):
            manual_path_status = "found"

    return jsonify({
        "path_status": path_status,
        "manual_path": manual_path,
        "manual_path_status": manual_path_status
    })