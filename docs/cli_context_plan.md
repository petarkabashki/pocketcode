# CLI Context Management Plan

This document outlines the plan for implementing CLI commands to manage the context used by the PocketCode assistant.

**1. Context Storage:**

*   A global dictionary named `cli_context` will be added to `pocketcode/main.py`.
*   This dictionary will store context items provided via the CLI during a session.
*   Structure:
    ```python
    cli_context = {
        "files": set(),      # Store unique file paths
        "folders": set(),    # Store unique folder paths
        "urls": set(),       # Store unique URLs
        "snippets": {}     # Store named snippets {name: content}
    }
    ```

**2. Proposed CLI Commands:**

A new top-level command `/context` will be introduced with the following subcommands:

*   **Check Context:**
    *   ` /context show [files|folders|urls|snippets|all]`
        *   Displays current context items. Defaults to `all`.
*   **Add Context:**
    *   ` /context add file <path_to_file>`
    *   ` /context add folder <path_to_folder>`
    *   ` /context add url <url>`
    *   ` /context add snippet <snippet_name> <snippet_content...>`
*   **Remove Context:**
    *   ` /context remove file <path_to_file>`
    *   ` /context remove folder <path_to_folder>`
    *   ` /context remove url <url>`
    *   ` /context remove snippet <snippet_name>`
*   **Clear Context:**
    *   ` /context clear [files|folders|urls|snippets|all]`
        *   Removes items of a specific type or all context. Defaults to `all`.

**3. Implementation Steps (within `pocketcode/main.py`):**

*   **Initialize `cli_context`:** Define the global dictionary.
*   **Update `handle_command`:** Add parsing and logic for `/context` subcommands to modify `cli_context`. Provide user feedback.
*   **Update `print_help`:** Include the new `/context` commands.
*   **Integrate Context into Processing:** Modify the main loop to pass `cli_context` to the active mode's `process_request` method within the `context` dictionary.

**4. Scope:**

*   This plan covers the CLI mechanism for context management.
*   Actual utilization of the context by specific modes is a separate task.

**5. Diagram:**

```mermaid
graph LR
    A[User Input: /context add file ...] --> B{handle_command};
    B -- Parses '/context' --> C{Context Logic};
    C -- Updates --> D[Global cli_context Dict];
    C -- Prints Feedback --> E[User Output];

    F[User Input: Normal Request] --> G{Main Loop};
    G -- Gets --> D;
    G -- Creates --> H[context Dict];
    H -- Includes cli_context --> I{current_mode_instance.process_request};
    I -- Uses Context --> J[Mode Logic];
    J --> K[Response];
    K --> E;