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
        personaSuggestionsDiv.id = 'persona-suggestions';
        personaSuggestionsDiv.style.position = 'absolute';
        personaSuggestionsDiv.style.border = '1px solid #ccc';
        personaSuggestionsDiv.style.backgroundColor = 'white';
        personaSuggestionsDiv.style.display = 'none';
        personaSuggestionsDiv.style.zIndex = '1000'; // Ensure it's above the editor
        personaSuggestionsDiv.style.maxHeight = '200px';
        personaSuggestionsDiv.style.overflowY = 'auto';
        document.body.appendChild(personaSuggestionsDiv);
    }
}

function hidePersonaSuggestions() {
    if (personaSuggestionsDiv) {
        personaSuggestionsDiv.style.display = 'none';
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
    currentMentionState.selectedIndex = -1; // Reset selection

    if (!filteredPersonas.length) {
        personaSuggestionsDiv.innerHTML = '<div>No matching personas</div>';
        // Optionally hide if no results, or show "No results"
        // For now, keep it visible to show "No matching personas"
    } else {
        personaSuggestionsDiv.innerHTML = ''; // Clear previous
        filteredPersonas.forEach((persona, index) => {
            const item = document.createElement('div');
            item.textContent = persona.name;
            item.style.padding = '5px';
            item.style.cursor = 'pointer';
            item.dataset.id = persona.persona_id;
            item.dataset.name = persona.name;

            item.addEventListener('mouseenter', () => {
                // Optional: highlight on mouse enter
                if (currentMentionState.selectedIndex !== -1 && personaSuggestionsDiv.children[currentMentionState.selectedIndex]) {
                    personaSuggestionsDiv.children[currentMentionState.selectedIndex].style.backgroundColor = 'white';
                }
                item.style.backgroundColor = '#eee';
                currentMentionState.selectedIndex = index;
            });
            item.addEventListener('mouseleave', () => {
                 // Optional: remove highlight on mouse leave if not selected by keyboard
                // item.style.backgroundColor = 'white'; 
            });

            item.addEventListener('click', () => {
                insertPersonaTag(cm, persona);
            });
            personaSuggestionsDiv.appendChild(item);
        });
    }

    const cursorPos = cm.cursorCoords(true, 'local');
    personaSuggestionsDiv.style.left = `${cursorPos.left}px`;
    personaSuggestionsDiv.style.top = `${cursorPos.bottom + 5}px`; // A bit below the cursor
    personaSuggestionsDiv.style.display = 'block';
}

function insertPersonaTag(cm, persona) {
    if (!currentMentionState.startPos || !cm) {
        hidePersonaSuggestions();
        return;
    }
    const textToInsert = `@[${persona.name}](${persona.persona_id})`;
    const currentCursor = cm.getCursor();
    // Replace from the '@' symbol up to the current cursor position
    cm.replaceRange(textToInsert, currentMentionState.startPos, currentCursor);
    hidePersonaSuggestions();
    cm.focus(); // Refocus editor
}

function handleEditorKeyEvent(cm, event, type) {
    if (type === 'keyup') {
        const cursor = cm.getCursor();
        const token = cm.getTokenAt(cursor);
        let charBefore = '';
        if (cursor.ch > 0) {
            charBefore = cm.getRange({ line: cursor.line, ch: cursor.ch - 1 }, cursor);
        }

        if (charBefore === '@') {
            currentMentionState.active = true;
            currentMentionState.editor = cm;
            currentMentionState.query = '';
            currentMentionState.startPos = { line: cursor.line, ch: cursor.ch - 1 };
            displayPersonaSuggestions(cm, '');
        } else if (currentMentionState.active && currentMentionState.editor === cm) {
            if (event.key && event.key.length === 1 && !event.altKey && !event.ctrlKey && event.key !== '@') { // Alphanumeric or symbol
                const prevCursor = { line: currentMentionState.startPos.line, ch: currentMentionState.startPos.ch + 1 };
                currentMentionState.query = cm.getRange(prevCursor, cursor);
                displayPersonaSuggestions(cm, currentMentionState.query);
            } else if (event.key === 'Backspace') {
                const prevCursor = { line: currentMentionState.startPos.line, ch: currentMentionState.startPos.ch +1 };
                 // Check if cursor is still after startPos.ch
                if (cursor.ch > currentMentionState.startPos.ch) {
                    currentMentionState.query = cm.getRange(prevCursor, cursor);
                    displayPersonaSuggestions(cm, currentMentionState.query);
                } else {
                    hidePersonaSuggestions(); // Cursor moved before or at @
                }
            } else if (!cm.getRange(currentMentionState.startPos, cursor).startsWith('@')) {
                 // If the @ is deleted or structure is broken
                 hidePersonaSuggestions();
            }
        }
    } else if (type === 'keydown' && currentMentionState.active && currentMentionState.editor === cm) {
        if (event.key === 'Escape') {
            event.preventDefault();
            hidePersonaSuggestions();
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (currentMentionState.selectedIndex !== -1 && currentMentionState.currentResults[currentMentionState.selectedIndex]) {
                insertPersonaTag(cm, currentMentionState.currentResults[currentMentionState.selectedIndex]);
            } else {
                hidePersonaSuggestions(); // Or insert current query as plain text? For now, just hide.
            }
        } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            if (currentMentionState.selectedIndex < currentMentionState.currentResults.length - 1) {
                currentMentionState.selectedIndex++;
                updateSuggestionsHighlight();
            }
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            if (currentMentionState.selectedIndex > 0) {
                currentMentionState.selectedIndex--;
                updateSuggestionsHighlight();
            }
        }
    }
}

function updateSuggestionsHighlight() {
    if (!personaSuggestionsDiv || !currentMentionState.active) return;
    Array.from(personaSuggestionsDiv.children).forEach((child, index) => {
        if (index === currentMentionState.selectedIndex) {
            child.style.backgroundColor = '#ddd'; // Highlight color
            child.scrollIntoView({ block: 'nearest' });
        } else {
            child.style.backgroundColor = 'white'; // Default background
        }
    });
}


function initializeEditorPersonaTagging(editorInstance) {
    if (!editorInstance) return;
    createPersonaSuggestionsUI(); // Ensure UI is created
    const cm = editorInstance.codemirror;

    cm.on('keyup', (cmInstance, event) => {
        handleEditorKeyEvent(cmInstance, event, 'keyup');
    });
    cm.on('keydown', (cmInstance, event) => {
        handleEditorKeyEvent(cmInstance, event, 'keydown');
    });
    cm.on('blur', (cmInstance) => {
        // Delay hiding to allow click on suggestion box
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