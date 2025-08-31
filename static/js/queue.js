// This file will manage the processing queue view.

import { apiRequest } from './api.js';
import { queuePageContent, fullPromptModal, fullPromptContent, fullPromptClose, fullPromptMetadataPane, queuePaginationContainer } from './dom.js';
import { showTopic } from './forum.js';
import { openPersonaModal } from './personas.js';
import { showToast } from './ui.js';

// --- Helper function to escape HTML for displaying prompt content safely ---
function escapeHTML(str) {
    if (typeof str !== 'string') return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function renderMetadata(item) {
    if (!fullPromptMetadataPane) return;

    fullPromptMetadataPane.innerHTML = ''; // Clear previous content

    // 1. Context Link
    const contextLinkContainer = document.createElement('div');
    contextLinkContainer.className = 'context-link-container';
    let linkHTML = '<p>No context link available.</p>';

    if (item.status === 'complete_target_deleted') {
        linkHTML = '<p><em>Original content was deleted.</em></p>';
    } else if (item.request_type === 'generate_persona' && item.status === 'complete' && item.result_object_id) {
        linkHTML = `<a href="#" data-persona-id="${item.result_object_id}" class="view-context-link">View Generated Persona</a>`;
    } else if (item.topic_id) {
        linkHTML = `<a href="#" data-topic-id="${item.topic_id}" class="view-context-link">View Topic</a>`;
    } else if (item.status !== 'complete') {
        linkHTML = '<p><em>Link will be available upon completion.</em></p>';
    }
    contextLinkContainer.innerHTML = linkHTML;
    fullPromptMetadataPane.appendChild(contextLinkContainer);

    // 2. Token Breakdown
    const tokenContainer = document.createElement('div');
    tokenContainer.className = 'token-breakdown-container';
    renderTokenBreakdownForModal(item.prompt_token_breakdown, tokenContainer);
    fullPromptMetadataPane.appendChild(tokenContainer);
    
    // 3. Actions Menu
    const actionsContainer = document.createElement('div');
    actionsContainer.className = 'queue-actions-container';
    actionsContainer.innerHTML = `
        <div class="kebab-menu">
            <button class="kebab-button">...</button>
            <div class="kebab-dropdown">
                <a href="#" class="kebab-item delete-queue-item" data-request-id="${item.request_id}">Delete</a>
            </div>
        </div>
    `;
    fullPromptMetadataPane.appendChild(actionsContainer);

    // Add event listeners
    const link = fullPromptMetadataPane.querySelector('.view-context-link');
    if (link) {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const topicId = e.target.dataset.topicId;
            const personaId = e.target.dataset.personaId;
            if (topicId) {
                showTopic(topicId);
                fullPromptModal.style.display = 'none';
            } else if (personaId) {
                openPersonaModal(personaId);
            }
        });
    }

    const kebabButton = actionsContainer.querySelector('.kebab-button');
    const kebabDropdown = actionsContainer.querySelector('.kebab-dropdown');
    kebabButton.addEventListener('click', () => {
        kebabDropdown.classList.toggle('visible');
    });

    const deleteButton = actionsContainer.querySelector('.delete-queue-item');
    deleteButton.addEventListener('click', async (e) => {
        e.preventDefault();
        const requestId = e.target.dataset.requestId;
        if (confirm(`Are you sure you want to delete queue item #${requestId}? This cannot be undone.`)) {
            try {
                await apiRequest(`/api/queue/${requestId}`, { method: 'DELETE' });
                showToast('Queue item deleted.');
                fullPromptModal.style.display = 'none';
                loadQueueData(); // Refresh the queue view
            } catch (error) {
                console.error('Failed to delete queue item:', error);
                showToast(`Error: ${error.message}`, 'error');
            }
        }
    });
}

