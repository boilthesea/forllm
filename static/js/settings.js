// This file will handle application settings.

import { apiRequest } from './api.js';
import {
    settingsPageContent,
    settingsBtn, // Needed for event listener in main.js
    exitSettingsBtn // Needed for event listener in main.js
} from './dom.js';
import { applyDarkMode, showSection, lastVisibleSectionId, openThemeCreator } from './ui.js'; // Need applyDarkMode, showSection, and lastVisibleSectionId
import { initThemeCreator } from './theming.js';
import { initializeTomSelect } from './ui-helpers.js';

// --- State Variables ---
export let currentSettings = { // Store loaded settings
    selectedModel: null,
    llmLinkSecurity: 'true',
    default_llm_context_window: '4096',
    autoCheckContextWindow: false,
    theme: 'theme-silvery',
    ch_max_ambient_posts: '5',
    ch_max_posts_per_sibling_branch: '2',
    ch_primary_history_budget_ratio: '0.7'
};

// --- DEBUG: Global click logger ---
document.addEventListener('click', (e) => {
  console.debug('[Global] Click at', e.target);
});

// --- NEW DATA FETCHING LOGIC ---

/**
 * Fetches application settings from the server.
 * @returns {Promise<object>} A promise that resolves to the settings object.
 */
async function fetchSettings() {
    return apiRequest('/api/settings');
}

/**
 * Fetches the list of available Ollama models from the server.
 * @returns {Promise<object>} A promise that resolves to the models data structure from the API.
 */
async function fetchOllamaModels() {
    // This API call is set to be silent on errors, returning the error object for processing.
    return apiRequest('/api/ollama/models', 'GET', null, false, true);
}

/**
 * The main entry point for initializing the settings system.
 * Fetches all required data concurrently and then renders the UI.
 */
export async function initializeSettings() {
    // Ensure the settings page HTML is rendered first.
    renderSettingsPage();

    // Set a loading state for all model dropdowns
    document.querySelectorAll('#model-select').forEach(el => {
        const ts = el.tomselect || initializeTomSelect(el, { create: false, controlInput: null });
        if (ts) {
            ts.clear();
            ts.clearOptions();
            ts.addOption({ value: '', text: 'Loading...' });
            ts.setValue('', true);
            ts.disable();
        }
    });

    try {
        // Step 1: Fetch settings and models in parallel
        const [settings, modelsResult] = await Promise.all([
            fetchSettings(),
            fetchOllamaModels()
        ]);

        // Step 2: Process the fetched settings and update the global state
        currentSettings = {
            selectedModel: settings.selectedModel || null,
            llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false',
            default_llm_context_window: settings.default_llm_context_window || '4096',
            autoCheckContextWindow: settings.autoCheckContextWindow === true || settings.autoCheckContextWindow === 'true',
            theme: settings.theme || 'theme-silvery',
            ch_max_ambient_posts: settings.ch_max_ambient_posts || '5',
            ch_max_posts_per_sibling_branch: settings.ch_max_posts_per_sibling_branch || '2',
            ch_primary_history_budget_ratio: settings.ch_primary_history_budget_ratio || '0.7'
        };
        applyTheme(currentSettings.theme);

        // Step 3: Process the fetched models
        let models = [];
        const settingsErrorElement = document.querySelector('#settings-page-content #settings-error') || document.querySelector('#settings-modal #settings-error');

        if (Array.isArray(modelsResult)) {
            models = modelsResult;
        } else if (modelsResult && Array.isArray(modelsResult.models)) {
            models = modelsResult.models;
            if (modelsResult.error && settingsErrorElement) {
                console.warn("Ollama connection issue reported by backend:", modelsResult.error);
                settingsErrorElement.textContent = "Warning: Ollama connection issue. Displaying default models.";
            }
        } else {
            console.error("Unexpected format or error fetching Ollama models:", modelsResult);
            models = currentSettings.selectedModel ? [currentSettings.selectedModel] : [];
            if (settingsErrorElement) {
                settingsErrorElement.textContent = "Error fetching models. Using current selection if available.";
            }
        }

        // Step 4: Determine the correct model to select (now that we have settings)
        const defaultModelFromBackend = models.length > 0 ? models[0] : null;
        let modelToSelect = currentSettings.selectedModel || defaultModelFromBackend;

        if (models.length > 0 && !models.includes(modelToSelect)) {
            modelToSelect = models[0]; // The saved model is not in the available list
        }
        currentSettings.selectedModel = modelToSelect; // Update state

        // Step 5: Populate the model dropdown with the correct data and selection
        updateAndInitializeAllModelSelects(models, modelToSelect);

        // Add event listener for changes to the model select dropdown
        document.querySelectorAll('#model-select').forEach(selectEl => {
            selectEl.removeEventListener('change', handleModelSelectionChange);
            selectEl.addEventListener('change', handleModelSelectionChange);
        });

        // Step 6: Update all other UI elements with the final, correct settings
        updateSettingsUI();

        // Step 7: Fetch context window for the selected model if needed
        const contextDisplay = document.querySelector('#settings-page-content #selected-model-context-window-display') || document.querySelector('#settings-modal #selected-model-context-window-display');
        if (modelToSelect && modelToSelect !== 'None' && currentSettings.autoCheckContextWindow) {
            await fetchAndDisplayModelContextWindow(modelToSelect, false);
        } else if (contextDisplay) {
            contextDisplay.textContent = '';
        }

    } catch (error) {
        console.error("Error initializing settings:", error);
        const settingsErrorElement = document.querySelector('#settings-page-content #settings-error') || document.querySelector('#settings-modal #settings-error');
        if (settingsErrorElement) {
            settingsErrorElement.textContent = `Could not load settings: ${error.message}`;
        }
        applyTheme('theme-silvery'); // Fallback theme
    } finally {
        // Re-enable model dropdowns regardless of outcome
        document.querySelectorAll('#model-select').forEach(el => {
            if (el.tomselect) {
                el.tomselect.enable();
            }
        });
    }
}

