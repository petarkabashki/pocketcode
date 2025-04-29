#%% pocketcode/flows/code.py
import logging
from typing import Dict, Any, Tuple, Optional # Added Optional
import importlib # Added for dynamic tool loading

# Assuming pocketflow is installed and Flow/Node are importable
# from pocketflow import Flow, Node # Placeholder

# Removed agent import: from pocketcode.agents.code_agent import CodeAgent

logger = logging.getLogger(__name__)

# Placeholder Node definitions (replace with actual node implementations)
class PlaceholderNode:
    """Represents a placeholder for an actual PocketFlow Node."""
    def __init__(self, name="PlaceholderNode", **kwargs): # Added **kwargs to accept unused args
        self.name = name
        self._transitions = {}
        logger.debug(f"{self.name} initialized.")

    def __rshift__(self, other):
        """Placeholder for defining default transitions."""
        logger.debug(f"Defining transition: {self.name} >> {getattr(other, 'name', 'Unknown')}")
        self._transitions["default"] = other
        return other # Allow chaining

    def __sub__(self, action_name):
        """Placeholder for defining named action transitions."""
        class TransitionBuilder:
            def __init__(self, source_node, action):
                self._source = source_node
                self._action = action
            def __rshift__(self, target_node):
                logger.debug(f"Defining transition: {self._source.name} - '{self._action}' >> {getattr(target_node, 'name', 'Unknown')}")
                self._source._transitions[self._action] = target_node
                return target_node
        return TransitionBuilder(self, action_name)

    def run(self, shared_store: Dict[str, Any]) -> str:
        """Placeholder run method for a node."""
        logger.info(f"Running {self.name} (placeholder)...")
        action = "default" # Default action for placeholders
        # Simulate some work or decision
        if "tool_to_call" in shared_store and self.name == "ExecuteTool":
             # Simulate tool execution outcome
             shared_store["tool_result"] = f"Placeholder result for {shared_store.get('tool_to_call')}"
             action = "tool_executed" # Simulate successful execution
        elif self.name == "FormatCodeResponse":
             shared_store["final_output"] = shared_store.get("final_answer", "Placeholder final response.")
             action = "response_formatted" # Action leading to end
        logger.info(f"{self.name} finished, returning action: '{action}'")
        return action

# --- Modified CodeAgentNode with Embedded Logic ---
class CodeAgentNode(PlaceholderNode):
    """
    A PocketFlow Node that handles code-related tasks by interacting
    with an LLM and deciding on subsequent actions (like tool use).
    """
    def __init__(self, name="CodeAgentNode", llm_client: Any = None, **kwargs): # Added **kwargs
        """
        Initializes the CodeAgentNode.

        Args:
            name: The name of the node.
            llm_client: An object capable of making LLM calls. Placeholder for now.
        """
        super().__init__(name, **kwargs) # Pass kwargs up
        self.llm_client = llm_client
        logger.info(f"{self.name} initialized.")
        if not self.llm_client:
            logger.warning(f"{self.name} initialized without a live LLM client. Will simulate responses.")

    def _build_prompt(self, user_request: str, context: Dict[str, Any]) -> str:
        """Builds the prompt to send to the LLM."""
        # TODO: Implement robust prompt engineering.
        prompt = f"""
User Request: {user_request}

Context:
{context.get('file_content', 'No file content provided.')}
{context.get('project_structure', 'No project structure provided.')}
{context.get('memory_bank', 'No memory bank context provided.')}

Available Tools: [List available tools here]

Based on the user request and context, determine the next step.
If a tool needs to be called, respond with the tool name and arguments in JSON format.
If the task is complete, respond with the final answer.
If you need more information, ask a clarifying question.
"""
        logger.debug("Built LLM prompt.")
        return prompt.strip()

    def _parse_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parses the LLM response to determine the action and arguments.
        """
        # TODO: Implement robust LLM response parsing.
        logger.debug(f"Parsing LLM response: {response[:100]}...")

        # --- Simulation ---
        # Simple check for tool call structure in the simulated response
        if '"tool_name":' in response and '"arguments":' in response:
             action = "call_tool"
             # Simulate extracting the specific tool name and args from the example
             if '"tool_name": "write_to_file"' in response:
                 args = {"tool_name": "write_to_file", "arguments": {"path": "example.py", "content": "print('Hello, Modified World!')"}}
             else:
                 args = {"tool_name": "placeholder_tool", "arguments": {"arg1": "value1"}}
             logger.info(f"LLM response parsed as action: {action}, args: {args}")
             return action, args
        else:
             action = "final_answer"
             args = {"answer": response}
             logger.info(f"LLM response parsed as action: {action}")
             return action, args
        # --- End Simulation ---

    def run(self, shared_store: Dict[str, Any]) -> str:
        """
        Executes the agent logic using data from the shared store.

        Args:
            shared_store: The dictionary holding flow state.

        Returns:
            The action determined by the agent ('call_tool', 'final_answer', etc.).
        """
        logger.info(f"Running {self.name}...")
        user_request = shared_store.get("initial_request", "No user request found.") # Use initial_request
        context = shared_store.get("context", {})

        # 1. Build the prompt
        prompt = self._build_prompt(user_request, context)

        # 2. Call the LLM (Simulated)
        logger.info("Simulating LLM call...")
        # In a real scenario: llm_response = self.llm_client.invoke(prompt)
        # Simulate a response that requests a tool call
        simulated_llm_response = """