// --- New Token Breakdown Rendering Function for Modal ---
function renderTokenBreakdownForModal(breakdownString, containerElement) {
    if (!containerElement) return;
    containerElement.innerHTML = ''; // Clear previous content

    if (!breakdownString) {
        const p = document.createElement('p');
        p.textContent = 'No token breakdown available.';
        containerElement.appendChild(p);
        return;
    }

    try {
        const breakdown = JSON.parse(breakdownString);
        const details = document.createElement('details');
        details.className = 'token-breakdown-details';

        const summary = document.createElement('summary');
        summary.textContent = `Total Tokens: ${breakdown.total_prompt_tokens || 'N/A'}`;
        details.appendChild(summary);

        const table = document.createElement('div');
        table.className = 'token-breakdown-table';
        table.style.display = 'table';
        table.style.width = '100%';

        const keyMapping = {
            persona_prompt_tokens: "Persona Instructions",
            user_post_tokens: "User Post",
            attachments_token_count: "Attachments",
            primary_chat_history_tokens: "Primary Chat History",
            ambient_chat_history_tokens: "Ambient Chat History",
            headers_tokens: "History Headers",
            chat_history_tokens: "Chat History (Legacy)"
        };

        const displayOrder = [
            'persona_prompt_tokens', 'user_post_tokens', 'attachments_token_count',
            'primary_chat_history_tokens', 'ambient_chat_history_tokens', 'headers_tokens', 'chat_history_tokens'
        ];

        displayOrder.forEach(key => {
            if (breakdown[key] !== undefined && breakdown[key] !== null && parseFloat(breakdown[key]) !== 0) {
                const row = document.createElement('div');
                row.style.display = 'table-row';
                const labelCell = document.createElement('div');
                labelCell.style.display = 'table-cell';
                labelCell.textContent = keyMapping[key] || key;
                const valueCell = document.createElement('div');
                valueCell.style.display = 'table-cell';
                valueCell.style.textAlign = 'right';
                valueCell.textContent = breakdown[key];
                row.appendChild(labelCell);
                row.appendChild(valueCell);
                table.appendChild(row);
            }
        });

        if (table.children.length > 0) {
            details.appendChild(table);
        }
        containerElement.appendChild(details);

    } catch (e) {
        console.error('Error parsing or rendering token breakdown for modal:', e);
        containerElement.innerHTML = '<p class="error-message">Error displaying token breakdown.</p>';
    }
}


// --- Persona Generation Modal Function ---
function showPersonaGenerationDetails(item) {
    if (!fullPromptModal || !fullPromptContent || !fullPromptMetadataPane) return;

    let params;
    try {
        params = JSON.parse(item.request_params);
    } catch (e) {
        console.error("Failed to parse request_params for persona generation item:", item);
        fullPromptContent.innerHTML = `<p class="error-message">Could not parse request details.</p>`;
        fullPromptMetadataPane.innerHTML = '';
        fullPromptModal.style.display = 'block';
        return;
    }

    const stage1Prompt = params.stage1_full_prompt || "Stage 1 prompt not available.";
    const stage2Template = params.stage2_prompt_template || "Stage 2 template not available.";

    const modalHTML = `
        <div class="collapsible-prompt-container">
            <details class="prompt-section" open>
                <summary>Stage 1: Expansion Prompt</summary>
                <pre>${escapeHTML(stage1Prompt)}</pre>
            </details>
            <details class="prompt-section">
                <summary>Stage 2: Refinement Template</summary>
                <pre>${escapeHTML(stage2Template)}</pre>
            </details>
        </div>
    `;
    fullPromptContent.innerHTML = modalHTML;
    
    renderMetadata(item);
    
    // Accordion logic
    const detailsElements = fullPromptContent.querySelectorAll('.prompt-section');
    detailsElements.forEach(details => {
        details.addEventListener('toggle', (event) => {
            if (event.target.open) {
                detailsElements.forEach(otherDetails => {
                    if (otherDetails !== event.target) {
                        otherDetails.open = false;
                    }
                });
            }
        });
    });

    fullPromptModal.style.display = 'block';
}


