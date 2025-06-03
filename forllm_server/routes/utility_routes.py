from flask import Blueprint, request, jsonify
from forllm_server.tokenizer_utils import count_tokens
import logging

utility_bp = Blueprint('utility_bp', __name__)
logger = logging.getLogger(__name__)

@utility_bp.route('/api/utils/count_tokens_for_text', methods=['POST'])
def count_tokens_for_text_route():
    try:
        data = request.get_json()
        text = data.get('text', '')
        if text is None: # Handle explicit null
            text = ''

        token_count = count_tokens(text)
        # Log the request and response for debugging
        # logger.debug(f"Counting tokens for text: '{text[:50]}...', count: {token_count}")
        return jsonify({'token_count': token_count})
    except Exception as e:
        logger.error(f"Error in /api/utils/count_tokens_for_text: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
