// This file will handle forum-specific logic.

import { apiRequest } from './api.js';
import {
    subforumList,
    newSubforumNameInput,
    topicListSection,
    currentSubforumName,
    topicList,
    newTopicTitleInput,
    newTopicContentInput,
    topicViewSection,
    currentTopicTitle,
    postList,
    replyFormContainer,
    replyToPostIdSpan,
    replyContentInput,
    settingsPageContent // Needed for link security check in postList event listener
} from './dom.js';
import { showSection, showLinkWarningPopup } from './ui.js';
import { newTopicEditor, replyEditor } from './editor.js'; // Import editor instances

// --- State Variables ---
let currentSubforumId = null;
let currentTopicId = null;
let currentPosts = []; // Store posts for the current topic
let currentPersonaId = null;

let stagedAttachments = []; // For managing files selected in UI before actual upload
let nextStagedAttachmentId = 0; // Counter for unique IDs for staged attachments

// --- Rendering Functions ---

export function renderSubforumList(subforums) {
    subforumList.innerHTML = '';
    if (!Array.isArray(subforums)) {
        console.error("Invalid subforums data:", subforums);
        return;
    }
    subforums.forEach(subforum => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = subforum.name;
        a.dataset.subforumId = subforum.subforum_id;
        a.dataset.subforumName = subforum.name;
        a.addEventListener('click', (e) => {
            e.preventDefault();
            loadTopics(subforum.subforum_id, subforum.name);
        });
        li.appendChild(a);

        // Add notification badge for subforum
        if (subforum.has_unseen_content) {
            const badge = document.createElement('span');
            badge.className = 'notification-badge';
            // Optionally, add a title or ARIA label for accessibility
            badge.title = 'Unseen content'; 
            a.appendChild(badge); // Append to the link itself to keep it inline
        }

        subforumList.appendChild(li);
    });
}

export function renderTopicList(topics) {
    topicList.innerHTML = '';
     if (!Array.isArray(topics)) {
        console.error("Invalid topics data:", topics);
        return;
    }
    topics.forEach(topic => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = topic.title;
        a.dataset.topicId = topic.topic_id;
        a.dataset.topicTitle = topic.title;
        a.addEventListener('click', (e) => {
            e.preventDefault();
            loadPosts(topic.topic_id, topic.title);
        });

        const meta = document.createElement('div');
        meta.className = 'topic-meta';
        meta.textContent = `Started by ${topic.username} | Posts: ${topic.post_count} | Last post: ${new Date(topic.last_post_at).toLocaleString()}`;
        li.appendChild(a);
        li.appendChild(meta);

        // Add notification badge for topic
        if (topic.has_unseen_content) {
            const badge = document.createElement('span');
            badge.className = 'notification-badge';
            badge.title = 'Unseen content';
            // Prepend to the link or append to the <li>. Appending to <a> might be better for alignment.
            a.appendChild(badge); // Append to the link
        }
        
        topicList.appendChild(li);
    });
}

export function renderPosts(posts) {
    postList.innerHTML = '';
    currentPosts = posts;

    if (!Array.isArray(posts)) {
        console.error("Invalid posts data:", posts);
        return;
    }

    const postsById = posts.reduce((map, post) => {
        map[post.post_id] = { ...post, children: [] };
        return map;
    }, {});

    const rootPosts = [];
    posts.forEach(post => {
        if (post.parent_post_id && postsById[post.parent_post_id]) {
            postsById[post.parent_post_id].children.push(postsById[post.post_id]);
        } else if (!post.parent_post_id) {
            rootPosts.push(postsById[post.post_id]);
        }
    });

    rootPosts.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    rootPosts.forEach(post => renderPostNode(post, postList, 0));
}

