### Phased Development Plan: Custom Instructions (Revision 2)

**Objective:** Implement a "custom instructions" feature that allows users to create, manage, and apply reusable prompt snippets. These instructions can be ordered, grouped into sets, and applied globally, as subforum defaults, or on-demand in posts using a `!tag` syntax. The editor will provide clear, real-time feedback on which instructions are active.

---

#### **Phase 1: Backend Foundation & Core Logic [COMPLETED]**

**Goal:** Evolve the database schema and APIs to support instruction ordering, sets, and the new UI for managing defaults. Ensure a smooth migration path for existing users.

1.  **Database Schema & Migration:**
    *   **Migration Strategy:** Update the `init_db` function in `forllm_server/database.py`. All schema changes will be wrapped in checks (`PRAGMA table_info(...)`) to see if columns/tables already exist. This ensures that running the application on an existing database will apply the changes non-destructively using `ALTER TABLE`.
    *   **`custom_instructions` Table:**
        *   Create this table if it doesn't exist.
        *   Add a `priority` column (INTEGER, default 0) to control application order.
        *   Add a `is_global_default` column (BOOLEAN, default FALSE).
    *   **`subforum_instruction_defaults` Table:**
        *   Create this new association table to link instructions to subforums (`instruction_id`, `subforum_id`). This replaces the previous plan for a generic association table and better supports the new UI.
    *   **Instruction Sets Tables:**
        *   Create `instruction_sets` (`set_id`, `name`).
        *   Create `instruction_set_items` (`set_id`, `instruction_id`) to link instructions to sets.
    *   **`posts` Table:**
        *   Add `tagged_custom_instructions_in_content` (TEXT) and `tagged_instruction_sets_in_content` (TEXT) columns.

2.  **API Endpoints (`custom_instruction_routes.py`):**
    *   **CRUD for Instructions:** Enhance the CRUD endpoints to also set/update `priority` and `is_global_default`.
    *   **CRUD for Sets:** Implement endpoints for creating, deleting, and managing the instructions within a set.
    *   **Subforum Default Management:**
        *   `POST /api/custom-instructions/<inst_id>/subforum-defaults`: Assigns an instruction as a default for a specific subforum (`subforum_id` in body).
        *   `DELETE /api/custom-instructions/<inst_id>/subforum-defaults/<subforum_id>`: Removes a default assignment.
        *   `GET /api/subforums/search?q=<query>`: A new endpoint in `forum_routes.py` to provide typeahead search results for subforum names.

3.  **Core Prompt Logic (`llm_processing.py`):**
    *   Update `process_llm_request` to handle the new features:
        *   **Set Expansion:** Before gathering instructions, expand any tagged sets (e.g., `!set:creative-writing`) into their constituent instruction IDs.
        *   **Gather All:** Collect instructions from all sources: global defaults (`is_global_default = true`), subforum defaults, tagged instructions, and expanded sets.
        *   **Order & Apply:** De-duplicate the final list of instructions, sort them based on the `priority` column, and then prepend their combined `prompt_text` to the LLM prompt.

---

#### **Phase 2: Frontend UI & Management [COMPLETED]**

**Goal:** Build the user interface for managing instructions and sets, including the new checkbox- and pill-based system for setting defaults.

1.  **Custom Instructions Management UI (`settings.js`):**
    *   Create the "Custom Instructions" tab in Settings.
    *   For each instruction in the list, display:
        *   Name, Edit/Delete buttons.
        *   A `priority` number input.
        *   A "Global Default" checkbox.
    *   **Subforum Defaults UI:**
        *   A "Subforum Default" checkbox.
        *   When checked, reveal a text input for adding subforums.
        *   Implement autocomplete on this input, calling `/api/subforums/search`.
        *   On selection, add the subforum as a styled "pill" below the input. Each pill will have an 'x' button.
        *   Clicking 'x' on a pill calls the `DELETE` endpoint to remove the association and removes the pill from the UI.
        *   Adding a pill calls the `POST` endpoint.
    *   **Instruction Sets UI:** Add a separate section for creating/managing sets, allowing users to add/remove instructions from them.

2.  **Editor Autocomplete (`editor.js`):**
    *   Update the autocomplete to recognize both `!` for individual instructions and `!set:` for sets.
    *   The API for suggestions (`/api/custom-instructions/list-active`) will be updated in the next phase to be context-aware.

---

#### **Phase 3: Editor Integration & Context-Awareness [COMPLETED]**

**Goal:** Integrate the active instructions display into the editor status bar and make the frontend fully aware of the context.

1.  **Editor Status Bar UI (`editor.js`):**
    *   Following the pattern of the token counter, add a new status bar panel for "Instructions".
    *   **Collapsed View:** `Instructs: !name1, !name2, ...` (truncated with an ellipsis).
    *   **Expanded View:** On click, it expands to show a detailed breakdown:
        *   **Global:** `!global-instruction-1`
        *   **Subforum (Subforum Name):** `!subforum-instruction-1`
        *   **Tagged:** `!tagged-instruction-1`

2.  **Dynamic UI Updates (`editor.js`):**
    *   Create a new function, `updateInstructionsDisplay`, modeled on `updateTokenBreakdown`.
    *   This function will trigger whenever the editor content changes (a `!` tag is added/removed) or the context changes (a subforum is selected).
    *   It will need to know the current subforum context to work correctly.

3.  **Context-Aware Backend (`custom_instruction_routes.py`):**
    *   Create a new endpoint: `GET /api/instructions/active-for-context?subforum_id=<id>`. This endpoint will return a structured JSON object containing the names and sources (Global, Subforum) of all default instructions for the given context. The frontend will use this to populate the status bar display.
    *   Refine the autocomplete suggestion endpoint (`/api/custom-instructions/list-active`) to use the `subforum_id` context to filter out already-applied defaults, as planned previously.