/**
 * Helper function to update all settings UI elements from the global `currentSettings`.
 * This should be called after `currentSettings` is confirmed to be up-to-date.
 */
function updateSettingsUI() {
    // This function can update elements in both the modal and the page view.
    const containers = [document.getElementById('settings-modal'), document.getElementById('settings-page-section')];
    containers.forEach(container => {
        if (!container) return;

        const autoCheckToggleInput = container.querySelector('#auto-check-context-window-toggle');
        if (autoCheckToggleInput) autoCheckToggleInput.checked = currentSettings.autoCheckContextWindow;

        const linkSecurityToggleInput = container.querySelector('#llm-link-security-toggle');
        if (linkSecurityToggleInput) linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';

        const contextWindowInput = container.querySelector('#default-llm-context-window-input');
        if (contextWindowInput) contextWindowInput.value = currentSettings.default_llm_context_window;

        const themeSelect = container.querySelector('#theme-select');
        if (themeSelect && themeSelect.tomselect) {
            themeSelect.tomselect.setValue(currentSettings.theme, true);
        }

        const maxAmbientPostsInput = container.querySelector('#ch-max-ambient-posts');
        if (maxAmbientPostsInput) maxAmbientPostsInput.value = currentSettings.ch_max_ambient_posts;

        const maxPostsPerSiblingInput = container.querySelector('#ch-max-posts-per-sibling-branch');
        if (maxPostsPerSiblingInput) maxPostsPerSiblingInput.value = currentSettings.ch_max_posts_per_sibling_branch;

        const primaryRatioInput = container.querySelector('#ch-primary-history-budget-ratio');
        if (primaryRatioInput) primaryRatioInput.value = currentSettings.ch_primary_history_budget_ratio;
    });
}


// --- Settings Page Rendering ---
export function renderSettingsPage() {
    console.debug('[Settings] Starting renderSettingsPage()');
    // Get both possible settings containers
    const modalContent = document.querySelector('#settings-modal .modal-content');
    const pageContent = document.querySelector('#settings-page-section #settings-page-content');

    import('./personas.js').then(module => {
        console.debug('[Settings] Loaded personas module.');
        window.personasModule = module.default;
        if (modalContent) renderContainerHTML(modalContent);
        if (pageContent) renderContainerHTML(pageContent);
    }).catch(err => {
        console.error('[Settings] Failed to load personas module:', err);
        // Still try to render if personas fail
        if (modalContent) renderContainerHTML(modalContent);
        if (pageContent) renderContainerHTML(pageContent);
    });
}

