# Refactoring Plan: Splitting `pocketcode/main.py`

## Goal

To improve maintainability and readability of `pocketcode/main.py` (currently 771 lines) by splitting it into smaller, more focused modules, aiming for a target size of around 300 lines per module where feasible.

## Analysis

`pocketcode/main.py` handles several responsibilities:
- Imports and Global State
- Logging Setup
- Watcher Queue Processing (`process_watcher_queue`)
- Main `run()` function (Orchestration, Setup, CLI Loop)
- Command Handling (`handle_command` for CLI commands like `/mode`, `/context`, etc.)
- Help Functions (`print_help`, `print_context_help`)

The `handle_command` function (approx. 370 lines) and its associated help functions represent a distinct logical unit suitable for extraction.

## Proposed Split

Extract the command handling logic into a dedicated module: `pocketcode/cli/command_handler.py`.

**Benefits:**
- Reduces the size of `main.py`.
- Improves separation of concerns (`main.py` for orchestration, `command_handler.py` for CLI commands).
- Enhances code navigation and maintainability.

## Implementation Steps

1.  **Create Directory:** Create `pocketcode/cli/`.
2.  **Create File:** Create `pocketcode/cli/__init__.py` (empty file to make it a package).
3.  **Create File:** Create `pocketcode/cli/command_handler.py`.
4.  **Move Code:** Cut the `handle_command`, `print_help`, and `print_context_help` function definitions from `pocketcode/main.py` and paste them into `pocketcode/cli/command_handler.py`.
5.  **Update `command_handler.py`:**
    *   Add necessary imports (e.g., `logging`, `os`, `typing`, potentially types from `pocketcode.core`).
    *   Modify the `handle_command` function signature to accept all previously global variables it needs as parameters. Proposed signature:
        ```python
        from typing import Dict, Optional, Any
        # Assuming these types are importable or defined
        # from pocketcode.core.memory_bank import MemoryBankManager
        # from pocketcode.core.watcher import FileWatcher
        # from pocketcode.core.interfaces import BaseMode

        def handle_command(
            command_input: str,
            config: Dict[str, Any],
            memory_manager: Optional[Any], # Replace Any with MemoryBankManager if importable
            file_watcher: Optional[Any],   # Replace Any with FileWatcher if importable
            current_mode_instance: Optional[Any], # Replace Any with BaseMode if importable
            registered_components: Dict[str, Dict],
            cli_context: Dict[str, Any],
            global_allow_mode_switching: bool
        ) -> None: # Or return something if needed
            # ... existing function body ...
            # Remove global declarations within the function
        ```
    *   Ensure `print_help` and `print_context_help` are called correctly within `handle_command`.
6.  **Update `main.py`:**
    *   Add import: `from pocketcode.cli.command_handler import handle_command`.
    *   In the main loop (`while True:` block), modify the call within the `if user_input.startswith('/'):` block to use the imported function and pass all required arguments explicitly:
        ```python
        handle_command(
            command_input=user_input,
            config=config,
            memory_manager=memory_manager,
            file_watcher=file_watcher,
            current_mode_instance=current_mode_instance,
            registered_components=registered_components,
            cli_context=cli_context,
            global_allow_mode_switching=global_allow_mode_switching
        )
        ```
    *   Remove `global` declarations in `main.py` for variables now passed as arguments to the imported `handle_command`, if they are no longer needed globally within `main.py`.

## Structure Diagram

```mermaid
graph TD
    subgraph pocketcode
        main["main.py (Orchestration, Loop)"]
        subgraph core
            direction LR
            mem["memory_bank.py"]
            reg["registration.py"]
            watch["watcher.py"]
            int["interfaces.py"]
        end
        subgraph cli [Proposed]
            direction LR
            cmd["command_handler.py (Handles /, help)"]
        end
        subgraph config
             direction LR
             loader["loader.py"]
             settings["settings.yaml"]
        end
        subgraph flows
             direction LR
             flow_code["code.py"]
             flow_arch["architect.py"]
        end
         subgraph modes
             direction LR
             mode_code["code.py"]
             mode_arch["architect.py"]
        end
         subgraph tools
             direction LR
             tool_fs["filesystem.py"]
             tool_git["git.py"]
        end
    end

    main -- Calls --> cmd
    main -- Uses --> reg
    main -- Uses --> mem
    main -- Uses --> watch
    main -- Uses --> loader
    main -- Uses --> mode_code
    main -- Uses --> mode_arch
    cmd -- Uses --> mem
    cmd -- Uses --> watch
    cmd -- Uses --> mode_code
    cmd -- Uses --> mode_arch
    cmd -- Uses --> tool_fs
    cmd -- Uses --> tool_git

    style cli fill:#ccf,stroke:#333,stroke-width:2px