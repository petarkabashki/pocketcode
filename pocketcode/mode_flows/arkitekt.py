#%% pocketcode/mode_flows/arkitekt.py
import logging
from typing import Dict, Any

from pocketflow import Flow # For type hinting return value

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

# --- Arkitekt Specific Nodes (Inheriting from Base Nodes) ---

class StartArkitektTask(BaseStartNode):
    """Arkitekt specific start node."""
    pass # Inherits base behavior

class EndArkitektTask(BaseEndNode):
    """Arkitekt specific end node."""
    pass # Inherits base behavior

class ArkitektAgentNode(BaseAgentNode):
    """
    Arkitekt specific Agent Node.
    Overrides _build_prompt for architectural planning and documentation tasks.
    """
    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt specifically for the Arkitekt mode."""
        logger.debug(f"Building prompt using {self.name}._build_prompt...")

        user_request = shared_store.get("initial_request", "No user request provided.")
        formatted_cli_context = shared_store.get("formatted_cli_context", "None provided.")
        tool_registry = self._get_tool_registry(shared_store)
        # Filter tools relevant to architecture/documentation if needed, or list all
        available_tools = list(tool_registry.keys())
        memory_bank_content = shared_store.get("memory_bank_content", "N/A")
        previous_tool_result = shared_store.get('tool_result', 'N/A')
        mode_name = shared_store.get('mode_name', 'Arkitekt')

        # Arkitekt-specific prompt
        prompt_lines = [
            f"You are in '{mode_name}' mode. Your goal is to analyze requirements, design software architecture, plan implementation steps, and generate/update documentation (like markdown files).",
            f"User Request: {user_request}",
            "\nContext:",
            f"  CLI Context: {formatted_cli_context}",
            f"  Memory Bank Summary:\n{memory_bank_content}", # Display potentially multi-line summary
            f"  Previous Tool Result: {previous_tool_result}",
            f"\nAvailable Tools: {available_tools}", # Focus on filesystem (read/write/search), memory bank tools
            "\nTask:",
            "Based on the user request, context, memory bank, available tools, and previous results, determine the next step for architectural planning or documentation.",
            "Think step-by-step. Break down complex tasks.",
            "Prioritize creating or updating documentation files (e.g., `.md`) using tools.",
            "Respond ONLY with a JSON object containing the action and its arguments.",
            "Possible actions:",
            "  - 'call_tool': If a tool (like read_file, write_to_file, search_files, list_files, memory bank tools) needs to be executed.",
            "    Required keys: 'action', 'tool_name', 'arguments' (object).",
            "  - 'final_answer': If the architectural task or documentation update is complete.",
            "    Required keys: 'action', 'answer' (string, often summarizing the work done or the final document state).",
            "  - 'ask_question': If you need clarification on requirements or design.",
            "    Required keys: 'action', 'question' (string).",
            "\nJSON Response:",
        ]
        prompt = "\n".join(prompt_lines)
        logger.debug(f"Built Arkitekt-specific LLM prompt:\n{prompt}")
        return prompt

    # Inherits run(), _parse_llm_response(), etc. from BaseAgentNode

class ArkitektToolExecutionNode(BaseToolExecutionNode):
    """Arkitekt specific tool execution node."""
    # For now, identical to base. Could add specific logic later if needed.
    pass # Inherits base behavior

class FormatArkitektResponse(BaseFormatResponseNode):
    """Arkitekt specific response formatting node."""
    # Could be customized later to better format markdown output summaries.
    pass # Inherits base behavior

class ArkitektErrorHandler(BaseErrorHandlerNode):
    """Arkitekt specific error handling node."""
    pass # Inherits base behavior


# --- Arkitekt Flow Creation Function ---

def create_arkitekt_flow() -> Flow:
    """
    Creates the PocketFlow instance for the Arkitekt Mode using base components.
    Dependencies are injected into the shared_store by the ModeManager.
    """
    logger.info("Creating PocketFlow for Arkitekt Mode using base flow structure...")

    # 1. Instantiate Arkitekt-specific nodes
    start_node = StartArkitektTask(name="StartArkitektTask")
    agent_node = ArkitektAgentNode(name="ArkitektAgent") # Uses overridden _build_prompt
    tool_execution_node = ArkitektToolExecutionNode(name="ArkitektExecuteTool")
    format_response_node = FormatArkitektResponse(name="FormatArkitektResponse")
    error_handler_node = ArkitektErrorHandler(name="ArkitektErrorHandler")
    end_node = EndArkitektTask(name="EndArkitektTask")

    # 2. Use the base flow wiring function
    arkitekt_flow = create_base_flow(
        start_node=start_node,
        agent_node=agent_node,
        tool_node=tool_execution_node,
        format_node=format_response_node,
        error_node=error_handler_node,
        end_node=end_node
    )

    logger.info("Arkitekt Mode PocketFlow structure created using base flow.")
    return arkitekt_flow

# --- End create_arkitekt_flow ---