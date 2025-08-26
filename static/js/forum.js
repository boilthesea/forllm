// This file will handle forum-specific logic.

import { apiRequest, fetchActivePersonas, tagPostForPersonaResponse } from './api.js'; // Added imports
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
    settingsPageContent, // Needed for link security check in postList event listener
    llmPersonaSelect,
    subforumPersonasBar
} from './dom.js';
import { showSection, showLinkWarningPopup, openSecondaryPane, isMobile, toggleMobileMenu } from './ui.js';
import { newTopicEditor, replyEditor, createEditor } from './editor.js'; // Import editor instances and creator
import { initializeTomSelect } from './ui-helpers.js';

// --- State Variables ---
let currentSubforumId = null;
let currentTopicId = null;
let currentPosts = []; // Store posts for the current topic
let currentPersonaId = null;
let isEditingPost = false;

// --- Persona Tagging Cache for forum.js ---
let forumActivePersonasCache = [];
let forumPersonasCacheTimestamp = 0;
const FORUM_PERSONA_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes


let stagedAttachments = []; // For managing files selected in UI before actual upload
let nextStagedAttachmentId = 0; // Counter for unique IDs for staged attachments

// --- Rendering Functions ---

import { subforumNav } from './dom.js';

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
            // If on mobile and the menu is open, close it
            if (isMobile() && subforumNav.classList.contains('mobile-menu-visible')) {
                toggleMobileMenu();
            }
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

        const openInPaneBtn = document.createElement('span');
        openInPaneBtn.className = 'topic-action-icon button-icon';
        openInPaneBtn.title = 'Open in new pane';
        openInPaneBtn.innerHTML = '&#x2924;'; // Symbol for "Open in new window"
        openInPaneBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation(); // Prevent the topic link's click event
            
            try {
                // Fetch the raw post data for the topic
                const posts = await apiRequest(`/api/topics/${topic.topic_id}/posts`);
                if (posts && posts.length > 0) {
                    // Create the same structure as the primary pane to ensure CSS rules apply
                    const tempSection = document.createElement('section');
                    tempSection.id = 'topic-view-section'; // Use the same ID to match styles

                    const tempPostList = document.createElement('div');
                    tempPostList.id = 'post-list';

                    // Reuse the existing post rendering logic to build the HTML
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
                    rootPosts.forEach(post => renderPostNode(post, tempPostList, 0));

                    tempSection.appendChild(tempPostList);

                    // Pass the generated HTML to openSecondaryPane
                    openSecondaryPane(tempSection.innerHTML, topic.title);
                } else {
                    openSecondaryPane('<p>This topic has no posts.</p>', topic.title);
                }
            } catch (error) {
                console.error('Failed to load topic for secondary pane:', error);
                openSecondaryPane('<p>Error loading topic content.</p>', 'Error');
            }
        });

        const meta = document.createElement('div');
        meta.className = 'topic-meta';
        meta.textContent = `Started by ${topic.username} | Posts: ${topic.post_count} | Last post: ${new Date(topic.last_post_at).toLocaleString()}`;
        li.appendChild(a);
        li.appendChild(openInPaneBtn);
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

