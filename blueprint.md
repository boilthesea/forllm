# FORLLM (FORum for Local Language Models) - Development Plan

## 1. Project Overview

**Goal:** Create a user-friendly, asynchronous frontend for local LLMs to mitigate long inference times and allow scheduled processing.
**Core Idea:** A forum-style interface where users post, and LLMs respond asynchronously, mimicking traditional forum interaction delays.
**Target Audience:** Hobbyists/developers running LLMs locally on consumer hardware.
**Problem Solved:** Long wait times for local LLM inference via an asynchronous, scheduled interaction model.

## 2. High-Level Architecture

```mermaid
graph TD
    User[User Browser] -- HTTP Request --> FE[Frontend (HTML/CSS/JS)];
    FE -- API Calls --> BE[Backend API (Python/Flask)];
    BE -- Read/Write --> DB[(SQLite Database)];
    BE -- Add Job --> Q[Request Queue];
    Processor[LLM Processor (Python Background Thread/Process)] -- Read Job --> Q;
    Processor -- Send Prompt --> Ollama[Ollama Instance];
    Ollama -- Return Response --> Processor;
    Processor -- Write Response --> DB;
    FE -- Poll/Fetch Updates --> BE;

    subgraph Backend Application
        BE
        Q
        Processor
        DB
    end

    subgraph User Interface
        User
        FE
    end

    subgraph External LLM Service
        Ollama
    end
```

*   **Frontend:** HTML, CSS, Vanilla JavaScript served directly by the backend.
*   **Backend:** Python (Flask recommended for simplicity in serving HTML and providing a basic API).
*   **Data Storage:** SQLite database (`forllm_data.db`) for storing users (simple profiles), subforums, topics, posts, replies, LLM queue, and LLM responses. SQLite is file-based, simple, and suitable for single-user local applications.
*   **Asynchronous Processing:** Python's built-in `queue.Queue` and `threading` (or `asyncio` if preferred) for managing the LLM request queue and background processing. A simple scheduler will be implemented to trigger processing during user-defined hours.
*   **LLM Integration:** Initial focus on Ollama via its API. Design will include an abstract base class for LLM interactions to facilitate future additions.

### File Responsibilities

*   **`forllm.py`** (Main Application Runner):
    *   Main application entry point.
    *   Initializes the Flask application.
    *   Registers all Blueprints from the `forllm_server.routes` package.
    *   Calls database initialization (`init_db()`) from `forllm_server.database`.
    *   Starts the background LLM worker thread (`llm_worker()`) from `forllm_server.llm_queue`.
    *   Runs the Flask development server.

*   **`forllm_server/`** (Core Server Logic Package):
    *   **`config.py`**: Manages all static configuration values and constants for the application (database paths, API URLs, default settings, etc.).
    *   **`database.py`**: Handles all aspects of database interaction: provides connection objects (`get_db`), manages connection teardown (`close_db`), and contains the initial database schema creation and migration logic (`init_db`). Also includes logic for persona CRUD, versioning, assignment, and fallback.
    *   **`markdown_config.py`**: Configures and provides the `MarkdownIt` instance used for rendering Markdown content to HTML, including custom Pygments syntax highlighting.
    *   **`llm_queue.py`**: Manages the in-memory queue for LLM requests (`llm_request_queue`) and contains the main loop for the background LLM processing thread (`llm_worker`), which polls both the in-memory and database queues.
    *   **`llm_processing.py`**: Contains the core logic for interacting with the LLM service (currently Ollama), including prompt construction, API call execution (`process_llm_request`), streaming response handling, and error management for LLM communication. Includes logic to determine and fetch the appropriate persona prompt instructions for an LLM request based on user override, subforum default, global default, or built-in fallback.
    *   **`scheduler.py`**: Implements the logic to determine if the LLM processor should be active based on defined schedules (`is_processing_time`), and provides utility functions to get current status and next schedule information.
    *   **`routes/main_routes.py`**: Defines Flask Blueprint for main application routes, including serving the `index.html` and static assets.
    *   **`routes/forum_routes.py`**: Defines Flask Blueprint for API endpoints related to forum management: subforums, topics, and posts (CRUD operations, listing). Includes endpoints for assigning/unassigning multiple personas per subforum and setting the per-subforum default persona.
    *   **`routes/llm_routes.py`**: Defines Flask Blueprint for API endpoints related to LLM interactions: requesting an LLM response for a post and fetching available Ollama models. Allows persona override at LLM request time.
    *   **`routes/schedule_routes.py`**: Defines Flask Blueprint for API endpoints managing LLM processing schedules: CRUD operations for schedules, and status/next schedule information.
    *   **`routes/settings_routes.py`**: Defines Flask Blueprint for API endpoints to get and update application-wide settings. Includes endpoints for persona management (list, create, update, delete, get, version history) and global default persona.

