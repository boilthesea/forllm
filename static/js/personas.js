// personas.js - Persona management UI logic
import { apiRequest } from './api.js';

// Debug helper function
function debugLog(context, ...args) {
  console.debug(`[Personas:${context}]`, ...args);
}

// Helper to get element from the current container
function getElement(id) {
  // Try modal content first
  const modalContent = document.querySelector('#settings-modal .modal-content');
  const pageContent = document.querySelector('#settings-page-section #settings-page-content');
  
  let element = modalContent?.querySelector('#' + id) || pageContent?.querySelector('#' + id);
  debugLog('getElement', `Looking for #${id}`, 'found:', element);
  return element;
}

// We'll get these lazily since the containers might not exist when this file loads
const Elements = {
  get personasListContainer() { 
    return document.querySelector('#personas-list-container'); 
  },
  get addPersonaBtn() { 
    return document.querySelector('#add-persona-btn'); 
  },
  get personaModal() { 
    const modal = document.querySelector('#persona-modal');
    debugLog('Elements.personaModal', 'Found modal:', modal);
    return modal;
  },
  get closePersonaModal() { 
    return document.querySelector('#close-persona-modal'); 
  },
  get personaForm() { 
    return document.querySelector('#persona-form'); 
  },
  get personaNameInput() { 
    return document.querySelector('#persona-name-input'); 
  },
  get personaInstructionsInput() { 
    return document.querySelector('#persona-instructions-input'); 
  },
  get personaPromptPreviewBtn() { 
    return document.querySelector('#persona-prompt-preview-btn'); 
  },
  get personaPromptPreview() { 
    return document.querySelector('#persona-prompt-preview'); 
  },
  get savePersonaBtn() { 
    return document.querySelector('#save-persona-btn'); 
  },
  get deletePersonaBtn() { 
    return document.querySelector('#delete-persona-btn'); 
  },
  get personaVersionsContainer() { 
    return document.querySelector('#persona-versions-container'); 
  },
  get globalDefaultPersonaSelect() { 
    return document.querySelector('#global-default-persona-select'); 
  },
  get saveGlobalDefaultPersonaBtn() { 
    return document.querySelector('#save-global-default-persona-btn'); 
  }
};

let editingPersonaId = null;

function showMessage(msg, type = 'info') {
  debugLog('showMessage', msg, type);
  let m = document.getElementById('personas-message');
  if (!m) {
    m = document.createElement('div');
    m.id = 'personas-message';
    if (Elements.personasListContainer) {
      Elements.personasListContainer.parentElement.insertBefore(m, Elements.personasListContainer);
    }
  }
  m.textContent = msg;
  m.className = 'personas-message personas-message-' + type;
  m.style.display = 'block';
  setTimeout(() => { m.style.display = 'none'; }, 3000);
}

async function safeApiRequest(url, method = 'GET', data = null) {
  debugLog('safeApiRequest', 'Calling', method, url, data);
  try {
    const result = await apiRequest(url, method, data);
    debugLog('safeApiRequest', 'Success:', result);
    return result;
  } catch (e) {
    debugLog('safeApiRequest', 'Error:', e);
    showMessage(e.message || 'API error', 'error');
    throw e;
  }
}

async function loadPersonasList() {
  debugLog('loadPersonasList', 'Starting...');
  const container = Elements.personasListContainer;
  if (!container) {
    console.warn('[Personas] No personas list container found');
    return;
  }
  
  container.innerHTML = '<em>Loading...</em>';
  try {
    const personas = await safeApiRequest('/api/personas');
    debugLog('loadPersonasList', 'Loaded personas:', personas);
    container.innerHTML = '';
    personas.forEach(p => {
      const div = document.createElement('div');
      div.className = 'persona-list-item';
      div.innerHTML = `<b>${p.name}</b> <button data-id="${p.persona_id}" class="edit-persona-btn">Edit</button>`;
      container.appendChild(div);
    });
    
    const select = Elements.globalDefaultPersonaSelect;
    if (select) {
      select.innerHTML = '';
      personas.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.persona_id;
        opt.textContent = p.name;
        select.appendChild(opt);
      });
      // Set current global default
      const globalDefault = await safeApiRequest('/api/personas/global-default');
      select.value = globalDefault.globalDefaultPersonaId;
    }
  } catch (e) {
    container.innerHTML = '<span style="color:red">Failed to load personas.</span>';
    console.error('[Personas] Failed to load:', e);
  }
}

