# UI/UX Overhaul Phased Development Plan

This document outlines the phased development plan for a significant UI/UX overhaul of the forllm application. The core goal is to implement a flexible three-column layout ("Tripane"), modernize the visual style, and improve the user experience on both desktop and mobile platforms.

**Progress Tracking:**
To track progress, update the status of each substep from `[TODO]` to `[WIP]` (Work In Progress) when you begin working on it, and to `[DONE]` upon successful completion. If you have to implement differently than the plan suggests, update the plan to reflect your changes. 

---

### Phase 1: Foundational Layout & Structure

**Goal:** Implement the core HTML structure and CSS for all new layout states. This phase is about building the static "scaffolding" without full interactivity.

- **1.1: Update HTML Structure** `[DONE]`
  - Modify `templates/index.html` to support the new layout.
  - Create a main container to hold the panes, e.g., `<main id="main-container">`.
  - Define the primary pane element, e.g., `<div id="primary-pane" class="main-pane">`. The existing `<section>` elements will be loaded into this pane.
  - The secondary pane will be created dynamically by JavaScript in a later phase and should not be in the initial HTML.

- **1.2: Implement Core CSS** `[DONE]`
  - In `static/css/layout.css`, add CSS rules for the new layout states.
  - **Default State:** Style `#main-container` to be a flex container. Style `#primary-pane` to have a fixed maximum width and be centered horizontally (e.g., using `margin: 0 auto`).
  - **Expanded Primary State:** Create a modifier class (e.g., `.primary-pane-expanded`) that makes `#primary-pane` take up all available flexible space.
  - **Tripane State:** Create a modifier class for `#main-container` (e.g., `.tripane-active`) that changes its `justify-content` to `flex-start` (left-aligning all panes). Define the initial width for the secondary pane.

- **1.3: Solidify Fixed Navigation** `[DONE]`
  - Review and confirm the CSS for `nav#subforum-nav` in `static/css/layout.css`.
  - Ensure it has `height: 100vh`, `position: sticky`, `top: 0`, and `overflow-y: auto` to make it a fixed, internally scrollable sidebar.

- **1.4: Initial Layout Testing** `[DONE]`
  - Manually add the modifier classes from step 1.2 in the browser's developer tools to simulate the different layout states.
  - Verify that the primary pane toggles correctly between centered and expanded.
  - Manually add a temporary secondary pane element and apply the `.tripane-active` class to verify the three-column layout aligns correctly to the left.

---

### Phase 2: UI Controls & Pane Management Logic

**Goal:** Wire up the JavaScript to dynamically manage pane creation, destruction, and content loading.

- **2.1: Implement Primary Pane Toggle** `[DONE]`
  - In `static/js/ui.js`, create a function `togglePrimaryPaneExpansion()`.
  - This function will add or remove the `.primary-pane-expanded` class on the primary pane element.
  - Add a new UI control (e.g., an expand/contract icon button) to the primary pane's header and attach an event listener to call this function.

- **2.2: Implement Secondary Pane Logic** `[DONE]`
  - In `static/js/ui.js`, create two functions: `openSecondaryPane()` and `closeSecondaryPane()`.
  - `openSecondaryPane(contentUrl)`:
    - Checks if the secondary pane already exists. If not, it creates the `div` element, gives it an ID (e.g., `secondary-pane`), and appends it to `#main-container`.
    - Adds the `.tripane-active` class to `#main-container`.
    - If the primary pane has the `.primary-pane-expanded` class, it removes it, automatically contracting it.
    - Fetches and injects the content from `contentUrl`.
    - Adds a "close" button to the new pane's header, which calls `closeSecondaryPane()`.
  - `closeSecondaryPane()`:
    - Removes the secondary pane element from the DOM.
    - Removes the `.tripane-active` class from `#main-container`.

- **2.3: Implement Content Routing Hook** `[DONE]`
  - In `static/js/forum.js`, within the function that renders the list of topics, add a new icon button (e.g., "open in new pane") next to each topic link.
  - Attach a click event listener to this new button that calls `ui.openSecondaryPane()` with the URL for that topic.

