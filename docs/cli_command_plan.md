# CLI Command Implementation Plan: /modes, /allow, /disallow

This document outlines the plan to implement a new `/modes` CLI command and refactor the existing `/allow` and `/disallow` commands in `pocketcode/main.py`.

## Requirements

1.  **`/modes` Command:**
    *   List all registered modes and their allowed tools (as defined in `settings.yaml`).
    *   Accept optional mode slugs as arguments to filter the output (e.g., `/modes code architect`).
    *   If no arguments are provided, list all modes.
2.  **`/allow` & `/disallow` Commands:**
    *   Modify these commands to manage the *auto-approval status* of tools, not the core `allowed_tools` list from the configuration.
    *   Introduce an optional `--mode <mode1> <mode2> ...` flag to apply the setting to specific modes.
    *   If the `--mode` flag is omitted, apply the setting globally.

## Implementation Plan

1.  **Modify `pocketcode/main.py`:**
    *   **Refactor `auto_allowed_tools`:** Change the global `auto_allowed_tools` dictionary from its current flat structure to a nested structure supporting global and per-mode settings.
        ```mermaid
        graph TD
            subgraph Proposed New Structure
                X[auto_allowed_tools] --> Y{__global__: dict};
                X --> Z{mode_slug_1: dict};
                X --> Z2{mode_slug_2: dict};
                X --> ZN[...];

                subgraph Global Settings
                    Y --> Y1{tool_name: bool};
                    Y --> Y2{__all__: bool};
                end

                subgraph Mode Specific Settings (Example: mode_slug_1)
                    Z --> Z1{tool_name: bool};
                    Z --> Z2_all{__all__: bool};
                end
            end
        ```
    *   **Implement `/modes` Command:**
        *   Add a new `elif command == "/modes":` block in `handle_command`.
        *   Parse arguments for optional mode slugs.
        *   Retrieve mode configurations from the `config` object.
        *   Iterate through selected modes and print their slugs and `allowed_tools` lists.
    *   **Update `/allow` & `/disallow` Logic:**
        *   Modify the argument parsing to handle the optional `--mode` flag and associated mode slugs.
        *   Update the logic to modify the correct part of the new `auto_allowed_tools` structure (either `__global__` or specific mode dictionaries).
    *   **Update `/tools` Command:**
        *   Adjust the logic that checks the auto-allow status. It should first check the specific mode's dictionary in `auto_allowed_tools`, then fall back to the `__global__` dictionary to determine if `(allowed)` should be printed.
    *   **Update `print_help`:**
        *   Add documentation for the new `/modes` command.
        *   Update the documentation for `/allow` and `/disallow` to explain the `--mode` flag and the auto-approval behavior.

## Next Steps

1.  Confirm this plan is saved successfully.
2.  Switch to `code` mode to implement the changes in `pocketcode/main.py`.