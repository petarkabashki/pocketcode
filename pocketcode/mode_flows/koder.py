#%% pocketcode/flows/koder.py
import logging
import json
from typing import Dict, Any, Tuple, Optional
import importlib

from pocketflow import Flow, Node

# Import the LLM client interface (used for type hinting)
# BaseLlmClient is retrieved from shared_store now, so direct import might not be needed here
# from pocketcode.core.interfaces import BaseLlmClient

logger = logging.getLogger(__name__)

# --- Base Node ---
class BaseCodeFlowNode(Node):
    """Base node for common initialization."""
    def __init__(self, name: str, **kwargs):
        super().__init__()
        self.name = name
        logger.debug(f"{self.name} initialized.")

# --- Start and End Nodes (Unchanged) ---
class StartCodeProcessing(BaseCodeFlowNode):
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}...")
        # Ensure essential dependencies are present early? Optional.
        # llm_client = shared_store.get("llm_client")
        # if not llm_client and shared_store.get("mode_config", {}).get("requires_llm", True):
        #     logger.error(f"LLM client missing in shared_store at {self.name}.")
        #     shared_store["error_message"] = "Flow start error: LLM client not available."
        #     return "error"
        return "continue"

class EndCodeProcessing(BaseCodeFlowNode):
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}... Flow complete.")
        return None

