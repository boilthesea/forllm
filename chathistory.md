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
    *   **Task 1.2.1 (Backend): Fetch Model Details from Ollama.**
        *   In `llm_processing.py` or a new `ollama_utils.py`:
            *   Create a function `get_ollama_model_details(model_name: str) -> dict`.
                *   This function will make an API call to Ollama's `/api/show` endpoint for the given `model_name`.
                *   Handle potential errors (model not found, Ollama not reachable).
        *   **Benefit:** Centralizes Ollama model introspection.
    *   **Task 1.2.2 (Backend): Parse `num_ctx` from Model Details.**
        *   In `get_ollama_model_details` or a helper:
            *   Parse the `parameters` string in the response from `/api/show` to find the `num_ctx` value (or other relevant context length parameters like `max_sequence_length`).
            *   Return this `num_ctx` value (or `None` if not found).
        *   **Benefit:** Extracts the crucial context window size.
    *   **Task 1.2.3 (Backend & Database - Optional Persisting): Cache Model Context Length.**
        *   In `database.py`:
            *   Consider adding a new table: `llm_model_metadata (model_name TEXT PRIMARY KEY, context_window INTEGER, last_checked TIMESTAMP)`.
        *   Modify `llm_processing.py`:
            *   When `get_ollama_model_details` successfully retrieves `num_ctx`, store/update it in this new table.
            *   Before calling `/api/show`, check this table first to avoid redundant API calls. Refresh periodically or when explicitly requested.
        *   **Benefit:** Reduces API calls to Ollama and speeds up context length retrieval.
    *   **Task 1.2.4 (Frontend & Backend): Display Model Context Length in Settings.**
        *   In `static/js/settings.js`:
            *   When displaying the list of available Ollama models, for the currently selected model (or all of them if fetched):
                *   Call a new backend endpoint (e.g., `/api/llm/models/<model_name>/context_window`) that uses the logic from 1.2.1-1.2.3.
                *   Display: "Selected Model (<model_name>): Detected Context ~Y tokens".
        *   **Benefit:** Makes users aware of their chosen model's capabilities.

---

*   **Sub-Phase 1.3: User-Configurable Fallback Context Length**
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

---

* **Sub-Phase 1.4: Comprehensive Token Count Display (Pre-Submission)**
    *   **Task 1.4.1 (Frontend & Backend): Detailed Token Breakdown UI.**
        *   This expands on Task 1.1.3.
        *   In `static/js/forum.js` (or `editor.js`):
            *   When the user is composing a post/reply:
                *   Display an area showing estimated token counts for various components that *will* form the prompt. This requires more backend interaction or more JS logic.
                *   **Option A (Backend-driven):**
                    *   Create a new backend endpoint: `/api/prompts/estimate_tokens`
                    *   Frontend sends: `current_post_text`, `selected_persona_id` (if chosen), `parent_post_id` (for future history), any attachment info.
                    *   Backend calculates:
                        *   `tokens(current_post_text)`
                        *   `tokens(persona_prompt_for_id)`
                        *   `tokens(system_prompt)`
                        *   `tokens(attachments)`
                        *   `tokens(chat_history)` (initially 0, placeholder for Phase 2)
                        *   `total_estimated_tokens`
                    *   Backend returns this breakdown.
                *   **Option B (Frontend-driven estimation with backend helper for persona):**
                    *   Frontend counts `current_post_text` (rough JS estimate or via `/api/utils/count_tokens_for_text`).
                    *   Frontend fetches selected persona prompt (or its token count) via API if not already loaded.
                    *   Frontend has a pre-defined system prompt token count (if static) or fetches it.
                *   Display:
                    *   `Post Content: ~A tokens`
                    *   `Persona Prompt (<Persona Name>): ~B tokens`
                    *   `System Instructions: ~C tokens`
                    *   `Attachments: ~D tokens`
                    *   `Chat History: ~E tokens` (initially 0)
                    *   `--------------------`
                    *   `Total Estimated: ~X tokens / Y available (for <current_model_name>)`
                    *   A visual bar or color coding (green/yellow/red) if approaching/exceeding `Y`.
        *   **Benefit:** Empowers users to manage their prompt size effectively *before* submitting, reducing errors and frustration. Option A is more accurate but chattier. Option B is faster but might be less precise for persona/system prompts unless their exact text is pulled to the FE.
    *   **Task 1.4.2 (Backend): "Pre-flight Check" in `llm_processing.py`.**
        *   Before actually sending to Ollama, the backend should perform its own definitive token count of the *final, assembled prompt* (including any history added in Phase 2).
        *   If this count (after applying a safety margin, e.g., 90-95% of `model_context_window`) exceeds the limit, the request should ideally not be sent to Ollama. Instead, an error should be logged, and the LLM request in the `llm_requests` table should be marked with an error like "Prompt too long after assembly."
        *   **Benefit:** Prevents Ollama errors due to excessive length and provides clearer feedback if pruning (from Phase 2) isn't enough.

