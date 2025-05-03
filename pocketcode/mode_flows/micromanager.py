# pocketcode/mode_flows/micromanager.py
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

# --- Micromanager Specific Nodes (Inheriting from Base Nodes) ---
# These are placeholders for now, inheriting base behavior.
# The AgentNode might need a custom _build_prompt later.

class StartMicromanageTask(BaseStartNode):
    """Micromanager specific start node."""
    # Inherits run method from BaseStartNode
    pass

class EndMicromanageTask(BaseEndNode):
    """Micromanager specific end node."""
    # Inherits run method from BaseEndNode
    pass

class MicromanagerAgentNode(BaseAgentNode):
    """
    Micromanager specific Agent Node.
    TODO: Override _build_prompt for task breakdown, delegation logic.
    Inherits run, _parse_llm_response, etc., from BaseAgentNode.
    """
    def _build_prompt(self, shared_store: Dict[str, Any]) -> str:
        """Builds the prompt specifically for the Micromanager mode."""
        logger.warning(f"{self.name}._build_prompt() is using the base implementation. "
                       "Micromanager requires a specific prompt for task breakdown/delegation.")
        # For now, call the base implementation which provides a generic structure
        # TODO: Replace with Micromanager-specific prompt logic
        return super()._build_prompt(shared_store)

    # run() method is inherited from BaseAgentNode
    # _parse_llm_response() is inherited from BaseAgentNode

class MicromanagerToolExecutionNode(BaseToolExecutionNode):
    """Micromanager specific tool execution node (currently identical to base)."""
    # Inherits run, _confirm_execution, _execute_tool methods from BaseToolExecutionNode
    pass

class FormatMicromanagerResponse(BaseFormatResponseNode):
    """Micromanager specific response formatting node (currently identical to base)."""
    # Inherits run method from BaseFormatResponseNode
    pass

class MicromanagerErrorHandler(BaseErrorHandlerNode):
    """Micromanager specific error handling node (currently identical to base)."""
    # Inherits run method from BaseErrorHandlerNode
    pass


# --- Micromanager Flow Creation Function ---

def create_micromanager_flow() -> Flow:
    """
    Creates the PocketFlow instance for the Micromanager Mode using base components.
    Dependencies are injected into the shared_store by the ModeManager.
    """
    logger.info("Creating PocketFlow for Micromanager Mode using base flow structure...")

    # 1. Instantiate Micromanager-specific nodes (which inherit from base nodes)
    start_node = StartMicromanageTask(name="StartMicromanageTask")
    agent_node = MicromanagerAgentNode(name="MicromanagerAgent") # Uses overridden _build_prompt (currently base)
    tool_execution_node = MicromanagerToolExecutionNode(name="MicromanagerExecuteTool")
    format_response_node = FormatMicromanagerResponse(name="FormatMicromanagerResponse")
    error_handler_node = MicromanagerErrorHandler(name="MicromanagerErrorHandler")
    end_node = EndMicromanageTask(name="EndMicromanageTask")

    # 2. Use the base flow wiring function
    micromanager_flow = create_base_flow(
        start_node=start_node,
        agent_node=agent_node,
        tool_node=tool_execution_node,
        format_node=format_response_node,
        error_node=error_handler_node,
        end_node=end_node
    )

    logger.info("Micromanager Mode PocketFlow structure created using base flow.")
    return micromanager_flow

# --- End create_micromanager_flow ---