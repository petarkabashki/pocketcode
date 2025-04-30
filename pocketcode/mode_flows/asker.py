#%% pocketcode/flows/asker.py
import logging
import json
from typing import Dict, Any, Tuple, Optional
import importlib

from pocketflow import Flow, Node

# Import the LLM client interface (used for type hinting)
# BaseLlmClient is retrieved from shared_store now, so direct import might not be needed here
# from pocketcode.core.interfaces import BaseLlmClient

logger = logging.getLogger(__name__) # Use current module name

# --- Base Node ---
class BaseAskerFlowNode(Node): # Renamed
    """Base node for common initialization in Asker flow."""
    def __init__(self, name: str, **kwargs):
        super().__init__()
        self.name = name
        logger.debug(f"{self.name} initialized.")

# --- Start and End Nodes ---
class StartAskerProcessing(BaseAskerFlowNode): # Renamed
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}...")
        # Optional: Add any Asker-specific startup checks here
        return "continue"

class EndAskerProcessing(BaseAskerFlowNode): # Renamed
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}... Asker flow complete.")
        return None

# --- Asker Agent Node ---
class AskerAgentNode(BaseAskerFlowNode): # Renamed
    """
    Interacts with LLM using dependencies from shared_store for the Asker mode.
    """
    def __init__(self, name="AskerAgentNode", **kwargs): # Renamed default name
        super().__init__(name=name, **kwargs)
        logger.info(f"{self.name} initialized (dependencies accessed via shared_store).")

    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt using info from shared_store for Asker mode."""
        user_request = shared_store.get("initial_request", "No user request provided.")
        formatted_cli_context = shared_store.get("formatted_cli_context")
        tool_registry = shared_store.get("tool_registry", {})
        # Get allowed tools specifically for this mode from mode_config if available
        mode_config = shared_store.get("mode_config", {})
        allowed_tools_config = mode_config.get("allowed_tools", [])
        # If allowed_tools are defined, use them, otherwise fall back to registry keys (less ideal)
        available_tools = allowed_tools_config if allowed_tools_config else list(tool_registry.keys())
        # TODO: Fetch tool descriptions/schemas for better prompting

        memory_bank_content = shared_store.get("memory_bank_content", "N/A")

        # Asker-specific role definition integrated into the prompt
        role_definition = "You are Roo, a helpful assistant designed to answer questions about the codebase or other topics. You can read files, search through the project, and list directory contents to gather information for your answers. Use the available tools to find the information needed."

        prompt_lines = [
            role_definition, # Added role definition
            f"\nUser Request: {user_request}",
            "\nContext:",
            f"  Mode: {shared_store.get('mode_name', 'Asker')}", # Default to Asker
            f"  CLI Context: {formatted_cli_context or 'None provided.'}",
            f"  Previous Tool Result: {shared_store.get('tool_result', 'N/A')}",
            f"  Memory Bank Summary: {memory_bank_content}",
            f"\nAvailable Tools: {available_tools}", # Use potentially filtered list
            "\nBased on the user request and context, determine the next step to answer the question.",
            "Respond ONLY in JSON format.", # Emphasize JSON only
            "The JSON object must have an 'action' key.",
            "If a tool needs to be called, provide 'action': 'call_tool', 'tool_name': <name>, 'arguments': {<args>}.",
            "If the question can be answered directly, provide 'action': 'final_answer', 'answer': <your final answer>.",
            "If you need clarification from the user, provide 'action': 'ask_question', 'question': <your question>."
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built Asker LLM prompt:\n{prompt}")
        return prompt

    def _parse_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """Parses the LLM's JSON response."""
        logger.debug(f"Parsing LLM response: {response[:200]}...")
        try:
            # Attempt to find and parse JSON block, handling potential markdown fences
            json_match = None
            if '```json' in response:
                json_start = response.find('```json') + len('```json')
                json_end = response.find('```', json_start)
                if json_end != -1:
                    json_content = response[json_start:json_end].strip()
                    json_match = json.loads(json_content)
            elif response.strip().startswith('{') and response.strip().endswith('}'):
                 json_match = json.loads(response.strip()) # Assume raw JSON if starts/ends with {}
            else: # Fallback: find first '{' and last '}'
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                     json_match = json.loads(response[json_start:json_end])

            if not json_match:
                 raise json.JSONDecodeError("Could not find or parse JSON block in response.", response, 0)

            parsed_response = json_match
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
                 raise ValueError(f"Invalid 'action' value received: {action}")


            logger.info(f"LLM response parsed as action: '{action}', args: {args}")
            return action, args

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}\nResponse: {response}")
            # Try to provide a more helpful error message if possible
            error_detail = f"LLM response was not valid JSON or JSON block not found: {e}"
            # Return a generic final answer indicating the failure
            shared_store["final_answer"] = f"Error: Could not understand the response from the AI assistant. Details: {error_detail}"
            return "final_answer", {"answer": shared_store["final_answer"]} # Force final answer on parse failure
        except ValueError as e:
             logger.error(f"Error in parsed LLM response structure: {e}\nResponse: {response}")
             error_detail = f"LLM response JSON structure invalid: {e}"
             shared_store["final_answer"] = f"Error: The AI assistant's response was malformed. Details: {error_detail}"
             return "final_answer", {"answer": shared_store["final_answer"]} # Force final answer


    def run(self, shared_store: Dict[str, Any]) -> str:
        """Executes the agent logic using dependencies from shared_store."""
        logger.info(f"Running {self.name}...")

        # --- Retrieve dependencies from shared_store ---
        llm_client = shared_store.get("llm_client")
        mode_config = shared_store.get("mode_config", {})

        # Check if LLM is required and available
        requires_llm = mode_config.get('requires_llm', True) # Assume required unless specified otherwise
        if requires_llm and not llm_client:
             logger.error(f"LLM client missing from shared_store but required for mode '{shared_store.get('mode_name')}'.")
             shared_store["error_message"] = f"{self.name} error: Required LLM client not available."
             return "error"
        # --- End Dependency Retrieval ---

        # 1. Build the prompt
        prompt = self._build_prompt(shared_store)

        if not requires_llm:
             logger.info(f"Mode '{shared_store.get('mode_name')}' does not require LLM. Skipping LLM call.")
             shared_store["final_answer"] = "Mode does not use LLM." # Example
             return "final_answer"

        # 2. Call the LLM using the generic interface from shared_store
        try:
            logger.info("Calling LLM via client from shared_store...")
            llm_response = ""

            llm_config = mode_config.get("llm_config", {}) # Get LLM config from mode_config
            provider = llm_config.get("provider") # Needed for factory/logging potentially
            model_name = llm_config.get("model")
            parameters = llm_config.get("parameters", {})

            if not model_name:
                # Try falling back to default model from global config if available
                global_config = shared_store.get("global_config", {})
                default_llm_config = global_config.get("defaults", {}).get("llm_config", {})
                model_name = default_llm_config.get("model")
                if not model_name:
                    raise ValueError("LLM 'model' name missing in mode configuration and no default found.")
                logger.warning(f"Using default LLM model '{model_name}' for mode '{shared_store.get('mode_name')}'.")
                # Also inherit default parameters if none specified in mode
                if not parameters:
                    parameters = default_llm_config.get("parameters", {})


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
        action, args = self._parse_llm_response(llm_response) # Use updated parser

        # 4. Update shared store based on action
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
        # Error case is handled within _parse_llm_response by forcing final_answer

        shared_store.pop("tool_result", None) # Clear previous tool result

        logger.info(f"{self.name} finished, returning action: '{action}'")
        return action
