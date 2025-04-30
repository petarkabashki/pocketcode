# Plan: Enhanced CLI with `prompt_toolkit`

This plan outlines the steps to enhance the Pocketcode CLI with features like command history, auto-suggestions, and improved navigation using the `prompt_toolkit` library.

## 1. Dependency Management

*   Add `prompt_toolkit` to the project's `requirements.txt` file.

## 2. Code Modifications (`pocketcode/main.py`)

*   **Imports:**
    *   Add necessary imports from `prompt_toolkit`:
        ```python
        from prompt_toolkit import prompt
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import NestedCompleter, WordCompleter, PathCompleter, GlobCompleter
        import os # Ensure os is imported
        ```
*   **History Setup:**
    *   Define `history_file_path = os.path.expanduser("~/.pocketcode_history")`.
    *   Instantiate `history = FileHistory(history_file_path)` before the main `while True:` loop.
*   **Completer Setup:**
    *   Define the command structure using `NestedCompleter`, prioritizing commands first, then arguments.
    *   Ensure `registered_components` and `cli_context` are accessible for dynamic completions (e.g., mode slugs, snippet names, paths).
    *   Example structure (needs refinement based on available data in `run()`):
        ```python
        completer_dict = {
            '/help': None,
            '/mode': WordCompleter(list(registered_components.get('modes', {}).keys())),
            '/modes': WordCompleter(list(registered_components.get('modes', {}).keys())),
            '/tools': WordCompleter(['--all']),
            '/context': {
                'show': WordCompleter(['files', 'folders', 'urls', 'snippets', 'all']),
                'add': {
                    'file': PathCompleter(),
                    'folder': PathCompleter(),
                    'url': None,
                    'snippet': None # Name first, then content
                },
                'remove': {
                    'file': PathCompleter(), # Or completer based on cli_context['files']
                    'folder': PathCompleter(), # Or completer based on cli_context['folders']
                    'url': WordCompleter(list(cli_context.get('urls', set()))),
                    'snippet': WordCompleter(list(cli_context.get('snippets', {}).keys()))
                },
                'clear': WordCompleter(['files', 'folders', 'urls', 'snippets', 'all']),
                'help': None
            },
            '/watch': {
                'start': PathCompleter(),
                'stop': PathCompleter(), # Or completer based on watched paths
                'status': None
            },
            '/create-memory-bank': None,
            '/mode-switch-status': None
        }
        completer = NestedCompleter.from_nested_dict(completer_dict)
        ```
    *   Instantiate the `completer` before the loop.
*   **Input Replacement:**
    *   Replace the existing `input()` call (around line 306) with:
        ```python
        user_input = prompt(
            f"({mode_prompt_name}) > ",
            history=history,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True # Recommended for better UX
        )
        ```

## 3. Testing

*   Verify history persistence across sessions (`~/.pocketcode_history` file creation/update).
*   Test up/down arrow navigation through history.
*   Test command completion (e.g., typing `/co` and pressing Tab).
*   Test argument completion (e.g., `/mode <tab>`, `/context add file <tab>`).
*   Verify auto-suggestions based on history.

## Conceptual Flow Diagram

```mermaid
graph TD
    subgraph pocketcode/main.py run()
        A[Start run()] --> B(Load Config);
        B --> C(Init Memory Bank);
        C --> D(Init Watcher);
        D --> E(Register Components);
        E --> F(Set Initial Mode);
        F --> G[Define history_file_path = "~/.pocketcode_history"];
        G --> H[Instantiate history = FileHistory(history_file_path)];
        H --> I[Define completer_logic (NestedCompleter)];
        I -- Accesses --> J[registered_components];
        I -- Accesses --> K[cli_context];
        I --> L[Instantiate completer];
        L --> M[Start Main Loop];
        M --> N{Read User Input via prompt_toolkit};
        N -- Uses --> H;
        N -- Uses --> L;
        N -- Uses --> P[AutoSuggestFromHistory];
        N -- Returns --> Q[User Command String];
        Q -- If command --> R[Pass to handle_command()];
        Q -- If request --> S[Pass to current_mode_instance.process_request()];
        R --> M;
        S --> M;
        M -- Ctrl+C --> T(Stop Watcher & Exit);
    end

    style N fill:#ccf,stroke:#333,stroke-width:2px