*   **`templates/index.html`**:
    *   The single HTML page that forms the entire frontend structure.
    *   Defines the layout, including the main navigation sidebar (`nav#subforum-nav`), content display areas for topics (`section#topic-list-section`) and posts (`section#topic-view-section`), and dedicated page sections for settings (`section#settings-page-section`) and the queue (`section#queue-page-section`).
    *   Contains the HTML structure for modals used for editing schedules (`div#schedule-modal`) and application settings (`div#settings-modal`).
    *   Includes placeholders and container elements where dynamic content (subforums, topics, posts, schedule details, settings options) is loaded by JavaScript.
    *   Links to the main CSS stylesheet (`static/style.css`) and the EasyMDE CSS.
    *   Includes the main JavaScript file (`static/script.js`) and the EasyMDE JavaScript library.
    *   Uses Jinja templating (`{% raw %}{% for subforum in subforums %}{% endraw %}`) for initially populating the subforum list (`ul#subforum-list`) when the page is first served by Flask.

*   **`static/js/`** (Frontend JavaScript Modules):
    *   **`main.js`**: The main application entry point. Initializes the application, sets up global event listeners (like `DOMContentLoaded`, window events, periodic updates), and orchestrates the loading and interaction of other modules.
    *   **`personas.js`**: Implements the frontend logic for managing personas, including CRUD operations, version history display, assignment to subforums, and global default persona management.
    *   **`api.js`**: Contains the `apiRequest` helper function and potentially other utilities for interacting with the backend API.
    *   **`dom.js`**: Centralizes references to key DOM elements used across different modules to avoid repeated `document.getElementById` calls.
    *   **`ui.js`**: Handles general user interface logic, including switching between different sections of the page (`showSection`) and managing UI components like the LLM link warning popup (`showLinkWarningPopup`).
    *   **`forum.js`**: Encapsulates all logic related to the forum features: loading, rendering, and handling user interactions for subforums, topics, and posts (including replies and LLM response requests). Displays assigned personas for a subforum, indicates the default persona, and allows persona selection/override when requesting an LLM response.
    *   **`schedule.js`**: Manages the scheduling functionality, including loading, rendering, and saving user-defined processing schedules, as well as displaying the next scheduled time and the current processor status.
    *   **`settings.js`**: Deals with application-wide settings, including loading, rendering, and saving user preferences like selected LLM model, personas and LLM link security. Also handles loading available Ollama models. Integrates persona management into the settings navigation and display.
    *   **`queue.js`**: Manages the display of the LLM processing queue, including fetching and rendering the list of queued tasks.
    *   **`editor.js`**: Responsible for initializing and configuring the EasyMDE Markdown editor instances used for creating new topics and replies.

*   **`static/css/base.css`**: Contains fundamental styles like body, typography, basic resets, and CSS variables. 
*   **`static/css/layout.css`**: Handles the main structural layout, including `main`, `nav#subforum-nav`, `section`, and future layouts. 
*   **`static/css/components.css`**: Groups styles for reusable UI elements such as buttons, form inputs, and the toggle switch. 
*   **`static/css/modals.css`**: Contains styles for all modal windows (general, schedule, settings, link warning) and related elements like close buttons and error messages. 
*   **`static/css/forum.css`**: Styles specific to the forum content display (topic lists, posts, LLM responses, metadata, actions, threading). 
*   **`static/css/markdown.css`**: Styles for rendering Markdown elements and Pygments syntax highlighting within posts. 
*   **`static/css/editor.css`**: Contains style overrides specifically for the EasyMDE editor.
*   **`static/css/status-indicator.css`**: Styles for the processing status indicator.

*   **`forllm_data.db`** (Database File):
    *   A SQLite database file.
    *   Stores all persistent application data, including:
        *   `users`: User profiles (currently a single default user).
        *   `subforums`: Definitions of different forum categories.
        *   `topics`: Topic titles and metadata, linked to subforums and users.
        *   `posts`: User-generated content and LLM responses, forming threaded discussions.
        *   `llm_requests`: Queue for LLM processing, tracking status, model, and persona.
        *   `schedule`: Defines active hours and days for the LLM processor.
        *   `settings`: Stores application-wide settings like selected LLM model. Also stores the global default persona ID.
        *   `personas`: Stores persona details, including name, prompt instructions, creation/update timestamps, and creator.
        *   `subforum_personas`: Links subforums and personas, indicating which personas are assigned to a subforum and the default for that subforum.
        *   `persona_versions`: Stores historical versions of persona details for versioning and revert capability.

