# Flow Output Refactor Plan

## Goal

Ensure all mode flows (`pocketcode/mode_flows/`) consistently produce user-visible output by setting the `shared_store["final_output"]` key, which is read and displayed by `pocketcode/main.py`.

## Analysis Summary

1.  **Base Structure (`pocketcode/mode_flows/base_flow.py`):**
    *   Defines a standard flow structure using the `create_base_flow` function.
    *   Includes a `BaseFormatResponseNode` responsible for consolidating results (answers, questions, errors) into `shared_store["final_output"]`.

2.  **Main Loop (`pocketcode/main.py`):**
    *   Correctly retrieves the active mode's flow structure.
    *   Executes the flow using `flow_structure.run(shared_store)`.
    *   Retrieves the final message using `shared_store.get("final_output", ...)` and prints it to the user.

3.  **Existing Flows:**
    *   **`koder.py` & `arkitekt.py`:** Correctly use `create_base_flow` and inherit from base nodes, ensuring they utilize the standard output mechanism.
    *   **`asker.py`:** Re-implements the flow logic instead of using `create_base_flow`. It includes a custom `FormatAskerResponse` node that functionally achieves the same result (setting `final_output`), but this approach is inconsistent and less maintainable.
    *   **`micromanager.py`:** Is currently a placeholder implementation. It does *not* use `create_base_flow` or include any node to set `shared_store["final_output"]`. This flow will not produce user output correctly in its current state.

## Approved Plan

To ensure consistency and correct output generation across all flows:

1.  **Refactor `micromanager.py`:**
    *   Modify `create_micromanager_flow` to import and use the `create_base_flow` function from `.base_flow`.
    *   Define placeholder node classes (e.g., `StartMicromanageTask(BaseStartNode)`, `MicromanagerAgentNode(BaseAgentNode)`, etc.) that inherit from the corresponding base nodes defined in `base_flow.py`.
    *   Instantiate these nodes and pass them to `create_base_flow` to wire the standard flow structure.

2.  **Refactor `asker.py`:**
    *   Modify `create_asker_flow` to import and use the `create_base_flow` function from `.base_flow`.
    *   Remove the duplicated node definitions within `asker.py` (e.g., `StartAskerProcessing`, `FormatAskerResponse`, `AskerErrorHandler`, `AskerToolExecutionNode`, `EndAskerProcessing`) as they are functionally equivalent to the base versions.
    *   Keep the custom `AskerAgentNode` as it overrides the `_build_prompt` method with mode-specific logic.
    *   Instantiate the necessary nodes (using base nodes like `BaseStartNode`, `BaseToolExecutionNode`, `BaseFormatResponseNode`, `BaseErrorHandlerNode`, `BaseEndNode`, and the custom `AskerAgentNode`) and pass them to `create_base_flow`.

## Standard Flow Structure (`create_base_flow`)

This diagram illustrates the standard flow logic that all modes should adhere to after the refactoring:

```mermaid
graph TD
    A[Start Node] --> B(Agent Node);
    B -- call_tool --> C{Tool Execution Node};
    B -- final_answer --> D[Format Response Node];
    B -- ask_question --> D;
    B -- error --> E(Error Handler Node);
    C -- tool_executed --> B;
    C -- tool_denied --> D;
    C -- tool_error --> E;
    E -- error_handled --> D;
    D -- response_formatted --> F[End Node];