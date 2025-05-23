# --- Configuration ---
DATABASE = 'forllm_data.db'
# Assume a single user for MVP
CURRENT_USER_ID = 1
CURRENT_USERNAME = "LocalUser"
# Placeholder for Ollama API endpoint
OLLAMA_BASE_URL = "http://localhost:11434" # Base Ollama URL
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags" # Endpoint to list local models
DEFAULT_MODEL = "llama3" # A sensible default

# Map Python's weekday() to short day names
DAY_MAP = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}

# --- File Uploads ---
UPLOAD_FOLDER = 'uploads'