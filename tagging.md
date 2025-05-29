# Persona Tagging Feature Plan

**Feature Goal:** Implement a persona tagging system in FORLLM to trigger asynchronous LLM responses from tagged personas in new posts/replies and via a dedicated tagging field for existing persona posts.

**Plan:**

This feature requires coordinated changes across the frontend (HTML, CSS, JavaScript) and the backend (Python/Flask, Database).

## 1. Database Modifications:

*   **`posts` table:** Add a new column, `tagged_personas_in_content` (TEXT/JSON), to store a list of persona IDs tagged within the post/reply *body* content. This will store the `persona_id`s extracted from the `@[Persona Name](persona_id)` format.
*   **New table `post_persona_tags`:** Create a new table specifically for tagging *existing* persona posts for a response.
    *   `tag_id` (INTEGER PRIMARY KEY)
    *   `post_id` (INTEGER, Foreign Key to `posts.post_id` - the existing post being responded to)
    *   `persona_id` (INTEGER, Foreign Key to `personas.persona_id` - the persona being tagged to respond)
    *   `tagged_by_user_id` (INTEGER, Foreign Key to `users.user_id` - the user who applied the tag)
    *   `created_at` (DATETIME)
    *   This table fulfills the requirement for a "new field" below existing persona posts.

## 2. Backend (Python/Flask) Modifications:

*   **API Endpoint for Persona List:** Create a new API endpoint (e.g., `GET /api/personas/list`) in [`forllm_server/routes/persona_routes.py`](forllm_server/routes/persona_routes.py) that returns a list of all available personas (`persona_id`, `name`), sorted alphabetically by name. This will feed the frontend's suggestion list.
*   **Modify Post/Reply Creation Endpoint:** Update the `POST /api/subforums/<subforum_id>/topics` (for new topics/initial posts) and `POST /api/topics/<topic_id>/posts` (for replies) endpoints in [`forllm_server/routes/forum_routes.py`](forllm_server/routes/forum_routes.py).
    *   These endpoints will receive the post/reply content from the frontend.
    *   Parse the content to identify `@[Persona Name](persona_id)` tags using a regular expression.
    *   Extract the `persona_id`s from the parsed tags.
    *   Store the extracted `persona_id`s in the new `tagged_personas_in_content` column in the `posts` table (as a JSON array).
    *   For each extracted `persona_id`, add a new entry to the `llm_requests` table, linking it to the newly created post (`post_id_to_respond_to`) and the tagged `persona_id`. Set the status to 'pending'.
*   **New API Endpoint for Tagging Existing Persona Posts:** Create a new API endpoint (e.g., `POST /api/posts/<post_id>/tag_persona`) in [`forllm_server/routes/llm_routes.py`](forllm_server/routes/llm_routes.py).
    *   This endpoint will accept the `post_id` of the existing post (which could be a user or persona post) and the `persona_id` to tag.
    *   Add a new entry to the `post_persona_tags` table, recording the `post_id`, `persona_id`, and the current user's ID.
    *   Add a new entry to the `llm_requests` table, linking it to the `post_id` and the tagged `persona_id`. Set the status to 'pending'.
*   **Modify Post Fetching Logic:** Update the backend logic that fetches posts (in [`forllm_server/routes/forum_routes.py`](forllm_server/routes/forum_routes.py)) to include the `tagged_personas_in_content` data and potentially fetch related data from the `post_persona_tags` table for rendering the new tagging field UI.
*   **Modify LLM Worker:** Update the background LLM worker in [`forllm_server/llm_queue.py`](forllm_server/llm_queue.py) and [`forllm_server/llm_processing.py`](forllm_server/llm_processing.py).
    *   The worker should process requests from the `llm_requests` table.
    *   When processing a request, it needs to determine the target post (`post_id_to_respond_to`) and the specific `persona_id` requested. This information will come directly from the `llm_requests` entry, which is populated by either the post creation endpoint (for body tags) or the new tagging endpoint (for field tags).
    *   Ensure the correct persona's prompt instructions are fetched and used for generating the response.

## 3. Frontend (HTML, CSS, JavaScript) Modifications:

*   **HTML (`templates/index.html`):**
    *   Add a container element near the EasyMDE editor instances (`newTopicEditor`, `replyEditor`) to serve as the display area for the persona suggestion list (an `@mention` dropdown).
    *   Modify the post rendering structure to include a dedicated area/field below each rendered post (especially persona posts) where users can select personas to tag that specific post for a response. This might involve adding a new `div` with a dropdown or a similar interactive element within the `renderPostNode` function in `static/js/forum.js`.
*   **CSS (`static/css/forum.css`):**
    *   Add styles for the `@mention` suggestion list (positioning, appearance, hover states).
    *   Add styles for the visual flare of recognized persona tags within the post content (e.g., a subtle background color, border, or distinct text style). Ensure it's distinct but not overly distracting.
    *   Add styles for the new tagging field/area below posts.
    *   Add styles for the tooltip that appears on hover over a tagged persona.