Okay, I need to modify the file 'example.py'. I will use the 'write_to_file' tool.
```json
{
  "tool_name": "write_to_file",
  "arguments": {
    "path": "example.py",
    "content": "print('Hello, Modified World!')"
  }
}
```
"""
        logger.info("LLM call simulation complete.")

        # 3. Parse the LLM response
        action, args = self._parse_llm_response(simulated_llm_response)

        # 4. Update shared store based on action
        if action == "call_tool":
            shared_store["tool_to_call"] = args.get("tool_name")
            shared_store["tool_arguments"] = args.get("arguments")
            logger.info(f"Node decided to call tool: {shared_store['tool_to_call']}")
        elif action == "final_answer":
            shared_store["final_answer"] = args.get("answer")
            logger.info("Node provided final answer.")
        # Add handling for other actions if needed

        logger.info(f"{self.name} finished, returning action: '{action}'")
        return action
# --- End Modified CodeAgentNode ---


# --- Added ToolExecutionNode ---
class ToolExecutionNode(PlaceholderNode):
    """
    Executes a tool requested by the LLM, performing confirmation checks.
    """
    def __init__(self, name="ToolExecutionNode", global_config: Optional[Dict] = None, tool_registry: Optional[Dict] = None, **kwargs):
        super().__init__(name, **kwargs)
        self.global_config = global_config if global_config else {}
        self.tool_registry = tool_registry if tool_registry else {}
        logger.info(f"{self.name} initialized.")
        if not self.global_config:
            logger.warning(f"{self.name} initialized without global_config.")
        if not self.tool_registry:
            logger.warning(f"{self.name} initialized without tool_registry.")

    def _confirm_execution(self, tool_name: str) -> bool:
        """Checks configuration and prompts user if confirmation is needed."""
        core_config = self.global_config.get('core', {})
        require_confirmation = core_config.get('require_tool_confirmation', True) # Default to True
        auto_approved_tools = core_config.get('auto_approved_tools', [])

        if not require_confirmation:
            logger.info("Tool confirmation is globally disabled. Proceeding.")
            return True # Confirmation globally disabled

        if tool_name in auto_approved_tools:
            logger.info(f"Tool '{tool_name}' is in auto-approved list. Proceeding.")
            return True # Tool is specifically auto-approved

        # If we reach here, confirmation is required and tool is not auto-approved
        try:
            confirm = input(f"[Confirmation] Allow execution of tool '{tool_name}'? (y/n): ").strip().lower()
            if confirm == 'y':
                logger.info(f"User approved execution of tool '{tool_name}'.")
                return True
            else:
                logger.warning(f"User denied execution of tool '{tool_name}'.")
                return False
        except EOFError: # Handle non-interactive environments
             logger.warning(f"Cannot get user confirmation for tool '{tool_name}' (EOFError). Denying execution.")
             return False


    def _execute_tool(self, tool_name: str, tool_args: Dict) -> Any:
        """Finds and executes the tool."""
        logger.info(f"Attempting to execute tool '{tool_name}' with args: {tool_args}")
        tool_path = self.tool_registry.get(tool_name)
        if not tool_path:
            logger.error(f"Tool '{tool_name}' not found in registry.")
            raise ValueError(f"Tool '{tool_name}' not registered.")

        try:
            # Dynamically import the tool class/function
            module_path, class_name = tool_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            ToolClass = getattr(module, class_name)

            # TODO: Instantiate and call the tool appropriately.
            # This might involve checking if it's a class or function,
            # passing arguments, handling potential exceptions.
            # For now, just log and return a placeholder result.
            logger.info(f"Found tool implementation at {tool_path}. Simulating execution...")
            # Example (if it were a class with an 'execute' method):
            # tool_instance = ToolClass()
            # result = tool_instance.execute(**tool_args)
            result = f"Simulated successful execution of {tool_name}"
            logger.info(f"Tool '{tool_name}' executed successfully (simulated).")
            return result

        except (ImportError, AttributeError, Exception) as e:
            logger.error(f"Failed to load or execute tool '{tool_name}' from {tool_path}: {e}", exc_info=True)
            raise RuntimeError(f"Error executing tool '{tool_name}': {e}") from e

    def run(self, shared_store: Dict[str, Any]) -> str:
        """Gets tool info, checks confirmation, executes tool, updates store."""
        logger.info(f"Running {self.name}...")
        tool_name = shared_store.get("tool_to_call")
        tool_args = shared_store.get("tool_arguments", {})

        if not tool_name:
            logger.error(f"{self.name} cannot run: 'tool_to_call' missing from shared store.")
            shared_store["tool_error"] = "Tool name missing."
            return "tool_error" # Or a more specific error action

        # Perform confirmation check
        if self._confirm_execution(tool_name):
            try:
                # Execute the tool
                result = self._execute_tool(tool_name, tool_args)
                shared_store["tool_result"] = result
                logger.info(f"Tool '{tool_name}' execution successful.")
                return "tool_executed"
            except Exception as e:
                logger.error(f"Error during tool execution for '{tool_name}': {e}", exc_info=True)
                shared_store["tool_error"] = str(e)
                return "tool_error"
        else:
            # User denied confirmation
            shared_store["tool_error"] = f"Execution of tool '{tool_name}' denied by user."
            return "tool_denied"
# --- End ToolExecutionNode ---


# Placeholder Flow definition
class PlaceholderFlow:
    """Represents a placeholder for an actual PocketFlow Flow."""
    def __init__(self, start_node):
        self.start_node = start_node
        logger.debug(f"PlaceholderFlow initialized with start node: {getattr(start_node, 'name', 'Unknown')}")

    def run(self, shared_store: Dict[str, Any]):
        """Placeholder run method for the flow."""
        logger.info(f"Running PlaceholderFlow starting from {getattr(self.start_node, 'name', 'Unknown')}...")
        current_node = self.start_node
        step = 0
        max_steps = 10 # Prevent infinite loops in placeholder

        while current_node and step < max_steps:
            logger.info(f"--- Flow Step {step + 1}: Running Node '{getattr(current_node, 'name', 'Unknown')}' ---")
            action = current_node.run(shared_store) # Call the node's run method
            logger.info(f"Node '{getattr(current_node, 'name', 'Unknown')}' returned action: '{action}'")

            # Find the next node based on the action returned by the current node
            next_node = getattr(current_node, '_transitions', {}).get(action)

            if next_node:
                logger.info(f"Transitioning via action '{action}' to node: {getattr(next_node, 'name', 'Unknown')}")
                current_node = next_node
            else:
                # Check for a default transition if specific action transition not found
                default_next_node = getattr(current_node, '_transitions', {}).get('default')
                if default_next_node:
                     logger.info(f"No transition for action '{action}', using default transition to node: {getattr(default_next_node, 'name', 'Unknown')}")
                     current_node = default_next_node
                else:
                     logger.info(f"No transition defined for action '{action}' or default from node '{getattr(current_node, 'name', 'Unknown')}'. Flow ending.")
                     current_node = None
            step += 1

        if step >= max_steps:
             logger.warning("PlaceholderFlow reached max steps limit.")
        logger.info("PlaceholderFlow finished.")


# --- Modified create_code_flow signature and implementation ---
def create_code_flow(mode_config: Dict[str, Any], global_config: Dict[str, Any], tool_registry: Dict[str, str]):
    """
    Creates the PocketFlow instance specifically for the Code Mode.

    Args:
        mode_config: Configuration specific to this mode.
        global_config: The overall application configuration.
        tool_registry: Dictionary mapping tool names to their implementation paths.
    """
    logger.info("Creating PocketFlow for Code Mode...")
    # TODO: Replace placeholders with actual PocketFlow Nodes and Flow
    # TODO: Implement node for Response formatting

    # Define nodes
    start_node = PlaceholderNode("StartCodeProcessing")
    llm_client = mode_config.get("llm_client") # Get LLM client if configured for the mode
    agent_node = CodeAgentNode("CodeAgentNode", llm_client=llm_client)
    # Instantiate the actual ToolExecutionNode, passing config and registry
    tool_execution_node = ToolExecutionNode(
        "ExecuteTool",
        global_config=global_config,
        tool_registry=tool_registry
    )
    format_response_node = PlaceholderNode("FormatCodeResponse")
    error_handler_node = PlaceholderNode("ErrorHandler") # Added placeholder for errors
    end_node = PlaceholderNode("EndCodeProcessing")

    # Define flow transitions
    start_node >> agent_node
    agent_node - "call_tool" >> tool_execution_node
    agent_node - "final_answer" >> format_response_node

    # Transitions from ToolExecutionNode
    tool_execution_node - "tool_executed" >> agent_node # Loop back to agent after successful execution
    tool_execution_node - "tool_denied" >> format_response_node # Go format response/message about denial
    tool_execution_node - "tool_error" >> error_handler_node # Go to error handler on execution failure

    format_response_node >> end_node
    error_handler_node >> end_node # End after handling error (or loop back if retry is possible)


    # Create the placeholder flow
    code_flow = PlaceholderFlow(start_node=start_node)

    logger.info("Code Mode PocketFlow created.")
    return code_flow
# --- End modified create_code_flow ---