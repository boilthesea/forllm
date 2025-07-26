// personas.js - Persona management UI logic
import { apiRequest } from './api.js';
import { initializeTomSelect } from './ui-helpers.js';

// Debug helper function
function debugLog(context, ...args) {
  console.debug(`[Personas:${context}]`, ...args);
}

// We'll get these lazily since the containers might not exist when this file loads
const Elements = {
  // These are inside the specific settings container (modal or page)
  personasListContainer: function(container) { 
    return container.querySelector('#personas-list-container'); 
  },
  addPersonaBtn: function(container) { 
    return container.querySelector('#add-persona-btn'); 
  },
  globalDefaultPersonaSelect: function(container) { 
    return container.querySelector('#global-default-persona-select'); 
  },
  saveGlobalDefaultPersonaBtn: function(container) { 
    return container.querySelector('#save-global-default-persona-btn'); 
  },

  // These are part of the global #persona-modal, accessed via document or the modal itself
  personaModal: function() { 
    const modal = document.querySelector('#persona-modal');
    // You can add debugLog here if needed, e.g., debugLog('Elements.personaModal', 'Found modal:', modal);
    return modal;
  },
  closePersonaModal: function() { 
    const modal = Elements.personaModal();
    return modal ? modal.querySelector('#close-persona-modal') : null;
  },
  personaForm: function() { 
    const modal = Elements.personaModal();
    return modal ? modal.querySelector('#persona-form') : null;
  },
  personaNameInput: function() { 
    const form = Elements.personaForm();
    return form ? form.querySelector('#persona-name-input') : null; 
  },
  personaInstructionsInput: function() { 
    const form = Elements.personaForm();
    return form ? form.querySelector('#persona-instructions-input') : null; 
  },
  personaPromptPreviewBtn: function() { 
    const form = Elements.personaForm();
    return form ? form.querySelector('#persona-prompt-preview-btn') : null;
  },
  personaPromptPreview: function() {
    const form = Elements.personaForm(); 
    return form ? form.querySelector('#persona-prompt-preview') : null;
  },
  savePersonaBtn: function() { 
    const form = Elements.personaForm();
    return form ? form.querySelector('#save-persona-btn') : null;
  },
  deletePersonaBtn: function() { 
    const form = Elements.personaForm();
    return form ? form.querySelector('#delete-persona-btn') : null;
  },
  personaVersionsContainer: function() {
    const modal = Elements.personaModal();
    return modal ? modal.querySelector('#persona-versions-container') : null;
  },
  // New elements for persona generation UI
  personaGenNameHintInput: function(container) { 
    return container.querySelector('#persona-gen-name-hint-input'); 
  },
  personaGenDescHintInput: function(container) { 
    return container.querySelector('#persona-gen-desc-hint-input'); 
  },
  generatePersonaBtn: function(container) { 
    return container.querySelector('#generate-persona-btn'); 
  },
  personaGenMessage: function(container) { 
    return container.querySelector('#persona-gen-message'); 
  }
  // Potentially personaGenModelSelect if model selection is added:
  // personaGenModelSelect: function(container) { 
  //  return container.querySelector('#persona-gen-model-select');
  // },
};

let editingPersonaId = null;

function showMessage(container, msg, type = 'info') {
  debugLog('showMessage', msg, type);
  let m = document.getElementById('personas-message');
  const plc = Elements.personasListContainer(container);
  if (!m) {
    m = document.createElement('div');
    m.id = 'personas-message';
    if (plc) {
      plc.parentElement.insertBefore(m, plc);
    }
  }
  m.textContent = msg;
  m.className = 'personas-message personas-message-' + type;
  m.style.display = 'block';
  setTimeout(() => { m.style.display = 'none'; }, 3000);
}

