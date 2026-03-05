"""Architect agent PocketFlow factory.

Creates a PocketFlow Flow for the Architect (core.Architect) agent.

Agent profile:
  - Specialises in system design, architecture review, and technical planning.
  - Read-only tools: read_file, list_files, glob_files, search_code.
  - Can hand off to Coder (implementation) and Ask (Q&A).

Note: This is the *core plugin's* Architect component. It is distinct from
the ``arkitekt`` plugin, which registers under its own plugin namespace with
the local bare name ``arkitekt``. No FR-006 ambiguity exists between the two.
"""
from __future__ import annotations

import logging
from typing import Any

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)

AGENT_NAME = "architect"
AGENT_DESCRIPTION = "Architecture and planning specialist."
DEFAULT_LLM_PROFILE = "gemini_default"


class ArchitectThinkNode(Node):
    """Single-turn LLM reasoning node for the Architect agent.

    Until the runtime registry is wired (Phase 5, T028), returns ``"continue"``
    so AgentRuntime's legacy LLM execution path remains in control.
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
                "ArchitectThinkNode: _llm_router not in shared_store; "
                "delegating to legacy LLM execution path."
            )
            return "continue"

        # Full LLM turn will be implemented here in Phase 5 (T028).
        return "continue"


def create_flow() -> Flow:
    """Zero-arg factory. Returns a PocketFlow Flow for the Architect agent."""
    think = ArchitectThinkNode()
    flow = Flow(start=think)
    return flow