function renderPostNode(post, parentElement, depth) {
    const postDiv = document.createElement('div');
    postDiv.className = 'post';
    postDiv.dataset.postId = post.post_id;
    postDiv.style.marginLeft = `${depth * 2}rem`;

    if (post.is_llm_response) {
        postDiv.classList.add('llm-response');
    }

    const metaDiv = document.createElement('div');
    metaDiv.className = 'post-meta';
    metaDiv.textContent = `Posted by ${post.username} on ${new Date(post.created_at).toLocaleString()}`;
    if (post.is_llm_response) {
        const llmMeta = document.createElement('span');
        llmMeta.className = 'llm-meta';
        llmMeta.textContent = ` (LLM: ${post.llm_model_id} / Persona: ${post.llm_persona_id})`;
        metaDiv.appendChild(llmMeta);
    }

    const contentDiv = document.createElement('div');
    contentDiv.className = 'post-content';
    contentDiv.innerHTML = post.content;

    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'post-actions';

    const replyButton = document.createElement('button');
    replyButton.textContent = 'Reply';
    replyButton.addEventListener('click', () => showReplyForm(post.post_id));
    actionsDiv.appendChild(replyButton);

    if (!post.is_llm_response) {
        const llmButton = document.createElement('button');
        llmButton.textContent = 'Request LLM Response';
        llmButton.addEventListener('click', () => requestLlm(post.post_id));
        actionsDiv.appendChild(llmButton);
    }

    postDiv.appendChild(metaDiv);
    postDiv.appendChild(contentDiv);
    postDiv.appendChild(actionsDiv);

    // --- Render Attachments for the post ---
    if (post.attachments && Array.isArray(post.attachments) && post.attachments.length > 0) {
        const attachmentsContainerDiv = document.createElement('div');
        attachmentsContainerDiv.className = 'post-attachments-list mt-2';
        attachmentsContainerDiv.id = `post-attachments-${post.post_id}`; // Unique ID for this post's attachments

        post.attachments.forEach(attachmentData => {
            renderAttachmentItem(attachmentData, attachmentsContainerDiv, post.post_id);
        });
        postDiv.appendChild(attachmentsContainerDiv);
    }
    // --- End Render Attachments ---

    parentElement.appendChild(postDiv);

    if (post.children && post.children.length > 0) {
        const repliesContainer = document.createElement('div');
        repliesContainer.className = 'post-replies';
        postDiv.appendChild(repliesContainer);
        post.children
            .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
            .forEach(child => renderPostNode(child, repliesContainer, 0));
    }
}


// --- Loading Functions ---
export async function loadSubforums() {
    try {
        const subforums = await apiRequest('/api/subforums');
        renderSubforumList(subforums);
        showSection('subforum-nav'); // This might need adjustment in main.js
    } catch (error) {
        // Error logged by apiRequest
    }
}

export async function loadTopics(subforumId, subforumName) {
    currentSubforumId = subforumId;
    currentTopicId = null;
    try {
        const topics = await apiRequest(`/api/subforums/${subforumId}/topics`);
        currentSubforumName.textContent = subforumName;
        renderTopicList(topics);
        showSection('topic-list-section');
    } catch (error) {
        // Error logged by apiRequest
    }
}

export async function loadPosts(topicId, topicTitle) {
    currentTopicId = topicId;
    try {
        const posts = await apiRequest(`/api/topics/${topicId}/posts`);
        currentTopicTitle.textContent = topicTitle;
        renderPosts(posts);
        showSection('topic-view-section');
        hideReplyForm();
    } catch (error) {
        // Error logged by apiRequest
    }
}

export async function loadSubforumPersonas(subforumId) {
    currentSubforumId = subforumId;
    const personas = await apiRequest(`/api/subforums/${subforumId}/personas`);
    llmPersonaSelect.innerHTML = '';
    personas.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.persona_id;
        opt.textContent = p.name + (p.is_default_for_subforum ? ' (default)' : '');
        llmPersonaSelect.appendChild(opt);
        if (p.is_default_for_subforum) currentPersonaId = p.persona_id;
    });
    if (personas.length > 0) {
        subforumPersonasBar.style.display = '';
        llmPersonaSelect.value = currentPersonaId;
        llmPersonaCurrentLabel.textContent = 'Current: ' + personas.find(p => p.persona_id == currentPersonaId)?.name;
    } else {
        subforumPersonasBar.style.display = 'none';
    }
}

