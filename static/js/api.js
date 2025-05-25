// This file will contain API helper functions.

export async function apiRequest(url, method = 'GET', data = null, isFormData = false) {
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
        if (response.status === 204 || response.status === 202) { // Handle 202 Accepted as well
            return null; // No content to parse
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch Error:', error);
        alert(`An error occurred: ${error.message}`); // Consider making alerts less intrusive or configurable
        throw error;
    }
}