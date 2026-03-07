"""
workspace_builder plugin PocketFlow factory.

This flow is tuned for authoring workspace plugin resources and related
workspace assets, then delegating the actual reasoning loop to the LLM runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node

logger = logging.getLogger(__name__)


class WorkspacePluginAuthorNode(Node):
    """Single-node authoring flow that hands control to the LLM runtime."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("initial_request", shared.get("task", ""))

    def exec(self, request: str) -> str:
        return request

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        llm_router = shared.get("_llm_router")
        if llm_router is not None:
            return "llm_delegate"

        logger.debug(
            "WorkspacePluginAuthorNode: no _llm_router in shared; recording pending request."
        )
        shared.setdefault("results", {})["workspace_builder"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        return "continue"


def create_flow() -> Flow:
    """Return the workspace plugin authoring flow."""
    return Flow(start=WorkspacePluginAuthorNode())
