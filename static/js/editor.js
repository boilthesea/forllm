// This file will handle the initialization and configuration of the EasyMDE editor instances.

import { newTopicContentInput, replyContentInput } from './dom.js';
import { apiRequest } from './api.js';

let cachedAttachmentsContent = { 'new-topic': { text: '', filesHash: null }, 'reply': { text: '', filesHash: null } };

// --- Persona Tagging Globals ---
let activePersonasCache = [];
let personasCacheTimestamp = 0;
const PERSONA_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
let personaSuggestionsDiv = null;
let currentMentionState = {
    editor: null,
    query: '',
    startPos: null,
    active: false,
    selectedIndex: -1,
    currentResults: []
};

// --- File Tagging Globals ---
let fileTagSuggestionsDiv = null;
let fileTagState = {
    editor: null,
    query: '',
    startPos: null,
    active: false,
    selectedIndex: -1,
    currentResults: []
};
let fileTagDebounceTimer = null;

// --- EasyMDE Configuration ---
const easyMDEConfigBase = {
    spellChecker: false,
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

function createEditorConfig(editorType) {
    return {
        ...easyMDEConfigBase,
        status: [
            "words",
            "lines",
            {
                className: `token-summary-control ${editorType}-token-summary`,
                defaultValue: (el) => {
                    el.innerHTML = ` | <span class="toggle-button" title="Toggle Token Breakdown">[+]</span> Tokens: <span class="total-token-count ${editorType}-statusbar-token-count">~0</span>`;
                },
                onUpdate: () => {}
            }
        ]
    };
}

function createPersonaSuggestionsUI() {
    if (!personaSuggestionsDiv) {
        personaSuggestionsDiv = document.createElement('div');
        personaSuggestionsDiv.id = 'personaMentionSuggestions';
        personaSuggestionsDiv.style.position = 'absolute';
        personaSuggestionsDiv.style.display = 'none';
        document.body.appendChild(personaSuggestionsDiv);
    }
}

function hidePersonaSuggestions() {
    if (personaSuggestionsDiv) {
        personaSuggestionsDiv.style.display = 'none';
        personaSuggestionsDiv.innerHTML = '';
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
        activePersonasCache = await apiRequest('/api/personas/list_active') || [];
        personasCacheTimestamp = now;
        if (!activePersonasCache.length) {
            hidePersonaSuggestions();
            return;
        }
    }

    const filteredPersonas = activePersonasCache.filter(p =>
        p.name.toLowerCase().includes(query.toLowerCase())
    );

    currentMentionState.currentResults = filteredPersonas;
    currentMentionState.selectedIndex = -1;

    personaSuggestionsDiv.innerHTML = '';
    if (!filteredPersonas.length) {
        const noResultsItem = document.createElement('div');
        noResultsItem.textContent = 'No matching personas';
        noResultsItem.classList.add('suggestion-item', 'no-results');
        personaSuggestionsDiv.appendChild(noResultsItem);
    } else {
        filteredPersonas.forEach((persona, index) => {
            const item = document.createElement('div');
            item.textContent = persona.name;
            item.classList.add('suggestion-item');
            item.dataset.id = persona.persona_id;
            item.dataset.name = persona.name;
            item.addEventListener('click', () => insertPersonaTag(cm, persona));
            personaSuggestionsDiv.appendChild(item);
        });
    }

    const startCoords = cm.cursorCoords(currentMentionState.startPos, 'local');
    const editorWrapper = cm.getWrapperElement();
    const editorRect = editorWrapper.getBoundingClientRect();
    const bodyRect = document.body.getBoundingClientRect();

    personaSuggestionsDiv.style.left = `${editorRect.left + startCoords.left - bodyRect.left}px`;
    personaSuggestionsDiv.style.top = `${editorRect.top + startCoords.bottom - bodyRect.top + 5}px`;
    personaSuggestionsDiv.style.display = 'block';
    updateSuggestionsHighlight(false);
}

function insertPersonaTag(cm, persona) {
    if (!currentMentionState.startPos || !cm) {
        hidePersonaSuggestions();
        return;
    }
    const textToInsert = `@[${persona.name}](${persona.persona_id})`;
    const currentCursor = cm.getCursor();
    cm.replaceRange(textToInsert, currentMentionState.startPos, currentCursor);
    hidePersonaSuggestions();
    cm.focus();
}

function handleEditorKeyEvent(cm, event, type) {
    if (fileTagState.active && fileTagState.editor === cm) {
        if (type === 'keydown') {
            if (['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault();
                if (event.key === 'Escape') {
                    hideFileTagSuggestions();
                } else if (event.key === 'Enter' || event.key === 'Tab') {
                    if (fileTagState.selectedIndex !== -1 && fileTagState.currentResults[fileTagState.selectedIndex]) {
                        insertFileTag(cm, fileTagState.currentResults[fileTagState.selectedIndex]);
                    } else {
                        hideFileTagSuggestions();
                    }
                } else if (event.key === 'ArrowDown') {
                    if (fileTagState.currentResults.length > 0) {
                        fileTagState.selectedIndex = (fileTagState.selectedIndex + 1) % fileTagState.currentResults.length;
                        updateFileTagSuggestionsHighlight();
                    }
                } else if (event.key === 'ArrowUp') {
                    if (fileTagState.currentResults.length > 0) {
                        fileTagState.selectedIndex = (fileTagState.selectedIndex - 1 + fileTagState.currentResults.length) % fileTagState.currentResults.length;
                        updateFileTagSuggestionsHighlight();
                    }
                }
                return;
            }
        }
        if (type === 'keyup') {
            const cursor = cm.getCursor();
            if (cursor.line === fileTagState.startPos.line && cursor.ch >= fileTagState.startPos.ch) {
                const textFromHash = cm.getRange(fileTagState.startPos, cursor);
                if (textFromHash.startsWith('#') && !textFromHash.substring(1).includes(' ') && textFromHash.length <= 100) {
                    fileTagState.query = textFromHash.substring(1);
                    displayFileTagSuggestions(cm, fileTagState.query);
                } else {
                    hideFileTagSuggestions();
                }
            } else {
                hideFileTagSuggestions();
            }
            return;
        }
    }

    if (currentMentionState.active && currentMentionState.editor === cm) {
        if (type === 'keydown') {
            if (['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault();
                if (event.key === 'Escape') {
                    hidePersonaSuggestions();
                } else if (event.key === 'Enter' || event.key === 'Tab') {
                    if (currentMentionState.selectedIndex !== -1 && currentMentionState.currentResults[currentMentionState.selectedIndex]) {
                        insertPersonaTag(cm, currentMentionState.currentResults[currentMentionState.selectedIndex]);
                    } else {
                        hidePersonaSuggestions();
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
                return;
            }
        }
        if (type === 'keyup') {
            const cursor = cm.getCursor();
            if (cursor.line === currentMentionState.startPos.line && cursor.ch >= currentMentionState.startPos.ch) {
                const textFromAt = cm.getRange(currentMentionState.startPos, cursor);
                if (textFromAt.startsWith('@') && !textFromAt.includes(' ') && textFromAt.length <= 50) {
                    currentMentionState.query = textFromAt.substring(1);
                    displayPersonaSuggestions(cm, currentMentionState.query);
                } else {
                    hidePersonaSuggestions();
                }
            } else {
                hidePersonaSuggestions();
            }
            return;
        }
    }

    if (type === 'keyup' && !currentMentionState.active && !fileTagState.active) {
        const cursor = cm.getCursor();
        if (cursor.ch > 0) {
            const charBefore = cm.getRange({ line: cursor.line, ch: cursor.ch - 1 }, cursor);
            if (charBefore === '@') {
                currentMentionState.active = true;
                currentMentionState.editor = cm;
                currentMentionState.query = '';
                currentMentionState.startPos = { line: cursor.line, ch: cursor.ch - 1 };
                displayPersonaSuggestions(cm, '');
            } else if (charBefore === '#') {
                fileTagState.active = true;
                fileTagState.editor = cm;
                fileTagState.query = '';
                fileTagState.startPos = { line: cursor.line, ch: cursor.ch - 1 };
                displayFileTagSuggestions(cm, '');
            }
        }
    }
}

function updateSuggestionsHighlight(shouldScroll = true) {
    if (!personaSuggestionsDiv || !currentMentionState.active) return;
    Array.from(personaSuggestionsDiv.children).forEach((child, index) => {
        if (child.classList.contains('no-results')) return;
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

function initializeEditorTagging(editorInstance) {
    if (!editorInstance) return;
    createPersonaSuggestionsUI();
    createFileTagSuggestionsUI();
    const cm = editorInstance.codemirror;

    cm.on('keyup', (cmInstance, event) => {
        if (['Control', 'Alt', 'Shift', 'Meta', 'CapsLock', 'Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
            return;
        }
        handleEditorKeyEvent(cmInstance, event, 'keyup');
    });
    cm.on('keydown', (cmInstance, event) => {
        if ((currentMentionState.active || fileTagState.active) && (currentMentionState.editor === cmInstance || fileTagState.editor === cmInstance) && ['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
            handleEditorKeyEvent(cmInstance, event, 'keydown');
        }
    });
    cm.on('blur', (cmInstance) => {
        setTimeout(() => {
            if (personaSuggestionsDiv && !personaSuggestionsDiv.contains(document.activeElement)) {
                if (currentMentionState.editor === cmInstance) {
                    hidePersonaSuggestions();
                }
            }
            if (fileTagSuggestionsDiv && !fileTagSuggestionsDiv.contains(document.activeElement)) {
                if (fileTagState.editor === cmInstance) {
                    hideFileTagSuggestions();
                }
            }
        }, 200);
    });
}

function highlightPersonaTags(cm) {
    if (!cm) return;
    const regex = /@\[([^\]]+)\]\((\d+)\)/g;
    const content = cm.getValue();
    let match;
    while ((match = regex.exec(content)) !== null) {
        const startPos = cm.posFromIndex(match.index);
        const endPos = cm.posFromIndex(match.index + match[0].length);
        cm.markText(startPos, endPos, {
            className: 'cm-persona-tag',
            atomic: true,
        });
    }
}

function createFileTagSuggestionsUI() {
    if (!fileTagSuggestionsDiv) {
        fileTagSuggestionsDiv = document.createElement('div');
        fileTagSuggestionsDiv.id = 'fileTagSuggestions';
        fileTagSuggestionsDiv.style.position = 'absolute';
        fileTagSuggestionsDiv.style.display = 'none';
        document.body.appendChild(fileTagSuggestionsDiv);
    }
}

function hideFileTagSuggestions() {
    if (fileTagSuggestionsDiv) {
        fileTagSuggestionsDiv.style.display = 'none';
        fileTagSuggestionsDiv.innerHTML = '';
    }
    fileTagState.active = false;
    fileTagState.editor = null;
    fileTagState.query = '';
    fileTagState.startPos = null;
    fileTagState.selectedIndex = -1;
    fileTagState.currentResults = [];
}

async function displayFileTagSuggestions(cm, query) {
    if (!fileTagState.active) return;

    clearTimeout(fileTagDebounceTimer);
    fileTagDebounceTimer = setTimeout(async () => {
        try {
            const results = await apiRequest(`/api/files/search?q=${encodeURIComponent(query)}`);
            fileTagState.currentResults = results;
            fileTagState.selectedIndex = -1;

            fileTagSuggestionsDiv.innerHTML = '';
            if (!results.length) {
                const noResultsItem = document.createElement('div');
                noResultsItem.textContent = 'No matching files';
                noResultsItem.classList.add('suggestion-item', 'no-results');
                fileTagSuggestionsDiv.appendChild(noResultsItem);
            } else {
                results.forEach((file, index) => {
                    const item = document.createElement('div');
                    item.textContent = file.display;
                    item.classList.add('suggestion-item');
                    item.dataset.path = file.path;
                    item.addEventListener('click', () => insertFileTag(cm, file));
                    fileTagSuggestionsDiv.appendChild(item);
                });
            }

            const startCoords = cm.cursorCoords(fileTagState.startPos, 'local');
            const editorWrapper = cm.getWrapperElement();
            const editorRect = editorWrapper.getBoundingClientRect();
            const bodyRect = document.body.getBoundingClientRect();

            fileTagSuggestionsDiv.style.left = `${editorRect.left + startCoords.left - bodyRect.left}px`;
            fileTagSuggestionsDiv.style.top = `${editorRect.top + startCoords.bottom - bodyRect.top + 5}px`;
            fileTagSuggestionsDiv.style.display = 'block';
            updateFileTagSuggestionsHighlight();

        } catch (error) {
            console.error("Error fetching file suggestions:", error);
            hideFileTagSuggestions();
        }
    }, 250);
}

function insertFileTag(cm, file) {
    if (!fileTagState.startPos || !cm) {
        hideFileTagSuggestions();
        return;
    }
    const filename = file.path.split(/[\\/]/).pop();
    const textToInsert = `[#${filename}](${file.path})`;
    const currentCursor = cm.getCursor();
    cm.replaceRange(textToInsert, fileTagState.startPos, currentCursor);
    
    const endPos = { line: fileTagState.startPos.line, ch: fileTagState.startPos.ch + textToInsert.length };
    cm.markText(fileTagState.startPos, endPos, {
        className: 'cm-file-tag',
        atomic: true,
    });

    hideFileTagSuggestions();
    cm.focus();
}

function updateFileTagSuggestionsHighlight(shouldScroll = true) {
    if (!fileTagSuggestionsDiv || !fileTagState.active) return;
    Array.from(fileTagSuggestionsDiv.children).forEach((child, index) => {
        if (index === fileTagState.selectedIndex) {
            child.classList.add('selected');
            if (shouldScroll) child.scrollIntoView({ block: 'nearest' });
        } else {
            child.classList.remove('selected');
        }
    });
}

function highlightFileTags(cm) {
    if (!cm) return;
    const regex = /\[#([^\]]+)\]\(([^)]+)\)/g;
    const content = cm.getValue();
    let match;
    while ((match = regex.exec(content)) !== null) {
        const startPos = cm.posFromIndex(match.index);
        const endPos = cm.posFromIndex(match.index + match[0].length);
        cm.markText(startPos, endPos, {
            className: 'cm-file-tag',
            atomic: true,
        });
    }
}

export function createEditor(textAreaElement, editorType, initialValue = '') {
    if (!textAreaElement) return null;

    const config = createEditorConfig(editorType);
    config.element = textAreaElement;
    config.initialValue = initialValue;

    const editor = new EasyMDE(config);
    initializeEditorTagging(editor);
    initializeTokenBreakdownDisplay(editor, editorType);

    editor.codemirror.on("refresh", function(cm) {
        highlightPersonaTags(cm);
        highlightFileTags(cm);
    });
    
    highlightPersonaTags(editor.codemirror);
    highlightFileTags(editor.codemirror);

    return editor;
}

if (newTopicContentInput) {
    newTopicEditor = createEditor(newTopicContentInput, 'new-topic');
}

if (replyContentInput) {
    replyEditor = createEditor(replyContentInput, 'reply');
}

function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

async function updateTokenBreakdown(editorInstance, editorType) {
    if (!editorInstance) return;
    const container = document.getElementById(`${editorType}-token-breakdown-container`);
    if (!container) return;

    const current_post_text = editorInstance.value();
    let selected_persona_id = null;
    const personaSelectElement = document.getElementById('llm-persona-select');
    if (personaSelectElement && personaSelectElement.value && personaSelectElement.value !== "0" && personaSelectElement.value !== "") {
        if (personaSelectElement.offsetParent !== null) {
            selected_persona_id = parseInt(personaSelectElement.value, 10);
        }
    }

    const attachments_text = cachedAttachmentsContent[editorType] ? cachedAttachmentsContent[editorType].text : "";
    let parent_post_id = null;
    if (editorType === 'reply') {
        const parentPostIdElement = document.getElementById('reply-parent-post-id');
        if (parentPostIdElement && parentPostIdElement.value) {
            parent_post_id = parseInt(parentPostIdElement.value, 10);
            if (isNaN(parent_post_id)) parent_post_id = null;
        }
    }
    const client_request_id = `${editorType}-${Date.now()}`;

    try {
        const requestBody = {
            current_post_text: current_post_text,
            selected_persona_id: selected_persona_id,
            attachments_text: attachments_text,
            parent_post_id: parent_post_id,
            request_id: client_request_id
        };
        const response = await fetch('/api/prompts/estimate_tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error('Error fetching token breakdown:', errorData.error || response.statusText);
            document.getElementById(`${editorType}-token-total-estimated`).textContent = 'Error';
            document.getElementById(`${editorType}-token-model-context-window`).textContent = 'N/A';
            return;
        }

        const data = await response.json();
        document.getElementById(`${editorType}-token-post-content`).textContent = `~${data.post_content_tokens}`;
        document.getElementById(`${editorType}-token-persona-name`).textContent = data.persona_name || "Default";
        document.getElementById(`${editorType}-token-persona-prompt`).textContent = `~${data.persona_prompt_tokens}`;
        document.getElementById(`${editorType}-token-attachments`).textContent = `~${data.attachments_tokens}`;
        document.getElementById(`${editorType}-token-chat-history`).textContent = `~${data.chat_history_tokens}`;
        const systemPromptEl = document.getElementById(`${editorType}-token-system-prompt`);
        if (systemPromptEl) systemPromptEl.textContent = `~${data.system_prompt_tokens}`;
        const primaryHistEl = document.getElementById(`${editorType}-token-primary-history`);
        if (primaryHistEl) primaryHistEl.textContent = `~${data.primary_chat_history_tokens}`;
        const ambientHistEl = document.getElementById(`${editorType}-token-ambient-history`);
        if (ambientHistEl) ambientHistEl.textContent = `~${data.ambient_chat_history_tokens}`;
        const headersEl = document.getElementById(`${editorType}-token-headers`);
        if (headersEl) headersEl.textContent = `~${data.headers_tokens}`;
        const finalInstructionEl = document.getElementById(`${editorType}-token-final-instruction`);
        if (finalInstructionEl) finalInstructionEl.textContent = `~${data.final_instruction_tokens}`;
        document.getElementById(`${editorType}-token-total-estimated`).textContent = `~${data.total_estimated_tokens}`;
        document.getElementById(`${editorType}-token-model-context-window`).textContent = data.model_context_window || "N/A";
        document.getElementById(`${editorType}-token-model-name`).textContent = data.model_name || "default";

        const easyMDEContainer = editorInstance.element.parentElement;
        if (easyMDEContainer) {
            const statusBarTokenCount = easyMDEContainer.querySelector(`.${editorType}-statusbar-token-count`);
            if (statusBarTokenCount) {
                statusBarTokenCount.textContent = `~${data.total_estimated_tokens}`;
            }
        }

        const visualBar = document.getElementById(`${editorType}-token-visual-bar`);
        let percentage = 0;
        if (data.model_context_window && data.model_context_window > 0) {
            percentage = (data.total_estimated_tokens / data.model_context_window) * 100;
        }
        percentage = Math.max(0, Math.min(100, percentage));
        visualBar.style.width = percentage + '%';
        if (percentage >= 90) {
            visualBar.style.backgroundColor = '#D32F2F';
        } else if (percentage >= 70) {
            visualBar.style.backgroundColor = '#FBC02D';
        } else {
            visualBar.style.backgroundColor = '#4CAF50';
        }
    } catch (error) {
        console.error('Failed to send request for token breakdown:', error);
        document.getElementById(`${editorType}-token-total-estimated`).textContent = 'Error';
        document.getElementById(`${editorType}-token-model-context-window`).textContent = 'N/A';
    }
}

function initializeTokenBreakdownDisplay(editorInstance, editorType) {
    if (!editorInstance || !editorInstance.codemirror) return;
    const breakdownContainer = document.getElementById(`${editorType}-token-breakdown-container`);
    if (!breakdownContainer) return;
    const easyMDEContainer = editorInstance.element.parentElement;
    if (!easyMDEContainer) return;

    const setupEventListeners = (statusBar) => {
        const tokenControl = statusBar.querySelector(`.${editorType}-token-summary`);
        if (!tokenControl) return;

        tokenControl.addEventListener('click', (event) => {
            event.stopPropagation();
            const isExpanded = breakdownContainer.classList.toggle('expanded');
            const toggleButton = tokenControl.querySelector('.toggle-button');
            if (toggleButton) {
                toggleButton.textContent = isExpanded ? '[-]' : '[+]';
            }
        });

        const debouncedTokenBreakdownUpdate = debounce(() => {
            updateTokenBreakdown(editorInstance, editorType);
        }, 750);

        editorInstance.codemirror.on('change', debouncedTokenBreakdownUpdate);
        const personaSelector = document.getElementById('llm-persona-select');
        if (personaSelector) {
            personaSelector.addEventListener('change', () => updateTokenBreakdown(editorInstance, editorType));
        }

        const attachmentInputId = editorType === 'new-topic' ? 'new-topic-attachment-input' : 'reply-attachment-input';
        const attachmentInput = document.getElementById(attachmentInputId);
        if (attachmentInput) {
            attachmentInput.addEventListener('change', async () => {
                const files = attachmentInput.files;
                let combinedText = "";
                let filesHash = "";
                if (files && files.length > 0) {
                    const textFilePromises = [];
                    const fileDetailsForHash = [];
                    const plainTextMimeTypes = ['text/plain', 'text/markdown', 'text/csv', 'application/json', 'application/xml', 'text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/x-javascript', 'text/x-python', 'application/python', 'application/x-python', 'text/x-java-source', 'text/x-csrc', 'text/x-c++src', 'application/rtf', 'text/richtext', 'text/yaml', 'application/yaml', 'text/x-yaml', 'application/x-yaml', 'text/toml', 'application/toml', 'application/ld+json', 'text/calendar', 'text/vcard', 'text/sgml', 'application/sgml', 'text/tab-separated-values', 'application/xhtml+xml', 'application/rss+xml', 'application/atom+xml', 'text/x-script.python'];
                    const plainTextExtensions = ['.txt', '.md', '.markdown', '.csv', '.json', '.xml', '.html', '.htm', '.css', '.js', '.py', '.pyw', '.java', '.c', '.cpp', '.h', '.hpp', '.rtf', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.log', '.text', '.tex', '.tsv', '.jsonld', '.ical', '.ics', '.vcf', '.vcard', '.sgml', '.sgm', '.xhtml', '.xht', '.rss', '.atom', '.sh', '.bash', '.ps1', '.bat', '.cmd'];
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
                updateTokenBreakdown(editorInstance, editorType);
            });
        }
        updateTokenBreakdown(editorInstance, editorType);
    };

    const observer = new MutationObserver((mutationsList, obs) => {
        for (const mutation of mutationsList) {
            if (mutation.type === 'childList') {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('editor-statusbar')) {
                        setupEventListeners(node);
                        obs.disconnect();
                        return;
                    }
                }
            }
        }
    });

    observer.observe(easyMDEContainer, { childList: true, subtree: false });
    const existingStatusBar = easyMDEContainer.querySelector('.editor-statusbar');
    if (existingStatusBar) {
        setupEventListeners(existingStatusBar);
        observer.disconnect();
    }
}