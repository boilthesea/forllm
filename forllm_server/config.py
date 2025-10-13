# --- Configuration ---
DATABASE = 'forllm_data.db'
# Assume a single user for MVP
CURRENT_USER_ID = 1
CURRENT_USERNAME = "LocalUser"
# Placeholder for Ollama API endpoint
OLLAMA_BASE_URL = "http://localhost:11434" # Base Ollama URL
# OLLAMA_API_BASE_URL is used by ollama_utils to fetch model details
OLLAMA_API_BASE_URL = 'http://localhost:11434'
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags" # Endpoint to list local models
DEFAULT_MODEL = "llama3" # A sensible default

# Map Python's weekday() to short day names
DAY_MAP = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}

# --- File Uploads ---
UPLOAD_FOLDER = 'uploads'

# --- Prompt Engineering ---
DEFAULT_OPTIMIZER_PROMPT = """
You are a helpful AI assistant specializing in prompt engineering. Your task is to take a user's simple or vague prompt and rewrite it into a more detailed, effective prompt that will generate a high-quality result from a text-to-image model like Stable Diffusion.
Focus on adding descriptive details, specifying the style, composition, lighting, and artistic medium. Use strong keywords that are known to work well with image generation models.
The user's original prompt will be provided below. You must only return the rewritten prompt and nothing else. Do not add any conversational text, greetings, or explanations.
"""