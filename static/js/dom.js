// This file will centralize DOM element references.

export const subforumNav = document.getElementById('subforum-nav');
export const subforumList = document.getElementById('subforum-list');
export const addSubforumBtn = document.getElementById('add-subforum-btn');
export const newSubforumNameInput = document.getElementById('new-subforum-name');

export const topicListSection = document.getElementById('topic-list-section');
export const currentSubforumName = document.getElementById('current-subforum-name');
export const topicList = document.getElementById('topic-list');
export const addTopicBtn = document.getElementById('add-topic-btn');
export const newTopicTitleInput = document.getElementById('new-topic-title');
export const newTopicContentInput = document.getElementById('new-topic-content');
export const backToSubforumsBtn = document.getElementById('back-to-subforums-btn');

export const topicViewSection = document.getElementById('topic-view-section');
export const currentTopicTitle = document.getElementById('current-topic-title');
export const postList = document.getElementById('post-list');
export const backToTopicsBtn = document.getElementById('back-to-topics-btn');

export const replyFormContainer = document.getElementById('reply-form-container');
export const replyToPostIdSpan = document.getElementById('reply-to-post-id');
export const replyContentInput = document.getElementById('reply-content');
export const submitReplyBtn = document.getElementById('submit-reply-btn');
export const cancelReplyBtn = document.getElementById('cancel-reply-btn');

// Schedule Elements
export const scheduleDisplay = document.getElementById('schedule-display'); // For next schedule text
export const editScheduleBtn = document.getElementById('edit-schedule-btn');
export const scheduleModal = document.getElementById('schedule-modal');
export const scheduleCloseBtn = scheduleModal ? scheduleModal.querySelector('.close-btn') : null; // Specific close button
export const scheduleListContainer = document.getElementById('schedule-list-container');
export const addScheduleRowBtn = document.getElementById('add-schedule-row-btn');
export const saveSchedulesBtn = document.getElementById('save-schedules-btn'); // Renamed save button
export const scheduleError = document.getElementById('schedule-error');
export const statusIndicatorContainer = document.getElementById('processing-status-indicator-container');
export const statusDot = document.getElementById('processing-status-dot');

// Settings Modal Elements
export const settingsBtn = document.getElementById('settings-btn');
// Settings Modal Elements (Now Page Elements)
export const settingsPageSection = document.getElementById('settings-page-section');
export const settingsPageContent = document.getElementById('settings-page-content');
export const exitSettingsBtn = document.getElementById('exit-settings-btn');
// Settings elements will be created dynamically inside settingsPageContent

// Queue Page Elements
export const queueBtn = document.getElementById('queue-btn');
export const queuePageSection = document.getElementById('queue-page-section');
export const queuePageContent = document.getElementById('queue-page-content');
export const exitQueueBtn = document.getElementById('exit-queue-btn');

// Full Prompt Modal Elements
export const fullPromptModal = document.getElementById('full-prompt-modal');
export const fullPromptContent = document.getElementById('full-prompt-content');
export const fullPromptClose = fullPromptModal ? fullPromptModal.querySelector('.close-btn') : null;