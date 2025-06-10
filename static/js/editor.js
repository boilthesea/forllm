// This file will handle the initialization and configuration of the EasyMDE editor instances.

import { newTopicContentInput, replyContentInput } from './dom.js';
import { fetchActivePersonas } from './api.js'; // Import API function

let cachedAttachmentsContent = { 'new-topic': { text: '', filesHash: null }, 'reply': { text: '', filesHash: null } };

// --- Persona Tagging Globals ---
let activePersonasCache = [];
let personasCacheTimestamp = 0;
const PERSONA_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
let personaSuggestionsDiv = null;
let currentMentionState = {
    editor: null, // The CodeMirror instance
    query: '',
    startPos: null, // {line, ch} where '@' was typed
    active: false,
    selectedIndex: -1,
    currentResults: [] // To store currently displayed results for keyboard navigation
};

// --- EasyMDE Configuration ---
const easyMDEConfigBase = {
    spellChecker: false,
    status: ["lines", "words"],
    toolbar: [
        "bold", "italic", "|",
        "heading-1", "heading-2", "heading-3", "|",
        "quote", "unordered-list", "ordered-list", "|",
        "code", "link", "|",
        "preview", "side-by-side", "fullscreen", "|",
        "guide"
    ],
};

export let newTopicEditor = null;
export let replyEditor = null;

function createPersonaSuggestionsUI() {
    if (!personaSuggestionsDiv) {
        personaSuggestionsDiv = document.createElement('div');
        // Ensure this ID matches the one in index.html and targeted by editor.css
        personaSuggestionsDiv.id = 'personaMentionSuggestions'; 
        // Styles are primarily handled by CSS. Ensure functional styles like position and initial display are set.
        personaSuggestionsDiv.style.position = 'absolute'; 
        personaSuggestionsDiv.style.display = 'none'; 
        document.body.appendChild(personaSuggestionsDiv);
    }
}

function hidePersonaSuggestions() {
    if (personaSuggestionsDiv) {
        personaSuggestionsDiv.style.display = 'none';
        personaSuggestionsDiv.innerHTML = ''; // Clear previous suggestions
    }
    currentMentionState.active = false;
    currentMentionState.editor = null;
    currentMentionState.query = '';
    currentMentionState.startPos = null;
    currentMentionState.selectedIndex = -1;
    currentMentionState.currentResults = [];
}

async function displayPersonaSuggestions(cm, query) {
    if (!currentMentionState.active) return;

    const now = Date.now();
    if (!activePersonasCache.length || (now - personasCacheTimestamp > PERSONA_CACHE_DURATION)) {
        console.log("Fetching active personas...");
        activePersonasCache = await fetchActivePersonas() || [];
        personasCacheTimestamp = now;
        if (!activePersonasCache.length) {
            console.log("No active personas found or failed to fetch.");
            hidePersonaSuggestions();
            return;
        }
    }

    const filteredPersonas = activePersonasCache.filter(p =>
        p.name.toLowerCase().includes(query.toLowerCase())
    );

    currentMentionState.currentResults = filteredPersonas;
    currentMentionState.selectedIndex = -1; 

    personaSuggestionsDiv.innerHTML = ''; // Clear previous suggestions
    if (!filteredPersonas.length) {
        const noResultsItem = document.createElement('div');
        noResultsItem.textContent = 'No matching personas';
        noResultsItem.classList.add('suggestion-item', 'no-results'); // Add classes for styling
        personaSuggestionsDiv.appendChild(noResultsItem);
    } else {
        filteredPersonas.forEach((persona, index) => {
            const item = document.createElement('div');
            item.textContent = persona.name;
            item.classList.add('suggestion-item'); // Add a common class for items
            item.dataset.id = persona.persona_id;
            item.dataset.name = persona.name;

            item.addEventListener('mouseenter', () => {
                // Remove 'selected' from previously selected item if any
                if (currentMentionState.selectedIndex !== -1 && personaSuggestionsDiv.children[currentMentionState.selectedIndex]) {
                    personaSuggestionsDiv.children[currentMentionState.selectedIndex].classList.remove('selected');
                }
                // Add 'selected' to current item and update index
                item.classList.add('selected');
                currentMentionState.selectedIndex = index;
            });
            item.addEventListener('mouseleave', () => {
                item.classList.remove('selected');
                 // Optional: reset selectedIndex if mouse leaves, or rely on keyboard nav to manage it
            });

            item.addEventListener('click', () => {
                insertPersonaTag(cm, persona);
            });
            personaSuggestionsDiv.appendChild(item);
        });
    }

    // Position suggestion div. Consider editor scroll and viewport.
    const editorWrapper = cm.getWrapperElement();
    const editorRect = editorWrapper.getBoundingClientRect();
    const bodyRect = document.body.getBoundingClientRect(); // To offset body scrolling if #personaMentionSuggestions is child of body

    // Get coordinates of the '@' character or start of the query
    const startCoords = cm.cursorCoords(currentMentionState.startPos, 'local');

    personaSuggestionsDiv.style.left = `${editorRect.left + startCoords.left - bodyRect.left}px`;
    personaSuggestionsDiv.style.top = `${editorRect.top + startCoords.bottom - bodyRect.top + 5}px`; // 5px below the line
    personaSuggestionsDiv.style.display = 'block';
    updateSuggestionsHighlight(false); // Update highlight without scrolling initially
}

