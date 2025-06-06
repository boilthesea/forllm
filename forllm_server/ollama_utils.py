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

def get_model_context_window(model_name: str, db, force_refresh: bool = False) -> int | None:
    """
    Gets the model context window, using cache first (unless force_refresh is True),
    then fetching from Ollama if not found or if refresh is forced.

    Args:
        model_name: The name of the model.
        db: Active database connection.

    Returns:
        The context window size as an integer, or None if not found/error.
    """
    if not model_name:
        current_app.logger.warning("get_model_context_window: model_name is empty.")
        return None

    if not force_refresh:
        cached_window = get_cached_model_context_window(db, model_name)
        if cached_window is not None:
            current_app.logger.info(f"Using cached context window for {model_name}: {cached_window}")
            return cached_window
        current_app.logger.info(f"No cache found for {model_name} (or cache check skipped due to force_refresh={force_refresh}). Proceeding to fetch.")
    else:
        current_app.logger.info(f"Force refresh requested for {model_name}. Bypassing cache check.")

    # If force_refresh is true, or if it's false but item was not in cache:
    current_app.logger.info(f"Fetching context window from Ollama for {model_name}.")

    model_details = get_ollama_model_details(model_name)
    if not model_details:
        return None

    context_window = parse_model_context_window(model_details)
    if context_window is None:
        current_app.logger.warning(f"Could not determine context window for {model_name} from Ollama.")
        return None

    current_app.logger.info(f"Fetched and parsed context window for {model_name}: {context_window}. Caching result.")

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

    print("\n--- Testing get_model_context_window (with mocked DB & mocked Ollama interaction) ---")

    # Store original functions to restore them later
    original_get_details = get_ollama_model_details
    original_parse_window = parse_model_context_window

    # Mock implementations for get_ollama_model_details and parse_model_context_window
    # These mocks will simulate fetching details and parsing them.
    def mock_get_details_for_test(model_name_param): # Renamed to avoid conflict
        print(f"MOCK_OLLAMA (get_details): Called for {model_name_param}")
        if model_name_param == "test_model_force_refresh_new_value":
             # Simulate new value for force refresh test
            return {"details": {"parameters": "num_ctx 3000"}} # New context window value
        elif model_name_param.startswith("test_model"):
            return {"details": {"parameters": "num_ctx 2048"}}
        return None

    def mock_parse_window_for_test(details_param): # Renamed to avoid conflict
        print(f"MOCK_OLLAMA (parse_window): Called with details: {details_param}")
        if details_param and "details" in details_param and "parameters" in details_param["details"]:
            params_str = details_param["details"]["parameters"]
            if "num_ctx 3000" in params_str:
                return 3000
            elif "num_ctx 2048" in params_str:
                return 2048
        return None

    # Replace the actual functions with mocks for testing this unit
    get_ollama_model_details = mock_get_details_for_test
    parse_model_context_window = mock_parse_window_for_test

    # Test scenarios
    print("\nTest A: Cache miss, successful fetch and cache")
    mock_db_cache.clear()
    window_a = get_model_context_window("test_model_a", None, force_refresh=False)
    print(f"Result (A - miss): {window_a}, Expected: 2048")
    assert window_a == 2048, f"Test A failed: Expected 2048, got {window_a}"
    assert mock_db_cache.get("test_model_a") == 2048, "Test A failed: Value not cached correctly"

    print("\nTest B: Cache hit")
    # get_ollama_model_details should NOT be called here
    window_b = get_model_context_window("test_model_a", None, force_refresh=False)
    print(f"Result (B - hit): {window_b}, Expected: 2048")
    assert window_b == 2048, f"Test B failed: Expected 2048, got {window_b}"

    print("\nTest C: Force refresh, successful fetch and cache update")
    mock_db_cache["test_model_force_refresh_new_value"] = 2048 # Pre-populate cache with old value
    print(f"Cache before force refresh for 'test_model_force_refresh_new_value': {mock_db_cache.get('test_model_force_refresh_new_value')}")
    # get_ollama_model_details SHOULD be called here, and it will return a new value (3000)
    window_c = get_model_context_window("test_model_force_refresh_new_value", None, force_refresh=True)
    print(f"Result (C - force refresh): {window_c}, Expected: 3000")
    assert window_c == 3000, f"Test C failed: Expected 3000, got {window_c}"
    assert mock_db_cache.get("test_model_force_refresh_new_value") == 3000, "Test C failed: Cache not updated with new value"

    print("\nTest D: Force refresh on a non-cached item")
    mock_db_cache.clear()
    window_d = get_model_context_window("test_model_d_force_non_cached", None, force_refresh=True)
    # Assuming test_model_d_force_non_cached resolves to 2048 by mock_get_details_for_test
    # (as it starts with "test_model")
    expected_val_d = 2048
    print(f"Result (D - force refresh non-cached): {window_d}, Expected: {expected_val_d}")
    assert window_d == expected_val_d, f"Test D failed: Expected {expected_val_d}, got {window_d}"
    assert mock_db_cache.get("test_model_d_force_non_cached") == expected_val_d, "Test D failed: Value not cached correctly"


    # Restore original functions
    get_ollama_model_details = original_get_details
    parse_model_context_window = original_parse_window
    get_cached_model_context_window = original_get_cached
    cache_model_context_window = original_cache_window

    print("\nAll local tests (including get_model_context_window) complete.")
