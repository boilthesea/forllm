import { openThemeCreator } from './ui.js';

/**
 * Initializes the theme creator by fetching CSS variables and populating the modal.
 */
export function initThemeCreator() {
    // This function will be called to open and set up the theme creator.
    // For now, we'll just open the modal. The rest of the logic will be added.
    openThemeCreator();
    
    // Find the active theme class on the body
    const bodyClass = document.body.className.match(/theme-[\w-]+/);
    if (!bodyClass) {
        console.error("No active theme found on body. Cannot initialize theme creator.");
        return;
    }
    const themeClassName = `.${bodyClass[0]}`;

    // Get the variables from the stylesheet
    const themeVariables = getCssVariablesForTheme(themeClassName);
    
    // Populate the modal with these variables
    populateThemeCreator(themeVariables);
}

/**
 * Finds the stylesheet that contains the theme rules and extracts the CSS variables.
 * @param {string} themeClassName - The class name of the theme to look for (e.g., '.theme-silvery').
 * @returns {Map<string, string>} A map of CSS variable names to their values.
 */
function getCssVariablesForTheme(themeClassName) {
    const variables = new Map();
    const styleSheets = Array.from(document.styleSheets);

    for (const sheet of styleSheets) {
        try {
            // Check if the sheet is accessible before trying to access its rules
            if (!sheet.cssRules) {
                continue;
            }
            const rules = Array.from(sheet.cssRules);
            for (const rule of rules) {
                // Check if the rule's selector matches our theme class
                if (rule.selectorText && rule.selectorText.includes(themeClassName) && rule.style) {
                    const style = rule.style;
                    for (let i = 0; i < style.length; i++) {
                        const propName = style[i];
                        if (propName.startsWith('--')) {
                            variables.set(propName, style.getPropertyValue(propName).trim());
                        }
                    }
                    // Found the theme, no need to search other stylesheets
                    return variables;
                }
            }
        } catch (e) {
            // This will catch SecurityError for cross-origin stylesheets
            if (e instanceof DOMException && e.name === 'SecurityError') {
                console.warn(`SecurityError: Could not access rules from cross-origin stylesheet: ${sheet.href}`);
            } else {
                console.warn(`Could not access rules from stylesheet: ${sheet.href}`, e);
            }
        }
    }
    return variables;
}

/**
 * Populates the theme creator modal with controls for each CSS variable.
 * @param {Map<string, string>} variables - A map of CSS variables and their values.
 */
function populateThemeCreator(variables) {
    const contentArea = document.getElementById('theme-creator-content');
    if (!contentArea) {
        console.error("Theme creator content area not found.");
        return;
    }

    // Create a scrollable container for the variables
    let variablesHtml = '<div class="theme-variable-grid-scroll-container"><h4>Color Variables</h4><div class="theme-variable-grid">';
    for (const [key, value] of variables.entries()) {
        variablesHtml += `
            <div class="theme-variable-item">
                <label for="${key}">${key.replace('--', '')}</label>
                <div class="color-input-wrapper">
                    <input type="color" id="${key}" name="${key}" value="${value}" title="Click to use color picker">
                    <input type="text" value="${value}" class="color-text-input" spellcheck="false">
                </div>
            </div>
        `;
    }
    variablesHtml += '</div></div>';

    // Create the container for the sticky "In-Use Colors" palette
    let inUseColorsHtml = '<div id="in-use-colors-container"><h4>In-Use Colors</h4><div id="in-use-colors-palette"></div></div>';

    // Set the inner HTML
    contentArea.innerHTML = variablesHtml + inUseColorsHtml;

    const footerArea = document.getElementById('theme-creator-footer');
    if (footerArea) {
        footerArea.innerHTML = `
            <button id="revert-theme-btn" class="button-secondary">Revert Changes</button>
            <button id="export-theme-btn" class="button-primary">Export to Clipboard</button>
        `;
    }

    // Add event listeners for live updates and new buttons
    addLiveUpdateListeners();
    addFeatureButtonListeners();
    updateInUseColors();
}

/**
 * Adds event listeners to the color inputs to update the theme in real-time.
 */
function addLiveUpdateListeners() {
    const contentArea = document.getElementById('theme-creator-content');
    if (!contentArea) return;

    contentArea.addEventListener('input', (event) => {
        const target = event.target;
        if (target.matches('input[type="color"], .color-text-input')) {
            const wrapper = target.closest('.color-input-wrapper');
            if (!wrapper) return;

            const colorInput = wrapper.querySelector('input[type="color"]');
            const textInput = wrapper.querySelector('.color-text-input');
            const variableName = colorInput.name;
            const newValue = target.value;

            // Sync the color picker and text input
            if (target.type === 'text') {
                if (/^#[0-9a-f]{3,6}$/i.test(newValue)) {
                    colorInput.value = newValue;
                }
            } else {
                textInput.value = newValue;
            }
            
            // Update the CSS variable on the body's inline style for live preview
            document.body.style.setProperty(variableName, newValue);

            // Update the "In-Use" palette
            updateInUseColors();
        }
    });
}

/**
 * Adds event listeners for the Revert and Export buttons.
 */
function addFeatureButtonListeners() {
    const revertBtn = document.getElementById('revert-theme-btn');
    const exportBtn = document.getElementById('export-theme-btn');

    if (revertBtn) {
        revertBtn.addEventListener('click', () => {
            // Clear all inline styles from the body
            document.body.style.cssText = null;
            // Re-populate the creator to show the original stylesheet values
            initThemeCreator();
        });
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            let cssText = '.theme-custom {\n';
            const variables = getCssVariablesForTheme('.theme-silvery'); // Or get current values
            variables.forEach((value, key) => {
                const currentValue = document.body.style.getPropertyValue(key).trim() || value;
                cssText += `    ${key}: ${currentValue};\n`;
            });
            cssText += '}';
            
            navigator.clipboard.writeText(cssText).then(() => {
                alert('Custom theme CSS copied to clipboard!');
            }, () => {
                alert('Failed to copy CSS. Please copy manually from the console.');
                console.log(cssText);
            });
        });
    }
}

/**
 * Scans all current color values and populates the "In-Use Colors" palette.
 */
function updateInUseColors() {
    const palette = document.getElementById('in-use-colors-palette');
    if (!palette) return;

    const colorInputs = document.querySelectorAll('#theme-creator-content input[type="color"]');
    const uniqueColors = new Set();
    colorInputs.forEach(input => uniqueColors.add(input.value.toLowerCase()));

    palette.innerHTML = '';
    uniqueColors.forEach(color => {
        const swatch = document.createElement('div');
        swatch.className = 'color-swatch';
        swatch.style.backgroundColor = color;
        swatch.title = `Click to copy ${color}`;
        swatch.dataset.color = color;
        swatch.addEventListener('click', () => {
            navigator.clipboard.writeText(color).then(() => {
                // Maybe show a small "Copied!" tooltip
            });
        });
        palette.appendChild(swatch);
    });
}