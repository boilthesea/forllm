import { apiRequest } from './api.js';
import { initializeTomSelect } from './ui-helpers.js';

// --- State ---
let instructionsCache = [];
let setsCache = [];

// --- Modal Handling ---
function openInstructionModal(instruction = null) {
    const instructionModal = document.getElementById('instruction-modal');
    const instructionForm = document.getElementById('instruction-form');
    const instructionModalTitle = document.getElementById('instruction-modal-title');
    const instructionIdInput = document.getElementById('instruction-id-input');
    const instructionNameInput = document.getElementById('instruction-name-input');
    const instructionPromptInput = document.getElementById('instruction-prompt-input');

    if (instruction) {
        instructionModalTitle.textContent = 'Edit Instruction';
        instructionIdInput.value = instruction.id;
        instructionNameInput.value = instruction.name;
        instructionPromptInput.value = instruction.prompt_text;
    } else {
        instructionModalTitle.textContent = 'Add Instruction';
        instructionForm.reset();
        instructionIdInput.value = '';
    }
    instructionModal.style.display = 'block';
}

function closeInstructionModal() {
    const instructionModal = document.getElementById('instruction-modal');
    if (instructionModal) {
        instructionModal.style.display = 'none';
    }
}

function openSetModal(set = null) {
    const setModal = document.getElementById('instruction-set-modal');
    const setForm = document.getElementById('instruction-set-form');
    const setModalTitle = document.getElementById('instruction-set-modal-title');
    const setIdInput = document.getElementById('instruction-set-id-input');
    const setNameInput = document.getElementById('instruction-set-name-input');
    const setInstructionsSelect = document.getElementById('instruction-set-instructions-select');

    const instructionOptions = instructionsCache.map(inst => ({ value: inst.id, text: inst.name }));
    const tomSelect = setInstructionsSelect.tomselect;

    tomSelect.clear();
    tomSelect.clearOptions();
    tomSelect.addOption(instructionOptions);

    if (set) {
        setModalTitle.textContent = 'Edit Instruction Set';
        setIdInput.value = set.id;
        setNameInput.value = set.name;
        tomSelect.setValue(set.instruction_ids);
    } else {
        setModalTitle.textContent = 'Add Instruction Set';
        setForm.reset();
        setIdInput.value = '';
    }
    setModal.style.display = 'block';
}

function closeSetModal() {
    const setModal = document.getElementById('instruction-set-modal');
    if (setModal) {
        setModal.style.display = 'none';
    }
}

// --- Data Fetching and Rendering ---
export async function loadCustomInstructionsData(container) {
    try {
        const [instructions, sets] = await Promise.all([
            apiRequest('/api/custom-instructions'),
            apiRequest('/api/instruction-sets')
        ]);
        instructionsCache = instructions;
        setsCache = sets;
        renderCustomInstructionsUI(instructions, sets, container);
    } catch (error) {
        console.error("Error loading custom instructions data:", error);
        const instructionsContainer = container.querySelector('#instructions-list-container');
        if (instructionsContainer) {
            instructionsContainer.innerHTML = `<p class="error-message">Error loading instructions: ${error.message}</p>`;
        }
    }
}

