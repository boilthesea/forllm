**Dynamic Persona Generation Engine**. This design will incorporate:

1.  Targeting smaller, local LLMs.
2.  Prioritizing structured natural language for the final persona instructions.
3.  A multi-stage backend generation process (Expansion & Refinement).
4.  Flexibility for different frontend contexts to specify inputs and desired output characteristics (like heading emphasis).

The goal is to produce a comprehensive document that details this module's design.

---

**Design Specification: Dynamic Persona Generation Engine for FORLLM**

**1. Introduction & Goals**

This document outlines the design for a Dynamic Persona Generation Engine within the FORLLM project. The primary goal of this engine is to enable users to provide minimal input (e.g., a name, a few keywords, or subforum details) and have FORLLM, through a series of LLM interactions, generate rich, detailed, and highly usable natural language persona instructions.

These generated instructions are specifically tailored to be effective as system prompts or custom instructions for smaller, locally-run LLMs, which are the primary target for FORLLM. The engine aims for:

*   **Richness from Scarcity:** Transform sparse user input into detailed persona descriptions.
*   **Digestibility for Small LLMs:** Produce persona instructions that are clear, concise, and easily understood by models with limited capacity.
*   **Consistency & Quality:** Ensure a reliable standard of persona generation.
*   **Flexibility & Reusability:** Allow the engine to be called from various frontend contexts with different input parameters and output nuances.
*   **Asynchronous Operation:** Integrate seamlessly with FORLLM's existing asynchronous LLM request queue.

**2. Core Component: Persona Generation Module**

A dedicated Python module, `forllm_server/persona_generator.py`, will encapsulate the core logic for persona generation. This module will be independent of specific frontend use cases or API endpoint implementations.

**2.1. Input Structure**

The module will accept a dictionary or a dedicated data class (`PersonaGenerationRequest`) with the following fields:

*   `generation_type`: (String, Required) Defines the context and primary input for generation (e.g., "from_name_and_description", "subforum_expert", "general_purpose_assistant"). This dictates the initial backend prompt templates used.
*   `input_details`: (Dictionary, Required) Contains the primary user-provided information. The structure varies based on `generation_type`:
    *   For `generation_type="from_name_and_description"`:
        *   `name_hint`: (String, Optional) A suggested name (e.g., "Albert Einstein").
        *   `description_hint`: (String, Optional) User-provided keywords, sentences, or core concepts (e.g., "Explains complex physics simply, slightly eccentric").
    *   For `generation_type="subforum_expert"`:
        *   `subforum_name`: (String, Required) The name of the subforum.
        *   `subforum_description`: (String, Required) The description of the subforum.
        *   `additional_directives`: (String, Optional) User-provided specifics for the expert (e.g., "Focus on practical applications and beginner-friendly explanations").
*   `output_preferences`: (Dictionary, Optional) Allows the calling context (frontend) to influence the final output.
    *   `desired_headings`: (List of Strings, Optional) A list of preferred section headings for the final natural language persona instructions (e.g., `["Core Identity", "Speaking Style", "Key Knowledge Areas", "Forbidden Actions"]`). If not provided, a default set of comprehensive headings will be used.
    *   `tone_preference`: (String, Optional) e.g., "formal", "casual", "witty".
    *   `length_preference`: (String, Optional) e.g., "concise", "detailed". (This is a soft hint to the LLM).
*   `llm_model_for_generation`: (String, Required) The identifier for the LLM model to be used for *this generation task* (can be different from models used by personas).
*   `target_persona_name_override`: (String, Optional) If the user wants to pre-define the exact name of the persona to be generated, otherwise the system will attempt to generate or refine one.

**2.2. Internal Generation Process (Multi-Stage LLM Interaction)**

The core of the module will implement a two-stage LLM-driven process to transform the input into the final persona instructions. This process is orchestrated internally and is not directly exposed as separate steps to the user or API.

**Stage 1: Expansion & Brainstorming**