*   **JavaScript (`static/js/editor.js`, `static/js/forum.js`, `static/js/api.js`, `static/js/ui.js`, `static/js/personas.js`):**
    *   **Editor Integration (`static/js/editor.js`):**
        *   Add event listeners to the EasyMDE editor instances to detect user input, specifically the `@` character followed by potential persona name characters.
        *   When an `@mention` sequence is detected, call a function to fetch the persona list (using the new API endpoint) and display the suggestion list near the cursor.
        *   Implement filtering logic for the suggestion list as the user types.
        *   Handle selection from the suggestion list: Replace the `@mention` text with the internal `@[Persona Name](persona_id)` format in the editor's value, but render it visually to the user as `@Persona Name` with the defined visual flare. This requires careful handling of EasyMDE's content and preview.
        *   Implement the visual flare and tooltip functionality for tagged personas within the editor's preview.
    *   **Forum Logic (`static/js/forum.js`):**
        *   Modify `addTopic` and `submitReply` functions to ensure the full content from the editor (including the `@[Persona Name](persona_id)` tags) is sent to the backend.
        *   Update `renderPosts` to:
            *   Display the visual flare for tagged personas within the post content based on the `tagged_personas_in_content` data.
            *   Render the new tagging field below each post.
            *   Populate the tagging field with a dropdown/selectable list of personas (using the new API endpoint).
            *   Implement the logic for selecting a persona in this new field.
            *   When a persona is selected in the new field, call the new `POST /api/posts/<post_id>/tag_persona` endpoint.
            *   Display any personas already tagged on this post via the new field.
        *   Implement tooltip display on hover for tagged personas in rendered posts.
    *   **API Interaction (`static/js/api.js`):** Add functions to call the new `GET /api/personas/list` and `POST /api/posts/<post_id>/tag_persona` endpoints.
    *   **UI Helpers (`static/js/ui.js`):** Add helper functions for managing the display, filtering, and positioning of the `@mention` suggestion list.
    *   **Personas Module (`static/js/personas.js`):** May need minor updates to integrate with the new persona listing API.

## 4. Workflow:

1.  **Tagging in New Post/Reply:**
    *   User types `@` in the editor.
    *   Frontend displays filtered persona suggestions.
    *   User selects a persona.
    *   Frontend inserts `@[Persona Name](persona_id)` (hidden) and displays `@Persona Name` with visual flare (visible).
    *   User submits post/reply.
    *   Frontend sends content with hidden tags to backend.
    *   Backend parses tags from content, saves post, and queues LLM requests for each tagged persona in `llm_requests`.
2.  **Tagging Existing Persona Post:**
    *   User views a post (especially a persona post).
    *   User interacts with the new tagging field below the post.
    *   Frontend displays selectable persona list.
    *   User selects a persona.
    *   Frontend calls the new `POST /api/posts/<post_id>/tag_persona` endpoint.
    *   Backend records the tag in `post_persona_tags` and queues an LLM request in `llm_requests` for the tagged persona to respond to the specified `post_id`.
3.  **LLM Processing:**
    *   The background LLM worker processes 'pending' requests from the `llm_requests` table according to the schedule.
    *   For each request, it uses the specified `persona_id` and the content of the `post_id_to_respond_to` to generate a response.
    *   The response is saved as a new post, linked as a reply to the original post.
4.  **Display:**
    *   Frontend fetches updated posts.
    *   `renderPosts` displays the new replies and applies the visual flare to tagged personas in the content of existing posts.

## Mermaid Diagram:

```mermaid
graph TD
    A[User] --> B(Frontend UI);
    B --> C{Editor / Tagging Field};
    C -- Type @ / Interact with Field --> D[Fetch Personas API];
    D --> E[Persona List];
    E --> C;
    C -- Select Persona --> F[Insert Tag / Trigger Tagging Endpoint];
    F -- New Post/Reply --> G[Backend API: Create Post/Reply];
    G -- Parse Tags from Content --> H[Database: Save Post (with tagged_personas_in_content)];
    H --> I[Database: Add LLM Requests to Queue];
    F -- Tag Existing Post --> J[Backend API: Tag Existing Post];
    J --> K[Database: Save Tag (post_persona_tags)];
    K --> I;
    I --> L[LLM Worker (Background)];
    L -- Process Request --> M[Ollama Instance];
    M --> L;
    L -- Save Response --> H;
    H --> N[Frontend UI: Display New Posts/Replies];
    N --> B;

    subgraph Frontend
        B
        C
        F
        N
    end

    subgraph Backend
        G
        J
        H
        I
        K
        L
        D
        E
    end

    subgraph External
        M
    end