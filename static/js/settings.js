// This file will handle application settings.

import { apiRequest } from './api.js';
import {
    settingsPageContent,
    settingsBtn, // Needed for event listener in main.js
    exitSettingsBtn // Needed for event listener in main.js
} from './dom.js';
import { applyDarkMode, showSection, lastVisibleSectionId, openThemeCreator } from './ui.js'; // Need applyDarkMode, showSection, and lastVisibleSectionId
import { initThemeCreator } from './theming.js';

// --- State Variables ---
export let currentSettings = { // Store loaded settings
    selectedModel: null,
    llmLinkSecurity: 'true',
    default_llm_context_window: '4096',
    autoCheckContextWindow: false, // New setting
    theme: 'theme-silvery', // Add theme setting
    // Add new chat history settings with their string defaults
    ch_max_ambient_posts: '5',
    ch_max_posts_per_sibling_branch: '2',
    ch_primary_history_budget_ratio: '0.7'
};

// --- DEBUG: Global click logger ---
document.addEventListener('click', (e) => {
  console.debug('[Global] Click at', e.target);
});

// --- Settings Page Rendering ---
export function renderSettingsPage() {
    console.debug('[Settings] Starting renderSettingsPage()');
    // Only render HTML if not already present
    let firstRender = false;
    // Get both possible settings containers
    const modalContent = document.querySelector('#settings-modal .modal-content');
    console.debug('[Settings] Found modal content:', modalContent);
    const pageContent = document.querySelector('#settings-page-section #settings-page-content');
    console.debug('[Settings] Found page content:', pageContent);    // Import personas module right away to ensure it's loaded
    console.debug('[Settings] Loading personas module...');
    import('./personas.js').then(module => {
        console.debug('[Settings] Loaded personas module.'); // Removed "calling attachHandlers"
        // Store personas module for later use
        window.personasModule = module.default;
        // Continue with rendering
        renderContainers();
    }).catch(err => {
        console.error('[Settings] Failed to load personas module:', err);
    });

    function renderContainers() {
        // Function to render settings content into a container
        const renderIntoContainer = (container) => {
            console.debug('[Settings] Rendering into container:', container);
            if (!container.querySelector('#settings-nav')) {
                container.innerHTML = `
<nav id="settings-nav">
  <ul>
    <li id="settings-nav-general">General</li>
    <li id="settings-nav-llm">LLM</li>
    <li id="settings-nav-schedule">Schedule</li>
    <li id="settings-nav-personas">Personas</li>
  </ul>
</nav>
<div id="settings-general-section" class="settings-tab-section">
    <div class="setting-item">
        <label for="model-select">Select LLM Model:</label>
        <select id="model-select">
            <option value="">Loading models...</option>
        </select>
        <p style="margin-top: 5px;" id="model-info-display">
           <span id="selected-model-context-window-display" style="font-size: 0.9em; color: #aaa;"></span>
        </p>
    </div>
    <div class="setting-item">
        <label for="auto-check-context-window-toggle">Auto-check model context window:</label>
        <input type="checkbox" id="auto-check-context-window-toggle">
        <span class="tooltip-icon" title="If checked, FORLLM will attempt to automatically determine the model's context window from its modelfile. Most modelfiles do not include this information. It's often best to manually set a 'Default LLM Context Window' below that meets your needs.">?</span>
    </div>
    <div class="setting-item">
        <label for="llm-link-security-toggle">LLM Link Security:</label>
        <input type="checkbox" id="llm-link-security-toggle">
    </div>
    <div class="setting-item">
        <label for="default-llm-context-window-input">Default LLM Context Window (tokens):</label>
        <input type="number" id="default-llm-context-window-input" class="number-input" min="0" placeholder="e.g., 4096">
        <p style="font-size: 0.8em; color: #888; margin-top: 3px;">Used if model-specific context window detection fails.</p>
    </div>
    <div class="setting-item">
        <label for="theme-select">Theme:</label>
        <select id="theme-select">
            <option value="theme-silvery">Silvery</option>
            <option value="theme-hc-black">High-Contrast Black</option>
        </select>
        <button id="open-theme-creator-btn" class="button-secondary" style="margin-left: 10px;">Theme Creator</button>
    </div>
    <button id="save-settings-btn">Save Settings</button>
    <p id="settings-error" class="error-message"></p>
</div>
<div id="settings-llm-section" class="settings-tab-section" style="display:none">
    <div class="settings-subsection">
        <h4>Chat History Configuration</h4>
        <div class="setting-item">
            <label for="ch-max-ambient-posts">Max Ambient Posts:</label>
            <input type="number" id="ch-max-ambient-posts" name="ch_max_ambient_posts" min="0">
            <span class="tooltip-icon" title="Maximum number of recent posts from other discussion branches to include as ambient history. Set to 0 to disable ambient history. (Default: 5)">?</span>
        </div>
        <div class="setting-item">
            <label for="ch-max-posts-per-sibling-branch">Max Posts Per Sibling Branch:</label>
            <input type="number" id="ch-max-posts-per-sibling-branch" name="ch_max_posts_per_sibling_branch" min="0">
            <span class="tooltip-icon" title="Maximum number of recent posts to include from each individual sibling branch for ambient history. (Default: 2)">?</span>
        </div>
        <div class="setting-item">
            <label for="ch-primary-history-budget-ratio">Primary History Budget Ratio:</label>
            <input type="number" step="0.05" min="0" max="1" id="ch-primary-history-budget-ratio" name="ch_primary_history_budget_ratio">
            <span class="tooltip-icon" title="Proportion (0.0 to 1.0) of available history tokens to allocate to the primary conversation thread. The rest is for ambient history. E.g., 0.7 means 70% for primary. (Default: 0.7)">?</span>
        </div>
    </div>
</div>
<div id="settings-schedule-section" class="settings-tab-section" style="display:none"></div>
<div id="settings-personas-section" class="settings-tab-section" style="display:none">
    <h2>Personas</h2>
    <button id="add-persona-btn">Add Persona</button>
    <div id="personas-list-container"></div>

    <!-- New Section for Generating Personas -->
    <hr class="modal-hr">
    <h4>Generate New Persona (MVP)</h4>
    <div class="setting-item">
        <label for="persona-gen-name-hint-input">Name Hint (Optional):</label>
        <input type="text" id="persona-gen-name-hint-input" class="text-input">
    </div>
    <div class="setting-item">
        <label for="persona-gen-desc-hint-input">Description Hint:</label>
        <textarea id="persona-gen-desc-hint-input" class="textarea-input" rows="3"></textarea>
    </div>
    <button id="generate-persona-btn" class="button-primary">Generate Persona</button>
    <p id="persona-gen-message" class="message-area" style="display: none;"></p>
    <!-- End New Section -->

    <hr class="modal-hr">
    <h3>Global Default Persona</h3>
    <select id="global-default-persona-select"></select>
    <button id="save-global-default-persona-btn">Save Global Default</button>
</div>
`;
                firstRender = true;
            }

            // Set up tab navigation within this container
            const settingsNav = container.querySelector('#settings-nav');
            if (settingsNav) {
                const navLis = settingsNav.querySelectorAll('li');
                navLis.forEach(li => console.debug('[Settings] Nav item in container:', li.id, li.textContent, 'display:', getComputedStyle(li).display));
                
                // Attach click handler to each li
                navLis.forEach(li => {
                    li.onclick = (e) => {
                        console.debug('[Settings] Nav click in container:', e.target.id);
                        // Remove active class from all tabs in THIS container
                        container.querySelectorAll('#settings-nav li').forEach(li2 => li2.classList.remove('active'));
                        e.target.classList.add('active');
                        
                        const tabId = e.target.id.replace('settings-nav-', 'settings-') + '-section';
                        console.debug('[Settings] Looking for tab section:', tabId, 'in container:', container);
                        
                        // Only toggle tabs in THIS container
                        container.querySelectorAll('.settings-tab-section').forEach(tab => {
                            const shouldShow = tab.id === tabId;
                            tab.style.display = shouldShow ? '' : 'none';
                            if (shouldShow) {
                                console.debug('[Settings] Showing tab section:', tab.id, 'in container:', container);                                if (tab.id === 'settings-personas-section') {
                                    console.debug('[Settings] Loading personas list...');
                                    if (window.personasModule && window.personasModule.loadPersonasList) {
                                        window.personasModule.loadPersonasList(container); // Pass container
                                    } else {
                                        console.error('[Settings] Personas module not loaded or missing loadPersonasList function');
                                    }
                                }
                            }
                        });
                    };
                });

                // Attach persona handlers for this container
                if (window.personasModule && window.personasModule.attachHandlers) {
                    console.debug('[Settings] Attaching persona handlers for container:', container);
                    window.personasModule.attachHandlers(container);
                } else {
                    console.error('[Settings] Personas module or attachHandlers not available for container:', container);
                }

                // Set initial active tab
                const generalTab = settingsNav.querySelector('#settings-nav-general');
                if (generalTab) {
                    console.debug('[Settings] Setting initial active tab in container');
                    navLis.forEach(li => li.classList.remove('active'));
                    generalTab.classList.add('active');
                    
                    // Show general section, hide others in THIS container
                    container.querySelectorAll('.settings-tab-section').forEach(tab => {
                        tab.style.display = (tab.id === 'settings-general-section') ? '' : 'none';
                    });
                }

                // Re-attach listeners for this container
                const autoCheckToggleInput = container.querySelector('#auto-check-context-window-toggle');
                if (autoCheckToggleInput) {
                    autoCheckToggleInput.checked = currentSettings.autoCheckContextWindow;
                }

                const linkSecurityToggleInput = container.querySelector('#llm-link-security-toggle');
                if (linkSecurityToggleInput) {
                    linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
                }

                const contextWindowInput = container.querySelector('#default-llm-context-window-input');
                if (contextWindowInput) {
                    contextWindowInput.value = currentSettings.default_llm_context_window;
                }

                const themeSelect = container.querySelector('#theme-select');
                if (themeSelect) {
                    themeSelect.value = currentSettings.theme;
                }

                // Populate new chat history settings fields
                const maxAmbientPostsInput = container.querySelector('#ch-max-ambient-posts');
                if (maxAmbientPostsInput) {
                    maxAmbientPostsInput.value = currentSettings.ch_max_ambient_posts || '5';
                }
                const maxPostsPerSiblingInput = container.querySelector('#ch-max-posts-per-sibling-branch');
                if (maxPostsPerSiblingInput) {
                    maxPostsPerSiblingInput.value = currentSettings.ch_max_posts_per_sibling_branch || '2';
                }
                const primaryRatioInput = container.querySelector('#ch-primary-history-budget-ratio');
                if (primaryRatioInput) {
                    primaryRatioInput.value = currentSettings.ch_primary_history_budget_ratio || '0.7';
                }
                
                const saveButton = container.querySelector('#save-settings-btn');
                if (saveButton) {
                    saveButton.addEventListener('click', saveSettings);
                }

                const themeCreatorBtn = container.querySelector('#open-theme-creator-btn');
                if (themeCreatorBtn) {
                    themeCreatorBtn.addEventListener('click', () => {
                        // Check if the theming module is loaded, then open the creator
                        if (typeof initThemeCreator === 'function') {
                            initThemeCreator();
                        } else {
                            console.error("Theme creator is not available.");
                            alert("Error: Theme creator module could not be loaded.");
                        }
                    });
                }
            }
        };

        // Render in both places if they exist
        if (modalContent) {
            renderIntoContainer(modalContent);
        }
        if (pageContent) {
            renderIntoContainer(pageContent);
        }
        
        // Trigger model loading
        loadOllamaModels();
    }
}

