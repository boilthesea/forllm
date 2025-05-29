# Persona Tagging Feature Plan

**Feature Goal:** Implement a persona tagging system in FORLLM to trigger asynchronous LLM responses from tagged personas. This includes tagging within new posts/replies using an `@mention` system with typeahead suggestions, and via a dedicated tagging field for existing posts (especially persona posts).

**Plan:**

This feature requires coordinated changes across the frontend (HTML, CSS, JavaScript) and the backend (Python/Flask, Database).

## 1a. Database Modifications:

*   **`posts` table:** Add a new column, `tagged_personas_in_content` (TEXT, storing a JSON array of persona IDs), to store a list of `persona_id`s extracted from `@[Persona Name](persona_id)` tags within the post/reply *body* content.
*   **New table `post_persona_tags`:** Create a new table specifically for tagging *existing* posts to request a response from a specific persona.
    *   `tag_id` (INTEGER PRIMARY KEY AUTOINCREMENT)
    *   `post_id` (INTEGER, Foreign Key to `posts.post_id` - the existing post being responded to)
    *   `persona_id` (INTEGER, Foreign Key to `personas.persona_id` - the persona being tagged to respond)
    *   `tagged_by_user_id` (INTEGER, Foreign Key to `users.user_id` - the user who applied the tag)
    *   `created_at` (DATETIME, DEFAULT CURRENT_TIMESTAMP)
    *   This table facilitates adding targeted LLM response requests to existing content.

## 1b. User Workflow:

1.  **Tagging in New Post/Reply (Content Editor):**
    *   User types `@` in the EasyMDE editor.
    *   Frontend immediately displays a list of available personas. As the user types more characters after the `@`, the list of persona suggestions dynamically filters and narrows in real-time.
    *   User selects a persona from the suggestion list (e.g., by clicking or using arrow keys and Enter).
    *   Frontend inserts the tag in a hidden format like `@[Persona Name](persona_id)` into the editor's raw content, while visually displaying it as a styled `@Persona Name` (e.g., with a different background or border) in the editor preview and rendered post.
    *   User submits the new topic or reply.
    *   Frontend sends the full content (including hidden tags) to the backend.
    *   Backend parses these tags from the content, saves the post, stores extracted `persona_id`s in `posts.tagged_personas_in_content`, and queues LLM requests in the `llm_requests` table for each uniquely tagged persona.

2.  **Tagging an Existing Post (Dedicated Tagging Field):**
    *   User is viewing any post (user-authored or an LLM response).
    *   Below the post content, a new "Tag Persona to Respond" field or button is available.
    *   User interacts with this field/button.
    *   Frontend presents an input field. As the user types a persona name, a list of matching personas appears and narrows down, similar to the `@mention` functionality.
    *   User selects a persona.
    *   Frontend makes an API call (e.g., `POST /api/posts/<post_id>/tag_persona`) with the `post_id` and selected `persona_id`.
    *   Backend records this explicit tag in the `post_persona_tags` table and queues an LLM request in `llm_requests` for the tagged persona to respond to the specified `post_id`.

3.  **LLM Processing:**
    *   The background LLM worker periodically checks the `llm_requests` table for 'pending' requests.
    *   For each request, it identifies the `post_id_to_respond_to` and the specific `persona_id` to use for generating the response.
    *   The LLM generates a response using the designated persona's instructions and the context of the target post.
    *   The LLM's response is saved as a new post in the `posts` table, linked as a reply to the `post_id_to_respond_to`.

4.  **Display:**
    *   The frontend, during its regular polling or data fetching, retrieves new posts, including LLM responses generated due to tagging.
    *   The `renderPosts` function in JavaScript will:
        *   Display new LLM-generated replies.
        *   Parse post content for `@[Persona Name](persona_id)` patterns (potentially using the `tagged_personas_in_content` data as a hint or for direct rendering if the raw markdown is preserved). It will then apply the visual flare (e.g., special styling, tooltip on hover showing persona details) to these recognized persona tags within the displayed post content.
        *   Indicate which personas have been explicitly tagged to respond via the dedicated tagging field, perhaps by listing them or showing a "response requested from X" message.

## 2. Backend (Python/Flask) Modifications:

*   **API Endpoint for Persona List (`forllm_server/routes/persona_routes.py`):**
    *   Create/ensure `GET /api/personas/list_active` (or similar) that returns a list of all *active/usable* personas (e.g., `persona_id`, `name`), sorted alphabetically by name. This is crucial for the frontend's typeahead suggestion feature.