// Re-attach event handlers
export function attachHandlers() {
  debugLog('attachHandlers', 'Starting...');
  
  // Add Persona button handler
  const addBtn = Elements.addPersonaBtn;
  if (addBtn) {
    debugLog('attachHandlers', 'Setting up Add Persona button');
    addBtn.addEventListener('click', (e) => {
      e.preventDefault();
      debugLog('addPersonaBtn.click', 'Button clicked');
      
      editingPersonaId = null;
      const modal = Elements.personaModal;
      debugLog('addPersonaBtn.click', 'Got modal:', modal);
      
      if (!modal) {
        console.error('[Personas] Persona modal not found!');
        return;
      }

      // Reset form fields
      const nameInput = Elements.personaNameInput;
      const instructionsInput = Elements.personaInstructionsInput;
      const deleteBtn = Elements.deletePersonaBtn;
      const previewDiv = Elements.personaPromptPreview;
      const versionsContainer = Elements.personaVersionsContainer;
      
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
      if (deleteBtn) deleteBtn.style.display = 'none';
      if (versionsContainer) versionsContainer.innerHTML = '';
      
      // Show modal
      debugLog('addPersonaBtn.click', 'Displaying modal');
      modal.style.display = 'block';
      modal.setAttribute('data-mode', 'create');
      if (nameInput) nameInput.focus();
    });
  }

  // Close Modal button handler
  const closeBtn = Elements.closePersonaModal;
  if (closeBtn) {
    debugLog('attachHandlers', 'Setting up Close Modal button');
    closeBtn.addEventListener('click', () => {
      const modal = Elements.personaModal;
      if (modal) {
        debugLog('closeBtn.click', 'Hiding modal');
        modal.style.display = 'none';
      }
    });
  }

  // Click outside modal to close
  const modal = Elements.personaModal;
  if (modal) {
    debugLog('attachHandlers', 'Setting up modal background click handler');
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        debugLog('modal.click', 'Closing modal via background click');
        modal.style.display = 'none';
      }
    });
  }

  // Form submit handler
  const form = Elements.personaForm;
  if (form) {
    debugLog('attachHandlers', 'Setting up form submit handler');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInput = Elements.personaNameInput;
      const instructionsInput = Elements.personaInstructionsInput;
      
      const name = nameInput ? nameInput.value.trim() : '';
      const prompt_instructions = instructionsInput ? instructionsInput.value.trim() : '';
      
      if (!name || !prompt_instructions) {
        showMessage('Name and instructions are required.', 'error');
        return;
      }
      
      try {
        if (editingPersonaId) {
          await safeApiRequest(`/api/personas/${editingPersonaId}`, 'PUT', { name, prompt_instructions });
          showMessage('Persona updated.', 'success');
        } else {
          await safeApiRequest('/api/personas', 'POST', { name, prompt_instructions });
          showMessage('Persona created.', 'success');
        }
        
        const modal = Elements.personaModal;
        if (modal) modal.style.display = 'none';
        
        loadPersonasList();
      } catch (e) {
        console.error('[Personas] Error saving persona:', e);
      }
    });
  }
}

// Export needed functions before we use them
const personas = {
  loadPersonasList,
  showMessage,
  attachHandlers
};

// Attach handlers when module loads
debugLog('init', 'Module loaded, attaching handlers...');
personas.attachHandlers();

// Export the personas object
export default personas;
