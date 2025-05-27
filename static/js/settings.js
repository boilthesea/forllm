// This file will handle application settings.

import { apiRequest } from './api.js';
import {
    settingsPageContent,
    settingsBtn, // Needed for event listener in main.js
    exitSettingsBtn // Needed for event listener in main.js
} from './dom.js';
import { applyDarkMode, showSection, lastVisibleSectionId } from './ui.js'; // Need applyDarkMode, showSection, and lastVisibleSectionId

// --- State Variables ---
export let currentSettings = { // Store loaded settings
    selectedModel: null,
    llmLinkSecurity: 'true' // Added default
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
    </div>
    <div class="setting-item">
        <label for="llm-link-security-toggle">LLM Link Security:</label>
        <input type="checkbox" id="llm-link-security-toggle">
    </div>
    <button id="save-settings-btn">Save Settings</button>
    <p id="settings-error" class="error-message"></p>
</div>
<div id="settings-llm-section" class="settings-tab-section" style="display:none"></div>
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
                const linkSecurityToggleInput = container.querySelector('#llm-link-security-toggle');
                if (linkSecurityToggleInput) {
                    linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
                }
                
                const saveButton = container.querySelector('#save-settings-btn');
                if (saveButton) {
                    saveButton.addEventListener('click', saveSettings);
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
            llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false' // Default to true if missing
        };
         if (settings.llmLinkSecurity === undefined) {
             currentSettings.llmLinkSecurity = 'true'; // Explicitly default if undefined
        }
        applyDarkMode(true); // Apply dark mode immediately

        // Update UI elements if they exist (they might be created later by renderSettingsPage)
        const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
        if (linkSecurityToggleInput) {
             linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
        }

        // Trigger model loading (it will handle populating the select later)
        // loadOllamaModels() will be called by renderSettingsPage when the elements are ready
    } catch (error) {
        console.error("Error loading settings:", error);
        // Apply default settings on error
        currentSettings = { selectedModel: null, llmLinkSecurity: 'true' };
        applyDarkMode(true); // Apply dark mode immediately
        // Still try to load models even if settings load failed
        // loadOllamaModels() will be called by renderSettingsPage
    }
}

export async function loadOllamaModels() {
    const modelSelectElement = settingsPageContent.querySelector('#model-select');
    const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

    // Ensure the select element exists before proceeding
    if (!modelSelectElement) {
         console.warn("Model select element not found yet in settings page.");
         return;
    }

    // Set loading state
    modelSelectElement.innerHTML = '<option value="">Loading models...</option>';
    modelSelectElement.disabled = true;
    if(settingsErrorElement) settingsErrorElement.textContent = ""; // Clear previous errors

    try {
        const modelsResult = await apiRequest('/api/ollama/models');
        let models = [];
        if (Array.isArray(modelsResult)) {
            models = modelsResult;
        } else if (modelsResult && Array.isArray(modelsResult.models)) {
            // Handle case where backend returns default list due to connection issue
            models = modelsResult.models;
            console.warn("Ollama connection issue reported by backend, using default model list:", modelsResult.error);
             if(settingsErrorElement) settingsErrorElement.textContent = "Warning: Ollama connection issue. Displaying default models.";
        } else {
             // Handle unexpected format or error from backend
             console.error("Unexpected format or error fetching Ollama models:", modelsResult);
             models = currentSettings.selectedModel ? [currentSettings.selectedModel] : []; // Use current if available, else empty
             if(settingsErrorElement) settingsErrorElement.textContent = "Error fetching models. Using current selection if available.";
        }
        renderModelOptions(modelSelectElement, models, currentSettings.selectedModel); // Populate the select
    } catch (error) {
        console.error("Error fetching Ollama models:", error);
        // Handle fetch error
        renderModelOptions(modelSelectElement, currentSettings.selectedModel ? [currentSettings.selectedModel] : [], currentSettings.selectedModel); // Use current if available
        if(settingsErrorElement) settingsErrorElement.textContent = `Could not fetch models: ${error.message}`;
    } finally {
         if (modelSelectElement) modelSelectElement.disabled = false; // Re-enable select even on error
    }
}

// --- Settings Actions ---
export async function saveSettings() {
    // Get elements from within the settings page content
    const modelSelectElement = settingsPageContent.querySelector('#model-select');
    const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
    const saveButton = settingsPageContent.querySelector('#save-settings-btn');
    const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

    if (!modelSelectElement || !linkSecurityToggleInput || !saveButton || !settingsErrorElement) {
        console.error("Settings elements not found for saving.");
        // Changed alert to console.error to avoid blocking UI in case of programmatic call
        console.error("An error occurred. Could not save settings. Required elements missing.");
        return;
    }

    const newSelectedModel = modelSelectElement.value;
    const newLlmLinkSecurity = linkSecurityToggleInput.checked;

    settingsErrorElement.textContent = ""; // Clear previous errors

    if (!newSelectedModel) {
        settingsErrorElement.textContent = "Please select a model.";
        modelSelectElement.focus();
        return;
    }

    const settingsToSave = {
        selectedModel: newSelectedModel,
        llmLinkSecurity: newLlmLinkSecurity.toString()
    };

    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';

    try {
        // Use PUT request to update settings
        const updatedSettings = await apiRequest('/api/settings', 'PUT', settingsToSave);

        // Update local state immediately based on what was sent,
        // assuming the backend confirms or handles potential discrepancies.
        currentSettings.selectedModel = settingsToSave.selectedModel;
        currentSettings.llmLinkSecurity = settingsToSave.llmLinkSecurity;

        // Update UI (redundant if page isn't re-rendered, but good practice)
        applyDarkMode(true); // Apply dark mode immediately
        linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
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