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

- **1.4: Initial Layout Testing** `[TODO]`
  - Manually add the modifier classes from step 1.2 in the browser's developer tools to simulate the different layout states.
  - Verify that the primary pane toggles correctly between centered and expanded.
  - Manually add a temporary secondary pane element and apply the `.tripane-active` class to verify the three-column layout aligns correctly to the left.

---

### Phase 2: UI Controls & Pane Management Logic

**Goal:** Wire up the JavaScript to dynamically manage pane creation, destruction, and content loading.

- **2.1: Implement Primary Pane Toggle** `[TODO]`
  - In `static/js/ui.js`, create a function `togglePrimaryPaneExpansion()`.
  - This function will add or remove the `.primary-pane-expanded` class on the primary pane element.
  - Add a new UI control (e.g., an expand/contract icon button) to the primary pane's header and attach an event listener to call this function.

- **2.2: Implement Secondary Pane Logic** `[TODO]`
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

- **2.3: Implement Content Routing Hook** `[TODO]`
  - In `static/js/forum.js`, within the function that renders the list of topics, add a new icon button (e.g., "open in new pane") next to each topic link.
  - Attach a click event listener to this new button that calls `ui.openSecondaryPane()` with the URL for that topic.

- **2.4: Pane Management Testing** `[TODO]`
  - Verify the primary pane's expand/contract button works.
  - Click the new "open in new pane" icon on a topic and verify:
    - The secondary pane appears on the right.
    - The layout correctly switches to the left-aligned Tripane view.
    - The primary pane contracts if it was expanded.
    - The correct topic content loads in the new pane.
    - The "close" button on the secondary pane works and restores the previous layout state.

---

### Phase 3: Mobile Experience

**Goal:** Implement the responsive CSS and logic for an optimized mobile layout.

- **3.1: Add Mobile CSS Media Queries** `[TODO]`
  - In `static/css/layout.css`, add a media query for mobile screen sizes.
  - Inside the query, override the desktop styles:
    - The primary pane should have `width: 100%`.
    - The secondary pane should be styled as a "bottom sheet" overlay: `position: fixed; bottom: 0; left: 0; width: 100%; height: 70%; transform: translateY(100%); transition: transform 0.3s ease-in-out;`.
    - Create a class `.mobile-pane-visible` that sets `transform: translateY(0);`.

- **3.2: Update Pane Logic for Mobile** `[TODO]`
  - In `static/js/ui.js`, modify `openSecondaryPane()` and `closeSecondaryPane()` to be screen-aware.
  - Use `window.matchMedia()` to check if the mobile media query is active.
  - If mobile is active, instead of creating/destroying the element, these functions will toggle the `.mobile-pane-visible` class to trigger the slide-up/slide-down animation.

- **3.3: Mobile Testing** `[TODO]`
  - Using browser developer tools, switch to a mobile device view.
  - Verify that opening content in the secondary pane causes it to slide up from the bottom as an overlay.
  - Verify that closing it causes it to slide back down.

---

### Phase 4: UI Modernization

**Goal:** Implement the new visual styles for buttons and add theme-switching capabilities.

- **4.1: Redefine Component Styles** `[TODO]`
  - In `static/css/components.css`, rewrite the CSS for buttons to match the new design language (rounded corners, gradients for primary, outlines for secondary, etc.).
  - Review and update other components like input fields and modals for consistency.

- **4.2: Define Color Themes** `[TODO]`
  - In `static/css/base.css`, define the full set of CSS variables for the "Silvery" and "High-Contrast Black" themes under modifier classes (e.g., `body.theme-silvery`, `body.theme-hc-black`).

- **4.3: Implement Theme Switcher** `[TODO]`
  - In the settings page/modal, add a dropdown or set of buttons to select a theme.
  - In `static/js/settings.js`, add logic to handle theme selection. This will involve changing a class on the `<body>` element and saving the user's preference to local storage and the backend.

- **4.4: Style Testing** `[TODO]`
  - Verify all buttons and components reflect the new design.
  - Test the theme switcher and ensure all colors update correctly across the entire application for all three themes.

---

### Phase 5: Finalization & Documentation

**Goal:** Review the implementation and update project documentation.

- **5.1: Code Review & Refinement** `[TODO]`
  - Perform a full review of all new HTML, CSS, and JavaScript.
  - Add comments where necessary, ensure code is clean and consistent, and remove any temporary testing code.

- **5.2: Update `blueprint.md`** `[TODO]`
  - Edit the `blueprint.md` file to document the new UI architecture.
  - Describe the three-column layout, the pane management system, and the content routing logic. This will serve as the new source of truth for the application's frontend structure.