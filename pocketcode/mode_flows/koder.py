#%% pocketcode/mode_flows/koder.py
import logging
from typing import Dict, Any, Optional

from pocketflow import Flow # Still needed for type hinting create_koder_flow return

# Import base flow components
from .base_flow import (
    BaseStartNode,
    BaseAgentNode,
    BaseToolExecutionNode,
    BaseFormatResponseNode,
    BaseErrorHandlerNode,
    BaseEndNode,
    create_base_flow
)

logger = logging.getLogger(__name__)

# --- Koder Specific Nodes (Inheriting from Base Nodes) ---

# BaseCodeFlowNode is removed as BaseFlowNode is used via inheritance

class StartCodeProcessing(BaseStartNode):
    """Koder specific start node (currently identical to base)."""
    # Inherits run method from BaseStartNode
    pass # No override needed for now

class EndCodeProcessing(BaseEndNode):
    """Koder specific end node (currently identical to base)."""
    # Inherits run method from BaseEndNode
    pass # No override needed for now

class CodeAgentNode(BaseAgentNode):
    """
    Koder specific Agent Node.
    Overrides _build_prompt for potential Koder-specific logic.
    Inherits run, _parse_llm_response, etc., from BaseAgentNode.
    """
    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt specifically for the Koder mode."""
        logger.debug(f"Building prompt using {self.name}._build_prompt...")

        # Retrieve necessary info using base class helpers or directly
        user_request = shared_store.get("initial_request", "No user request provided.")
        formatted_cli_context = shared_store.get("formatted_cli_context", "None provided.")
        tool_registry = self._get_tool_registry(shared_store) # Use helper from base
        available_tools = list(tool_registry.keys()) # TODO: Enhance with descriptions/schemas
        memory_bank_content = shared_store.get("memory_bank_content", "N/A")
        previous_tool_result = shared_store.get('tool_result', 'N/A')
        mode_name = shared_store.get('mode_name', 'Koder') # Default to Koder if not set

        # Koder-specific prompt adjustments can go here
        # For now, it's similar to the base prompt example
        prompt_lines = [
            f"You are in '{mode_name}' mode. Your goal is to write, modify, or analyze code based on the user request.",
            f"User Request: {user_request}",
            "\nContext:",
            f"  CLI Context: {formatted_cli_context}",
            f"  Memory Bank Summary: {memory_bank_content}",
            f"  Previous Tool Result: {previous_tool_result}",
            f"\nAvailable Tools: {available_tools}", # Consider adding tool descriptions/schemas from registry
            "\nTask:",
            "Based on the user request, context, memory bank, available tools, and previous results, determine the next step.",
            "Focus on code generation, modification, or analysis tasks.",
            "Respond ONLY with a JSON object containing the action and its arguments.",
            "Possible actions:",
            "  - 'call_tool': If a tool (like read_file, write_to_file, search_files) needs to be executed.",
            "    Required keys: 'action', 'tool_name', 'arguments' (object).",
            "  - 'final_answer': If the coding task is complete and you have the final code or message.",
            "    Required keys: 'action', 'answer' (string).",
            "  - 'ask_question': If you need clarification on the coding task.",
            "    Required keys: 'action', 'question' (string).",
            "\nJSON Response:",
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built Koder-specific LLM prompt:\n{prompt}")
        return prompt

    # run() method is inherited from BaseAgentNode
    # _parse_llm_response() is inherited from BaseAgentNode

class KoderToolExecutionNode(BaseToolExecutionNode):
    """Koder specific tool execution node (currently identical to base)."""
    # Inherits run, _confirm_execution, _execute_tool methods from BaseToolExecutionNode
    pass # No override needed for now

class FormatCodeResponse(BaseFormatResponseNode):
    """Koder specific response formatting node (currently identical to base)."""
    # Inherits run method from BaseFormatResponseNode
    pass # No override needed for now

class KoderErrorHandler(BaseErrorHandlerNode):
    """Koder specific error handling node (currently identical to base)."""
    # Inherits run method from BaseErrorHandlerNode
    pass # No override needed for now


# --- Koder Flow Creation Function ---

def create_koder_flow() -> Flow:
    """
    Creates the PocketFlow instance for the Koder Mode using base components.
    Dependencies are injected into the shared_store by the ModeManager.
    """
    logger.info("Creating PocketFlow for Koder Mode using base flow structure...")

    # 1. Instantiate Koder-specific nodes (which inherit from base nodes)
    start_node = StartCodeProcessing(name="StartKoderProcessing")
    agent_node = CodeAgentNode(name="KoderAgent") # Uses overridden _build_prompt
    tool_execution_node = KoderToolExecutionNode(name="KoderExecuteTool")
    format_response_node = FormatCodeResponse(name="FormatKoderResponse")
    error_handler_node = KoderErrorHandler(name="KoderErrorHandler")
    end_node = EndCodeProcessing(name="EndKoderProcessing")

    # 2. Use the base flow wiring function
    koder_flow = create_base_flow(
        start_node=start_node,
        agent_node=agent_node,
        tool_node=tool_execution_node,
        format_node=format_response_node,
        error_node=error_handler_node,
        end_node=end_node
    )

    logger.info("Koder Mode PocketFlow structure created using base flow.")
    return koder_flow

# --- End create_koder_flow ---