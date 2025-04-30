# Code Mode Implementation Plan

## 1. Problem Statement

The current `KoderMode` (`pocketcode/modes/code.py`) and its associated workflow (`pocketcode/flows/code.py`) are non-functional due to the use of placeholder classes (`PlaceholderNode`, `PlaceholderFlow`) and simulated logic instead of actual implementations using the PocketFlow library and real LLM/tool interactions.

## 2. Goal

Refactor `pocketcode/modes/code.py` and `pocketcode/flows/code.py` to use the actual PocketFlow library, implement real node logic (LLM interaction, tool execution, response formatting, error handling), and enable the `flow.run()` execution path.

## 3. Implementation Steps

### 3.1. Update `pocketcode/flows/code.py`

#### 3.1.1. Imports
   - Add/uncomment necessary imports from the PocketFlow library (e.g., `from pocketflow import Flow, Node`).
   - Ensure `importlib` is present for dynamic tool loading.

#### 3.1.2. Replace Placeholder Base Class
   - Remove the `PlaceholderNode` class definition.
   - Update all node classes (`CodeAgentNode`, `ToolExecutionNode`, `FormatCodeResponse`, `ErrorHandler`, `StartCodeProcessing`, `EndCodeProcessing`) to inherit from `pocketflow.Node`.

#### 3.1.3. Implement `CodeAgentNode`
   - **LLM Interaction:** Replace the simulated LLM call (lines 138-152) with actual interaction using the `self.llm_client` instance. This involves:
     - Properly constructing the prompt (consider enhancing `_build_prompt`).
     - Making the actual call (e.g., `self.llm_client.invoke(prompt)` or similar, depending on the client's interface).
     - Robustly parsing the real LLM response in `_parse_llm_response` to determine the action (`call_tool`, `final_answer`, `ask_question`, etc.) and extract necessary arguments (tool name, tool args, final answer text, question text).
   - **State Management:** Ensure it correctly reads from and writes necessary information (like `tool_to_call`, `tool_arguments`, `final_answer`) to the `shared_store`.

#### 3.1.4. Implement `ToolExecutionNode`
   - **Tool Execution:** Replace the simulated tool execution (lines 230-240) with actual dynamic loading and execution:
     - Use `importlib` to load the module and class/function specified in `self.tool_registry[tool_name]`.
     - Instantiate the tool class if necessary.
     - Call the appropriate execution method/function, passing `tool_args`.
     - Handle potential exceptions during loading or execution.
     - Store the actual result or error in `shared_store["tool_result"]` or `shared_store["tool_error"]`.
   - **Confirmation:** Keep the `_confirm_execution` logic as it provides a safety mechanism (though it might need refinement for non-interactive environments).

#### 3.1.5. Implement `FormatCodeResponse` Node
   - Define a new class `FormatCodeResponse(Node)`.
   - Implement its `run(self, shared_store)` method.
   - Logic should retrieve the final answer, tool denial message, or error message from `shared_store` and format it appropriately for the user.
   - Store the final formatted string in `shared_store["final_output"]`.
   - Return an action indicating completion (e.g., "response_formatted").

#### 3.1.6. Implement `ErrorHandler` Node
   - Define a new class `ErrorHandler(Node)`.
   - Implement its `run(self, shared_store)` method.
   - Logic should retrieve error details (`tool_error`, etc.) from `shared_store`.
   - Log the error comprehensively.
   - Decide on the next step:
     - Format an error message for the user (store in `shared_store["final_output"]`).
     - Potentially attempt a retry by transitioning back to `CodeAgentNode` (requires adding state to prevent infinite loops).
     - For now, default to formatting an error message and transitioning to the end.
   - Return an appropriate action (e.g., "error_handled", "retry_attempt").

#### 3.1.7. Replace `PlaceholderFlow`
   - Remove the `PlaceholderFlow` class definition.
   - In `create_code_flow`, instantiate the flow using `pocketflow.Flow(start_node=start_node)`.

#### 3.1.8. Update `create_code_flow`
   - Ensure all nodes (`start_node`, `agent_node`, `tool_execution_node`, `format_response_node`, `error_handler_node`, `end_node`) are instantiated using their actual implemented classes inheriting from `pocketflow.Node`.
   - Define transitions using the actual PocketFlow syntax (e.g., `agent_node.add_transition("call_tool", tool_execution_node)`). Verify the syntax (`>>`, `- "action" >>`) is compatible with the library version used.
   - Return the instantiated `pocketflow.Flow` object.

### 3.2. Update `pocketcode/modes/code.py`

#### 3.2.1. Imports
   - Add/uncomment necessary imports (e.g., `from pocketflow import Flow`).

#### 3.2.2. Activate Flow Execution
   - In the `process_request` method, remove the placeholder block (lines 171-177).
   - Uncomment or add the actual flow execution call: `final_result = self._flow.run(shared_store=shared_store)` (or similar, depending on the PocketFlow `run` method's signature and return value).
   - Ensure the result from `flow.run()` (which might be the final `shared_store` or a specific output value) is correctly processed and returned.

## 4. Target Flow Diagram (Mermaid)

```mermaid
graph TD
    A[Start: StartCodeProcessing] --> B(CodeAgentNode);
    B -- final_answer --> D(FormatCodeResponse);
    B -- call_tool --> C{ExecuteTool};
    C -- tool_executed --> B;
    C -- tool_denied --> D;
    C -- tool_error --> E(ErrorHandler);
    D --> F[End: EndCodeProcessing];
    E -- error_handled --> D; // Or potentially back to B for retry
```

## 5. Testing Considerations

- Test with simple requests not requiring tools.
- Test with requests requiring tool execution (e.g., `write_to_file`).
- Test tool confirmation logic (approve/deny).
- Test error handling for invalid tool names or execution failures.
- Test interaction with the LLM (requires a configured client).