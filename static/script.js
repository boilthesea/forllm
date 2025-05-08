document.addEventListener('DOMContentLoaded', () => {
    // --- State Variables ---
    let currentSubforumId = null;
    let currentTopicId = null;
    let currentPosts = []; // Store posts for the current topic
    let newTopicEditor = null; // EasyMDE instance for new topics
    let replyEditor = null; // EasyMDE instance for replies
    let schedules = []; // Store loaded schedules
    // New day order and abbreviations for SMTWRFS
    const DAY_MAP = {
        'Sun': 'S', 'Mon': 'M', 'Tue': 'T', 'Wed': 'W', 'Thu': 'R', 'Fri': 'F', 'Sat': 'S'
    };
    const DAY_ORDER_ABBR = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']; // Keep original abbr for mapping and tooltips
    const DAY_ORDER_SINGLE = ['S', 'M', 'T', 'W', 'R', 'F', 'S']; // For display labels

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
    // Settings Modal Elements (Now Page Elements)
    const settingsPageSection = document.getElementById('settings-page-section');
    const settingsPageContent = document.getElementById('settings-page-content');
    const exitSettingsBtn = document.getElementById('exit-settings-btn');
    // Settings elements will be created dynamically inside settingsPageContent

    // Queue Page Elements
    const queueBtn = document.getElementById('queue-btn');
    const queuePageSection = document.getElementById('queue-page-section');
    const queuePageContent = document.getElementById('queue-page-content');
    const exitQueueBtn = document.getElementById('exit-queue-btn');

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

    // --- Queue Rendering Functions ---
    function renderQueueList(queueItems) {
        queuePageContent.innerHTML = ''; // Clear loading/previous content

        if (!Array.isArray(queueItems) || queueItems.length === 0) {
            queuePageContent.innerHTML = '<p>The processing queue is currently empty.</p>';
            return;
        }

        const list = document.createElement('ul');
        list.className = 'queue-list'; // Add class for potential styling

        queueItems.forEach(item => {
            const li = document.createElement('li');
            li.className = 'queue-item'; // Add class for potential styling

            // Example: Display basic info. Adjust based on actual data from backend.
            const postIdText = item.post_id ? `Post ID: ${item.post_id}` : 'N/A';
            const queuedAt = item.queued_at ? new Date(item.queued_at).toLocaleString() : 'Unknown time';
            const taskType = item.task_type || 'LLM Request'; // Example field

            li.innerHTML = `
                <strong>${taskType}</strong> for ${postIdText}<br>
                <span class="queue-meta">Queued: ${queuedAt}</span>
            `;
            // Add more details as needed based on backend response structure
            list.appendChild(li);
        });

        queuePageContent.appendChild(list);
    }

    // --- Queue Rendering Functions ---
    function renderQueueList(queueItems) {
        queuePageContent.innerHTML = ''; // Clear loading/previous content

        if (!Array.isArray(queueItems) || queueItems.length === 0) {
            queuePageContent.innerHTML = '<p>The processing queue is currently empty.</p>';
            return;
        }

        const list = document.createElement('ul');
        list.className = 'queue-list'; // Add class for potential styling

        queueItems.forEach(item => {
            const li = document.createElement('li');
            li.className = 'queue-item'; // Add class for potential styling

            // Example: Display basic info. Adjust based on actual data from backend.
            const postIdText = item.post_id ? `Post ID: ${item.post_id}` : 'N/A';
            const queuedAt = item.queued_at ? new Date(item.queued_at).toLocaleString() : 'Unknown time';
            const taskType = item.task_type || 'LLM Request'; // Example field

            li.innerHTML = `
                <strong>${taskType}</strong> for ${postIdText}<br>
                <span class="queue-meta">Queued: ${queuedAt}</span>
            `;
            // Add more details as needed based on backend response structure
            list.appendChild(li);
        });

        queuePageContent.appendChild(list);
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
        // Use DAY_ORDER_ABBR for value and checking, DAY_ORDER_SINGLE for label text
        DAY_ORDER_ABBR.forEach((dayAbbr, index) => {
            const daySingle = DAY_ORDER_SINGLE[index];
            const isChecked = activeDays.includes(dayAbbr); // Check against 'Mon', 'Tue', etc.
            const label = document.createElement('label');
            label.title = dayAbbr; // Tooltip shows 'Sun', 'Mon', etc.
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = dayAbbr; // Value stored remains 'Mon', 'Tue', etc.
            checkbox.checked = isChecked;
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(daySingle)); // Display text is 'S', 'M', 'T', etc.
            daysSelector.appendChild(label);
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

            // Format days from schedule_details (assuming comma-separated abbr like "Mon,Wed,Fri")
            let formattedDays = "Days?"; // Default if parsing fails
            if (nextScheduleInfo.schedule_details) {
                 try {
                     // Example parsing: "0-6 on Mon,Wed,Fri" -> extract "Mon,Wed,Fri"
                     const parts = nextScheduleInfo.schedule_details.split(' on ');
                     if (parts.length > 1) {
                         const daysStr = parts[1].trim();
                         const daysAbbr = daysStr.split(',').map(d => d.trim());
                         // Map abbreviations to single letters based on DAY_MAP
                         formattedDays = daysAbbr.map(abbr => DAY_MAP[abbr] || '?').join(' ');
                     } else {
                         // Fallback if format is unexpected
                         formattedDays = nextScheduleInfo.schedule_details; // Show original detail string
                     }
                 } catch (e) {
                     console.error("Error parsing schedule_details for days:", e);
                     formattedDays = nextScheduleInfo.schedule_details; // Show original on error
                 }
            }

            scheduleDisplay.textContent = `Next: ${formattedDate} at ${formattedTime} (${formattedDays})`;
            scheduleDisplay.title = `Full details: ${nextScheduleInfo.schedule_details}`; // Keep full details in title
        } else {
            scheduleDisplay.textContent = "No upcoming processing schedule.";
            scheduleDisplay.title = ""; // Clear title
        }
    }

    // --- Settings Page Rendering ---
    function renderSettingsPage() {
        // Check if content already exists to avoid duplication
        if (settingsPageContent.querySelector('#settings-form')) {
            return;
        }
        settingsPageContent.innerHTML = ''; // Clear previous content if any

        const form = document.createElement('form');
        form.id = 'settings-form';

        // Dark Mode
        const darkModeItem = document.createElement('div');
        darkModeItem.className = 'setting-item';
        darkModeItem.innerHTML = `
            <label for="dark-mode-toggle">Dark Mode:</label>
            <input type="checkbox" id="dark-mode-toggle">
        `;
        const darkModeToggleInput = darkModeItem.querySelector('#dark-mode-toggle');
        darkModeToggleInput.checked = currentSettings.darkMode === 'true';
        darkModeToggleInput.addEventListener('change', () => {
            applyDarkMode(darkModeToggleInput.checked);
        });
        form.appendChild(darkModeItem);

        // Model Select
        const modelSelectItem = document.createElement('div');
        modelSelectItem.className = 'setting-item';
        modelSelectItem.innerHTML = `
            <label for="model-select">Select LLM Model:</label>
            <select id="model-select">
                <option value="">Loading models...</option> <!-- Initial loading state -->
            </select>
        `;
        form.appendChild(modelSelectItem);

        // LLM Link Security
        const linkSecurityItem = document.createElement('div');
        linkSecurityItem.className = 'setting-item';
        linkSecurityItem.innerHTML = `
            <label for="llm-link-security-toggle">LLM Link Security:</label>
            <input type="checkbox" id="llm-link-security-toggle">
        `;
        const linkSecurityToggleInput = linkSecurityItem.querySelector('#llm-link-security-toggle');
        linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
        form.appendChild(linkSecurityItem);

        // Save Button
        const saveButton = document.createElement('button');
        saveButton.type = 'button'; // Prevent default form submission
        saveButton.id = 'save-settings-btn';
        saveButton.textContent = 'Save Settings';
        saveButton.addEventListener('click', saveSettings); // Add listener here
        form.appendChild(saveButton);

        // Error Message Area
        const errorP = document.createElement('p');
        errorP.id = 'settings-error';
        errorP.className = 'error-message';
        form.appendChild(errorP);

        settingsPageContent.appendChild(form);

        // Trigger model loading now that the select element exists
        loadOllamaModels();
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
        // console.log('applyDarkMode called with isDark =', isDark, '. Caller:', (new Error()).stack.split('\n')[2].trim()); // Logging removed
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        // The state of the actual checkbox input is handled by renderSettingsPage
        // when it creates/updates the settings UI.
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

    function renderModelOptions(modelSelectElement, models, selectedModel) {
        if (!modelSelectElement) {
            console.error("renderModelOptions called with no modelSelectElement");
            return;
        }
        modelSelectElement.innerHTML = '';
        if (!Array.isArray(models) || models.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No models found or error loading.';
            option.disabled = true;
            modelSelectElement.appendChild(option);
            return;
        }

        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            if (modelName === selectedModel) {
                option.selected = true;
            }
            modelSelectElement.appendChild(option);
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
            showSection('topic-list-section');
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
            showSection('topic-view-section');
            hideReplyForm();
        } catch (error) {
            // Error logged by apiRequest
        }
    }

    // --- Queue Loading Function ---
    async function loadQueueData() {
        if (!queuePageContent) return; // Ensure element exists

        queuePageContent.innerHTML = '<p>Loading queue...</p>'; // Show loading state

        try {
            // NOTE: Assumes a backend endpoint '/api/queue' exists and returns an array of queue items.
            const queueData = await apiRequest('/api/queue');
            renderQueueList(queueData);
        } catch (error) {
            console.error("Error loading queue data:", error);
            queuePageContent.innerHTML = `<p class="error-message">Failed to load queue: ${error.message}</p>`;
        }
    }

    // --- Queue Loading Function ---
    async function loadQueueData() {
        if (!queuePageContent) return; // Ensure element exists

        queuePageContent.innerHTML = '<p>Loading queue...</p>'; // Show loading state

        try {
            const queueData = await apiRequest('/api/queue'); // Fetch from the new endpoint
            renderQueueList(queueData);
        } catch (error) {
            console.error("Error loading queue data:", error);
            queuePageContent.innerHTML = `<p class="error-message">Failed to load queue: ${error.message}</p>`;
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
                llmLinkSecurity: settings.llmLinkSecurity === 'true' ? 'true' : 'false' // Default to true if missing
            };
             if (settings.llmLinkSecurity === undefined) {
                 currentSettings.llmLinkSecurity = 'true'; // Explicitly default if undefined
            }
            // console.log('loadSettings: currentSettings loaded:', JSON.stringify(currentSettings)); // Logging removed
            applyDarkMode(currentSettings.darkMode === 'true'); // Apply dark mode immediately

            // Update UI elements if they exist (they might be created later by renderSettingsPage)
            const darkModeToggleInput = settingsPageContent.querySelector('#dark-mode-toggle');
            if (darkModeToggleInput) {
                darkModeToggleInput.checked = currentSettings.darkMode === 'true';
            }
            const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
            if (linkSecurityToggleInput) {
                 linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
            }

            // Trigger model loading (it will handle populating the select later)
            // loadOllamaModels() will be called by renderSettingsPage when the elements are ready
        } catch (error) {
            console.error("Error loading settings:", error);
            // Apply default settings on error
            currentSettings = { darkMode: 'false', selectedModel: null, llmLinkSecurity: 'true' };
            // console.log('loadSettings: Error loading settings, applying default darkMode=false. Error:', error); // Logging removed
            applyDarkMode(false);
            // Still try to load models even if settings load failed
            // loadOllamaModels() will be called by renderSettingsPage
        }
    }

    async function loadOllamaModels() {
        const modelSelectElement = settingsPageContent.querySelector('#model-select');
        const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

        // Ensure the select element exists before proceeding
        if (!modelSelectElement) {
             console.warn("Model select element not found yet in settings page.");
             return;
        }

        // Set loading state
        modelSelectElement.innerHTML = '<option value="">Loading models...</option>';
        modelSelectElement.disabled = true;
        if(settingsErrorElement) settingsErrorElement.textContent = ""; // Clear previous errors

        try {
            const modelsResult = await apiRequest('/api/ollama/models');
            let models = [];
            if (Array.isArray(modelsResult)) {
                models = modelsResult;
            } else if (modelsResult && Array.isArray(modelsResult.models)) {
                // Handle case where backend returns default list due to connection issue
                models = modelsResult.models;
                console.warn("Ollama connection issue reported by backend, using default model list:", modelsResult.error);
                 if(settingsErrorElement) settingsErrorElement.textContent = "Warning: Ollama connection issue. Displaying default models.";
            } else {
                 // Handle unexpected format or error from backend
                 console.error("Unexpected format or error fetching Ollama models:", modelsResult);
                 models = currentSettings.selectedModel ? [currentSettings.selectedModel] : []; // Use current if available, else empty
                 if(settingsErrorElement) settingsErrorElement.textContent = "Error fetching models. Using current selection if available.";
            }
            renderModelOptions(modelSelectElement, models, currentSettings.selectedModel); // Populate the select
        } catch (error) {
            console.error("Error fetching Ollama models:", error);
            // Handle fetch error
            renderModelOptions(modelSelectElement, currentSettings.selectedModel ? [currentSettings.selectedModel] : [], currentSettings.selectedModel); // Use current if available
            if(settingsErrorElement) settingsErrorElement.textContent = `Could not fetch models: ${error.message}`;
        } finally {
             if (modelSelectElement) modelSelectElement.disabled = false; // Re-enable select even on error
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
        // Get elements from within the settings page content
        const darkModeToggleInput = settingsPageContent.querySelector('#dark-mode-toggle');
        const modelSelectElement = settingsPageContent.querySelector('#model-select');
        const linkSecurityToggleInput = settingsPageContent.querySelector('#llm-link-security-toggle');
        const saveButton = settingsPageContent.querySelector('#save-settings-btn');
        const settingsErrorElement = settingsPageContent.querySelector('#settings-error');

        if (!darkModeToggleInput || !modelSelectElement || !linkSecurityToggleInput || !saveButton || !settingsErrorElement) {
            console.error("Settings elements not found for saving.");
            alert("An error occurred. Could not save settings.");
            return;
        }

        const newDarkMode = darkModeToggleInput.checked;
        const newSelectedModel = modelSelectElement.value;
        const newLlmLinkSecurity = linkSecurityToggleInput.checked;

        settingsErrorElement.textContent = ""; // Clear previous errors

        if (!newSelectedModel) {
            settingsErrorElement.textContent = "Please select a model.";
            modelSelectElement.focus();
            return;
        }

        const settingsToSave = {
            darkMode: newDarkMode.toString(),
            selectedModel: newSelectedModel,
            llmLinkSecurity: newLlmLinkSecurity.toString()
        };

        saveButton.disabled = true;
        saveButton.textContent = 'Saving...';

        try {
            // Use PUT request to update settings
            const updatedSettings = await apiRequest('/api/settings', 'PUT', settingsToSave);

            // Update local state immediately based on what was sent,
            // assuming the backend confirms or handles potential discrepancies.
            currentSettings.darkMode = settingsToSave.darkMode;
            currentSettings.selectedModel = settingsToSave.selectedModel;
            currentSettings.llmLinkSecurity = settingsToSave.llmLinkSecurity;

            // Update UI (redundant if page isn't re-rendered, but good practice)
            applyDarkMode(currentSettings.darkMode === 'true');
            darkModeToggleInput.checked = currentSettings.darkMode === 'true';
            linkSecurityToggleInput.checked = currentSettings.llmLinkSecurity === 'true';
            // Re-render model options to ensure the saved one is selected
            // (though it should already be selected from the user's choice)
            if (modelSelectElement) {
                renderModelOptions(
                    modelSelectElement,
                    Array.from(modelSelectElement.options).map(opt => opt.value).filter(value => value !== ""), // Exclude "Loading..." or error options
                    currentSettings.selectedModel
                );
            }

            // Optionally provide feedback to the user
            // settingsErrorElement.textContent = "Settings saved successfully!";
            // setTimeout(() => { settingsErrorElement.textContent = ""; }, 3000);

            // Decide whether to close the settings page or not. Let's keep it open.
            // showSection(lastVisibleSectionId);

        } catch (error) {
            settingsErrorElement.textContent = `Error saving settings: ${error.message}`;
            console.error("Error saving settings:", error);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = 'Save Settings';
        }
    }

    // --- UI Navigation ---
    let lastVisibleSectionId = 'topic-list-section'; // Keep track of the last main view

    function showSection(sectionIdToShow) {
        // Always keep the sidebar visible
        subforumNav.style.display = 'flex'; // Use flex as defined in CSS

        // Hide all main content sections first
        topicListSection.style.display = 'none';
        topicViewSection.style.display = 'none';
        settingsPageSection.style.display = 'none';
        queuePageSection.style.display = 'none';

        // Show the requested section
        const sectionElement = document.getElementById(sectionIdToShow);
        if (sectionElement) {
            sectionElement.style.display = 'block'; // Or 'flex' if it uses flex layout internally
            // Update last visible section only if it's a main content view
            if (['topic-list-section', 'topic-view-section'].includes(sectionIdToShow)) {
                 lastVisibleSectionId = sectionIdToShow;
            }
        } else if (sectionIdToShow === 'subforum-list-only') {
             // Special case: only show sidebar, hide all right-pane sections
             // This might be triggered by back-to-subforums button
        } else {
            console.warn(`Section with ID ${sectionIdToShow} not found.`);
            // Optionally default to showing the topic list or subforum list
             topicListSection.style.display = 'block';
             lastVisibleSectionId = 'topic-list-section';
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
        showSection('subforum-list-only'); // Hide right pane sections
    });

    backToTopicsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentSubforumId) {
            const subforumLink = subforumList.querySelector(`a[data-subforum-id="${currentSubforumId}"]`);
            const subforumName = subforumLink ? subforumLink.dataset.subforumName : 'Selected Subforum';
            loadTopics(currentSubforumId, subforumName); // This calls showSection('topic-list')
        } else {
            showSection('subforum-list-only'); // Go back to just the sidebar view
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
        // console.log('Settings button clicked. Attempting to call renderSettingsPage.'); // Logging removed
        try {
            renderSettingsPage(); // Ensure content is created
            // console.log('renderSettingsPage call successful.'); // Logging removed
        } catch (e) {
            // console.error('Error calling renderSettingsPage from settingsBtn click:', e); // Logging removed
            // If an error still occurs, it will appear in the console naturally.
        }
        showSection('settings-page-section');
    });

    exitSettingsBtn.addEventListener('click', () => {
        showSection(lastVisibleSectionId); // Go back to the last main view
    });

    queueBtn.addEventListener('click', () => {
        showSection('queue-page-section');
        loadQueueData(); // Load data when section is shown
    });

    exitQueueBtn.addEventListener('click', () => {
        showSection(lastVisibleSectionId); // Go back to the last main view
    });


// Event listeners for dynamically created elements (save button, dark mode toggle)
// are now added within renderSettingsPage()

    // Close modals if clicking outside of them
    window.addEventListener('click', (event) => {
        if (event.target == scheduleModal) {
            scheduleModal.style.display = 'none';
        }
        // Remove modal closing logic
        // if (event.target == settingsModal) {
        //     settingsModal.style.display = 'none';
        // }
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

    initialLoad();

});