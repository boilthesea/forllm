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
        const newTopic = await apiRequest(`/api/subforums/${currentSubforumId}/topics`, 'POST', { title, content });
         if (newTopic) {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = '#';
            a.textContent = newTopic.title;
            a.dataset.topicId = newTopic.topic_id;
            a.dataset.topicTitle = newTopic.title;
            a.addEventListener('click', (e) => {
                e.preventDefault();
                loadPosts(newTopic.topic_id, newTopic.title);
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
        const newPost = await apiRequest(`/api/topics/${currentTopicId}/posts`, 'POST', { content, parent_post_id: parentPostId });
        if (newPost) {
            hideReplyForm();
            loadPosts(currentTopicId, currentTopicTitle.textContent);
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
        await apiRequest(`/api/posts/${postId}/request_llm`, 'POST');
        alert(`LLM response request queued for post ${postId}. It will be processed during scheduled hours.`);
    } catch (error) {
        // Error handled by apiRequest
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

// Export state variables if needed by other modules (e.g., main.js for initial load)
export { currentSubforumId, currentTopicId, currentPosts };