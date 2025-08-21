// This file will handle the initialization and configuration of the EasyMDE editor instances.

import { newTopicContentInput, replyContentInput } from './dom.js';
import { apiRequest } from './api.js';

let cachedAttachmentsContent = { 'new-topic': { text: '', filesHash: null }, 'reply': { text: '', filesHash: null } };

// --- Tagging Globals ---
let activePersonasCache = [];
let personasCacheTimestamp = 0;
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
let instructionCache = [];
let instructionCacheTimestamp = 0;

let suggestionsDiv = null;
let currentTagState = {
    editor: null,
    query: '',
    startPos: null,
    active: false,
    selectedIndex: -1,
    currentResults: [],
    type: null // Can be 'persona', 'file', 'instruction', 'set'
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

function createSuggestionsUI() {
    if (!suggestionsDiv) {
        suggestionsDiv = document.createElement('div');
        suggestionsDiv.id = 'tagSuggestions';
        suggestionsDiv.style.position = 'absolute';
        suggestionsDiv.style.display = 'none';
        document.body.appendChild(suggestionsDiv);
    }
}

function hideSuggestions() {
    if (suggestionsDiv) {
        suggestionsDiv.style.display = 'none';
        suggestionsDiv.innerHTML = '';
    }
    currentTagState.active = false;
    currentTagState.editor = null;
    currentTagState.query = '';
    currentTagState.startPos = null;
    currentTagState.selectedIndex = -1;
    currentTagState.currentResults = [];
    currentTagState.type = null;
}

async function displaySuggestions(cm) {
    if (!currentTagState.active) return;

    let results = [];
    const query = currentTagState.query;

    if (currentTagState.type === 'persona') {
        const now = Date.now();
        if (!activePersonasCache.length || (now - personasCacheTimestamp > CACHE_DURATION)) {
            activePersonasCache = await apiRequest('/api/personas/list_active') || [];
            personasCacheTimestamp = now;
        }
        results = activePersonasCache.filter(p => p.name.toLowerCase().includes(query.toLowerCase()));
    } else if (currentTagState.type === 'instruction' || currentTagState.type === 'set') {
        const now = Date.now();
        if (!instructionCache.length || (now - instructionCacheTimestamp > CACHE_DURATION)) {
            instructionCache = await apiRequest('/api/custom-instructions/autocomplete') || [];
            instructionCacheTimestamp = now;
        }
        const typeFilter = currentTagState.type;
        results = instructionCache.filter(i => i.type === typeFilter && i.name.toLowerCase().includes(query.toLowerCase()));
    } else if (currentTagState.type === 'file') {
        clearTimeout(fileTagDebounceTimer);
        fileTagDebounceTimer = setTimeout(async () => {
            try {
                const fileResults = await apiRequest(`/api/files/search?q=${encodeURIComponent(query)}`);
                renderSuggestions(cm, fileResults);
            } catch (error) {
                console.error("Error fetching file suggestions:", error);
                hideSuggestions();
            }
        }, 250);
        return; // Return early, renderSuggestions will be called by the timeout
    }

    renderSuggestions(cm, results);
}

function renderSuggestions(cm, results) {
    currentTagState.currentResults = results;
    currentTagState.selectedIndex = -1;

    suggestionsDiv.innerHTML = '';
    if (!results.length) {
        const noResultsItem = document.createElement('div');
        noResultsItem.textContent = `No matching ${currentTagState.type}s`;
        noResultsItem.classList.add('suggestion-item', 'no-results');
        suggestionsDiv.appendChild(noResultsItem);
    } else {
        results.forEach((item, index) => {
            const div = document.createElement('div');
            div.textContent = item.name || item.display;
            div.classList.add('suggestion-item');
            div.addEventListener('click', () => insertTag(cm, item));
            suggestionsDiv.appendChild(div);
        });
    }

    const startCoords = cm.cursorCoords(currentTagState.startPos, 'local');
    const editorWrapper = cm.getWrapperElement();
    const editorRect = editorWrapper.getBoundingClientRect();
    const bodyRect = document.body.getBoundingClientRect();

    suggestionsDiv.style.left = `${editorRect.left + startCoords.left - bodyRect.left}px`;
    suggestionsDiv.style.top = `${editorRect.top + startCoords.bottom - bodyRect.top + 5}px`;
    suggestionsDiv.style.display = 'block';
    updateSuggestionsHighlight(false);
}

function insertTag(cm, item) {
    if (!currentTagState.startPos || !cm) {
        hideSuggestions();
        return;
    }
    let textToInsert = '';
    switch (currentTagState.type) {
        case 'persona':
            textToInsert = `@[${item.name}](${item.persona_id})`;
            break;
        case 'file':
            const filename = item.path.split(/[\\/]/).pop();
            textToInsert = `[#${filename}](${item.path})`;
            break;
        case 'instruction':
            textToInsert = `![${item.name}](${item.id})`;
            break;
        case 'set':
            textToInsert = `!set:[${item.name}](${item.id})`;
            break;
    }

    const currentCursor = cm.getCursor();
    cm.replaceRange(textToInsert, currentTagState.startPos, currentCursor);
    hideSuggestions();
    cm.focus();
}

function handleEditorKeyEvent(cm, event, keypressType) {
    if (!currentTagState.active) {
        if (keypressType === 'keyup') {
            const cursor = cm.getCursor();
            const line = cm.getLine(cursor.line);
            const textBeforeCursor = line.substring(0, cursor.ch);

            const personaMatch = textBeforeCursor.match(/@([\w-]*)$/);
            const fileMatch = textBeforeCursor.match(/#([\w.-]*)$/);
            const instructionMatch = textBeforeCursor.match(/!([\w-]*)$/);
            const setMatch = textBeforeCursor.match(/!set:([\w-]*)$/);

            let match, type, query, triggerText;

            if (setMatch) {
                [triggerText, query] = setMatch;
                type = 'set';
            } else if (instructionMatch) {
                [triggerText, query] = instructionMatch;
                type = 'instruction';
            } else if (personaMatch) {
                [triggerText, query] = personaMatch;
                type = 'persona';
            } else if (fileMatch) {
                [triggerText, query] = fileMatch;
                type = 'file';
            }

            if (type) {
                currentTagState.active = true;
                currentTagState.editor = cm;
                currentTagState.query = query;
                currentTagState.type = type;
                currentTagState.startPos = { line: cursor.line, ch: cursor.ch - query.length - triggerText.lastIndexOf(query) };
                displaySuggestions(cm);
            }
        }
        return;
    }

    // --- Key handling when suggestions are active ---
    if (keypressType === 'keydown') {
        if (['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
            event.preventDefault();
            if (event.key === 'Escape') {
                hideSuggestions();
            } else if (event.key === 'Enter' || event.key === 'Tab') {
                if (currentTagState.selectedIndex !== -1 && currentTagState.currentResults[currentTagState.selectedIndex]) {
                    insertTag(cm, currentTagState.currentResults[currentTagState.selectedIndex]);
                } else {
                    hideSuggestions();
                }
            } else if (event.key === 'ArrowDown') {
                if (currentTagState.currentResults.length > 0) {
                    currentTagState.selectedIndex = (currentTagState.selectedIndex + 1) % currentTagState.currentResults.length;
                    updateSuggestionsHighlight();
                }
            } else if (event.key === 'ArrowUp') {
                if (currentTagState.currentResults.length > 0) {
                    currentTagState.selectedIndex = (currentTagState.selectedIndex - 1 + currentTagState.currentResults.length) % currentTagState.currentResults.length;
                    updateSuggestionsHighlight();
                }
            }
        }
    } else if (keypressType === 'keyup') {
        const cursor = cm.getCursor();
        if (cursor.line !== currentTagState.startPos.line || cursor.ch < currentTagState.startPos.ch) {
            hideSuggestions();
            return;
        }

        const textFromTrigger = cm.getRange(currentTagState.startPos, cursor);
        let query = '';

        if (currentTagState.type === 'set' && textFromTrigger.startsWith('!set:')) {
            query = textFromTrigger.substring(5);
        } else if (['persona', 'file', 'instruction'].includes(currentTagState.type)) {
            query = textFromTrigger.substring(1);
        }

        if (textFromTrigger.includes(' ')) {
            hideSuggestions();
            return;
        }

        currentTagState.query = query;
        displaySuggestions(cm);
    }
}

function updateSuggestionsHighlight(shouldScroll = true) {
    if (!suggestionsDiv || !currentTagState.active) return;
    Array.from(suggestionsDiv.children).forEach((child, index) => {
        if (child.classList.contains('no-results')) return;
        if (index === currentTagState.selectedIndex) {
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
    createSuggestionsUI();
    const cm = editorInstance.codemirror;

    cm.on('keyup', (cmInstance, event) => {
        if (['Control', 'Alt', 'Shift', 'Meta', 'CapsLock', 'Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
            return;
        }
        handleEditorKeyEvent(cmInstance, event, 'keyup');
    });
    cm.on('keydown', (cmInstance, event) => {
        if (currentTagState.active && currentTagState.editor === cmInstance && ['Escape', 'Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
            handleEditorKeyEvent(cmInstance, event, 'keydown');
        }
    });
    cm.on('blur', (cmInstance) => {
        setTimeout(() => {
            if (suggestionsDiv && !suggestionsDiv.contains(document.activeElement)) {
                if (currentTagState.editor === cmInstance) {
                    hideSuggestions();
                }
            }
        }, 200);
    });
}

function highlightTags(cm) {
    if (!cm) return;
    const tagRegexes = {
        'cm-persona-tag': /@\[([^\]]+)\]\((\d+)\)/g,
        'cm-file-tag': /..\[#([^]]+)\]\(([^)]+)\)/g,
        'cm-instruction-tag': /!\[([^\]]+)\]\((\d+)\)/g,
        'cm-set-tag': /!set:\[([^\]]+)\]\((\d+)\)/g
    };

    const content = cm.getValue();
    for (const className in tagRegexes) {
        const regex = tagRegexes[className];
        let match;
        while ((match = regex.exec(content)) !== null) {
            const startPos = cm.posFromIndex(match.index);
            const endPos = cm.posFromIndex(match.index + match[0].length);
            cm.markText(startPos, endPos, {
                className: className,
                atomic: true,
            });
        }
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
        highlightTags(cm);
    });
    
    highlightTags(editor.codemirror);

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