- **2.4: Pane Management Testing** `[DONE]`
  - Verify the primary pane's expand/contract button works.
  - Click the new "open in new pane" icon on a topic and verify:
    - The secondary pane appears on the right.
    - The layout correctly switches to the left-aligned Tripane view.
    - The primary pane contracts if it was expanded.
    - The correct topic content loads in the new pane.
    - The "close" button on the secondary pane works and restores the previous layout state.

---

### Phase 3: Mobile Experience & Responsive Overhaul

**Goal:** Implement a fully responsive, mobile-first experience. This includes a new condensed top navigation bar, a slide-down main menu, and a two-stage "bottom sheet" for the secondary pane.

- **3.1: Add HTML for Mobile Navigation** `[DONE]`
  - In `templates/index.html`, create a new `<nav id="mobile-top-nav">` element, positioned before the main `<main>` tag. This element will be hidden by default and made visible only on mobile.
  - Inside `<mobile-top-nav>`:
    - Create the hamburger menu button: `<button id="mobile-menu-btn" title="Toggle Menu">`.
    - Inside the button, construct the "FOR/LLM" logo using a nested structure for better CSS control:
      ```html
      <div class="mobile-logo">
          <div class="logo-bar"></div>
          <div class="logo-text-container">
              <span class="logo-text">FOR</span>
              <span class="logo-text">LLM</span>
          </div>
          <div class="logo-bar"></div>
      </div>
      ```
    - Add the `<div id="processing-status-indicator-container">` to the mobile nav. The original remains in the desktop sidebar, and JavaScript is updated to manage both.
    - Create a container for icons: `<div class="mobile-nav-icons">`.
    - Add icon buttons with unique IDs (`mobile-schedule-btn`, etc.) for Schedule (`&#x1F552;`), Queue (`&#x2630;`), and Settings (`&#x2699;`).

- **3.2: Implement Responsive CSS with Media Queries** `[DONE]`
  - In `static/css/layout.css`, add a media query for mobile screen sizes (e.g., `@media (max-width: 768px)`).
  - **Mobile Layout Adjustments (Inside Media Query):**
    - Hide the desktop sidebar: `nav#subforum-nav { display: none; }`.
    - Make the mobile top nav visible and style it:
      - `#mobile-top-nav { display: flex; justify-content: space-between; align-items: center; position: fixed; top: 0; left: 0; width: 100%; height: 50px; /* Adjust height as needed */ z-index: 1000; }`
      - Add styles for the logo and icons within the top bar.
    - Repurpose `nav#subforum-nav` as the slide-down menu:
      - Override its desktop styles to be a full-screen overlay: `display: flex; position: fixed; top: 0; left: 0; width: 100%; height: 100vh; transform: translateX(-100%); transition: transform 0.3s ease-in-out; z-index: 999;`.
      - Create a modifier class `.mobile-menu-visible { transform: translateX(0); }`.
    - Style the primary pane to take up the full width: `#primary-pane { width: 100%; }`.
  - **Secondary Pane "Bottom Sheet" CSS (Inside Media Query):**
    - Override desktop styles: `#secondary-pane { position: fixed; bottom: 0; left: 0; width: 100%; height: 75%; /* Adjust height */ transform: translateY(100%); transition: transform 0.3s ease-in-out; border-left: none; border-top: 1px solid var(--post-border); }`.
    - Create a class for the "peeking" state: `.mobile-pane-peek { transform: translateY(calc(100% - 60px)); /* 60px 'peek' height */ }`.
    - Create a class for the fully visible state: `.mobile-pane-visible { transform: translateY(0); }`.

- **3.3: Update JavaScript Logic for Mobile Interactivity** `[DONE]`
  - In `static/js/ui.js`, add a helper function: `const isMobile = () => window.matchMedia("(max-width: 768px)").matches;`.
  - **Implement Mobile Menu Toggle:**
    - Create a new function `toggleMobileMenu()`.
    - This function will toggle the `.mobile-menu-visible` class on the `nav#subforum-nav` element.
    - In `main.js`, attach an event listener to the `#mobile-menu-btn` to call this new function.
  - **Update Pane Logic to be Screen-Aware:**
    - Modify `openSecondaryPane()`:
      - Add a check: `if (isMobile()) { ... } else { ... }`.
      - **Mobile Logic:** Instead of adding `.tripane-active`, it should create the `#secondary-pane` if it doesn't exist, and then toggle the `.mobile-pane-peek` class to show the initial bottom bar. The pane's header should get a new event listener to toggle between `.mobile-pane-peek` and `.mobile-pane-visible`.
      - **Desktop Logic:** Keep the existing behavior.
    - Modify `closeSecondaryPane()`:
      - Add a check: `if (isMobile()) { ... } else { ... }`.
      - **Mobile Logic:** Remove both `.mobile-pane-peek` and `.mobile-pane-visible` classes to hide the pane. The DOM element can be kept for reuse.
      - **Desktop Logic:** Keep the existing behavior of removing the element and the `.tripane-active` class.

