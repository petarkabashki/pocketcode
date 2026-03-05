"""
Arkitekt agent PocketFlow factory.

The Arkitekt agent specialises in architecture and planning tasks: reading
existing code, listing files, and searching the codebase to produce high-level
design plans and recommendations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)


class ArkitektThinkNode(Node):
    """Think/exec node for the Arkitekt agent."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("initial_request", shared.get("task", ""))

    def exec(self, request: str) -> str:
        return request

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        llm_router = shared.get("_llm_router")
        if llm_router is not None:
            return "llm_delegate"
        logger.debug("ArkitektThinkNode: no _llm_router in shared; skipping LLM call.")
        shared.setdefault("results", {})["arkitekt"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        return "continue"


def create_flow() -> Flow:
    """Return an Arkitekt agent Flow."""
    think = ArkitektThinkNode()
    return Flow(start=think)