function renderModelOptions(modelSelectElement, models, selectedModel) {
    if (!modelSelectElement) {
        console.error("renderModelOptions called with no modelSelectElement");
        return;
    }
    modelSelectElement.innerHTML = '';
    if (!Array.isArray(models) || models.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No models found or error loading.';
        option.disabled = true;
        modelSelectElement.appendChild(option);
        return;
    }

    models.forEach(modelName => {
        const option = document.createElement('option');
        option.value = modelName;
        option.textContent = modelName;
        if (modelName === selectedModel) {
            option.selected = true;
        }
        modelSelectElement.appendChild(option);
    });
}

// --- Loading Functions ---
export async function loadSettings() {
    try {
        const settings = await apiRequest('/api/settings');
        currentSettings = {
            selectedModel: settings.selectedModel || null,
            llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false',
            default_llm_context_window: settings.default_llm_context_window || '4096',
            autoCheckContextWindow: settings.autoCheckContextWindow === true || settings.autoCheckContextWindow === 'true', // Ensure boolean
            theme: settings.theme || 'theme-silvery',
            // Load new chat history settings, using defaults if missing from backend response
            ch_max_ambient_posts: settings.ch_max_ambient_posts || '5',
            ch_max_posts_per_sibling_branch: settings.ch_max_posts_per_sibling_branch || '2',
            ch_primary_history_budget_ratio: settings.ch_primary_history_budget_ratio || '0.7'
        };
        // Ensure boolean-like strings are strictly 'true' or 'false'
        if (currentSettings.llmLinkSecurity === undefined) currentSettings.llmLinkSecurity = 'true';
        if (currentSettings.autoCheckContextWindow === undefined) currentSettings.autoCheckContextWindow = false;

        applyTheme(currentSettings.theme);

        // Update UI elements if they exist (they might be created later by renderSettingsPage)
        // This part is somewhat redundant if renderSettingsPage correctly populates fields
        // based on currentSettings during its execution.
        const autoCheckToggleInput = settingsPageContent.querySelector('#auto-check-context-window-toggle');
        if (autoCheckToggleInput) autoCheckToggleInput.checked = currentSettings.autoCheckContextWindow;

        const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
        if (linkSecurityToggleInput) linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';

        const contextWindowInput = settingsPageContent.querySelector('#default-llm-context-window-input');
        if (contextWindowInput) contextWindowInput.value = currentSettings.default_llm_context_window;

        const maxAmbientPostsInput = settingsPageContent.querySelector('#ch-max-ambient-posts');
        if (maxAmbientPostsInput) maxAmbientPostsInput.value = currentSettings.ch_max_ambient_posts;

        const maxPostsPerSiblingInput = settingsPageContent.querySelector('#ch-max-posts-per-sibling-branch');
        if (maxPostsPerSiblingInput) maxPostsPerSiblingInput.value = currentSettings.ch_max_posts_per_sibling_branch;

        const primaryRatioInput = settingsPageContent.querySelector('#ch-primary-history-budget-ratio');
        if (primaryRatioInput) primaryRatioInput.value = currentSettings.ch_primary_history_budget_ratio;

    } catch (error) {
        console.error("Error loading settings:", error);
        // Apply default settings on error (currentSettings already holds defaults from its definition)
        applyDarkMode(true);
    }
}

