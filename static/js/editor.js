// This file will handle the initialization and configuration of the EasyMDE editor instances.

import { newTopicContentInput, replyContentInput } from './dom.js';
import { fetchActivePersonas } from './api.js'; // Import API function

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
}

if (replyContentInput) {
     replyEditor = new EasyMDE({
        ...easyMDEConfigBase,
        element: replyContentInput
    });
    initializeEditorPersonaTagging(replyEditor);
}