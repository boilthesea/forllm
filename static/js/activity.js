import { apiRequest } from './api.js';
import { showSection } from './ui.js';
import {
    activityNewTopicsList,
    activityNewRepliesList,
    activityNewPersonasList
} from './dom.js';
import { loadPosts, loadTopics, setCurrentTopicAndSubforum } from './forum.js'; // Assuming loadPosts will show the section
import { showSettingsPage, openPersonaForEditing } from './settings.js'; // Assuming settings.js will expose a way to open a persona

async function renderNewTopics() {
    if (!activityNewTopicsList) return;
    activityNewTopicsList.innerHTML = '<li>Loading new topics...</li>';
    try {
        const topics = await apiRequest('/api/activity/recent_topics', 'GET');
        activityNewTopicsList.innerHTML = ''; // Clear loading
        if (topics && topics.length > 0) {
            topics.forEach(topic => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = '#';
                a.textContent = `${topic.title} (in ${topic.subforum_name})`;
                a.dataset.topicId = topic.topic_id;
                a.dataset.subforumId = topic.subforum_id;
                a.dataset.subforumName = topic.subforum_name; // Store for loadTopics
                a.addEventListener('click', async (e) => {
                    e.preventDefault();
                    // Need to ensure currentSubforumId and currentTopicId are set before loading posts
                    // And that the topic list section is updated for "back" navigation
                    setCurrentTopicAndSubforum(topic.subforum_id, topic.topic_id, topic.subforum_name, topic.title);
                    await loadPosts(topic.topic_id); // loadPosts should handle showing topic-view-section
                });
                li.appendChild(a);
                activityNewTopicsList.appendChild(li);
            });
        } else {
            activityNewTopicsList.innerHTML = '<li>No new topics.</li>';
        }
    } catch (error) {
        console.error('Error loading recent topics:', error);
        activityNewTopicsList.innerHTML = '<li>Error loading new topics.</li>';
    }
}

async function renderNewReplies() {
    if (!activityNewRepliesList) return;
    activityNewRepliesList.innerHTML = '<li>Loading new replies...</li>';
    try {
        const replies = await apiRequest('/api/activity/recent_replies', 'GET');
        activityNewRepliesList.innerHTML = ''; // Clear loading
        if (replies && replies.length > 0) {
            replies.forEach(reply => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = '#';
                // Using a more descriptive text for the link
                a.textContent = `Reply in "${reply.topic_title}": "${reply.content_snippet}..."`;
                a.dataset.topicId = reply.topic_id;
                a.dataset.postId = reply.post_id;
                a.dataset.subforumId = reply.subforum_id; // For context if needed
                // Need subforum_name and topic_title for setCurrentTopicAndSubforum
                a.dataset.subforumName = reply.subforum_name;
                a.dataset.topicTitle = reply.topic_title;


                a.addEventListener('click', async (e) => {
                    e.preventDefault();
                    setCurrentTopicAndSubforum(reply.subforum_id, reply.topic_id, reply.subforum_name, reply.topic_title);
                    await loadPosts(reply.topic_id); // loadPosts will show the section
                    // TODO: Scroll to and highlight the specific post (reply.post_id)
                    // For now, just navigating to the topic is sufficient.
                    const postElement = document.getElementById(`post-${reply.post_id}`);
                    if (postElement) {
                        postElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        postElement.classList.add('highlighted-post'); // Add a class for styling
                        setTimeout(() => postElement.classList.remove('highlighted-post'), 3000); // Remove highlight after 3s
                    }
                });
                li.appendChild(a);
                activityNewRepliesList.appendChild(li);
            });
        } else {
            activityNewRepliesList.innerHTML = '<li>No new replies.</li>';
        }
    } catch (error) {
        console.error('Error loading recent replies:', error);
        activityNewRepliesList.innerHTML = '<li>Error loading new replies.</li>';
    }
}

async function renderNewPersonas() {
    if (!activityNewPersonasList) return;
    activityNewPersonasList.innerHTML = '<li>Loading new personas...</li>';
    try {
        const personas = await apiRequest('/api/activity/recent_personas', 'GET');
        activityNewPersonasList.innerHTML = ''; // Clear loading
        if (personas && personas.length > 0) {
            personas.forEach(persona => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = '#';
                a.textContent = persona.name;
                a.dataset.personaId = persona.persona_id;
                a.addEventListener('click', async (e) => {
                    e.preventDefault();
                    // Navigate to settings, then personas tab, then open this persona.
                    // This relies on settings.js providing a way to do this.
                    showSettingsPage(true); // true to indicate navigating to personas tab
                    // A slight delay might be needed if showSettingsPage involves async ops before tab switching logic
                    setTimeout(() => {
                        openPersonaForEditing(persona.persona_id);
                    }, 100); // Small delay to ensure persona tab is visible
                });
                li.appendChild(a);
                activityNewPersonasList.appendChild(li);
            });
        } else {
            activityNewPersonasList.innerHTML = '<li>No new personas.</li>';
        }
    } catch (error) {
        console.error('Error loading recent personas:', error);
        activityNewPersonasList.innerHTML = '<li>Error loading new personas.</li>';
    }
}

export async function loadActivityData() {
    // Render all three panels
    await Promise.all([
        renderNewTopics(),
        renderNewReplies(),
        renderNewPersonas()
    ]);
}
