// This file will manage the processing queue view.

import { apiRequest } from './api.js';
import { queuePageContent, fullPromptModal, fullPromptContent, fullPromptClose, fullPromptMetadataPane, queuePaginationContainer } from './dom.js';

// --- Helper function to escape HTML for displaying prompt content safely ---
// Moved here to be accessible by other functions if needed, or can be kept local
function escapeHTML(str) {
    if (typeof str !== 'string') return ''; // Ensure str is a string
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}


// --- New Token Breakdown Rendering Function for Modal ---
function renderTokenBreakdownForModal(breakdownString, containerElement) {
    if (!containerElement) return;
    containerElement.innerHTML = ''; // Clear previous content

    if (!breakdownString) {
        containerElement.innerHTML = '<p>No token breakdown available.</p>';
        return;
    }

    try {
        const breakdown = JSON.parse(breakdownString);
        const table = document.createElement('div'); // Using divs for table structure
        table.style.display = 'table';
        table.style.width = '100%'; // Use full width of the pane

        const keyMapping = {
            total_prompt_tokens: "Total Final Prompt Tokens",
            persona_prompt_tokens: "Persona Instructions",
            user_post_tokens: "User Post",
            attachments_token_count: "Attachments",
            primary_chat_history_tokens: "Primary Chat History",
            ambient_chat_history_tokens: "Ambient Chat History",
            headers_tokens: "History Headers",
            chat_history_tokens: "Chat History (Legacy)" // Keep for older records
        };

        // Order of display, total first
        const displayOrder = [
            'total_prompt_tokens',
            'persona_prompt_tokens',
            'user_post_tokens',
            'attachments_token_count',
            'primary_chat_history_tokens',
            'ambient_chat_history_tokens',
            'headers_tokens',
            'chat_history_tokens'
        ];

        displayOrder.forEach(key => {
            if (breakdown[key] !== undefined && breakdown[key] !== null) {
                const isTotal = key === 'total_prompt_tokens';
                // Only display if value is not zero, OR if it's the total tokens
                if (isTotal || parseFloat(breakdown[key]) !== 0) {
                    const row = document.createElement('div');
                    row.style.display = 'table-row';

                    const labelCell = document.createElement('div');
                    labelCell.style.display = 'table-cell';
                    labelCell.style.textAlign = 'left';
                    labelCell.style.padding = '2px 5px';
                    labelCell.textContent = keyMapping[key] || key;

                    const valueCell = document.createElement('div');
                    valueCell.style.display = 'table-cell';
                    valueCell.style.textAlign = 'right';
                    valueCell.style.padding = '2px 5px';
                    valueCell.textContent = breakdown[key];

                    if (!isTotal) {
                        labelCell.style.fontSize = '0.9em';
                        valueCell.style.fontSize = '0.9em';
                    } else {
                        labelCell.style.fontWeight = 'bold';
                        valueCell.style.fontWeight = 'bold';
                    }
                    row.appendChild(labelCell);
                    row.appendChild(valueCell);
                    table.appendChild(row);
                }
            }
        });

        if (table.children.length > 0) {
            containerElement.appendChild(table);
        } else {
            containerElement.innerHTML = '<p>Token breakdown contains no data or only zero values.</p>';
        }

    } catch (e) {
        console.error('Error parsing or rendering token breakdown for modal:', e);
        containerElement.innerHTML = '<p class="error-message">Error displaying token breakdown.</p>';
    }
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
        let personaDisplay = 'default';
        if (item.llm_persona) {
            if (item.persona_name) {
                personaDisplay = `${item.persona_name} (ID: ${item.llm_persona})`;
            } else {
                personaDisplay = `ID: ${item.llm_persona} (Name not found)`;
            }
        }
        
        let snippet;
        let summaryContent;

        if (status === 'pending_dependency' && item.parent_request_id) {
            li.classList.add('chained-request');
            snippet = `This is a chained reply, waiting for response to request <span class="parent-request-link">#${item.parent_request_id}</span>.`;
            summaryContent = `
                <strong>Request ID: ${item.request_id}</strong><br>
                Status: <span class="queue-status status-${status}">Pending Dependency</span><br>
                Model: ${model}, Persona: ${personaDisplay}<br>
                Queued: <span class="queue-meta">${queuedAt}</span>
            `;
        } else {
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
        }


        li.innerHTML = `
            <div class="queue-item-summary">
                ${summaryContent}
            </div>
            <div class="queue-item-snippet">
                ${snippet}
            </div>
        `;

        // Add click listener to show full prompt and pass token breakdown string
        li.addEventListener('click', () => showFullPromptModal(item.request_id, item.prompt_token_breakdown));

        list.appendChild(li);
    });

    queuePageContent.appendChild(list);
}

// --- Full Prompt Modal Functions ---
async function showFullPromptModal(requestId, tokenBreakdownString) { // Added tokenBreakdownString parameter
    if (!fullPromptModal || !fullPromptContent || !fullPromptMetadataPane) return;

    fullPromptContent.innerHTML = '<p>Loading prompt...</p>';
    fullPromptMetadataPane.innerHTML = ''; // Clear metadata pane initially
    fullPromptModal.style.display = 'block'; // Show the modal

    try {
        const response = await apiRequest(`/api/queue/${requestId}/prompt`);
        if (response && response.prompt) {
            fullPromptContent.innerHTML = `<pre>${escapeHTML(response.prompt)}</pre>`;
        } else {
            fullPromptContent.innerHTML = '<p class="error-message">Failed to load prompt.</p>';
        }
    } catch (error) {
        console.error(`Error loading prompt for request ${requestId}:`, error);
        fullPromptContent.innerHTML = `<p class="error-message">Failed to load prompt: ${error.message}</p>`;
    }

    // Render the token breakdown in the metadata pane
    renderTokenBreakdownForModal(tokenBreakdownString, fullPromptMetadataPane);
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