# --- Modified CodeAgentNode ---
class CodeAgentNode(BaseCodeFlowNode):
    """
    Interacts with LLM using dependencies from shared_store.
    """
    # REMOVED llm_client from __init__
    def __init__(self, name="CodeAgentNode", **kwargs):
        super().__init__(name=name, **kwargs)
        # self.llm_client is no longer stored here
        logger.info(f"{self.name} initialized (dependencies accessed via shared_store).")

    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt using info from shared_store."""
        user_request = shared_store.get("initial_request", "No user request provided.")
        # context = shared_store.get("context", {}) # Original context if needed
        formatted_cli_context = shared_store.get("formatted_cli_context") # Assuming this is still prepared elsewhere
        tool_registry = shared_store.get("tool_registry", {}) # Get from store
        available_tools = list(tool_registry.keys()) # TODO: Add tool descriptions/schemas

        # TODO: Implement robust prompt engineering using mode_config, memory bank content etc. from shared_store
        memory_bank_content = shared_store.get("memory_bank_content", "N/A") # Example access
        mode_config = shared_store.get("mode_config", {}) # Example access

        prompt_lines = [
            f"User Request: {user_request}",
            "\nContext:",
            f"  Mode: {shared_store.get('mode_name', 'Unknown')}",
            f"  CLI Context: {formatted_cli_context or 'None provided.'}",
            f"  Previous Tool Result: {shared_store.get('tool_result', 'N/A')}",
            f"  Memory Bank Summary: {memory_bank_content}", # Add relevant context
            f"\nAvailable Tools: {available_tools}",
            "\nBased on the user request, context, and previous results, determine the next step.",
            "Respond in JSON format.",
            "If a tool needs to be called, provide 'action': 'call_tool', 'tool_name': <name>, 'arguments': {<args>}.",
            "If the task is complete, provide 'action': 'final_answer', 'answer': <final message>.",
            "If you need more information, provide 'action': 'ask_question', 'question': <question text>."
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built LLM prompt:\n{prompt}")
        return prompt

    def _parse_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """Parses the LLM's JSON response (Unchanged)."""
        logger.debug(f"Parsing LLM response: {response[:200]}...")
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                 parsed_response = json.loads(response[json_start:json_end])
                 logger.debug(f"Parsed JSON: {parsed_response}")
            else:
                 parsed_response = json.loads(response)
                 logger.debug(f"Parsed JSON (fallback): {parsed_response}")

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

            logger.info(f"LLM response parsed as action: '{action}', args: {args}")
            return action, args

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}\nResponse: {response}")
            return "error", {"error_message": f"LLM response was not valid JSON: {e}"}
        except ValueError as e:
             logger.error(f"Error in parsed LLM response structure: {e}\nResponse: {response}")
             return "error", {"error_message": f"LLM response JSON structure invalid: {e}"}


    def run(self, shared_store: Dict[str, Any]) -> str:
        """Executes the agent logic using dependencies from shared_store."""
        logger.info(f"Running {self.name}...")

        # --- Retrieve dependencies from shared_store ---
        llm_client = shared_store.get("llm_client")
        mode_config = shared_store.get("mode_config", {})
        # tool_registry = shared_store.get("tool_registry", {}) # Needed for prompt building

        # Check if LLM is required and available
        requires_llm = mode_config.get('requires_llm', True)
        if requires_llm and not llm_client:
             logger.error(f"LLM client missing from shared_store but required for mode '{shared_store.get('mode_name')}'.")
             shared_store["error_message"] = f"{self.name} error: Required LLM client not available."
             return "error"
        # --- End Dependency Retrieval ---

        # 1. Build the prompt
        prompt = self._build_prompt(shared_store)

        # If no LLM is needed/available, perhaps transition differently?
        if not requires_llm:
             logger.info(f"Mode '{shared_store.get('mode_name')}' does not require LLM. Skipping LLM call.")
             # Decide default action - maybe format a default response or error?
             shared_store["final_answer"] = "Mode does not use LLM." # Example
             return "final_answer"

        # 2. Call the LLM using the generic interface from shared_store
        try:
            logger.info("Calling LLM via client from shared_store...")
            llm_response = ""

            llm_config = mode_config.get("llm_config", {}) # Get LLM config from mode_config
            provider = llm_config.get("provider")
            model_name = llm_config.get("model")
            parameters = llm_config.get("parameters", {})

            if not model_name:
                raise ValueError("LLM 'model' name missing in mode configuration.")

            generate_args = {
                "model": model_name,
                **parameters
            }
            logger.debug(f"Calling llm_client.generate for provider '{provider}' with args: {generate_args}")

            # Use the llm_client retrieved from shared_store
            llm_response = llm_client.generate(prompt=prompt, **generate_args)

            logger.info("LLM call successful.")
            logger.debug(f"LLM raw response: {llm_response}")
        except (ValueError, NotImplementedError) as e:
             logger.error(f"Configuration or wrapper error during LLM call: {e}", exc_info=True)
             shared_store["error_message"] = f"LLM configuration/wrapper error: {e}"
             return "error"
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            shared_store["error_message"] = f"LLM invocation failed: {e}"
            return "error"

        # 3. Parse the LLM response
        action, args = self._parse_llm_response(llm_response)

        # 4. Update shared store based on action (Unchanged logic)
        shared_store["last_llm_action"] = action
        if action == "call_tool":
            shared_store["tool_to_call"] = args.get("tool_name")
            shared_store["tool_arguments"] = args.get("arguments")
            logger.info(f"Node decided to call tool: {shared_store['tool_to_call']}")
        elif action == "final_answer":
            shared_store["final_answer"] = args.get("answer")
            logger.info("Node provided final answer.")
        elif action == "ask_question":
             shared_store["question_to_ask"] = args.get("question")
             logger.info("Node decided to ask a question.")
        elif action == "error":
             shared_store["error_message"] = args.get("error_message", "Unknown parsing error")
             logger.error(f"Error determined during LLM response parsing: {shared_store['error_message']}")

        shared_store.pop("tool_result", None) # Clear previous tool result

        logger.info(f"{self.name} finished, returning action: '{action}'")
        return action
# --- End Modified CodeAgentNode ---