function renderContainerHTML(container) {
    if (!container || container.querySelector('#settings-nav')) {
        // If container is invalid or already rendered, do nothing.
        return;
    }
    console.debug('[Settings] Rendering HTML into container:', container);
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
            <option value="">Loading...</option>
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
       <div class="settings-subsection">
           <h4>File Tagging Settings</h4>
           <p class="settings-info-text">Only plain text files are supported. Blocked file types will be ignored.</p>
           <div id="file-indexing-settings-container">
               <!-- Indexed Folders List -->
               <div class="setting-item">
                   <label>Indexed Folders:</label>
                   <ul id="indexed-folders-list" class="indexed-folders-list">
                       <!-- Folders will be dynamically inserted here -->
                   </ul>
               </div>
               <!-- Add New Folder Form -->
               <div class="setting-item">
                   <label for="new-folder-path-input">Add Folder to Index:</label>
                   <div class="input-with-button">
                       <input type="text" id="new-folder-path-input" placeholder="Click Browse to select a folder">
                       <button id="browse-folder-btn" class="button-secondary">Browse...</button>
                       <button id="add-indexed-folder-btn" class="button-secondary">Add</button>
                   </div>
                   <div class="setting-item" style="margin-left: 10px;">
                       <input type="checkbox" id="new-folder-recursive-toggle" checked>
                       <label for="new-folder-recursive-toggle">Index Recursively</label>
                   </div>
               </div>
                <!-- Filter Lists -->
               <div class="setting-item">
                   <label for="global-blocklist-input">Global Blocklist (comma-separated extensions):</label>
                   <textarea id="global-blocklist-input" class="textarea-input" rows="3"></textarea>
               </div>
               <div class="setting-item">
                   <label for="global-allowlist-input">Global Allowlist (comma-separated extensions):</label>
                   <textarea id="global-allowlist-input" class="textarea-input" rows="2" placeholder="Optional. If set, only these types will be indexed."></textarea>
               </div>
               <button id="save-filters-btn" class="button-secondary">Save Filters</button>
               <button id="reindex-files-btn" class="button-primary">Re-index All Files</button>
               <p id="file-indexing-message" class="message-area" style="display: none;"></p>
           </div>
       </div>
    </div>
</div>
<div id="settings-schedule-section" class="settings-tab-section" style="display:none"></div>
<div id="settings-personas-section" class="settings-tab-section" style="display:none">
    <h2>Personas</h2>
    <button id="add-persona-btn">Add Persona</button>
    <div id="personas-list-container"></div>
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
    <hr class="modal-hr">
    <h3>Global Default Persona</h3>
    <select id="global-default-persona-select"></select>
    <button id="save-global-default-persona-btn">Save Global Default</button>
</div>
`;
    // Attach all event handlers and initialize components for this container
    attachContainerEventHandlers(container);
}

function attachContainerEventHandlers(container) {
    // Tab Navigation
    const settingsNav = container.querySelector('#settings-nav');
    if (settingsNav) {
        settingsNav.querySelectorAll('li').forEach(li => {
            li.onclick = (e) => {
                container.querySelectorAll('#settings-nav li').forEach(li2 => li2.classList.remove('active'));
                e.target.classList.add('active');
                const tabId = e.target.id.replace('settings-nav-', 'settings-') + '-section';
                container.querySelectorAll('.settings-tab-section').forEach(tab => {
                    tab.style.display = (tab.id === tabId) ? '' : 'none';
                    if (tab.id === tabId && tab.id === 'settings-personas-section') {
                        if (window.personasModule && window.personasModule.loadPersonasList) {
                            window.personasModule.loadPersonasList(container);
                        }
                    }
                });
            };
        });
        // Set initial active tab
        const generalTab = settingsNav.querySelector('#settings-nav-general');
        if (generalTab) {
            generalTab.classList.add('active');
            container.querySelectorAll('.settings-tab-section').forEach(tab => {
                tab.style.display = (tab.id === 'settings-general-section') ? '' : 'none';
            });
        }
    }

    // Persona Handlers
    if (window.personasModule && window.personasModule.attachHandlers) {
        window.personasModule.attachHandlers(container);
    }

    // General Settings Handlers
    initializeTomSelect(container.querySelector('#theme-select'), { create: false, controlInput: null });
    container.querySelector('#save-settings-btn')?.addEventListener('click', () => saveSettings(container));
    container.querySelector('#open-theme-creator-btn')?.addEventListener('click', () => {
        if (typeof initThemeCreator === 'function') {
            initThemeCreator();
        } else {
            console.error("Theme creator is not available.");
            alert("Error: Theme creator module could not be loaded.");
        }
    });

   // File Indexing Handlers
   container.querySelector('#browse-folder-btn')?.addEventListener('click', () => browseForFolder(container));
   container.querySelector('#add-indexed-folder-btn')?.addEventListener('click', () => addIndexedFolder(container));
   container.querySelector('#indexed-folders-list').addEventListener('click', (e) => {
        if (e.target.classList.contains('delete-folder-btn')) {
           const folderId = e.target.dataset.folderId;
           deleteIndexedFolder(folderId, container);
       } else if (e.target.classList.contains('folder-toggle')) {
           const folderId = e.target.dataset.folderId;
           const isRecursive = container.querySelector(`#recursive-toggle-${folderId}`).checked;
           const useGlobal = container.querySelector(`#global-filters-toggle-${folderId}`).checked;
           updateIndexedFolder(folderId, { is_recursive: isRecursive, use_global_filters: useGlobal }, container);
           // Toggle visibility of custom filters panel
           const customFiltersPanel = container.querySelector(`#custom-filters-${folderId}`);
           if (customFiltersPanel) {
               customFiltersPanel.style.display = useGlobal ? 'none' : 'block';
           }
       } else if (e.target.classList.contains('save-custom-filters-btn')) {
           const folderId = e.target.dataset.folderId;
           const custom_blocklist = container.querySelector(`#custom-blocklist-${folderId}`).value.split(',').map(ext => ext.trim()).filter(Boolean);
           const custom_allowlist = container.querySelector(`#custom-allowlist-${folderId}`).value.split(',').map(ext => ext.trim()).filter(Boolean);
           updateIndexedFolder(folderId, {
               custom_blocklist: JSON.stringify(custom_blocklist),
               custom_allowlist: JSON.stringify(custom_allowlist)
           }, container);
       }
   });
   container.querySelector('#save-filters-btn')?.addEventListener('click', () => saveFileFilters(container));
   container.querySelector('#reindex-files-btn')?.addEventListener('click', () => triggerReindex(container));

    // Populate UI fields from the current state
    updateSettingsUI();
   // Load file indexing settings when the LLM tab is shown
   loadFileIndexingSettings(container);
}