---
### Phase 2: Chat History Implementation

**Goal:** Incorporate conversational history into LLM prompts, with intelligent pruning for branching discussions.

---

*   **Sub-Phase 2.1: Basic Linear Chat History (Primary Thread Only)**
    *   **Task 2.1.1 (Backend): Fetch Ancestral Post Chain.**
        *   In `llm_processing.py` or `database.py`:
            *   Create `get_post_ancestors(post_id, db_connection) -> List[Post]`. This function recursively fetches parent posts until the topic root is reached. Returns them in chronological order (oldest first).
        *   **Benefit:** Forms the basis of the direct conversation.
    *   **Task 2.1.2 (Backend): Assemble Linear Chat History String.**
        *   In `llm_processing.py`:
            *   Create `format_linear_history(posts: List[Post]) -> str`.
            *   Formats the list of posts into a string, e.g.:
                ```
                User (<username>/Anonymous): <post_content>
                LLM (<persona_name>/<model_name>): <llm_response_content>
                User (<username>/Anonymous): <reply_content>
                ...
                ```
            *   Clearly label user vs. LLM/persona contributions.
        *   **Benefit:** Creates a standard representation of the conversation.
    *   **Task 2.1.3 (Backend): Integrate Linear History into Prompt Assembly.**
        *   Modify the main prompt construction logic in `llm_processing.py`:
            *   Fetch ancestors for the `post_id_to_respond_to`.
            *   Format this history.
            *   Include it in the prompt string sent to the LLM, typically between the system/persona prompt and the current user's latest message.
        *   **Benefit:** Provides the LLM with direct conversational context.
    *   **Task 2.1.4 (Backend): Basic Pruning for Linear History.**
        *   Before sending to Ollama, after assembling the full prompt (system + persona + linear history + current post):
            *   Calculate total tokens using `count_tokens`.
            *   Get the `model_context_window` (with safety margin).
            *   If `total_tokens > allowed_tokens`:
                *   Iteratively remove the oldest turns (a user post + its LLM reply if it's a pair, or just the oldest single post) from the `formatted_linear_history` string/list.
                *   Recalculate `total_tokens`. Repeat until it fits.
                *   **Crucial:** Always keep the system/persona prompt and the *current user's post* that the LLM is responding to.
        *   **Benefit:** Ensures the prompt fits, prioritizing the most recent parts of the direct conversation.

---

*   **Sub-Phase 2.2: Advanced Branch-Aware Chat History (Primary + Ambient)**
    *   **Task 2.2.1 (Backend): Identify Primary and Sibling Threads.**
        *   In `llm_processing.py` or `database.py`:
            *   `get_primary_thread_posts(target_post_id, db)`: Returns the list of posts from `target_post_id` up to the topic root (already done in 2.1.1).
            *   `get_sibling_branch_summary_posts(topic_id, primary_thread_post_ids, db, max_posts_per_sibling_branch=2, max_total_sibling_posts=5) -> List[Post]`:
                *   Find all direct children of the `topic_id` (these are roots of main branches).
                *   Exclude the branch that the `primary_thread_post_ids` belong to.
                *   For each remaining sibling branch, fetch its `max_posts_per_sibling_branch` most recent posts.
                *   Limit the total number of returned sibling posts to `max_total_sibling_posts`, prioritizing overall recency if truncation is needed across branches.
        *   **Benefit:** Isolates the main conversation and gathers relevant context from parallel discussions.
    *   **Task 2.2.2 (Backend): Structured Prompt Assembly with Prioritization.**
        *   Refine prompt construction in `llm_processing.py`:
            *   **Order of Inclusion & Token Budgeting:**
                1.  System Prompt (e.g., "You are a helpful AI...")
                2.  Persona Instructions (e.g., "You are Albert Einstein...")
                3.  *Placeholder for Ambient Introduction (e.g., "--- Other Recent Discussions ---")*
                4.  *Placeholder for Ambient Content*
                5.  Main Conversation Introduction (e.g., "--- Current Conversation Thread ---")
                6.  Primary Conversation Thread (chronological, leading up to current user's post, excluding current post itself).
                7.  Current User's Post (the one the LLM is replying to).
                8.  Assistant's Turn Start (e.g., "Assistant: ")
            *   **Token Allocation and Pruning Strategy:**
                *   Calculate `available_tokens = (model_context_window * safety_margin) - tokens(fixed_elements_like_system_persona_current_post_headers)`.
                *   **Step 1: Fit Primary Thread.**
                    *   Attempt to fit the full primary thread (from 2.2.1).
                    *   If too long, prune its oldest messages (as in 2.1.4) until it fits within `available_tokens`.
                    *   Update `available_tokens` by subtracting `tokens(fitted_primary_thread)`.
                *   **Step 2: Fit Ambient Threads (if space).**
                    *   If `available_tokens > 0`:
                        *   Fetch sibling/ambient posts using `get_sibling_branch_summary_posts`.
                        *   Format them (e.g., each post prefixed by `[From thread by UserX/PersonaY]: content`).
                        *   **Option A (Simple Recency):** Take the N most recent ambient posts that fit in the remaining `available_tokens`. Prune oldest ambient posts if the whole set doesn't fit.
                        *   **Option B (Fair Allocation - More Complex):**
                            *   Mentally divide `available_tokens` among a few (e.g., 2-3) most active/recent sibling branches.
                            *   For each allocated slot, fill with the most recent posts from that specific branch.
                            *   This is harder to implement fairly and dynamically. Start with Option A.
                        *   **Option C (Summarization - Very Advanced, Future):** Use another LLM call to summarize long ambient threads. (Out of scope for now).
                    *   Insert the fitted ambient content into its placeholder.
        *   **Benefit:** Creates a highly contextual prompt that prioritizes the direct conversation while allowing awareness of parallel discussions, all within token limits. Clear structuring helps the LLM differentiate.

---

*   **Sub-Phase 2.3: UI/UX and Configuration for Chat History**
    *   **Task 2.3.1 (Frontend): Update Token Breakdown Display.**
        *   The UI from Task 1.4.1 should now show an estimated count for "Chat History: ~E tokens", reflecting the history that *would be constructed* based on the current post's context. This requires the backend endpoint (`/api/prompts/estimate_tokens`) to simulate the history building and pruning logic.
        *   **Benefit:** User sees impact of history on token count.
    *   **Task 2.3.2 (Backend/Settings - Optional): Configuration for History Depth/Style.**
        *   Consider adding application settings for:
            *   `max_ambient_posts_to_include`: User can tune how much "other discussion" is included.
            *   `prefer_primary_thread_depth_over_ambient`: A boolean, if true, prioritize fitting more of the primary thread even if it means less/no ambient context.
        *   **Benefit:** Gives users some control over the trade-off between direct conversation depth and ambient awareness.
    *   **Task 2.3.3 (Documentation/Help): Explain History Mechanism.**
        *   Provide simple documentation explaining to users how chat history is constructed and pruned, so they understand why an LLM might sometimes seem to "forget" very old parts of a long branched discussion.
        *   **Benefit:** Manages user expectations.

---

This detailed plan gives you a roadmap. Remember to commit frequently and test each small piece. The chat history, especially the branch-aware part, will require careful debugging and iteration. Good luck!