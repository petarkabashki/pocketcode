# Technical Context: Pocketcode

## Core Technologies

*   **Programming Language:** Python (Targeting version 3.10+ for modern features, unless PocketFlow requires otherwise).
*   **Framework:** PocketFlow (Specific version TBD, assume latest stable).
*   **Package Management:** `pip` with `requirements.txt` or potentially `poetry` / `pdm` for better dependency management (Decision TBD).
*   **Version Control:** Git (Repository assumed to be managed by the user).

## Development Setup

*   **Environment:** Recommend using a Python virtual environment (e.g., `venv`) to isolate dependencies.
    ```bash
    python -m venv .venv
    source .venv/bin/activate # Linux/macOS
    # .venv\Scripts\activate # Windows
    pip install -r requirements.txt # (Once requirements are defined)
    ```
*   **Operating System:** Should be cross-platform (Linux, macOS, Windows), typical for Python projects.
*   **IDE:** Any standard IDE with Python support (VS Code, PyCharm, etc.).
*   **External Dependencies:**
    *   **ripgrep (`rg`):** Required for the native `search_code` tool. Must be installed separately and available in the system's PATH.
        *   Installation: See [ripgrep releases](https://github.com/BurntSushi/ripgrep/releases) or use package managers (e.g., `apt install ripgrep`, `brew install ripgrep`, `choco install ripgrep`).

## Technical Constraints & Considerations

*   **PocketFlow Dependency:** The architecture and implementation will be heavily influenced by PocketFlow's capabilities and limitations.
*   **Extendability:** Interfaces for adding Modes, Tools, and Workflows must be clearly defined and simple to use.
*   **Embeddability:** Core workflow execution logic should be callable from other Python code with minimal setup.
*   **Tooling:**
    *   Need robust mechanisms for registering and invoking tools within PocketFlow.
    *   Supports both standard Python functions registered as tools and potentially more complex MCP tools.
    *   A core set of native tools are provided in `pocketcode.tools` for essential operations:
        *   `execute_shell_command`: Runs shell commands.
        *   Filesystem tools (`read_file`, `write_file`, `create_directory`, `list_directory`, `glob_files`).
        *   Git wrappers (`git_status`, `git_diff`, `git_add`, `git_commit`, `git_pull`, `git_push`).
        *   `search_code`: Code search using `ripgrep`.
*   **Performance:** While flexibility is key, performance implications of the chosen architecture (especially with complex workflows or many tools) should be considered.