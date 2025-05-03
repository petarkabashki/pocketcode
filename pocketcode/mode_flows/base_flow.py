#%% pocketcode/mode_flows/base_flow.py
import logging
import json
import importlib
from typing import Dict, Any, Tuple, Optional, List

from pocketflow import Flow, Node

# Import interfaces for type hinting (assuming they exist)
# from pocketcode.core.interfaces import BaseLlmClient # Retrieved from shared_store

logger = logging.getLogger(__name__)

# --- Base Node ---
class BaseFlowNode(Node):
    """Base node for common initialization and logging."""
    def __init__(self, name: str, **kwargs):
        super().__init__()
        self.name = name
        logger.debug(f"BaseFlowNode '{self.name}' initialized.")

    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        """Placeholder run method. Subclasses should override."""
        logger.info(f"Running {self.name}...")
        # Default behavior might be to just continue or end, depending on node type
        return "continue" # Or None, or specific action

# --- Standard Flow Nodes ---

class BaseStartNode(BaseFlowNode):
    """Generic node to start a flow."""
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}... Flow starting.")
        # Can add initial checks here if needed (e.g., required keys in shared_store)
        return "continue"

class BaseEndNode(BaseFlowNode):
    """Generic node to end a flow."""
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}... Flow complete.")
        # Cleanup or final logging can happen here
        return None # Explicitly end the flow

class BaseErrorHandlerNode(BaseFlowNode):
    """Handles errors occurring during the flow execution."""
    def run(self, shared_store: Dict[str, Any]) -> str:
        logger.info(f"Running {self.name}...")
        error_message = shared_store.get("tool_error") or shared_store.get("error_message") or "Unknown error"
        logger.error(f"Error handled in flow by {self.name}: {error_message}")
        # Prepare a final message indicating an error occurred
        logger.debug(f"Entering {self.name}. Error message: {error_message}") # ADDED
        shared_store["final_answer"] = f"An error occurred during processing: {error_message}"
        # Clean up error flags
        shared_store.pop("tool_error", None)
        shared_store.pop("error_message", None)
        return "error_handled" # Transition to formatting

class BaseFormatResponseNode(BaseFlowNode):
    """Formats the final response or message for the user."""
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}...")
        final_output = "Process finished." # Default message

        if "final_answer" in shared_store:
            final_output = shared_store["final_answer"]
        elif "question_to_ask" in shared_store:
             # Prefix questions clearly
             final_output = f"Question: {shared_store['question_to_ask']}"
        # Errors are handled by ErrorHandler setting final_answer,
        # but we can add a fallback just in case.
        elif "tool_error" in shared_store:
             final_output = f"Process ended due to tool error: {shared_store['tool_error']}"
        elif "error_message" in shared_store:
             final_output = f"Process ended due to error: {shared_store['error_message']}"

        logger.info(f"Formatted final output by {self.name}: {final_output[:150]}...")
        shared_store["final_output"] = final_output
        # Clear intermediate states used for formatting
        # --- BEGIN ADDED LOGGING ---
        logger.debug(f"Value assigned to shared_store['final_output'] in {self.name}: {shared_store.get('final_output', '!!! KEY NOT FOUND !!!')}")
        # --- END ADDED LOGGING ---
        shared_store.pop("final_answer", None)
        shared_store.pop("question_to_ask", None)
        return "response_formatted" # Transition to end node

# --- Core Agent and Tool Nodes ---