async function displayPostTagSuggestions(query, suggestionsDiv, postId, inputElement) {
    const now = Date.now();
    if (!forumActivePersonasCache.length || (now - forumPersonasCacheTimestamp > FORUM_PERSONA_CACHE_DURATION)) {
        console.log("Fetching personas for post tagging...");
        forumActivePersonasCache = await fetchActivePersonas() || [];
        forumPersonasCacheTimestamp = now;
        if (!forumActivePersonasCache.length) {
            console.log("No active personas found or failed to fetch for post tagging.");
        }
    }

    // Sanitize query: remove leading '@' if present, as persona names don't have it.
    const sanitizedQuery = query.startsWith('@') ? query.substring(1) : query;

    const filteredPersonas = forumActivePersonasCache.filter(p =>
        p.name.toLowerCase().includes(sanitizedQuery.toLowerCase())
    );

    suggestionsDiv.innerHTML = ''; // Clear previous suggestions
    if (!filteredPersonas.length) {
        const noResultsItem = document.createElement('div');
        noResultsItem.textContent = 'No matching personas';
        noResultsItem.classList.add('suggestion-item', 'no-results'); // Use classes for styling
        suggestionsDiv.appendChild(noResultsItem);
        // Keep suggestionsDiv visible to show "No results", or hide if preferred:
        // suggestionsDiv.style.display = 'none'; 
        // return;
    } else {
        filteredPersonas.forEach(persona => {
            const item = document.createElement('div');
            item.textContent = persona.name;
            item.classList.add('suggestion-item'); // Common class for styling from CSS
            item.dataset.personaId = persona.persona_id; // Store ID for action
            item.dataset.personaName = persona.name; // Store name for action

            // Hover effects will be handled by CSS :hover on .suggestion-item
            
            // Use mousedown to ensure it fires before the input's blur event
            item.addEventListener('mousedown', async (e) => { 
                e.preventDefault(); // Prevent the input from losing focus immediately
                try {
                    console.log(`Tagging post ${postId} with persona ${persona.persona_id} (${persona.name})`);
                    await tagPostForPersonaResponse(String(postId), String(persona.persona_id));
                    inputElement.value = ''; 
                    suggestionsDiv.style.display = 'none';
                    suggestionsDiv.innerHTML = ''; // Clear items
                    alert(`Post ${postId} tagged for ${persona.name} to respond.`);
                    // Consider a less intrusive notification or UI update here
                } catch (error) {
                    // Error already logged by tagPostForPersonaResponse/apiRequest
                    alert(`Failed to tag post for ${persona.name}.`);
                }
            });
            suggestionsDiv.appendChild(item);
        });
    }
    
    // Position suggestionsDiv - This assumes .tag-persona-container is position:relative
    // and .tag-persona-suggestions is position:absolute.
    suggestionsDiv.style.left = '0'; 
    suggestionsDiv.style.top = `${inputElement.offsetHeight}px`; // Position directly below input
    suggestionsDiv.style.width = `${inputElement.offsetWidth}px`; // Match width
        
    suggestionsDiv.style.display = 'block';
}

