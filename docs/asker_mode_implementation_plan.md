# Asker Mode Implementation Plan

This document outlines the plan to implement the new "Asker" mode within the PocketCode application. This mode will be integrated as a core flow, similar to the existing "koder" mode.

## Goal

Create a new mode named "Asker" (`❓ Asker`) specialized in answering questions about the codebase or other topics by utilizing file system reading, searching, and listing tools.

## Implementation Steps

1.  **Create Flow File:**
    *   Create a new Python file: `pocketcode/flows/asker.py`.

2.  **Implement Flow Logic in `asker.py`:**
    *   Copy the basic structure and node definitions from `pocketcode/flows/koder.py`.
    *   Rename the primary flow creation function from `create_code_flow` to `create_asker_flow`.
    *   *(Recommended)* Rename the `CodeAgentNode` class to `AskerAgentNode` and update `create_asker_flow` accordingly.
    *   Modify the `_build_prompt` method within the agent node (`AskerAgentNode` or equivalent) to reflect the "Asker" role: "You are Roo, a helpful assistant designed to answer questions about the codebase or other topics. You can read files, search through the project, and list directory contents to gather information for your answers. Use the available tools to find the information needed." Maintain the existing JSON action format (`call_tool`, `final_answer`, `ask_question`).

3.  **Update Configuration (`pocketcode/config/settings.yaml`):**
    *   Add a new entry under the `modes:` section for `asker`:

    ```yaml
    asker:
      name: "❓ Asker"
      description: "Mode specialized for answering questions using file system and search tools."
      flow_module: pocketcode.flows.asker.create_asker_flow # Points to the new flow function
      # Inherits default llm_config (provider/model/parameters)
      allowed_tools: # Specify tools for this mode
        - read_file
        - list_files
        - glob_files    # Tool for pattern matching files
        - search_code   # Tool for searching within files
        # Note: Default memory bank tools are also implicitly available if enabled globally
      # Optional: Define specific prompts later if needed
      # prompt_template_path: prompts/asker_mode_system.txt
      # custom_instructions_path: prompts/asker_mode_instructions.txt
    ```

## Conceptual Flow Diagram

```mermaid
graph TD
    A[User Request (Question)] --> B(ModeManager: Selects Asker Mode);
    B --> C{PocketFlow: asker.py};
    C -- Runs --> D(AskerAgentNode: Build Prompt);
    D -- Prompt --> E(LLM);
    E -- Response (JSON Action) --> F(AskerAgentNode: Parse Response);
    F -- call_tool --> G(ToolExecutionNode);
    G -- tool_name: read/search/list/glob --> H(Filesystem/Search Tools);
    H -- Result --> I(ToolExecutionNode: Update Store);
    I -- tool_executed --> D;
    F -- final_answer --> J(FormatResponseNode);
    J --> K[Formatted Answer to User];
    F -- ask_question --> J;
    F -- error --> L(ErrorHandler);
    G -- tool_error --> L;
    L --> J;

    subgraph Configuration (settings.yaml)
        M(modes.asker.flow_module: pocketcode.flows.asker.create_asker_flow)
        N(modes.asker.allowed_tools: [read_file, list_files, ...])
    end

    subgraph Code Implementation
        O(pocketcode/flows/asker.py)
        P(create_asker_flow function)
        Q(AskerAgentNode class)
    end

    M --> C;
    N --> G;
    O -- Contains --> P;
    P -- Creates --> C;
    O -- Contains --> Q;
    P -- Instantiates --> Q;
```

## Next Steps (After Plan Approval)

1.  Switch to `code` mode.
2.  Execute the implementation steps (create `asker.py`, modify `settings.yaml`).