async function safeApiRequest(container, url, method = 'GET', data = null) { // Added container
  debugLog('safeApiRequest', 'Calling', method, url, data);
  try {
    const result = await apiRequest(url, method, data);
    debugLog('safeApiRequest', 'Success:', result);
    return result;
  } catch (e) {
    debugLog('safeApiRequest', 'Error:', e);
    showMessage(container, e.message || 'API error', 'error'); // Pass container
    throw e;
  }
}

async function loadPersonasList(container) {
  debugLog('loadPersonasList', 'Starting...');
  const listContainer = Elements.personasListContainer(container);
  if (!listContainer) {
    console.warn('[Personas] No personas list container found');
    return;
  }
  
  listContainer.innerHTML = '<em>Loading...</em>';
  try {
    const personas = await safeApiRequest(container, '/api/personas'); // Pass container
    debugLog('loadPersonasList', 'Loaded personas:', personas);
    listContainer.innerHTML = '';
    personas.forEach(p => {
      const div = document.createElement('div');
      div.className = 'persona-list-item';
      div.innerHTML = `<b>${p.name}</b> <button data-id="${p.persona_id}" class="edit-persona-btn">Edit</button>`;
      listContainer.appendChild(div);
    });

    // Event delegation is now handled by attachHandlers, so no need to add listeners here.
    
    const select = Elements.globalDefaultPersonaSelect(container);
    if (select) {
      select.innerHTML = '';
      personas.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.persona_id;
        opt.textContent = p.name;
        select.appendChild(opt);
      });
      // Set current global default
      const globalDefault = await safeApiRequest(container, '/api/personas/global-default'); // Pass container
      const tsInstance = initializeTomSelect(select, {
          create: false,
          controlInput: null // Disables text input completely
      });
      if (tsInstance) {
        tsInstance.setValue(globalDefault.globalDefaultPersonaId, true); // Silently set value
      }
    }
  } catch (e) {
    listContainer.innerHTML = '<span style="color:red">Failed to load personas.</span>';
    console.error('[Personas] Failed to load:', e);
  }
}