// --- File Indexing Logic ---
async function loadFileIndexingSettings(container) {
   try {
       const data = await apiRequest('/api/settings/file-indexing');
       renderFileIndexingSettings(data, container);
   } catch (error) {
       console.error("Error loading file indexing settings:", error);
       const messageArea = container.querySelector('#file-indexing-message');
       if (messageArea) {
           messageArea.textContent = `Error: ${error.message}`;
           messageArea.style.display = 'block';
       }
   }
}

function renderFileIndexingSettings(data, container) {
   const foldersList = container.querySelector('#indexed-folders-list');
   const blocklistInput = container.querySelector('#global-blocklist-input');
   const allowlistInput = container.querySelector('#global-allowlist-input');

   // Render folders
   foldersList.innerHTML = '';
   if (data.indexed_folders && data.indexed_folders.length > 0) {
       data.indexed_folders.forEach(folder => {
           const li = document.createElement('li');
           li.className = 'indexed-folder-item';

           // Safely parse custom lists
           let customBlock = [];
           let customAllow = [];
           try {
               if (folder.custom_blocklist) customBlock = JSON.parse(folder.custom_blocklist);
           } catch (e) { console.error(`Error parsing custom_blocklist for folder ${folder.id}:`, folder.custom_blocklist); }
           try {
               if (folder.custom_allowlist) customAllow = JSON.parse(folder.custom_allowlist);
           } catch (e) { console.error(`Error parsing custom_allowlist for folder ${folder.id}:`, folder.custom_allowlist); }


           li.innerHTML = `
               <div class="folder-main-controls">
                   <span class="folder-path-display">${folder.folder_path}</span>
                   <div class="folder-toggles">
                       <input type="checkbox" id="recursive-toggle-${folder.id}" class="folder-toggle" data-folder-id="${folder.id}" ${folder.is_recursive ? 'checked' : ''}>
                       <label for="recursive-toggle-${folder.id}">Recursive</label>
                       <input type="checkbox" id="global-filters-toggle-${folder.id}" class="folder-toggle" data-folder-id="${folder.id}" ${folder.use_global_filters ? 'checked' : ''}>
                       <label for="global-filters-toggle-${folder.id}">Use Global Filters</label>
                   </div>
                   <button class="button-icon delete-folder-btn" data-folder-id="${folder.id}" title="Remove Folder">&times;</button>
               </div>
               <div id="custom-filters-${folder.id}" class="custom-filters-panel" style="display: ${folder.use_global_filters ? 'none' : 'block'};">
                   <label for="custom-blocklist-${folder.id}">Custom Blocklist:</label>
                   <textarea id="custom-blocklist-${folder.id}" class="textarea-input" rows="2">${customBlock.join(', ')}</textarea>
                   <label for="custom-allowlist-${folder.id}">Custom Allowlist:</label>
                   <textarea id="custom-allowlist-${folder.id}" class="textarea-input" rows="2">${customAllow.join(', ')}</textarea>
                   <button class="button-secondary save-custom-filters-btn" data-folder-id="${folder.id}">Save Custom Filters</button>
               </div>
           `;
           foldersList.appendChild(li);
       });
   } else {
       foldersList.innerHTML = '<li>No folders are currently indexed.</li>';
   }

   // Render filters
   const blocklist = data.filter_rules.filter(r => r.rule_type === 'global_blocklist').map(r => r.extension).join(', ');
   const allowlist = data.filter_rules.filter(r => r.rule_type === 'global_allowlist').map(r => r.extension).join(', ');
   blocklistInput.value = blocklist;
   allowlistInput.value = allowlist;
}