// --- Action Functions ---
export async function addSubforum() {
    const name = newSubforumNameInput.value.trim();
    if (!name) {
        alert('Please enter a subforum name.');
        return;
    }
    try {
        const newSubforum = await apiRequest('/api/subforums', 'POST', { name });
        if (newSubforum) {
             const li = document.createElement('li');
             const a = document.createElement('a');
             a.href = '#';
             a.textContent = newSubforum.name;
             a.dataset.subforumId = newSubforum.subforum_id;
             a.dataset.subforumName = newSubforum.name;
             a.addEventListener('click', (e) => {
                 e.preventDefault();
                 loadTopics(newSubforum.subforum_id, newSubforum.name);
             });
             li.appendChild(a);
             subforumList.appendChild(li);
             newSubforumNameInput.value = '';
        }
    } catch (error) {
        // Error handled by apiRequest
    }
}

export async function addTopic() {
    const title = newTopicTitleInput.value.trim();
    const content = newTopicEditor ? newTopicEditor.value().trim() : newTopicContentInput.value.trim();
    if (!title || !content) {
        alert('Please enter both a title and content for the new topic.');
        return;
    }
    if (!currentSubforumId) {
        alert('Cannot add topic: No subforum selected.');
        return;
    }

    // The event listener on 'new-topic-attachment-input' calls handleFileSelection,
    // which populates stagedAttachments.
    // renderStagedAttachments is called by handleFileSelection to show the staged files.
    // Staging area should be cleared when the form is *initially prepared*,
    // which is not directly in addTopic but when the UI for creating a new topic is shown.
    // For now, we assume stagedAttachments holds the correct files for THIS topic submission.

    try {
        const newTopicResponse = await apiRequest(`/api/subforums/${currentSubforumId}/topics`, 'POST', { title, content });
         if (newTopicResponse && newTopicResponse.topic_id && newTopicResponse.initial_post_id) {
            // Successfully created topic and initial post
            const initial_post_id = newTopicResponse.initial_post_id;
            console.log('[DEBUG addTopic] Topic created. initial_post_id:', initial_post_id, 'Staged attachments count:', stagedAttachments.length);

            // Files are now handled by handleFileSelection and stagedAttachments.
            console.log('[DEBUG addTopic] Preparing to call uploadStagedAttachments. postId:', initial_post_id, 'Attachments:', stagedAttachments);
            if (stagedAttachments.length > 0) {
                await uploadStagedAttachments(initial_post_id, stagedAttachments, 'new-topic-pending-attachments-list');
            }
            
            // Clear staged attachments and UI *after* successful post creation and uploads
            stagedAttachments = [];
            nextStagedAttachmentId = 0;
            renderStagedAttachments('new-topic-pending-attachments-list'); // Clears the UI

            // Clear the file input (its value is cleared in handleFileSelection, this is a fallback or UI cleanup)
            const fileInput = document.getElementById('new-topic-attachment-input');
            if (fileInput) fileInput.value = '';


            // Refresh the topic list and potentially navigate to the new topic
            // The existing code for adding to topic list is fine.
            // Consider if we should auto-load the new topic: loadPosts(newTopicResponse.topic_id, newTopicResponse.title);
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = '#';
            a.textContent = newTopicResponse.title;
            a.dataset.topicId = newTopicResponse.topic_id;
            a.dataset.topicTitle = newTopicResponse.title;
            a.addEventListener('click', (e) => {
                e.preventDefault();
                loadPosts(newTopicResponse.topic_id, newTopicResponse.title);
            });
             const meta = document.createElement('div');
             meta.className = 'topic-meta';
             meta.textContent = `Started by You | Posts: 1 | Last post: Just now`;
             li.appendChild(a);
             li.appendChild(meta);
             topicList.appendChild(li);

            newTopicTitleInput.value = '';
            if (newTopicEditor) {
                newTopicEditor.value('');
            } else {
                newTopicContentInput.value = '';
            }
        }
    } catch (error) {
        // Error handled by apiRequest
    }
}