export async function loadOllamaModels() {
    const modelSelectElement = settingsPageContent.querySelector('#model-select');
    const settingsErrorElement = settingsPageContent.querySelector('#settings-error');
    // const selectedOllamaModelDisplay = settingsPageContent.querySelector('#selected-ollama-model-display'); // REMOVED
    const contextWindowInput = settingsPageContent.querySelector('#default-llm-context-window-input'); // Added for fetchAndDisplayModelContextWindow

    // Ensure the select element exists before proceeding
    if (!modelSelectElement) {
         console.warn("Model select element not found yet in settings page.");
         return;
    }
    // if (!selectedOllamaModelDisplay) { // REMOVED
    //     console.warn("Selected Ollama model display element not found."); // REMOVED
    // } // REMOVED


    // Set loading state
    modelSelectElement.innerHTML = '<option value="">Loading models...</option>';
    modelSelectElement.disabled = true;
    if(settingsErrorElement) settingsErrorElement.textContent = ""; // Clear previous errors

    try {
        const modelsResult = await apiRequest('/api/ollama/models', 'GET', null, false, true); // Added silentError = true
        let models = [];
        let defaultModelFromBackend = modelsResult && modelsResult.models && modelsResult.models.length > 0 ? modelsResult.models[0] : null;

        if (Array.isArray(modelsResult)) { // Direct array of model names
            models = modelsResult;
            defaultModelFromBackend = models.length > 0 ? models[0] : null;
        } else if (modelsResult && Array.isArray(modelsResult.models)) { // Object with models array and possibly error
            models = modelsResult.models;
            if (modelsResult.error) {
                console.warn("Ollama connection issue reported by backend, using default model list:", modelsResult.error);
                if(settingsErrorElement) settingsErrorElement.textContent = "Warning: Ollama connection issue. Displaying default models.";
            }
        } else {
             console.error("Unexpected format or error fetching Ollama models:", modelsResult);
             models = currentSettings.selectedModel ? [currentSettings.selectedModel] : [];
             if(settingsErrorElement) settingsErrorElement.textContent = "Error fetching models. Using current selection if available.";
        }

        // Determine the model to select: current setting, or first from list, or null
        let modelToSelect = currentSettings.selectedModel || defaultModelFromBackend;
        if (models.length === 0 && !currentSettings.selectedModel) {
            modelToSelect = null; // No models, no selection
        } else if (models.length > 0 && !models.includes(modelToSelect) && !currentSettings.selectedModel) {
            // If currentSettings.selectedModel was null, and modelToSelect (first from backend) isn't in the (possibly filtered) list
            modelToSelect = models[0]; // Fallback to the first model in the processed list
        }


        renderModelOptions(modelSelectElement, models, modelToSelect);

        // if (selectedOllamaModelDisplay) { // REMOVED
        //     selectedOllamaModelDisplay.textContent = modelToSelect || 'None'; // REMOVED
        // } // REMOVED
        currentSettings.selectedModel = modelToSelect; // Update current setting state

        const autoCheckToggle = settingsPageContent.querySelector('#auto-check-context-window-toggle');
        if (modelToSelect && modelToSelect !== 'None' && autoCheckToggle && autoCheckToggle.checked) {
            await fetchAndDisplayModelContextWindow(modelToSelect, false);
        } else {
            const contextDisplay = settingsPageContent.querySelector('#selected-model-context-window-display');
            if (contextDisplay) contextDisplay.textContent = '';
        }

        // Add/Update event listener for changes
        modelSelectElement.removeEventListener('change', handleModelSelectionChange); // Remove previous if any
        modelSelectElement.addEventListener('change', handleModelSelectionChange);

    } catch (error) {
        console.error("Error fetching Ollama models:", error);
        renderModelOptions(modelSelectElement, currentSettings.selectedModel ? [currentSettings.selectedModel] : [], currentSettings.selectedModel);
        if(settingsErrorElement) settingsErrorElement.textContent = `Could not fetch models: ${error.message}`;
        // if (selectedOllamaModelDisplay) { // REMOVED
        //     selectedOllamaModelDisplay.textContent = currentSettings.selectedModel || 'Error'; // REMOVED
        // } // REMOVED
         // Attempt to show context for a previously selected model if list fails to load
        if (currentSettings.selectedModel) {
            await fetchAndDisplayModelContextWindow(currentSettings.selectedModel, false); // Explicitly false
        }
    } finally {
         if (modelSelectElement) modelSelectElement.disabled = false;
    }
}