// --- Queue Rendering Functions ---
export function renderQueueList(queueItems) {
    if (!queuePageContent) return; // Ensure element exists
    queuePageContent.innerHTML = ''; // Clear loading/previous content

    if (!Array.isArray(queueItems) || queueItems.length === 0) {
        queuePageContent.innerHTML = '<p>The processing queue is currently empty.</p>';
        return;
    }

    const list = document.createElement('ul');
    list.className = 'queue-list'; // Add class for potential styling

    queueItems.forEach(item => {
        const li = document.createElement('li');
        li.className = 'queue-item'; // Add class for potential styling
        li.dataset.requestId = item.request_id; // Store request ID for click handling

        const queuedAt = item.requested_at ? new Date(item.requested_at).toLocaleString() : 'Unknown time';
        const status = item.status || 'unknown';
        const model = item.llm_model || 'default';
        
        let snippet;
        let summaryContent;

        if (item.request_type === 'generate_persona') {
            li.classList.add('persona-generation-item');
            let nameHint = 'New Persona';
            try {
                const params = JSON.parse(item.request_params);
                nameHint = params?.input_details?.name_hint || params?.target_persona_name_override || nameHint;
            } catch (e) { /* Use default */ }

            summaryContent = `
                <strong>Request ID: ${item.request_id}</strong><br>
                Status: <span class="queue-status status-${status}">${status}</span><br>
                Type: Persona Generation<br>
                Model: ${model}<br>
                Queued: <span class="queue-meta">${queuedAt}</span>
            `;
            snippet = `Generating persona with name hint: "${escapeHTML(nameHint)}"`;
            li.addEventListener('click', () => showPersonaGenerationDetails(item));

        } else if (status === 'pending_dependency' && item.parent_request_id) {
            li.classList.add('chained-request');
            let personaDisplay = 'default';
             if (item.llm_persona) {
                if (item.persona_name) {
                    personaDisplay = `${item.persona_name} (ID: ${item.llm_persona})`;
                } else {
                    personaDisplay = `ID: ${item.llm_persona} (Name not found)`;
                }
            }
            snippet = `This is a chained reply, waiting for response to request <span class="parent-request-link">#${item.parent_request_id}</span>.`;
            summaryContent = `
                <strong>Request ID: ${item.request_id}</strong><br>
                Status: <span class="queue-status status-${status}">Pending Dependency</span><br>
                Model: ${model}, Persona: ${personaDisplay}<br>
                Queued: <span class="queue-meta">${queuedAt}</span>
            `;
            li.addEventListener('click', () => showFullPromptModal(item));

        } else { // Standard post response
            let personaDisplay = 'default';
            if (item.llm_persona) {
                if (item.persona_name) {
                    personaDisplay = `${item.persona_name} (ID: ${item.llm_persona})`;
                } else {
                    personaDisplay = `ID: ${item.llm_persona} (Name not found)`;
                }
            }
            snippet = item.post_snippet ? escapeHTML(item.post_snippet.substring(0, 150) + '...') : 'No snippet available';
            snippet = `Original Post Snippet: "${snippet}"`;

            // Get total tokens for summary display
            let totalTokensDisplay = "N/A";
            if (item.prompt_token_breakdown) {
                try {
                    const breakdown = JSON.parse(item.prompt_token_breakdown);
                    if (breakdown.total_prompt_tokens !== undefined) {
                        totalTokensDisplay = breakdown.total_prompt_tokens;
                    }
                } catch (e) {
                    console.warn(`Could not parse token breakdown for item ${item.request_id} in summary.`);
                }
            }
            summaryContent = `
                <strong>Request ID: ${item.request_id}</strong><br>
                Status: <span class="queue-status status-${status}">${status}</span><br>
                Model: ${model}, Persona: ${personaDisplay}<br>
                Queued: <span class="queue-meta">${queuedAt}</span><br>
                Total Tokens: <span class="queue-meta">${totalTokensDisplay}</span>
            `;
            li.addEventListener('click', () => showFullPromptModal(item));
        }


        li.innerHTML = `
            <div class="queue-item-summary">
                ${summaryContent}
            </div>
            <div class="queue-item-snippet">
                ${snippet}
            </div>
        `;

        list.appendChild(li);
    });

    queuePageContent.appendChild(list);
}

