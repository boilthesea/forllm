import json
import os
import requests
from flask import current_app # For potential future use with app_context in _call_llm
from forllm_server.config import OLLAMA_GENERATE_URL
from .database import get_subforum_details # New import

# Helper function for LLM calls
def _call_llm(prompt, model_id, flask_app): # flask_app for context, if needed later
    print(f"Calling LLM: Model '{model_id}', Prompt (start): '{prompt[:200]}...'")
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={'model': model_id, 'prompt': prompt, 'stream': False},
            headers={'Content-Type': 'application/json'},
            timeout=300  # 5 minutes, adjust as needed
        )
        response.raise_for_status()
        response_data = response.json()
        response_text = response_data.get('response', '')
        if not response_text:
            print("Warning: LLM returned empty response.")
            return {"status": "error", "error_message": "LLM returned empty response", "text": None}
        return {"status": "success", "text": response_text}
    except requests.exceptions.Timeout:
        print("Error: LLM request timed out.")
        return {"status": "error", "error_message": "LLM request timed out", "text": None}
    except requests.exceptions.RequestException as e:
        print(f"Error: LLM request failed: {e}")
        return {"status": "error", "error_message": f"LLM request failed: {str(e)}", "text": None}
    except json.JSONDecodeError:
        print("Error: Could not decode JSON response from LLM.")
        return {"status": "error", "error_message": "Invalid JSON response from LLM", "text": None}