async function browseForFolder(container) {
    const input = container.querySelector('#new-folder-path-input');
    const browseBtn = container.querySelector('#browse-folder-btn');
    browseBtn.textContent = '...';
    browseBtn.disabled = true;
    try {
        const response = await apiRequest('/api/utils/browse-folder');
        if (response && response.path) {
            input.value = response.path;
        }
    } catch (error) {
        console.error("Error browsing for folder:", error);
        alert(`Failed to browse for folder: ${error.message}`);
    } finally {
        browseBtn.textContent = 'Browse...';
        browseBtn.disabled = false;
    }
}

async function addIndexedFolder(container) {
   const input = container.querySelector('#new-folder-path-input');
   const recursiveToggle = container.querySelector('#new-folder-recursive-toggle');
   const path = input.value.trim();
   const is_recursive = recursiveToggle.checked;

   if (!path) return;
 
   try {
       await apiRequest('/api/settings/file-indexing/folders', 'POST', { path, is_recursive });
       input.value = '';
       await loadFileIndexingSettings(container); // Refresh list
   } catch (error) {
       console.error("Error adding folder:", error);
       alert(`Failed to add folder: ${error.message}`);
   }
}

async function deleteIndexedFolder(folderId, container) {
    if (!confirm('Are you sure you want to remove this folder from the index?')) return;
 
    try {
        await apiRequest(`/api/settings/file-indexing/folders/${folderId}`, 'DELETE');
        await loadFileIndexingSettings(container); // Refresh list
    } catch (error) {
        console.error("Error deleting folder:", error);
        alert(`Failed to delete folder: ${error.message}`);
    }
}

async function updateIndexedFolder(folderId, settings, container) {
    try {
        await apiRequest(`/api/settings/file-indexing/folders/${folderId}`, 'PUT', settings);
        // Optional: show a temporary success message
        const messageArea = container.querySelector('#file-indexing-message');
        if (messageArea) {
            messageArea.textContent = 'Folder settings updated.';
            messageArea.style.display = 'block';
            setTimeout(() => { messageArea.style.display = 'none'; }, 2000);
        }
    } catch (error) {
        console.error(`Error updating folder ${folderId}:`, error);
        alert(`Failed to update folder settings: ${error.message}`);
        // Re-load settings to revert UI to last known good state
        await loadFileIndexingSettings(container);
    }
}