*   **Modify Post/Reply Creation Endpoints (`forllm_server/routes/forum_routes.py`):**
    *   Update `POST /api/subforums/<subforum_id>/topics` (for new topics/initial posts) and `POST /api/topics/<topic_id>/posts` (for replies).
    *   These endpoints will receive the post/reply content.
    *   Implement robust parsing logic (e.g., using regular expressions) to find all instances of `@[Persona Name](persona_id)` tags within the received content.
    *   Extract all unique `persona_id`s from these tags.
    *   Store the JSON array of these `persona_id`s in the new `posts.tagged_personas_in_content` column for the created post.
    *   For each unique `persona_id` extracted, create a new entry in the `llm_requests` table. This entry should specify the `post_id_to_respond_to` (the ID of the post just created), the `persona_id` extracted from the tag, the `model` associated with the persona (or system default if not specified), and set `status` to 'pending'.
*   **New API Endpoint for Tagging Existing Posts (`forllm_server/routes/llm_routes.py`):**
    *   Create `POST /api/posts/<int:post_id>/tag_persona`.
    *   This endpoint will accept a JSON body containing `persona_id`.
    *   It will add an entry to the `post_persona_tags` table (linking `post_id`, `persona_id`, `tagged_by_user_id`).
    *   It will then create a new entry in the `llm_requests` table, similar to above, for the specified `post_id` and `persona_id`.
*   **Modify Post Fetching Logic (`forllm_server/routes/forum_routes.py`):**
    *   When fetching posts (e.g., for topic view), ensure the `tagged_personas_in_content` data is included for posts.
    *   Consider if data from `post_persona_tags` related to a post needs to be fetched and sent to the client (e.g., to show "Response requested from Persona X").
*   **LLM Worker Enhancement (`forllm_server/llm_queue.py`, `forllm_server/llm_processing.py`):**
    *   The LLM worker already processes items from `llm_requests`. Ensure it correctly uses the `persona_id` (and associated `model` if stored per persona or in request) from the queue item to fetch the right persona instructions and configure the LLM call.
    *   The `request_type` in `llm_requests` might be 'respond_to_post_via_tag' or similar to differentiate if needed, though existing 'respond_to_post' might suffice if `persona_id` is correctly utilized.

## 3. Frontend (HTML, CSS, JavaScript) Modifications:

*   **HTML (`templates/index.html`):**
    *   Near the EasyMDE instances (`newTopicEditor`, `replyEditor`), add a dedicated `div` (e.g., `<div class="mention-suggestions" style="display:none;"></div>`) to serve as the container for the `@mention` persona suggestion list.
    *   In the template for rendering individual posts (likely generated by `renderPostNode` in JS), add a new section/element below the post content. This will house the UI for tagging that existing post (e.g., an input field and a button, or an interactive "Tag Persona to Respond" component).
*   **CSS (`static/css/forum.css`, `static/css/components.css`):**
    *   Styles for the `@mention` suggestion list: absolute positioning (near cursor/input), width, borders, item highlighting on hover/selection, scrollbar if list is long.
    *   Styles for the visual flare of recognized `@Persona Name` tags within rendered post content (e.g., `background-color: #444; padding: 1px 3px; border-radius: 3px;`) and potentially within the EasyMDE preview.
    *   Styles for a tooltip that can appear on hover over a tagged persona name, showing more details (if implemented).
    *   Styles for the new "Tag Persona to Respond" field/area below posts: input field styling, button styling, and the associated persona suggestion list.
*   **JavaScript (`static/js/editor.js`):**
    *   Enhance EasyMDE setup. On editor `input` or `keyup` events, check if the text preceding the cursor matches an `@mention` pattern (e.g., `@` followed by zero or more characters).
    *   When an `@mention` sequence is detected:
        *   Dynamically fetch the persona list from `GET /api/personas/list_active` (cache this list for a short period to avoid excessive API calls).
        *   Display the suggestion list container.
        *   As the user types after `@`, continuously filter the cached persona list in real-time based on the typed text and update the displayed suggestions.
        *   Implement keyboard navigation (up/down arrows, Enter to select) and mouse click selection for the suggestion list.
        *   On selection, insert the `@[Persona Name](persona_id)` string at the cursor position in EasyMDE's underlying textarea. The visual rendering in EasyMDE's preview should ideally show the styled `@Persona Name`.
