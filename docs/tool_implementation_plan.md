# Pocketcode: Native Tool Implementation Plan

**Goal:** Implement a core set of utility tools as Python functions within the `pocketcode` project, define their interfaces for LLM use via PocketFlow, and integrate them.

## 1. Project Structure

*   Ensure the `pocketcode/tools/` directory exists.
*   Create/Update the following files within `pocketcode/tools/`:
    *   `__init__.py`: Standard Python package marker.
    *   `system.py`: Contains shell command execution logic.
    *   `filesystem.py`: Contains file I/O, directory operations, and globbing.
    *   `git.py`: Contains wrappers for common Git commands.
    *   `search.py`: Contains file content search logic using `ripgrep`.
    *   `tool_definitions.py` (or integrate into PocketFlow registration): Defines the schemas and descriptions for each tool function for PocketFlow/LLM consumption.

## 2. Tool Implementation Details

### `pocketcode/tools/system.py`

*   **Function:** `execute_shell_command(command: str) -> dict`
*   **Description:** Executes a shell command and returns its stdout, stderr, and return code.
*   **Implementation:** Use `subprocess.run`, capture outputs, handle errors.
*   **Schema:**
    ```json
    {
      "name": "execute_shell_command",
      "description": "Executes a shell command and returns its stdout, stderr, and return code.",
      "parameters": {
        "type": "object",
        "properties": { "command": { "type": "string", "description": "The shell command to execute." } },
        "required": ["command"]
      }
    }
    ```

### `pocketcode/tools/filesystem.py`

*   **Function:** `read_file(path: str) -> str`
*   **Description:** Reads the content of a file.
*   **Implementation:** Use `pathlib.Path(path).read_text()`, handle `FileNotFoundError`.
*   **Schema:** `{ "name": "read_file", "description": "Reads the content of a file.", "parameters": { "type": "object", "properties": { "path": { "type": "string", "description": "Relative path to the file." } }, "required": ["path"] } }`

*   **Function:** `write_file(path: str, content: str) -> None`
*   **Description:** Writes content to a file, overwriting or creating as needed.
*   **Implementation:** Use `pathlib.Path(path).write_text(content)`, ensure parent directories exist (`pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)`).
*   **Schema:** `{ "name": "write_file", "description": "Writes content to a file, overwriting or creating as needed.", "parameters": { "type": "object", "properties": { "path": { "type": "string", "description": "Relative path to the file." }, "content": { "type": "string", "description": "The content to write." } }, "required": ["path", "content"] } }`

*   **Function:** `create_directory(path: str) -> None`
*   **Description:** Creates a directory, including parent directories if needed.
*   **Implementation:** Use `pathlib.Path(path).mkdir(parents=True, exist_ok=True)`.
*   **Schema:** `{ "name": "create_directory", "description": "Creates a directory, including parent directories if needed.", "parameters": { "type": "object", "properties": { "path": { "type": "string", "description": "Relative path of the directory to create." } }, "required": ["path"] } }`

*   **Function:** `list_directory(path: str = '.', recursive: bool = False) -> list[str]`
*   **Description:** Lists files and directories within a path.
*   **Implementation:** Use `pathlib.Path(path).iterdir()` or `rglob('*')`. Return relative string paths.
*   **Schema:** `{ "name": "list_directory", "description": "Lists files and directories within a path.", "parameters": { "type": "object", "properties": { "path": { "type": "string", "description": "Relative path of the directory to list.", "default": "." }, "recursive": { "type": "boolean", "description": "Whether to list recursively.", "default": false } }, "required": [] } }`

*   **Function:** `glob_files(pattern: str, base_path: str = '.') -> list[str]`
*   **Description:** Finds files/directories matching a glob pattern.
*   **Implementation:** Use `pathlib.Path(base_path).glob(pattern)` or `rglob`. Return relative string paths.
*   **Schema:** `{ "name": "glob_files", "description": "Finds files/directories matching a glob pattern.", "parameters": { "type": "object", "properties": { "pattern": { "type": "string", "description": "The glob pattern (e.g., '*.py', '**/*.txt')." }, "base_path": { "type": "string", "description": "The base directory to search within.", "default": "." } }, "required": ["pattern"] } }`

### `pocketcode/tools/git.py`

*(All functions use `execute_shell_command` from `system.py`)*

*   **Function:** `git_status() -> str`
*   **Description:** Shows the git working tree status.
*   **Implementation:** Call `execute_shell_command("git status --porcelain")`.
*   **Schema:** `{ "name": "git_status", "description": "Shows the git working tree status.", "parameters": { "type": "object", "properties": {}, "required": [] } }`

*   **Function:** `git_diff(file_path: str = None, staged: bool = False) -> str`
*   **Description:** Shows git changes (diff).
*   **Implementation:** Call `execute_shell_command(f"git diff {'--staged ' if staged else ''}{file_path if file_path else ''}")`.
*   **Schema:** `{ "name": "git_diff", "description": "Shows git changes (diff).", "parameters": { "type": "object", "properties": { "file_path": { "type": "string", "description": "Optional path to a specific file to diff." }, "staged": { "type": "boolean", "description": "Show staged changes instead of working directory changes.", "default": false } }, "required": [] } }`