function renderCustomInstructionsUI(instructions, sets, container) {
    const instructionsContainer = container.querySelector('#instructions-list-container');
    const setsContainer = container.querySelector('#instruction-sets-list-container');

    if (!instructionsContainer || !setsContainer) return;

    instructionsContainer.innerHTML = '';
    instructions.forEach(inst => {
        const instEl = document.createElement('div');
        instEl.className = 'instruction-item';
        instEl.dataset.instructionId = inst.id;

        const subforumPills = inst.subforum_defaults.map(sf => `
            <span class="subforum-pill" data-subforum-id="${sf.subforum_id}">
                ${sf.name}
                <button class="delete-pill-btn" data-instruction-id="${inst.id}" data-subforum-id="${sf.subforum_id}">&times;</button>
            </span>
        `).join('');

        const hasSubforumDefaults = inst.subforum_defaults.length > 0;

        instEl.innerHTML = `
            <details>
                <summary class="instruction-header">
                    <strong class="instruction-name">${inst.name}</strong>
                    <div class="instruction-controls">
                        <button class="button-secondary button-small edit-instruction-btn">Edit</button>
                        <button class="button-danger button-small delete-instruction-btn">Delete</button>
                    </div>
                </summary>
                <div class="instruction-body">
                    <p class="prompt-preview"><em>Prompt:</em> ${inst.prompt_text.substring(0, 150)}${inst.prompt_text.length > 150 ? '...' : ''}</p>
                    <div class="setting-item">
                        <label>Priority:</label>
                        <input type="number" class="priority-input" value="${inst.priority}" style="width: 60px;">
                    </div>
                    <div class="setting-item">
                        <label>Global Default:</label>
                        <input type="checkbox" class="global-default-checkbox" ${inst.is_global_default ? 'checked' : ''}>
                    </div>
                    <div class="setting-item">
                        <label>Subforum Default:</label>
                        <input type="checkbox" class="subforum-default-checkbox" ${hasSubforumDefaults ? 'checked' : ''}>
                    </div>
                    <div class="subforum-input-container" style="display: ${hasSubforumDefaults ? 'block' : 'none'};">
                        <div class="subforum-pills-container">${subforumPills}</div>
                        <select class="subforum-search-input" placeholder="Add subforum..."></select>
                    </div>
                </div>
            </details>
        `;
        instructionsContainer.appendChild(instEl);
    });

    setsContainer.innerHTML = '';
    sets.forEach(set => {
        const setEl = document.createElement('div');
        setEl.className = 'instruction-set-item';
        setEl.dataset.setId = set.id;

        const instructionPills = set.instruction_ids.map(instId => {
            const instruction = instructions.find(i => i.id === instId);
            return `<span class="instruction-pill">${instruction ? instruction.name : 'Unknown'}</span>`;
        }).join('');

        setEl.innerHTML = `
            <div class="instruction-set-header">
                <strong>${set.name}</strong>
                <div class="instruction-set-controls">
                    <button class="button-secondary button-small edit-instruction-set-btn">Edit</button>
                    <button class="button-danger button-small delete-instruction-set-btn">Delete</button>
                </div>
            </div>
            <div class="instruction-set-body">${instructionPills}</div>
        `;
        setsContainer.appendChild(setEl);
    });

    // Initialize TomSelect for subforum search inputs
    container.querySelectorAll('.subforum-search-input').forEach(select => {
        if (select.tomselect) return;

        const instItem = select.closest('.instruction-item');
        const instructionId = instItem.dataset.instructionId;

        initializeTomSelect(select, {
            valueField: 'subforum_id',
            labelField: 'name',
            searchField: 'name',
            create: false,
            load: async (query, callback) => {
                try {
                    const data = await apiRequest(`/api/subforums/search?q=${encodeURIComponent(query)}`);
                    callback(data);
                } catch (error) {
                    console.error("Error fetching subforums:", error);
                    callback([]);
                }
            },
            onChange: async (value) => {
                if (!value) return;
                const subforumId = value;
                try {
                    await apiRequest(`/api/custom-instructions/${instructionId}/subforum-defaults`, 'POST', { subforum_id: subforumId });
                    loadCustomInstructionsData(container);
                } catch (error) {
                    alert(`Error adding subforum default: ${error.message}`);
                }
                const ts = select.tomselect;
                ts.clear();
                ts.blur();
            }
        });
    });
}