async function saveFileFilters(container) {
   const blocklist = container.querySelector('#global-blocklist-input').value.split(',').map(ext => ext.trim()).filter(Boolean);
   const allowlist = container.querySelector('#global-allowlist-input').value.split(',').map(ext => ext.trim()).filter(Boolean);

   try {
       await apiRequest('/api/settings/file-indexing/filters', 'PUT', { blocklist, allowlist });
       alert('Filter settings saved.');
   } catch (error) {
       console.error("Error saving filters:", error);
       alert(`Failed to save filters: ${error.message}`);
   }
}

async function triggerReindex(container) {
   const messageArea = container.querySelector('#file-indexing-message');
   messageArea.textContent = 'Re-indexing in progress...';
   messageArea.style.display = 'block';

   try {
       const result = await apiRequest('/api/settings/file-indexing/reindex', 'POST');
       messageArea.textContent = `Re-indexing complete. Indexed ${result.indexed_files} files.`;
   } catch (error) {
       console.error("Error triggering re-index:", error);
       messageArea.textContent = `Error: ${error.message}`;
   }
}

function renderModelOptions(modelSelectElement, models, selectedModel) {
    if (!modelSelectElement) return;
    const tsInstance = modelSelectElement.tomselect;
    if (!tsInstance) return;

    tsInstance.clearOptions();
    if (!Array.isArray(models)) return;

    models.forEach(modelName => tsInstance.addOption({ value: modelName, text: modelName }));
    tsInstance.setValue(selectedModel, true); // Silently set value
}

export function updateAndInitializeAllModelSelects(models, modelToSelect) {
    document.querySelectorAll('#model-select').forEach(selectEl => {
        if (!selectEl.tomselect) {
            initializeTomSelect(selectEl, { create: false, controlInput: null });
        }
        renderModelOptions(selectEl, models, modelToSelect);
    });
}

async function handleModelSelectionChange(event) {
    const selectedModel = event.target.value;
    currentSettings.selectedModel = selectedModel;

    // Update the UI in both possible views
    updateSettingsUI();

    const autoCheckToggle = document.querySelector('#settings-page-content #auto-check-context-window-toggle') || document.querySelector('#settings-modal #auto-check-context-window-toggle');
    if (autoCheckToggle && autoCheckToggle.checked) {
        await fetchAndDisplayModelContextWindow(selectedModel, false);
    } else {
        const contextDisplay = document.querySelector('#settings-page-content #selected-model-context-window-display') || document.querySelector('#settings-modal #selected-model-context-window-display');
        if (contextDisplay) contextDisplay.textContent = '';
    }
}

async function fetchAndDisplayModelContextWindow(modelName, isForcedRefresh = false) {
    const displayElement = document.querySelector('#settings-page-content #selected-model-context-window-display') || document.querySelector('#settings-modal #selected-model-context-window-display');
    if (!displayElement) return;

    if (!modelName || modelName === 'None') {
        displayElement.textContent = '';
        return;
    }

    const autoCheckToggle = document.querySelector('#settings-page-content #auto-check-context-window-toggle') || document.querySelector('#settings-modal #auto-check-context-window-toggle');
    if (!autoCheckToggle || (!autoCheckToggle.checked && !isForcedRefresh)) {
        displayElement.textContent = '';
        return;
    }

    displayElement.innerHTML = ' (Context: Loading...)';

    const showErrorState = () => {
        displayElement.innerHTML = ' context limit unavailable ';
        const refreshSpan = document.createElement('span');
        refreshSpan.textContent = '🔄';
        refreshSpan.style.cursor = 'pointer';
        refreshSpan.style.marginLeft = '5px';
        refreshSpan.title = 'Refresh context window';
        refreshSpan.setAttribute('aria-label', 'Refresh context window');
        refreshSpan.addEventListener('click', (event) => {
            event.preventDefault();
            fetchAndDisplayModelContextWindow(modelName, true);
        });
        displayElement.appendChild(refreshSpan);
    };

    try {
        let apiUrl = `/api/llm/models/${encodeURIComponent(modelName)}/context_window?refresh=${isForcedRefresh}`;
        const data = await apiRequest(apiUrl, 'GET', null, false, true);

        if (data && data.context_window !== undefined && data.context_window !== null) {
            displayElement.textContent = ` (Context: ${data.context_window} tokens)`;
        } else {
            showErrorState();
        }
    } catch (error) {
        console.error(`Exception fetching context window for ${modelName}:`, error);
        showErrorState();
    }
}