# --- End Asker Agent Node ---


# --- Tool Execution Node ---
# Using the same ToolExecutionNode logic as koder, just renaming the class for clarity within this flow context
class AskerToolExecutionNode(BaseAskerFlowNode): # Renamed
    """Executes tools using dependencies from shared_store for Asker flow."""
    def __init__(self, name="AskerToolExecutionNode", **kwargs): # Renamed default name
        super().__init__(name=name, **kwargs)
        logger.info(f"{self.name} initialized (dependencies accessed via shared_store).")

    # Method copied from koder.py's ToolExecutionNode - checks global config
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
            # TODO: Replace input() with proper UI interaction mechanism provided via shared_store or context
            logger.warning(f"Confirmation required for tool '{tool_name}'. Attempting interactive prompt (placeholder).")
            # Placeholder for UI interaction - for now, auto-approve in non-interactive
            # confirm = input(f"[Confirmation] Allow execution of tool '{tool_name}'? (y/n): ").strip().lower()
            # if confirm == 'y':
            #     logger.info(f"User approved execution of tool '{tool_name}'.")
            #     return True
            # else:
            #     logger.warning(f"User denied execution of tool '{tool_name}'.")
            #     return False
            logger.warning("Placeholder confirmation: Auto-approving tool execution.")
            return True # Auto-approve for now
        except EOFError:
             logger.warning(f"Cannot get user confirmation for tool '{tool_name}' (EOFError/non-interactive). Denying execution.")
             return False
        except Exception as e:
             logger.error(f"Error during user confirmation prompt for tool '{tool_name}': {e}. Denying execution.", exc_info=True)
             return False

    # Method copied from koder.py's ToolExecutionNode - uses tool registry
    def _execute_tool(self, tool_name: str, tool_args: Dict, tool_registry: Dict) -> Any:
        """Finds, loads, and executes the tool using registry from shared_store."""
        logger.info(f"Attempting to execute tool '{tool_name}' with args: {tool_args}")
        if not tool_registry:
             raise RuntimeError("Tool registry is not available in shared_store.")

        tool_path = tool_registry.get(tool_name)
        if not tool_path:
            # Check if it's a built-in tool group name (like 'read') - these aren't directly executable
            if tool_name in ["read", "edit", "command", "mcp", "browser"]:
                 raise ValueError(f"Attempted to execute tool group '{tool_name}' directly. Only specific tool functions can be executed.")
            raise ValueError(f"Tool '{tool_name}' not found in registry.")

        try:
            # Assuming tools are registered as 'module.path.FunctionName' or 'module.path.ClassName'
            # We need to handle both functions and potentially classes with a 'run' method or similar
            module_path, object_name = tool_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            ToolObjectOrFunc = getattr(module, object_name)

            # TODO: Add more robust handling for tool types (functions vs classes) if needed
            # For now, assume it's a callable function
            logger.info(f"Found tool implementation at {tool_path}. Executing...")
            # Inject shared_store? Or rely on tool definition? Assume simple call for now.
            result = ToolObjectOrFunc(**tool_args)
            logger.info(f"Tool '{tool_name}' executed successfully.")
            return result

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load tool '{tool_name}' from {tool_path}: {e}", exc_info=True)
            raise RuntimeError(f"Could not load tool '{tool_name}': {e}") from e
        except Exception as e:
            logger.error(f"Error during execution of tool '{tool_name}': {e}", exc_info=True)
            # Provide more context in the error if possible
            raise RuntimeError(f"Error executing tool '{tool_name}' with args {tool_args}: {e}") from e

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
# --- End Tool Execution Node ---


