"""Coder agent PocketFlow factory.

Creates a PocketFlow Flow that implements the Coder agent's decision loop.
The flow uses the LLM router and tool runtime available via the runtime registry
that is populated in shared_store by the workflow runtime.

Agent profile:
  - Specialises in code implementation, editing, and verification.
  - Preferred tools: read_file, write_to_file, list_files, create_directory,
    glob_files, search_code, execute_command, git tools.
  - Can hand off to Architect (planning) and Ask (Q&A).
"""
from __future__ import annotations

import logging
from typing import Any

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)

AGENT_NAME = "coder"
AGENT_DESCRIPTION = "Code implementation and editing specialist."
DEFAULT_LLM_PROFILE = "gemini_default"


class CoderThinkNode(Node):
    """Single-turn LLM reasoning node for the Coder agent.

    Reads context from ``shared_store``, calls the LLM (if a router is
    available via ``shared_store["_llm_router"]``), and returns the
    appropriate PocketFlow transition.

    When the runtime registry is not yet wired (Phase < 5), the node
    returns ``"continue"`` so the legacy execution path in AgentRuntime
    remains in control.
    """

    def prep(self, shared: dict) -> dict:
        return {
            "agent_name": shared.get("active_agent", AGENT_NAME),
            "request": shared.get("initial_request", ""),
            "context": shared.get("cli_context", {}),
            "results": shared.get("results", {}),
            "last_tool_route": shared.get("last_tool_route"),
        }

    def exec(self, prep_res: dict) -> Any:
        # Resolved in post() — nothing to execute without the LLM router reference.
        return prep_res

    def post(self, shared: dict, prep_res: dict, exec_res: Any) -> str:
        # Phase 5+: use LLM router from shared_store when wired.
        # Phase 4: return "continue" so AgentRuntime falls through to its LLM path.
        llm_router = shared.get("_llm_router")
        if llm_router is None:
            logger.debug(
                "CoderThinkNode: _llm_router not in shared_store; "
                "delegating to legacy LLM execution path."
            )
            return "continue"

        # Full LLM turn will be implemented here in Phase 5 (T028).
        return "continue"


def create_flow() -> Flow:
    """Zero-arg factory. Returns a PocketFlow Flow for the Coder agent."""
    think = CoderThinkNode()
    flow = Flow(start=think)
    return flow
