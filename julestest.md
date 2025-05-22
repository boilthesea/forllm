# Jules Test Document for LLM Fallback

This document outlines a test scenario for the LLM server's fallback mechanism.

## Scenario: Ollama Server Unreachable

The primary test is to ensure the application behaves gracefully when the Ollama server (expected at `http://localhost:11435`) is not running or is unreachable.

### Expected Behavior:

1.  **User Action**: User submits a post that would normally trigger an LLM response.
2.  **System Behavior (Ollama Unreachable)**:
    *   The `forllm_server` attempts to connect to Ollama.
    *   The connection fails.
    *   The system logs a message indicating the connection failure (e.g., "Ollama connection failed: ConnectionError. Using dummy LLM processor for request X.").
    *   The `_dummy_llm_processor` is invoked.
    *   A dummy response is generated (e.g., "This is a dummy LLM response for post Y using model Z and persona P. The intended prompt was: ...").
    *   This dummy response is saved to the `posts` table, linked to the original post.
    *   The corresponding entry in the `llm_requests` table is marked as 'complete'.
3.  **User Interface**: The user sees the dummy response appear in the forum thread, clearly indicating it's an automated placeholder.

### How to Test:

1.  Ensure the `forllm_server` application is running.
2.  **Crucially, ensure the Ollama server is NOT running or is firewalled.**
3.  Create a new topic or reply to an existing post in the forum application.
4.  Observe the server logs for messages about Ollama connection failure and the invocation of the dummy processor.
5.  Verify in the user interface that a dummy response is displayed.
6.  Check the `posts` table in the database (`forllm_data.db`) to confirm the dummy response is stored correctly and linked to the parent post.
7.  Check the `llm_requests` table to ensure the request is marked 'complete' and not 'error' (unless an error occurred *within* the dummy processor itself, which is a secondary test case).

## Secondary Scenario: Error within Dummy Processor

This is less critical but good to be aware of. If the `_dummy_llm_processor` itself encounters an error (e.g., a database issue while trying to save the dummy post), it should:

1.  Log the error.
2.  Update the `llm_requests` table entry to 'error' with the specific error message from the dummy processor.

This ensures that even fallback failures are tracked.