## 3. Phased Development Plan

### Phase 1: Minimum Viable Product (MVP) - Core Asynchronous Forum [DONE]

**Goal:** Deliver the essential forum structure and the core asynchronous LLM interaction loop with Ollama for initial user testing and feedback.

**MVP Features:**

1.  **Backend Setup (Python/Flask):** [DONE]
    *   Basic Flask application structure. [DONE]
    *   Routes to serve HTML/CSS/JS assets. [DONE]
    *   Basic API endpoints for forum actions (create topic, post reply, request LLM response, fetch data). [DONE]
2.  **Database Schema (SQLite):** [DONE]
    *   Tables for: `users` (simple: `user_id`, `username`), `subforums` (`subforum_id`, `name`), `topics` (`topic_id`, `subforum_id`, `user_id`, `title`, `created_at`), `posts` (`post_id`, `topic_id`, `user_id`, `parent_post_id` (for threading), `content`, `created_at`, `is_llm_response`, `llm_model_id`, `llm_persona_id`). [DONE]
    *   Table for `llm_requests` (`request_id`, `post_id_to_respond_to`, `requested_at`, `status` (pending, processing, complete, error), `llm_model`, `llm_persona`). [DONE]
    *   Table for `schedule` (`schedule_id`, `start_hour`, `end_hour`, `enabled`). [DONE]
3.  **Basic User Identification:** [DONE]
    *   Assume a single, local user. Store a simple username (e.g., in a config file or the DB). No login system. [DONE]
4.  **Subforum/Topic Management:** [DONE]
    *   API and basic UI to create/list subforums. [DONE]
    *   API and basic UI to create/list topics within a subforum. [DONE]
    *   API and basic UI to view posts within a topic. [DONE]
5.  **Post/Reply Management:** [DONE]
    *   API and basic UI to create the initial post for a topic. [DONE]
    *   API and basic UI to reply to existing posts (user or LLM). [DONE]
    *   Simple text area for input. [DONE] (Upgraded to EasyMDE)
6.  **Threaded Display (Reddit-Style):** [DONE]
    *   Frontend logic (JavaScript) to fetch posts for a topic and render them in a nested, threaded structure based on `parent_post_id`. [DONE]
7.  **LLM Request Initiation:** [DONE]
    *   UI element (e.g., a button) on each user post to "Request LLM Response". [DONE]
    *   On click, send request to backend API, specifying the `post_id` to respond to. [DONE]
    *   Initially use a hardcoded/default Ollama model and a simple default persona concept (e.g., "Helpful Assistant"). [DONE] (Model selection now available via settings)
8.  **Asynchronous Queue & Scheduler:** [DONE]
    *   Backend implementation of a queue (`llm_requests` table acts as persistent queue). [DONE]
    *   A background thread/process that periodically checks the `schedule` table and the `llm_requests` table for pending requests (`status='pending'`). [DONE]
    *   Scheduler logic to only process jobs during allowed hours. [DONE]
9.  **Ollama Integration:** [DONE]
    *   Python code within the background processor to:
        *   Construct the appropriate prompt based on the target post and potentially some context from the thread. [DONE]
        *   Send the request to the configured Ollama API endpoint. [DONE]
        *   Handle the response (success or error). [DONE]
10. **LLM Response Handling:** [DONE]
    *   Upon successful Ollama inference, the processor saves the LLM response as a new post in the `posts` table, linked to the original user post (`parent_post_id`), and marked appropriately (`is_llm_response=True`, `llm_model_id`, `llm_persona_id`). [DONE]
    *   Update the request status in `llm_requests` table. [DONE]
11. **Displaying LLM Responses:** [DONE]
    *   Frontend fetches updated posts, including new LLM responses. [DONE]
    *   Clearly label LLM posts with model/persona info. Handle multiple LLM replies to the same user post. [DONE]
12. **Basic UI (HTML/CSS/JS):** [DONE]
    *   Minimal, functional UI focusing on readability and core actions. Served directly by Flask. Basic JS for interactions (fetching data, submitting forms/requests without full page reloads where sensible). [DONE]

**Why this MVP?** This set of features provides the core value proposition: asynchronous LLM interaction within a familiar forum structure. It allows users to test the fundamental workflow, experience the asynchronous nature, and provide feedback on the core concept before investing in more complex features.

### Phase 2: LLM Interaction Enhancements & Configuration

**Goal:** Improve the flexibility and power of LLM interactions.

**Features:**