*   **JavaScript (`static/js/forum.js`):**
    *   **`addTopic()` / `submitReply()`**: Ensure the raw content from EasyMDE (including the `@[Persona Name](persona_id)` tags) is sent to the backend.
    *   **`renderPosts()` / `renderPostNode()`**:
        *   When rendering post content, identify `@[Persona Name](persona_id)` tags. This could be done by regex matching on the content, or if the backend provides `tagged_personas_in_content` and their names, use that. Replace/wrap these tags with HTML (`<span>` or `<a>`) styled for the visual flare. Add hover tooltips if desired.
        *   Render the new "Tag Persona to Respond" UI below each post. This UI will include an input field.
        *   Attach event listeners to this input field. On input, fetch/filter the persona list (similar to `@mention` in `editor.js`) and display suggestions.
        *   On selecting a persona from this field's suggestions, call the `POST /api/posts/<post_id>/tag_persona` API endpoint (via a function in `api.js`).
        *   Display personas already tagged on this post via this mechanism (e.g., "Response requested from: PersonaX, PersonaY").
*   **JavaScript (`static/js/api.js`):**
    *   Add a function: `fetchActivePersonas()` to call `GET /api/personas/list_active`.
    *   Add a function: `tagPostForPersonaResponse(postId, personaId)` to call `POST /api/posts/<post_id>/tag_persona`.
*   **JavaScript (`static/js/ui.js`):**
    *   May contain helper functions for creating, showing, hiding, and managing the suggestion list UI elements (both for `@mention` and the standalone tagging field), including filtering logic if centralized.

## Mermaid Diagram (Illustrative Flow):

```mermaid
graph TD
    subgraph UserAction_NewPost
        A1[User types @ in Editor] --> B1{Frontend JS (editor.js)};
        B1 -- Detects @ --> C1[API Call: GET /api/personas/list_active];
        C1 --> D1[Persona List Data];
        D1 --> B1;
        B1 -- Filters/Displays Suggestions --> A1;
        A1 -- Selects Persona --> B1;
        B1 -- Inserts @[Name](id) --> E1[Editor Content];
        A1 -- Submits Post --> F1[Frontend JS (forum.js)];
        F1 -- Content w/ Tags --> G1[Backend API: Create Post/Reply];
    end

    subgraph UserAction_TagExistingPost
        A2[User interacts with Tag Field] --> B2{Frontend JS (forum.js)};
        B2 -- Types Persona Name --> C1;
        D1 --> B2;
        B2 -- Filters/Displays Suggestions --> A2;
        A2 -- Selects Persona --> B2;
        B2 -- post_id, persona_id --> H1[Backend API: POST /posts/.../tag_persona];
    end

    subgraph BackendProcessing
        G1 -- Parse Tags, Save Post --> I1[DB: posts (content, tagged_personas_in_content)];
        I1 --> J1[DB: Add to llm_requests];
        H1 -- Save Tag --> K1[DB: post_persona_tags];
        K1 --> J1;
        J1 --> L1[LLM Worker];
        L1 -- Fetches Persona, Post --> M1[Ollama/LLM Service];
        M1 -- LLM Response --> L1;
        L1 -- Saves Response --> I1_Reply[DB: posts (new reply)];
    end

    subgraph DisplayUpdate
        I1_Reply --> N1[Frontend Polls/Fetches Updates];
        N1 --> O1[Frontend JS (forum.js): renderPosts];
        O1 -- Renders new reply & highlights tags --> P1[User Browser: Updated View];
    end
```

## Phased Development Plan for Persona Tagging

This feature will be developed in three phases to manage complexity and allow for iterative implementation.

### Phase 1: Backend Foundation

**Goal:** Implement all necessary database changes and backend API endpoints to support persona tagging. The system should be able to receive tags, store them, and queue requests, but no frontend interaction will be built yet.

**Tasks:**

1.  **Database Schema Updates (`forllm_server/database.py`):**
    *   Modify the `posts` table to add the `tagged_personas_in_content` column (TEXT, for JSON array of persona IDs).
    *   Create the new `post_persona_tags` table schema (`tag_id`, `post_id`, `persona_id`, `tagged_by_user_id`, `created_at`).
    *   Update `init_db()` to reflect these changes and handle schema migration if necessary.
2.  **Persona List API Endpoint (`forllm_server/routes/persona_routes.py`):**
    *   Implement `GET /api/personas/list_active` to return a sorted list of active personas (`persona_id`, `name`).
3.  **Update Post Creation/Reply Endpoints (`forllm_server/routes/forum_routes.py`):**
    *   Modify `POST /api/subforums/<subforum_id>/topics` and `POST /api/topics/<topic_id>/posts`.
    *   Add logic to parse `@[Persona Name](persona_id)` tags from the input `content`.
    *   Store extracted `persona_id`s into `posts.tagged_personas_in_content`.
    *   For each unique tagged persona, add a corresponding request to the `llm_requests` table.