// Re-attach event handlers
// --- Event Delegation Setup ---
// This single function replaces all the individual .addEventListener calls.
// It's called once and attaches listeners to persistent parent elements.
export function attachHandlers(container) {
  debugLog('attachHandlers', 'Attaching delegated event listeners...');

  // Check if handlers are already attached to prevent duplicates.
  if (container.dataset.handlersAttached === 'true') {
    debugLog('attachHandlers', 'Delegated handlers already attached to this container.');
    return;
  }
  container.dataset.handlersAttached = 'true';

  // --- Main container click handler ---
  container.addEventListener('click', async (e) => {
    const target = e.target;

    // Edit Persona button (in the list)
    if (target.matches('.edit-persona-btn')) {
      e.preventDefault();
      const personaId = target.dataset.id;
      openPersonaInModal(personaId, container);
      return;
    }

    // Add Persona button
    if (target.matches('#add-persona-btn')) {
      e.preventDefault();
      debugLog('addPersonaBtn.click', 'Button clicked');
      editingPersonaId = null;
      const modal = Elements.personaModal();
      if (!modal) {
        console.error('[Personas] Persona modal not found!');
        return;
      }
      const modalTitle = modal.querySelector('#persona-modal-title');
      if (modalTitle) modalTitle.textContent = 'Add Persona';
      const form = Elements.personaForm();
      if(form) form.reset();
      const deleteBtn = Elements.deletePersonaBtn();
      if (deleteBtn) deleteBtn.style.display = 'none';
      const versionsContainer = Elements.personaVersionsContainer();
      if(versionsContainer) versionsContainer.innerHTML = '';
      const previewDiv = Elements.personaPromptPreview();
      if(previewDiv) previewDiv.innerHTML = '';
      
      modal.style.display = 'block';
      modal.setAttribute('data-mode', 'create');
      const nameInput = Elements.personaNameInput();
      if (nameInput) nameInput.focus();
      return;
    }

    // Save Global Default Persona button
    if (target.matches('#save-global-default-persona-btn')) {
      e.preventDefault();
      const selectElement = Elements.globalDefaultPersonaSelect(container);
      if (!selectElement || !selectElement.value) {
        showMessage(container, 'Please select a persona to set as global default.', 'error');
        return;
      }
      try {
        await safeApiRequest(container, '/api/personas/global-default', 'PUT', { globalDefaultPersonaId: selectElement.value });
        showMessage(container, 'Global default persona saved.', 'success');
      } catch (err) {
        showMessage(container, `Error saving global default: ${err.message || err}`, 'error');
      }
      return;
    }

    // Generate Persona button
    if (target.matches('#generate-persona-btn')) {
        e.preventDefault();
        debugLog('generatePersonaBtn.click', 'Generate button clicked');
        const nameHintInput = Elements.personaGenNameHintInput(container);
        const descHintInput = Elements.personaGenDescHintInput(container);
        const genMessageEl = Elements.personaGenMessage(container);
        const description_hint = descHintInput ? descHintInput.value.trim() : '';

        if (!description_hint) {
            if (genMessageEl) {
                genMessageEl.textContent = 'Description hint is required.';
                genMessageEl.className = 'message-area error';
                genMessageEl.style.display = 'block';
                setTimeout(() => { genMessageEl.style.display = 'none'; }, 3000);
            }
            return;
        }

        const payload = {
            name_hint: nameHintInput ? nameHintInput.value.trim() : '',
            description_hint: description_hint
        };

        try {
            if (genMessageEl) {
                genMessageEl.textContent = 'Queueing persona generation...';
                genMessageEl.className = 'message-area info';
                genMessageEl.style.display = 'block';
            }
            const result = await safeApiRequest(container, '/api/personas/generate/from_details', 'POST', payload);
            if (genMessageEl) {
                genMessageEl.textContent = `Persona generation queued. Request ID: ${result.request_id}. It will appear in the list once processed.`;
                genMessageEl.className = 'message-area success';
            }
            if (nameHintInput) nameHintInput.value = '';
            if (descHintInput) descHintInput.value = '';
        } catch (err) {
            debugLog('generatePersonaBtn.click', 'Error:', err);
            if (genMessageEl) {
                genMessageEl.textContent = `Error: ${err.message || 'Failed to queue generation.'}`;
                genMessageEl.className = 'message-area error';
                genMessageEl.style.display = 'block';
            }
        }
        return;
    }
  });

  // --- Modal-specific event delegation ---
  const modal = Elements.personaModal();
  if (modal && modal.dataset.handlersAttached !== 'true') {
    modal.dataset.handlersAttached = 'true';

    modal.addEventListener('click', async (e) => {
      const target = e.target;

      // Close modal button or background
      if (target.matches('#close-persona-modal') || target === modal) {
        e.preventDefault();
        modal.style.display = 'none';
        return;
      }

      // Delete Persona button
      if (target.matches('#delete-persona-btn')) {
        e.preventDefault();
        if (!editingPersonaId) return;
        if (!confirm('Are you sure you want to delete this persona?')) return;
        
        try {
          // Note: `container` is not available in this scope. We need to find the settings container.
          const settingsContainer = document.querySelector('#settings-page-content') || document.body;
          await safeApiRequest(settingsContainer, `/api/personas/${editingPersonaId}`, 'DELETE');
          showMessage(settingsContainer, 'Persona deleted.', 'success');
          modal.style.display = 'none';
          editingPersonaId = null;
          loadPersonasList(settingsContainer); // Refresh the list
        } catch (err) {
          const settingsContainer = document.querySelector('#settings-page-content') || document.body;
          showMessage(settingsContainer, `Error deleting persona: ${err.message || err}`, 'error');
        }
        return;
      }

      // Preview Persona button
      if (target.matches('#persona-prompt-preview-btn')) {
        e.preventDefault();
        const name = Elements.personaNameInput().value.trim();
        const instructions = Elements.personaInstructionsInput().value.trim();
        const previewDiv = Elements.personaPromptPreview();
        if (!instructions) {
          previewDiv.textContent = 'Please enter instructions to preview.';
          return;
        }
        previewDiv.textContent = 'Loading preview...';
        try {
          const response = await safeApiRequest(null, '/api/personas/preview', 'POST', { name, prompt_instructions: instructions });
          if (response && response.preview_text) {
            previewDiv.textContent = response.preview_text;
          } else {
            previewDiv.textContent = `Error: ${response.error || 'Failed to load preview.'}`;
          }
        } catch (error) {
          previewDiv.textContent = `Error: ${error.message || 'Failed to load preview.'}`;
        }
        return;
      }
    });

    // Form submission
    const form = Elements.personaForm();
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = Elements.personaNameInput().value.trim();
        const instructions = Elements.personaInstructionsInput().value.trim();
        const settingsContainer = document.querySelector('#settings-page-content') || document.body;

        if (!name || !instructions) {
          showMessage(settingsContainer, 'Name and instructions are required.', 'error');
          return;
        }

        try {
          if (editingPersonaId) {
            await safeApiRequest(settingsContainer, `/api/personas/${editingPersonaId}`, 'PUT', { name, prompt_instructions: instructions });
            showMessage(settingsContainer, 'Persona updated.', 'success');
          } else {
            await safeApiRequest(settingsContainer, '/api/personas', 'POST', { name, prompt_instructions: instructions });
            showMessage(settingsContainer, 'Persona created.', 'success');
          }
          modal.style.display = 'none';
          loadPersonasList(settingsContainer);
        } catch (err) {
          // safeApiRequest already shows the message
          console.error('[Personas] Error saving persona:', err);
        }
      });
    }
  }
}

