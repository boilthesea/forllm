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
    darkMode: 'false',
    selectedModel: null,
    llmLinkSecurity: 'true' // Added default
};

// --- Settings Page Rendering ---
export function renderSettingsPage() {
    // Check if content already exists to avoid duplication
    if (settingsPageContent.querySelector('#settings-form')) {
        return;
    }
    settingsPageContent.innerHTML = ''; // Clear previous content if any

    const form = document.createElement('form');
    form.id = 'settings-form';

    // Dark Mode
    const darkModeItem = document.createElement('div');
    darkModeItem.className = 'setting-item';
    darkModeItem.innerHTML = `
        <label for="dark-mode-toggle">Dark Mode:</label>
        <input type="checkbox" id="dark-mode-toggle">
    `;
    const darkModeToggleInput = darkModeItem.querySelector('#dark-mode-toggle');
    darkModeToggleInput.checked = currentSettings.darkMode === 'true';
    darkModeToggleInput.addEventListener('change', () => {
        applyDarkMode(darkModeToggleInput.checked);
    });
    form.appendChild(darkModeItem);

    // Model Select
    const modelSelectItem = document.createElement('div');
    modelSelectItem.className = 'setting-item';
    modelSelectItem.innerHTML = `
        <label for="model-select">Select LLM Model:</label>
        <select id="model-select">
            <option value="">Loading models...</option> <!-- Initial loading state -->
        </select>
    `;
    form.appendChild(modelSelectItem);

    // LLM Link Security
    const linkSecurityItem = document.createElement('div');
    linkSecurityItem.className = 'setting-item';
    linkSecurityItem.innerHTML = `
        <label for="llm-link-security-toggle">LLM Link Security:</label>
        <input type="checkbox" id="llm-link-security-toggle">
    `;
    const linkSecurityToggleInput = linkSecurityItem.querySelector('#llm-link-security-toggle');
    linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
    form.appendChild(linkSecurityItem);

    // Save Button
    const saveButton = document.createElement('button');
    saveButton.type = 'button'; // Prevent default form submission
    saveButton.id = 'save-settings-btn';
    saveButton.textContent = 'Save Settings';
    saveButton.addEventListener('click', saveSettings); // Add listener here
    form.appendChild(saveButton);

    // Error Message Area
    const errorP = document.createElement('p');
    errorP.id = 'settings-error';
    errorP.className = 'error-message';
    form.appendChild(errorP);

    settingsPageContent.appendChild(form);

    // Trigger model loading now that the select element exists
    loadOllamaModels();
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
            darkMode: settings.darkMode === 'true' ? 'true' : 'false',
            selectedModel: settings.selectedModel || null,
            llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false' // Default to true if missing
        };
         if (settings.llmLinkSecurity === undefined) {
             currentSettings.llmLinkSecurity = 'true'; // Explicitly default if undefined
        }
        applyDarkMode(currentSettings.darkMode === 'true'); // Apply dark mode immediately

        // Update UI elements if they exist (they might be created later by renderSettingsPage)
        const darkModeToggleInput = settingsPageContent.querySelector('#dark-mode-toggle');
        if (darkModeToggleInput) {
            darkModeToggleInput.checked = currentSettings.darkMode === 'true';
        }
        const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
        if (linkSecurityToggleInput) {
             linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
        }

        // Trigger model loading (it will handle populating the select later)
        // loadOllamaModels() will be called by renderSettingsPage when the elements are ready
    } catch (error) {
        console.error("Error loading settings:", error);
        // Apply default settings on error
        currentSettings = { darkMode: 'false', selectedModel: null, llmLinkSecurity: 'true' };
        applyDarkMode(false);
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
    const darkModeToggleInput = settingsPageContent.querySelector('#dark-mode-toggle');
    const modelSelectElement = settingsPageContent.querySelector('#model-select');
    const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
    const saveButton = settingsPageContent.querySelector('#save-settings-btn');
    const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

    if (!darkModeToggleInput || !modelSelectElement || !linkSecurityToggleInput || !saveButton || !settingsErrorElement) {
        console.error("Settings elements not found for saving.");
        alert("An error occurred. Could not save settings.");
        return;
    }

    const newDarkMode = darkModeToggleInput.checked;
    const newSelectedModel = modelSelectElement.value;
    const newLlmLinkSecurity = linkSecurityToggleInput.checked;

    settingsErrorElement.textContent = ""; // Clear previous errors

    if (!newSelectedModel) {
        settingsErrorElement.textContent = "Please select a model.";
        modelSelectElement.focus();
        return;
    }

    const settingsToSave = {
        darkMode: newDarkMode.toString(),
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
        currentSettings.darkMode = settingsToSave.darkMode;
        currentSettings.selectedModel = settingsToSave.selectedModel;
        currentSettings.llmLinkSecurity = settingsToSave.llmLinkSecurity;

        // Update UI (redundant if page isn't re-rendered, but good practice)
        applyDarkMode(currentSettings.darkMode === 'true');
        darkModeToggleInput.checked = currentSettings.darkMode === 'true';
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
        saveButton.disabled = false;
        saveButton.textContent = 'Save Settings';
    }
}