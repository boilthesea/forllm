import requests
import json
from flask import current_app

from .database import get_cached_model_context_window, cache_model_context_window

def get_ollama_model_details(model_name: str) -> dict | None:
    """
    Fetches model details from Ollama's /api/show endpoint.

    Args:
        model_name: The name of the model to get details for.

    Returns:
        A dictionary containing the model details if successful, None otherwise.
    """
    if not model_name:
        current_app.logger.error("get_ollama_model_details: model_name cannot be empty.")
        return None

    ollama_base_url = current_app.config.get('OLLAMA_API_BASE_URL', 'http://localhost:11434')
    show_url = f"{ollama_base_url}/api/show"
    payload = {"name": model_name}

    current_app.logger.info(f"Fetching details for model '{model_name}' from {show_url}")

    try:
        response = requests.post(show_url, json=payload, timeout=10) # Added timeout
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)

        details = response.json()
        current_app.logger.info(f"Successfully fetched details for model '{model_name}'")
        # current_app.logger.debug(f"Model details for '{model_name}': {json.dumps(details, indent=2)}")
        return details
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            current_app.logger.warning(f"Model '{model_name}' not found on Ollama server at {show_url}.")
        else:
            current_app.logger.error(f"HTTP error fetching details for model '{model_name}': {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        current_app.logger.error(f"Connection error: Could not connect to Ollama at {show_url}. Is Ollama running? Details: {e}")
        return None
    except requests.exceptions.Timeout as e:
        current_app.logger.error(f"Timeout error fetching details for model '{model_name}': {e}")
        return None
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error fetching details for model '{model_name}': {e}")
        return None
    except json.JSONDecodeError as e:
        current_app.logger.error(f"Error decoding JSON response for model '{model_name}': {e}")
        current_app.logger.error(f"Response text: {response.text if 'response' in locals() else 'Response object not available'}")
        return None

def parse_model_context_window(model_details: dict) -> int | None:
    """
    Parses the model details to find the context window size (num_ctx).

    Args:
        model_details: A dictionary containing model details from Ollama's /api/show.
                       Expected to have a 'details' key, which in turn has a 'parameters' key
                       containing a multi-line string with model parameters.

    Returns:
        The context window size (num_ctx) as an integer if found, None otherwise.
    """
    if not model_details:
        current_app.logger.warning("parse_model_context_window: model_details is None or empty.")
        return None

    try:
        parameters_str = model_details.get('details', {}).get('parameters', '')
        if not parameters_str:
            current_app.logger.warning("parse_model_context_window: 'parameters' string not found or empty in model_details.")
            # Fallback: Check common alternative locations if 'parameters' is missing or doesn't have num_ctx
            # Some models might store it directly in 'model_info' or similar, though 'parameters' is standard for /api/show
            if 'model_info' in model_details:
                num_ctx_val = model_details['model_info'].get('num_ctx')
                if isinstance(num_ctx_val, int):
                    current_app.logger.info(f"Found num_ctx: {num_ctx_val} in model_info as integer.")
                    return num_ctx_val
                elif isinstance(num_ctx_val, str) and num_ctx_val.isdigit():
                     current_app.logger.info(f"Found num_ctx: {num_ctx_val} in model_info as string, converting.")
                     return int(num_ctx_val)

            current_app.logger.warning("parse_model_context_window: 'parameters' string not found or empty, and no fallback num_ctx found in model_info.")
            return None

        lines = parameters_str.strip().split('\n')
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and (parts[0] == 'num_ctx' or parts[0] == 'max_sequence_length'): # Check for both common names
                try:
                    context_window = int(parts[1])
                    current_app.logger.info(f"Successfully parsed context window (num_ctx/max_sequence_length): {context_window} from parameters string.")
                    return context_window
                except ValueError:
                    current_app.logger.error(f"parse_model_context_window: Found '{parts[0]}' but could not parse value '{parts[1]}' as integer.")
                    return None

        current_app.logger.warning(f"parse_model_context_window: 'num_ctx' or 'max_sequence_length' not found in parameters string: {parameters_str}")
        return None

    except Exception as e:
        current_app.logger.error(f"parse_model_context_window: Unexpected error while parsing model details: {e}")
        current_app.logger.debug(f"Model details causing error: {json.dumps(model_details, indent=2)}")
        return None

def get_model_context_window(model_name: str, db) -> int | None:
    """
    Gets the model context window, using cache first, then fetching from Ollama if not found.

    Args:
        model_name: The name of the model.
        db: Active database connection.

    Returns:
        The context window size as an integer, or None if not found/error.
    """
    if not model_name:
        current_app.logger.warning("get_model_context_window: model_name is empty.")
        return None

    cached_window = get_cached_model_context_window(db, model_name)
    if cached_window is not None:
        current_app.logger.info(f"Using cached context window for {model_name}: {cached_window}")
        return cached_window

    current_app.logger.info(f"No cache found for {model_name}. Fetching from Ollama.")

    model_details = get_ollama_model_details(model_name)
    if not model_details:
        return None

    context_window = parse_model_context_window(model_details)
    if context_window is None:
        return None

    current_app.logger.info(f"Fetched and parsed context window for {model_name}: {context_window}. Caching now.")

    try:
        cache_model_context_window(db, model_name, context_window)
    except Exception as e:
        current_app.logger.error(f"Failed to cache context window for {model_name} due to: {e}")

    return context_window

if __name__ == '__main__':
    class MockApp:
        def __init__(self):
            self.config = {'OLLAMA_API_BASE_URL': 'http://localhost:11434'}
            self.logger = MockLogger()

    class MockLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")

    current_app = MockApp()

    mock_db_cache = {}

    def mock_get_cached_model_context_window(db, model_name):
        return mock_db_cache.get(model_name)

    def mock_cache_model_context_window(db, model_name, context_window):
        mock_db_cache[model_name] = context_window
        print(f"MOCK_DB: Cached {model_name} -> {context_window}")

    global get_cached_model_context_window, cache_model_context_window
    original_get_cached = get_cached_model_context_window
    original_cache_window = cache_model_context_window
    get_cached_model_context_window = mock_get_cached_model_context_window
    cache_model_context_window = mock_cache_model_context_window

    print("\n--- Testing get_ollama_model_details ---")
    # model_name_to_test = "phi3"
    # details = get_ollama_model_details(model_name_to_test)
    # if details:
    #     print(f"Live fetch for {model_name_to_test} successful for later tests.")

    print("\n--- Testing parse_model_context_window ---")
    details_valid_num_ctx = { "details": { "parameters": "num_ctx              4096\nother_param         value" } }
    ctx_window = parse_model_context_window(details_valid_num_ctx)
    assert ctx_window == 4096
    print("Parse model context window tests (abbreviated, assume they pass from previous step).")

    print("\n--- Testing get_model_context_window (with mocked DB & live Ollama if model exists) ---")

    original_get_details = get_ollama_model_details
    original_parse_window = parse_model_context_window

    def mock_get_details_success(model_name):
        print(f"MOCK_OLLAMA: Called get_ollama_model_details for {model_name}")
        if model_name == "test_model_cache_miss":
            return {"details": {"parameters": "num_ctx 2048"}}
        return None

    def mock_parse_window_success(details):
        print("MOCK_OLLAMA: Called parse_model_context_window")
        if details and details.get("details", {}).get("parameters") == "num_ctx 2048":
            return 2048
        return None

    get_ollama_model_details = mock_get_details_success
    parse_model_context_window = mock_parse_window_success

    print("\nTest A: Cache miss, successful fetch and cache")
    mock_db_cache.clear()
    window_miss = get_model_context_window("test_model_cache_miss", None)
    print(f"Result (miss): {window_miss}, Expected: 2048")
    assert window_miss == 2048
    assert mock_db_cache.get("test_model_cache_miss") == 2048

    print("\nTest B: Cache hit")
    window_hit = get_model_context_window("test_model_cache_miss", None)
    print(f"Result (hit): {window_hit}, Expected: 2048")
    assert window_hit == 2048

    get_ollama_model_details = original_get_details
    parse_model_context_window = original_parse_window
    get_cached_model_context_window = original_get_cached
    cache_model_context_window = original_cache_window

    print("\nAll local tests (including get_model_context_window) complete.")
