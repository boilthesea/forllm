from flask import Blueprint, request, jsonify
from forllm_server.calibre_handler import get_ebook_metadata
from forllm_server.audio_database import add_audiobook, add_chapter
import hashlib

audio_bp = Blueprint('audio_bp', __name__)

@audio_bp.route('/api/audio/upload_ebook', methods=['POST'])
def upload_ebook():
    data = request.get_json()
    ebook_path = data.get('path')

    if not ebook_path:
        return jsonify({"error": "File path is required"}), 400

    try:
        with open(ebook_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return jsonify({"error": "Ebook file not found"}), 404

    ebook_data = get_ebook_metadata(ebook_path)
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