*   **Objective:** To take the initial sparse `input_details` and use an LLM to generate a broad range of ideas, details, and creative elaborations related to the desired persona.
*   **Process:**
    1.  **Select Expansion Prompt Template:** Based on the `generation_type`, an "Expansion Prompt Template" is chosen (e.g., from `forllm_server/persona_prompt_templates/expansion/subforum_expert.txt`).
    2.  **Populate Template:** The template is populated with `input_details`.
    3.  **Construct Expansion Prompt:**
        *   **Role:** "You are a highly creative and knowledgeable assistant. Your task is to brainstorm and expand extensively on the following concept for an AI persona."
        *   **Input:** "You will receive: [Placeholders for `name_hint`, `description_hint`, `subforum_name`, etc.]."
        *   **Task:** "Generate a rich, detailed, and imaginative text exploring various facets of this persona. Consider:
            *   Potential background or origin stories.
            *   Key personality traits, quirks, and motivations.
            *   Specific knowledge domains and areas of expertise.
            *   Possible speaking styles, tones, and common phrases.
            *   Goals or objectives the persona might have.
            *   Potential limitations or areas of ignorance.
            *   If for a subforum, deeply integrate the `{{subforum_name}}` and `{{subforum_description}}` into all aspects.
            *   If `{{additional_directives}}` are provided, ensure they are central to your brainstorming."
        *   **Output Instruction:** "Produce a comprehensive, free-form text. Do not worry about conciseness at this stage; focus on generating a wealth of creative material. Aim for [target word count hint, e.g., 300-500 words]."
    4.  **LLM Call:** The constructed Expansion Prompt is sent to the `llm_model_for_generation` via `llm_processing.py`.
    5.  **Store Intermediate Output:** The raw text output from this stage is stored temporarily.

**Stage 2: Refinement & Structuring for Digestibility**

