"""
architect agent PocketFlow factory.

The architect agent specialises in architecture and planning tasks: reading
existing code, listing files, and searching the codebase to produce high-level
design plans and recommendations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)


class architectThinkNode(Node):
    """Think/exec node for the architect agent."""

    def prep(self, shared: Dict[str, Any]) -> None:
        shared.setdefault("_request", shared.get("initial_request", shared.get("task", "")))

    def exec(self, prep_res: str) -> None:
        pass

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> None:
        llm_router = shared.get("_llm_router")
        if llm_router is not None:
            shared.setdefault("_next_node", "llm_delegate")
            return
        logger.debug("architectThinkNode: no _llm_router in shared; skipping LLM call.")
        shared.setdefault("results", {})["architect"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        shared.setdefault("_next_node", "continue")


def create_flow() -> Flow:
    """Return an architect agent Flow."""
    think = architectThinkNode()
    return Flow(start=think)