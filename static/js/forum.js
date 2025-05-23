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
    try {
        const newTopicResponse = await apiRequest(`/api/subforums/${currentSubforumId}/topics`, 'POST', { title, content });
         if (newTopicResponse && newTopicResponse.topic_id && newTopicResponse.initial_post_id) {
            // Successfully created topic and initial post
            const initial_post_id = newTopicResponse.initial_post_id;

            // Handle file uploads for the new post
            const fileInput = document.getElementById('new-topic-attachment-input');
            if (fileInput && fileInput.files.length > 0) {
                // The finalDisplayContainerId needs to be dynamically known or updated after the post is rendered.
                // For now, uploads will add to a pending list. The main post list will refresh via loadPosts.
                // Or, if loadPosts is called after this, the attachments will be rendered then.
                // Let's pass the specific container ID for the new post, which will be created when posts are re-rendered.
                await handleFileUploadsForPost(initial_post_id, fileInput.files, 'new-topic-pending-attachments-list', `post-attachments-${initial_post_id}`);
                fileInput.value = ''; // Clear the file input
                const pendingList = document.getElementById('new-topic-pending-attachments-list');
                if (pendingList) pendingList.innerHTML = ''; // Clear pending list display
            }

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

            // Handle file uploads for the new reply
            const fileInput = document.getElementById('reply-attachment-input');
            if (fileInput && fileInput.files.length > 0) {
                // Similar to addTopic, pass the specific container ID for the new reply post.
                await handleFileUploadsForPost(new_reply_post_id, fileInput.files, 'reply-pending-attachments-list', `post-attachments-${new_reply_post_id}`);
                fileInput.value = ''; // Clear the file input
                const pendingList = document.getElementById('reply-pending-attachments-list');
                if (pendingList) pendingList.innerHTML = ''; // Clear pending list display
            }

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
 * Uploads a single file to the server for a given post.
 * @param {number} postId - The ID of the post to attach the file to.
 * @param {File} file - The file object to upload.
 * @param {HTMLElement} [tempDisplayContainer=null] - Optional. A DOM element to show temporary upload status for this specific file.
 * @returns {Promise<object|null>} The attachment data from the server or null on failure.
 */
async function uploadSingleFile(postId, file, tempDisplayContainer = null) {
    const tempId = `temp-upload-${postId}-${file.name}-${Date.now()}`; // Include postId for better uniqueness
    let tempListItem = null;

    if (tempDisplayContainer) {
        tempListItem = document.createElement('div');
        tempListItem.className = 'pending-attachment-item';
        tempListItem.textContent = `Uploading ${file.name}...`;
        tempListItem.id = tempId;
        tempDisplayContainer.appendChild(tempListItem);
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const newAttachmentData = await apiRequest(`/api/posts/${postId}/attachments`, 'POST', formData, true); // true for isFormData
        if (newAttachmentData && newAttachmentData.attachment_id) {
            if (tempListItem) {
                tempListItem.textContent = `${file.name} - Uploaded successfully.`;
                // Remove the temporary item after a short delay
                setTimeout(() => tempListItem.remove(), 3000);
            }
            return newAttachmentData;
        } else {
            throw new Error('Upload completed but no valid attachment data returned.');
        }
    } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        if (tempListItem) {
            tempListItem.textContent = `Failed to upload ${file.name}: ${error.message || 'Unknown error'}`;
            tempListItem.style.color = 'red';
            // Optionally, don't remove error messages automatically or provide a way to clear them.
        } else {
            // Fallback alert if no temp display area was provided (less likely with new flow)
            alert(`Failed to upload ${file.name}: ${error.message || 'Unknown error'}`);
        }
        return null;
    }
}

/**
 * Handles the selection of files from a FileList, uploading them for a given post.
 * After successful uploads, it can optionally render them into a final display container.
 * @param {number} postId - The ID of the post.
 * @param {FileList} fileList - The FileList object (e.g., from an input element's .files property).
 * @param {string} tempDisplayListId - The ID of the DOM element to display temporary file statuses during upload.
 * @param {string} [finalDisplayContainerId=null] - Optional. The ID of the DOM container where successfully uploaded attachments should be fully rendered using renderAttachmentItem.
 */
async function handleFileUploadsForPost(postId, fileList, tempDisplayListId, finalDisplayContainerId = null) {
    if (!fileList || fileList.length === 0) {
        console.log("handleFileUploadsForPost: No files to upload.");
        return;
    }
    if (!postId) {
        console.error("handleFileUploadsForPost: postId is required.");
        alert("Error: Cannot upload attachments without a valid post ID.");
        return;
    }

    const tempDisplayListElement = document.getElementById(tempDisplayListId);
    const finalDisplayContainerElement = finalDisplayContainerId ? document.getElementById(finalDisplayContainerId) : null;

    if (tempDisplayListElement) {
        // Clear previous items from the temporary display list for this batch of uploads
        // tempDisplayListElement.innerHTML = ''; // Commented out: uploadSingleFile appends, so clearing might remove ongoing upload statuses from parallel calls if any. Let individual items be removed.
    }

    for (const file of fileList) {
        const newAttachmentData = await uploadSingleFile(postId, file, tempDisplayListElement); // Pass temp element for status updates
        if (newAttachmentData && finalDisplayContainerElement) {
            // If a final container is specified, render the successfully uploaded attachment there.
            renderAttachmentItem(newAttachmentData, finalDisplayContainerElement, postId);
        }
    }
}

// Export state variables if needed by other modules (e.g., main.js for initial load)
export { currentSubforumId, currentTopicId, currentPosts };
// Export new attachment handlers
export { handleFileUploadsForPost, renderAttachmentItem }; // renderAttachmentItem is exported for direct use if needed elsewhere