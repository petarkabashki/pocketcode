# PocketCode Memory Bank Tools Design

## 1. Introduction

This document outlines the design for a set of integrated tools within PocketCode to manage the Memory Bank (`pocketcode_docs`). The goal is to replace direct file manipulation with a structured, validated, and abstracted interface, improving reliability and maintainability.

## 2. Goals

*   Provide dedicated tools for reading, writing, and querying Memory Bank content.
*   Abstract away the underlying file structure (`pocketcode_docs` directory, specific filenames).
*   Integrate seamlessly with the existing PocketCode tool system.
*   Leverage existing logic in `pocketcode/core/memory_bank.py`.
*   Improve error handling and validation for Memory Bank interactions.

## 3. Proposed Tools

The following tools are proposed to manage the Memory Bank:

### 3.1. `read_memory_bank_file`

*   **Description:** Reads the entire content of a specified Memory Bank file (e.g., `productContext.md`).
*   **Parameters:**
    *   `file_name` (string, required): The name of the Memory Bank file to read (e.g., "productContext.md", "activeContext.md", "systemPatterns.md", "techContext.md", "progress.md").
    *   `project_path` (string, optional): Absolute or relative path to the project root. If omitted, defaults to the current project context managed by PocketCode.
*   **Returns:** (string) The content of the specified file.
*   **Errors:**
    *   `MemoryBankFileNotFoundError`: If the specified `file_name` does not exist within the resolved `pocketcode_docs` directory.
    *   `InvalidMemoryBankFileNameError`: If the `file_name` is not one of the recognized Memory Bank files.
    *   `ProjectNotFoundError`: If `project_path` is provided but invalid or doesn't contain a `pocketcode_docs` directory.
    *   `ReadError`: General file reading errors.

### 3.2. `write_memory_bank_file`

*   **Description:** Writes content to a specified Memory Bank file, completely overwriting any existing content. Creates the file if it doesn't exist.
*   **Parameters:**
    *   `file_name` (string, required): The name of the Memory Bank file to write to.
    *   `content` (string, required): The new content to write to the file.
    *   `project_path` (string, optional): Path to the project root.
*   **Returns:** (boolean) `True` if the write operation was successful, `False` otherwise.
*   **Errors:**
    *   `InvalidMemoryBankFileNameError`: If the `file_name` is not valid.
    *   `ProjectNotFoundError`: If `project_path` is invalid.
    *   `WriteError`: General file writing errors (permissions, disk space, etc.).

### 3.3. `append_to_memory_bank_file`

*   **Description:** Appends content to the end of a specified Memory Bank file. Useful for incrementally updating files like `progress.md`. Creates the file if it doesn't exist.
*   **Parameters:**
    *   `file_name` (string, required): The name of the Memory Bank file to append to.
    *   `content` (string, required): The content to append. A newline character will be added before the appended content if the file is not empty and doesn't end with one.
    *   `project_path` (string, optional): Path to the project root.
*   **Returns:** (boolean) `True` if the append operation was successful, `False` otherwise.
*   **Errors:**
    *   `InvalidMemoryBankFileNameError`: If the `file_name` is not valid.
    *   `ProjectNotFoundError`: If `project_path` is invalid.
    *   `WriteError`: General file writing/appending errors.

### 3.4. `get_memory_bank_summary`

*   **Description:** Retrieves a concise summary or extracts key information from one or more Memory Bank files. This provides a higher-level view than raw file content. (Implementation might involve simple heuristics or potentially an LLM call).
*   **Parameters:**
    *   `file_names` (list[string], optional): A list of Memory Bank file names to summarize. Defaults to all standard files if omitted.
    *   `topic` (string, optional): A specific topic or question to focus the summary on (e.g., "current blockers", "tech stack").
    *   `project_path` (string, optional): Path to the project root.
*   **Returns:** (string) The generated summary.
*   **Errors:**
    *   `MemoryBankFileNotFoundError`: If any specified `file_name` does not exist.
    *   `InvalidMemoryBankFileNameError`: If any `file_name` is not valid.
    *   `ProjectNotFoundError`: If `project_path` is invalid.
    *   `SummarizationError`: If the summary generation fails.

### 3.5. `check_memory_bank_status`

*   **Description:** Verifies the existence and basic validity (e.g., non-empty) of the standard Memory Bank files within a project.
*   **Parameters:**
    *   `project_path` (string, optional): Path to the project root.
*   **Returns:** (dict) A dictionary reporting the status of each standard Memory Bank file (e.g., `{"productContext.md": "OK", "activeContext.md": "MISSING", "progress.md": "EMPTY"}`). Status values could include "OK", "MISSING", "EMPTY", "ERROR".
*   **Errors:**
    *   `ProjectNotFoundError`: If `project_path` is invalid or doesn't contain a `pocketcode_docs` directory.

## 4. Integration Plan

1.  **Tool Definitions:** Define the schemas (parameters, descriptions) for these new tools, likely within `pocketcode/tools/tool_definitions.py` or potentially a new dedicated file like `pocketcode/tools/memory_bank_definitions.py` if the number of tools grows significantly.
2.  **Tool Implementation:** Create a new Python module, `pocketcode/tools/memory_bank_tools.py`, to house the implementation logic for these tools.
3.  **Core Logic Interaction:** The functions within `memory_bank_tools.py` will import and utilize the `MemoryBank` class from `pocketcode/core/memory_bank.py` to handle:
    *   Resolving the correct `pocketcode_docs` directory based on the `project_path` or current context.
    *   Getting the full paths to specific Memory Bank files (`get_file_path` method).
    *   Potentially leveraging validation methods if added to the `MemoryBank` class.
4.  **Registration:** Ensure the new tools are registered with the PocketCode tool system. This might involve updating `pocketcode/core/registration.py` or ensuring the tool discovery mechanism automatically picks up the definitions and implementations based on their location and structure.
5.  **Error Handling:** Implement the specified error conditions using custom exception classes (e.g., `MemoryBankFileNotFoundError`, `InvalidMemoryBankFileNameError`) defined perhaps in `pocketcode/core/exceptions.py` or within the `memory_bank_tools.py` module itself.

## 5. Leveraging `pocketcode/core/memory_bank.py`

The existing `MemoryBank` class in `pocketcode/core/memory_bank.py` is crucial for these tools. It should be the single source of truth for:

*   Locating the `pocketcode_docs` directory relative to a project root.
*   Knowing the standard names of Memory Bank files.
*   Providing methods like `get_file_path(file_name)` to abstract away path construction.

The new tool implementations will instantiate or use a shared instance of the `MemoryBank` class to perform these tasks before attempting file I/O. This avoids duplicating logic for finding and validating Memory Bank files. Future enhancements to the `MemoryBank` class (e.g., adding validation checks) would automatically benefit the tools using it.

## 6. Future Considerations

*   **Validation:** Implement more sophisticated content validation within the `write` and `append` tools or the `MemoryBank` class itself.
*   **Structured Data:** Explore storing some Memory Bank information in a more structured format (e.g., YAML, JSON) alongside or instead of pure Markdown, which could enable more powerful querying tools.
*   **Caching:** Implement caching for read operations if performance becomes an issue.