export function showReplyForm(postId) {
    replyToPostIdSpan.textContent = postId;
    if (replyEditor) {
        replyEditor.value('');
    } else {
        replyContentInput.value = '';
    }

    // Clear and prepare staging area for reply attachments
    stagedAttachments = [];
    nextStagedAttachmentId = 0;
    renderStagedAttachments('reply-pending-attachments-list');

    replyFormContainer.style.display = 'block';
    if (replyEditor) {
        replyEditor.codemirror.focus();
    } else {
        replyContentInput.focus();
    }
}

export function hideReplyForm() {
    replyFormContainer.style.display = 'none';
    replyToPostIdSpan.textContent = '';
    if (replyEditor) {
        replyEditor.value('');
    } else {
        replyContentInput.value = '';
    }
}

export async function submitReply() {
    const content = replyEditor ? replyEditor.value().trim() : replyContentInput.value.trim();
    const parentPostId = parseInt(replyToPostIdSpan.textContent, 10);

    if (!content) {
        alert('Please enter reply content.');
        return;
    }
    if (!currentTopicId || !parentPostId) {
        alert('Cannot reply: Topic or parent post context is missing.');
        return;
    }

    try {
        const newPostResponse = await apiRequest(`/api/topics/${currentTopicId}/posts`, 'POST', { content, parent_post_id: parentPostId });
        if (newPostResponse && newPostResponse.post_id) {
            const new_reply_post_id = newPostResponse.post_id;
            console.log('[DEBUG submitReply] Reply created. new_reply_post_id:', new_reply_post_id, 'Staged attachments count:', stagedAttachments.length);
            
            // Files are now handled by handleFileSelection and stagedAttachments.
            console.log('[DEBUG submitReply] Preparing to call uploadStagedAttachments. postId:', new_reply_post_id, 'Attachments:', stagedAttachments);
            if (stagedAttachments.length > 0) {
                await uploadStagedAttachments(new_reply_post_id, stagedAttachments, 'reply-pending-attachments-list');
            }
            // Clear staged attachments and update UI after successful post creation and uploads
            stagedAttachments = [];
            nextStagedAttachmentId = 0;
            renderStagedAttachments('reply-pending-attachments-list'); // Clears the UI

            // Clear the file input (its value is cleared in handleFileSelection, this is a fallback or UI cleanup)
            const fileInput = document.getElementById('reply-attachment-input');
            if (fileInput) fileInput.value = '';

            hideReplyForm();
            loadPosts(currentTopicId, currentTopicTitle.textContent); // This will re-render the posts, including new attachments.
        }
    } catch (error) {
        // Error handled by apiRequest
    }
}

export async function requestLlm(postId) {
    if (!confirm(`Request an LLM response to post ${postId}?`)) {
        return;
    }
    try {
        let payload = {};
        if (typeof llmPersonaSelect !== 'undefined' && llmPersonaSelect && llmPersonaSelect.value) {
            payload.persona_id = llmPersonaSelect.value;
        }
        await apiRequest(`/api/posts/${postId}/request_llm`, 'POST', payload);
        alert(`LLM response request queued for post ${postId}. It will be processed during scheduled hours.`);
    } catch (error) {
        alert('Failed to queue LLM response: ' + (error.message || error));
    }
}