- **3.4: Mobile Experience Testing** `[DONE]`
  - Using browser developer tools, switch to a mobile device viewport.
  - **Top Navigation:**
    - Verify the desktop sidebar is hidden and the new fixed top navigation bar is displayed correctly with the logo, icons, and status indicator.
    - Click the hamburger icon to verify the main navigation menu slides in from the side, and clicking a link or a close button hides it.
  - **Secondary Pane Workflow:**
    - Verify that opening content in the secondary pane causes it to first appear as a "peeking" bar at the bottom.
    - Verify that tapping/clicking the peeking bar causes it to expand into the full "bottom sheet" overlay.
    - Verify that closing the pane (e.g., via a close button) causes it to slide back down and out of view.


---

### Phase 4: UI Modernization & Flat Design Implementation

**Goal:** Transition the application from a gradient-based, skeuomorphic design to a modern, flat aesthetic. This involves creating a clear visual hierarchy for interactive elements, redesigning core navigation components, and ensuring a consistent style across the UI.

- **4.1: Adopt a Flat Design Philosophy** `[DONE]`
  - **Principle:** Eliminate gradients and heavy shadows in favor of solid colors, clean lines, and meaningful use of space.
  - **Action:** In `static/css/components.css`, remove `linear-gradient` backgrounds and `box-shadow` properties from the base `button` style.

- **4.2: Implement New Button Hierarchy** `[DONE]`
  - **Primary Actions** (e.g., "Create Topic", "Save"): Style with a solid, high-contrast background color to draw user attention.
    - Create a `.button-primary` class.
  - **Secondary Actions** (e.g., "Cancel", "Back"): Style with a transparent background and a colored border (outline style).
    - Create a `.button-secondary` class.
  - **Tertiary/Icon-Only Actions** (e.g., "Open in new pane"): Style with no background or border by default. A subtle background should appear on hover to indicate the clickable area.
    - Create a `.button-icon` or similar utility class.

- **4.3: Redesign Main Navigation** `[DONE]`
  - **Goal:** Convert the heavy navigation buttons into a lighter, "tab-like" list.
  - **HTML Change:** In `templates/index.html`, replace the `<button>` elements for "Edit Schedules", "Settings", and "Queue" with a `<ul>` containing `<li>` and `<a>` tags.
  - **CSS Change:** In `static/css/layout.css`, style the new navigation list to be clean and scannable.
  - **Active State:** Implement a style for the active navigation link (e.g., a persistent background color and a contrasting left border) to clearly show the user's current location. This will require JavaScript in `ui.js` to toggle an `.active` class.

- **4.4: Redesign Contextual Actions** `[DONE]`
  - **Goal:** Make the "Open in new pane" action a subtle, icon-only button.
  - **JS Change:** In `static/js/forum.js`, modify the element creation from `<button>` to a `<span>` or `<i>` with a specific class (e.g., `topic-action-icon`).
  - **CSS Change:** In `static/css/forum.css`, use Flexbox on the parent `<li>` to position the icon to the right (`justify-content: space-between`). Style the icon to be minimal, with a background appearing only on hover.

- **4.5: Update Other Components for Consistency** `[DONE]`
  - Review and update input fields, textareas, and modals to align with the new flat design language.
  - Focus on clean borders, consistent corner-rounding, and clear focus states.

- **4.6: Define Color Themes** `[DONE]`
  - In `static/css/base.css`, define the full set of CSS variables for the "Silvery" and "High-Contrast Black" themes under modifier classes (e.g., `body.theme-silvery`, `body.theme-hc-black`). This should now include variables for the new primary and secondary action colors.

- **4.7: Implement Theme Switcher** `[DONE]`
  - In the settings page/modal, add a dropdown or set of buttons to select a theme.
  - In `static/js/settings.js`, add logic to handle theme selection. This will involve changing a class on the `<body>` element and saving the user's preference to local storage and the backend.