async function handleModelSelectionChange(event) {
    const selectedModel = event.target.value;
    // const selectedOllamaModelDisplay = settingsPageContent.querySelector('#selected-ollama-model-display'); // REMOVED
    // if (selectedOllamaModelDisplay) { // REMOVED
    //     selectedOllamaModelDisplay.textContent = selectedModel; // REMOVED
    // } // REMOVED
    currentSettings.selectedModel = selectedModel;
    const autoCheckToggle = settingsPageContent.querySelector('#auto-check-context-window-toggle');

    if (autoCheckToggle && autoCheckToggle.checked) {
        await fetchAndDisplayModelContextWindow(selectedModel, false);
    } else {
        const contextDisplay = settingsPageContent.querySelector('#selected-model-context-window-display');
        if (contextDisplay) contextDisplay.textContent = '';
    }
}

// New function to fetch and display context window
async function fetchAndDisplayModelContextWindow(modelName, isForcedRefresh = false) {
    const displayElement = settingsPageContent.querySelector('#selected-model-context-window-display');
    if (!displayElement) {
        console.error("Context window display element not found");
        return;
    }

    // If !modelName || modelName === 'None', set textContent to '' and no refresh icon.
    if (!modelName || modelName === 'None') {
        displayElement.textContent = '';
        return;
    }

    const autoCheckToggle = settingsPageContent.querySelector('#auto-check-context-window-toggle');
    if (!autoCheckToggle || !autoCheckToggle.checked) {
        // If the auto-check is off, ensure the display is clear, unless we are force refreshing (e.g. user clicked refresh icon)
        if (!isForcedRefresh) {
             displayElement.textContent = '';
             return;
        }
        // If it IS a forced refresh, proceed even if the main checkbox is off.
    }


    displayElement.innerHTML = ''; // Clear previous content, including any refresh icon
    displayElement.textContent = ' (Context: Loading...)'; // Temporary text

    const showErrorState = () => {
        displayElement.innerHTML = ''; // Clear loading text
        displayElement.textContent = 'context limit unavailable '; // 3. Set text content

        const refreshSpan = document.createElement('span'); // 3. Create span
        refreshSpan.textContent = '🔄'; // 3. Set textContent
        refreshSpan.style.cursor = 'pointer'; // 3. Style cursor
        refreshSpan.style.marginLeft = '5px'; // 3. Style margin
        refreshSpan.title = 'Refresh context window'; // 3. Add title (aria-label is also good)
        refreshSpan.setAttribute('aria-label', 'Refresh context window');

        refreshSpan.addEventListener('click', (event) => { // 3. Attach event listener
            event.preventDefault(); // 3. Prevent default
            fetchAndDisplayModelContextWindow(modelName, true); // 3. Call self, with force refresh
        });
        displayElement.appendChild(refreshSpan); // 3. Append span
    };

    try {
        let apiUrl = `/api/llm/models/${encodeURIComponent(modelName)}/context_window`;
        if (isForcedRefresh) {
            apiUrl += '?refresh=true';
        }
        const data = await apiRequest(apiUrl, 'GET', null, false, true); // Added silentError = true

        // 2. API call successful and data.context_window is available
        if (data && data.context_window !== undefined && data.context_window !== null) {
            displayElement.textContent = ` (Context: ${data.context_window} tokens)`;
        } else {
            // API call was successful but context_window is null/undefined (e.g. API returned 404, which apiRequest might turn into a resolved promise with specific data structure)
            // Or data object itself is not as expected.
            console.warn(`Context window data not available for ${modelName}, or API response structure unexpected. Data:`, data);
            showErrorState(); // 3. Call error/unavailable state handler
        }
    } catch (error) { // API call failed (e.g. network error, 5xx, or apiRequest threw an error)
        console.error(`Exception fetching context window for ${modelName}:`, error);
        showErrorState(); // 3. Call error/unavailable state handler
    }
}