// Link Interception - Moved from main event listeners
postList.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (link && link.classList.contains('llm-link')) {
        // Access currentSettings from settings.js
        if (currentSettings.llmLinkSecurity === 'true') {
            event.preventDefault();
            const url = link.href;
            const text = link.textContent;
            showLinkWarningPopup(url, text);
        }
    }
});

// --- Attachment Handling Functions ---

/**
 * Renders a single attachment item in the specified container.
 * Sets up event listeners for editing user prompt and deleting the attachment.
 * @param {object} attachmentData - Data for the attachment (attachment_id, filename, user_prompt, filepath).
 * @param {HTMLElement} containerElement - The DOM element to append the attachment item to.
 * @param {number} postId - The ID of the post this attachment belongs to (used for context if needed).
 * @returns {HTMLElement|null} The created attachment item element, or null if failed.
 */
function renderAttachmentItem(attachmentData, containerElement, postId) {
    if (!attachmentData || !containerElement) {
        console.error("renderAttachmentItem: Missing attachmentData or containerElement", attachmentData, containerElement);
        return null;
    }

    const itemDiv = document.createElement('div');
    itemDiv.className = 'attachment-item mb-2';
    itemDiv.dataset.attachmentId = attachmentData.attachment_id;

    const fileNameSpan = document.createElement('span');
    fileNameSpan.className = 'attachment-filename';
    fileNameSpan.textContent = attachmentData.filename;
    itemDiv.appendChild(fileNameSpan);

    const promptInput = document.createElement('input');
    promptInput.type = 'text';
    promptInput.className = 'attachment-user-prompt form-input';
    promptInput.value = attachmentData.user_prompt || '';
    promptInput.placeholder = 'Custom prompt for LLM (optional)';
    promptInput.addEventListener('blur', async () => {
        const newPrompt = promptInput.value.trim();
        if (newPrompt !== (attachmentData.user_prompt || '')) {
            try {
                await apiRequest(`/api/attachments/${attachmentData.attachment_id}`, 'PUT', { user_prompt: newPrompt });
                attachmentData.user_prompt = newPrompt; // Update local data representation
            } catch (error) {
                alert(`Failed to update attachment prompt: ${error.message}`);
                promptInput.value = attachmentData.user_prompt || ''; // Revert on error
            }
        }
    });
    itemDiv.appendChild(promptInput);

    const deleteButton = document.createElement('button');
    deleteButton.className = 'delete-attachment-btn btn btn-danger btn-small';
    deleteButton.textContent = 'Delete';
    deleteButton.addEventListener('click', async () => {
        if (confirm(`Are you sure you want to delete attachment "${attachmentData.filename}"?`)) {
            try {
                await apiRequest(`/api/attachments/${attachmentData.attachment_id}`, 'DELETE');
                itemDiv.remove();
            } catch (error) {
                alert(`Failed to delete attachment: ${error.message}`);
            }
        }
    });
    itemDiv.appendChild(deleteButton);
    containerElement.appendChild(itemDiv);
    return itemDiv;
}

/**
 * Uploads a single file with its order and potentially updates its user prompt.
 * @param {number} postId - The ID of the post to attach the file to.
 * @param {File} file - The file object to upload.
 * @param {number} orderInPost - The order of this attachment in the post.
 * @param {HTMLElement} [tempStatusElement=null] - Optional. A DOM element to show temporary upload status for this specific file.
 * @returns {Promise<object|null>} The attachment data from the server or null on failure.
 */
