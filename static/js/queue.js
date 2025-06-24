// This file will manage the processing queue view.

import { apiRequest } from './api.js';
import { queuePageContent, fullPromptModal, fullPromptContent, fullPromptClose } from './dom.js'; // Assuming fullPromptModal, fullPromptContent, fullPromptClose are added to dom.js

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

        // Display more details based on backend response structure
        const postIdText = item.post_id_to_respond_to ? `Post ID: ${item.post_id_to_respond_to}` : 'N/A';
        const queuedAt = item.requested_at ? new Date(item.requested_at).toLocaleString() : 'Unknown time';
        const status = item.status || 'unknown';
        const model = item.llm_model || 'default';
        let personaDisplay = 'default'; // Default text
        if (item.llm_persona) { // Check if persona ID exists
            if (item.persona_name) {
                personaDisplay = `${item.persona_name} (ID: ${item.llm_persona})`;
            } else {
                // If persona_name is null/undefined but ID exists (e.g., persona deleted, or ID was invalid)
                personaDisplay = `ID: ${item.llm_persona} (Name not found)`;
            }
        }
        const snippet = item.post_snippet ? item.post_snippet.substring(0, 150) + '...' : 'No snippet available'; // Display a snippet

        li.innerHTML = `
            <div class="queue-item-summary">
                <strong>Request ID: ${item.request_id}</strong><br>
                Status: <span class="queue-status status-${status}">${status}</span><br>
                Model: ${model}, Persona: ${personaDisplay}<br> 
                Queued: <span class="queue-meta">${queuedAt}</span>
            </div>
            <div class="queue-item-snippet">
                Original Post Snippet: "${snippet}"
            </div>
        `;

        // --- NEW: Add Prompt Token Breakdown ---
        if (item.prompt_token_breakdown) {
            try {
                const breakdown = JSON.parse(item.prompt_token_breakdown);
                const breakdownDiv = document.createElement('div');
                breakdownDiv.className = 'queue-item-token-breakdown';
                // Initially hidden, will be shown if content is added.
                // Or, style directly with 'block' if always shown when present.
                breakdownDiv.style.marginTop = '5px';
                breakdownDiv.style.padding = '8px'; // Increased padding
                breakdownDiv.style.backgroundColor = '#2c3e50'; // Darker background, fits dark theme
                breakdownDiv.style.borderRadius = '4px'; // Slightly more rounded
                breakdownDiv.style.color = '#ecf0f1'; // Light text color for all content within

                let breakdownHTML = '<p style="margin-bottom: 5px; font-weight: bold; color: #1abc9c;">Prompt Token Breakdown:</p><ul style="list-style-type: none; padding-left: 0;">'; // Added color to title
                const keyMapping = {
                    total_prompt_tokens: "Total Final Prompt Tokens",
                    persona_prompt_tokens: "Persona Instructions",
                    user_post_tokens: "User Post",
                    attachments_token_count: "Attachments",
                    // Old key, for backward compatibility if some records have it
                    chat_history_tokens: "Chat History (Legacy)",
                    // New keys
                    primary_chat_history_tokens: "Primary Chat History",
                    ambient_chat_history_tokens: "Ambient Chat History",
                    headers_tokens: "History Headers"
                };

                // Display total first
                if (breakdown.total_prompt_tokens !== undefined) {
                     breakdownHTML += `<li>${keyMapping.total_prompt_tokens}: ${breakdown.total_prompt_tokens}</li>`;
                }

                // Display other components
                const componentKeys = [
                    'persona_prompt_tokens',
                    'user_post_tokens',
                    'attachments_token_count',
                    'primary_chat_history_tokens',
                    'ambient_chat_history_tokens',
                    'headers_tokens',
                    'chat_history_tokens' // Check legacy last
                ];

                componentKeys.forEach(key => {
                    if (breakdown[key] !== undefined && breakdown[key] !== null) {
                        // Only display if value is not zero, except for total_prompt_tokens
                        if (key === 'total_prompt_tokens' || parseFloat(breakdown[key]) !== 0) {
                             breakdownHTML += `<li>${keyMapping[key] || key}: ${breakdown[key]}</li>`;
                        }
                    }
                });

                breakdownHTML += '</ul>';

                // Only append if there's meaningful content beyond the title
                if (breakdownHTML.includes('<li>')) {
                    breakdownDiv.innerHTML = breakdownHTML;
                    li.appendChild(breakdownDiv);
                }
            } catch (e) {
                console.error(`Error parsing token breakdown for request ${item.request_id}:`, e);
                const errorDiv = document.createElement('div');
                errorDiv.className = 'queue-item-token-breakdown-error';
                errorDiv.textContent = 'Error displaying token breakdown.';
                errorDiv.style.color = 'red';
                errorDiv.style.fontSize = '0.9em';
                li.appendChild(errorDiv);
            }
        }
        // --- END NEW ---

        // Add click listener to show full prompt
        li.addEventListener('click', () => showFullPromptModal(item.request_id));

        list.appendChild(li);
    });

    queuePageContent.appendChild(list);
}

// --- Full Prompt Modal Functions ---
async function showFullPromptModal(requestId) {
    if (!fullPromptModal || !fullPromptContent) return;

    fullPromptContent.innerHTML = '<p>Loading prompt...</p>';
    fullPromptModal.style.display = 'block'; // Show the modal

    try {
        const response = await apiRequest(`/api/queue/${requestId}/prompt`);
        if (response && response.prompt) {
            // Display the prompt, maybe format it nicely
            fullPromptContent.innerHTML = `<pre>${escapeHTML(response.prompt)}</pre>`;
        } else {
            fullPromptContent.innerHTML = '<p class="error-message">Failed to load prompt.</p>';
        }
    } catch (error) {
        console.error(`Error loading prompt for request ${requestId}:`, error);
        fullPromptContent.innerHTML = `<p class="error-message">Failed to load prompt: ${error.message}</p>`;
    }
}

// Helper function to escape HTML for displaying prompt content safely
function escapeHTML(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}


// --- Queue Loading Function ---
export async function loadQueueData() {
    if (!queuePageContent) return; // Ensure element exists

    // Only show loading state if it's the initial load or explicitly requested
    if (queuePageContent.innerHTML === '' || queuePageContent.innerHTML.includes('Failed to load queue')) {
         queuePageContent.innerHTML = '<p>Loading queue...</p>'; // Show loading state
    }


    try {
        const queueData = await apiRequest('/api/queue'); // Fetch from the new endpoint
        renderQueueList(queueData);
    } catch (error) {
        console.error("Error loading queue data:", error);
        queuePageContent.innerHTML = `<p class="error-message">Failed to load queue: ${error.message}</p>`;
    }
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