function renderPostNode(post, parentElement, depth) {
    const postDiv = document.createElement('div');
    postDiv.className = 'post';
    postDiv.dataset.postId = post.post_id;
    postDiv.style.marginLeft = `${depth * 2}rem`;

    if (post.is_llm_response) {
        postDiv.classList.add('llm-response');
    }

    // --- Create Meta Header ---
    const metaDiv = document.createElement('div');
    metaDiv.className = 'post-meta';

    const metaInfo = document.createElement('div');
    metaInfo.className = 'post-meta-info';
    const displayName = (post.is_llm_response && post.persona_name) ? post.persona_name : post.username;
    const dateString = new Date(post.created_at).toLocaleString();
    metaInfo.innerHTML = `Posted by <strong>${displayName}</strong> on ${dateString}`;

    if (post.is_llm_response) {
        const llmMeta = document.createElement('span');
        llmMeta.className = 'llm-meta';
        llmMeta.textContent = ` (LLM: ${post.llm_model_id || 'default'} / Persona ID: ${post.llm_persona_id})`;
        metaInfo.appendChild(llmMeta);
    }

    const metaActions = document.createElement('div');
    metaActions.className = 'post-meta-actions';

    const optionsButton = document.createElement('button');
    optionsButton.className = 'post-options-btn';
    optionsButton.innerHTML = '&hellip;';

    const optionsMenu = document.createElement('div');
    optionsMenu.className = 'post-options-menu';

    const editBtn = document.createElement('a');
    editBtn.href = '#';
    editBtn.className = 'edit-post-btn';
    editBtn.textContent = 'Edit';
    editBtn.dataset.postId = post.post_id;
    optionsMenu.appendChild(editBtn);

    const isRootPost = post.parent_post_id === null;
    if (isRootPost) {
        const deleteTopicBtn = document.createElement('a');
        deleteTopicBtn.href = '#';
        deleteTopicBtn.className = 'delete-topic-btn';
        deleteTopicBtn.textContent = 'Delete Topic';
        deleteTopicBtn.dataset.topicId = post.topic_id;
        optionsMenu.appendChild(deleteTopicBtn);
    } else {
        const deletePostBtn = document.createElement('a');
        deletePostBtn.href = '#';
        deletePostBtn.className = 'delete-post-btn';
        deletePostBtn.textContent = 'Delete Post';
        deletePostBtn.dataset.postId = post.post_id;
        optionsMenu.appendChild(deletePostBtn);
    }

    metaActions.appendChild(optionsButton);
    metaActions.appendChild(optionsMenu);

    optionsButton.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.post-options-menu').forEach(menu => {
            if (menu !== optionsMenu) {
                menu.style.display = 'none';
            }
        });
        optionsMenu.style.display = optionsMenu.style.display === 'block' ? 'none' : 'block';
    });

    metaDiv.appendChild(metaInfo);
    metaDiv.appendChild(metaActions);
    // --- End Meta Header ---

    const contentDiv = document.createElement('div');
    contentDiv.className = 'post-content';
    contentDiv.id = `post-content-${post.post_id}`;
    contentDiv.innerHTML = post.content;

    contentDiv.innerHTML = contentDiv.innerHTML.replace(
        /@\[([^\]]+)\]\((\d+)\)/g, 
        '<span class="persona-tag" data-persona-id="$2" title="Persona: $1 (ID: $2)">@$1</span>'
    );

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

    const tagPersonaContainer = document.createElement('div');
    tagPersonaContainer.className = 'tag-persona-container';
    
    const tagInput = document.createElement('input');
    tagInput.type = 'text';
    tagInput.placeholder = 'Tag persona to respond...';
    tagInput.className = 'tag-persona-input';
    tagInput.dataset.postId = post.post_id; 

    const tagSuggestionsDiv = document.createElement('div');
    tagSuggestionsDiv.className = 'tag-persona-suggestions';
    tagSuggestionsDiv.style.display = 'none'; 

    tagInput.addEventListener('input', async (e) => {
        const query = e.target.value;
        const currentPostId = e.target.dataset.postId;
        if (query.length > 0) {
            await displayPostTagSuggestions(query, tagSuggestionsDiv, currentPostId, tagInput);
        } else {
            tagSuggestionsDiv.style.display = 'none';
        }
    });
    
    tagInput.addEventListener('blur', () => {
        setTimeout(() => {
            if (!tagSuggestionsDiv.matches(':hover')) {
                tagSuggestionsDiv.style.display = 'none';
            }
        }, 200);
    });

    tagPersonaContainer.appendChild(tagInput);
    tagPersonaContainer.appendChild(tagSuggestionsDiv);
    actionsDiv.appendChild(tagPersonaContainer);

    postDiv.appendChild(metaDiv);
    postDiv.appendChild(contentDiv);
    postDiv.appendChild(actionsDiv);

    const personaTagElements = contentDiv.querySelectorAll('.persona-tag');
    personaTagElements.forEach(tagEl => {
        tagEl.addEventListener('click', function(event) {
            event.preventDefault();
        });
    });

    if (post.attachments && Array.isArray(post.attachments) && post.attachments.length > 0) {
        const attachmentsContainerDiv = document.createElement('div');
        attachmentsContainerDiv.className = 'post-attachments-list mt-2';
        attachmentsContainerDiv.id = `post-attachments-${post.post_id}`;

        post.attachments.forEach(attachmentData => {
            renderAttachmentItem(attachmentData, attachmentsContainerDiv, post.post_id);
        });
        postDiv.appendChild(attachmentsContainerDiv);
    }

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

// Removed displayPostTagSuggestions from here as it's moved above renderPostNode