async function uploadSingleFile(postId, file, orderInPost, tempStatusElement = null) {
    console.log('[DEBUG uploadSingleFile] Entered function. postId:', postId, 'File name:', file.name, 'Order:', orderInPost);
    // console.log('[DEBUG] uploadSingleFile - File details: name:', file.name, 'size:', file.size, 'type:', file.type, 'lastModified:', file.lastModified, 'File instance of File:', file instanceof File);

    if (tempStatusElement) {
        tempStatusElement.textContent = `Uploading ${file.name}...`;
    }

    const formData = new FormData();
    // console.log('[DEBUG] uploadSingleFile - Initialized FormData object:', formData);
    formData.append('file', file);
    formData.append('order_in_post', orderInPost); // Add order_in_post
    // console.log('[DEBUG] uploadSingleFile - FormData after appending file and order. Calling formData.has("file"):', formData.has('file'));
    // for (let [key, value] of formData.entries()) { console.log('[DEBUG] uploadSingleFile - FormData entry: key=', key, 'value=', value); }

    try {
        // The backend route /api/posts/<post_id>/attachments needs to handle 'order_in_post' from FormData
        const newAttachmentData = await apiRequest(`/api/posts/${postId}/attachments`, 'POST', formData, true); 
        if (newAttachmentData && newAttachmentData.attachment_id) {
            if (tempStatusElement) {
                tempStatusElement.textContent = `${file.name} - Uploaded.`;
            }
            return newAttachmentData; // Return the full data including the server-generated ID
        } else {
            throw new Error('Upload of file completed but no valid attachment data returned.');
        }
    } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
        if (tempStatusElement) {
            tempStatusElement.textContent = `Failed to upload ${file.name}: ${error.message || 'Unknown error'}`;
            tempStatusElement.style.color = 'red';
        } else {
            alert(`Failed to upload ${file.name}: ${error.message || 'Unknown error'}`);
        }
        return null; // Indicate failure
    }
}


/**
 * Uploads all staged attachments for a given post.
 * @param {number} postId - The ID of the post to associate attachments with.
 * @param {Array<object>} attachmentsToUpload - Array of staged attachment objects {id, file, userPrompt}.
 * @param {string} tempDisplayListId - The ID of the DOM element where temporary status is shown (likely the staged list itself).
 */
async function uploadStagedAttachments(postId, attachmentsToUpload, tempDisplayListId) {
    console.log('[DEBUG uploadStagedAttachments] Entered function. postId:', postId, 'Attachments to upload:', attachmentsToUpload);
    const displayListElement = document.getElementById(tempDisplayListId);
    if (!displayListElement) {
        console.error(`uploadStagedAttachments: Display list element '${tempDisplayListId}' not found.`); // Kept console.error, removed [DEBUG]
        // Potentially alert the user or throw an error if this UI element is critical
    }
    // console.log(`[DEBUG] uploadStagedAttachments - Uploading ${attachmentsToUpload.length} files for post ${postId}`);

    for (let i = 0; i < attachmentsToUpload.length; i++) {
        const stagedAttachment = attachmentsToUpload[i];
        let tempStatusElement = null;

        // Try to find the specific staged item in the UI to update its status
        if (displayListElement) {
            tempStatusElement = displayListElement.querySelector(`[data-id="${stagedAttachment.id}"]`);
            if (tempStatusElement) {
                 // Maybe add a specific child element for status messages within the staged item
                const statusSpan = tempStatusElement.querySelector('.staged-upload-status') || document.createElement('span');
                statusSpan.className = 'staged-upload-status';
                statusSpan.textContent = ' Uploading...';
                tempStatusElement.appendChild(statusSpan); // Append if new
                tempStatusElement = statusSpan; // Update this element
            }
        }
        
        const newAttachmentData = await uploadSingleFile(postId, stagedAttachment.file, i, tempStatusElement);

        if (newAttachmentData && newAttachmentData.attachment_id) {
            if (stagedAttachment.userPrompt && stagedAttachment.userPrompt.trim() !== '') {
                try {
                    // console.log(`[DEBUG] Updating user_prompt for attachment ${newAttachmentData.attachment_id} to "${stagedAttachment.userPrompt}"`);
                    await apiRequest(`/api/attachments/${newAttachmentData.attachment_id}`, 'PUT', { user_prompt: stagedAttachment.userPrompt });
                    if (tempStatusElement) tempStatusElement.textContent = ` ${stagedAttachment.file.name} - Uploaded & prompt saved.`;
                } catch (e) {
                    console.error(`Failed to update user_prompt for ${stagedAttachment.file.name}:`, e); // Kept console.error
                    if (tempStatusElement) tempStatusElement.textContent = ` ${stagedAttachment.file.name} - Uploaded, but prompt update failed.`;
                    tempStatusElement.style.color = 'orange'; // Or some other indication of partial success
                }
            } else {
                 if (tempStatusElement) tempStatusElement.textContent = ` ${stagedAttachment.file.name} - Uploaded.`;
            }
            // The attachment will be rendered properly when loadPosts refreshes the view.
            // No need to call renderAttachmentItem here as the temporary list is just for feedback.
        } else {
            // uploadSingleFile already handles updating tempStatusElement on failure.
            console.error(`[DEBUG] Failed to upload staged file: ${stagedAttachment.file.name}`);
        }
    }
    // After all uploads, the calling function (addTopic/submitReply) will clear stagedAttachments
    // and re-render the (now empty) staging list.
    // The main post list will be refreshed by loadPosts, showing the newly uploaded attachments.
}


