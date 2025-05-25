import json
import os
import requests
from flask import current_app # For potential future use with app_context in _call_llm
from forllm_server.config import OLLAMA_GENERATE_URL

# Helper function for LLM calls
def _call_llm(prompt, model_id, flask_app): # flask_app for context, if needed later
    print(f"Calling LLM: Model '{model_id}', Prompt (start): '{prompt[:200]}...'") # Increased preview length
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
    input_details = request_details.get('input_details', {})
    llm_model_for_generation = request_details.get('llm_model_for_generation')
    # output_preferences are read but specific handling for desired_headings is deferred as per prompt
    output_preferences = request_details.get('output_preferences', {}) 
    target_persona_name_override = request_details.get('target_persona_name_override', '')

    name_hint = input_details.get('name_hint', '')
    description_hint = input_details.get('description_hint', '')

    if not llm_model_for_generation:
        # This case should ideally be handled by the route before queueing,
        # but as a safeguard:
        print("Error: llm_model_for_generation is missing.")
        return {"status": "error", "error_message": "llm_model_for_generation is required."}

    # === Stage 1: Expansion ===
    print("Starting Stage 1: Expansion")
    try:
        expansion_template_path = os.path.join(
            os.path.dirname(__file__),
            'persona_prompt_templates', 'expansion', 'from_name_and_description.txt'
        )
        with open(expansion_template_path, 'r', encoding='utf-8') as f:
            expansion_template = f.read()
    except FileNotFoundError:
        print(f"Error: Expansion prompt template not found at {expansion_template_path}")
        return {"status": "error", "error_message": "Expansion prompt template not found."}

    expansion_prompt = expansion_template.replace("{{name_hint}}", name_hint).replace("{{description_hint}}", description_hint)
    
    expansion_result = _call_llm(expansion_prompt, llm_model_for_generation, flask_app) 
    if expansion_result["status"] == "error":
        return {
            "status": "error", 
            "error_message": f"Expansion stage failed: {expansion_result['error_message']}", 
            "persona_name": name_hint or "Expansion Failed", # Provide some context
            "prompt_instructions": expansion_result.get('text', '') # Return error text if available
        }
    brainstormed_text_from_stage_1 = expansion_result["text"]
    print(f"Stage 1 (Expansion) successful. Brainstormed text length: {len(brainstormed_text_from_stage_1)}")

    # === Stage 2: Refinement ===
    print("Starting Stage 2: Refinement")
    try:
        refinement_template_path = os.path.join(
            os.path.dirname(__file__),
            'persona_prompt_templates', 'refinement', 'from_name_and_description.txt'
        )
        with open(refinement_template_path, 'r', encoding='utf-8') as f:
            refinement_template = f.read()
    except FileNotFoundError:
        print(f"Error: Refinement prompt template not found at {refinement_template_path}")
        return {"status": "error", "error_message": "Refinement prompt template not found."}

    # Prepare output_preferences for template
    desired_headings = output_preferences.get('desired_headings', []) 
    
    if isinstance(desired_headings, list) and desired_headings:
        # Format as a comma-separated string for the prompt.
        # The prompt template should instruct the LLM to use these as the primary headings.
        desired_headings_str = ", ".join(desired_headings)
        # Example of how the prompt template might need to be phrased:
        # "Use the following comma-separated list of headings for your output structure: {{desired_headings_list_or_default}}. If this list is empty or not provided, use your default set of headings."
        print(f"Using custom desired_headings: {desired_headings_str}")
    else:
        # Fallback to default list string if empty or not a list
        desired_headings_str = "## Persona Name:,## Core Identity:,## Key Personality Traits:,## Knowledge Domain & Expertise:,## Speaking Style & Tone:,## Interaction Guidelines & Behaviors:,## Forbidden Actions & Topics:,## Example Phrases:"
        print(f"Using default desired_headings: {desired_headings_str}")

    refinement_prompt = refinement_template.replace("{{brainstormed_text_from_stage_1}}", brainstormed_text_from_stage_1)
    refinement_prompt = refinement_prompt.replace("{{name_hint}}", name_hint)
    refinement_prompt = refinement_prompt.replace("{{description_hint}}", description_hint)
    # This line is the key change for desired_headings:
    refinement_prompt = refinement_prompt.replace("{{desired_headings_list_or_default}}", desired_headings_str) 
    refinement_prompt = refinement_prompt.replace("{{target_persona_name_override}}", target_persona_name_override)
    refinement_prompt = refinement_prompt.replace("{{tone_preference}}", output_preferences.get('tone_preference', ''))
    refinement_prompt = refinement_prompt.replace("{{length_preference}}", output_preferences.get('length_preference', ''))
    # Note: llm_model_for_generation is not a placeholder in the refinement prompt template provided.

    refinement_result = _call_llm(refinement_prompt, llm_model_for_generation, flask_app)
    if refinement_result["status"] == "error":
        return {
            "status": "error", 
            "error_message": f"Refinement stage failed: {refinement_result['error_message']}", 
            "persona_name": name_hint or "Refinement Failed", # Provide some context
            "prompt_instructions": refinement_result.get('text', '')
        }
    final_instructions_text = refinement_result["text"]
    print(f"Stage 2 (Refinement) successful. Final text length: {len(final_instructions_text)}")
    
    # === Parsing Final Output ===
    # Priority: Override > Parsed from LLM (if not overridden) > Name Hint > Default
    persona_name = target_persona_name_override # Highest priority

    if not persona_name: # If no override, try to parse or use hint
        # Attempt to parse from LLM output
        parsed_llm_name = None
        if "## Persona Name:" in final_instructions_text:
            try:
                name_section_and_rest = final_instructions_text.split("## Persona Name:", 1)[1]
                parsed_llm_name = name_section_and_rest.split("##", 1)[0].strip().splitlines()[0].strip()
            except IndexError:
                print("Warning: Parsing '## Persona Name:' failed during name extraction.")
        
        if parsed_llm_name:
            persona_name = parsed_llm_name
        elif name_hint:
            persona_name = name_hint
        else:
            persona_name = "Generated Persona" # Fallback default

    prompt_instructions = final_instructions_text
    # If a name was parsed from the LLM output AND there was no override,
    # we might want to remove the "## Persona Name: ..." section from the instructions.
    # This logic is a bit simplified from the original single-stage parsing.
    if not target_persona_name_override and "## Persona Name:" in final_instructions_text:
        try:
            # This assumes the "## Persona Name:" line is at the beginning if present.
            split_by_name_heading = final_instructions_text.split("## Persona Name:", 1)
            if len(split_by_name_heading) > 1:
                name_section_and_rest = split_by_name_heading[1]
                # Further split to isolate the name itself and the rest of the content
                parts = name_section_and_rest.split("##", 1)
                if len(parts) > 1: # Check if there is content after the name section
                    # This means there was a "## Persona Name: actual_name ## Next Heading" structure
                    prompt_instructions = "##" + parts[1].strip() # Keep the "##" for the next heading
                else: 
                    # This means "## Persona Name: actual_name" was the only thing, or the last thing.
                    # If it's the only thing, instructions might become empty.
                    # If it implies the rest of the text _is_ the name, this is problematic.
                    # For now, if no "##" follows the name, assume the rest is instructions
                    # but this part of parsing could be fragile.
                    # A robust approach might be to rely on the LLM to *not* include the name line
                    # if it's told to generate instructions based on a name it's also generating.
                    # For now, let's assume the name section is distinct.
                    # If the text _only_ contained "## Persona Name: Foobar", prompt_instructions would become empty here.
                    # This is unlikely if the prompt asks for multiple sections.
                    # A simple fix: if parts[1] is empty, means name was last.
                    # In that case, don't strip. Instructions are the whole text.
                    # The current logic is: if "##NextHeading" exists, strip name section.
                    # If not, prompt_instructions remains final_instructions_text.
                    pass # Keep prompt_instructions as final_instructions_text
        except Exception as e:
            print(f"Warning: Error during final parsing of prompt_instructions: {e}")
            # Fallback: prompt_instructions remains final_instructions_text

    print(f"Final Persona Name: '{persona_name}', Instructions (start): '{prompt_instructions[:100]}...'")

    return {
        "persona_name": persona_name.strip(), # Ensure name is stripped
        "prompt_instructions": prompt_instructions.strip(),
        "status": "success"
    }

# Example PersonaGenerationRequest structure (for reference, if needed):
# {
#     "generation_type": "from_name_and_description", // Or other types later
#     "input_details": {
#         "name_hint": "Optional name suggestion",
#         "description_hint": "Few sentences or keywords"
#     },
#     "output_preferences": { // Optional
#         "desired_headings": ["## Persona Name:", "## Core Identity:", ...], // For future full handling
#         "tone_preference": "witty", 
#         "length_preference": "concise" 
#     },
#     "target_persona_name_override": "Specific Name", // Optional
#     "llm_model_for_generation": "model_identifier" // Should be validated before this point
# }