function applyTheme(themeName) {
    document.body.classList.remove('theme-silvery', 'theme-hc-black');
    document.body.classList.add(themeName);
}

// --- Settings Actions ---
export async function saveSettings() {
    // Get elements from within the settings page content
    const modelSelectElement = settingsPageContent.querySelector('#model-select');
    const autoCheckToggleInput = settingsPageContent.querySelector('#auto-check-context-window-toggle'); // New
    const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
    const contextWindowInput = settingsPageContent.querySelector('#default-llm-context-window-input');
    const themeSelect = settingsPageContent.querySelector('#theme-select');
    // New chat history inputs
    const chMaxAmbientPostsInput = settingsPageContent.querySelector('#ch-max-ambient-posts');
    const chMaxPostsPerSiblingBranchInput = settingsPageContent.querySelector('#ch-max-posts-per-sibling-branch');
    const chPrimaryHistoryBudgetRatioInput = settingsPageContent.querySelector('#ch-primary-history-budget-ratio');

    const saveButton = settingsPageContent.querySelector('#save-settings-btn');
    const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

    if (!modelSelectElement || !autoCheckToggleInput || !linkSecurityToggleInput || !contextWindowInput || !themeSelect ||
        !chMaxAmbientPostsInput || !chMaxPostsPerSiblingBranchInput || !chPrimaryHistoryBudgetRatioInput ||
        !saveButton || !settingsErrorElement) {
        console.error("Settings elements not found for saving.");
        // More detailed logging for missing elements
        if (!modelSelectElement) console.error("Missing: modelSelectElement");
        if (!autoCheckToggleInput) console.error("Missing: autoCheckToggleInput");
        if (!linkSecurityToggleInput) console.error("Missing: linkSecurityToggleInput");
        if (!contextWindowInput) console.error("Missing: contextWindowInput");
        if (!themeSelect) console.error("Missing: themeSelect");
        if (!chMaxAmbientPostsInput) console.error("Missing: chMaxAmbientPostsInput");
        if (!chMaxPostsPerSiblingBranchInput) console.error("Missing: chMaxPostsPerSiblingBranchInput");
        if (!chPrimaryHistoryBudgetRatioInput) console.error("Missing: chPrimaryHistoryBudgetRatioInput");
        if (!saveButton) console.error("Missing: saveButton");
        if (!settingsErrorElement) console.error("Missing: settingsErrorElement");

        settingsErrorElement.textContent = "An error occurred. Could not save settings. Required elements missing.";
        return;
    }

    const newSelectedModel = modelSelectElement.value;
    const newAutoCheckContextWindow = autoCheckToggleInput.checked; // New
    const newLlmLinkSecurity = linkSecurityToggleInput.checked;
    const newDefaultContextWindow = contextWindowInput.value;
    const newTheme = themeSelect.value;
    // Get values from new fields
    const chMaxAmbientPosts = chMaxAmbientPostsInput.value;
    const chMaxPostsPerSiblingBranch = chMaxPostsPerSiblingBranchInput.value;
    const chPrimaryHistoryBudgetRatio = chPrimaryHistoryBudgetRatioInput.value;

    settingsErrorElement.textContent = ""; // Clear previous errors

    // Basic Client-side Validations (Backend will also validate)
    if (!newSelectedModel) {
        settingsErrorElement.textContent = "Please select a model.";
        modelSelectElement.focus();
        return;
    }
    if (!newDefaultContextWindow || isNaN(parseInt(newDefaultContextWindow, 10)) || parseInt(newDefaultContextWindow, 10) < 0) {
        settingsErrorElement.textContent = "Default LLM Context Window must be a non-negative number.";
        contextWindowInput.focus();
        return;
    }
    if (isNaN(parseInt(chMaxAmbientPosts, 10)) || parseInt(chMaxAmbientPosts, 10) < 0) {
        settingsErrorElement.textContent = "Max Ambient Posts must be a non-negative number.";
        chMaxAmbientPostsInput.focus();
        return;
    }
    if (isNaN(parseInt(chMaxPostsPerSiblingBranch, 10)) || parseInt(chMaxPostsPerSiblingBranch, 10) < 0) {
        settingsErrorElement.textContent = "Max Posts Per Sibling Branch must be a non-negative number.";
        chMaxPostsPerSiblingBranchInput.focus();
        return;
    }
    if (isNaN(parseFloat(chPrimaryHistoryBudgetRatio)) || parseFloat(chPrimaryHistoryBudgetRatio) < 0.0 || parseFloat(chPrimaryHistoryBudgetRatio) > 1.0) {
        settingsErrorElement.textContent = "Primary History Budget Ratio must be between 0.0 and 1.0.";
        chPrimaryHistoryBudgetRatioInput.focus();
        return;
    }

    const settingsToSave = {
        selectedModel: newSelectedModel,
        autoCheckContextWindow: newAutoCheckContextWindow, // New
        llmLinkSecurity: newLlmLinkSecurity.toString(),
        default_llm_context_window: parseInt(newDefaultContextWindow, 10).toString(),
        theme: newTheme,
        // Add new settings to payload
        ch_max_ambient_posts: chMaxAmbientPosts,
        ch_max_posts_per_sibling_branch: chMaxPostsPerSiblingBranch,
        ch_primary_history_budget_ratio: chPrimaryHistoryBudgetRatio
    };

    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';

    try {
        // Use PUT request to update settings
        const updatedSettings = await apiRequest('/api/settings', 'PUT', settingsToSave, false, true); // Added silentError = true

        // Update local state immediately based on what was sent,
        // assuming the backend confirms or handles potential discrepancies.
        currentSettings.selectedModel = settingsToSave.selectedModel;
        currentSettings.autoCheckContextWindow = settingsToSave.autoCheckContextWindow; // New
        currentSettings.llmLinkSecurity = settingsToSave.llmLinkSecurity;
        currentSettings.default_llm_context_window = settingsToSave.default_llm_context_window;
        currentSettings.theme = settingsToSave.theme;
        // Update local state for new settings
        currentSettings.ch_max_ambient_posts = settingsToSave.ch_max_ambient_posts;
        currentSettings.ch_max_posts_per_sibling_branch = settingsToSave.ch_max_posts_per_sibling_branch;
        currentSettings.ch_primary_history_budget_ratio = settingsToSave.ch_primary_history_budget_ratio;

        // Update UI (redundant if page isn't re-rendered, but good practice for consistency)
        applyTheme(currentSettings.theme);
        if(autoCheckToggleInput) autoCheckToggleInput.checked = currentSettings.autoCheckContextWindow; // New
        if(linkSecurityToggleInput) linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
        if (contextWindowInput) contextWindowInput.value = currentSettings.default_llm_context_window;
        // Update new fields in UI
        if (chMaxAmbientPostsInput) chMaxAmbientPostsInput.value = currentSettings.ch_max_ambient_posts;
        if (chMaxPostsPerSiblingBranchInput) chMaxPostsPerSiblingBranchInput.value = currentSettings.ch_max_posts_per_sibling_branch;
        if (chPrimaryHistoryBudgetRatioInput) chPrimaryHistoryBudgetRatioInput.value = currentSettings.ch_primary_history_budget_ratio;

        // Re-render model options to ensure the saved one is selected
        // (though it should already be selected from the user's choice)
        if (modelSelectElement) {
            renderModelOptions(
                modelSelectElement,
                Array.from(modelSelectElement.options).map(opt => opt.value).filter(value => value !== ""), // Exclude "Loading..." or error options
                currentSettings.selectedModel
            );
        }

        // Optionally provide feedback to the user
        // settingsErrorElement.textContent = "Settings saved successfully!";
        // setTimeout(() => { settingsErrorElement.textContent = ""; }, 3000);

        // Decide whether to close the settings page or not. Let's keep it open.
        // showSection(lastVisibleSectionId);

    } catch (error) {
        settingsErrorElement.textContent = `Error saving settings: ${error.message}`;
        console.error("Error saving settings:", error);
    } finally {
        if (saveButton) { // Check if saveButton exists before modifying
            saveButton.disabled = false;
            saveButton.textContent = 'Save Settings';
        }
    }
}