// --- Event Handlers ---
async function handleFormSubmit(event, container) {
    if (event.target.id === 'instruction-form') {
        event.preventDefault();
        const id = event.target.querySelector('#instruction-id-input').value;
        const data = {
            name: event.target.querySelector('#instruction-name-input').value,
            prompt_text: event.target.querySelector('#instruction-prompt-input').value,
            priority: 0,
            is_global_default: false
        };

        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/custom-instructions/${id}` : '/api/custom-instructions';

        if (id) {
            const original = instructionsCache.find(i => i.id == id);
            if (original) {
                data.priority = original.priority;
                data.is_global_default = original.is_global_default;
            }
        }

        try {
            await apiRequest(url, method, data);
            closeInstructionModal();
            loadCustomInstructionsData(container);
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    }

    if (event.target.id === 'instruction-set-form') {
        event.preventDefault();
        const id = event.target.querySelector('#instruction-set-id-input').value;
        const setInstructionsSelect = document.getElementById('instruction-set-instructions-select');
        const data = {
            name: event.target.querySelector('#instruction-set-name-input').value,
            instruction_ids: setInstructionsSelect.tomselect.getValue()
        };
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/instruction-sets/${id}` : '/api/instruction-sets';

        try {
            await apiRequest(url, method, data);
            closeSetModal();
            loadCustomInstructionsData(container);
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    }
}

async function handleClick(event, container) {
    // Modal open/close
    if (event.target.id === 'add-instruction-btn') openInstructionModal();
    if (event.target.id === 'add-instruction-set-btn') openSetModal();
    if (event.target.closest('.close-btn')) {
        if (event.target.closest('#instruction-modal')) closeInstructionModal();
        if (event.target.closest('#instruction-set-modal')) closeSetModal();
    }
    if (event.target.matches('#instruction-modal, #instruction-set-modal')) {
        event.target.style.display = 'none';
    }

    // Instruction item controls
    const instItem = event.target.closest('.instruction-item');
    if (instItem) {
        const instructionId = instItem.dataset.instructionId;
        if (event.target.classList.contains('edit-instruction-btn')) {
            const instruction = instructionsCache.find(i => i.id == instructionId);
            if (instruction) openInstructionModal(instruction);
        } else if (event.target.classList.contains('delete-instruction-btn')) {
            if (confirm('Are you sure you want to delete this instruction?')) {
                try {
                    await apiRequest(`/api/custom-instructions/${instructionId}`, 'DELETE');
                    loadCustomInstructionsData(container);
                } catch (error) {
                    alert(`Error deleting instruction: ${error.message}`);
                }
            }
        } else if (event.target.classList.contains('delete-pill-btn')) {
            const subforumId = event.target.dataset.subforumId;
            if (confirm(`Are you sure you want to remove this subforum default?`)) {
                try {
                    await apiRequest(`/api/custom-instructions/${instructionId}/subforum-defaults/${subforumId}`, 'DELETE');
                    loadCustomInstructionsData(container);
                } catch (error) {
                    alert(`Error removing default: ${error.message}`);
                }
            }
        }
    }

    // Instruction set item controls
    const setItem = event.target.closest('.instruction-set-item');
    if (setItem) {
        const setId = setItem.dataset.setId;
        if (event.target.classList.contains('edit-instruction-set-btn')) {
            const set = setsCache.find(s => s.id == setId);
            if (set) openSetModal(set);
        } else if (event.target.classList.contains('delete-instruction-set-btn')) {
            if (confirm('Are you sure you want to delete this set?')) {
                try {
                    await apiRequest(`/api/instruction-sets/${setId}`, 'DELETE');
                    loadCustomInstructionsData(container);
                } catch (error) {
                    alert(`Error deleting set: ${error.message}`);
                }
            }
        }
    }
}

async function handleChange(event, container) {
    const instItem = event.target.closest('.instruction-item');
    if (!instItem) return;
    const instructionId = instItem.dataset.instructionId;
    const instruction = instructionsCache.find(i => i.id == instructionId);
    if (!instruction) return;

    if (event.target.classList.contains('priority-input') || event.target.classList.contains('global-default-checkbox')) {
        const priority = instItem.querySelector('.priority-input').value;
        const is_global_default = instItem.querySelector('.global-default-checkbox').checked;
        
        try {
            await apiRequest(`/api/custom-instructions/${instructionId}`, 'PUT', {
                name: instruction.name,
                prompt_text: instruction.prompt_text,
                priority: parseInt(priority, 10),
                is_global_default: is_global_default
            });
            // Update cache to prevent race conditions on multiple fast changes
            instruction.priority = parseInt(priority, 10);
            instruction.is_global_default = is_global_default;
        } catch (error) {
            alert(`Error updating instruction: ${error.message}`);
            loadCustomInstructionsData(container); // Re-sync with DB on error
        }
    } else if (event.target.classList.contains('subforum-default-checkbox')) {
        const inputContainer = instItem.querySelector('.subforum-input-container');
        inputContainer.style.display = event.target.checked ? 'block' : 'none';
    }
}

// --- Initialization ---
let isInitialized = false;
export function initializeCustomInstructions() {
    if (isInitialized) return;

    // The container is needed for reloading data, we can get it when needed.
    const getContainer = () => document.getElementById('settings-page-content') || document.getElementById('settings-modal');

    // Initialize TomSelect for the set modal once
    const setInstructionsSelect = document.getElementById('instruction-set-instructions-select');
    if (setInstructionsSelect && !setInstructionsSelect.tomselect) {
        initializeTomSelect(setInstructionsSelect, {
            plugins: ['remove_button'],
        });
    }

    document.addEventListener('submit', (event) => {
        if (event.target.closest('#settings-custom-instructions-section') || event.target.closest('.modal')) {
            handleFormSubmit(event, getContainer());
        }
    });

    document.addEventListener('click', (event) => {
        // We listen globally for modal events, but scope other clicks to the section
        if (event.target.closest('#settings-custom-instructions-section') || event.target.closest('.modal')) {
             handleClick(event, getContainer());
        }
    });
    
    document.addEventListener('change', (event) => {
        if (event.target.closest('#settings-custom-instructions-section')) {
            handleChange(event, getContainer());
        }
    });

    isInitialized = true;
}