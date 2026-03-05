"""Ask agent PocketFlow factory.

Creates a PocketFlow Flow for the Ask (Q&A) agent.

Agent profile:
  - Specialises in answering repository questions and code explanation.
  - Read-only tools: read_file, list_files, glob_files, search_code.
  - Uses the *fast* LLM profile (``gemini_fast``) for low-latency responses.
  - Can hand off to Coder and Architect.
"""
from __future__ import annotations

import logging
from typing import Any

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)

AGENT_NAME = "ask"
AGENT_DESCRIPTION = "Repository Q&A specialist."
DEFAULT_LLM_PROFILE = "gemini_fast"


class AskThinkNode(Node):
    """Single-turn LLM reasoning node for the Ask agent.

    Returns ``"continue"`` when the runtime registry is not yet wired,
    allowing AgentRuntime's legacy LLM path to handle the turn.
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
        return prep_res

    def post(self, shared: dict, prep_res: dict, exec_res: Any) -> str:
        llm_router = shared.get("_llm_router")
        if llm_router is None:
            logger.debug(
                "AskThinkNode: _llm_router not in shared_store; "
                "delegating to legacy LLM execution path."
            )
            return "continue"

        # Full LLM turn will be implemented here in Phase 5 (T028).
        return "continue"


def create_flow() -> Flow:
    """Zero-arg factory. Returns a PocketFlow Flow for the Ask agent."""
    think = AskThinkNode()
    flow = Flow(start=think)
    return flow
