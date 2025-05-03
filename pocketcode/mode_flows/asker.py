#%% pocketcode/mode_flows/asker.py
import logging
import json
from typing import Dict, Any, Tuple, Optional

from pocketflow import Flow # For type hinting return value

# Import base flow components
from .base_flow import (
    BaseStartNode,
    BaseAgentNode, # Import BaseAgentNode for inheritance
    BaseToolExecutionNode,
    BaseFormatResponseNode,
    BaseErrorHandlerNode,
    BaseEndNode,
    create_base_flow
)

logger = logging.getLogger(__name__) # Use current module name

# --- Asker Agent Node (Customized) ---
# Keep this custom node because it overrides _build_prompt and _parse_llm_response
class AskerAgentNode(BaseAgentNode): # Inherit from BaseAgentNode
    """
    Interacts with LLM using dependencies from shared_store for the Asker mode.
    Overrides _build_prompt for Asker-specific instructions and context.
    Overrides _parse_llm_response for potentially more robust JSON handling.
    """
    def __init__(self, name="AskerAgentNode", **kwargs): # Keep constructor simple
        super().__init__(name=name, **kwargs)
        # Dependencies (LLM client, config, etc.) are accessed via shared_store in run()

    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt using info from shared_store for Asker mode."""
        logger.debug(f"Building prompt using {self.name}._build_prompt...")
        # Retrieve necessary info using base class helpers or directly
        user_request = shared_store.get("initial_request", "No user request provided.")
        formatted_cli_context = shared_store.get("formatted_cli_context", "None provided.")
        tool_registry = self._get_tool_registry(shared_store) # Use helper from base
        memory_bank_content = shared_store.get("memory_bank_content", "N/A")
        previous_tool_result = shared_store.get('tool_result', 'N/A')
        mode_name = shared_store.get('mode_name', 'Asker') # Default to Asker if not set

        # Get allowed tools specifically for this mode from mode_config if available
        mode_config = self._get_mode_config(shared_store) # Use helper from base
        allowed_tools_config = mode_config.get("allowed_tools", [])
        # If allowed_tools are defined, use them, otherwise fall back to registry keys
        # TODO: Fetch tool descriptions/schemas for better prompting
        available_tools = allowed_tools_config if allowed_tools_config else list(tool_registry.keys())

        # Asker-specific role definition integrated into the prompt
        role_definition = "You are Roo, a helpful assistant designed to answer questions about the codebase or other topics. You can read files, search through the project, and list directory contents to gather information for your answers. Use the available tools to find the information needed."

        prompt_lines = [
            role_definition, # Added role definition
            f"\nUser Request: {user_request}",
            "\nContext:",
            f"  Mode: {mode_name}",
            f"  CLI Context: {formatted_cli_context}",
            f"  Previous Tool Result: {previous_tool_result}",
            f"  Memory Bank Summary: {memory_bank_content}",
            f"\nAvailable Tools: {available_tools}", # Use potentially filtered list
            "\nBased on the user request and context, determine the next step to answer the question.",
            "Respond ONLY in JSON format.", # Emphasize JSON only
            "The JSON object must have an 'action' key.",
            "If a tool needs to be called, provide 'action': 'call_tool', 'tool_name': <name>, 'arguments': {<args>}.",
            "If the question can be answered directly, provide 'action': 'final_answer', 'answer': <your final answer>.",
            "If you need clarification from the user, provide 'action': 'ask_question', 'question': <question>."
            "\nJSON Response:",
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built Asker LLM prompt:\n{prompt}")
        return prompt

    def _parse_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parses the LLM's JSON response.
        (Keeping this potentially more robust version from the original asker.py)
        """
        logger.debug(f"Parsing LLM response using {self.name}._parse_llm_response: {response[:200]}...")
        try:
            logger.debug(f"Raw LLM response received by {self.name}: {response}") # ADDED with correct indentation
            # Attempt to find and parse JSON block, handling potential markdown fences
            json_match = None
            if '```json' in response:
                json_start = response.find('```json') + len('```json')
                json_end = response.find('```', json_start)
                if json_end != -1:
                    json_content = response[json_start:json_end].strip()
                    logger.debug(f"Attempting to parse fenced JSON block: {json_content}")
                    json_match = json.loads(json_content)
            elif response.strip().startswith('{') and response.strip().endswith('}'):
                 logger.debug(f"Attempting to parse raw JSON block: {response.strip()}")
                 json_match = json.loads(response.strip()) # Assume raw JSON if starts/ends with {}
            else: # Fallback: find first '{' and last '}'
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                     content_to_parse = response[json_start:json_end]
                     logger.debug(f"Attempting to parse fallback JSON block: {content_to_parse}")
                     json_match = json.loads(content_to_parse)

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
            error_msg = f"Failed to parse LLM response as JSON: {e}. Response: {response}"
            logger.error(error_msg)
            # Return error action instead of forcing final_answer
            return "error", {"error_message": error_msg}
        except ValueError as e:
             error_msg = f"Error in parsed LLM response structure or content: {e}. Response: {response}"
             logger.error(error_msg)
             return "error", {"error_message": error_msg}
        except Exception as e:
             error_msg = f"Unexpected error parsing LLM response: {e}. Response: {response}"
             logger.error(error_msg, exc_info=True)
             return "error", {"error_message": error_msg}

    # run() method is inherited from BaseAgentNode

# --- Create Asker Flow (Using Base Structure) ---
def create_asker_flow() -> Flow:
    """
    Creates the PocketFlow instance structure for the Asker Mode using base components.
    Dependencies (LLM client, tool registry, configs) are injected
    into the shared_store by the ModeManager before running.
    """
    logger.info("Creating PocketFlow structure for Asker Mode using base flow...")

    # 1. Instantiate nodes using Base classes and the custom AskerAgentNode
    start_node = BaseStartNode(name="StartAskerProcessing")
    agent_node = AskerAgentNode(name="AskerAgentNode") # Use the custom agent node
    tool_execution_node = BaseToolExecutionNode(name="ExecuteAskerTool")
    format_response_node = BaseFormatResponseNode(name="FormatAskerResponse")
    error_handler_node = BaseErrorHandlerNode(name="AskerErrorHandler")
    end_node = BaseEndNode(name="EndAskerProcessing")

    # 2. Use the base flow wiring function
    asker_flow = create_base_flow(
        start_node=start_node,
        agent_node=agent_node,
        tool_node=tool_execution_node,
        format_node=format_response_node,
        error_node=error_handler_node,
        end_node=end_node
    )

    logger.info("Asker Mode PocketFlow structure created using base flow.")
    return asker_flow
# --- End Create Asker Flow ---