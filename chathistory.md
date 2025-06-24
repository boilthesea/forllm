Okay, this is a great way to approach it – building the foundation methodically before tackling the more complex chat history.

Here's a phased development plan, incorporating your groundwork steps and then expanding to the advanced chat history features, including options for you to consider:

## FORLLM: Tokenizer & Chat History Development Plan

### Phase 1: Groundwork - Tokenizer Integration & Context Window Awareness

**Goal:** Establish the core mechanisms for understanding token counts and model context limits.

---

*   **Sub-Phase 1.1: Tokenizer Setup & Basic Integration**
    *   **[DONE] Task 1.1.1 (Backend): Install and Configure Tokenizer.**
        *   In `forllm_server/tokenizer_utils.py` (Note: actual path):
            *   Added `tiktoken` to `requirements.txt`.
            *   Implemented `count_tokens(text: str) -> int` using `tiktoken.get_encoding("cl100k_base").encode(text)`.
            *   Includes logging for initialization success or failure, and returns 0 if not initialized.
        *   Benefit: Establishes a consistent way to estimate token counts. `cl100k_base` is a good general-purpose default.
    *   **[DONE] Task 1.1.2 (Backend): Initial Token Counting for Core Components.**
        *   Modified `forllm_server/llm_processing.py` where prompts are constructed (before sending to Ollama):
            *   Calculates and logs token counts for:
                *   `persona_instructions`
                *   `original_post['content']` (user's current post content)
                *   `attachments_string` (concatenated text from attachments)
                *   The final `prompt_content`
            *   These counts are logged via Python's `logging` module.
        *   Benefit: Understands the token cost of existing prompt components.
    *   **[DONE] Task 1.1.3 (Frontend - Optional Early Feedback): Basic Token Estimator UI.**
        *   In `static/js/editor.js`:
            *   As the user types in the EasyMDE editor for a new post/reply:
                *   On a debounced `change` event, sends the current text to a new backend endpoint `/api/utils/count_tokens_for_text` (in `forllm_server/routes/utility_routes.py`) which uses the `count_tokens` function.
                *   Displays this estimated count (`Tokens: ~X`) near the editor. Added CSS for styling in `static/css/editor.css`.
        *   Benefit: Gives the user immediate feedback on their post's size.

---

*   **Sub-Phase 1.2: Model Context Window Discovery (Ollama)**
    *   **[DONE] Task 1.2.1 (Backend): Fetch Model Details from Ollama.**
        *   In `forllm_server/ollama_utils.py` (new file):
            *   Created function `get_ollama_model_details(model_name: str) -> dict`.
                *   Makes an API call to Ollama's `/api/show`.
                *   Handles errors.
        *   Benefit: Centralizes Ollama model introspection.
    *   **[DONE] Task 1.2.2 (Backend): Parse `num_ctx` from Model Details.**
        *   In `forllm_server/ollama_utils.py`:
            *   Created `parse_model_context_window(model_details: dict) -> int | None`.
            *   Parses the `parameters` string from `/api/show` response (or checks `model_info`) for `num_ctx` or `max_sequence_length`.
        *   Benefit: Extracts the crucial context window size.
    *   **[DONE] Task 1.2.3 (Backend & Database): Cache Model Context Length.**
        *   In `forllm_server/database.py`:
            *   Added new table: `llm_model_metadata (model_name TEXT PRIMARY KEY, context_window INTEGER, last_checked DATETIME DEFAULT CURRENT_TIMESTAMP)`. Table created in `init_db()`.
            *   Added helper functions `get_cached_model_context_window` and `cache_model_context_window`.
        *   In `forllm_server/ollama_utils.py`:
            *   Implemented `get_model_context_window(model_name: str, db)` which uses the database cache first, then falls back to fetching from Ollama via `get_ollama_model_details` and `parse_model_context_window`, then caches the result.
        *   Benefit: Reduces API calls to Ollama and speeds up context length retrieval.
    *   **[DONE] Task 1.2.4 (Frontend & Backend): Display Model Context Length in Settings.**
        *   In `forllm_server/routes/llm_routes.py`:
            *   Created new GET endpoint: `/api/llm/models/<path:model_name>/context_window`. Uses `ollama_utils.get_model_context_window`.
        *   In `static/js/settings.js`:
            *   Modified `loadOllamaModels` and added `fetchAndDisplayModelContextWindow` and `handleModelSelectionChange`.
            *   When displaying the list of available Ollama models, or when the selection changes, calls the new backend endpoint.
            *   Displays: "Selected Model (<model_name>): (Context: ~Y tokens)" or "(Context: Not Available)" in the settings UI (via a new `<span>` in `index.html`).
        *   Benefit: Makes users aware of their chosen model's capabilities.

    **Implementation Summary for Sub-Phase 1.2:**
    This sub-phase was completed by introducing a new utility module `forllm_server/ollama_utils.py` which handles direct communication with the Ollama `/api/show` endpoint to fetch model details and parse the context window size (`num_ctx` or `max_sequence_length`). To optimize performance, a caching layer was added using a new SQLite table `llm_model_metadata` (managed in `forllm_server/database.py`), which stores the retrieved context window sizes. A new API endpoint `/api/llm/models/<path:model_name>/context_window` was created in `forllm_server/routes/llm_routes.py` to expose this information. The frontend was updated in `static/js/settings.js` and `templates/index.html` to call this endpoint and display the context window for the selected Ollama model on the settings page, providing users with immediate feedback on model capabilities.

---

*   **[DONE] Sub-Phase 1.3: User-Configurable Fallback Context Length**
    *   **Task 1.3.1 (Backend & Database): Store Fallback Setting.**
        *   In `database.py`, add to your `settings` table: `default_llm_context_window INTEGER`.
        *   Initialize with a sensible default (e.g., 2048 or 4096).
    *   **Task 1.3.2 (Backend): Implement Fallback Logic.**
        *   In `llm_processing.py`, when trying to determine context length:
            *   First, try `get_ollama_model_details` (which might use the cache from 1.2.3).
            *   If it fails or returns no `num_ctx`, use the `default_llm_context_window` from the settings table.
    *   **Task 1.3.3 (Frontend & Backend): UI for Setting Fallback.**
        *   In `static/js/settings.js` and `routes/settings_routes.py`:
            *   Add a field in the application settings UI for "Default LLM Context Window (if model-specific detection fails): [input number]".
            *   Save this to the database.
        *   **Benefit:** Provides a safety net if Ollama doesn't provide context info or if a non-Ollama model is used in the future.

    **Implementation Summary for Sub-Phase 1.3:**
    This sub-phase was completed by introducing a user-configurable fallback context length.
    - In `forllm_server/database.py`, the `settings` table now stores a `default_llm_context_window` (defaulting to '4096'). This setting is added during initial DB creation and also when an older database is updated.
    - The settings API in `forllm_server/routes/settings_routes.py` (`/api/settings`) was updated to allow GET and PUT operations for `default_llm_context_window`, ensuring the value is an integer (stored as a string).
    - The frontend settings UI in `static/js/settings.js` was enhanced to include an input field for this value under the "General" settings tab. This involved updating `renderSettingsPage()` to create the input, `loadSettings()` to populate it, and `saveSettings()` to persist it, including validation for a non-negative integer.
    - In `forllm_server/llm_processing.py`, the `process_llm_request` function now determines an `effective_context_window`. It prioritizes the model-specific context window (obtained via `ollama_utils.get_model_context_window`), falls back to the user-configured `default_llm_context_window` from settings if the specific one isn't found, and finally uses a hardcoded value (2048 tokens) if neither is available. The determined `effective_context_window` is logged.

---

* **[DONE] Sub-Phase 1.4: Comprehensive Token Count Display (Pre-Submission)**
    *   **Task 1.4.1 (Frontend & Backend): Detailed Token Breakdown UI.**
        *   This expands on Task 1.1.3.
        *   In `static/js/editor.js`:
            *   When the user is composing a post/reply:
                *   Display an area showing estimated token counts for various components that *will* form the prompt.
                *   **Implementation Details:**
                    *   New backend endpoint: `/api/prompts/estimate_tokens` (in `forllm_server/routes/utility_routes.py`).
                    *   Frontend sends: `current_post_text`, `selected_persona_id` (if a global persona selector is used, otherwise null/default), `attachments_text` (concatenated content of selected text-based attachments), and `parent_post_id` (unused for now).
                    *   Backend calculates:
                        *   `tokens(current_post_text)`
                        *   `tokens(persona_prompt_for_id)`
                        *   `tokens(system_prompt)` (placeholder, currently 0)
                        *   `tokens(attachments_text)`
                        *   `tokens(chat_history)` (initially 0, placeholder for Phase 2)
                        *   `total_estimated_tokens`
                    *   Backend returns this breakdown, including `persona_name`, `model_context_window`, and `model_name`.
                *   Display in UI (near editor, via `templates/index.html` and `static/js/editor.js`):
                    *   `Post Content: ~A tokens`
                    *   `Persona Prompt (<Actual Persona Name>): ~B tokens`
                    *   `System Instructions: ~C tokens`
                    *   `Attachments: ~D tokens`
                    *   `Chat History: ~E tokens` (initially 0)
                    *   `--------------------`
                    *   `Total Estimated: ~X tokens / Y available (for <current_model_name>)`
                    *   A visual bar indicating usage against the model's context window, color-coded (green/yellow/red).
    *   **Task 1.4.2 (Backend): "Pre-flight Check" in `llm_processing.py`.**
        *   Before actually sending to Ollama, the backend performs its own definitive token count of the *final, assembled prompt*.
        *   If this count (after applying a safety margin, currently hardcoded at 95% of `model_context_window`) exceeds the limit:
            *   The request is not sent to Ollama.
            *   An error should be logged, and the LLM request in the `llm_requests` table should be marked with `status='error'` and a detailed `error_message` (e.g., 'Error: Prompt too long after assembly. Tokens: X, Max Allowed (after safety margin): Y (Context: Z)').
        *   The token breakdown (persona, user post, attachments, total) is stored as a JSON string in the `llm_requests.prompt_token_breakdown` column (new column added in `forllm_server/database.py`) and displayed in the queue UI (`static/js/queue.js`) for relevant items (completed or error).
        *   **Benefit:** Prevents Ollama errors due to excessive length and provides clearer feedback.

    **Implementation Summary for Sub-Phase 1.4:**
    This sub-phase focused on providing comprehensive token count information to the user and implementing a pre-flight check to prevent oversized prompts from being sent to the LLM.
    - **Detailed Token Breakdown UI (Task 1.4.1):**
        - A new API endpoint `/api/prompts/estimate_tokens` was created in `forllm_server/routes/utility_routes.py`. It accepts current post text, selected persona ID, and concatenated text from attachments. It returns a detailed breakdown of estimated token counts for each component (post content, persona prompt, attachments, system prompt placeholder, chat history placeholder), the total estimated tokens, and the current model's name and context window size.
        - The frontend editor interface (`static/js/editor.js` and `templates/index.html`) was updated to call this endpoint. As the user types or changes attachments/persona, a detailed breakdown is displayed near the editor, including a visual bar indicating usage against the model's context window.
    - **Backend Pre-flight Check & Token Storage (Task 1.4.2):**
        - In `forllm_server/llm_processing.py`, before sending a request to Ollama, the final assembled prompt's token count is calculated.
        - A `prompt_token_breakdown` JSON string (containing counts for persona, user post, attachments, and total) is now stored in a new `prompt_token_breakdown` column in the `llm_requests` table (migration handled in `forllm_server/database.py`).
        - If this total count exceeds 95% of the model's effective context window, the request is marked as an error in the database (with a detailed message), and not sent to the LLM.
        - The `static/js/queue.js` was updated to parse and display this `prompt_token_breakdown` for completed/error items in the queue UI.
    This provides users with immediate feedback on prompt size and helps prevent unnecessary LLM processing errors.

---
### Phase 2: Chat History Implementation

**Goal:** Incorporate conversational history into LLM prompts, with intelligent pruning for branching discussions.

---

*   **Sub-Phase 2.1: Basic Linear Chat History (Primary Thread Only)**
    *   **[DONE] Task 2.1.1 (Backend): Fetch Ancestral Post Chain.**
        *   Implemented `get_post_ancestors(post_id, db_connection)` in `forllm_server/database.py`. This function recursively fetches parent posts from the given `post_id` up to the topic root, returning them in chronological order (oldest first). All specified fields from the `posts` table are included.
        *   **Benefit:** Forms the basis of the direct conversation.
    *   **[DONE] Task 2.1.2 (Backend): Assemble Linear Chat History String.**
        *   Implemented `format_linear_history(posts: list, db_connection)` in `forllm_server/llm_processing.py`. This function formats the list of posts (from `get_post_ancestors`) into a string, clearly labeling user posts vs. LLM/persona contributions (e.g., "User: <content>" or "LLM (<persona_name>/<llm_model_name>): <content>"). It fetches persona names using `llm_persona_id`.
        *   **Benefit:** Creates a standard representation of the conversation.
    *   **[DONE] Task 2.1.3 (Backend): Integrate Linear History into Prompt Assembly.**
        *   Modified `process_llm_request` in `forllm_server/llm_processing.py`. Before finalizing the prompt, it now calls `get_post_ancestors` and `format_linear_history` to build the chat history string. This history is prepended to the `prompt_content` (after attachments and persona instructions, but before the current user's post). Token counts in `prompt_token_breakdown` are updated to include `chat_history_tokens`.
        *   **Benefit:** Provides the LLM with direct conversational context.
    *   **[DONE] Task 2.1.4 (Backend): Basic Pruning for Linear History.**
        *   Enhanced `process_llm_request` in `forllm_server/llm_processing.py`. After the full prompt is assembled, if its token count exceeds the allowed limit (context window * 0.95), a loop iteratively removes the oldest turns (lines) from the `chat_history_string` part of the prompt. The persona instructions, attachments, and current user's post are never removed. This pruning attempts to make the prompt fit before the final pre-flight check. Token counts are updated post-pruning.
        *   **Benefit:** Ensures the prompt fits, prioritizing the most recent parts of the direct conversation.

    **Implementation Summary for Sub-Phase 2.1:**
    This sub-phase successfully implemented a basic linear chat history mechanism.
    1.  `get_post_ancestors` was created in `database.py` to fetch the direct chain of posts leading to the current one.
    2.  `format_linear_history` was added to `llm_processing.py` to convert this chain into a clearly labeled "User:" / "LLM (persona/model):" string format.
    3.  The main prompt assembly logic in `process_llm_request` now incorporates this formatted linear history, placing it after persona instructions and before the current user's post.
    4.  A basic pruning strategy was also added to `process_llm_request`: if the fully assembled prompt (including history) exceeds 95% of the model's context window, the oldest turns from the chat history are iteratively removed until the prompt fits or all history is removed. Attachments, persona, and the current user's post are preserved.
    Token counts for chat history are now included in the `prompt_token_breakdown` stored in the database. This provides a foundational context for LLM replies based on the immediate preceding conversation.

---

*   **[DONE] Sub-Phase 2.2: Advanced Branch-Aware Chat History (Primary + Ambient)**
    *   **Task 2.2.1 (Backend): Identify Primary and Sibling Threads.**
        *   **Summary:**
            *   `get_primary_thread_posts`: This is effectively handled by `get_post_ancestors(target_post_id, db)` from Sub-Phase 2.1.1, which retrieves the direct chain of posts leading to the current post being responded to.
            *   `get_sibling_branch_roots(topic_id, primary_thread_post_ids, db)`: Implemented in `forllm_server/database.py`. This function fetches all root posts (those with `parent_post_id IS NULL`) within a given `topic_id`, then filters out any post whose `post_id` is present in the `primary_thread_post_ids` list. This identifies the starting points of all other discussion branches in the same topic.
            *   `get_recent_posts_from_branch(branch_root_id, db, max_posts=N)`: Implemented in `forllm_server/database.py`. For a given `branch_root_id` (a `post_id` that is the start of a sibling branch), this function uses a recursive CTE to find all descendant posts and returns the `N` most recent ones in chronological order.
            *   **Usage in `llm_processing.py`**: The `process_llm_request` function uses these to build ambient context. After fetching the primary thread (`ancestors`), it extracts their IDs. It then calls `get_sibling_branch_roots` to find other branch starting points. For each root, `get_recent_posts_from_branch` is called (with `max_posts_per_sibling_branch` e.g., 2). All collected posts from these sibling branches are pooled, sorted by their creation date (most recent first), and then truncated to a global maximum (e.g., `MAX_TOTAL_AMBIENT_POSTS` like 5). These selected posts are then reversed to be chronological for the prompt.
        *   **Benefit:** Isolates the main conversation and gathers relevant, recent context from parallel discussions.
    *   **Task 2.2.2 (Backend): Structured Prompt Assembly with Prioritization.**
        *   **Summary:**
            *   **Order of Inclusion & Token Budgeting:** The prompt construction in `llm_processing.py` now follows this approximate order:
                1.  `attachments_string` (if any, with its own formatting and newlines)
                2.  `persona_instructions` (followed by `\n\n`)
                3.  `AMBIENT_HISTORY_HEADER` (e.g., "--- Other Recent Discussions ---", if ambient posts exist, followed by `\n\n`)
                4.  Formatted Ambient Posts (each post prefixed like `[From other thread by User/LLM (PersonaName)]: content`, joined by `\n`, followed by `\n\n` if the section exists)
                5.  `PRIMARY_HISTORY_HEADER` (e.g., "--- Current Conversation Thread ---", if primary history posts exist, followed by `\n\n`)
                6.  Formatted Primary Conversation Thread (from `format_linear_history`, followed by `\n\n` if the section exists)
                7.  `User wrote: ` + `original_post['content']` (followed by `\n\n`)
                8.  `FINAL_INSTRUCTION` (e.g., "Respond to this post.")
            *   **Token Allocation and Pruning Strategy:**
                *   A helper function `_prune_history_string(history_content, budget, logger_prefix, request_id)` was implemented to remove the oldest lines from a given string of history content until it fits the `budget`.
                *   `fixed_elements_tokens` are calculated first (attachments, persona, user's current post with "User wrote: " prefix, final instruction).
                *   `available_tokens_for_history_sections` is `max_allowed_tokens - fixed_elements_tokens`.
                *   **Primary Thread:**
                    *   The budget for primary history *content* is `(available_tokens_for_history_sections * PRIMARY_HISTORY_BUDGET_RATIO) - tokens(PRIMARY_HISTORY_HEADER + "\n\n")`.
                    *   The raw primary history content (from `format_linear_history`) is pruned against this budget using `_prune_history_string`.
                    *   The final token count for the primary section includes header tokens if content remains.
                *   **Ambient Threads:**
                    *   The budget for ambient history *content* is the remaining `available_tokens_for_history_sections` after accounting for the actual tokens used by the (potentially pruned) primary history section (including its header), minus tokens for the `AMBIENT_HISTORY_HEADER`.
                    *   The raw ambient posts content (formatted and joined) is pruned against this budget.
                    *   The final token count for the ambient section includes header tokens if content remains.
            *   The token breakdown stored in the `llm_requests` table was updated. `chat_history_tokens` was renamed to `primary_chat_history_tokens` (stores token count of pruned primary content, excluding header). A new `ambient_chat_history_tokens` key was added (for pruned ambient content, excluding header). A `headers_tokens` key stores the sum of tokens for headers that were actually included. `total_prompt_tokens` reflects all parts.
        *   **Benefit:** Creates a highly contextual prompt that prioritizes the direct conversation while allowing awareness of parallel discussions, all within token limits. Clear structuring helps the LLM differentiate.

    **Implementation Summary for Sub-Phase 2.2:**
    Sub-Phase 2.2 significantly enhanced chat history by introducing branch awareness.
    - **Database Functions:** Two new functions were added to `forllm_server/database.py`:
        - `get_sibling_branch_roots(topic_id, primary_thread_post_ids, db)`: Identifies starting posts of other discussion branches within the same topic.
        - `get_recent_posts_from_branch(branch_root_id, db, max_posts)`: Fetches a specified number of recent posts from a given branch.
    - **LLM Processing (`llm_processing.py`):**
        - **Ambient Context:** The `process_llm_request` function now uses the new database functions to gather "ambient" posts from sibling branches. It limits posts per branch (via `MAX_POSTS_PER_SIBLING_BRANCH`) and total ambient posts (via `MAX_TOTAL_AMBIENT_POSTS`), prioritizing overall recency.
        - **Prompt Structure:** The prompt was restructured to include distinct sections for ambient history (under "--- Other Recent Discussions ---") and primary history (under "--- Current Conversation Thread ---"), in addition to attachments, persona, the current user's post, and a final instruction.
        - **Token Budgeting & Pruning:** A more sophisticated pruning strategy was implemented:
            - Fixed elements (attachments, persona, user post, final instruction) have their tokens calculated first.
            - The remaining `available_tokens_for_history_sections` are then allocated.
            - Primary history content is pruned against a dedicated budget (e.g., 70% of available history tokens, defined by `PRIMARY_HISTORY_BUDGET_RATIO`), minus its header cost.
            - Ambient history content is pruned against the remaining budget, minus its header cost.
            - A helper `_prune_history_string` was created for this.
        - **Token Breakdown:** The `prompt_token_breakdown` in the `llm_requests` table was updated to store `primary_chat_history_tokens` (content only), `ambient_chat_history_tokens` (content only), and `headers_tokens`.
    This allows the LLM to have a more holistic understanding of the ongoing discussion by including relevant context from parallel threads while carefully managing token limits.

---

*   **[DONE] Sub-Phase 2.3: UI/UX and Configuration for Chat History**
    *   **[DONE] Task 2.3.1 (Frontend): Update Token Breakdown Display.**
        *   The UI from Task 1.4.1 should now show an estimated count for "Chat History: ~E tokens", reflecting the history that *would be constructed* based on the current post's context. This requires the backend endpoint (`/api/prompts/estimate_tokens`) to simulate the history building and pruning logic.
        *   **Note:** The backend estimation logic for `/api/prompts/estimate_tokens` will need significant updates to accurately mirror the new complex history building (primary + ambient fetching, formatting, and multi-stage pruning) now implemented in `process_llm_request`. This is a non-trivial change for the estimator.
        *   **Benefit:** User sees impact of history on token count.
    *   **[DONE] Task 2.3.2 (Backend/Settings - Optional): Configuration for History Depth/Style.**
        *   Add application settings for:
            *   `max_ambient_posts_to_include`: User can tune how much "other discussion" is included. (Currently handled by `MAX_TOTAL_AMBIENT_POSTS` constant in `llm_processing.py`).
            *   `max_posts_per_sibling_branch`: (Currently `MAX_POSTS_PER_SIBLING_BRANCH` constant).
            *   `prefer_primary_thread_depth_over_ambient`: A boolean, if true, prioritize fitting more of the primary thread even if it means less/no ambient context. (Currently handled by `PRIMARY_HISTORY_BUDGET_RATIO` constant).
        *   Make these user configurable in the database and via the settings UI under the LLM tab in a chat history section and place a tooltip in the UI where a user can get a brief explanation of what the setting does.
        *   **Benefit:** Gives users some control over the trade-off between direct conversation depth and ambient awareness.
    *   **[DONE] Task 2.3.3 (Documentation/Help): Explain History Mechanism.**
        *   Provide simple documentation explaining to users how chat history is constructed (primary and ambient) and pruned, so they understand why an LLM might sometimes seem to "forget" very old parts of a long branched discussion.
        *   **Benefit:** Manages user expectations.

    **Implementation Summary for Sub-Phase 2.3:**
    This sub-phase completed the chat history feature set by enhancing UI/UX and adding configurability.
    1.  **Token Estimator Accuracy (Task 2.3.1):** The `/api/prompts/estimate_tokens` endpoint in `utility_routes.py` was significantly upgraded. It now calls the refactored helper functions (`_get_raw_history_strings`, `_prune_history_sections`) from `llm_processing.py`, ensuring it accurately simulates the full primary and ambient history construction, including the multi-stage pruning logic based on current database settings. This provides a much more precise token breakdown in the frontend editor.
    2.  **Configurable History Settings (Task 2.3.2):**
        *   **Database & Backend:** New settings (`ch_max_ambient_posts`, `ch_max_posts_per_sibling_branch`, `ch_primary_history_budget_ratio`) were added to the `settings` table in `database.py` with defaults. The `llm_processing.py` module was updated to fetch and use these settings (with fallbacks to defaults) instead of hardcoded constants, via a new `get_chat_history_settings` helper. The settings API in `settings_routes.py` now handles GET/PUT for these new keys, including validation.
        *   **Frontend:** The settings UI (`index.html` and `settings.js`) was updated to include a "Chat History Configuration" section under LLM settings, allowing users to view and modify these parameters.
    3.  **User Documentation (Task 2.3.3):** A "User Instructions: Understanding Chat History in FORLLM" section was appended to this `chathistory.md` file, explaining how history is built, pruned, and configured.

---

This detailed plan gives you a roadmap. Remember to commit frequently and test each small piece. The chat history, especially the branch-aware part, will require careful debugging and iteration. Good luck!

## User Instructions: Understanding Chat History in FORLLM

FORLLM's chat history feature is designed to give the LLM context about the ongoing conversation, making its responses more relevant and coherent. Here's a breakdown of how it works:

### How History is Constructed

When you ask an LLM to respond to a post, FORLLM automatically assembles relevant context from the current topic:

1.  **Primary Conversation Thread:**
    *   This includes the direct chain of posts leading up to the post you're responding to (i.e., its parent, its parent's parent, and so on, up to the original topic post).
    *   This is considered the most important context.
    *   Posts are formatted to distinguish between user messages and LLM responses (e.g., "User: ..." or "LLM (Persona Name): ...").

2.  **Ambient Conversational Context:**
    *   To provide broader awareness, FORLLM also looks at other discussion branches within the same topic.
    *   It tries to pick up recent, relevant snippets from these "sibling" threads.
    *   This helps the LLM understand if related points are being discussed elsewhere in the topic, even if not directly in the current reply chain.

These two types of history are presented to the LLM in clearly marked sections (e.g., "--- Current Conversation Thread ---" and "--- Other Recent Discussions ---") to help it differentiate.

### Token Limits and Pruning

LLMs have a limited "context window" – they can only process a certain number of tokens (words or parts of words) at once. If the combined history, your current post, persona instructions, and any attachments exceed this limit, FORLLM must shorten, or "prune," the history.

*   **Pruning Strategy:** FORLLM prioritizes keeping the most recent information and the primary conversation thread.
    1.  First, it calculates the tokens needed for your current post, the persona's instructions, and any file attachments. These are considered essential and are not pruned.
    2.  The remaining available tokens are then allocated to chat history.
    3.  The **Primary Conversation Thread** gets a larger portion of this budget (you can configure this ratio). If it's too long, the *oldest* posts from this thread are removed one by one until it fits its allocated budget.
    4.  The **Ambient Conversational Context** then uses the remaining token budget. If it's too long, the *oldest* or least relevant snippets from sibling threads are removed until it fits.
*   **Why Pruning is Necessary:** Without pruning, prompts could become too long for the LLM to handle, leading to errors or incomplete responses. The goal is to provide the most relevant context possible within the available limits. This means very old parts of a long and branched discussion might eventually be "forgotten" by the LLM in that specific interaction.

### Configuring Chat History

You can customize how chat history is constructed via the application settings (under the "LLM" tab):

*   **Max Ambient Posts:** Controls the maximum total number of recent posts from *all other* discussion branches to include as ambient history. Setting this to 0 effectively disables ambient history. (Default: 5)
*   **Max Posts Per Sibling Branch:** Sets the maximum number of recent posts to draw from *each individual* sibling branch when gathering ambient history. (Default: 2)
*   **Primary History Budget Ratio:** A value between 0.0 and 1.0 that determines the proportion of the available token budget (after accounting for your post, persona, etc.) that should be reserved for the primary conversation thread. For example, a value of 0.7 means 70% of the history tokens will be dedicated to the primary thread, and 30% to ambient context. (Default: 0.7)

By adjusting these settings, you can fine-tune the balance between the depth of the direct conversation and the breadth of ambient context provided to the LLM.