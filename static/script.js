document.addEventListener('DOMContentLoaded', () => {
    // --- State Variables ---
    let currentSubforumId = null;
    let currentTopicId = null;
    let currentPosts = []; // Store posts for the current topic
    let newTopicEditor = null; // EasyMDE instance for new topics
    let replyEditor = null; // EasyMDE instance for replies
    let schedules = []; // Store loaded schedules
    const DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']; // For consistent day ordering

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

    // Schedule Elements
    const scheduleDisplay = document.getElementById('schedule-display'); // For next schedule text
    const editScheduleBtn = document.getElementById('edit-schedule-btn');
    const scheduleModal = document.getElementById('schedule-modal');
    const scheduleCloseBtn = scheduleModal.querySelector('.close-btn'); // Specific close button
    const scheduleListContainer = document.getElementById('schedule-list-container');
    const addScheduleRowBtn = document.getElementById('add-schedule-row-btn');
    const saveSchedulesBtn = document.getElementById('save-schedules-btn'); // Renamed save button
    const scheduleError = document.getElementById('schedule-error');
    const statusIndicatorContainer = document.getElementById('processing-status-indicator-container');
    const statusDot = document.getElementById('processing-status-dot');

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
        selectedModel: null,
        llmLinkSecurity: 'true' // Added default
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
            if (response.status === 204 || response.status === 202) {
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error('Fetch Error:', error);
            alert(`An error occurred: ${error.message}`);
            throw error;
        }
    }

    // --- Rendering Functions ---

    function renderSubforumList(subforums) {
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

    function renderTopicList(topics) {
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

    function renderPosts(posts) {
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

    // --- Schedule Rendering Functions ---
    function renderSchedules(scheduleData) {
        schedules = scheduleData || []; // Update global schedules state
        scheduleListContainer.innerHTML = ''; // Clear existing rows
        if (!Array.isArray(schedules) || schedules.length === 0) {
            scheduleListContainer.innerHTML = '<p>No schedules configured. Click "+" to add one.</p>';
        } else {
            schedules.forEach(schedule => {
                const scheduleRow = createScheduleRowElement(schedule);
                scheduleListContainer.appendChild(scheduleRow);
            });
        }
        // Add event listeners to newly created delete buttons
        scheduleListContainer.querySelectorAll('.delete-schedule-btn').forEach(btn => {
            btn.addEventListener('click', handleDeleteSchedule);
        });
    }

    function createScheduleRowElement(schedule = {}) {
        const scheduleId = schedule.id || null; // Use null for new rows
        const startHour = schedule.start_hour !== undefined ? schedule.start_hour : 0;
        const endHour = schedule.end_hour !== undefined ? schedule.end_hour : 6;
        const enabled = schedule.enabled !== undefined ? schedule.enabled : false; // Default new schedules to disabled
        const activeDays = schedule.days_active ? schedule.days_active.split(',') : []; // Default to no days if new

        const row = document.createElement('div');
        row.className = 'schedule-row';
        if (scheduleId) {
            row.dataset.scheduleId = scheduleId;
        }

        const timeInputContainer = document.createElement('div');
        timeInputContainer.className = 'time-inputs';
        timeInputContainer.innerHTML = `
            <input type="number" class="schedule-start-hour" min="0" max="23" value="${startHour}" title="Start Hour (0-23)">
            <span>to</span>
            <input type="number" class="schedule-end-hour" min="0" max="23" value="${endHour}" title="End Hour (0-23)">
        `;

        const daysSelector = document.createElement('div');
        daysSelector.className = 'days-selector';
        DAY_ORDER.forEach(day => {
            const isChecked = activeDays.includes(day);
            daysSelector.innerHTML += `
                <label title="${day}">
                    <input type="checkbox" value="${day}" ${isChecked ? 'checked' : ''}>${day.substring(0,1)}
                </label>
            `;
        });

        const toggleLabel = document.createElement('label');
        toggleLabel.className = 'toggle-switch';
        toggleLabel.title = enabled ? 'Schedule Enabled' : 'Schedule Disabled';
        toggleLabel.innerHTML = `
            <input type="checkbox" class="schedule-enabled" ${enabled ? 'checked' : ''}>
            <span class="slider round"></span>
        `;
        toggleLabel.querySelector('.schedule-enabled').addEventListener('change', (e) => {
             toggleLabel.title = e.target.checked ? 'Schedule Enabled' : 'Schedule Disabled';
        });

        const deleteButton = document.createElement('button');
        deleteButton.className = 'delete-schedule-btn';
        deleteButton.textContent = 'Delete';
        deleteButton.title = 'Delete this schedule';
        if (!scheduleId) {
             deleteButton.textContent = 'Remove';
             deleteButton.title = 'Remove this new schedule row';
        }

        row.appendChild(timeInputContainer);
        row.appendChild(daysSelector);
        row.appendChild(toggleLabel);
        row.appendChild(deleteButton);
        return row;
    }

    function renderNextSchedule(nextScheduleInfo) {
         if (nextScheduleInfo && nextScheduleInfo.next_start_iso) {
             const nextStart = new Date(nextScheduleInfo.next_start_iso);
             const formattedDate = nextStart.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
             const formattedTime = nextStart.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: true });
             scheduleDisplay.textContent = `Next: ${formattedDate} at ${formattedTime} (${nextScheduleInfo.schedule_details})`;
         } else {
             scheduleDisplay.textContent = "No upcoming processing schedule.";
         }
     }

     function renderCurrentStatus(statusInfo) {
         const isActive = statusInfo && statusInfo.active;
         statusDot.classList.remove('status-active', 'status-inactive', 'status-loading', 'status-error');

         if (isActive === true) {
             statusDot.classList.add('status-active');
             statusIndicatorContainer.title = 'Schedule active';
         } else if (isActive === false) {
             statusDot.classList.add('status-inactive');
             statusIndicatorContainer.title = 'No schedule active';
         } else {
             statusDot.classList.add('status-error');
             statusIndicatorContainer.title = 'Schedule status: Unknown';
         }
     }

    // --- Dark Mode ---
    function applyDarkMode(isDark) {
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        darkModeToggle.checked = isDark;
    }

    // --- Link Security Popup ---
    function showLinkWarningPopup(linkUrl, linkText) {
        const existingPopup = document.getElementById('link-warning-popup');
        if (existingPopup) {
            existingPopup.remove();
        }

        const popup = document.createElement('div');
        popup.id = 'link-warning-popup';
        popup.className = 'modal';
        popup.style.display = 'block';

        const popupContent = document.createElement('div');
        popupContent.className = 'modal-content link-warning-content';

        const closeBtnEl = document.createElement('span');
        closeBtnEl.className = 'close-btn';
        closeBtnEl.innerHTML = '&times;';
        closeBtnEl.onclick = () => popup.remove();

        const title = document.createElement('h4');
        title.textContent = 'Link Security Warning';

        const text = document.createElement('p');
        text.innerHTML = `You clicked on a link generated by an LLM: <br>
                          <strong>Text:</strong> ${linkText}<br>
                          <strong>URL:</strong> <span class="link-url">${linkUrl}</span>`;

        const warning = document.createElement('p');
        warning.innerHTML = `<strong>Warning:</strong> LLM data can be outdated or inaccurate. This link might lead to an unexpected or potentially harmful website. Verify the destination before proceeding.`;
        warning.style.color = 'orange';

        const buttonContainer = document.createElement('div');
        buttonContainer.style.marginTop = '1rem';
        buttonContainer.style.textAlign = 'right';

        const proceedBtn = document.createElement('button');
        proceedBtn.textContent = 'Proceed to Link';
        proceedBtn.onclick = () => {
            window.open(linkUrl, '_blank', 'noopener noreferrer');
            popup.remove();
        };

        const cancelBtnEl = document.createElement('button');
        cancelBtnEl.textContent = 'Cancel';
        cancelBtnEl.style.marginLeft = '0.5rem';
        cancelBtnEl.onclick = () => popup.remove();

        buttonContainer.appendChild(cancelBtnEl);
        buttonContainer.appendChild(proceedBtn);
        popupContent.appendChild(closeBtnEl);
        popupContent.appendChild(title);
        popupContent.appendChild(text);
        popupContent.appendChild(warning);
        popupContent.appendChild(buttonContainer);
        popup.appendChild(popupContent);
        document.body.appendChild(popup);

        popup.addEventListener('click', (event) => {
            if (event.target === popup) {
                popup.remove();
            }
        });
    }

    function renderModelOptions(models, selectedModel) {
        modelSelect.innerHTML = '';
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
            showSection('subforum-nav');
        } catch (error) {
            // Error logged by apiRequest
        }
    }

    async function loadTopics(subforumId, subforumName) {
        currentSubforumId = subforumId;
        currentTopicId = null;
        try {
            const topics = await apiRequest(`/api/subforums/${subforumId}/topics`);
            currentSubforumName.textContent = subforumName;
            renderTopicList(topics);
            showSection('topic-list');
        } catch (error) {
            // Error logged by apiRequest
        }
    }

     async function loadPosts(topicId, topicTitle) {
        currentTopicId = topicId;
        try {
            const posts = await apiRequest(`/api/topics/${topicId}/posts`);
            currentTopicTitle.textContent = topicTitle;
            renderPosts(posts);
            showSection('topic-view');
            hideReplyForm();
        } catch (error) {
            // Error logged by apiRequest
        }
    }

    async function loadSchedules() {
        try {
            const scheduleData = await apiRequest('/api/schedules');
            renderSchedules(scheduleData);
        } catch (error) {
            scheduleError.textContent = "Error loading schedules.";
            console.error("Error in loadSchedules:", error);
            renderSchedules([]);
        }
    }

     async function loadNextSchedule() {
         try {
             const nextInfo = await apiRequest('/api/schedule/next');
             renderNextSchedule(nextInfo);
         } catch (error) {
             scheduleDisplay.textContent = "Error loading next schedule info.";
             console.error("Error loading next schedule:", error);
         }
     }

     async function loadCurrentStatus() {
         try {
             const statusInfo = await apiRequest('/api/schedule/status');
             renderCurrentStatus(statusInfo);
         } catch (error) {
             renderCurrentStatus(null); // Indicate error state
             console.error("Error loading current status:", error);
         }
     }

    async function loadSettings() {
        try {
            const settings = await apiRequest('/api/settings');
            currentSettings = {
                darkMode: settings.darkMode === 'true' ? 'true' : 'false',
                selectedModel: settings.selectedModel || null,
                llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false'
            };
            if (settings.llmLinkSecurity === undefined) {
                 currentSettings.llmLinkSecurity = 'true';
            }

            applyDarkMode(currentSettings.darkMode === 'true');
            const llmSecurityToggle = document.getElementById('llm-link-security-toggle');
            if (llmSecurityToggle) {
                 llmSecurityToggle.checked = currentSettings.llmLinkSecurity === 'true';
            }
            await loadOllamaModels();
        } catch (error) {
            console.error("Error loading settings:", error);
            applyDarkMode(false);
            await loadOllamaModels();
        }
    }

    async function loadOllamaModels() {
        try {
            const modelsResult = await apiRequest('/api/ollama/models');
            let models = [];
            if (Array.isArray(modelsResult)) {
                models = modelsResult;
            } else if (modelsResult && Array.isArray(modelsResult.models)) {
                models = modelsResult.models;
                console.warn("Ollama connection issue, using default model list:", modelsResult.error);
            } else {
                 console.error("Unexpected format for Ollama models:", modelsResult);
                 models = [currentSettings.selectedModel || 'default'];
            }
            renderModelOptions(models, currentSettings.selectedModel);
        } catch (error) {
            console.error("Error fetching Ollama models:", error);
            renderModelOptions([currentSettings.selectedModel || 'default'], currentSettings.selectedModel);
            settingsError.textContent = "Could not fetch models from Ollama.";
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

    async function addTopic() {
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

    function showReplyForm(postId) {
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

    function hideReplyForm() {
        replyFormContainer.style.display = 'none';
        replyToPostIdSpan.textContent = '';
        if (replyEditor) {
            replyEditor.value('');
        } else {
            replyContentInput.value = '';
        }
    }

    async function submitReply() {
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

    async function requestLlm(postId) {
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

    // --- Schedule Actions ---
    function addScheduleRow() {
        const newRow = createScheduleRowElement();
        scheduleListContainer.appendChild(newRow);
        newRow.querySelector('.delete-schedule-btn').addEventListener('click', handleDeleteSchedule);
         // Check if placeholder needs to be removed
        const placeholder = scheduleListContainer.querySelector('p');
        if (placeholder && placeholder.textContent.startsWith('No schedules configured')) {
            placeholder.remove();
        }
    }

    async function handleDeleteSchedule(event) {
        const rowToDelete = event.target.closest('.schedule-row');
        const scheduleId = rowToDelete.dataset.scheduleId;

        if (scheduleId) {
            if (!confirm(`Are you sure you want to delete schedule ${scheduleId}? This cannot be undone.`)) {
                return;
            }
            try {
                await apiRequest(`/api/schedules/${scheduleId}`, 'DELETE');
                rowToDelete.remove();
                 if (!scheduleListContainer.querySelector('.schedule-row')) {
                    scheduleListContainer.innerHTML = '<p>No schedules configured. Click "+" to add one.</p>';
                 }
            } catch (error) {
                scheduleError.textContent = `Error deleting schedule: ${error.message}`;
            }
        } else {
            rowToDelete.remove();
             if (!scheduleListContainer.querySelector('.schedule-row')) {
                scheduleListContainer.innerHTML = '<p>No schedules configured. Click "+" to add one.</p>';
             }
        }
    }

     async function saveSchedules() {
        scheduleError.textContent = "";
        const scheduleRows = scheduleListContainer.querySelectorAll('.schedule-row');
        const promises = [];
        let validationError = false;

        if (scheduleRows.length === 0) { // No schedules to save
            scheduleModal.style.display = 'none'; // Just close modal
            await loadSchedules(); // Ensure UI reflects empty state if needed
            await loadCurrentStatus();
            await loadNextSchedule();
            return;
        }

        scheduleRows.forEach((row, index) => {
            const scheduleId = row.dataset.scheduleId || null;
            const startHourInput = row.querySelector('.schedule-start-hour');
            const endHourInput = row.querySelector('.schedule-end-hour');
            const enabledCheckbox = row.querySelector('.schedule-enabled');
            const dayCheckboxes = row.querySelectorAll('.days-selector input[type="checkbox"]:checked');

            const startHour = parseInt(startHourInput.value, 10);
            const endHour = parseInt(endHourInput.value, 10);
            const enabled = enabledCheckbox.checked;
            const daysActive = Array.from(dayCheckboxes).map(cb => cb.value);

            startHourInput.style.borderColor = '';
            endHourInput.style.borderColor = '';
            row.querySelector('.days-selector').style.border = '';

            if (isNaN(startHour) || startHour < 0 || startHour > 23 ||
                isNaN(endHour) || endHour < 0 || endHour > 23) {
                scheduleError.textContent += `Invalid hours in row ${index + 1}. Must be 0-23. `;
                validationError = true;
                startHourInput.style.borderColor = 'red';
                endHourInput.style.borderColor = 'red';
            }
            if (daysActive.length === 0) {
                 scheduleError.textContent += `Select at least one day in row ${index + 1}. `;
                 validationError = true;
                 row.querySelector('.days-selector').style.border = '1px solid red';
            }

            if (!validationError) {
                const scheduleData = {
                    start_hour: startHour,
                    end_hour: endHour,
                    days_active: daysActive,
                    enabled: enabled
                };
                if (scheduleId) {
                    promises.push(apiRequest(`/api/schedules/${scheduleId}`, 'PUT', scheduleData));
                } else {
                    promises.push(apiRequest('/api/schedules', 'POST', scheduleData));
                }
            }
        });

        if (validationError) return;
        if (promises.length === 0) {
             // This case might happen if all rows had validation errors but were not new,
             // or if there were no actual changes to existing rows.
             // For simplicity, if no promises, assume no valid changes to save.
             // scheduleError.textContent = "No valid changes to save.";
             return;
        }

        try {
            saveSchedulesBtn.disabled = true;
            saveSchedulesBtn.textContent = 'Saving...';
            await Promise.all(promises);
            await loadSchedules();
            await loadCurrentStatus();
            await loadNextSchedule();
            scheduleModal.style.display = 'none';
        } catch (error) {
            scheduleError.textContent = `Error saving schedules: ${error.message}`;
            console.error("Error saving schedules:", error);
        } finally {
             saveSchedulesBtn.disabled = false;
             saveSchedulesBtn.textContent = 'Save All Schedules';
        }
    }

    // --- Settings Actions ---
    async function saveSettings() {
        const newDarkMode = darkModeToggle.checked;
        const newSelectedModel = modelSelect.value;
        const llmSecurityToggle = document.getElementById('llm-link-security-toggle');
        const newLlmLinkSecurity = llmSecurityToggle ? llmSecurityToggle.checked : true;

        settingsError.textContent = "";

        if (!newSelectedModel) {
            settingsError.textContent = "Please select a model.";
            return;
        }

        const settingsToSave = {
            darkMode: newDarkMode.toString(),
            selectedModel: newSelectedModel,
            llmLinkSecurity: newLlmLinkSecurity.toString()
        };

        try {
            const updatedSettings = await apiRequest('/api/settings', 'PUT', settingsToSave);
            if (updatedSettings) {
                currentSettings = updatedSettings;
                applyDarkMode(currentSettings.darkMode === 'true');
                 if (llmSecurityToggle) {
                    llmSecurityToggle.checked = currentSettings.llmLinkSecurity === 'true';
                 }
                renderModelOptions(
                    Array.from(modelSelect.options).map(opt => opt.value),
                    currentSettings.selectedModel
                );
                settingsModal.style.display = 'none';
            } else {
                 settingsError.textContent = "Failed to save settings. Server response was empty.";
            }
        } catch (error) {
            settingsError.textContent = `Error saving settings: ${error.message}`;
        }
    }

    // --- UI Navigation ---
    function showSection(section) {
        subforumNav.style.display = 'none';
        topicListSection.style.display = 'none';
        topicViewSection.style.display = 'none';

        if (section === 'subforum-nav') {
            subforumNav.style.display = 'block';
        } else if (section === 'topic-list') {
            subforumNav.style.display = 'block';
            topicListSection.style.display = 'block';
        } else if (section === 'topic-view') {
            subforumNav.style.display = 'block';
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
            const subforumLink = subforumList.querySelector(`a[data-subforum-id="${currentSubforumId}"]`);
            const subforumName = subforumLink ? subforumLink.dataset.subforumName : 'Selected Subforum';
            loadTopics(currentSubforumId, subforumName);
        } else {
            showSection('subforum-nav');
        }
    });

    // Schedule Modal Listeners
    editScheduleBtn.addEventListener('click', async () => {
        scheduleError.textContent = "";
        statusDot.classList.remove('status-error'); // Clear potential error state on dot
        statusDot.classList.add('status-loading');
        statusIndicatorContainer.title = 'Schedule status: Loading...';
        await loadSchedules(); // Load current schedules into modal before showing
        scheduleModal.style.display = 'block';
    });

    scheduleCloseBtn.addEventListener('click', () => {
        scheduleModal.style.display = 'none';
    });

    addScheduleRowBtn.addEventListener('click', addScheduleRow);
    saveSchedulesBtn.addEventListener('click', saveSchedules);

    // Settings Modal Listeners
    settingsBtn.addEventListener('click', () => {
        settingsError.textContent = "";
        loadOllamaModels().then(() => {
             settingsModal.style.display = 'block';
        });
    });

    settingsCloseBtn.addEventListener('click', () => {
        settingsModal.style.display = 'none';
    });

    saveSettingsBtn.addEventListener('click', saveSettings);

    darkModeToggle.addEventListener('change', () => {
        applyDarkMode(darkModeToggle.checked);
    });

    // Close modals if clicking outside of them
    window.addEventListener('click', (event) => {
        if (event.target == scheduleModal) {
            scheduleModal.style.display = 'none';
        }
        if (event.target == settingsModal) {
            settingsModal.style.display = 'none';
        }
    });

    // Link Interception
    postList.addEventListener('click', (event) => {
        const link = event.target.closest('a');
        if (link && link.classList.contains('llm-link')) {
            if (currentSettings.llmLinkSecurity === 'true') {
                event.preventDefault();
                const url = link.href;
                const text = link.textContent;
                showLinkWarningPopup(url, text);
            }
        }
    });

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

    // --- Initial Load & Periodic Updates ---
    function initialLoad() {
        loadSubforums();
        loadSettings(); // Loads settings, then models
        loadCurrentStatus();
        loadNextSchedule();
        setInterval(loadCurrentStatus, 30000); // Update status every 30 seconds
        setInterval(loadNextSchedule, 30000); // Update next schedule every 30 seconds
    }

    initialLoad();

});