function applyTheme(themeName) {
    document.body.classList.remove('theme-silvery', 'theme-hc-black');
    if (themeName) {
        document.body.classList.add(themeName);
    }
}

export async function saveSettings(container) {
    if (!container) {
        console.error("Save settings called without a valid container context.");
        return;
    }

    const modelSelectElement = container.querySelector('#model-select');
    const autoCheckToggleInput = container.querySelector('#auto-check-context-window-toggle');
    const linkSecurityToggleInput = container.querySelector('#llm-link-security-toggle');
    const contextWindowInput = container.querySelector('#default-llm-context-window-input');
    const themeSelect = container.querySelector('#theme-select');
    const chMaxAmbientPostsInput = container.querySelector('#ch-max-ambient-posts');
    const chMaxPostsPerSiblingBranchInput = container.querySelector('#ch-max-posts-per-sibling-branch');
    const chPrimaryHistoryBudgetRatioInput = container.querySelector('#ch-primary-history-budget-ratio');
    const saveButton = container.querySelector('#save-settings-btn');
    const settingsErrorElement = container.querySelector('#settings-error');

    // Simple validation check
    if (!modelSelectElement || !saveButton || !settingsErrorElement) {
        console.error("Required settings elements not found in the container for saving.");
        return;
    }

    const settingsToSave = {
        selectedModel: modelSelectElement.value,
        autoCheckContextWindow: autoCheckToggleInput.checked,
        llmLinkSecurity: linkSecurityToggleInput.checked.toString(),
        default_llm_context_window: contextWindowInput.value,
        theme: themeSelect.value,
        ch_max_ambient_posts: chMaxAmbientPostsInput.value,
        ch_max_posts_per_sibling_branch: chMaxPostsPerSiblingBranchInput.value,
        ch_primary_history_budget_ratio: chPrimaryHistoryBudgetRatioInput.value
    };

    // Further validation can be added here...

    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';
    settingsErrorElement.textContent = "";

    try {
        await apiRequest('/api/settings', 'PUT', settingsToSave);
        // After a successful save, re-initialize everything to ensure UI is consistent
        // with the newly saved state. This is the most robust approach.
        await initializeSettings();

        // Optional: Show a temporary success message
        if (settingsErrorElement) {
            settingsErrorElement.textContent = "Settings saved successfully!";
            setTimeout(() => { settingsErrorElement.textContent = ""; }, 3000);
        }

    } catch (error) {
        if (settingsErrorElement) {
            settingsErrorElement.textContent = `Error saving settings: ${error.message}`;
        }
        console.error("Error saving settings:", error);
    } finally {
        if (saveButton) {
            saveButton.disabled = false;
            saveButton.textContent = 'Save Settings';
        }
    }
}

export function showSettingsPage(navigateToPersonasTab = false) {
    renderSettingsPage(); // Ensure content is created/updated
    showSection('settings-page-section');
    initializeSettings(); // Initialize data every time the page is shown

    if (navigateToPersonasTab) {
        const pageContent = document.getElementById('settings-page-content');
        if (pageContent) {
            const personasNavTab = pageContent.querySelector('#settings-nav-personas');
            personasNavTab?.click();
        }
    }
}

export function openPersonaForEditing(personaId) {
    showSettingsPage(true);
    setTimeout(() => {
        const settingsContentContainer = document.getElementById('settings-page-content');
        const personasTabContentContainer = settingsContentContainer?.querySelector('#settings-personas-section');
        if (window.personasModule?.openPersonaInModal && personasTabContentContainer) {
            window.personasModule.openPersonaInModal(personaId, personasTabContentContainer);
        } else {
            console.error('[Settings] Could not open persona for editing.');
            alert('Error: Could not open persona editor.');
        }
    }, 150);
}

// DEPRECATED FUNCTIONS
export async function loadSettings() {
    console.warn("loadSettings() is deprecated. Use initializeSettings().");
    return initializeSettings();
}
export async function loadOllamaModels() {
    console.warn("loadOllamaModels() is deprecated and should not be called directly.");
    // This function is now a no-op because initializeSettings handles it.
}