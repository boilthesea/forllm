// personas.js - Persona management UI logic
import { apiRequest } from './api.js';

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

    // Add event listeners for new "Edit" buttons
    listContainer.querySelectorAll('.edit-persona-btn').forEach(button => {
      button.addEventListener('click', async (e) => {
        e.preventDefault();
        const personaId = e.target.dataset.id;
        editingPersonaId = parseInt(personaId);
        debugLog('editPersonaBtn.click', `Editing persona ID: ${editingPersonaId}`);

        try {
          const persona = await safeApiRequest(container, `/api/personas/${editingPersonaId}`);
          const nameInput = Elements.personaNameInput();
          const instructionsInput = Elements.personaInstructionsInput();
          const modal = Elements.personaModal();
          const modalTitle = modal ? modal.querySelector('#persona-modal-title') : null;
          const deleteBtn = Elements.deletePersonaBtn();

          if (nameInput) nameInput.value = persona.name;
          if (instructionsInput) instructionsInput.value = persona.prompt_instructions;
          
          if (modalTitle) modalTitle.textContent = 'Edit Persona';
          if (deleteBtn) deleteBtn.style.display = 'inline-block';
          
          if (modal) modal.style.display = 'block';
          if (nameInput) nameInput.focus();

        } catch (err) {
          showMessage(container, `Error fetching persona details: ${err.message || err}`, 'error');
        }
      });
    });
    
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
      select.value = globalDefault.globalDefaultPersonaId;
    }
  } catch (e) {
    listContainer.innerHTML = '<span style="color:red">Failed to load personas.</span>';
    console.error('[Personas] Failed to load:', e);
  }
}

