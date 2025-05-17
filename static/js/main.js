// This file will be the main entry point for the frontend JavaScript.

import {
    loadSubforums,
    addSubforum,
    addTopic,
    submitReply,
    hideReplyForm,
    loadTopics, // Needed for backToTopicsBtn
    currentSubforumId // Needed for backToTopicsBtn
} from './forum.js';

import {
    loadSchedules,
    loadNextSchedule,
    loadCurrentStatus,
    addScheduleRow,
    saveSchedules
} from './schedule.js';

import {
    loadSettings,
    renderSettingsPage,
    saveSettings // Although saveSettings is called internally by renderSettingsPage, keep import for clarity
} from './settings.js';

import { loadQueueData } from './queue.js';

import { showSection, lastVisibleSectionId } from './ui.js';

import {
    addSubforumBtn,
    addTopicBtn,
    submitReplyBtn,
    cancelReplyBtn,
    backToSubforumsBtn,
    backToTopicsBtn,
    editScheduleBtn,
    scheduleCloseBtn,
    addScheduleRowBtn,
    saveSchedulesBtn,
    settingsBtn,
    exitSettingsBtn,
    queueBtn,
    exitQueueBtn,
    subforumList, // Needed for backToTopicsBtn
    scheduleModal // Needed for schedule modal listeners
} from './dom.js';

// --- Initial Load & Periodic Updates ---
function initialLoad() {
    loadSubforums().then(() => {
        // After subforums load, decide initial view
        // For now, default to showing topic list section (empty until subforum clicked)
        showSection('topic-list-section');
    });
    loadSettings(); // Loads settings (which includes dark mode and model list trigger)
    loadCurrentStatus();
    loadNextSchedule();
    setInterval(loadCurrentStatus, 30000); // Update status every 30 seconds
    setInterval(loadNextSchedule, 30000); // Update next schedule every 30 seconds
}

// --- Global Event Listeners ---
document.addEventListener('DOMContentLoaded', () => {
    // Forum Action Buttons
    if (addSubforumBtn) addSubforumBtn.addEventListener('click', addSubforum);
    if (addTopicBtn) addTopicBtn.addEventListener('click', addTopic);
    if (submitReplyBtn) submitReplyBtn.addEventListener('click', submitReply);
    if (cancelReplyBtn) cancelReplyBtn.addEventListener('click', hideReplyForm);

    // Navigation Buttons
    if (backToSubforumsBtn) {
        backToSubforumsBtn.addEventListener('click', (e) => {
            e.preventDefault();
            // currentSubforumId = null; // State is managed within forum.js now
            // currentTopicId = null; // State is managed within forum.js now
            showSection('subforum-list-only'); // Hide right pane sections
        });
    }

    if (backToTopicsBtn) {
        backToTopicsBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (currentSubforumId) { // Access state from forum.js
                const subforumLink = subforumList.querySelector(`a[data-subforum-id="${currentSubforumId}"]`);
                const subforumName = subforumLink ? subforumLink.dataset.subforumName : 'Selected Subforum';
                loadTopics(currentSubforumId, subforumName); // This calls showSection('topic-list')
            } else {
                showSection('subforum-list-only'); // Go back to just the sidebar view
            }
        });
    }

    // Schedule Modal Listeners
    if (editScheduleBtn) {
        editScheduleBtn.addEventListener('click', async () => {
            // scheduleError.textContent = ""; // Error handling moved to schedule.js
            // statusDot.classList.remove('status-error'); // Status updates moved to schedule.js
            // statusDot.classList.add('status-loading');
            // statusIndicatorContainer.title = 'Schedule status: Loading...';
            await loadSchedules(); // Load current schedules into modal before showing
            if (scheduleModal) scheduleModal.style.display = 'block';
        });
    }

    if (scheduleCloseBtn && scheduleModal) { // Ensure both exist
        scheduleCloseBtn.addEventListener('click', () => {
            scheduleModal.style.display = 'none';
        });
    }

    if (addScheduleRowBtn) addScheduleRowBtn.addEventListener('click', addScheduleRow);
    if (saveSchedulesBtn) saveSchedulesBtn.addEventListener('click', saveSchedules);

    // Settings Page Listeners
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            renderSettingsPage(); // Ensure content is created
            showSection('settings-page-section');
        });
    }

    if (exitSettingsBtn) {
        exitSettingsBtn.addEventListener('click', () => {
            showSection(lastVisibleSectionId); // Go back to the last main view
        });
    }

    // Queue Page Listeners
    if (queueBtn) {
        queueBtn.addEventListener('click', () => {
            showSection('queue-page-section');
            loadQueueData(); // Load data when section is shown
        });
    }

    if (exitQueueBtn) {
        exitQueueBtn.addEventListener('click', () => {
            showSection(lastVisibleSectionId); // Go back to the last main view
        });
    }

    // Initial Load
    initialLoad();
});

// window click listener for modals is now in ui.js
// postList click listener for link interception is now in forum.js