// --- Loading Functions ---
export async function loadSubforums(shouldShowSection = true) {
    try {
        const subforums = await apiRequest('/api/subforums');
        renderSubforumList(subforums);
        if (shouldShowSection) {
            showSection('subforum-nav'); // This might need adjustment in main.js
        }
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
        document.dispatchEvent(new CustomEvent('subforumChanged', { detail: { subforumId: currentSubforumId } }));
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
        // After successfully loading posts and updating user activity for the topic,
        // refresh the subforum list to update badges.
        // Pass false to prevent loadSubforums from hiding the topic view section
        loadSubforums(false);
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
        const tsInstance = initializeTomSelect(llmPersonaSelect, {
            create: false,
            controlInput: null, // Disables text input completely
            onChange: (value) => {
                currentPersonaId = value;
                const llmPersonaCurrentLabel = document.getElementById('llm-persona-current-label');
                if (llmPersonaCurrentLabel) {
                    const selectedPersona = personas.find(p => p.persona_id == value);
                    llmPersonaCurrentLabel.textContent = 'Current: ' + (selectedPersona ? selectedPersona.name : 'None');
                }
            }
        });
        if (tsInstance) {
            tsInstance.setValue(currentPersonaId, true); // Silently set value
        }
        const llmPersonaCurrentLabel = document.getElementById('llm-persona-current-label');
        if(llmPersonaCurrentLabel) llmPersonaCurrentLabel.textContent = 'Current: ' + personas.find(p => p.persona_id == currentPersonaId)?.name;
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

async function enterEditMode(postId) {
    if (isEditingPost) {
        alert('Please save or cancel your current edit before editing another post.');
        return;
    }
    isEditingPost = true;

    const post = currentPosts.find(p => p.post_id == postId);
    if (!post) {
        isEditingPost = false;
        return;
    }

    // --- Fetch raw content for editing ---
    let rawContent;
    try {
        const response = await apiRequest(`/api/posts/${postId}/raw`);
        if (!response || typeof response.content === 'undefined') {
            throw new Error('Invalid response from raw content endpoint.');
        }
        rawContent = response.content;
    } catch (error) {
        alert('Failed to load post content for editing. Please try again.');
        console.error('Error fetching raw post content:', error);
        isEditingPost = false;
        return;
    }
    // --- End fetch raw content ---

    const postContentDiv = document.getElementById(`post-content-${postId}`);
    const postDiv = postContentDiv.closest('.post');
    const actionsDiv = postDiv.querySelector('.post-actions');

    const originalContentHTML = postContentDiv.innerHTML;
    let originalTitle = null;

    if (actionsDiv) actionsDiv.style.display = 'none';

    const editorContainer = document.createElement('div');
    editorContainer.className = 'edit-container';

    const isRootPost = post.parent_post_id === null;
    if (isRootPost) {
        const topicTitleElement = document.getElementById('current-topic-title');
        originalTitle = topicTitleElement.textContent;
        const titleInput = document.createElement('input');
        titleInput.type = 'text';
        titleInput.className = 'edit-topic-title-input form-input';
        titleInput.value = originalTitle;
        topicTitleElement.innerHTML = '';
        topicTitleElement.appendChild(titleInput);
        titleInput.id = 'current-topic-title-edit'; // Use a class or more specific selector if needed
    }

    const textArea = document.createElement('textarea');
    editorContainer.appendChild(textArea);
    postContentDiv.innerHTML = '';
    postContentDiv.appendChild(editorContainer);

    const easyMDE = createEditor(textArea, `edit-post-${postId}`, rawContent);

    const editActions = document.createElement('div');
    editActions.className = 'edit-actions mt-2';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.className = 'btn button-primary';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'btn button-secondary ml-2';

    editActions.appendChild(saveBtn);
    editActions.appendChild(cancelBtn);
    editorContainer.appendChild(editActions);

    const cancelEdit = () => {
        isEditingPost = false;
        postContentDiv.innerHTML = originalContentHTML;

        if (isRootPost) {
            const topicTitleElement = document.getElementById('current-topic-title');
            if (topicTitleElement) {
                topicTitleElement.innerHTML = ''; // Clear the input
                topicTitleElement.textContent = originalTitle;
            }
        }

        if (actionsDiv) actionsDiv.style.display = 'flex';
    };

    saveBtn.addEventListener('click', async () => {
        const newContent = easyMDE.value();
        let newTitle = null;
        const payload = { content: newContent };

        if (isRootPost) {
            const titleInput = document.querySelector('.edit-topic-title-input');
            newTitle = titleInput.value.trim();
            if (!newTitle) {
                alert('Topic title cannot be empty.');
                return;
            }
            payload.title = newTitle;
        }

        try {
            const response = await apiRequest(`/api/posts/${postId}`, 'PUT', payload);
            if (response) {
                isEditingPost = false;
                post.content = newContent;
                postContentDiv.innerHTML = response.new_content_html;

                if (isRootPost && response.new_title) {
                    const topicTitleElement = document.getElementById('current-topic-title');
                    if (topicTitleElement) {
                        topicTitleElement.innerHTML = '';
                        topicTitleElement.textContent = response.new_title;
                    }
                }

                if (actionsDiv) actionsDiv.style.display = 'flex';
            } else {
                cancelEdit();
            }
        } catch (error) {
            cancelEdit();
        }
    });

    cancelBtn.addEventListener('click', cancelEdit);
}

// Event Delegation for post actions (edit, delete, links)
postList.addEventListener('click', async (event) => {
    const target = event.target;

    // Handle LLM link security
    const link = target.closest('a');
    if (link && link.classList.contains('llm-link')) {
        if (currentSettings.llmLinkSecurity === 'true') {
            event.preventDefault();
            const url = link.href;
            const text = link.textContent;
            showLinkWarningPopup(url, text);
        }
        return; // Stop further processing
    }

    // Handle Delete Post
    if (target.classList.contains('delete-post-btn')) {
        event.preventDefault();
        const postId = target.dataset.postId;
        if (confirm('Are you sure you want to delete this post? This action is permanent and cannot be undone.')) {
            try {
                await apiRequest(`/api/posts/${postId}`, 'DELETE');
                const postContentDiv = document.getElementById(`post-content-${postId}`);
                if (postContentDiv) {
                    postContentDiv.innerHTML = '<p><em>[Post Deleted]</em></p>';
                    const postDiv = postContentDiv.closest('.post');
                    // Remove action buttons and edit/delete options
                    const actionsDiv = postDiv.querySelector('.post-actions');
                    if (actionsDiv) actionsDiv.remove();
                    const metaActionsDiv = postDiv.querySelector('.post-meta-actions');
                    if (metaActionsDiv) metaActionsDiv.remove();
                }
            } catch (error) {
                console.error(`Failed to delete post ${postId}:`, error);
            }
        }
    }

    // Handle Delete Topic
    if (target.classList.contains('delete-topic-btn')) {
        event.preventDefault();
        const topicId = target.dataset.topicId;
        if (confirm('Are you sure you want to delete this entire topic? This will delete all posts and cannot be undone.')) {
            try {
                await apiRequest(`/api/topics/${topicId}`, 'DELETE');
                // After deleting, load the parent subforum's topic list
                const subforumLink = subforumList.querySelector(`a[data-subforum-id="${currentSubforumId}"]`);
                const subforumName = subforumLink ? subforumLink.dataset.subforumName : 'Current Subforum';
                loadTopics(currentSubforumId, subforumName);
            } catch (error) {
                console.error(`Failed to delete topic ${topicId}:`, error);
            }
        }
    }

    // Handle Edit Post
    if (target.classList.contains('edit-post-btn')) {
        event.preventDefault();
        const postId = target.dataset.postId;
        // Close the options menu before entering edit mode
        const menu = target.closest('.post-options-menu');
        if (menu) {
            menu.style.display = 'none';
        }
        enterEditMode(postId);
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
    deleteButton.textContent = '🗑';
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

export function setCurrentTopicAndSubforum(subforumId, topicId, subforumName, topicTitle) {
    currentSubforumId = subforumId;
    currentTopicId = topicId;
    // Update UI elements if they exist (e.g., breadcrumbs or titles)
    if (currentSubforumName && subforumName) {
        currentSubforumName.textContent = subforumName;
    }
    if (currentTopicTitle && topicTitle) {
        currentTopicTitle.textContent = topicTitle;
    }
    // This function primarily sets state. UI updates related to showing sections
    // or loading data are handled by functions like loadPosts, loadTopics.
}

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