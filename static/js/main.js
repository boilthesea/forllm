// This file will be the main entry point for the frontend JavaScript.

import {
    loadSubforums,
    addSubforum,
    addTopic,
    submitReply,
    hideReplyForm,
    loadTopics, // Needed for backToTopicsBtn
    currentSubforumId, // Needed for backToTopicsBtn
    loadSubforumPersonas,
    handleFileSelection // Import for attachment staging
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

import { showSection, lastVisibleSectionId, toggleMobileMenu, isMobile } from './ui.js';

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
    activityPageSection, // Added
    exitActivityBtn,     // Added
    subforumList,
    scheduleModal,
    mobileScheduleBtn,
    mobileQueueBtn,
    mobileSettingsBtn
} from './dom.js';

// Import loadActivityData for the exit button, though ui.js handles calling it on showSection
import { loadActivityData } from './activity.js';

// --- Initial Load & Periodic Updates ---
function initialLoad() {
    loadSubforums().then(() => {
        // After subforums load, show the default section (now activity page via showSection(null))
        showSection(null);
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

    // Page Navigation Buttons
    if (backToSubforumsBtn) {
        backToSubforumsBtn.addEventListener('click', (e) => {
            e.preventDefault();
            // currentSubforumId = null; // State is managed within forum.js now
            // currentTopicId = null; // State is managed within forum.js now
            showSection('activity-page-section'); // Go back to the activity page
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


    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', toggleMobileMenu);
    }

    // Schedule Modal Listeners
    const openScheduleModal = async (e) => {
        await loadSchedules();
        if (scheduleModal) scheduleModal.style.display = 'block';
        // We don't show a section here, so we don't set active nav.
        // The modal is an overlay.
    };
    if (editScheduleBtn) editScheduleBtn.addEventListener('click', openScheduleModal);
    if (mobileScheduleBtn) mobileScheduleBtn.addEventListener('click', openScheduleModal);

    if (scheduleCloseBtn && scheduleModal) { // Ensure both exist
        scheduleCloseBtn.addEventListener('click', () => {
            scheduleModal.style.display = 'none';
        });
    }

    if (addScheduleRowBtn) addScheduleRowBtn.addEventListener('click', addScheduleRow);
    if (saveSchedulesBtn) saveSchedulesBtn.addEventListener('click', saveSchedules);

    // Settings Page Listeners
    const openSettingsPage = (e) => {
        renderSettingsPage();
        showSection('settings-page-section', e.target);
    };
    if (settingsBtn) settingsBtn.addEventListener('click', openSettingsPage);
    if (mobileSettingsBtn) mobileSettingsBtn.addEventListener('click', openSettingsPage);

    if (exitSettingsBtn) {
        exitSettingsBtn.addEventListener('click', () => {
            showSection(lastVisibleSectionId); // Go back to the last main view
        });
    }

    // Queue Page Listeners
    const openQueuePage = (e) => {
        showSection('queue-page-section', e.target);
        loadQueueData();
    };
    if (queueBtn) queueBtn.addEventListener('click', openQueuePage);
    if (mobileQueueBtn) mobileQueueBtn.addEventListener('click', openQueuePage);

    if (exitQueueBtn) {
        exitQueueBtn.addEventListener('click', () => {
            showSection(lastVisibleSectionId); // Go back to the last main view
        });
    }

    // Initial Load
    initialLoad();

    // Activity Page Listener
    if (exitActivityBtn) {
        exitActivityBtn.addEventListener('click', () => {
            // Refresh the activity data when exiting (or clicking the 'exit' which acts as refresh)
            if (typeof loadActivityData === 'function') {
                loadActivityData();
            }
            // Optionally, ensure the section is shown if it wasn't already
            // showSection('activity-page-section'); // ui.js showSection will call loadActivityData
        });
    }

    // Attachment File Input Listeners
    const newTopicAttachmentInput = document.getElementById('new-topic-attachment-input');
    if (newTopicAttachmentInput) {
        newTopicAttachmentInput.addEventListener('change', handleFileSelection);
    } else {
        // This might be expected if the new topic form isn't always visible or part of the initial DOM.
        // console.warn("Element with ID 'new-topic-attachment-input' not found during initial setup.");
    }

    const replyAttachmentInput = document.getElementById('reply-attachment-input');
    if (replyAttachmentInput) {
        replyAttachmentInput.addEventListener('change', handleFileSelection);
    } else {
        // This might be expected if the reply form isn't always visible or part of the initial DOM.
        // console.warn("Element with ID 'reply-attachment-input' not found during initial setup.");
    }
});

// window click listener for modals is now in ui.js
// postList click listener for link interception is now in forum.js

// Example: when a topic is loaded, call loadSubforumPersonas(subforumId)
window.loadTopic = async function(topicId, subforumId) {
  // ...existing code to load topic...
  await loadSubforumPersonas(subforumId);
  // ...existing code...
};