export function showSettingsPage(navigateToPersonasTab = false) {
    console.debug('[Settings] showSettingsPage called. Navigate to Personas:', navigateToPersonasTab);
    renderSettingsPage(); // Ensure content is created/updated
    showSection('settings-page-section');

    if (navigateToPersonasTab) {
        const pageContent = document.getElementById('settings-page-content');
        if (pageContent) {
            const personasNavTab = pageContent.querySelector('#settings-nav-personas');
            if (personasNavTab) {
                console.debug('[Settings] Programmatically clicking Personas tab.');
                personasNavTab.click(); // This should trigger loading personas list if not already loaded
            } else {
                console.error('[Settings] Personas navigation tab not found.');
            }
        } else {
            console.error('[Settings] Settings page content container not found.');
        }
    }
}


export function openPersonaForEditing(personaId) {
    console.debug(`[Settings] openPersonaForEditing called for ID: ${personaId}`);
    showSettingsPage(true); // Show settings page and navigate to personas tab

    // The settings page content container
    const settingsContentContainer = document.getElementById('settings-page-content');
    if (!settingsContentContainer) {
        console.error('[Settings:openPersonaForEditing] Settings page content container not found.');
        return;
    }
    
    // The specific container for the personas tab content, used as context for openPersonaInModal
    const personasTabContentContainer = settingsContentContainer.querySelector('#settings-personas-section');
    if (!personasTabContentContainer) {
        console.error('[Settings:openPersonaForEditing] Personas tab content container not found.');
        return;
    }

    // Wait for personasModule to be loaded and tab switch to potentially complete UI updates.
    // personasModule is loaded by renderSettingsPage, and tab click might have async aspects.
    setTimeout(() => {
        if (window.personasModule && typeof window.personasModule.openPersonaInModal === 'function') {
            console.debug(`[Settings:openPersonaForEditing] Calling personasModule.openPersonaInModal for ID: ${personaId}`);
            window.personasModule.openPersonaInModal(personaId, personasTabContentContainer);
        } else {
            console.error('[Settings:openPersonaForEditing] personasModule or openPersonaInModal is not available.');
            // Optionally, provide user feedback here if the modal can't be opened.
            alert('Error: Could not open persona editor. Personas module not ready.');
        }
    }, 150); // Increased timeout slightly to allow tab switch and potential async ops within it.
}