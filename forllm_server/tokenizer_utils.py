import tiktoken
import logging

# Configure logging
logger = logging.getLogger(__name__)

_tokenizer = None
_tokenizer_initialized = False
_initialization_error = None

def _initialize_tokenizer():
    global _tokenizer, _tokenizer_initialized, _initialization_error
    if _tokenizer_initialized:
        return

    try:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
        _tokenizer_initialized = True
        logger.info("tiktoken cl100k_base tokenizer initialized successfully.")
    except Exception as e:
        _initialization_error = e
        _tokenizer_initialized = False # Explicitly set to false on error
        logger.error(f"Failed to initialize tiktoken tokenizer: {e}", exc_info=True)

def count_tokens(text: str) -> int:
    '''
    Counts the number of tokens in the given text using the cl100k_base tokenizer.

    Args:
        text: The input string.

    Returns:
        The number of tokens, or 0 if the tokenizer is not initialized or text is empty.
        Logs an error if tokenizer initialization previously failed.
    '''
    _initialize_tokenizer() # Ensure tokenizer is attempted to be initialized

    if not _tokenizer_initialized:
        if _initialization_error:
            logger.error(f"Cannot count tokens because tokenizer initialization failed: {_initialization_error}")
        else:
            logger.error("Cannot count tokens because tokenizer is not initialized and no specific error was recorded.")
        return 0 # Or raise an exception, depending on desired error handling

    if not text:
        return 0

    try:
        tokens = _tokenizer.encode(text)
        return len(tokens)
    except Exception as e:
        logger.error(f"Error encoding text with tiktoken: {e}", exc_info=True)
        return 0 # Or raise, depending on how you want to handle encoding errors

# Attempt to initialize the tokenizer when the module is loaded
# This makes it ready for use as soon as possible.
_initialize_tokenizer()

# Example usage (optional, for testing)
if __name__ == '__main__':
    sample_text = "This is a test sentence."
    token_count = count_tokens(sample_text)
    if _tokenizer_initialized:
        logger.info(f"'{sample_text}' has {token_count} tokens.")
    else:
        logger.error("Tokenizer could not be initialized. Please check logs.")

    another_text = "Another example."
    token_count_another = count_tokens(another_text)
    if _tokenizer_initialized:
        logger.info(f"'{another_text}' has {token_count_another} tokens.")
    else:
        logger.error("Tokenizer could not be initialized for the second text either.")

    # Test with empty string
    empty_text = ""
    token_count_empty = count_tokens(empty_text)
    if _tokenizer_initialized:
          logger.info(f"'{empty_text}' has {token_count_empty} tokens.")

    # Test with None (though type hint says str, good to be robust)
    # This will cause an error if not handled by a check like 'if not text:'
    # For now, count_tokens has 'if not text:'
    # none_text = None
    # token_count_none = count_tokens(none_text)
    # logger.info(f"'{none_text}' has {token_count_none} tokens.")
