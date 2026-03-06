"""
coder agent PocketFlow factory.

The coder agent specialises in coding tasks: writing code, creating files,
applying git diffs, and debugging. It delegates to the LLM runner via the
shared store and falls back gracefully when the LLM router is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)


class coderThinkNode(Node):
    """Think/exec node for the coder agent."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("initial_request", shared.get("task", ""))

    def exec(self, request: str) -> str:
        return request

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        llm_router = shared.get("_llm_router")
        if llm_router is not None:
            return "llm_delegate"
        logger.debug("coderThinkNode: no _llm_router in shared; skipping LLM call.")
        shared.setdefault("results", {})["coder"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        return "continue"


def create_flow() -> Flow:
    """Return a coder agent Flow."""
    think = coderThinkNode()
    return Flow(start=think)