*   **Objective:** To take the verbose output from Stage 1 and use an LLM to distill it into a clear, concise, and actionable set of natural language persona instructions, specifically structured for effectiveness with smaller LLMs.
*   **Process:**
    1.  **Select Refinement Prompt Template:** Based on the `generation_type`, a "Refinement Prompt Template" is chosen (e.g., from `forllm_server/persona_prompt_templates/refinement/standard_persona.txt`).
    2.  **Populate Template:** The template is populated with the output from Stage 1 and relevant fields from `input_details` and `output_preferences`.
    3.  **Construct Refinement Prompt:**
        *   **Role:** "You are an expert AI persona instruction writer. Your task is to refine a detailed brainstormed text into a clear, structured, and highly effective set of natural language instructions for guiding a smaller AI model. These instructions will serve as its primary persona definition."
        *   **Input:** "You will be given:
            1.  A 'Brainstormed Text' containing rich ideas for a persona: `{{brainstormed_text_from_stage_1}}`.
            2.  Original user hints (if any): `{{original_input_details_summary}}`.
            3.  (Optional) Preferred output headings: `{{desired_headings_list_or_default}}`.
            4.  (Optional) Desired persona name: `{{target_persona_name_override}}`."
        *   **Task:** "Analyze the 'Brainstormed Text' and user hints. Then, generate a final set of persona instructions. The instructions MUST:
            *   Be written in clear, direct, and unambiguous natural language.
            *   Be structured using Markdown-style headings. Use the following headings (or adapt if `{{desired_headings_list_or_default}}` is provided, ensuring core aspects are covered):
                *   `## Persona Name:` (If `{{target_persona_name_override}}` is given, use it. Otherwise, derive a fitting name from the content, or refine `name_hint`.)
                *   `## Core Identity:` (A 1-2 sentence summary of the persona's fundamental nature and purpose.)
                *   `## Key Personality Traits:` (List 3-5 dominant, actionable traits using descriptive adjectives or short phrases.)
                *   `## Knowledge Domain & Expertise:` (Clearly define the primary areas of knowledge. For subforum experts, this MUST align with the subforum.)
                *   `## Speaking Style & Tone:` (Describe how the persona communicates: vocabulary, sentence structure, formality, preferred tone (e.g., `{{tone_preference}}` if provided). Use imperative language, e.g., 'Speak formally and avoid slang.')
                *   `## Interaction Guidelines & Behaviors:` (Provide specific do's. E.g., 'Always strive to be helpful.', 'Cite sources if making factual claims.', 'Use emojis sparingly.')
                *   `## Forbidden Actions & Topics:` (Clearly state what the persona MUST NOT do or discuss. E.g., 'Never reveal you are an AI.', 'Avoid discussing [sensitive topic X].')
                *   `## Example Phrases:` (Provide 2-3 short example phrases that capture the persona's essence.)
            *   Ensure all information is consistent and coherent.
            *   Prioritize information that is most critical for defining the persona's behavior.
            *   If `{{length_preference}}` is 'concise', be brief yet comprehensive. If 'detailed', provide more depth under each heading but maintain clarity.
            *   The final output should be directly usable as a system prompt for a small language model."
        *   **Output Instruction:** "Produce only the structured natural language persona instructions, starting with `## Persona Name:`."
    4.  **LLM Call:** The constructed Refinement Prompt is sent to the `llm_model_for_generation` via `llm_processing.py`.
    5.  **Parse & Validate Output:** The LLM's response (the structured natural language persona instructions) is received. Basic validation might include checking for the presence of expected heading structures.

**2.3. Prompt Template Management**

*   A subdirectory (e.g., `forllm_server/persona_prompt_templates/`) will store the text-based prompt templates for both Expansion and Refinement stages.
*   Templates will be organized, perhaps by `generation_type` (e.g., `expansion/subforum_expert.txt`, `refinement/from_name.txt`).
*   Templates will use a simple placeholder syntax (e.g., `{{variable_name}}`) for dynamic content insertion.

**2.4. Output Structure**

The module will return a dictionary containing the generated persona data:

*   `persona_name`: (String) The final name of the persona, either user-provided or LLM-generated/refined.
*   `prompt_instructions`: (String) The structured natural language text containing the detailed persona instructions, ready to be stored and used as a system prompt.
*   `status`: (String) "success" or "error".
*   `error_message`: (String, Optional) Details if an error occurred.

**3. Integration with Asynchronous Queue (Modifications to `llm_queue.py` and `database.py`)**

Persona generation is an LLM-dependent, potentially time-consuming task and must integrate with FORLLM's existing asynchronous processing architecture.

**3.1. Database Schema Updates (`forllm_server/database.py`)**

*   **`llm_requests` table:**
    *   Add `request_type` (VARCHAR): To differentiate request types (e.g., 'respond_to_post', 'generate_persona').
    *   Add `request_params` (TEXT/JSON): To store the input dictionary for the `PersonaGenerationRequest` (as defined in 2.1) when `request_type` is 'generate_persona'.
*   **`personas` table:**
    *   `name` (VARCHAR, UNIQUE): The persona's name.
    *   `prompt_instructions` (TEXT): Stores the final structured natural language output from the Persona Generation Module.
    *   `generation_source` (VARCHAR, Optional): e.g., 'user_manual', 'llm_generated_from_name', 'llm_generated_subforum_expert'.
    *   `generation_input_details` (TEXT/JSON, Optional): Stores a copy of the `input_details` (from 2.1) that led to this persona's generation, for traceability.
    *   (Other existing fields like `created_at`, `updated_at`, `created_by_user_id` remain).
*   **`persona_versions` table:**
    *   Will continue to store historical versions of `prompt_instructions` and other relevant persona fields.

**3.2. Queue and Worker Modifications (`forllm_server/llm_queue.py`)**

*   **Queueing a Persona Generation Request:**
    *   When an API endpoint receives a persona generation request, it will construct the `PersonaGenerationRequest` input dictionary.
    *   A new entry will be added to the `llm_requests` table with:
        *   `request_type = 'generate_persona'`
        *   `request_params = <JSON string of PersonaGenerationRequest input>`
        *   `status = 'pending'`
        *   `llm_model = <llm_model_for_generation from PersonaGenerationRequest>`
*   **`llm_worker` Function Update:**
    *   The worker will check the `request_type` of dequeued jobs.
    *   If `request_type == 'generate_persona'`:
        1.  Deserialize `request_params` into the `PersonaGenerationRequest` structure.
        2.  Call the main function of the `Persona Generation Module` (`persona_generator.py`) with these parameters.
        3.  If generation is successful:
            *   Save the new persona ( `persona_name`, `prompt_instructions`, `generation_source`, `generation_input_details`) to the `personas` table (and create an initial entry in `persona_versions`) using database functions from `database.py`.
            *   Update the `llm_requests` status to 'complete'.
        4.  If generation fails:
            *   Log the error.
            *   Update the `llm_requests` status to 'error' and store an error message if available.

**4. API Endpoints (New or Modified in `forllm_server/routes/`)**

New API endpoints will be created, likely in a new `forllm_server/routes/persona_routes.py` or integrated into `settings_routes.py`.

*   **`POST /api/personas/generate/from_details`**
    *   **Request Body (JSON):**
        ```json
        {
            "name_hint": "Optional name suggestion",
            "description_hint": "Few sentences or keywords",
            "output_preferences": { /* see 2.1 */ },
            "llm_model_for_generation": "model_identifier",
            "target_persona_name_override": "Optional fixed name"
        }
        ```
    *   **Action:**
        1.  Constructs `PersonaGenerationRequest` with `generation_type="from_name_and_description"`.
        2.  Queues the request in `llm_requests`.
    *   **Response:** `202 Accepted` with request ID, or error.

*   **`POST /api/personas/generate/subforum_expert`**
    *   **Request Body (JSON):**
        ```json
        {
            "subforum_id": "id_of_the_subforum",
            "additional_directives": "Optional user specifics for the expert",
            "output_preferences": { /* see 2.1 */ },
            "llm_model_for_generation": "model_identifier",
            "target_persona_name_override": "Optional fixed name"
        }
        ```
    *   **Action:**
        1.  Backend fetches `subforum_name` and `subforum_description` using `subforum_id`.
        2.  Constructs `PersonaGenerationRequest` with `generation_type="subforum_expert"`.
        3.  Queues the request in `llm_requests`.
    *   **Response:** `202 Accepted` with request ID, or error.

*   **`POST /api/personas/generate/subforum_experts_batch`** (For generating multiple experts for one subforum)
    *   **Request Body (JSON):**
        ```json
        {
            "subforum_id": "id_of_the_subforum",
            "number_to_generate": 3,
            "additional_directives_global": "Optional specifics applying to all generated experts",
            "output_preferences": { /* see 2.1 */ },
            "llm_model_for_generation": "model_identifier"
        }
        ```
    *   **Action:**
        1.  Backend fetches `subforum_name` and `subforum_description`.
        2.  For `number_to_generate` times:
            *   Constructs a `PersonaGenerationRequest` with `generation_type="subforum_expert"`.
            *   Slight variations could be programmatically introduced to `additional_directives` for each expert if desired for diversity, or `additional_directives_global` applied to all.
            *   Queues each request.
    *   **Response:** `202 Accepted` with a list of request IDs, or error.

**5. Frontend Integration (Conceptual for `static/js/personas.js` and others)**

Frontend modules will need to:

*   Provide UI elements (forms, buttons) to collect user input for persona generation (e.g., on settings page, subforum management page).
    *   For `name_hint`, `description_hint`, `additional_directives`.
    *   Allow selection of `llm_model_for_generation` (from available models).
    *   Potentially offer advanced options for `output_preferences` (e.g., a checklist for `desired_headings` or a dropdown for `tone_preference`).
*   Make API calls to the new generation endpoints.
*   Handle the asynchronous nature: display "generating..." feedback, show the request in the queue view (`queue.js`).
*   Once generation is complete, fetch and display the new persona in the persona list (`personas.js`).
*   For subforum experts, provide UI to trigger batch generation and display generated experts associated with the subforum.
*   Allow a "Regenerate" option for LLM-generated personas, which would re-trigger the generation process, potentially allowing users to tweak the original `input_details` or `output_preferences`.

**6. Error Handling & Resilience**

*   The `Persona Generation Module` should gracefully handle errors from LLM calls (timeouts, API errors, malformed responses from the LLM at either stage).
*   The `llm_worker` should correctly mark `llm_requests` as 'error' and store relevant error messages.
*   Frontend should display these errors to the user if a generation task fails.
*   Consider a maximum retry count for LLM calls within the generation stages if transient errors are common with local setups.

**7. Future Considerations / Extensibility**

*   **More Sophisticated Staging:** The two-stage process could be expanded (e.g., a validation/critique stage between expansion and refinement).
*   **User Feedback Loop:** Allow users to rate or provide feedback on generated personas, which could (in a very advanced system) be used to fine-tune the generation prompts.
*   **Template Versioning:** As prompt templates evolve, versioning them might be beneficial.
*   **Caching:** If identical generation requests are common (unlikely with creative tasks), caching could be considered, though the focus is on unique generation.

This self-contained design aims to provide a robust and flexible engine for generating high-quality, natural language persona instructions tailored for FORLLM's target environment of smaller, local LLMs.


---

**Phased Development Plan for Dynamic Persona Generation Engine**

This plan outlines the incremental implementation of the Dynamic Persona Generation Engine. Each phase builds upon the previous, culminating in the full feature set as described in the main design specification.

**Phase A: MVP - Core Persona Generation Pipeline & Basic UI**

**Goal:** Establish the fundamental backend infrastructure and workflow for LLM-driven persona generation, with a minimal frontend interface for testing the `from_details` generation type. The focus is on a working end-to-end process, even if the initial generated personas are basic.

**Key Features & Tasks:**

1.  **Backend - Core Module Setup (`persona_generator.py`):**
    *   Create `forllm_server/persona_generator.py`.
    *   Implement a simplified, single-stage generation process for the MVP.
        *   **Input:** Accept a simplified `PersonaGenerationRequest` (Section 2.1) focused on `generation_type="from_name_and_description"` with `name_hint` and `description_hint`.
        *   **Process (Simplified for MVP):**
            *   Construct a *single, basic "Enhancement Prompt"* directly within the module (or from a very simple template file). This prompt will instruct the LLM to:
                *   Take the `name_hint` and `description_hint`.
                *   Generate a persona description.
                *   Structure the output using a few hardcoded Markdown headings (e.g., `## Persona Name:`, `## Core Identity:`, `## Speaking Style:`). This combines elements of Stage 1 (Expansion) and Stage 2 (Refinement) from Section 2.2 into one simpler step for the MVP.
            *   Call `llm_processing.py` to send this prompt to the LLM.
            *   Parse the LLM's response to extract the name and the structured natural language instructions.
        *   **Output:** Return the `persona_name` and `prompt_instructions` (Section 2.4).
    *   Initial prompt templates (Section 2.3): Create a placeholder directory (e.g., `forllm_server/persona_prompt_templates/mvp/`) for one simple generation prompt template.

2.  **Backend - Database Schema Updates (`database.py`):**
    *   Implement the schema changes to `llm_requests`, `personas`, and `persona_versions` tables as detailed in Section 3.1.
        *   `llm_requests`: Add `request_type`, `request_params`.
        *   `personas`: Add `prompt_instructions`, `generation_source`, `generation_input_details`. (Ensure existing fields are compatible).
        *   `persona_versions`: Ensure it can store `prompt_instructions` history.
    *   Update `init_db()` to reflect these changes.
    *   Add basic CRUD functions in `database.py` for saving the newly generated persona data.

3.  **Backend - Queue & Worker Modifications (`llm_queue.py`):**
    *   Modify `llm_worker` to:
        *   Check for `request_type == 'generate_persona'` (Section 3.2).
        *   Deserialize `request_params`.
        *   Call the MVP version of the `persona_generator.py` module.
        *   On success, save the new persona to the database using the new DB functions.
        *   Update `llm_requests` status (`complete`, `error`).

4.  **Backend - API Endpoint (`forllm_server/routes/persona_routes.py`):**
    *   Create the new file `forllm_server/routes/persona_routes.py`.
    *   Implement the `POST /api/personas/generate/from_details` endpoint (Section 4).
        *   This endpoint will accept `name_hint`, `description_hint`, and `llm_model_for_generation`.
        *   It will construct the simplified `PersonaGenerationRequest` for the MVP.
        *   It will add a new job to the `llm_requests` table with `request_type='generate_persona'`.
    *   Register this new Blueprint in `forllm.py`.

5.  **Frontend - Basic UI Integration (`static/js/personas.js`):**
    *   On the existing "Personas" tab/section in the UI:
        *   Add a new section titled "Generate New Persona".
        *   Include input fields for "Persona Name Hint" (optional text input) and "Persona Description Hint" (textarea).
        *   Add a "Generate Persona" button.
        *   (The `llm_model_for_generation` can initially be hardcoded to use the globally selected LLM or a simple dropdown if model selection UI is readily adaptable).
    *   On button click:
        *   Collect input from the fields.
        *   Make an API call to `POST /api/personas/generate/from_details`.
        *   Provide basic user feedback (e.g., "Generation queued...", display request in queue if `queue.js` is sufficiently developed).
        *   Once the persona is generated (polled or refreshed via existing mechanisms), it should appear in the persona list.

**MVP Success Criteria:**
*   User can input a name hint and description hint on the personas page.
*   A "generate_persona" request is successfully queued.
*   The `llm_worker` processes the request using the MVP `persona_generator.py`.
*   A new persona, with `prompt_instructions` generated by an LLM, is saved to the database.
*   The newly generated persona appears in the persona list in the UI.
*   The core structure for prompts, generation logic, and API is in place for future expansion.

---

**Phase B: Full Two-Stage Generation, Enhanced Prompts & Output Control**

**Goal:** Implement the full, more sophisticated two-stage LLM generation process (Expansion & Refinement) as designed, introduce richer prompt templating, and allow for basic output control via `output_preferences`.

**Key Features & Tasks:**

1.  **Backend - Advanced Persona Generation (`persona_generator.py`):**
    *   Refactor the module to implement the full **Stage 1: Expansion & Brainstorming** and **Stage 2: Refinement & Structuring for Digestibility** (Section 2.2).
    *   Utilize separate, more detailed prompt templates for each stage.
    *   Implement logic to pass the output of Stage 1 as input to Stage 2.

2.  **Backend - Prompt Template Management (Section 2.3):**
    *   Organize prompt templates into subdirectories (e.g., `expansion/`, `refinement/`) within `forllm_server/persona_prompt_templates/`.
    *   Develop more detailed and robust prompt templates for `generation_type="from_name_and_description"` for both stages. These templates should incorporate the detailed guidance from Section 2.2 (e.g., role definition, input spec, output structure mandate, quality attributes).

3.  **Backend - Output Preferences (`persona_generator.py`, API):**
    *   Extend `PersonaGenerationRequest` (Section 2.1) to fully support `output_preferences`, starting with `desired_headings`.
    *   Modify the API endpoint (`POST /api/personas/generate/from_details`) to accept `output_preferences` in the request body.
    *   Update `persona_generator.py` (specifically the Refinement stage prompt construction) to use `desired_headings` if provided, otherwise fall back to a default set of comprehensive headings.

4.  **Frontend - Output Preferences UI (`static/js/personas.js`):**
    *   (Optional, could be deferred) Add UI elements to allow the user to specify some `output_preferences`. For `desired_headings`, this could be a multi-select checklist or a comma-separated input field for advanced users. Initially, the backend can just use its defaults if no UI is present for this.

**Phase B Success Criteria:**
*   The persona generation process uses the distinct two-stage (Expansion, Refinement) LLM calls.
*   More sophisticated and specific prompt templates are used for each stage.
*   The system can generate personas with a structure influenced by `desired_headings` if provided.
*   Generated personas are noticeably richer and better structured than in the MVP.

---

**Phase C: Subforum Expert Generation, Batching & Blueprint Update**

**Goal:** Extend the engine to support specialized persona generation types like "subforum_expert," enable batch generation, enhance frontend integration for these new types, and update the project's main `blueprint.md`.

**Key Features & Tasks:**

1.  **Backend - Subforum Expert Generation Type (`persona_generator.py`):**
    *   Extend `persona_generator.py` to handle `generation_type="subforum_expert"` (Section 2.1, 2.2).
        *   This includes fetching `subforum_name` and `subforum_description` based on `subforum_id`.
        *   Using these details prominently in both Expansion and Refinement prompts.
    *   Create new prompt templates specifically for `generation_type="subforum_expert"` for both stages. These templates should emphasize the subforum context.

2.  **Backend - New API Endpoints (`forllm_server/routes/persona_routes.py`):**
    *   Implement `POST /api/personas/generate/subforum_expert` (Section 4).
    *   Implement `POST /api/personas/generate/subforum_experts_batch` (Section 4), including logic to queue multiple individual generation requests.

3.  **Frontend - Subforum Expert UI (`static/js/forum.js` or `personas.js`):**
    *   Provide UI elements (e.g., on a subforum's settings/management page) to trigger single and batch generation of subforum experts.
        *   Input fields for `subforum_id` (likely implicit from context), `additional_directives`, `number_to_generate` (for batch).
        *   Allow selection of `llm_model_for_generation`.
    *   Display generated subforum experts associated with their subforum.
    *   Implement a "Regenerate" button for LLM-generated personas. This would re-queue a generation request, potentially allowing the user to slightly modify the original `input_details` (from `personas.generation_input_details`) or `output_preferences`.

4.  **Backend - Remaining `output_preferences` (Section 2.1):**
    *   Implement support for `tone_preference` and `length_preference` in `persona_generator.py` and API requests. These would be passed as hints to the LLM in the Refinement prompt.

5.  **Error Handling & Resilience (Section 6):**
    *   Conduct a thorough review and enhancement of error handling throughout the generation pipeline.
    *   Ensure clear error messages are stored and can be displayed to the user.

6.  **Documentation - Update `blueprint.md`:**
    *   Update the "File Responsibilities" section of `blueprint.md` to include:
        *   `forllm_server/persona_generator.py`
        *   `forllm_server/routes/persona_routes.py`
        *   The new prompt template directory structure.
    *   Add "Dynamic Persona Generation" to Phase 4 features in `blueprint.md`, marking it as substantially complete by this phase's end (or reflecting its phased delivery).
    *   Update database schema descriptions in `blueprint.md` if necessary.
    *   Ensure the high-level architecture diagram and description in `blueprint.md` still accurately reflect the system with this new component.

**Phase C Success Criteria:**
*   Users can generate personas specifically tailored as "subforum experts."
*   Batch generation of subforum experts is functional.
*   Frontend provides appropriate UI for these new generation types.
*   The "Regenerate" functionality is available.
*   The main `blueprint.md` accurately reflects the new module, files, and features.
*   The persona generation engine is feature-complete as per the original design specification.

This phased approach should allow for steady progress, iterative testing, and a robust final feature.