- **4.8: Style Testing** `[DONE]`
  - Verify all buttons and components reflect the new design hierarchy.
  - Test the theme switcher and ensure all colors update correctly across the entire application.
  - Confirm the new navigation and contextual actions are functional and visually polished.

---

### Phase 5: Interactive Theme Creator

**Goal:** Develop a client-side, movable modal that allows for real-time visual theme creation and customization. This tool will enable rapid iteration on color schemes and provide an easy way to export new themes for inclusion in `base.css`.

- **5.1: Theme Core CSS Variables** `[DONE]`
  - **Action:** In `static/css/base.css`, identified all hardcoded colors in other CSS files (`forum.css`, `components.css`, `status-indicator.css`, `modals.css`) and converted them to CSS variables.
  - **New Variables Created:**
    - `--status-pending-bg`, `--status-processing-bg`, `--status-complete-bg`, `--status-error-bg`, `--status-unknown-bg`
    - `--settings-nav-active-bg`, `--settings-nav-active-color`, `--settings-nav-hover-bg`, `--settings-nav-hover-color`
    - `--status-indicator-active-bg`, `--status-indicator-inactive-bg`, `--status-indicator-loading-bg`, `--status-indicator-error-bg`
    - `--persona-tag-bg`, `--persona-tag-text`
    - `--button-danger-bg`, `--button-danger-text`, `--button-danger-hover-bg`
    - `--button-success-bg`, `--button-success-text`, `--button-success-hover-bg`
    - `--notification-badge-bg`, `--error-text-color`
  - **Action:** Replaced the hardcoded values in the respective CSS files with these new `var()` functions.

- **5.2: Theme Creator Modal Scaffolding** `[DONE]`
  - **Action:** In `static/js/ui.js`, created the `openThemeCreator()` function to generate the HTML for the theme creator modal.
  - **Action:** In `static/css/modals.css`, added a new, dedicated set of styles for `#theme-creator-modal`.
  - **Critical:** Styles use hardcoded, high-contrast values to ensure the modal is always usable.
  - **Action:** Implemented `makeDraggable()` in `static/js/ui.js` to make the modal draggable by its header.
  - **Action:** Implemented a `--reset-theme` command-line argument in `forllm.py` to reset the theme to default in the database.

- **5.3: Live Theming Engine** `[DONE]`
  - **Action:** Created a new `static/js/theming.js` module.
  - **Action:** Implemented `getCssVariablesForTheme()` to introspect all CSS variables from the active theme stylesheet.
  - **Action:** Implemented `populateThemeCreator()` to dynamically create controls for each variable.
  - **Action:** Implemented `addLiveUpdateListeners()` to update CSS variables on the `<body>` element's inline style for a live preview when a color is changed.

- **5.4: UI Controls & Features** `[DONE]`
  - **Action:** The native `<input type="color">` serves as the integrated color picker.
  - **Action:** Implemented the "In-Use Colors" palette via `updateInUseColors()`, which scans current colors and displays them as clickable swatches.
  - **Action:** Created the "Revert Changes" button, which clears inline styles from the `<body>` and re-initializes the creator to restore stylesheet defaults.
  - **Action:** Created the "Export to Clipboard" button, which generates a `.theme-custom` CSS ruleset with the current values and copies it to the clipboard.

- **5.5: Integration** `[DONE]`
  - **Action:** Added a "Theme Creator" button to the settings page in `static/js/settings.js`.
  - **Action:** Added an event listener to the new button to call `initThemeCreator()` from `theming.js`.
  - **Action:** Imported `theming.js` into `templates/index.html`.
  - **Action:** Updated this document to reflect completion.

---

### Phase 6: Finalization & Documentation

**Goal:** Review the implementation and update project documentation.

- **6.1: Code Review & Refinement** `[DONE]`
  - Perform a full review of all new HTML, CSS, and JavaScript.
  - Add comments where necessary, ensure code is clean and consistent, and remove any temporary testing code.

- **6.2: Update `blueprint.md`** `[DONE]`
  - Edit the `blueprint.md` file to document the new UI architecture.
  - Describe the three-column layout, the pane management system, and the content routing logic. This will serve as the new source of truth for the application's frontend structure.