// Export state variables if needed by other modules (e.g., main.js for initial load)
export { currentSubforumId, currentTopicId, currentPosts };
// Export new attachment handlers
export { renderAttachmentItem }; // handleFileUploadsForPost is removed

/**
 * Handles file selection from an input element, adding files to a staging area.
 * @param {Event} event - The file input change event.
 */
export function handleFileSelection(event) {
    const files = event.target.files;
    if (!files) return;

    for (const file of files) {
        const newStagedAttachment = {
            id: `staged-${nextStagedAttachmentId++}`, // Give a temporary unique ID for UI management
            file: file,
            userPrompt: '' // Default empty user prompt, can be edited in UI later
        };
        stagedAttachments.push(newStagedAttachment);
    }

    console.log('[DEBUG handleFileSelection] After adding files. Staged attachments count:', stagedAttachments.length, 'Content:', JSON.stringify(stagedAttachments.map(a => ({name: a.file.name, id: a.id, userPrompt: a.userPrompt}))));
    const listId = event.target.id === 'new-topic-attachment-input' 
                   ? 'new-topic-pending-attachments-list' 
                   : 'reply-pending-attachments-list';
    renderStagedAttachments(listId);

    event.target.value = null; // Clear the file input to allow selecting the same file again
    // console.log('[DEBUG] Staged attachments after selection and render:', stagedAttachments);
}

/**
 * Renders the currently staged attachments into the specified list container.
 * @param {string} targetListId - The ID of the DOM element to render into.
 */
