"""
Asker agent PocketFlow factory.

The Asker agent specialises in clarification: it prompts the user for missing
information and feeds the answers back into the task context so other agents
can proceed with complete requirements.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)


class AskerThinkNode(Node):
    """Think/exec node for the Asker agent."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("initial_request", shared.get("task", ""))

    def exec(self, request: str) -> str:
        return request

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        llm_router = shared.get("_llm_router")
        if llm_router is not None:
            return "llm_delegate"
        logger.debug("AskerThinkNode: no _llm_router in shared; skipping LLM call.")
        shared.setdefault("results", {})["asker"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        return "continue"


def create_flow() -> Flow:
    """Return an Asker agent Flow."""
    think = AskerThinkNode()
    return Flow(start=think)