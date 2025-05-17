// This file will contain API helper functions.

export async function apiRequest(url, method = 'GET', body = null) {
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