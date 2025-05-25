import json
import os
import requests # Added
from flask import current_app
# from forllm_server.llm_processing import process_llm_request # Not directly used now
from forllm_server.config import OLLAMA_GENERATE_URL # Added

# Placeholder for actual LLM call, similar to process_llm_request
# For MVP, we might simplify this and not use all parts of process_llm_request directly
# but rather adapt its core logic for sending a prompt and getting a response.

def generate_persona_from_details(request_details, flask_app):
    """
    Generates persona instructions based on name and description hints.
    MVP: Uses a simplified, single-stage LLM call.
    """
    generation_type = request_details.get('generation_type')
    input_details = request_details.get('input_details', {})
    llm_model_for_generation = request_details.get('llm_model_for_generation')

    name_hint = input_details.get('name_hint', '')
    description_hint = input_details.get('description_hint', '')

    # Construct the MVP prompt
    # For MVP, load from a simple template file
    prompt_template_path = os.path.join(
        os.path.dirname(__file__),
        'persona_prompt_templates',
        'mvp',
        'basic_enhancement.txt'
    )

    try:
        with open(prompt_template_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        # Fallback if template is missing, though it should be created
        prompt_template = "Persona Name: {{name_hint}}\n\nCore Identity: Based on {{description_hint}}, expand this.\n\nSpeaking Style: Be helpful."
        print(f"Warning: Prompt template not found at {prompt_template_path}. Using basic fallback.")


    prompt = prompt_template.replace("{{name_hint}}", name_hint).replace("{{description_hint}}", description_hint)

    # Make the LLM call (simplified for MVP)
    # This part needs to be adapted from llm_processing.py's call to Ollama
    # For now, let's assume a function that takes a prompt and returns text
    # In a real scenario, this would involve requests.post to Ollama, error handling, etc.
    
    # ----- Actual LLM Call -----
    print(f"Sending persona generation prompt to LLM ({OLLAMA_GENERATE_URL}) for model '{llm_model_for_generation}'...")
    llm_response_text = None
    error_message_for_status = None

    try:
        # For MVP, a non-streaming call is simpler to implement here
        response = requests.post(
            OLLAMA_GENERATE_URL, # Ensure this is correctly configured
            json={'model': llm_model_for_generation, 'prompt': prompt, 'stream': False}, # stream=False for simpler MVP
            headers={'Content-Type': 'application/json'},
            timeout=300 # Adjust timeout as needed
        )
        response.raise_for_status() # Will raise HTTPError for bad responses (4xx or 5xx)

        response_data = response.json()
        llm_response_text = response_data.get('response', '')

        if not llm_response_text:
            print("Warning: LLM response was empty.")
            # llm_response_text = "Error: LLM returned an empty response." # Or handle as error
            error_message_for_status = "LLM returned empty response"
            # If LLM response is empty, we might not want to proceed with parsing.
            # Setting llm_response_text to an error message or just returning early.
            # For now, let's ensure it goes to the error return path.

    except requests.exceptions.Timeout:
        print("Error: LLM request timed out.")
        # llm_response_text = "Error: LLM request timed out." # This will be set by the error return
        error_message_for_status = "LLM request timed out"
    except requests.exceptions.RequestException as e:
        print(f"Error: LLM request failed: {e}")
        # llm_response_text = f"Error: LLM request failed: {e}" # This will be set by the error return
        error_message_for_status = f"LLM request failed: {str(e)}"
    except json.JSONDecodeError:
        print("Error: Could not decode JSON response from LLM.")
        # llm_response_text = "Error: Could not decode JSON response from LLM." # This will be set by the error return
        error_message_for_status = "Invalid JSON response from LLM"

    if error_message_for_status:
        # Ensure llm_response_text has some content for the error case,
        # potentially the error message itself if no other text is available.
        error_display_text = llm_response_text if llm_response_text else f"Error: {error_message_for_status}"
        return {
            "persona_name": name_hint or "Generation Failed",
            "prompt_instructions": error_display_text, # Contains the error message or original empty response
            "status": "error",
            "error_message": error_message_for_status
        }
    
    # Parse the LLM response (MVP assumes a simple structure)
    # If we reached here, llm_response_text should be valid (not None, not an error itself)
    persona_name = name_hint or "Generated Persona" # Default if not in response
    prompt_instructions = llm_response_text

    # Extract persona name from response if possible (simple parsing for MVP)
    if "## Persona Name:" in llm_response_text:
        try:
            name_section = llm_response_text.split("## Persona Name:")[1].split("##")[0].strip()
            if name_section:
                persona_name = name_section.split('\n')[0].strip()
        except IndexError:
            pass # Keep default

    # Remove the Persona Name section from the instructions if it was parsed
    if persona_name != (name_hint or "Generated Persona"): # if name was successfully parsed
         prompt_instructions = llm_response_text.split("## Persona Name:")[1].split("##", 1)[1]
         prompt_instructions = "##" + prompt_instructions # Add back the first '##' for the next section

    print(f"Generated persona: Name='{persona_name}', Instructions='{prompt_instructions[:100]}...'")

    return {
        "persona_name": persona_name,
        "prompt_instructions": prompt_instructions.strip(),
        "status": "success" # Assuming success for MVP simulation
    }

# Example PersonaGenerationRequest structure (for reference):
# {
#     "generation_type": "from_name_and_description",
#     "input_details": {
#         "name_hint": "Optional name suggestion",
#         "description_hint": "Few sentences or keywords"
#     },
#     "llm_model_for_generation": "model_identifier"
# }
