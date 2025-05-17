// This file will manage the processing queue view.

import { apiRequest } from './api.js';
import { queuePageContent } from './dom.js';

// --- Queue Rendering Functions ---
export function renderQueueList(queueItems) {
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

        // Example: Display basic info. Adjust based on actual data from backend.
        const postIdText = item.post_id ? `Post ID: ${item.post_id}` : 'N/A';
        const queuedAt = item.queued_at ? new Date(item.queued_at).toLocaleString() : 'Unknown time';
        const taskType = item.task_type || 'LLM Request'; // Example field

        li.innerHTML = `
            <strong>${taskType}</strong> for ${postIdText}<br>
            <span class="queue-meta">Queued: ${queuedAt}</span>
        `;
        // Add more details as needed based on backend response structure
        list.appendChild(li);
    });

    queuePageContent.appendChild(list);
}

// --- Queue Loading Function ---
export async function loadQueueData() {
    if (!queuePageContent) return; // Ensure element exists

    queuePageContent.innerHTML = '<p>Loading queue...</p>'; // Show loading state

    try {
        const queueData = await apiRequest('/api/queue'); // Fetch from the new endpoint
        renderQueueList(queueData);
    } catch (error) {
        console.error("Error loading queue data:", error);
        queuePageContent.innerHTML = `<p class="error-message">Failed to load queue: ${error.message}</p>`;
    }
}