4.  **New Tagging Endpoint for Existing Posts (`forllm_server/routes/llm_routes.py`):**
    *   Implement `POST /api/posts/<int:post_id>/tag_persona`.
    *   This endpoint will accept `persona_id` in the request body.
    *   Add a record to `post_persona_tags`.
    *   Add a corresponding request to the `llm_requests` table.
5.  **LLM Worker Adaptation (`forllm_server/llm_queue.py`, `forllm_server/llm_processing.py`):**
    *   Verify that the LLM worker correctly uses the `persona_id` from `llm_requests` items to fetch the appropriate persona instructions for processing.

### Phase 2: Frontend JavaScript Core Logic

**Goal:** Implement the JavaScript functionality for both `@mention` tagging in the editor and the dedicated tagging field for existing posts. This phase focuses on functionality; styling will be minimal.

**Tasks:**

1.  **API Utility Functions (`static/js/api.js`):**
    *   Create `fetchActivePersonas()` to call the new persona list API.
    *   Create `tagPostForPersonaResponse(postId, personaId)` to call the new endpoint for tagging existing posts.
2.  **Editor Integration (`static/js/editor.js`):**
    *   Add event listeners to EasyMDE instances for `@` character detection.
    *   On detection, call `fetchActivePersonas()`.
    *   Implement basic UI (e.g., an unstyled list) to display persona suggestions.
    *   Implement real-time filtering logic for the suggestion list as the user types after `@`.
    *   Handle selection from the list: insert `@[Persona Name](persona_id)` into the editor's value. (Visual flare in editor can be deferred to Phase 3).
3.  **Forum Interaction Logic (`static/js/forum.js`):**
    *   Modify `addTopic()` and `submitReply()` to ensure they send the raw editor content (now potentially containing hidden tags).
    *   **Tagging Existing Posts:**
        *   Implement basic functionality for the "Tag Persona to Respond" feature. This includes an input field.
        *   On input in this field, fetch/filter personas and display a basic suggestion list.
        *   On selection, call `tagPostForPersonaResponse()` from `api.js`.
    *   **Rendering Tagged Content (Basic):**
        *   In `renderPosts()`, add initial logic to find `@[Persona Name](persona_id)` patterns in post content and replace them with a simple visual marker like `@{Persona Name}` for now. Full styling deferred.

### Phase 3: Frontend Presentation (HTML/CSS) & Documentation Update

**Goal:** Finalize the user interface with proper HTML structure and CSS styling for all tagging-related elements. Update the main `blueprint.md` to reflect the new feature.

**Tasks:**

1.  **HTML Structure (`templates/index.html`):**
    *   Implement the final HTML for the `@mention` suggestion list container.
    *   Implement the final HTML structure for the "Tag Persona to Respond" section below posts.
2.  **CSS Styling (`static/css/forum.css`, `static/css/components.css`, `static/css/editor.css`):**
    *   Style the `@mention` suggestion list (positioning, appearance, item hover/selection).
    *   Style the visual flare for `@Persona Name` tags within rendered post content (and, if feasible, in the EasyMDE preview).
    *   Style tooltips for tagged personas (if implemented).
    *   Style the "Tag Persona to Respond" input field, button, and its suggestion list.
3.  **JavaScript Refinements (Visuals & UX):**
    *   **`static/js/editor.js`**: Refine the visual display of `@Persona Name` within the EasyMDE preview if possible.
    *   **`static/js/forum.js`**:
        *   Update `renderPosts()` to use final HTML and CSS for displaying tagged personas in content.
        *   Implement and style tooltips on hover for tagged personas in rendered posts.
        *   Ensure the "Tag Persona to Respond" UI is fully styled and integrated.
    *   **`static/js/ui.js`**: Finalize any UI helper functions for suggestion lists, ensuring smooth interactions.
4.  **Documentation (`blueprint.md` Update):**
    *   Update the "Database Schema (`forllm_data.db`)" section with the new `posts.tagged_personas_in_content` column and the `post_persona_tags` table.
    *   Update "File Responsibilities" for `forllm_server/routes/persona_routes.py`, `forllm_server/routes/forum_routes.py`, and `forllm_server/routes/llm_routes.py` to reflect new/modified API endpoints.
    *   Modify the "Inter-Persona Communication (Tagging)" feature description under "Phase 4: Advanced LLM Interactions & Integrations" to indicate its implementation through `@mention` and dedicated field tagging, referencing the `@[Persona Name](persona_id)` format and the new UI elements.
    *   Ensure the high-level architecture diagram and description are still accurate or update as needed.