def generate_persona_from_details(request_details, flask_app):
    generation_type = request_details.get('generation_type', 'from_name_and_description') # Default
    input_details = request_details.get('input_details', {})
    llm_model_for_generation = request_details.get('llm_model_for_generation')
    output_preferences = request_details.get('output_preferences', {})
    target_persona_name_override = request_details.get('target_persona_name_override', '')

    name_hint = input_details.get('name_hint', '')
    description_hint = input_details.get('description_hint', '')
    
    subforum_name = None
    subforum_description = None
    additional_directives = input_details.get('additional_directives', '')

    if not llm_model_for_generation:
        return {"status": "error", "error_message": "llm_model_for_generation is required."}

    if generation_type == "subforum_expert":
        subforum_id = input_details.get('subforum_id')
        if not subforum_id:
            return {"status": "error", "error_message": "Missing subforum_id for subforum_expert generation."}
        
        with flask_app.app_context(): # Ensure DB operations have app context
            sf_details = get_subforum_details(subforum_id)

        if not sf_details:
            return {"status": "error", "error_message": f"Could not retrieve details for subforum_id {subforum_id}."}
        subforum_name = sf_details['name']
        subforum_description = sf_details['description']
        
        expansion_template_name = "subforum_expert.txt"
        refinement_template_name = "subforum_expert.txt"
        print(f"Generation Type: Subforum Expert for '{subforum_name}'")
    elif generation_type == "from_name_and_description":
        expansion_template_name = "from_name_and_description.txt"
        refinement_template_name = "from_name_and_description.txt"
        print(f"Generation Type: From Name and Description (Name Hint: '{name_hint}')")
    else:
        return {"status": "error", "error_message": f"Unsupported generation_type: {generation_type}"}

    # === Stage 1: Expansion ===
    print(f"Starting Stage 1: Expansion with template '{expansion_template_name}'")
    try:
        expansion_template_path = os.path.join(
            os.path.dirname(__file__),
            'persona_prompt_templates', 'expansion', expansion_template_name
        )
        with open(expansion_template_path, 'r', encoding='utf-8') as f:
            expansion_template = f.read()
    except FileNotFoundError:
        return {"status": "error", "error_message": f"Expansion prompt template {expansion_template_name} not found."}

    expansion_prompt = expansion_template
    if generation_type == "subforum_expert":
        expansion_prompt = expansion_prompt.replace("{{subforum_name}}", subforum_name or '')
        expansion_prompt = expansion_prompt.replace("{{subforum_description}}", subforum_description or '')
        expansion_prompt = expansion_prompt.replace("{{additional_directives}}", additional_directives or '')
    elif generation_type == "from_name_and_description":
        expansion_prompt = expansion_prompt.replace("{{name_hint}}", name_hint or '')
        expansion_prompt = expansion_prompt.replace("{{description_hint}}", description_hint or '')
    
    expansion_result = _call_llm(expansion_prompt, llm_model_for_generation, flask_app) 
    if expansion_result["status"] == "error":
        return {"status": "error", "error_message": f"Expansion stage failed: {expansion_result['error_message']}", 
                "persona_name": name_hint or "Expansion Failed", 
                "prompt_instructions": expansion_result.get('text', '')}
    brainstormed_text_from_stage_1 = expansion_result["text"]
    print(f"Stage 1 (Expansion) successful. Brainstormed text length: {len(brainstormed_text_from_stage_1)}")

    # === Stage 2: Refinement ===
    print(f"Starting Stage 2: Refinement with template '{refinement_template_name}'")
    try:
        refinement_template_path = os.path.join(
            os.path.dirname(__file__),
            'persona_prompt_templates', 'refinement', refinement_template_name
        )
        with open(refinement_template_path, 'r', encoding='utf-8') as f:
            refinement_template = f.read()
    except FileNotFoundError:
        return {"status": "error", "error_message": f"Refinement prompt template {refinement_template_name} not found."}

    desired_headings = output_preferences.get('desired_headings', [])
    if isinstance(desired_headings, list) and desired_headings:
        desired_headings_str = ", ".join(desired_headings)
    else:
        desired_headings_str = "## Persona Name:,## Core Identity:,## Key Personality Traits:,## Knowledge Domain & Expertise:,## Speaking Style & Tone:,## Interaction Guidelines & Behaviors:,## Forbidden Actions & Topics:,## Example Phrases:"

    refinement_prompt = refinement_template.replace("{{brainstormed_text_from_stage_1}}", brainstormed_text_from_stage_1 or '')
    # These are in both refinement templates, so replace them regardless of type
    refinement_prompt = refinement_prompt.replace("{{name_hint}}", name_hint or '') 
    refinement_prompt = refinement_prompt.replace("{{description_hint}}", description_hint or '')

    if generation_type == "subforum_expert":
        refinement_prompt = refinement_prompt.replace("{{subforum_name}}", subforum_name or '')
        refinement_prompt = refinement_prompt.replace("{{subforum_description}}", subforum_description or '')
        refinement_prompt = refinement_prompt.replace("{{additional_directives}}", additional_directives or '')
    
    refinement_prompt = refinement_prompt.replace("{{desired_headings_list_or_default}}", desired_headings_str)
    refinement_prompt = refinement_prompt.replace("{{target_persona_name_override}}", target_persona_name_override or '')
    refinement_prompt = refinement_prompt.replace("{{tone_preference}}", output_preferences.get('tone_preference', ''))
    refinement_prompt = refinement_prompt.replace("{{length_preference}}", output_preferences.get('length_preference', ''))

    refinement_result = _call_llm(refinement_prompt, llm_model_for_generation, flask_app)
    if refinement_result["status"] == "error":
        return {"status": "error", "error_message": f"Refinement stage failed: {refinement_result['error_message']}", 
                "persona_name": name_hint or "Refinement Failed", 
                "prompt_instructions": refinement_result.get('text', '')}
    final_instructions_text = refinement_result["text"]
    print(f"Stage 2 (Refinement) successful. Final text length: {len(final_instructions_text)}")
    
    # === Parsing Final Output ===
    parsed_persona_name_successfully = False
    persona_name_to_save = target_persona_name_override  # Highest priority

    if not persona_name_to_save: # If no override
        if "## Persona Name:" in final_instructions_text:
            try:
                name_section_and_rest = final_instructions_text.split("## Persona Name:", 1)[1]
                parsed_name_from_llm = name_section_and_rest.split("##", 1)[0].strip().splitlines()[0].strip()
                if parsed_name_from_llm:
                    persona_name_to_save = parsed_name_from_llm
                    parsed_persona_name_successfully = True 
            except IndexError:
                print("Warning: Parsing '## Persona Name:' failed during name extraction.")
        
        if not persona_name_to_save: # Still no name, try hint
            persona_name_to_save = name_hint
        
        if not persona_name_to_save and generation_type == "subforum_expert" and subforum_name:
            persona_name_to_save = f"{subforum_name} Expert" # Fallback for subforum expert type

    if not persona_name_to_save: # Absolute fallback
        persona_name_to_save = "Generated Persona"

    prompt_instructions_to_save = final_instructions_text
    if parsed_persona_name_successfully and not target_persona_name_override:
        # Attempt to remove the "## Persona Name: ..." line from instructions if it was parsed and not overridden
        try:
            # More robust way to split: find first "## Persona Name:", then find the end of that line.
            # Then, find the start of the next "##" heading.
            lines = final_instructions_text.splitlines()
            name_line_index = -1
            for i, line in enumerate(lines):
                if line.strip().startswith("## Persona Name:"):
                    name_line_index = i
                    break
            
            if name_line_index != -1:
                # Find where the actual instructions start (next heading or significant content)
                instructions_start_index = -1
                for i in range(name_line_index + 1, len(lines)):
                    if lines[i].strip().startswith("## ") or lines[i].strip(): # Next heading or any non-empty line
                        instructions_start_index = i
                        break
                if instructions_start_index != -1:
                    prompt_instructions_to_save = "\n".join(lines[instructions_start_index:])
                else: # Only name was generated, or no content after name
                    prompt_instructions_to_save = "" 
            # If "## Persona Name:" was not found or structure is unexpected, prompt_instructions_to_save remains final_instructions_text
        except Exception as e:
            print(f"Minor error trying to strip parsed name from instructions: {e}")
            # Fallback: prompt_instructions_to_save remains final_instructions_text

    print(f"Final Persona Name: '{persona_name_to_save}', Instructions (start): '{prompt_instructions_to_save[:100]}...'")

    return {
        "persona_name": persona_name_to_save.strip(),
        "prompt_instructions": prompt_instructions_to_save.strip(),
        "status": "success"
    }

# Example PersonaGenerationRequest structure (for reference, if needed):
# {
#     "generation_type": "from_name_and_description" OR "subforum_expert",
#     "input_details": {
#         "name_hint": "Optional name suggestion", (used by both)
#         "description_hint": "Few sentences or keywords" (used by from_name_and_description)
#         "subforum_id": 123, (used by subforum_expert)
#         "additional_directives": "Focus on X, Y, Z." (used by subforum_expert)
#     },
#     "output_preferences": { 
#         "desired_headings": ["## Persona Name:", "## Core Identity:", ...], 
#         "tone_preference": "witty", 
#         "length_preference": "concise" 
#     },
#     "target_persona_name_override": "Specific Name", 
#     "llm_model_for_generation": "model_identifier"
# }