# --- Format Response Node ---
class FormatAskerResponse(BaseAskerFlowNode): # Renamed
    """Formats the final response or message for the user in Asker flow."""
    def run(self, shared_store: Dict[str, Any]) -> Optional[str]:
        logger.info(f"Running {self.name}...")
        final_output = "No final output generated." # Default

        # Prioritize specific outputs
        if "final_answer" in shared_store:
            final_output = shared_store["final_answer"]
        elif "question_to_ask" in shared_store:
             # Format as a question for the UI/user
             final_output = f"Question: {shared_store['question_to_ask']}"
        elif "tool_error" in shared_store:
             # Format tool errors clearly
             final_output = f"Process ended due to tool error: {shared_store['tool_error']}"
        elif "error_message" in shared_store:
             # Format general flow errors
             final_output = f"An error occurred during processing: {shared_store['error_message']}"

        logger.info(f"Formatted final output: {final_output[:100]}...")
        shared_store["final_output"] = final_output # Store the final formatted string
        return "response_formatted"

# --- Error Handler Node ---
class AskerErrorHandler(BaseAskerFlowNode): # Renamed
    """Handles errors occurring during the Asker flow execution."""
    def run(self, shared_store: Dict[str, Any]) -> str:
        logger.info(f"Running {self.name}...")
        # Consolidate error messages
        error_message = shared_store.get("tool_error") or shared_store.get("error_message") or "Unknown error"
        logger.error(f"Error handled in Asker flow: {error_message}")
        # Set a user-friendly final answer indicating failure
        shared_store["final_answer"] = f"Sorry, I encountered an error and couldn't complete the request: {error_message}"
        # Clear specific error flags
        shared_store.pop("tool_error", None)
        shared_store.pop("error_message", None)
        return "error_handled"


# --- Create Asker Flow ---
def create_asker_flow(): # Renamed
    """
    Creates the PocketFlow instance structure for the Asker Mode.
    Dependencies (LLM client, tool registry, configs) are injected
    into the shared_store by the ModeManager before running.
    """
    logger.info("Creating PocketFlow structure for Asker Mode...")

    # Define nodes using renamed classes
    start_node = StartAskerProcessing(name="StartAskerProcessing")
    agent_node = AskerAgentNode(name="AskerAgentNode")
    tool_execution_node = AskerToolExecutionNode(name="ExecuteAskerTool") # Renamed instance
    format_response_node = FormatAskerResponse(name="FormatAskerResponse")
    error_handler_node = AskerErrorHandler(name="AskerErrorHandler")
    end_node = EndAskerProcessing(name="EndAskerProcessing")

    # Define flow transitions (same logic as koder flow)
    start_node - "continue" >> agent_node

    agent_node - "call_tool" >> tool_execution_node
    agent_node - "final_answer" >> format_response_node
    agent_node - "ask_question" >> format_response_node
    agent_node - "error" >> error_handler_node # Catch agent errors (e.g., LLM config)

    tool_execution_node - "tool_executed" >> agent_node # Loop back to agent after tool use
    tool_execution_node - "tool_denied" >> format_response_node # Format denial message
    tool_execution_node - "tool_error" >> error_handler_node # Handle tool execution errors

    error_handler_node - "error_handled" >> format_response_node # Format error message

    format_response_node - "response_formatted" >> end_node # End the flow

    # Create the flow structure
    asker_flow = Flow(start=start_node) # Renamed variable

    logger.info("Asker Mode PocketFlow structure created.")
    return asker_flow
# --- End Create Asker Flow ---