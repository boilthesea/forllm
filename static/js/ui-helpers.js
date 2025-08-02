/**
 * Initializes a Tom Select instance on a given HTML element.
 * Destroys any existing instance on the element before creating a new one.
 * @param {HTMLElement} element - The <select> element to initialize.
 * @param {object} [options={}] - Optional Tom Select configuration.
 * @returns {TomSelect|null} The new TomSelect instance or null if the element is invalid.
 */
export function initializeTomSelect(element, options = {}) {
    if (!element || typeof element.nodeName === 'undefined') {
        console.warn(`TomSelect: Invalid element passed for initialization.`, element);
        return null;
    }

    // Destroy existing instance if it exists
    if (element.tomselect) {
        element.tomselect.destroy();
    }

    // Create a new instance
    return new TomSelect(element, options);
}