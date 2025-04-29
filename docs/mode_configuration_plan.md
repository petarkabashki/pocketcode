# Mode Configuration and Execution Plan

## 1. Goal

To create a flexible and extensible system for defining, configuring, and executing different operational "modes" within PocketCoder. Each mode should have its own specific behavior, defined by:

*   A dedicated PocketFlow workflow.
*   A configurable Language Model (LLM) and parameters.
*   A defined set of allowed tools that the LLM can invoke.
*   Custom prompts and instructions.

## 2. Configuration (`settings.yaml`)

Mode configuration will be centralized in `pocketcode/config/settings.yaml`.

### 2.1. `defaults` Section

Provides default values that modes can inherit or override, reducing redundancy.

```yaml
defaults:
  llm_config:
    provider: google # Default provider
    model: gemini-1.5-pro-latest # Default model
    parameters:
      temperature: 0.7
  allowed_tools: # Default tools available to all modes unless overridden
    - read_file
    - write_to_file
    - list_files
  # Add other potential defaults (e.g., default prompt path)
```

### 2.2. `tools` Section

Registers all available tools in the system, mapping a tool name to its implementation module. Modes reference these names in their `allowed_tools`.

```yaml
tools: # Register all available tools
  read_file: pocketcode.tools.filesystem.ReadFileTool
  write_to_file: pocketcode.tools.filesystem.WriteToFileTool
  list_files: pocketcode.tools.filesystem.ListFilesTool
  search_files: pocketcode.tools.search.SearchFilesTool
  execute_command: pocketcode.tools.system.ExecuteCommandTool
  # ... add other tools as they are implemented
```

### 2.3. `modes` Section

Defines each available mode. Each key is the mode's unique `slug`.

```yaml
modes:
  code: # Mode Slug
    name: "💻 Code" # User-friendly display name
    description: "Mode specialized for writing and modifying code using a PocketFlow." # Purpose
    mode_module: pocketcode.modes.code.CodeMode # Path to the BaseMode subclass implementation
    flow_module: pocketcode.flows.code.create_code_flow # Path to the function that creates the PocketFlow instance
    prompt_template_path: prompts/code_mode_system.txt # (Optional) Path to main system prompt file
    llm_config: # Overrides default LLM config
      provider: anthropic
      model: claude-3-opus-20240229
      parameters:
        temperature: 0.5
    allowed_tools: # List of tool names this mode's LLM can call via YAML
      - read_file
      - write_to_file
      - list_files
      - search_files
      - execute_command
    custom_instructions_path: prompts/code_mode_instructions.txt # (Optional) Path to mode-specific instructions

  architect:
    name: "🏗️ Architect"
    description: "Mode for planning, designing system architecture, and documentation."
    mode_module: pocketcode.modes.architect.ArchitectMode
    flow_module: pocketcode.flows.architect.create_architect_flow
    prompt_template_path: prompts/architect_mode_system.txt
    # Inherits default llm_config
    allowed_tools: # Defines specific tools for this mode
      - read_file
      - write_to_file # Potentially restricted to *.md via implementation logic
      - list_files
      - search_files
    custom_instructions_path: prompts/architect_mode_instructions.txt

  # Add other modes (ask, debug, etc.) following the same structure
```

## 3. PocketFlow Integration

*   **Mode-Flow Mapping:** Each mode is explicitly linked to a PocketFlow via the `flow_module` key in its configuration. This key points to a Python function (e.g., `create_code_flow()`) that constructs and returns the specific `Flow` instance for that mode.
*   **Mode Entry Point:** The `mode_module` key points to a Python class inheriting from `pocketcode.core.interfaces.BaseMode`. This class acts as the main handler for the mode. Its responsibilities include:
    *   Loading its configuration from `settings.yaml`.
    *   Instantiating the correct PocketFlow by calling the function specified in `flow_module`.
    *   Initializing the PocketFlow's `shared_store` with necessary context (e.g., user request, custom instructions).
    *   Running the PocketFlow (`flow.run(shared_store)` or `flow.run_async(shared_store)`).
    *   Processing the final state of the `shared_store` to return the mode's result.

## 4. YAML/Tag-Based Tool Calling (Agent Pattern)

LLM tool invocation will follow the PocketFlow "Agent" pattern using a structured YAML format.

