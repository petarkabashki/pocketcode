# Plan: Create Micromanager Mode

## Objective

Create a new "Micromanager" mode for PocketCoder. This mode will analyze tasks, break them down into subtasks, and delegate these subtasks to other appropriate modes, passing necessary context.

## Mode Definition

The mode is defined directly within the main `pocketcode/config/settings.yaml` file.

```yaml
  micromanager:
    name: "🧐 Micromanager"
    description: "Mode for analyzing tasks, breaking them down into subtasks, and delegating execution to other specialized modes."
    module: pocketcode.modes.micromanager.MicromanagerMode # NOTE: This module needs to be created later
    flow_module: pocketcode.flows.micromanager.create_micromanager_flow # NOTE: This flow needs to be created later
    # prompt_template_path: prompts/micromanager_system.txt # Optional: Can add later
    # llm_config: # Inherits default LLM config for now
    allowed_tools: # Tools needed for analysis and planning
      - read_file
      - list_files
      - search_files
      # Assuming delegation tools (switch_mode, new_task) and ask_followup_question are handled by the core system or flow implementation
    # custom_instructions_path: prompts/micromanager_instructions.txt # Optional: Can add later
```

## Implementation Plan (Completed)

1.  **Fetch Instructions:** Obtained instructions for creating modes.
2.  **Initial Plan:** Proposed creating an "Orchestrator" mode in `.roomodes`.
3.  **Feedback:** User requested renaming to "Micromanager" and using `settings.yaml`.
4.  **Update `settings.yaml`:** Added the `micromanager` mode definition to `pocketcode/config/settings.yaml`. (Completed).
5.  **Remove `.roomodes`:** Deleted the `.roomodes` file as it was no longer needed. (Completed).
6.  **Update & Rename Plan:** Updated this plan document and saved it as `docs/micromanager_mode_plan.md`. (Completed).
7.  **Revise Diagram:** Updated the workflow diagram based on user feedback. (This step).

## Micromanager Workflow Diagram (Revised)

```mermaid
graph TD
    A["User Request Received"] --> B{"Micromanager Mode"}
    B --> C["1: Analyze Task & Context"]
    C --> D["2: Break into Sequential Subtasks"]
    D --> E["3: Identify Mode & Required Context per Subtask"]
    E --> F["4: Create Execution Plan &lt;Subtasks, Modes, Context&gt;"]
    F --> G{"5: Confirm Plan with User?"}
    G -- Approved --> H["6: Initialize Subtask Queue"]
    H --> I{"7: Any Subtasks Left in Queue?"}
    I -- Yes --> J["8: Get Next Subtask from Queue"]
    J --> K["9: Delegate Subtask<br>(Use 'new_task' tool with necessary context)"]
    K --> L["10: Target Mode Executes Subtask"]
    L -- Returns Result/Status --> B
    B --> M["11: Process Subtask Result / Update Context / Monitor Progress"]
    M --> I
    I -- No --> N["12: Verify Overall Task Completion based on results"]
    N -- Completed --> O["13: Task Finished Successfully"]
    N -- Incomplete/Failed --> P["14: Report Issues / Potentially Revise Plan"]
    P --> F
    G -- Needs Changes --> F


  ```