class BaseAgentNode(BaseFlowNode):
    """
    Base node for interacting with the LLM.
    Handles prompt building, LLM calls, and response parsing.
    Relies on shared_store for dependencies (LLM client, config, tools).
    """
    def _get_llm_client(self, shared_store: Dict[str, Any]) -> Any:
        """Retrieves the LLM client from shared_store."""
        llm_client = shared_store.get("llm_client")
        if not llm_client:
            logger.error("LLM client missing from shared_store.")
            raise ValueError("LLM client not available in shared_store.")
        return llm_client

    def _get_mode_config(self, shared_store: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieves mode configuration from shared_store."""
        return shared_store.get("mode_config", {})

    def _get_tool_registry(self, shared_store: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieves the tool registry from shared_store."""
        return shared_store.get("tool_registry", {})

    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """
        Builds the prompt for the LLM.
        Subclasses should override this method for mode-specific prompt engineering.
        """
        logger.warning(f"{self.name}._build_prompt() is using the base implementation. "
                       "Consider overriding for mode-specific prompts.")

        user_request = shared_store.get("initial_request", "No user request provided.")
        formatted_cli_context = shared_store.get("formatted_cli_context", "None provided.")
        tool_registry = self._get_tool_registry(shared_store)
        available_tools = list(tool_registry.keys()) # TODO: Enhance with descriptions/schemas
        memory_bank_content = shared_store.get("memory_bank_content", "N/A")
        previous_tool_result = shared_store.get('tool_result', 'N/A')

        # Basic prompt structure - adapt as needed
        prompt_lines = [
            f"User Request: {user_request}",
            "\nContext:",
            f"  Mode: {shared_store.get('mode_name', 'Unknown')}",
            f"  CLI Context: {formatted_cli_context}",
            f"  Memory Bank Summary: {memory_bank_content}",
            f"  Previous Tool Result: {previous_tool_result}",
            f"\nAvailable Tools: {available_tools}", # Consider adding tool descriptions
            "\nTask:",
            "Based on the user request, context, memory bank, available tools, and previous results, determine the next step.",
            "Respond ONLY with a JSON object containing the action and its arguments.",
            "Possible actions:",
            "  - 'call_tool': If a tool needs to be executed.",
            "    Required keys: 'action', 'tool_name', 'arguments' (object).",
            "  - 'final_answer': If the task is complete and you have the final response.",
            "    Required keys: 'action', 'answer' (string).",
            "  - 'ask_question': If you need more information from the user.",
            "    Required keys: 'action', 'question' (string).",
            "\nJSON Response:",
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built generic LLM prompt:\n{prompt}")
        return prompt

    def _parse_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """Parses the LLM's JSON response."""
        logger.debug(f"Parsing LLM response: {response[:200]}...")
        try:
            # Attempt to find and parse JSON block robustly
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                 content_to_parse = response[json_start:json_end]
                 logger.debug(f"Attempting to parse JSON block: {content_to_parse}")
                 parsed_response = json.loads(content_to_parse)
            else:
                 # Fallback: try parsing the whole response if no clear block found
                 logger.warning("Could not find clear JSON block, attempting to parse entire response.")
                 parsed_response = json.loads(response)

            logger.debug(f"Parsed JSON: {parsed_response}")

            action = parsed_response.get("action")
            if not action:
                raise ValueError("LLM response JSON missing 'action' key.")

            args = {}
            if action == "call_tool":
                args["tool_name"] = parsed_response.get("tool_name")
                args["arguments"] = parsed_response.get("arguments", {})
                if not args["tool_name"]:
                    raise ValueError("LLM response for 'call_tool' missing 'tool_name'.")
            elif action == "final_answer":
                args["answer"] = parsed_response.get("answer")
                if not args["answer"]:
                    raise ValueError("LLM response for 'final_answer' missing 'answer'.")
            elif action == "ask_question":
                 args["question"] = parsed_response.get("question")
                 if not args["question"]:
                     raise ValueError("LLM response for 'ask_question' missing 'question'.")
            elif action not in ["call_tool", "final_answer", "ask_question"]:
                 raise ValueError(f"LLM response provided an unknown action: '{action}'")


            logger.info(f"LLM response parsed successfully. Action: '{action}', Args: {args}")
            return action, args

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse LLM response as JSON: {e}. Response: {response}"
            logger.error(error_msg)
            return "error", {"error_message": error_msg}
        except ValueError as e:
             error_msg = f"Error in parsed LLM response structure or content: {e}. Response: {response}"
             logger.error(error_msg)
             return "error", {"error_message": error_msg}
        except Exception as e:
             error_msg = f"Unexpected error parsing LLM response: {e}. Response: {response}"
             logger.error(error_msg, exc_info=True)
             return "error", {"error_message": error_msg}


    def run(self, shared_store: Dict[str, Any]) -> str:
        """Executes the agent logic: build prompt, call LLM, parse response."""
        logger.info(f"Running {self.name}...")

        try:
            # 1. Retrieve dependencies
            llm_client = self._get_llm_client(shared_store)
            mode_config = self._get_mode_config(shared_store)
            # tool_registry needed for prompt building
            self._get_tool_registry(shared_store)

            # Check if LLM is required for this mode
            requires_llm = mode_config.get('requires_llm', True)
            if not requires_llm:
                 logger.info(f"Mode '{shared_store.get('mode_name')}' does not require LLM. Skipping LLM call in {self.name}.")
                 # Decide default action - perhaps format a default response or transition?
                 shared_store["final_answer"] = "Mode does not use LLM." # Example
                 return "final_answer" # Or another appropriate transition

            # 2. Build the prompt
            prompt = self._build_prompt(shared_store)

            # 3. Call the LLM
            logger.info(f"Calling LLM via client from shared_store in {self.name}...")
            llm_response = ""
            llm_config = mode_config.get("llm_config", {})
            provider = llm_config.get("provider") # Optional, client might handle this
            model_name = llm_config.get("model")
            parameters = llm_config.get("parameters", {})

            if not model_name:
                raise ValueError("LLM 'model' name missing in mode configuration.")

            generate_args = {
                "model": model_name,
                **parameters
            }
            logger.debug(f"Calling llm_client.generate for provider '{provider}' with args: {generate_args}")

            llm_response = llm_client.generate(prompt=prompt, **generate_args)
            logger.info(f"{self.name}: LLM call successful.")
            logger.debug(f"LLM raw response: {llm_response}")

            # 4. Parse the LLM response
            action, args = self._parse_llm_response(llm_response)

            # 5. Update shared store based on action
            shared_store["last_llm_action"] = action
            if action == "call_tool":
                shared_store["tool_to_call"] = args.get("tool_name")
                shared_store["tool_arguments"] = args.get("arguments")
                logger.info(f"{self.name} decided to call tool: {shared_store['tool_to_call']}")
            elif action == "final_answer":
                shared_store["final_answer"] = args.get("answer")
                logger.info(f"{self.name} provided final answer.")
            elif action == "ask_question":
                 shared_store["question_to_ask"] = args.get("question")
                 logger.info(f"{self.name} decided to ask a question.")
            elif action == "error":
                 # Error message already logged during parsing, store it
                 shared_store["error_message"] = args.get("error_message", "Unknown parsing error")
                 logger.error(f"Error determined by {self.name} during LLM response processing: {shared_store['error_message']}")

            # Clear previous tool result before next potential tool call or final formatting
            shared_store.pop("tool_result", None)

            logger.info(f"{self.name} finished, returning action: '{action}'")
            return action

        except (ValueError, NotImplementedError, KeyError) as e:
             logger.error(f"Configuration or dependency error in {self.name}: {e}", exc_info=True)
             shared_store["error_message"] = f"{self.name} configuration/dependency error: {e}"
             return "error"
        except Exception as e:
            logger.error(f"Unexpected error during {self.name} execution: {e}", exc_info=True)
            shared_store["error_message"] = f"Unexpected error in {self.name}: {e}"
            return "error"


class BaseToolExecutionNode(BaseFlowNode):
    """
    Base node for executing tools requested by the AgentNode.
    Handles confirmation, loading, execution, and result storage.
    Relies on shared_store for dependencies (tool registry, config).
    """
    def _get_global_config(self, shared_store: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieves global configuration from shared_store."""
        return shared_store.get("global_config", {})

    def _get_tool_registry(self, shared_store: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieves the tool registry from shared_store."""
        registry = shared_store.get("tool_registry")
        if not registry:
            raise ValueError("Tool registry missing from shared_store.")
        return registry

    def _confirm_execution(self, tool_name: str, global_config: Dict) -> bool:
        """Checks configuration for tool execution confirmation."""
        core_config = global_config.get('core', {})
        require_confirmation = core_config.get('require_tool_confirmation', True) # Default to requiring confirmation
        auto_approved_tools = core_config.get('auto_approved_tools', [])

        if not require_confirmation:
            logger.debug("Tool confirmation is globally disabled. Proceeding.")
            return True
        if tool_name in auto_approved_tools:
            logger.debug(f"Tool '{tool_name}' is in auto-approved list. Proceeding.")
            return True

        # --- Interactive Confirmation (Placeholder) ---
        # In a real application, this should integrate with the UI/CLI framework
        try:
            # TODO: Replace input() with a proper UI interaction mechanism provided via shared_store or context
            logger.warning(f"Confirmation required for tool '{tool_name}'. Using basic input() prompt.")
            confirm = input(f"[Confirmation] Execute tool '{tool_name}'? (y/n): ").strip().lower()
            if confirm == 'y':
                logger.info(f"User approved execution of tool '{tool_name}'.")
                return True
            else:
                logger.warning(f"User denied execution of tool '{tool_name}'.")
                return False
        except EOFError:
             # Handle non-interactive environments gracefully
             logger.warning(f"Cannot get user confirmation for tool '{tool_name}' (EOFError/non-interactive). Denying execution.")
             return False
        except Exception as e:
             logger.error(f"Error during user confirmation prompt for tool '{tool_name}': {e}. Denying execution.", exc_info=True)
             return False
        # --- End Interactive Confirmation ---

    def _execute_tool(self, tool_name: str, tool_args: Dict, tool_registry: Dict) -> Any:
        """Finds, loads, and executes the tool using the registry."""
        logger.info(f"Attempting to execute tool '{tool_name}' with args: {tool_args}")

        tool_path = tool_registry.get(tool_name)
        if not tool_path:
            raise ValueError(f"Tool '{tool_name}' not found in registry.")

        try:
            # Expecting path like 'pocketcode.tools.filesystem.read_file'
            module_path, object_name = tool_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            # Assume the object is the callable tool function/class constructor
            ToolObjectOrFunction = getattr(module, object_name)

            # TODO: Potentially differentiate between function tools and class-based tools if needed
            logger.info(f"Found tool implementation at {tool_path}. Executing...")
            # Pass arguments using **kwargs
            result = ToolObjectOrFunction(**tool_args)
            logger.info(f"Tool '{tool_name}' executed successfully.")
            # TODO: Consider standardizing result format (e.g., always a string or dict)
            return result

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load tool '{tool_name}' from {tool_path}: {e}", exc_info=True)
            raise RuntimeError(f"Could not load tool '{tool_name}': {e}") from e
        except TypeError as e:
             logger.error(f"Argument mismatch when calling tool '{tool_name}' with args {tool_args}: {e}", exc_info=True)
             raise RuntimeError(f"Incorrect arguments provided to tool '{tool_name}': {e}") from e
        except Exception as e:
            logger.error(f"Error during execution of tool '{tool_name}': {e}", exc_info=True)
            # Propagate a more specific error if possible, otherwise generic runtime error
            raise RuntimeError(f"Error executing tool '{tool_name}': {e}") from e

    def run(self, shared_store: Dict[str, Any]) -> str:
        """Gets tool info, checks confirmation, executes tool, updates store."""
        logger.info(f"Running {self.name}...")

        tool_name = shared_store.get("tool_to_call")
        tool_args = shared_store.get("tool_arguments", {})

        if not tool_name:
            logger.error(f"{self.name} cannot run: 'tool_to_call' missing from shared store.")
            shared_store["tool_error"] = "Internal error: Tool name missing."
            return "tool_error"

        try:
            # Retrieve dependencies within the try block
            global_config = self._get_global_config(shared_store)
            tool_registry = self._get_tool_registry(shared_store)

            # 1. Confirm Execution
            if self._confirm_execution(tool_name, global_config):
                # 2. Execute Tool
                result = self._execute_tool(tool_name, tool_args, tool_registry)
                shared_store["tool_result"] = result # Store the raw result
                logger.info(f"Tool '{tool_name}' execution successful, result stored.")
                # Clear the request flags for the tool that just ran
                shared_store.pop("tool_to_call", None)
                shared_store.pop("tool_arguments", None)
                return "tool_executed" # Transition back to AgentNode
            else:
                # Execution denied
                denial_message = f"Execution of tool '{tool_name}' denied by user or configuration."
                shared_store["tool_error"] = denial_message # Store reason for denial
                logger.warning(denial_message)
                 # Clear the request flags even if denied
                shared_store.pop("tool_to_call", None)
                shared_store.pop("tool_arguments", None)
                return "tool_denied" # Transition to FormatResponseNode

        except (ValueError, RuntimeError, TypeError) as e:
            # Catch errors from dependency retrieval or tool execution/loading
            logger.error(f"Error during {self.name} for tool '{tool_name}': {e}", exc_info=False) # Log concisely
            shared_store["tool_error"] = f"Failed during processing for tool '{tool_name}': {e}"
             # Clear the request flags on error
            shared_store.pop("tool_to_call", None)
            shared_store.pop("tool_arguments", None)
            return "tool_error" # Transition to ErrorHandlerNode
        except Exception as e:
            # Catch unexpected errors
            logger.error(f"Unexpected error in {self.name} for tool '{tool_name}': {e}", exc_info=True)
            shared_store["tool_error"] = f"Unexpected error processing tool '{tool_name}': {e}"
             # Clear the request flags on error
            shared_store.pop("tool_to_call", None)
            shared_store.pop("tool_arguments", None)
            return "tool_error" # Transition to ErrorHandlerNode


# --- Base Flow Creation Function ---

def create_base_flow(
    start_node: BaseStartNode,
    agent_node: BaseAgentNode,
    tool_node: BaseToolExecutionNode,
    format_node: BaseFormatResponseNode,
    error_node: BaseErrorHandlerNode,
    end_node: BaseEndNode
) -> Flow:
    """
    Wires together the standard flow nodes into a PocketFlow instance.

    Args:
        start_node: The node to begin the flow.
        agent_node: The node handling LLM interaction.
        tool_node: The node handling tool execution.
        format_node: The node for formatting the final response.
        error_node: The node for handling errors.
        end_node: The node to terminate the flow.

    Returns:
        A configured PocketFlow.Flow instance.
    """
    logger.info("Wiring base flow structure...")

    # Define transitions
    start_node - "continue" >> agent_node

    agent_node - "call_tool" >> tool_node
    agent_node - "final_answer" >> format_node
    agent_node - "ask_question" >> format_node
    agent_node - "error" >> error_node # Errors from agent (config, LLM call, parsing)

    tool_node - "tool_executed" >> agent_node # Loop back after successful execution
    tool_node - "tool_denied" >> format_node # Go to format if user denies
    tool_node - "tool_error" >> error_node # Errors from tool (confirmation, loading, execution)

    error_node - "error_handled" >> format_node # Always format after handling error

    format_node - "response_formatted" >> end_node # End after formatting

    # Create the flow instance
    flow = Flow(start=start_node)
    logger.info("Base flow structure wired successfully.")
    return flow