# --- Modified ToolExecutionNode ---
class ToolExecutionNode(BaseCodeFlowNode):
    """Executes tools using dependencies from shared_store."""
    # REMOVED global_config and tool_registry from __init__
    def __init__(self, name="ToolExecutionNode", **kwargs):
        super().__init__(name=name, **kwargs)
        # self.global_config and self.tool_registry are no longer stored here
        logger.info(f"{self.name} initialized (dependencies accessed via shared_store).")

    # Modified to accept dependencies from shared_store via args
    def _confirm_execution(self, tool_name: str, global_config: Dict) -> bool:
        """Checks configuration (from shared_store) for confirmation."""
        core_config = global_config.get('core', {})
        require_confirmation = core_config.get('require_tool_confirmation', True)
        auto_approved_tools = core_config.get('auto_approved_tools', [])

        if not require_confirmation:
            logger.info("Tool confirmation is globally disabled. Proceeding.")
            return True
        if tool_name in auto_approved_tools:
            logger.info(f"Tool '{tool_name}' is in auto-approved list. Proceeding.")
            return True

        try:
            # TODO: Replace input() with proper UI interaction mechanism
            logger.warning(f"Confirmation required for tool '{tool_name}'. Attempting interactive prompt.")
            confirm = input(f"[Confirmation] Allow execution of tool '{tool_name}'? (y/n): ").strip().lower()
            if confirm == 'y':
                logger.info(f"User approved execution of tool '{tool_name}'.")
                return True
            else:
                logger.warning(f"User denied execution of tool '{tool_name}'.")
                return False
        except EOFError:
             logger.warning(f"Cannot get user confirmation for tool '{tool_name}' (EOFError/non-interactive). Denying execution.")
             return False
        except Exception as e:
             logger.error(f"Error during user confirmation prompt for tool '{tool_name}': {e}. Denying execution.", exc_info=True)
             return False

    # Modified to accept tool_registry from shared_store via args
    def _execute_tool(self, tool_name: str, tool_args: Dict, tool_registry: Dict) -> Any:
        """Finds, loads, and executes the tool using registry from shared_store."""
        logger.info(f"Attempting to execute tool '{tool_name}' with args: {tool_args}")
        if not tool_registry:
             raise RuntimeError("Tool registry is not available in shared_store.")

        tool_path = tool_registry.get(tool_name)
        if not tool_path:
            raise ValueError(f"Tool '{tool_name}' not found in registry.")

        try:
            module_path, object_name = tool_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            ToolObject = getattr(module, object_name)

            # Assuming tool is a function for simplicity
            logger.info(f"Found tool implementation at {tool_path}. Executing...")
            result = ToolObject(**tool_args)
            logger.info(f"Tool '{tool_name}' executed successfully.")
            return result

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load tool '{tool_name}' from {tool_path}: {e}", exc_info=True)
            raise RuntimeError(f"Could not load tool '{tool_name}': {e}") from e
        except Exception as e:
            logger.error(f"Error during execution of tool '{tool_name}': {e}", exc_info=True)
            raise RuntimeError(f"Error executing tool '{tool_name}': {e}") from e

    def run(self, shared_store: Dict[str, Any]) -> str:
        """Gets tool info, checks confirmation, executes tool, updates store."""
        logger.info(f"Running {self.name}...")

        # --- Retrieve dependencies from shared_store ---
        global_config = shared_store.get("global_config")
        tool_registry = shared_store.get("tool_registry")
        tool_name = shared_store.get("tool_to_call")
        tool_args = shared_store.get("tool_arguments", {})

        if not tool_name:
            logger.error(f"{self.name} cannot run: 'tool_to_call' missing from shared store.")
            shared_store["tool_error"] = "Tool name missing."
            return "tool_error"
        if not tool_registry:
             logger.error(f"{self.name} cannot run: Tool registry missing from shared_store.")
             shared_store["tool_error"] = "Tool registry misconfiguration."
             return "tool_error"
        if not global_config:
             logger.warning(f"{self.name} running without global_config in shared_store.")
             # Decide if this is an error or can proceed with defaults
             global_config = {} # Use empty dict to avoid errors in _confirm_execution
        # --- End Dependency Retrieval ---

        # Perform confirmation check using retrieved global_config
        if self._confirm_execution(tool_name, global_config):
            try:
                # Execute the tool using retrieved tool_registry
                result = self._execute_tool(tool_name, tool_args, tool_registry)
                shared_store["tool_result"] = result
                logger.info(f"Tool '{tool_name}' execution successful.")
                return "tool_executed"
            except Exception as e:
                logger.error(f"Caught error during tool execution for '{tool_name}': {e}", exc_info=False)
                shared_store["tool_error"] = f"Execution failed for tool '{tool_name}': {e}"
                return "tool_error"
        else:
            denial_message = f"Execution of tool '{tool_name}' denied by user or config."
            shared_store["tool_error"] = denial_message
            logger.warning(denial_message)
            return "tool_denied"
