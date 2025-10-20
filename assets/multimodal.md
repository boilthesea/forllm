# Multimodal Integration Plan for FORLLM

This document outlines the phased development plan for integrating image, video, and audio generation (eventually both text to speech and music) capabilities into the FORLLM application. The plan is based on a detailed analysis of the existing architecture and a series of design decisions.

## Phase 1: Backend Refactoring and Core API [DONE]

**Goal:** Rearchitect the backend to support multiple, diverse content generators and establish the foundational database changes and API endpoints. This phase is non-visual but critical for all subsequent work.

1.  **Unified Database Strategy:**
    *   In `forllm_server/database.py`, all schema changes will be made to the main `forllm_data.db` file to create a centralized media library. The miniapp-specific databases (`forllm_audio.db`, etc.) will only store metadata unique to their domain (e.g., project structures, chapter lists).
    *   **New Table (`generated_media`):** Add a new table to track all generated media files from all sources (inline forum commands and miniapps). This provides a single source for features like the "Recent Media" panel.
        ```sql
        CREATE TABLE IF NOT EXISTS generated_media (
            media_id INTEGER PRIMARY KEY AUTOINCREMENT,
            llm_request_id INTEGER NOT NULL,
            source_app TEXT NOT NULL, -- 'forum', 'audiobook', 'music', 'image_app', 'video_app'
            media_type TEXT NOT NULL, -- 'image', 'audio', 'video'
            file_path TEXT NOT NULL,
            prompt TEXT, -- The final prompt used for generation
            project_id INTEGER, -- Optional, links to a project in a miniapp's DB
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (llm_request_id) REFERENCES llm_requests(request_id)
        );
        ```
    *   **`posts` Table Migration:**
        *   Add a new column `content_structured` (TEXT) to the `posts` table.
        *   Implement a one-time migration logic within `init_db()` to populate `content_structured` for all existing posts, converting their plain-text `content` into the new JSON array format (e.g., `[{ "type": "text", "data": "..." }]`).

2.  **Backend Architecture Refactoring:**
    *   Create a new directory: `forllm_server/generators/`.
    *   Define a base class `BaseGenerator` in `forllm_server/generators/base.py` with an abstract `generate(request_details)` method.
    *   Move and refactor the existing text generation logic from `llm_processing.py` into a new `forllm_server/generators/ollama_connector.py` that inherits from `BaseGenerator`.
    *   Create placeholder connector files for the new services: `diffusers_connector.py`, `tts_connector.py`, `music_connector.py`, and `video_connector.py`.

3.  **Dispatcher Implementation:**
    *   Modify the `llm_worker` in `llm_queue.py` to act as a pure dispatcher.
    *   The worker will read a request's `request_type` and use a dictionary to map it to the appropriate generator class (e.g., `'generate_image' -> DiffusersConnector`).
    *   The worker will instantiate the mapped connector and call its `generate()` method, delegating all further processing.

4.  **New API Endpoints:**
    *   Create a new file `forllm_server/routes/generation_routes.py` and register its Blueprint.
    *   Implement the API endpoint for post-generation actions (e.g., `POST /api/generation/queue_from_post`). This endpoint will take a `post_id`, `generation_type`, prompt, and parameters, and create the corresponding entry in the `llm_requests` table.

## Phase 2: UI for Core Navigation and Settings [DONE]

**Goal:** Implement the user-facing UI for navigating between different application modes and configuring the new services.

1.  **Two-Tier Navigation UI:**
    *   In `static/js/ui.js` and `templates/index.html`, implement the new two-level navigation system.
    *   **Top-Level App Switcher:** Replace the static "Subforums" title with a custom dropdown component that acts as the "App Switcher." This dropdown will contain the top-level apps: "Forum," "Audio," and "Visual."
    *   **Secondary App Navigation:** When a user selects an app from the switcher (e.g., "Audio"), the sidebar area (currently used for the subforum list) will dynamically update to show that app's specific navigation links (e.g., "Audiobooks," "Music").
    *   Implement the JavaScript logic to manage the state of the App Switcher and render the correct secondary navigation links in the sidebar.

2.  **Settings Page UI:**
    *   In `static/js/settings.js` and `templates/index.html`, add new tabs to the Settings modal for "Images," "Video," "Text to Speech," and "Music."
    *   Each tab will contain form fields for configuring the respective services (e.g., Hugging Face model name for `diffusers`, video generation API URL).
    *   Implement the JavaScript to save these new settings via API calls.