// Export needed functions
const personas = {
  loadPersonasList, // Now expects container
  showMessage,      // Now expects container
  attachHandlers    // Now expects container
};

// Attach handlers when module loads
// debugLog('init', 'Module loaded, attaching handlers...');
// personas.attachHandlers(); // Removed: This will be called by the importing module

// Export the personas object
export default personas;

export async function openPersonaInModal(personaId, settingsContainer) {
  editingPersonaId = parseInt(personaId);
  debugLog('openPersonaInModal', `Editing persona ID: ${editingPersonaId}`);

  try {
    const persona = await safeApiRequest(settingsContainer, `/api/personas/${editingPersonaId}`);
    const nameInput = Elements.personaNameInput();
    const instructionsInput = Elements.personaInstructionsInput();
    const modal = Elements.personaModal();
    const modalTitle = modal ? modal.querySelector('#persona-modal-title') : null;
    const deleteBtn = Elements.deletePersonaBtn();
    const previewDiv = Elements.personaPromptPreview();
    const versionsContainer = Elements.personaVersionsContainer();

    if (nameInput) nameInput.value = persona.name;
    if (instructionsInput) instructionsInput.value = persona.prompt_instructions;
    
    if (modalTitle) modalTitle.textContent = 'Edit Persona';
    if (deleteBtn) deleteBtn.style.display = 'inline-block';
    if (previewDiv) previewDiv.innerHTML = ''; // Clear previous preview
    if (versionsContainer) versionsContainer.innerHTML = ''; // Clear previous versions

    // TODO: Optionally load and display persona versions here if desired upon opening.
    // For now, versions are typically loaded/displayed if a dedicated "View Versions" button is clicked.
    
    if (modal) {
      modal.style.display = 'block';
      modal.setAttribute('data-mode', 'edit'); // Indicate edit mode
    }
    if (nameInput) nameInput.focus();

  } catch (err) {
    // settingsContainer is the context for showMessage if an error occurs fetching persona
    showMessage(settingsContainer, `Error fetching persona details: ${err.message || err}`, 'error');
  }
}