*   **Agent Nodes:** Within each mode's PocketFlow, specific `Node` subclasses will act as "Agent Nodes" responsible for LLM interaction and tool execution.
*   **Process:**
    1.  **Prompt Construction:** The Agent Node constructs a prompt for the LLM configured in the mode's `llm_config`. This prompt includes:
        *   Relevant context from the PocketFlow `shared_store`.
        *   The mode's system prompt and custom instructions.
        *   A description of the tools listed in the mode's `allowed_tools`, formatted as an "Action Space".
        *   An explicit instruction to return the decision in the following YAML format, enclosed in ```yaml fences.
    2.  **Required YAML Output Format:**
        ```yaml
        thinking: |
            <LLM's step-by-step reasoning for choosing the action and parameters>
        action: <tool_name>
        parameters:
            <param1_name>: <param1_value>
            <param2_name>: <param2_value>
            # ... other parameters
        ```
    3.  **LLM Call:** The node executes the LLM call.
    4.  **Response Parsing:** The node parses the YAML block from the LLM's response.
    5.  **Validation:**
        *   Checks if the `action` (tool name) is present in the mode's `allowed_tools` list.
        *   Retrieves the schema for the chosen tool (from the `BaseTool` implementation specified in the main `tools` registration).
        *   Validates the provided `parameters` against the tool's schema.
    6.  **Tool Execution:** If validation passes, the node executes the corresponding `BaseTool`'s `execute()` method with the validated parameters.
    7.  **State Update:** The node updates the PocketFlow `shared_store` with the results from the tool execution.
    8.  **Flow Control:** The node's `post()` method returns an appropriate `Action` string (e.g., `tool_executed`, `clarification_needed`, `task_complete`, `loop_back_to_agent`) to direct the PocketFlow to the next step.

## 5. Architecture Diagram

```mermaid
graph TD
    A[settings.yaml] --> B(Defaults);
    A --> C(Tools Registration);
    A --> D(Modes Configuration);

    subgraph Defaults
        B1(Default LLM Config)
        B2(Default Allowed Tools)
    end

    subgraph Tools Registration
        C1(Tool Name 1: Tool Module Path 1)
        C2(Tool Name 2: Tool Module Path 2)
        C3(...)
    end

    subgraph Modes Configuration
        D1(Mode Slug 1) --> E1{Mode Config 1};
        D2(Mode Slug 2) --> E2{Mode Config 2};
        D3(...)

        E1 --> F1(Name)
        E1 --> F2(Description)
        E1 --> F3(Mode Module Path)
        E1 --> F4(Flow Module Path) # Added
        E1 --> F5(Prompt Path)
        E1 --> F6(LLM Config)
        E1 --> F7(Allowed Tools) # For LLM Tool Calling
        E1 --> F8(Custom Instructions Path)

        # ... (Config for Mode 2 similar) ...
    end

    H[Mode Impl Classes (BaseMode subclasses)] <-- F3;
    I[Tool Impl Classes (BaseTool subclasses)] <-- C1 & C2;
    J[Prompt Files] <-- F5;
    K[Custom Instruction Files] <-- F8;
    L[Flow Creation Functions] <-- F4; # Added Link
    M[PocketFlow Nodes/Flows] <-- L;

    N[Core System] --> A;
    N --> H;
    N --> I;
    N --> J;
    N --> K;
    N --> L;
    N --> M;

    H --> L; # Mode class uses Flow creation function
    L --> M; # Flow creation function uses Nodes
    M --> F6; # Nodes use LLM Config
    M --> F7; # Agent nodes use Allowed Tools list for Action Space & Validation
    M --> I; # Agent nodes execute Tools based on parsed YAML action
```

## 6. Implementation Steps (High-Level)

1.  Update `settings.yaml` with the new structure (`defaults`, `tools`, `modes` sections).
2.  Implement the core logic for loading and parsing `settings.yaml`.
3.  Implement `BaseMode` subclasses for each defined mode.
4.  Implement PocketFlow `Node` subclasses, including the "Agent Nodes" for LLM interaction and tool calling.
5.  Implement PocketFlow creation functions (`create_..._flow()`) for each mode.
6.  Ensure `BaseTool` implementations provide necessary `name`, `description`, and `schema` properties.
7.  Integrate the mode loading and execution logic into the main application entry point (`pocketcode/main.py` or equivalent).