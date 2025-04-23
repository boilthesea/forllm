document.addEventListener('DOMContentLoaded', () => {
    // --- State Variables ---
    let currentSubforumId = null;
    let currentTopicId = null;
    let currentPosts = []; // Store posts for the current topic to build threads

    // --- DOM Elements ---
    const subforumNav = document.getElementById('subforum-nav');
    const subforumList = document.getElementById('subforum-list');
    const addSubforumBtn = document.getElementById('add-subforum-btn');
    const newSubforumNameInput = document.getElementById('new-subforum-name');

    const topicListSection = document.getElementById('topic-list-section');
    const currentSubforumName = document.getElementById('current-subforum-name');
    const topicList = document.getElementById('topic-list');
    const addTopicBtn = document.getElementById('add-topic-btn');
    const newTopicTitleInput = document.getElementById('new-topic-title');
    const newTopicContentInput = document.getElementById('new-topic-content');
    const backToSubforumsBtn = document.getElementById('back-to-subforums-btn');

    const topicViewSection = document.getElementById('topic-view-section');
    const currentTopicTitle = document.getElementById('current-topic-title');
    const postList = document.getElementById('post-list');
    const backToTopicsBtn = document.getElementById('back-to-topics-btn');

    const replyFormContainer = document.getElementById('reply-form-container');
    const replyToPostIdSpan = document.getElementById('reply-to-post-id');
    const replyContentInput = document.getElementById('reply-content');
    const submitReplyBtn = document.getElementById('submit-reply-btn');
    const cancelReplyBtn = document.getElementById('cancel-reply-btn');

    // Schedule Modal Elements
    const scheduleDisplay = document.getElementById('schedule-display');
    const editScheduleBtn = document.getElementById('edit-schedule-btn');
    const scheduleModal = document.getElementById('schedule-modal');
    const closeBtn = scheduleModal.querySelector('.close-btn');
    const startHourInput = document.getElementById('start-hour');
    const endHourInput = document.getElementById('end-hour');
    const scheduleEnabledCheckbox = document.getElementById('schedule-enabled');
    const saveScheduleBtn = document.getElementById('save-schedule-btn');
    const scheduleError = document.getElementById('schedule-error');

    // Settings Modal Elements
    const settingsBtn = document.getElementById('settings-btn');
    const settingsModal = document.getElementById('settings-modal');
    const settingsCloseBtn = settingsModal.querySelector('.close-btn');
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const modelSelect = document.getElementById('model-select');
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    const settingsError = document.getElementById('settings-error');

    // --- State Variables ---
    let currentSettings = { // Store loaded settings
        darkMode: 'false',
        selectedModel: null
    };


    // --- API Helper Function ---
    async function apiRequest(url, method = 'GET', body = null) {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                console.error('API Error:', errorData);
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            // Handle cases where response might be empty (e.g., 201 No Content or 202 Accepted)
             if (response.status === 204 || response.status === 202) {
                return null; // Or return a specific indicator if needed
            }
            return await response.json();
        } catch (error) {
            console.error('Fetch Error:', error);
            alert(`An error occurred: ${error.message}`);
            throw error; // Re-throw to handle in calling function if needed
        }
    }

    // --- Rendering Functions ---

    function renderSubforumList(subforums) {
        subforumList.innerHTML = ''; // Clear existing list
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
            a.dataset.subforumName = subforum.name; // Store name for later use
            a.addEventListener('click', (e) => {
                e.preventDefault();
                loadTopics(subforum.subforum_id, subforum.name);
            });
            li.appendChild(a);
            subforumList.appendChild(li);
        });
    }

    function renderTopicList(topics) {
        topicList.innerHTML = ''; // Clear existing list
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
            a.dataset.topicTitle = topic.title; // Store title
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

    function renderPosts(posts) {
        postList.innerHTML = ''; // Clear existing list
        currentPosts = posts; // Store for potential future use (e.g., finding parent content)

        if (!Array.isArray(posts)) {
            console.error("Invalid posts data:", posts);
            return;
        }

        // Build a map of posts by ID for easy lookup
        const postsById = posts.reduce((map, post) => {
            map[post.post_id] = { ...post, children: [] };
            return map;
        }, {});

        // Build the tree structure
        const rootPosts = [];
        posts.forEach(post => {
            if (post.parent_post_id && postsById[post.parent_post_id]) {
                postsById[post.parent_post_id].children.push(postsById[post.post_id]);
            } else if (!post.parent_post_id) {
                rootPosts.push(postsById[post.post_id]);
            }
        });

        // Sort root posts by creation date (API already sorts, but good practice)
        rootPosts.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

        // Render the tree
        rootPosts.forEach(post => renderPostNode(post, postList, 0));
    }

    function renderPostNode(post, parentElement, depth) {
        const postDiv = document.createElement('div');
        postDiv.className = 'post';
        postDiv.dataset.postId = post.post_id;
        postDiv.style.marginLeft = `${depth * 2}rem`; // Indentation

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
        contentDiv.textContent = post.content; // Basic text rendering for now

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'post-actions';

        const replyButton = document.createElement('button');
        replyButton.textContent = 'Reply';
        replyButton.addEventListener('click', () => showReplyForm(post.post_id));
        actionsDiv.appendChild(replyButton);

        // Only show "Request LLM Response" button on non-LLM posts
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

        // Recursively render children, sorted by date
        if (post.children && post.children.length > 0) {
            const repliesContainer = document.createElement('div');
            repliesContainer.className = 'post-replies';
            postDiv.appendChild(repliesContainer); // Append replies container to the parent post div
            post.children
                .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
                .forEach(child => renderPostNode(child, repliesContainer, 0)); // Reset depth visually within container
        }
    }

     function renderSchedule(schedule) {
        if (schedule) {
            const enabledText = schedule.enabled ? "Enabled" : "Disabled";
            scheduleDisplay.textContent = `Processing Schedule: ${String(schedule.start_hour).padStart(2, '0')}:00 - ${String(schedule.end_hour).padStart(2, '0')}:00 (${enabledText})`;
            // Update modal inputs
            startHourInput.value = schedule.start_hour;
            endHourInput.value = schedule.end_hour;
            scheduleEnabledCheckbox.checked = schedule.enabled;
        } else {
            scheduleDisplay.textContent = "Could not load schedule.";
        }
    }

    function applyDarkMode(isDark) {
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        // Ensure toggle reflects the state
        darkModeToggle.checked = isDark;
    }

    function renderModelOptions(models, selectedModel) {
        modelSelect.innerHTML = ''; // Clear existing options
        if (!Array.isArray(models) || models.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No models found or error loading.';
            option.disabled = true;
            modelSelect.appendChild(option);
            return;
        }

        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            if (modelName === selectedModel) {
                option.selected = true;
            }
            modelSelect.appendChild(option);
        });
    }


    // --- Loading Functions ---

    async function loadSubforums() {
        try {
            const subforums = await apiRequest('/api/subforums');
            renderSubforumList(subforums);
            showSection('subforum-nav'); // Show only subforum list initially
        } catch (error) {
            // Error already logged by apiRequest
        }
    }

    async function loadTopics(subforumId, subforumName) {
        currentSubforumId = subforumId;
        currentTopicId = null; // Reset topic when viewing topic list
        try {
            const topics = await apiRequest(`/api/subforums/${subforumId}/topics`);
            currentSubforumName.textContent = subforumName; // Update heading
            renderTopicList(topics);
            showSection('topic-list');
        } catch (error) {
            // Error already logged by apiRequest
        }
    }

     async function loadPosts(topicId, topicTitle) {
        currentTopicId = topicId;
        try {
            const posts = await apiRequest(`/api/topics/${topicId}/posts`);
            currentTopicTitle.textContent = topicTitle; // Update heading
            renderPosts(posts);
            showSection('topic-view');
            hideReplyForm(); // Ensure reply form is hidden initially
        } catch (error) {
            // Error already logged by apiRequest
        }
    }

    async function loadSchedule() {
        try {
            const schedule = await apiRequest('/api/schedule');
            renderSchedule(schedule);
        } catch (error) {
            scheduleDisplay.textContent = "Error loading schedule.";
        }
    }

     async function loadSettings() {
        try {
            const settings = await apiRequest('/api/settings');
            currentSettings = settings; // Store globally
            applyDarkMode(settings.darkMode === 'true');
            // Load models *after* getting settings so we know which one to pre-select
            await loadOllamaModels();
        } catch (error) {
            console.error("Error loading settings:", error);
            // Apply default dark mode (false) and attempt to load models anyway
            applyDarkMode(false);
            await loadOllamaModels(); // Try loading models even if settings fail
        }
    }

    async function loadOllamaModels() {
        try {
            const modelsResult = await apiRequest('/api/ollama/models');
            let models = [];
            if (Array.isArray(modelsResult)) {
                // Direct array of names if successful
                models = modelsResult;
            } else if (modelsResult && Array.isArray(modelsResult.models)) {
                 // Handle the case where Ollama might be down and we return {error, models: [DEFAULT_MODEL]}
                models = modelsResult.models;
                console.warn("Ollama connection issue, using default model list:", modelsResult.error);
            } else {
                 console.error("Unexpected format for Ollama models:", modelsResult);
                 models = [currentSettings.selectedModel || 'default']; // Fallback
            }
            renderModelOptions(models, currentSettings.selectedModel);
        } catch (error) {
            console.error("Error fetching Ollama models:", error);
            renderModelOptions([currentSettings.selectedModel || 'default'], currentSettings.selectedModel); // Show current/default on error
            settingsError.textContent = "Could not fetch models from Ollama."; // Show error in modal
        }
    }


    // --- Action Functions ---

    async function addSubforum() {
        const name = newSubforumNameInput.value.trim();
        if (!name) {
            alert('Please enter a subforum name.');
            return;
        }
        try {
            const newSubforum = await apiRequest('/api/subforums', 'POST', { name });
            if (newSubforum) {
                // Add to list visually without full reload
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
                 newSubforumNameInput.value = ''; // Clear input
            }
        } catch (error) {
            // Error already handled by apiRequest
        }
    }

    async function addTopic() {
        const title = newTopicTitleInput.value.trim();
        const content = newTopicContentInput.value.trim();
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
                // Add to list visually without full reload
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
                 // We don't have all meta details immediately, show basic info
                 meta.textContent = `Started by You | Posts: 1 | Last post: Just now`;
                 li.appendChild(a);
                 li.appendChild(meta);
                 topicList.appendChild(li); // Add to top or bottom? Maybe bottom for now.

                newTopicTitleInput.value = '';
                newTopicContentInput.value = '';
            }
        } catch (error) {
            // Error already handled by apiRequest
        }
    }

    function showReplyForm(postId) {
        replyToPostIdSpan.textContent = postId;
        replyContentInput.value = ''; // Clear previous content
        replyFormContainer.style.display = 'block';
        replyContentInput.focus();
    }

    function hideReplyForm() {
        replyFormContainer.style.display = 'none';
        replyToPostIdSpan.textContent = '';
        replyContentInput.value = '';
    }

    async function submitReply() {
        const content = replyContentInput.value.trim();
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
                // Reload posts for the topic to show the new reply in the correct thread position
                hideReplyForm();
                loadPosts(currentTopicId, currentTopicTitle.textContent); // Reload posts
            }
        } catch (error) {
            // Error handled by apiRequest
        }
    }

    async function requestLlm(postId) {
        if (!confirm(`Request an LLM response to post ${postId}?`)) {
            return;
        }
        try {
            // 202 Accepted is expected, response body might be null
            await apiRequest(`/api/posts/${postId}/request_llm`, 'POST');
            alert(`LLM response request queued for post ${postId}. It will be processed during scheduled hours.`);
            // Optionally, update UI to show request is pending (Phase 2/3 feature)
        } catch (error) {
            // Error handled by apiRequest
        }
    }

     async function saveSchedule() {
        const startHour = parseInt(startHourInput.value, 10);
        const endHour = parseInt(endHourInput.value, 10);
        const enabled = scheduleEnabledCheckbox.checked;

        if (isNaN(startHour) || startHour < 0 || startHour > 23 ||
            isNaN(endHour) || endHour < 0 || endHour > 23) {
            scheduleError.textContent = "Hours must be between 0 and 23.";
            return;
        }
        scheduleError.textContent = ""; // Clear error

        try {
            const updatedSchedule = await apiRequest('/api/schedule', 'PUT', {
                start_hour: startHour,
                end_hour: endHour,
                enabled: enabled
            });
            if (updatedSchedule) {
                renderSchedule(updatedSchedule);
                scheduleModal.style.display = 'none'; // Close modal on success
            }
        } catch (error) {
             scheduleError.textContent = `Error saving schedule: ${error.message}`;
        }
    }

    async function saveSettings() {
        const newDarkMode = darkModeToggle.checked;
        const newSelectedModel = modelSelect.value;

        settingsError.textContent = ""; // Clear previous errors

        if (!newSelectedModel) {
            settingsError.textContent = "Please select a model.";
            return;
        }

        const settingsToSave = {
            darkMode: newDarkMode.toString(), // Save as string 'true'/'false'
            selectedModel: newSelectedModel
        };

        try {
            const updatedSettings = await apiRequest('/api/settings', 'PUT', settingsToSave);
            if (updatedSettings) {
                currentSettings = updatedSettings; // Update global state
                applyDarkMode(currentSettings.darkMode === 'true'); // Re-apply just in case
                renderModelOptions( // Re-render options to ensure selection is correct
                    Array.from(modelSelect.options).map(opt => opt.value), // Get current options
                    currentSettings.selectedModel
                );
                settingsModal.style.display = 'none'; // Close modal on success
            } else {
                 settingsError.textContent = "Failed to save settings. Server response was empty.";
            }
        } catch (error) {
            settingsError.textContent = `Error saving settings: ${error.message}`;
        }
    }


    // --- UI Navigation ---
    function showSection(section) {
        // Hide all main content sections first
        subforumNav.style.display = 'none';
        topicListSection.style.display = 'none';
        topicViewSection.style.display = 'none';

        // Show the requested section(s)
        if (section === 'subforum-nav') {
            subforumNav.style.display = 'block';
        } else if (section === 'topic-list') {
            subforumNav.style.display = 'block'; // Keep subforum nav visible
            topicListSection.style.display = 'block';
        } else if (section === 'topic-view') {
            subforumNav.style.display = 'block'; // Keep subforum nav visible
            topicViewSection.style.display = 'block';
        }
    }

    // --- Event Listeners ---
    addSubforumBtn.addEventListener('click', addSubforum);
    addTopicBtn.addEventListener('click', addTopic);
    submitReplyBtn.addEventListener('click', submitReply);
    cancelReplyBtn.addEventListener('click', hideReplyForm);

    backToSubforumsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        currentSubforumId = null;
        currentTopicId = null;
        showSection('subforum-nav');
    });

    backToTopicsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentSubforumId) {
            // Need the name again - ideally store it when loading topics
            // Find the name from the link dataset if possible
            const subforumLink = subforumList.querySelector(`a[data-subforum-id="${currentSubforumId}"]`);
            const subforumName = subforumLink ? subforumLink.dataset.subforumName : 'Selected Subforum';
            loadTopics(currentSubforumId, subforumName); // Reload topics for the current subforum
        } else {
            showSection('subforum-nav'); // Fallback
        }
    });

     // Schedule Modal Listeners
    editScheduleBtn.addEventListener('click', () => {
        scheduleError.textContent = ""; // Clear previous errors
        scheduleModal.style.display = 'block';
    });

    closeBtn.addEventListener('click', () => {
        scheduleModal.style.display = 'none';
    });

    saveScheduleBtn.addEventListener('click', saveSchedule);

    // Close modals if clicking outside of them
    window.addEventListener('click', (event) => {
        if (event.target == scheduleModal) {
            scheduleModal.style.display = 'none';
        }
        // Also close settings modal if clicking outside
        if (event.target == settingsModal) {
            settingsModal.style.display = 'none';
        }
    });

// Settings Modal Listeners
settingsBtn.addEventListener('click', () => {
    settingsError.textContent = ""; // Clear previous errors
    // Ensure model list and selection are up-to-date when opening
    loadOllamaModels().then(() => {
         settingsModal.style.display = 'block';
    });
});

settingsCloseBtn.addEventListener('click', () => {
    settingsModal.style.display = 'none';
});

saveSettingsBtn.addEventListener('click', saveSettings);

// Apply dark mode immediately on toggle for better UX
darkModeToggle.addEventListener('change', () => {
    applyDarkMode(darkModeToggle.checked);
});


// --- Initial Load ---
loadSubforums();
loadSchedule();
loadSettings(); // Load settings and models on page load

});