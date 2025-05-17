// This file will manage the scheduling feature.

import { apiRequest } from './api.js';
import {
    scheduleListContainer,
    scheduleError,
    scheduleDisplay,
    statusDot,
    statusIndicatorContainer,
    scheduleModal, // Needed for saving schedules
    saveSchedulesBtn // Needed for saving schedules
} from './dom.js';

// --- State Variables ---
let schedules = []; // Store loaded schedules

// New day order and abbreviations for SMTWRFS
const DAY_MAP = {
    'Sun': 'S', 'Mon': 'M', 'Tue': 'T', 'Wed': 'W', 'Thu': 'R', 'Fri': 'F', 'Sat': 'S'
};
const DAY_ORDER_ABBR = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']; // Keep original abbr for mapping and tooltips
const DAY_ORDER_SINGLE = ['S', 'M', 'T', 'W', 'R', 'F', 'S']; // For display labels


// --- Schedule Rendering Functions ---
export function renderSchedules(scheduleData) {
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

export function renderNextSchedule(nextScheduleInfo) {
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

export function renderCurrentStatus(statusInfo) {
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

// --- Loading Functions ---
export async function loadSchedules() {
    try {
        const scheduleData = await apiRequest('/api/schedules');
        renderSchedules(scheduleData);
    } catch (error) {
        scheduleError.textContent = "Error loading schedules.";
        console.error("Error in loadSchedules:", error);
        renderSchedules([]);
    }
}

export async function loadNextSchedule() {
     try {
         const nextInfo = await apiRequest('/api/schedule/next');
         renderNextSchedule(nextInfo);
     } catch (error) {
         scheduleDisplay.textContent = "Error loading next schedule info.";
         console.error("Error loading next schedule:", error);
     }
}

export async function loadCurrentStatus() {
     try {
         const statusInfo = await apiRequest('/api/schedule/status');
         renderCurrentStatus(statusInfo);
     } catch (error) {
         renderCurrentStatus(null); // Indicate error state
         console.error("Error loading current status:", error);
     }
}

// --- Schedule Actions ---
export function addScheduleRow() {
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

export async function saveSchedules() {
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

// Export state variables if needed by other modules
export { schedules, DAY_MAP, DAY_ORDER_ABBR, DAY_ORDER_SINGLE };