// Re-attach event handlers
export function attachHandlers(container) {
  debugLog('attachHandlers', 'Starting...');
  
  // Add Persona button handler
  const addBtn = Elements.addPersonaBtn(container);
  if (addBtn) {
    debugLog('attachHandlers', 'Setting up Add Persona button');
    addBtn.addEventListener('click', (e) => {
      e.preventDefault();
      debugLog('addPersonaBtn.click', 'Button clicked');
      
      editingPersonaId = null;
      const modal = Elements.personaModal(); // Global
      debugLog('addPersonaBtn.click', 'Got modal:', modal);
      
      if (!modal) {
        console.error('[Personas] Persona modal not found!');
        return;
      }
      
      const modalTitle = modal.querySelector('#persona-modal-title');
      if (modalTitle) modalTitle.textContent = 'Add Persona';

      // Reset form fields
      const nameInput = Elements.personaNameInput(); // Global
      const instructionsInput = Elements.personaInstructionsInput(); // Global
      const deleteBtn = Elements.deletePersonaBtn(); // Global
      const previewDiv = Elements.personaPromptPreview(); // Global
      const versionsContainer = Elements.personaVersionsContainer(); // Global
      
      debugLog('addPersonaBtn.click', 'Form elements:', {
        nameInput,
        instructionsInput,
        deleteBtn,
        previewDiv,
        versionsContainer
      });
      
      if (nameInput) nameInput.value = '';
      if (instructionsInput) instructionsInput.value = '';
      if (previewDiv) previewDiv.innerHTML = '';
      if (deleteBtn) deleteBtn.style.display = 'none'; // Hide delete button for new personas
      if (versionsContainer) versionsContainer.innerHTML = '';
      
      // Show modal
      debugLog('addPersonaBtn.click', 'Displaying modal');
      modal.style.display = 'block';
      modal.setAttribute('data-mode', 'create');
      if (nameInput) nameInput.focus();
    });
  }

  // Save Global Default Persona button handler
  const saveGlobalDefaultBtn = Elements.saveGlobalDefaultPersonaBtn(container);
  if (saveGlobalDefaultBtn) {
    debugLog('attachHandlers', 'Setting up Save Global Default Persona button');
    saveGlobalDefaultBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      const selectElement = Elements.globalDefaultPersonaSelect(container);
      if (!selectElement) {
        showMessage(container, 'Global default persona select not found.', 'error');
        return;
      }
      const selectedId = selectElement.value;
      if (!selectedId) {
        showMessage(container, 'Please select a persona to set as global default.', 'error');
        return;
      }
      try {
        await safeApiRequest(container, '/api/personas/global-default', 'PUT', { globalDefaultPersonaId: selectedId });
        showMessage(container, 'Global default persona saved.', 'success');
      } catch (err) {
        showMessage(container, `Error saving global default: ${err.message || err}`, 'error');
      }
    });
  }
  
  // Delete Persona button handler (global modal button)
  const deletePersonaButton = Elements.deletePersonaBtn();
  if (deletePersonaButton) {
    debugLog('attachHandlers', 'Setting up Delete Persona button');
    deletePersonaButton.addEventListener('click', async (e) => {
      e.preventDefault();
      if (!editingPersonaId) {
        showMessage(container, 'No persona selected for deletion.', 'error');
        return;
      }
      if (!confirm('Are you sure you want to delete this persona?')) {
        return;
      }
      try {
        await safeApiRequest(container, `/api/personas/${editingPersonaId}`, 'DELETE');
        showMessage(container, 'Persona deleted.', 'success');
        const modal = Elements.personaModal();
        if (modal) modal.style.display = 'none';
        editingPersonaId = null;
        loadPersonasList(container); // Refresh the list
      } catch (err) {
        showMessage(container, `Error deleting persona: ${err.message || err}`, 'error');
      }
    });
  }

  // Close Modal button handler
  const closeBtn = Elements.closePersonaModal(); // Global
  if (closeBtn) {
    debugLog('attachHandlers', 'Setting up Close Modal button');
    closeBtn.addEventListener('click', () => {
      const modal = Elements.personaModal(); // Global
      if (modal) {
        debugLog('closeBtn.click', 'Hiding modal');
        modal.style.display = 'none';
      }
    });
  }

  // Click outside modal to close
  const modalGlobal = Elements.personaModal(); // Global, rename to avoid conflict
  if (modalGlobal) {
    debugLog('attachHandlers', 'Setting up modal background click handler');
    modalGlobal.addEventListener('click', (e) => {
      if (e.target === modalGlobal) {
        debugLog('modal.click', 'Closing modal via background click');
        modalGlobal.style.display = 'none';
      }
    });
  }

  // Form submit handler
  const form = Elements.personaForm(); // Global
  if (form) {
    debugLog('attachHandlers', 'Setting up form submit handler');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInput = Elements.personaNameInput(); // Global
      const instructionsInput = Elements.personaInstructionsInput(); // Global
      
      const name = nameInput ? nameInput.value.trim() : '';
      const prompt_instructions = instructionsInput ? instructionsInput.value.trim() : '';
      
      if (!name || !prompt_instructions) {
        showMessage(container, 'Name and instructions are required.', 'error'); // Pass container
        return;
      }
      
      try {
        if (editingPersonaId) {
          await safeApiRequest(container, `/api/personas/${editingPersonaId}`, 'PUT', { name, prompt_instructions }); // Pass container
          showMessage(container, 'Persona updated.', 'success'); // Pass container
        } else {
          await safeApiRequest(container, '/api/personas', 'POST', { name, prompt_instructions }); // Pass container
          showMessage(container, 'Persona created.', 'success'); // Pass container
        }
        
        const modal = Elements.personaModal(); // Global
        if (modal) modal.style.display = 'none';
        
        loadPersonasList(container); // Pass container
      } catch (e) {
        console.error('[Personas] Error saving persona:', e);
        // showMessage already called by safeApiRequest
      }
    });
  }

  // Prompt Preview button handler
  const previewBtn = Elements.personaPromptPreviewBtn();
  const previewDiv = Elements.personaPromptPreview();

  if (previewBtn && previewDiv) {
    debugLog('attachHandlers', 'Setting up Prompt Preview button');
    previewBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      debugLog('previewBtn.click', 'Preview button clicked');

      const nameInput = Elements.personaNameInput();
      const instructionsInput = Elements.personaInstructionsInput();

      if (!nameInput || !instructionsInput) {
        console.error('[Personas:Preview] Name or instructions input not found.');
        previewDiv.textContent = 'Error: Form inputs not found.';
        return;
      }

      const personaName = nameInput.value.trim();
      const personaInstructions = instructionsInput.value.trim();

      if (!personaInstructions) {
        previewDiv.textContent = 'Please enter instructions to preview.';
        return;
      }
      // Name is optional for preview, backend might use a default or just show instructions.

      previewDiv.textContent = 'Loading preview...';
      try {
        const response = await safeApiRequest(
          null, // Pass null as container for this specific call, error messages go to console via safeApiRequest's own debugLog
          '/api/personas/preview', 
          'POST', 
          { name: personaName, prompt_instructions: personaInstructions }
        );
        if (response && response.preview_text) {
          previewDiv.textContent = response.preview_text;
        } else if (response && response.error) {
          previewDiv.textContent = `Error: ${response.error}`;
        } 
        else {
          previewDiv.textContent = 'Failed to load preview. No preview text received.';
        }
      } catch (error) {
        // This catch block might be redundant if safeApiRequest handles all errors and showMessage(null,...) is acceptable.
        // However, it's good for specific error formatting in the previewDiv.
        console.error('[Personas:Preview] Error fetching prompt preview:', error);
        previewDiv.textContent = `Error: ${error.message || 'Failed to load preview.'}`;
      }
    });
  } else {
    if (!previewBtn) debugLog('attachHandlers', 'Preview button not found in modal.');
    if (!previewDiv) debugLog('attachHandlers', 'Preview div not found in modal.');
  }

  // Event listener for the new "Generate Persona" button
  const genPersonaButton = Elements.generatePersonaBtn(container);
  if (genPersonaButton) {
      debugLog('attachHandlers', 'Setting up Generate Persona button');
      genPersonaButton.addEventListener('click', async (e) => {
          e.preventDefault();
          debugLog('generatePersonaBtn.click', 'Generate button clicked');

          const nameHintInput = Elements.personaGenNameHintInput(container);
          const descHintInput = Elements.personaGenDescHintInput(container);
          const genMessageEl = Elements.personaGenMessage(container);
          // const modelSelect = Elements.personaGenModelSelect ? Elements.personaGenModelSelect(container) : null; // If model selection is added

          const name_hint = nameHintInput ? nameHintInput.value.trim() : '';
          const description_hint = descHintInput ? descHintInput.value.trim() : '';
          // let llm_model_for_generation = modelSelect ? modelSelect.value : ''; // If model selection is added
          // if (llm_model_for_generation === "Use Global Default") llm_model_for_generation = ''; // API will use global if empty

          if (!description_hint) {
              if (genMessageEl) {
                  genMessageEl.textContent = 'Description hint is required.';
                  genMessageEl.className = 'message-area error'; // Assuming you have CSS for .error
                  genMessageEl.style.display = 'block';
                  setTimeout(() => { genMessageEl.style.display = 'none'; }, 3000);
              }
              return;
          }

          const payload = {
              name_hint: name_hint,
              description_hint: description_hint
              // llm_model_for_generation: llm_model_for_generation // If model selection is added
          };

          try {
              if (genMessageEl) {
                  genMessageEl.textContent = 'Queueing persona generation...';
                  genMessageEl.className = 'message-area info'; // Assuming CSS for .info
                  genMessageEl.style.display = 'block';
              }
              
              const result = await safeApiRequest(container, '/api/personas/generate/from_details', 'POST', payload);
              
              if (genMessageEl) {
                  genMessageEl.textContent = `Persona generation queued. Request ID: ${result.request_id}. It will appear in the list once processed.`;
                  genMessageEl.className = 'message-area success'; // Assuming CSS for .success
                  // Do not hide immediately, let user see the message.
                  // Consider automatically refreshing the queue view or persona list after a delay,
                  // or instructing the user to check the queue.
              }
              if (nameHintInput) nameHintInput.value = ''; // Clear input on success
              if (descHintInput) descHintInput.value = ''; // Clear input on success

              // The persona list will update when the queue processor finishes and the main polling updates the UI.
              // Or, if there's a specific function to refresh the queue view, call it here.
              // e.g., if (window.queue && window.queue.loadQueue) window.queue.loadQueue(); 
              // For MVP, relying on existing persona list refresh (e.g., when settings tab is re-focused or via global polling) is okay.

          } catch (err) {
              debugLog('generatePersonaBtn.click', 'Error:', err);
              if (genMessageEl) {
                  genMessageEl.textContent = `Error: ${err.message || 'Failed to queue generation.'}`;
                  genMessageEl.className = 'message-area error';
                  genMessageEl.style.display = 'block';
                  // Do not hide error immediately.
              }
          }
      });
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
