# Base LLM/Tool Flow Implementation Plan

## Objective

Create a foundational "base flow" for LLM interactions and tool usage within the `pocketcode` project. Existing and future mode-specific flows (Koder, Arkitekt, Asker, etc.) will derive from or extend this base flow via configuration and inheritance, promoting code reuse, consistency, and maintainability.

## Analysis of Existing Flows

*   **`pocketcode/mode_flows/koder.py`**: Provides a concrete implementation using `pocketflow`. It defines specific nodes (`StartCodeProcessing`, `CodeAgentNode`, `ToolExecutionNode`, `FormatCodeResponse`, `ErrorHandler`, `EndCodeProcessing`) and relies on a `shared_store` dictionary for dependency injection (LLM client, configs, tool registry) and state management. The core logic involves a loop between the `CodeAgentNode` (LLM interaction) and `ToolExecutionNode`.
*   **`pocketcode/mode_flows/arkitekt.py`**: Currently a placeholder, but outlines a similar structure anticipating nodes for requirements, design, documentation (LLM agent + tools), formatting, and ending. It also suggests an agent-tool loop.
*   **Common Patterns**:
    *   Standard flow: Start -> Agent -> [Optional Tool -> Agent]... -> Format -> End.
    *   Reliance on `shared_store` for state and dependencies.
    *   An "Agent" node for LLM calls, prompt building, response parsing, and decision-making.
    *   A "Tool Execution" node for handling tool mechanics.
    *   Standardized start, end, formatting, and error handling nodes.

## Proposed Solution: Base Flow Structure

Introduce a new file, `pocketcode/mode_flows/base_flow.py`, containing reusable base node classes and a standard flow wiring mechanism.

### 1. Base Node Classes (`pocketcode/mode_flows/base_flow.py`)

*   **`BaseStartNode`**: Generic flow initiator.
*   **`BaseAgentNode`**: Central LLM interaction node.
    *   Retrieves dependencies (`llm_client`, `tool_registry`, configs, request, context, memory bank info, previous tool results) from `shared_store`.
    *   Provides a virtual `_build_prompt(shared_store)` method for customization by subclasses.
    *   Handles LLM calls using the client from `shared_store`.
    *   Parses standard JSON response (`action`, `tool_name`, `arguments`, `answer`, `question`, `error_message`).
    *   Determines next transition (`call_tool`, `final_answer`, `ask_question`, `error`).
*   **`BaseToolExecutionNode`**: Handles tool execution logic.
    *   Retrieves tool details and dependencies from `shared_store`.
    *   Manages confirmation checks.
    *   Loads and executes tools via `tool_registry`.
    *   Updates `shared_store` with results/errors.
    *   Returns transitions (`tool_executed`, `tool_denied`, `tool_error`).
*   **`BaseFormatResponseNode`**: Formats the final output based on the flow outcome.
*   **`BaseErrorHandlerNode`**: Catches errors and prepares a standard error response.
*   **`BaseEndNode`**: Generic flow terminator.

### 2. Base Flow Wiring (`pocketcode/mode_flows/base_flow.py`)

*   A function like `create_base_flow(...)` will assemble instances of these base nodes (or their subclasses) into the standard flow structure:
    `Start -> Agent -> Tool -> Agent ... -> Format -> End`, including error paths.

### 3. Refactoring Existing Flows

*   Modify existing flow nodes (e.g., in `koder.py`, `arkitekt.py`) to inherit from the corresponding base nodes in `base_flow.py`.
*   Override methods like `_build_prompt` in specific Agent nodes where custom logic is needed.
*   Update the `create_<mode>_flow` functions to use these inherited nodes, potentially utilizing the `create_base_flow` wiring function.

## Mermaid Diagram

```mermaid
graph TD
    subgraph BaseFlow (in base_flow.py)
        direction LR
        B_Start(BaseStartNode) --> B_Agent(BaseAgentNode);
        B_Agent -- call_tool --> B_Tool(BaseToolExecutionNode);
        B_Agent -- final_answer / ask_question --> B_Format(BaseFormatResponseNode);
        B_Agent -- error --> B_Error(BaseErrorHandlerNode);
        B_Tool -- tool_executed --> B_Agent;
        B_Tool -- tool_denied --> B_Format;
        B_Tool -- tool_error --> B_Error;
        B_Error -- error_handled --> B_Format;
        B_Format -- response_formatted --> B_End(BaseEndNode);
    end

    subgraph ModeSpecificFlow (e.g., Koder - extends BaseFlow)
        direction LR
        M_Start(ModeStartNode <br> inherits B_Start) --> M_Agent(ModeAgentNode <br> inherits B_Agent <br> *optional override _build_prompt*);
        M_Agent -- call_tool --> M_Tool(ModeToolNode <br> inherits B_Tool);
        M_Agent -- final_answer / ask_question --> M_Format(ModeFormatNode <br> inherits B_Format);
        M_Agent -- error --> M_Error(ModeErrorNode <br> inherits B_Error);
        M_Tool -- tool_executed --> M_Agent;
        M_Tool -- tool_denied --> M_Format;
        M_Tool -- tool_error --> M_Error;
        M_Error -- error_handled --> M_Format;
        M_Format -- response_formatted --> M_End(ModeEndNode <br> inherits B_End);
    end

    style BaseFlow fill:#eee,stroke:#333,stroke-width:1px,color:#333
    style ModeSpecificFlow fill:#fdf,stroke:#f0f,stroke-width:1px

    link ModeSpecificFlow B_Start style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
    link ModeSpecificFlow B_Agent style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
    link ModeSpecificFlow B_Tool style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
    link ModeSpecificFlow B_Format style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
    link ModeSpecificFlow B_Error style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
    link ModeSpecificFlow B_End style stroke:#f0f,stroke-width:2px,stroke-dasharray: 5 5;
```

## Next Steps

1.  Implement the base node classes and flow structure in `pocketcode/mode_flows/base_flow.py`.
2.  Refactor `pocketcode/mode_flows/koder.py` to inherit from the base flow components.
3.  Implement `pocketcode/mode_flows/arkitekt.py` using the base flow components.
4.  Refactor other flows (`asker.py`, `micromanager.py`) similarly.