function renderStagedAttachments(targetListId) {
    const listElement = document.getElementById(targetListId);
    if (!listElement) {
        console.error(`renderStagedAttachments: Target list element with ID '${targetListId}' not found.`); // Kept console.error, removed [DEBUG]
        return;
    }
    listElement.innerHTML = ''; // Clear current display

    stagedAttachments.forEach((attachment, index) => { // Add index for reordering logic
        const itemDiv = document.createElement('div');
        itemDiv.className = 'staged-attachment-item'; // Use this class for styling
        itemDiv.dataset.id = attachment.id;

        const fileNameSpan = document.createElement('span');
        fileNameSpan.className = 'staged-filename';
        fileNameSpan.textContent = attachment.file.name;
        itemDiv.appendChild(fileNameSpan);

        const promptInput = document.createElement('input');
        promptInput.type = 'text';
        promptInput.className = 'staged-user-prompt form-input'; // Added form-input
        promptInput.value = attachment.userPrompt;
        promptInput.placeholder = 'Custom prompt for LLM (optional)';
        promptInput.addEventListener('input', (e) => { // 'input' for immediate update
            const stagedAtt = stagedAttachments.find(sa => sa.id === attachment.id);
            if (stagedAtt) {
                stagedAtt.userPrompt = e.target.value;
                // console.log('[DEBUG] Updated userPrompt for staged ID', attachment.id, 'to:', stagedAtt.userPrompt);
            }
        });
        itemDiv.appendChild(promptInput);

        // --- Controls Container ---
        const controlsDiv = document.createElement('div');
        controlsDiv.className = 'staged-attachment-controls';

        const moveUpButton = document.createElement('button');
        moveUpButton.className = 'move-staged-up-btn staged-attachment-action-btn btn btn-secondary btn-small';
        moveUpButton.innerHTML = '&#x2191;'; // Up arrow: ↑
        moveUpButton.title = 'Move Up';
        moveUpButton.disabled = (index === 0);
        moveUpButton.addEventListener('click', () => {
            const currentIdx = stagedAttachments.findIndex(sa => sa.id === attachment.id);
            if (currentIdx > 0) {
                [stagedAttachments[currentIdx - 1], stagedAttachments[currentIdx]] = [stagedAttachments[currentIdx], stagedAttachments[currentIdx - 1]];
                renderStagedAttachments(targetListId);
                // console.log('[DEBUG] Moved up staged attachment ID', attachment.id);
            }
        });
        controlsDiv.appendChild(moveUpButton);

        const moveDownButton = document.createElement('button');
        moveDownButton.className = 'move-staged-down-btn staged-attachment-action-btn btn btn-secondary btn-small';
        moveDownButton.innerHTML = '&#x2193;'; // Down arrow: ↓
        moveDownButton.title = 'Move Down';
        moveDownButton.disabled = (index === stagedAttachments.length - 1);
        moveDownButton.addEventListener('click', () => {
            const currentIdx = stagedAttachments.findIndex(sa => sa.id === attachment.id);
            if (currentIdx < stagedAttachments.length - 1 && currentIdx !== -1) {
                [stagedAttachments[currentIdx + 1], stagedAttachments[currentIdx]] = [stagedAttachments[currentIdx], stagedAttachments[currentIdx + 1]];
                renderStagedAttachments(targetListId);
                // console.log('[DEBUG] Moved down staged attachment ID', attachment.id);
            }
        });
        controlsDiv.appendChild(moveDownButton);
        
        const removeButton = document.createElement('button');
        removeButton.className = 'remove-staged-btn staged-attachment-action-btn btn btn-danger btn-small';
        removeButton.innerHTML = '&#x1F5D1;'; // Trash can: 🗑️
        removeButton.title = 'Remove';
        removeButton.addEventListener('click', () => {
            stagedAttachments = stagedAttachments.filter(sa => sa.id !== attachment.id);
            renderStagedAttachments(targetListId); // Re-render the list for this specific target
            // console.log('[DEBUG] Removed staged attachment ID', attachment.id, '. Remaining:', stagedAttachments);
        });
        controlsDiv.appendChild(removeButton);

        itemDiv.appendChild(controlsDiv); // Append controls container to the itemDiv

        listElement.appendChild(itemDiv);
    });
    // console.log(`[DEBUG] Rendered ${stagedAttachments.length} items into ${targetListId}`);
}


/*
// Event listeners for file inputs - These should ideally be set up in main.js or an init function.
// Ensure these IDs match the ones in templates/index.html
document.addEventListener('DOMContentLoaded', () => {
    const newTopicAttachmentInput = document.getElementById('new-topic-attachment-input');
    if (newTopicAttachmentInput) {
        newTopicAttachmentInput.addEventListener('change', handleFileSelection);
    } else {
        console.warn("Element with ID 'new-topic-attachment-input' not found for event listener setup.");
    }

    const replyAttachmentInput = document.getElementById('reply-attachment-input');
    if (replyAttachmentInput) {
        replyAttachmentInput.addEventListener('change', handleFileSelection);
    } else {
        console.warn("Element with ID 'reply-attachment-input' not found for event listener setup.");
    }
});
*/