*   **Function:** `git_add(files: list[str]) -> None`
*   **Description:** Stages changes in specified files for the next commit.
*   **Implementation:** Call `execute_shell_command(f"git add {' '.join(files)}")`. Check return code.
*   **Schema:** `{ "name": "git_add", "description": "Stages changes in specified files for the next commit.", "parameters": { "type": "object", "properties": { "files": { "type": "array", "items": { "type": "string" }, "description": "List of file paths to stage. Use '.' to stage all." } }, "required": ["files"] } }`

*   **Function:** `git_commit(message: str) -> None`
*   **Description:** Commits staged changes to the git repository.
*   **Implementation:** Call `execute_shell_command(f"git commit -m \"{message}\"")`. Check return code.
*   **Schema:** `{ "name": "git_commit", "description": "Commits staged changes to the git repository.", "parameters": { "type": "object", "properties": { "message": { "type": "string", "description": "The commit message." } }, "required": ["message"] } }`

*   **Function:** `git_pull(remote: str = 'origin', branch: str = None) -> str`
*   **Description:** Fetches from and integrates with another repository or a local branch.
*   **Implementation:** Determine current branch if needed. Call `execute_shell_command(f"git pull {remote} {branch if branch else ''}")`. Return output.
*   **Schema:** `{ "name": "git_pull", "description": "Fetches from and integrates with another repository or a local branch.", "parameters": { "type": "object", "properties": { "remote": { "type": "string", "description": "The remote repository name.", "default": "origin" }, "branch": { "type": "string", "description": "The branch name to pull. Defaults to the current branch's upstream." } }, "required": [] } }`

*   **Function:** `git_push(remote: str = 'origin', branch: str = None) -> str`
*   **Description:** Updates remote refs using local refs.
*   **Implementation:** Determine current branch if needed. Call `execute_shell_command(f"git push {remote} {branch if branch else ''}")`. Return output.
*   **Schema:** `{ "name": "git_push", "description": "Updates remote refs using local refs.", "parameters": { "type": "object", "properties": { "remote": { "type": "string", "description": "The remote repository name.", "default": "origin" }, "branch": { "type": "string", "description": "The branch name to push. Defaults to the current branch." } }, "required": [] } }`

### `pocketcode/tools/search.py`

*   **Dependency:** Requires `ripgrep` (rg) installed and in PATH.
*   **Function:** `search_code(query: str, path: str = '.', file_pattern: str = None, case_sensitive: bool = False, context_lines: int = 2) -> str`
*   **Description:** Searches code using ripgrep (rg). Requires 'rg' to be installed.
*   **Implementation:** Check for `rg` existence. Construct and execute `rg` command via `execute_shell_command`, preferably using `--json` output for easier parsing. Example: `rg --json --heading --line-number {'-g ' + file_pattern if file_pattern else ''} {'-C ' + str(context_lines)} {'-s' if case_sensitive else '-i'} {query} {path}`. Parse JSON or return raw output.
*   **Schema:** `{ "name": "search_code", "description": "Searches code using ripgrep (rg). Requires 'rg' to be installed.", "parameters": { "type": "object", "properties": { "query": { "type": "string", "description": "The regex pattern to search for." }, "path": { "type": "string", "description": "The directory or file path to search within.", "default": "." }, "file_pattern": { "type": "string", "description": "Glob pattern to filter files (e.g., '*.py')." }, "case_sensitive": { "type": "boolean", "description": "Perform a case-sensitive search.", "default": false }, "context_lines": { "type": "integer", "description": "Number of context lines to show before/after matches.", "default": 2 } }, "required": ["query"] } }`

## 3. PocketFlow Integration

*   **Action:** Investigate PocketFlow's tool registration mechanism.
*   **Goal:** Determine how to register the Python functions (from `system.py`, `filesystem.py`, `git.py`, `search.py`) along with their corresponding schemas so that the PocketFlow framework can invoke them based on LLM requests. This might involve decorators, a central registry class, or configuration files.

## 4. Documentation & Setup

*   **Action:** Update project documentation (`README.md` or `cline_docs/techContext.md`).
*   **Goal:** Add `ripgrep` as a prerequisite, including installation instructions. Document the newly created native tools.

## 5. Implementation Phase

*   **Action:** Switch to Code mode.
*   **Goal:** Implement the Python functions and the PocketFlow registration logic according to this plan.

## Diagram

```mermaid
graph TD
    subgraph Pocketcode Agent
        LLM
    end

    subgraph PocketFlow Framework
        ToolCallingMechanism -- Reads --> ToolRegistry[Tool Registry (Schemas/Functions)]
    end

    subgraph Pocketcode Tools (pocketcode/tools/)
        T_System(system.py):::tool
        T_FS(filesystem.py):::tool
        T_Git(git.py):::tool
        T_Search(search.py):::tool
        ToolDefs(tool_definitions.py):::def
    end

    subgraph External Dependencies
        ripgrep(ripgrep executable):::dep
    end

    classDef tool fill:#cde4ff,stroke:#6699ff
    classDef def fill:#e8dff5,stroke:#9966cc
    classDef dep fill:#f8d7da,stroke:#dc3545

    LLM -- Tool Request (Name, Args) --> ToolCallingMechanism
    ToolCallingMechanism -- Finds/Calls --> Pocketcode Tools
    Pocketcode Tools -- Uses --> Python Libraries (subprocess, pathlib, os, glob)
    Pocketcode Tools -- Returns Result --> ToolCallingMechanism
    ToolCallingMechanism -- Formats Output --> LLM

    T_Git -- Uses --> T_System
    T_Search -- Uses --> T_System -- Calls --> ripgrep
    ToolDefs -- Populates --> ToolRegistry