// This file will contain API helper functions.

export async function apiRequest(url, method = 'GET', data = null, isFormData = false, silentError = false) {
    const options = {
        method,
        headers: {}, // Initialize headers
    };

    if (isFormData) {
        // For FormData, do not set Content-Type header.
        // The browser will automatically set it to 'multipart/form-data' with the correct boundary.
        if (data) {
            options.body = data;
        }
    } else {
        // For JSON data
        options.headers['Content-Type'] = 'application/json';
        if (data) {
            options.body = JSON.stringify(data);
        }
    }

    // Debugging logs
    // console.log('[DEBUG] apiRequest - URL:', url, 'Method:', method, 'Options:', JSON.stringify(options, null, 2));
    // if (isFormData && data) {
        // Loop through FormData entries to log them
        // This helps confirm what FormData contains right before fetch
        // for (let [key, value] of data.entries()) {
            // console.log('[DEBUG] apiRequest - FormData entry before fetch: key=', key, 'value=', value);
            // If value is a File object, log its properties
            // if (value instanceof File) {
                // console.log('[DEBUG] apiRequest - File details: name=', value.name, 'size=', value.size, 'type=', value.type);
            // }
        // }
    // }
    // End Debugging logs

    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
            console.error('API Error:', errorData);
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        if (response.status === 204) { // No Content
            return null; 
        }
        // For 200 OK, 201 Created, 202 Accepted, etc., try to parse JSON,
        // as the persona generation queueing endpoint *does* return a JSON body with 202.
        return await response.json(); 
    } catch (error) {
        console.error('Fetch Error:', error);
        if (!silentError) {
            alert(`An error occurred: ${error.message}`); // Consider making alerts less intrusive or configurable
        }
        throw error;
    }
}

/**
 * Fetches the list of active personas.
 * @returns {Promise<Array|null>} A promise that resolves to an array of active personas, or null if an error occurs.
 */
export async function fetchActivePersonas() {
    try {
        const personas = await apiRequest('/api/personas/list_active', 'GET');
        return personas;
    } catch (error) {
        // apiRequest already logs the error to console and shows an alert.
        // Depending on desired behavior, we might want to return null or re-throw.
        // For now, let the error propagate (as apiRequest throws it).
        // If a fallback value like null is preferred, this catch block can return it.
        console.error("fetchActivePersonas failed:", error); // Additional context for this specific function call
        return null; // Or re-throw if callers are expected to handle it: throw error;
    }
}

/**
 * Tags a post for a specific persona to respond and queues an LLM request.
 * @param {number|string} postId The ID of the post to tag.
 * @param {number|string} personaId The ID of the persona to tag.
 * @returns {Promise<Object|null>} A promise that resolves to the API response object on success, or null on failure.
 */
export async function tagPostForPersonaResponse(postId, personaId) {
    const requestData = { persona_id: personaId };
    try {
        const response = await apiRequest(`/api/posts/${postId}/tag_persona`, 'POST', requestData);
        console.log('Successfully tagged post for persona response:', response); // Log success
        return response; // response from apiRequest will be the parsed JSON
    } catch (error) {
        // apiRequest already logs the error to console and shows an alert.
        console.error(`tagPostForPersonaResponse failed for postId ${postId}, personaId ${personaId}:`, error); // Additional context
        return null; // Or re-throw: throw error;
    }
}