function insertPersonaTag(cm, persona) {
    if (!currentMentionState.startPos || !cm) {
        hidePersonaSuggestions();
        return;
    }
    const textToInsert = `@[${persona.name}](${persona.persona_id})`;
    const currentCursor = cm.getCursor();
    // Replace from the '@' symbol (startPos) up to the current cursor position
    cm.replaceRange(textToInsert, currentMentionState.startPos, currentCursor);
    hidePersonaSuggestions();
    cm.focus(); 
}

function handleEditorKeyEvent(cm, event, type) {
    // If suggestions are active, certain key events are handled differently
    if (currentMentionState.active && currentMentionState.editor === cm) {
        if (type === 'keydown') {
            if (['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault(); // Prevent default editor actions for these keys
                if (event.key === 'Escape') {
                    hidePersonaSuggestions();
                } else if (event.key === 'Enter' || event.key === 'Tab') {
                    if (currentMentionState.selectedIndex !== -1 && currentMentionState.currentResults[currentMentionState.selectedIndex]) {
                        insertPersonaTag(cm, currentMentionState.currentResults[currentMentionState.selectedIndex]);
                    } else {
                        hidePersonaSuggestions(); // Or insert query as plain text if no selection
                    }
                } else if (event.key === 'ArrowDown') {
                    if (currentMentionState.currentResults.length > 0) {
                        currentMentionState.selectedIndex = (currentMentionState.selectedIndex + 1) % currentMentionState.currentResults.length;
                        updateSuggestionsHighlight();
                    }
                } else if (event.key === 'ArrowUp') {
                    if (currentMentionState.currentResults.length > 0) {
                        currentMentionState.selectedIndex = (currentMentionState.selectedIndex - 1 + currentMentionState.currentResults.length) % currentMentionState.currentResults.length;
                        updateSuggestionsHighlight();
                    }
                }
                return; // Event handled
            }
        }
        // For keyup, or other keydown events when suggestions are active
        if (type === 'keyup') {
            const cursor = cm.getCursor();
            // Check if cursor is still within a potential mention
            if (cursor.line === currentMentionState.startPos.line && cursor.ch >= currentMentionState.startPos.ch) {
                const textFromAt = cm.getRange(currentMentionState.startPos, cursor);
                if (textFromAt.startsWith('@') && !textFromAt.includes(' ') && textFromAt.length <= 50) { // Basic validation
                    currentMentionState.query = textFromAt.substring(1); // Remove '@'
                    displayPersonaSuggestions(cm, currentMentionState.query);
                } else {
                    hidePersonaSuggestions(); // Invalid mention (e.g., space typed, or @ deleted)
                }
            } else {
                hidePersonaSuggestions(); // Cursor moved out of mention line/context
            }
            return; // Event handled (or decided to hide)
        }
    }

    // If suggestions are NOT active, check if we need to activate them
    if (type === 'keyup' && !currentMentionState.active) {
        const cursor = cm.getCursor();
        if (cursor.ch > 0) {
            const charBefore = cm.getRange({ line: cursor.line, ch: cursor.ch - 1 }, cursor);
            if (charBefore === '@') {
                currentMentionState.active = true;
                currentMentionState.editor = cm;
                currentMentionState.query = '';
                currentMentionState.startPos = { line: cursor.line, ch: cursor.ch - 1 };
                displayPersonaSuggestions(cm, '');
            }
        }
    }
}

function updateSuggestionsHighlight(shouldScroll = true) {
    if (!personaSuggestionsDiv || !currentMentionState.active) return;
    Array.from(personaSuggestionsDiv.children).forEach((child, index) => {
        if (child.classList.contains('no-results')) return; // Skip "no results" item
        if (index === currentMentionState.selectedIndex) {
            child.classList.add('selected');
            if (shouldScroll) {
                child.scrollIntoView({ block: 'nearest' });
            }
        } else {
            child.classList.remove('selected');
        }
    });
}


function initializeEditorPersonaTagging(editorInstance) {
    if (!editorInstance) return;
    createPersonaSuggestionsUI(); 
    const cm = editorInstance.codemirror;

    cm.on('keyup', (cmInstance, event) => {
        // Filter out keys that should not trigger suggestion logic / query updates
        if (['Control', 'Alt', 'Shift', 'Meta', 'CapsLock', 'Escape', 'Enter', 'Tab', 
             'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 
             'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
            return;
        }
        handleEditorKeyEvent(cmInstance, event, 'keyup');
    });
    cm.on('keydown', (cmInstance, event) => {
        // Only pass to handler if suggestions are active and it's a relevant key
        if (currentMentionState.active && currentMentionState.editor === cmInstance &&
            ['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
            handleEditorKeyEvent(cmInstance, event, 'keydown');
        }
    });
    cm.on('blur', (cmInstance) => {
        setTimeout(() => {
            // Check if the new active element is part of our suggestion box
            if (personaSuggestionsDiv && !personaSuggestionsDiv.contains(document.activeElement)) {
                 if (currentMentionState.editor === cmInstance) { // Only hide if blur is from the currently active editor
                    hidePersonaSuggestions();
                }
            }
        }, 200);
    });
}

// Initialize editors
if (newTopicContentInput) {
    newTopicEditor = new EasyMDE({
        ...easyMDEConfigBase,
        element: newTopicContentInput
    });
    initializeEditorPersonaTagging(newTopicEditor);
    initializeTokenBreakdownDisplay(newTopicEditor, 'new-topic');
}

if (replyContentInput) {
     replyEditor = new EasyMDE({
        ...easyMDEConfigBase,
        element: replyContentInput
    });
    initializeEditorPersonaTagging(replyEditor);
    initializeTokenBreakdownDisplay(replyEditor, 'reply');
}

// --- Token Breakdown Display ---

// Debounce function - (Make sure it's defined, or import if it's global)
function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

// Function to update token breakdown via API
async function updateTokenBreakdown(editorInstance, editorType) {
    if (!editorInstance) return;

    const container = document.getElementById(`${editorType}-token-breakdown-container`);
    if (!container) {
        console.error(`Token breakdown container not found for ${editorType}`);
        return;
    }
    container.style.display = 'block'; // Ensure it's visible

    const current_post_text = editorInstance.value();

    // --- Simplification for selected_persona_id ---
    // Try to get from 'llm-persona-select' if it's relevant, otherwise null.
    // This element is in `index.html`'s `subforum-personas-bar`.
    // Its applicability depends on whether this bar is visible/used for the current editor context.
    let selected_persona_id = null;
    const personaSelectElement = document.getElementById('llm-persona-select');
    if (personaSelectElement && personaSelectElement.value) {
        // Check if the persona selector is relevant for the current editor context
        // For a new topic, it might be less relevant than for a reply if the bar is tied to existing topic context.
        // For now, we'll take it if available. This might need refinement.
        if (editorType === 'reply' || (editorType === 'new-topic' && personaSelectElement.offsetParent !== null)) { // visible check
             if (personaSelectElement.value !== "0" && personaSelectElement.value !== "") { // "0" or "" often means no selection / default
                selected_persona_id = parseInt(personaSelectElement.value, 10);
            }
        }
    }
    // console.log(`Editor type: ${editorType}, Selected Persona ID: ${selected_persona_id}`);


    // --- Simplification for attachments_text ---
    const attachments_text = cachedAttachmentsContent[editorType] ? cachedAttachmentsContent[editorType].text : "";
    // console.log(`Using cached attachments text for ${editorType} in updateTokenBreakdown`);


    try {
        const response = await fetch('/api/prompts/estimate_tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_post_text: current_post_text,
                selected_persona_id: selected_persona_id,
                attachments_text: attachments_text,
                // parent_post_id: null // Not used yet
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error('Error fetching token breakdown:', errorData.error || response.statusText);
            // Display a simplified error in the breakdown area
            document.getElementById(`${editorType}-token-total-estimated`).textContent = 'Error';
            document.getElementById(`${editorType}-token-model-context-window`).textContent = 'N/A';
            return;
        }

        const data = await response.json();

        // Update DOM elements
        document.getElementById(`${editorType}-token-post-content`).textContent = `~${data.post_content_tokens}`;
        document.getElementById(`${editorType}-token-persona-name`).textContent = data.persona_name || "Default";
        document.getElementById(`${editorType}-token-persona-prompt`).textContent = `~${data.persona_prompt_tokens}`;
        document.getElementById(`${editorType}-token-system-prompt`).textContent = `~${data.system_prompt_tokens}`;
        document.getElementById(`${editorType}-token-attachments`).textContent = `~${data.attachments_tokens}`;
        document.getElementById(`${editorType}-token-chat-history`).textContent = `~${data.chat_history_tokens}`;
        document.getElementById(`${editorType}-token-total-estimated`).textContent = `~${data.total_estimated_tokens}`;
        document.getElementById(`${editorType}-token-model-context-window`).textContent = data.model_context_window || "N/A";
        document.getElementById(`${editorType}-token-model-name`).textContent = data.model_name || "default";

        // Update visual bar
        const visualBar = document.getElementById(`${editorType}-token-visual-bar`);
        let percentage = 0;
        if (data.model_context_window && data.model_context_window > 0) {
            percentage = (data.total_estimated_tokens / data.model_context_window) * 100;
        }
        percentage = Math.max(0, Math.min(100, percentage)); // Clamp between 0 and 100

        visualBar.style.width = percentage + '%';
        if (percentage >= 90) {
            visualBar.style.backgroundColor = '#D32F2F'; // Red
        } else if (percentage >= 70) {
            visualBar.style.backgroundColor = '#FBC02D'; // Yellow
        } else {
            visualBar.style.backgroundColor = '#4CAF50'; // Green
        }

    } catch (error) {
        console.error('Failed to send request for token breakdown:', error);
        document.getElementById(`${editorType}-token-total-estimated`).textContent = 'Error';
        document.getElementById(`${editorType}-token-model-context-window`).textContent = 'N/A';
    }
}

// Function to set up token breakdown display for an editor instance
function initializeTokenBreakdownDisplay(editorInstance, editorType) {
    if (!editorInstance || !editorInstance.codemirror) {
        console.warn(`Editor instance or CodeMirror not found for ${editorType}. Token breakdown display disabled.`);
        return;
    }

    const breakdownContainer = document.getElementById(`${editorType}-token-breakdown-container`);
    if (!breakdownContainer) {
        console.warn(`Token breakdown container not found for ${editorType}.`);
        return;
    }
    breakdownContainer.style.display = 'block'; // Make it visible

    // Debounced update function specific to this editor instance
    const debouncedTokenBreakdownUpdate = debounce(() => {
        updateTokenBreakdown(editorInstance, editorType);
    }, 750); // 750ms debounce delay

    // Listen for changes in the editor
    editorInstance.codemirror.on('change', debouncedTokenBreakdownUpdate);

    // Also listen for changes on persona selector and attachment input
    const personaSelector = document.getElementById('llm-persona-select');
    if (personaSelector) {
        personaSelector.addEventListener('change', () => updateTokenBreakdown(editorInstance, editorType));
    }

    const attachmentInputId = editorType === 'new-topic' ? 'new-topic-attachment-input' : 'reply-attachment-input';
    const attachmentInput = document.getElementById(attachmentInputId);
    if (attachmentInput) {
        attachmentInput.addEventListener('change', async () => {
            // console.log(`Attachment change detected for ${editorType}`);
            const files = attachmentInput.files;
            let combinedText = "";
            let filesHash = ""; // Simple hash: concat names and sizes

            if (files && files.length > 0) {
                const textFilePromises = [];
                const fileDetailsForHash = [];

                const plainTextMimeTypes = [
                    'text/plain', 'text/markdown', 'text/csv', 'application/json', 'application/xml',
                    'text/html', 'text/css', 'text/javascript', 'application/javascript',
                    'application/x-javascript', 'text/x-python', 'application/python',
                    'application/x-python', 'text/x-java-source', 'text/x-csrc', 'text/x-c++src',
                    'application/rtf', 'text/richtext', 'text/yaml', 'application/yaml', 'text/x-yaml',
                    'application/x-yaml', 'text/toml', 'application/toml', 'application/ld+json',
                    'text/calendar', 'text/vcard', 'text/sgml', 'application/sgml', 'text/tab-separated-values',
                    'application/xhtml+xml', 'application/rss+xml', 'application/atom+xml', 'text/x-script.python'
                ];
                const plainTextExtensions = [
                    '.txt', '.md', '.markdown', '.csv', '.json', '.xml', '.html', '.htm', '.css', '.js',
                    '.py', '.pyw', '.java', '.c', '.cpp', '.h', '.hpp', '.rtf', '.yaml', '.yml',
                    '.toml', '.ini', '.cfg', '.conf', '.log', '.text', '.tex', '.tsv', '.jsonld',
                    '.ical', '.ics', '.vcf', '.vcard', '.sgml', '.sgm', '.xhtml', '.xht', '.rss', '.atom',
                    '.sh', '.bash', '.ps1', '.bat', '.cmd'
                ];

                for (const file of files) {
                    fileDetailsForHash.push(`${file.name}_${file.size}`);
                    let isTextFile = false;
                    if (plainTextMimeTypes.includes(file.type)) {
                        isTextFile = true;
                    } else if (file.type === "" || file.type === "application/octet-stream") {
                        const fileNameLower = file.name.toLowerCase();
                        for (const ext of plainTextExtensions) {
                            if (fileNameLower.endsWith(ext)) {
                                isTextFile = true;
                                break;
                            }
                        }
                    }

                    if (isTextFile) {
                        textFilePromises.push(file.text());
                    }
                }
                try {
                    const fileContents = await Promise.all(textFilePromises);
                    combinedText = fileContents.join("\n\n---\n\n");
                } catch (error) {
                    console.error("Error reading attachment file contents for caching:", error);
                    combinedText = "[Error reading attachment contents]";
                }
                filesHash = fileDetailsForHash.join('|');
            }

            cachedAttachmentsContent[editorType] = { text: combinedText, filesHash: filesHash };
            // console.log(`Cached attachments for ${editorType}:`, cachedAttachmentsContent[editorType]);

            updateTokenBreakdown(editorInstance, editorType);
        });
    }


    // Initial breakdown update
    updateTokenBreakdown(editorInstance, editorType);
}