*   **Multiple LLM Backend Support:** [TODO]
    *   Refactor Ollama integration into a modular class structure. [TODO]
    *   Add support for at least one other backend type (e.g., LM Studio, an OpenAI-compatible API endpoint). [TODO]
    *   Configuration mechanism (e.g., YAML/JSON file) to define available LLM backends and their connection details. [TODO]
*   **Persona Management:** [DONE]
    *   Database schema extension for `personas` (`persona_id`, `name`, `prompt_instructions`, `created_by_user`). [TODO]
    *   UI for users to create, view, edit, and delete custom personas (saved prompt instructions). [TODO]
*   **Explicit Model/Persona Selection:** [WIP]
    *   Modify the "Request LLM Response" UI to allow selecting from configured LLM backends and saved/default personas. (Model selection from settings is implemented, but not persona selection at request time).
    *   Store selected model/persona in the `llm_requests` table. (Model is stored, persona is default).
*   **Basic Prompt Management:** [TODO]
    * Chat history construction for replies.
*   **Basic File Attachment:** [DONE]
*   **Improved Error Handling & Status:** [WIP]
    *   More detailed status updates for queued requests (e.g., "queued", "processing", "error: connection failed", "error: inference failed"). (DB has status, but UI for queue page is basic). [DONE]
    *   Display errors clearly in the UI. (Some `alert()` and console errors, but could be more user-friendly).

### Phase 3: UI/UX Improvements & Forum Features

**Goal:** Enhance the user experience and add more standard forum functionalities.

**Features:**
*   **Dark Mode Only:** [DONE] Switch to dark mode only for comfort and reduction in css complexity.
*   **Markdown Support:** [DONE] Implement Markdown rendering for posts (e.g., using a Python library on the backend and a JS library on the frontend).
*   **Notifications:** [TODO] Simple in-app indicator (e.g., a badge on the navigation) when new LLM responses have arrived since the last view. (Desktop notifications could be a later addition).
*   **Progress Indicators:** [TODO] Basic visual feedback in the UI showing which requests are queued or actively being processed by the background worker.
*   **Search Functionality:** [TODO] Implement basic text search across topics and posts.
*   **Voting/Ranking (Optional):** [TODO] Simple up/down voting mechanism for posts/replies.
*   **UI Polish:** [DONE] General improvements to CSS, layout, and responsiveness. Consider a lightweight CSS framework if needed.

### Phase 4: Advanced LLM Interactions & Integrations

**Goal:** Introduce sophisticated LLM capabilities and potential external integrations.

**Features:**

*   **Dynamic Persona Generation:** [TODO] Functionality to use a specified LLM to generate a persona based on a user description or topic context.
    * For subforums request a user specified number of personas based on subforum name and description, give user a field to request specifics. Queuable.
    * Autogenerated subforum personas should have a regenerate button next to them for those that aren't up to snuff. Queuable.
    * 
*   **Inter-Persona Communication (Tagging):** [TODO] Implement `@PersonaName` or similar tagging in user replies to direct a specific LLM/Persona to respond. Requires parsing logic in the backend.
*   **Optional Automated Persona Interaction:** [TODO] A setting (per-topic?) to allow enabled personas to automatically reply to each other's posts within certain limits (e.g., depth, time). *Requires careful design to avoid runaway computation.*
*   **Summarization Tools:** [TODO] Add a feature to use an LLM to summarize a selected topic thread or a set of LLM replies.
*   **Rich Text Editor (Optional):** [DONE] Replace plain text area with a simple WYSIWYG editor. (EasyMDE implemented)
*   **External Tool Integration:** [TODO] Design hooks or APIs for potential future integration with other local tools (e.g., triggering image generation based on a post).
*   **More Detailed User Profiles:** [TODO] Allow associating more local metadata with the user profile.

## 4. Architectural Considerations Summary

*   **Modularity:** The LLM integration is designed around an abstract base class or interface from Phase 1, explicitly expanded in Phase 2 to support multiple backends.
*   **Asynchronicity:** The core queue (`llm_requests` table) and background processor are central to the Phase 1 design, ensuring the UI remains responsive. The scheduler adds control over *when* processing occurs.
*   **Data Persistence & Integrity:** SQLite provides simple, local persistence. Transactions should be used for database operations involving multiple steps (e.g., adding request, updating status, saving response) to maintain consistency. The background processor needs to handle potential database access conflicts gracefully, although with a single user, this is less critical than in a multi-user web app.
*   **Error Handling:** Robust error handling for LLM communication (timeouts, connection errors, API errors) and database operations will be implemented from Phase 1 and refined in subsequent phases.