// --- Full Prompt Modal Functions ---
async function showFullPromptModal(item) { 
    if (!fullPromptModal || !fullPromptContent || !fullPromptMetadataPane) return;

    // Delegate to the new function if it's a persona generation request
    if (item.request_type === 'generate_persona') {
        showPersonaGenerationDetails(item);
        return;
    }

    fullPromptContent.innerHTML = '<p>Loading prompt...</p>';
    fullPromptModal.style.display = 'block'; // Show the modal

    try {
        const response = await apiRequest(`/api/queue/${item.request_id}/prompt`);
        if (response && response.prompt) {
            fullPromptContent.innerHTML = `<pre>${escapeHTML(response.prompt)}</pre>`;
        } else {
            fullPromptContent.innerHTML = '<p class="error-message">Failed to load prompt.</p>';
        }
    } catch (error) {
        console.error(`Error loading prompt for request ${item.request_id}:`, error);
        fullPromptContent.innerHTML = `<p class="error-message">Failed to load prompt: ${error.message}</p>`;
    }

    // Render the token breakdown in the metadata pane
    renderMetadata(item);
}



// --- Queue Loading Function ---
export async function loadQueueData(page = 1) {
    if (!queuePageContent) return;

    if (page === 1) {
        queuePageContent.innerHTML = '<p>Loading queue...</p>';
    }

    try {
        const data = await apiRequest(`/api/queue?page=${page}&per_page=10`);
        renderQueueList(data.items);

        if (queuePaginationContainer) {
            renderPagination(data.total_pages, data.current_page);
        }

    } catch (error) {
        console.error("Error loading queue data:", error);
        queuePageContent.innerHTML = `<p class="error-message">Failed to load queue: ${error.message}</p>`;
    }
}

// --- Pagination Rendering ---
function renderPagination(totalPages, currentPage) {
    if (!queuePaginationContainer) return;
    queuePaginationContainer.innerHTML = '';

    if (totalPages <= 1) return;

    const createButton = (text, page, isDisabled = false, isCurrent = false, isGap = false) => {
        const btn = document.createElement(isCurrent || isGap ? 'span' : 'button');
        btn.textContent = text;
        if (isGap) {
            btn.className = 'page-gap';
        } else {
            btn.className = 'page-number';
            if (isCurrent) btn.classList.add('active');
            btn.disabled = isDisabled;
            btn.dataset.page = page;
            btn.addEventListener('click', () => loadQueueData(page));
        }
        return btn;
    };

    // Previous Button
    const prevButton = createButton('< Prev', currentPage - 1, currentPage === 1);
    queuePaginationContainer.appendChild(prevButton);

    // Page Numbers
    const pagesToShow = [];
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) {
            pagesToShow.push(i);
        }
    } else {
        pagesToShow.push(1);
        if (currentPage > 3) pagesToShow.push('...');
        
        let start = Math.max(2, currentPage - 1);
        let end = Math.min(totalPages - 1, currentPage + 1);

        for (let i = start; i <= end; i++) {
            pagesToShow.push(i);
        }

        if (currentPage < totalPages - 2) pagesToShow.push('...');
        pagesToShow.push(totalPages);
    }

    const uniquePages = [...new Set(pagesToShow)]; // Remove duplicates

    uniquePages.forEach(p => {
        if (p === '...') {
            queuePaginationContainer.appendChild(createButton('...', 0, false, false, true));
        } else {
            queuePaginationContainer.appendChild(createButton(p, p, false, p === currentPage));
        }
    });


    // Next Button
    const nextButton = createButton('Next >', currentPage + 1, currentPage === totalPages);
    queuePaginationContainer.appendChild(nextButton);
}

// --- Modal Close Listener ---
// Assuming fullPromptClose is the close button element
if (fullPromptClose) {
    fullPromptClose.addEventListener('click', () => {
        if (fullPromptModal) {
            fullPromptModal.style.display = 'none'; // Hide the modal
        }
    });
}

// Close modal if user clicks outside of it
window.addEventListener('click', (event) => {
    if (fullPromptModal && event.target === fullPromptModal) {
        fullPromptModal.style.display = 'none';
    }
});

// TODO: Implement periodic queue refresh in main.js or here
// Example: setInterval(loadQueueData, 15000); // Refresh every 15 seconds