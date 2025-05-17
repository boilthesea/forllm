// This file will handle the initialization and configuration of the EasyMDE editor instances.

import { newTopicContentInput, replyContentInput } from './dom.js';

// --- EasyMDE Configuration & Initialization ---
const easyMDEConfig = {
    element: null,
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

export let newTopicEditor = null; // EasyMDE instance for new topics
export let replyEditor = null; // EasyMDE instance for replies

// Initialize editors if the elements exist
if (newTopicContentInput) {
    newTopicEditor = new EasyMDE({
        ...easyMDEConfig,
        element: newTopicContentInput
    });
}

if (replyContentInput) {
     replyEditor = new EasyMDE({
        ...easyMDEConfig,
        element: replyContentInput
    });
}