# --- End Modified ToolExecutionNode ---


# --- FormatCodeResponse Node (Unchanged) ---
class FormatCodeResponse(BaseCodeFlowNode):
    """Formats the final response or message for the user."""
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}...")
        final_output = "No final output generated."

        if "final_answer" in shared_store:
            final_output = shared_store["final_answer"]
        elif "question_to_ask" in shared_store:
             final_output = f"Question: {shared_store['question_to_ask']}"
        elif "tool_error" in shared_store:
             final_output = f"Process ended: {shared_store['tool_error']}"
        elif "error_message" in shared_store:
             final_output = f"An error occurred: {shared_store['error_message']}"

        logger.info(f"Formatted final output: {final_output[:100]}...")
        shared_store["final_output"] = final_output
        return "response_formatted"

# --- ErrorHandler Node (Unchanged) ---
class ErrorHandler(BaseCodeFlowNode):
    """Handles errors occurring during the flow execution."""
    def run(self, shared_store: Dict[str, Any]) -> str:
        logger.info(f"Running {self.name}...")
        error_message = shared_store.get("tool_error") or shared_store.get("error_message") or "Unknown error"
        logger.error(f"Error handled in flow: {error_message}")
        shared_store["final_answer"] = f"An error occurred during processing: {error_message}"
        shared_store.pop("tool_error", None)
        shared_store.pop("error_message", None)
        return "error_handled"


# --- Modified create_code_flow ---
# REMOVED arguments: mode_config, global_config, tool_registry, llm_client
def create_koder_flow():
    """
    Creates the PocketFlow instance structure for the Code Mode.
    Dependencies are injected into the shared_store by the ModeManager.
    """
    logger.info("Creating PocketFlow structure for Code Mode...")

    # Define nodes - REMOVED dependency injection during instantiation
    start_node = StartCodeProcessing(name="StartCodeProcessing")
    agent_node = CodeAgentNode(name="CodeAgentNode")
    tool_execution_node = ToolExecutionNode(name="ExecuteTool")
    format_response_node = FormatCodeResponse(name="FormatCodeResponse")
    error_handler_node = ErrorHandler(name="ErrorHandler")
    end_node = EndCodeProcessing(name="EndCodeProcessing")

    # Define flow transitions (Unchanged)
    start_node - "continue" >> agent_node

    agent_node - "call_tool" >> tool_execution_node
    agent_node - "final_answer" >> format_response_node
    agent_node - "ask_question" >> format_response_node
    agent_node - "error" >> error_handler_node

    tool_execution_node - "tool_executed" >> agent_node
    tool_execution_node - "tool_denied" >> format_response_node
    tool_execution_node - "tool_error" >> error_handler_node

    error_handler_node - "error_handled" >> format_response_node

    format_response_node - "response_formatted" >> end_node

    # Create the flow structure
    code_flow = Flow(start=start_node)

    logger.info("Code Mode PocketFlow structure created.")
    return code_flow
# --- End modified create_code_flow ---