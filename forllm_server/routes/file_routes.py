from flask import Blueprint, request, jsonify
from ..file_indexer import search_indexed_files

file_routes = Blueprint('file_routes', __name__)

@file_routes.route('/api/files/search', methods=['GET'])
def search_files_endpoint():
    """
    Endpoint for the editor's autocomplete file search.
    Searches the file_index_cache based on the query parameter 'q'.
    """
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([]) # Return empty list if query is empty

    try:
        results = search_indexed_files(query)
        return jsonify(results)
    except Exception as e:
        # Log the exception e
        print(f"Error in file search endpoint: {e}")
        return jsonify({"error": "An error occurred during file search."}), 500