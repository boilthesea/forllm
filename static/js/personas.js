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
  }
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
