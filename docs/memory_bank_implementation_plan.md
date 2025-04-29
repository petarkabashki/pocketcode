# Pocketcode Memory Bank Implementation Plan

## Goal

Integrate a memory bank system into `pocketcode` that checks for and loads context from files within a specified directory (`pocketcode_docs` by default) in the user's project root (Current Working Directory - CWD) before the main application logic proceeds. This ensures the AI assistant has necessary context upon startup.

## Core Concepts

1.  **Configuration:** Define the memory bank directory name and required files in `settings.yaml`.
2.  **Location:** The memory bank directory resides in the CWD where the `pocketcode` CLI is executed.
3.  **Management:** A dedicated `MemoryBankManager` class handles checking, creating (if necessary), verifying, and loading memory bank files.
4.  **Verification:** Strictly enforce the presence and non-emptiness of required memory bank files before allowing the selected mode to start. Abort startup if verification fails.
5.  **Integration:** Instantiate the `MemoryBankManager` early in the startup process (`main.py`) and pass it to the selected `Mode` instance.
6.  **Access:** Modes use the passed manager instance to load and access the verified content.

## Required Memory Bank Files

The following files must exist and be non-empty within the configured `memory_bank_dir`:

*   `productContext.md`: Project purpose, goals, high-level features.
*   `activeContext.md`: Current task, recent changes, next steps.
*   `systemPatterns.md`: Architecture, design patterns, key technical decisions.
*   `techContext.md`: Languages, frameworks, setup, constraints, style guides.
*   `progress.md`: Overall status, completed features, work remaining.

## Detailed Implementation Steps

1.  **Update Configuration (`pocketcode/config/settings.yaml`):**
    *   Add new keys under the `core` section:
    ```yaml
    core:
      log_level: INFO
      require_tool_confirmation: true
      memory_bank_dir: pocketcode_docs # Name of the directory in CWD
      memory_bank_files:              # List of required files
        - productContext.md
        - activeContext.md
        - systemPatterns.md
        - techContext.md
        - progress.md
      # ... other core settings
    ```

2.  **Implement `MemoryBankManager` (`pocketcode/core/memory_bank.py`):**
    *   Create `pocketcode/core/memory_bank.py`.
    *   Define `MemoryBankIncompleteError(Exception)`.
    *   Implement `MemoryBankManager`:
        *   `__init__(self, core_config: Dict, project_root: str)`: Stores config, calculates full path to memory bank dir.
        *   `get_memory_bank_path() -> str`: Returns the full path.
        *   `verify_and_prepare() -> None`: Checks/creates dir, checks each required file for existence and non-emptiness. Raises `MemoryBankIncompleteError` if any check fails, listing all issues found. Logs success/failure.
        *   `load_content() -> Dict[str, str]`: Reads all verified files into a dictionary. Handles `IOError`.
        *   `get_file_content(filename: str) -> str | None`: Reads a single specified file.

3.  **Integrate into Startup (`pocketcode/main.py`):**
    *   Import `MemoryBankManager`, `MemoryBankIncompleteError`, `os`, `sys`.
    *   In `run()`, after loading config:
        *   Get CWD: `project_root = os.getcwd()`
        *   Get core config: `core_config = config.get('core', {})`
        *   Instantiate manager: `memory_manager = MemoryBankManager(core_config, project_root)`
        *   Verify:
            ```python
            try:
                logger.info(f"Verifying memory bank in: {memory_manager.get_memory_bank_path()}")
                memory_manager.verify_and_prepare()
                logger.info("Memory bank verified successfully.")
            except MemoryBankIncompleteError as e:
                logger.error(f"Memory Bank setup incomplete: {e}")
                logger.error("Please create or populate the required files in the memory bank directory and restart.")
                sys.exit(1) # Exit if verification fails
            except Exception as e:
                logger.error(f"An unexpected error occurred during memory bank verification: {e}", exc_info=True)
                sys.exit(1)
            ```
    *   Pass `memory_manager` when instantiating the mode: `current_mode_instance = ModeClass(config=mode_config, memory_manager=memory_manager)`

4.  **Adapt Mode Implementations (e.g., `pocketcode/modes/*.py`):**
    *   Modify `__init__` of relevant modes to accept `memory_manager: MemoryBankManager` and store it (e.g., `self._memory_manager = memory_manager`).
    *   Access content via `self._memory_manager.load_content()` or `self._memory_manager.get_file_content(filename)` within mode logic.

## Conceptual Flow Diagram

```mermaid
graph TD
    A[Start pocketcode CLI] --> B{Load settings.yaml};
    B --> C{Get CWD};
    C --> D{Instantiate MemoryBankManager};
    D --> E{Call manager.verify_and_prepare()};
    E -- Success --> F{Instantiate Selected Mode};
    E -- Failure (MemoryBankIncompleteError) --> G{Log Error & Exit};
    F --> H{Pass MemoryBankManager to Mode};
    H --> I[Run Mode Interaction Loop];
    I --> J{Mode uses MemoryBankManager};
    J --> K[Process Request];
```

## Future Considerations

*   Add specific tools (e.g., `update_active_context_tool`) for modes to modify memory bank files during runtime, if needed.