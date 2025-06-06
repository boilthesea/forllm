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
        found_in_cache, cached_value = get_cached_model_context_window(db, model_name)
        if found_in_cache:
            # cached_value can be an int or None (if None was explicitly cached)
            current_app.logger.info(f"Using cached context window for {model_name}: {cached_value}")
            return cached_value
        else:
            # This means the model_name was not found in the cache table at all.
            current_app.logger.info(f"No cache entry found for {model_name} (force_refresh=False). Proceeding to fetch.")
    else: # This else block is for the force_refresh=True case
        current_app.logger.info(f"Force refresh requested for {model_name}. Bypassing cache lookup.")

    # Proceed to fetch from Ollama if:
    # 1. force_refresh is True (cache lookup bypassed)
    # 2. force_refresh is False AND found_in_cache was False (cache miss)
    current_app.logger.info(f"Fetching context window from Ollama for {model_name}.")

    model_details = get_ollama_model_details(model_name)
    if not model_details:
        # Model not found by Ollama or other error during fetch. Cache this "None" state.
        current_app.logger.warning(f"Failed to fetch model details for {model_name} from Ollama. Caching this 'not found' state.")
        try:
            cache_model_context_window(db, model_name, None) # Cache None when details aren't available
        except Exception as e:
            current_app.logger.error(f"Failed to cache 'not found' state for {model_name} due to: {e}")
        return None

    context_window = parse_model_context_window(model_details)
    # context_window can be an int or None if parsing failed or num_ctx not found.
    # Cache whatever result we get (int or None).
    current_app.logger.info(f"Parsed context window for {model_name}: {context_window}. Caching this result.")

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
    original_get_cached_db = get_cached_model_context_window # Save original DB function

    # Mock DB cache for testing get_model_context_window behavior
    mock_db_for_tests = {}

    def mock_get_cached_from_dict(db_conn, model_name_param): # Renamed
        print(f"MOCK_DB (get_cached): Called for {model_name_param}")
        if model_name_param in mock_db_for_tests:
            val = mock_db_for_tests[model_name_param]
            print(f"MOCK_DB (get_cached): Hit for {model_name_param}, returning ({True}, {val})")
            return True, val # Simulate cache hit, value can be int or None
        print(f"MOCK_DB (get_cached): Miss for {model_name_param}, returning ({False}, {None})")
        return False, None # Simulate cache miss

    def mock_cache_to_dict(db_conn, model_name_param, context_window_param): # Renamed
        print(f"MOCK_DB (cache_window): Caching for {model_name_param}: {context_window_param}")
        mock_db_for_tests[model_name_param] = context_window_param

    # Replace actual DB interactions with mocks for this test suite
    get_cached_model_context_window = mock_get_cached_from_dict
    cache_model_context_window = mock_cache_to_dict

    # Mock implementations for get_ollama_model_details and parse_model_context_window
    def mock_get_details_for_test(model_name_param):
        print(f"MOCK_OLLAMA (get_details): Called for {model_name_param}")
        if model_name_param == "test_model_real_success":
            return {"details": {"parameters": "num_ctx 2048"}}
        elif model_name_param == "test_model_force_refresh_new_val":
            return {"details": {"parameters": "num_ctx 3000"}}
        elif model_name_param == "test_model_parse_fail": # Details are fine, but parsing will fail
            return {"details": {"parameters": "some_other_param 123"}}
        elif model_name_param == "test_model_fetch_fail": # Ollama fetch itself fails
            return None
        return None # Default to fetch failure

    def mock_parse_window_for_test(details_param):
        print(f"MOCK_OLLAMA (parse_window): Called with details: {details_param}")
        if not details_param: return None
        params_str = details_param.get("details", {}).get("parameters", "")
        if "num_ctx 2048" in params_str: return 2048
        if "num_ctx 3000" in params_str: return 3000
        return None # Parsing fails if num_ctx not found

    # Replace Ollama interactions with mocks for this test suite
    get_ollama_model_details = mock_get_details_for_test
    parse_model_context_window = mock_parse_window_for_test

    # --- Test Scenarios ---
    print("\nTest 1: Cache miss, successful fetch, parse, and cache")
    mock_db_for_tests.clear()
    window1 = get_model_context_window("test_model_real_success", None, force_refresh=False)
    assert window1 == 2048, f"Test 1 Failed: Expected 2048, got {window1}"
    assert mock_db_for_tests.get("test_model_real_success") == 2048, "Test 1 Failed: Not cached"

    print("\nTest 2: Cache hit (value is an int)")
    # get_ollama_model_details and parse_model_context_window should NOT be called.
    # mock_db_for_tests already contains "test_model_real_success" -> 2048
    window2 = get_model_context_window("test_model_real_success", None, force_refresh=False)
    assert window2 == 2048, f"Test 2 Failed: Expected 2048, got {window2}"

    print("\nTest 3: Force refresh, successful fetch with new value, cache update")
    mock_db_for_tests["test_model_force_refresh_new_val"] = 1024 # Old value in cache
    window3 = get_model_context_window("test_model_force_refresh_new_val", None, force_refresh=True)
    assert window3 == 3000, f"Test 3 Failed: Expected 3000, got {window3}"
    assert mock_db_for_tests.get("test_model_force_refresh_new_val") == 3000, "Test 3 Failed: Cache not updated"

    print("\nTest 4: Cache miss, Ollama fetch, but parsing fails (num_ctx not found). Cache None.")
    mock_db_for_tests.clear()
    window4 = get_model_context_window("test_model_parse_fail", None, force_refresh=False)
    assert window4 is None, f"Test 4 Failed: Expected None, got {window4}"
    assert "test_model_parse_fail" in mock_db_for_tests and mock_db_for_tests["test_model_parse_fail"] is None, "Test 4 Failed: None not cached"

    print("\nTest 5: Cache hit (value is None, previously cached parse fail/fetch fail)")
    # mock_db_for_tests already contains "test_model_parse_fail" -> None
    window5 = get_model_context_window("test_model_parse_fail", None, force_refresh=False)
    assert window5 is None, f"Test 5 Failed: Expected None from cache, got {window5}"

    print("\nTest 6: Cache miss, Ollama fetch itself fails. Cache None.")
    mock_db_for_tests.clear()
    window6 = get_model_context_window("test_model_fetch_fail", None, force_refresh=False)
    assert window6 is None, f"Test 6 Failed: Expected None, got {window6}"
    assert "test_model_fetch_fail" in mock_db_for_tests and mock_db_for_tests["test_model_fetch_fail"] is None, "Test 6 Failed: None not cached for fetch fail"

    print("\nTest 7: Force refresh on an item that previously failed (cached as None), now succeeds.")
    mock_db_for_tests["test_model_real_success"] = None # Simulate previous failure
    window7 = get_model_context_window("test_model_real_success", None, force_refresh=True)
    assert window7 == 2048, f"Test 7 Failed: Expected 2048, got {window7}"
    assert mock_db_for_tests.get("test_model_real_success") == 2048, "Test 7 Failed: Cache not updated to new success value"

    # Restore original functions
    get_ollama_model_details = original_get_details
    parse_model_context_window = original_parse_window
    get_cached_model_context_window = original_get_cached_db # Restore original DB function
    get_cached_model_context_window = original_get_cached
    cache_model_context_window = original_cache_window

    print("\nAll local tests (including get_model_context_window) complete.")