3.  **`@optimize` Persona Implementation:**
    *   **Reserved Name:** Implement backend validation to prevent users from creating a persona named "optimize".
    *   **System-Level Prompt:** Define the default optimizer prompt as a system-level constant in `forllm_server/config.py`.
    *   **Settings UI:** Add a dedicated "Prompt Optimizer" section to the Settings UI. This section will display the default system prompt and provide a textarea for the user to enter their own override. This override will be saved to the `settings` table. A "Restore Default" button will clear the override.
    *   **Processing Logic:** When handling an `@optimize` request, the backend will use the user's override from the settings if it exists; otherwise, it will fall back to the system default constant.

4.  **Modularize Recent Activity Landing Page:**
    *   Implement areas on the main recent activity page to show new types of content, such as recent pictures, videos, audiobooks, and music, by querying the new central `generated_media` table.
    *   The page should be constructed to show the desired sections depending on whether it's the main landing page or a view within a specific miniapp.

5.  **Update Documentation Plan:**
    *   Add subphase 8.2 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to reflect the new UI navigation and settings configurations.

## Phase 3: Inline Generation and Post-Generation Actions [DONE]

**Goal:** Implement the core user workflows for generating multimodal content directly within the forum interface.

1.  **Backend Command Parsing:**
    *   In `forllm_server/routes/forum_routes.py`, extend the regex-based parsing to recognize the new command syntax (`$image`, `$video`, `$tts(...)`, `$music(...)`, `@optimize:$image`, etc.).
    *   Update the logic to create the appropriate `llm_requests` entries with the correct `request_type`, `request_params`, and `parent_request_id` for chains.

2.  **Frontend Post Rendering:**
    *   Modify the `renderPostNode` function in `static/js/forum.js` to handle the new `content_structured` JSON format.
    *   It should loop through the content blocks and render appropriate HTML for each type (`<p>` for text, `<img>` for images, `<audio>` for audio, `<video>` for video).
    *   Implement the display logic for "pending" and "error" states for generated content.

3.  **Post-Generation Actions UI:**
    *   In `renderPostNode`, add the new "Generate Image," "Generate Video," "Generate TTS Audio," and "Generate Music" options to the "..." menu.
    *   Create a new, reusable modal component for generation parameters.
    *   In the `postList` event listener, add handlers for the new menu options that open this modal, pre-filled with the post's content.

4.  **Update Documentation Plan:**
    *   Add subphase 8.3 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to reflect the new inline generation commands and post-generation action UI.

## Phase 4: Full Service Integration and First-Use Experience [WIP]

**Goal:** Complete the integration with the external generation services and ensure the features are fully functional end-to-end.

1.  **Implement `diffusers` Connector:** 
    *   In `diffusers_connector.py`, write the code to integrate with the Hugging Face `diffusers` library.
    *   This involves importing a pipeline, loading the specified model from settings, and calling it with the prompt.
    *   The result will be a PIL Image object, which the connector must then save to a file in the `media/images/` directory before creating the corresponding entry in the central `generated_media` table.
    *   The connector should be designed to optionally (in settings) allow the load a model into memory once on startup of the image or video app to avoid long load times for each request. This should not load a model on the start of the forllm app overall since most inference is queued and inference occurs across different model types, mostly through ollama.

2.  **Implement `kokoro` (TTS) Connector:** [DONE]
    *   In `tts_connector.py`, write the code to connect to the kokoro library, submit text, and handle the audio file result.
    *   The connector will save the generated audio to `media/audio/` and update the `generated_media` table.

3.  **Implement `Ace-step` (music) Connector:**
    *   In `music_connector.py`, write the code to integrate with Ace-step.
    *   Assume Ace-step will be installed to /forllm_server/generators/Ace-step/ via the pip install git+https://github.com/ace-step/ACE-Step.git method.
    *   The connector will save generated music to `media/music/` directory and create the corresponding entry in the central `generated_media` table.

4.  **Implement `@optimize` Logic:**
    *   In the `ollama_connector.py`, add logic to handle requests where the `request_type` is `optimize_prompt`. It will use the system prompt (or the user's override) to transform the input text.

5.  **Update Documentation Plan:**
    *   Add subphase 8.4.1 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to reflect the full integration of the `diffusers` and `kokoro` services. 

6.  **Update `readme.md` installation instructions:**
    *   Diffusers, kokoro, ace-step all have installation requirements that need to be documented.

## Phase 5: Audiobook Miniapp Integration [WIP]

**Goal:** Implement a self-contained "Audiobook" miniapp within forllm, leveraging the kokoro engine to convert user-provided ebooks into playable audiobooks.

### 5.1. Database and File Structure [DONE]

*   **New Database (`forllm_audio.db`):**
    *   A separate SQLite database will be created to manage audiobook-specific metadata.
    *   A new database connection handler will be implemented.
*   **New Directory (`media/audiobooks/`):**
    *   A directory to store the final `.m4b` audiobook files. The path will be configurable in the settings.

### 5.2. Database Schema for `forllm_audio.db`

```sql
CREATE TABLE IF NOT EXISTS audiobooks (
    book_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    cover_image_path TEXT, -- Path to a cached cover image
    source_file_hash TEXT NOT NULL UNIQUE, -- SHA256 hash of the original ebook to prevent duplicates
    output_file_path TEXT, -- Final path to the generated .m4b file
    status TEXT NOT NULL DEFAULT 'pending_extraction', -- 'pending_extraction', 'pending_user_review', 'queued', 'processing', 'completed', 'error'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audiobook_chapters (
    chapter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    extracted_text TEXT NOT NULL, -- The full, cleaned text of the chapter
    llm_request_id INTEGER, -- Links to the specific chapter job in the main DB's llm_requests table
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'queued', 'processing', 'completed', 'error'
    FOREIGN KEY (book_id) REFERENCES audiobooks(book_id)
);
```

### 5.3. Ebook Ingestion and Processing Workflow [DONE]

This workflow is designed to be robust and decoupled from the original source file.

1.  **User Action:** The user selects the "Audiobooks" app from the new App Switcher UI and clicks an "Open Ebook" button.
2.  **File Selection:** A native file dialog prompts the user to select a Calibre-compatible ebook.
3.  **Immediate Processing:**
    *   The backend receives the file path.
    *   It immediately calls a new `calibre_handler.py` module (inspired by the `audiblez` logic).
    *   This handler uses the Calibre `ebook-convert` command-line tool to convert the source ebook into an intermediate `HTMLZ` format.
    *   The `HTMLZ` is unzipped, and `BeautifulSoup` is used to parse the HTML and `metadata.opf` file.
4.  **Data Extraction and Storage:**
    *   Metadata (title, author, cover) and chapter content (split by `<h1>`/`<h2>` tags) are extracted.
    *   A new entry is created in the `audiobooks` table with a status of `pending_user_review`.
    *   Each extracted chapter's title and cleaned text is saved as a new entry in the `audiobook_chapters` table, linked to the parent book.
5.  **UI Population:** The extracted data is sent back to the frontend, which populates the two-pane generation UI for user review.

### 5.4. Generation UI (Two-Pane Layout) [DONE]

Once a book is processed, the user is presented with a dedicated two-pane interface:

*   **Left Pane (Controls):**
    *   **Open Ebook Button:** To start a new conversion.
    *   **Chapter List:** A selectable list of all extracted chapters. Users can deselect non-content chapters (e.g., "Title Page," "Copyright").
    *   **Settings:**
        *   **Voice Selector:** A dropdown to choose the TTS voice (with a default set in the main app settings).
        *   Other parameters (speed, etc.) as needed.
    *   **Action Buttons:**
        *   **Queue Audiobook:** The primary action.
        *   **Run Now (Optional):** For immediate, synchronous processing with a blocking progress bar.
    *   **Status Area:** A progress indicator for active jobs.

*   **Right Pane (Preview & Metadata):**
    *   **Top Section:** Displays the book's cover image, title, and author.
    *   **Bottom Section:** A large, scrollable text area that displays the full text of the chapter currently selected in the left pane, allowing the user to verify the content.

### 5.5. Background Queuing and Processing [TODO]

This leverages the existing `llm_requests` queue with a parent/child dependency model.

1.  **User Action:** The user clicks "Queue Audiobook."
2.  **Parent Job Creation:**
    *   A single "parent" request is created in the `llm_requests` table in `forllm_data.db`.
    *   `request_type`: `generate_audiobook_parent`
    *   `request_params`: JSON containing the `book_id` from `forllm_audio.db`.
    *   This parent job will be the only one visible in the main queue UI.
3.  **Child Job Creation:**
    *   For each *selected* chapter in the UI, a corresponding "child" request is created in `llm_requests`.
    *   `request_type`: `generate_audiobook_chapter`
    *   `request_params`: JSON containing the `chapter_id` from `forllm_audio.db`.
    *   `parent_request_id`: The ID of the parent job created above.
    *   `status`: `pending_dependency`.
4.  **Processing Logic (`tts_connector.py`):**
    *   The `llm_worker` will have a new handler for `generate_audiobook_chapter`.
    *   The `tts_connector` will:
        1.  Use the `chapter_id` to query `forllm_audio.db` and retrieve the `extracted_text`.
        2.  Implement the refined, in-memory streaming architecture discussed in `kokoro_core.md`. Text will be fed segment-by-segment (where a segment is a user adjustable number of sentences anywhere from 1 to 5) to the TTS engine, and the resulting audio chunks will be piped directly to a single `ffmpeg` process via `stdin`.
        3.  Each chapter will be saved as a temporary `.wav` or `.mp3` file.
5.  **Final Assembly:**
    *   Once all child jobs for a parent are `complete`, the `llm_worker` will trigger a final assembly job.
    *   This job will use `ffmpeg` to concatenate all temporary chapter audio files, embed the book's metadata and cover image, and write the final `.m4b` file to the `media/audiobooks/` directory.
    *   The `audiobooks.output_file_path` and `status` will be updated in `forllm_audio.db`. The final file path will also be recorded in the main `generated_media` table.

### 5.6. Audiobook Library and Player UI [TODO]

*   **Library View:**
    *   The main view of the "Audiobooks" app will be a grid or list displaying the cover, title, and author of all `completed` audiobooks.
    *   This view is populated by querying the `audiobooks` table in `forllm_audio.db`.
*   **Player View:**
    *   Clicking a book in the library navigates to a dedicated player view.
    *   This view will feature:
        *   Large cover art.
        *   Standard playback controls (play/pause, seek bar, volume).
        *   A chapter selection dropdown/list to navigate the audiobook.
        *   The player will use the `output_file_path` from the database to load the correct `.m4b` file.

### 5.7  **Update Documentation Plan:** [TODO]
    *   Add subphase 8.5 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to describe the new Audiobook miniapp's architecture, database schema, and UI/UX flow.

## Phase 6: Music Miniapp Integration [TODO]

**Goal:** Implement a self-contained "Music" miniapp within forllm, leveraging a generative music model to create audio from user prompts.

### 6.1. Database and File Structure

*   **New Database (`forllm_music.db`):**
    *   A separate SQLite database to manage music-specific project metadata.
*   **New Directory (`media/music/`):**
    *   A directory to store generated `.wav` or `.mp3` music files, configurable in settings.

### 6.2. Database Schema for `forllm_music.db`

```sql
CREATE TABLE IF NOT EXISTS music_projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT,
    status TEXT NOT NULL DEFAULT 'wip', -- 'wip', 'completed', 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3. Music Generation UI (Hybrid Model)

The "Music" miniapp, accessible via the App Switcher and its secondary navigation, will feature a hybrid UI for simple and advanced use.

*   **Default View (Simple Generation):**
    *   A large text input for the music prompt.
    *   Controls for basic parameters (e.g., duration, style).
    *   A "Generate" button that queues a single, non-project-based track.
    *   A list or grid of recent, non-project-based generations for quick playback (queried from the central `generated_media` table).

*   **Project View (Advanced):**
    *   A button to "Create New Song" or switch to the project library.
    *   The project library will display all existing `music_projects`.
    *   Opening a project will navigate to a dedicated two-pane layout for managing the tracks within that project.

### 6.4. Background Queuing and Processing

This will leverage the existing `llm_requests` queue.

1.  **User Action:** The user submits a prompt from either the simple or project view.
2.  **Job Creation:**
    *   A request is created in the `llm_requests` table in `forllm_data.db`.
    *   `request_type`: `generate_music_track`
    *   `request_params`: JSON containing the `prompt`, `project_id` (if applicable), and other generation parameters.
3.  **Processing Logic (`music_connector.py`):**
    *   The `llm_worker` will have a new handler for `generate_music_track`.
    *   The `music_connector` will:
        1.  Interact with the configured music generation model.
        2.  Save the resulting audio file to the `media/music/` directory.
        3.  Create an entry in the central `generated_media` table, including the `llm_request_id`, `source_app` ('music'), `media_type` ('audio'), `file_path`, and `project_id` (if applicable).

### 6.5  **Update Documentation Plan:**
    *   Add subphase 8.6 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to describe the new Music miniapp's architecture, database schema, and UI/UX flow.

## Phase 7: Visual Miniapp Integration [TODO]

**Goal:** Implement a self-contained "Visual" miniapp for image and video generation, mirroring the hybrid simple/project-based structure.

### 7.1. Database and File Structure

*   **New Database (`forllm_visual.db`):**
    *   A separate SQLite database to manage visual-specific project metadata.
*   **New Directories:**
    *   `media/images/`: For storing generated images.
    *   `media/videos/`: For storing generated videos.

### 7.2. Database Schema for `forllm_visual.db`

```sql
CREATE TABLE IF NOT EXISTS image_projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'wip', -- 'wip', 'completed', 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS video_projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'wip',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3. Visual App UI and Workflow

The "Visual" app, a top-level entry in the App Switcher, will have secondary navigation links for "Images" and "Videos".

*   **Images Section:**
    *   Will follow the hybrid model from the Music miniapp, with a simple prompt-to-image default view and a more structured, project-based workflow.
*   **Videos Section:**
    *   Will also follow the hybrid model, supporting both simple inline/UI generation and a more advanced project-based workflow for creating multi-clip videos.

### 7.4. Background Queuing and Connectors

*   **New Connectors:**
    *   The `diffusers_connector.py` will be enhanced to handle project-based logic.
    *   A new `video_connector.py` will be created in `forllm_server/generators/`.
*   **Request Types:**
    *   New `request_type` values will be used (e.g., `generate_image`, `generate_video`).
    *   The `llm_worker` will dispatch these to the appropriate connectors.
*   **Processing Logic:**
    *   Upon completion, both connectors will save the generated file and create a corresponding entry in the central `generated_media` table, setting the `source_app`, `media_type`, and optional `project_id`.

### 7.5. Finalizing Changes in Other Phases

*   **Phase 2 (Settings):**
    *   The Settings modal will be updated with a "Video" tab.
    *   A checkbox for "Vision Enabled" will be added next to each model in the main Ollama settings.
*   **Phase 3 (Inline Generation):**
    *   The backend command parsing will be updated to handle the `$video(...)` command.
    *   The "..." menu on posts will get a "Generate Video from Post" option.

### 7.6  **Update Documentation Plan:**
    *   Add subphase 8.7 to Phase 8, outlining the `blueprint.md` sections that will need to be updated to describe the new Visual miniapp's architecture, database schema, and UI/UX flow.

## Phase 8: Update assets/Blueprint.md to reflect the new multimodal update

Review blueprint.md and compare it to this phased development plan, read whatever code is necessary to update blueprint.md to reflect the changes this multimodal update has made to the codebase.

1.  **Phase 8.1: Document Phase 1 Changes**
    *   **`forllm_server/database.py`**: Update the description to include the new `generated_media` table and the `content_structured` column in the `posts` table. Mention the one-time data migration.
    *   **`forllm_server/llm_processing.py`**: Update its responsibility to focus only on history-building logic, noting that the core request processing has been moved.
    *   **`forllm_server/llm_queue.py`**: Update the `llm_worker` description to reflect its new role as a dispatcher that maps `request_type` to generator classes.
    *   **`forllm_data.db`**: In the database file description, add entries for the new `generated_media` table and the `content_structured` column under the `posts` table.
    *   **New Files/Directories**: Add entries for the new `forllm_server/generators/` directory and its contents (`base.py`, `ollama_connector.py`, etc.), and for `forllm_server/routes/generation_routes.py`. Describe their primary responsibilities.

2.  **Phase 8.2: Document Phase 2 Changes**
    *   **`templates/index.html`**: Update the description of the `#subforum-nav` element to reflect its new role as a dynamic two-tier navigation container, managed by the "App Switcher."
    *   **`static/js/ui.js`**: Update its description to include the management of the new App Switcher and the dynamic rendering of secondary navigation links.
    *   **`static/js/settings.js`**: Update its description to mention handling the new settings tabs and form fields for Images, Video, Text to Speech, Music, and the Prompt Optimizer.
    *   **`forllm_server/config.py`**: Add a note about the new `DEFAULT_OPTIMIZER_PROMPT` constant for the `@optimize` feature.
    *   **`forllm_server/llm_queue.py`**: Update its description to include the validation that prevents a user from creating a persona with the reserved name "optimize".
    *   **`forllm_server/routes/activity_routes.py`**: Update its description to include the new `/api/activity/recent_media` endpoint for fetching recently generated media.
    *   **`forllm_server/database.py`**: Update its description to include the new `get_recent_media` function.
    *   **`static/js/activity.js`**: Update its description to mention fetching and rendering data from the new recent media endpoint.

3.  **Phase 8.3: Document Phase 3 Changes**
    *   **`forllm_server/routes/forum_routes.py`**: Update its description to include parsing for new generation commands (`$image`, `$video`, etc.) and chained commands with `@optimize`.
    *   **`static/js/forum.js`**: Update the `renderPostNode` function's description to mention handling the `content_structured` JSON format for rendering multimodal content, including pending/error states. Also, mention the addition of "Generate..." options to the post menu and the new `openGenerationModal` function.
    *   **`templates/index.html`**: Add a description for the new reusable `#generation-modal` component.
    *   **`static/js/main.js`**: Update its description to include the new event listener for handling submissions from the generation modal.

---

## Further Considerations

This section documents other areas of the application that will be impacted by the multimodal overhaul.

### 1. Token Estimation

*   **Impact:** The editor's token estimator is designed for text-only prompts. Commands like `$image(a long prompt)` will incorrectly contribute to the token count for text generation requests.
*   **Recommendation:**
    *   **Short-Term:** Modify the token estimation JavaScript to strip out any `$command(...)` blocks before sending the text to the estimation API.
    *   **Long-Term:** Enhance the token estimator UI to show a breakdown, e.g., "Text Tokens: 500, Image Prompt Tokens: 30".

### 2. Search Functionality

*   **Impact:** A future text-based search feature will need to be aware of the new `content_structured` JSON format.
*   **Recommendation:**
    *   The search backend logic should be designed to parse the `content_structured` JSON and only search on blocks where `type` is `text`.
    *   Extend search to index the `prompt` column of the `generated_media` table, allowing users to find posts based on the content of generated media.

### 3. Recent Activity Page

*   **Impact:** The "Recent Activity" page does not account for new media generations.
*   **Recommendation:**
    *   Add a new panel to the Recent Activity page titled "New Media" or "Recent Generations."
    *   This panel will be populated by querying the central `generated_media` table, joining with `llm_requests` and `posts` to provide context (e.g., "Image generated in topic 'My Trip to the Zoo'").

### 4. Error Handling and UX

*   **Impact:** Local generation libraries can encounter errors (e.g., out of memory).
*   **Recommendation:**
    *   The `generate()` method in each connector must have robust `try...except` blocks.
    *   When an error occurs, the connector should update the corresponding `llm_requests` entry with a `status` of 'error' and a clear `error_message`.
    *   The frontend rendering logic must correctly display this error state, providing the error message and a "Retry" button.

### 5. Resource Management

*   **Impact:** Image and video generation can be far more resource-intensive than text generation.
*   **Recommendation:**
    *   **Long-Term:** Consider adding a `priority` column to the `llm_requests` table. The `llm_worker` could be modified to fetch requests based on this priority (e.g., `ORDER BY priority DESC, requested_at ASC`). Text-based requests could be given a higher priority to ensure the forum remains interactive.

## Discussion of Specifics

### A. Proposed Syntax and Functionality

Let's use a new special character, the dollar sign (`$`), to signify a generation command.

**1. Simple Generation (Entire Post as Prompt):**

A user places a single command at the beginning or end of their post. This signals that the *entire post content* should be used as the prompt for the specified generator.

*   **Syntax:**
    *   `$image`
    *   `$tts`
    *   `$video`
    *   `$music`
*   **Example:**
    > `$image`\
    > A photorealistic image of a red panda programming on a laptop in a coffee shop.

**2. Dependant Generation (Chaining):**

The colon (`:`) syntax for chaining will be preserved and extended to handle complex, multi-modal conversations.

*   **Simple Persona-to-Generator:**
    *   **Syntax:** `@PersonaName:$tts`
    *   **Behavior:** The text output of `@PersonaName` is piped directly to the `$tts` generator.

*   **Complex Multi-Step Chains:**
    *   **Syntax:** `@Persona1:$image:@Persona2:$tts:@Persona3`
    *   **Behavior:** This creates a sequential chain of replies.
        1.  `@Persona1` responds to the user's post and generates an image.
        2.  `@Persona2` responds to `@Persona1`'s post.
        3.  `@Persona3` responds to `@Persona2`'s post.
    *   **Challenge:** How does `@Persona2`, a text-only LLM, "see" the image generated by `@Persona1`? This requires a fallback mechanism.

*   **Chat History Fallback for Media:**
    *   To ensure conversational continuity with text-only LLMs, any generated media in a post will be represented in the chat history sent to subsequent models as a structured, HTML-style tag.
    *   **Image Fallback:** `<img src="image1.png" alt="The prompt used to generate the image">`
    *   **Audio Fallback:** `<audio src="audio1.mp3" alt="The prompt used for the TTS or music generation">`
    *   This provides a descriptive placeholder, allowing the text-only LLM to understand that media was generated and what it represents.

*   **Handling Vision-Enabled Models:**
    *   The application settings will allow users to manually flag specific LLM models as "Vision Enabled."
    *   When a request is processed for a vision-enabled model, the backend will alter the payload. Instead of the HTML-style fallback, it will include the actual image data (e.g., as a base64-encoded string) in the prompt, allowing the model to "see" the image from the previous turn.

**3. Inline Generation (Specific Part of a Post):**

For generating content from only a portion of the text, we can use a syntax that wraps the prompt.

*   **Syntax:** `$command(prompt text)`
*   **Example:**
    > I was walking through the forest and I saw `$image(a majestic deer with glowing antlers)`. It was an incredible sight.
*   **Workflow:** The backend regex would specifically look for this `$...()` pattern, extract the inner text as the prompt, and queue a generation request. The original tag (`$image(...)`) would be replaced in the final post by the generated image.

**4. Parameterization:**

For adding parameters like image dimensions or voice selection, we can extend the inline syntax with key-value pairs, separated by a pipe `|`.

*   **Syntax:** `$command(prompt text | key1=value1 | key2=value2)`
*   **Example:**
    > `$image(a robot reading a book | aspect_ratio=16:9 | style=impressionist painting)`

This approach builds directly on the proven concepts in your existing code, which should simplify implementation significantly.

**5. Optimization Prompts:**

The most intuitive approach is to **treat prompt optimization as a distinct, chainable action** using a dedicated, reserved keyword.

### B. Proposed Syntax for Prompt Optimization

Let's use a special, reserved keyword, `optimize`, in the same way we use a persona name. This leverages the existing chaining syntax (`@Persona1:@Persona2`) that the backend is already built to handle.

**1. Chaining to a Generator:**

*   **Syntax:** `@optimize:$image`
*   **Example:**
    > `@optimize:$image`\
    > a cat
*   **Workflow:**
    1.  The system queues a request to a designated "prompt optimization" LLM with the prompt "a cat".
    2.  A second request is queued for the `$image` service, with a `status` of `pending_dependency` and a `parent_request_id` pointing to the optimization request.
    3.  The optimization LLM returns an enhanced prompt, for example: "A cinematic, photorealistic shot of a fluffy calico cat, sitting majestically on a velvet cushion, soft morning light filtering through a nearby window, detailed fur, sharp focus on its bright green eyes."
    4.  The `llm_worker` detects the completion, activates the `$image` request, and sends this new, optimized prompt to the `diffusers` connector.

**2. Chaining with a Persona and a Generator:**

*   **Syntax:** `@CreativeWriter:@optimize:$image`
*   **Example:**
    > `@CreativeWriter:@optimize:$image`\
    > Write a single sentence describing a futuristic city.
*   **Workflow:**
    1.  `@CreativeWriter` generates the sentence: "Gleaming chrome spires pierced the neon-purple clouds as flying vehicles zipped silently between floating sky-gardens."
    2.  `@optimize` takes that sentence and enhances it for an image generator: "Epic sci-fi concept art, a sprawling futuristic city with gleaming chrome spires... high detail, volumetric lighting, 8k."
    3.  `$image` receives the final, optimized prompt and generates the image.

**3. Inline Optimization:**

*   **Syntax:** `@optimize:$image(a cat)`
*   **Example:**
    > I would love to see `@optimize:$image(a picture of a dog)`.
*   **Workflow:** This would follow the same dependency chain, but the final generated image would replace the `@optimize:$image(a picture of a dog)` tag in the post.

**Advantages of this Approach:**

*   **Clarity:** The user can clearly read the flow of operations: "optimize this, then make an image."
*   **Extensibility:** It uses the exact same backend chaining logic as multi-persona tagging, requiring minimal new parsing code.
*   **Flexibility:** The "optimizer" itself can be configured in the settings—it could be a specific persona the user creates, or a default system prompt.

### C. Post Generation UI

The existing structure of dynamic menu creation and event delegation is perfect for adding our new features.

**Proposed UI and Workflow**

**1. Displaying Generated Content:**

*   **Inline Content:** When a post is rendered, the backend will replace a tag like `$image(...)` with the final HTML.
    *   **Success:** `<img src="/path/to/generated/image.png" class="generated-content">` or an HTML5 `<audio>` or `<video>` player.
    *   **Pending:** `<div class="generated-content pending" data-request-id="123">Generating image... <div class="spinner"></div></div>`.
    *   **Failure:** `<div class="generated-content error">Failed to generate image. <button class="retry-btn" data-request-id="123">Retry</button></div>`.
*   **Post-Level Content:** For content generated from an entire post (e.g., an audio version), the generated media will appear in a dedicated container at the top of the post's content, separate from the text.

**2. The "..." Options Menu:**

Inside the `renderPostNode` function, we will add the new options to the `optionsMenu` div:

```javascript
// In renderPostNode, after creating edit/delete buttons...
const generateImageBtn = document.createElement('a');
generateImageBtn.href = '#';
generateImageBtn.className = 'generate-image-btn';
generateImageBtn.textContent = 'Generate Image from Post';
generateImageBtn.dataset.postId = post.post_id;
optionsMenu.appendChild(generateImageBtn);

// ... similar buttons for Video, Audio (TTS), and Music
```

**3. Handling the Actions:**

We will add new `if` blocks to the `postList` event listener:

```javascript
// In postList.addEventListener('click', ...)
if (target.classList.contains('generate-image-btn')) {
    event.preventDefault();
    const postId = target.dataset.postId;
    openGenerationModal('image', postId);
}
// ... similar handlers for other generation types
```

**4. The Generation Modal (`openGenerationModal`):**

Instead of queueing a request immediately, clicking the button will open a modal. This provides a much better user experience. The modal will:

*   Show the original post's text in a (potentially editable) textarea, pre-filled as the prompt.
*   Provide UI elements for common parameters (e.g., a dropdown for image aspect ratio, a dropdown for voice selection).
*   Have a "Queue Generation" button that sends the prompt and parameters to a new API endpoint to create the `llm_request`.

### D. Finalized Backend Architecture Plan

1.  **Create a `generators` Directory:**
    *   Create a new directory: `forllm_server/generators/`.
    *   The existing logic from `llm_processing.py` will be moved and refactored into `forllm_server/generators/ollama_connector.py`.
    *   New files will be created for other services: `diffusers_connector.py`, `tts_connector.py`, `music_connector.py`, and `video_connector.py`.
    *   A base class, `BaseGenerator`, will be defined to ensure a consistent interface.

2.  **Refactor the `llm_worker`:**
    *   The `llm_worker` in `llm_queue.py` will be refactored to be a pure dispatcher.
    *   It will use a dictionary to map `request_type` strings to generator classes.
    *   The `generate` method within each connector will be responsible for all job-specific logic: building the payload, communicating with the external library, and handling the result (saving the file, updating the central `generated_media` table).

3.  **Create a `media` Directory:**
    *   A top-level directory named `media` will be created to store output files, with subdirectories for `images`, `videos`, `audio`, `music`, and `audiobooks`.

### E. Finalized Database Plan

Our database plan is confirmed and refined. We will use a **hybrid approach**: a central media library for tracking all generated files, and separate, domain-specific databases for the miniapps' internal metadata.

1.  **Main Database (`forllm_data.db`) Changes:**
    *   **`posts` Table Migration:** Add a `content_structured` (TEXT) column and perform a one-time migration to convert existing post content to the new JSON format.
    *   **New `generated_media` Table:** Add the `CREATE TABLE IF NOT EXISTS generated_media` statement to `init_db`. This table will track every generated file, linking back to the `llm_requests` entry and providing a `source_app` and optional `project_id` for context.

2.  **Miniapp Databases (`forllm_audio.db`, etc.):**
    *   These databases will be created as needed.
    *   They will **not** track individual media files. Instead, they will store metadata related to their specific domain, such as `audiobooks` and `audiobook_chapters` tables, or `music_projects` and `image_projects` tables. The `project_id` from these tables will be referenced in the main `generated_media` table.

This approach provides the best of both worlds: a centralized, queryable library of all media assets, and clean, decoupled data management for the internal workings of each miniapp.

---


