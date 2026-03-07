"""
MicroManager agent PocketFlow factory.

The micromanager is an orchestrating agent that:
  1. Examines the incoming task in shared["task"] / shared["messages"].
  2. Decides which core specialist (coder, architect, ask) is best suited.
  3. Resolves that agent's flow from shared["_registry"].agents and runs it.

shared["_registry"] is populated at session start by workflow_runtime.
Until that is wired, this flow degrades gracefully by logging a warning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from pocketflow import Flow, Node
from pocketcode.core.namespace_registry import RegistryError

logger = logging.getLogger(__name__)

_ROUTING_RULES: list[tuple[tuple[str, ...], str]] = [
    (("code", "implement", "write", "fix", "debug", "refactor"), "coder::coder"),
    (("architect", "design", "plan", "structure", "scaffold"), "architect::architect"),
    (("ask", "question", "explain", "help", "what", "how", "why"), "asker::ask"),
]

_DEFAULT_AGENT = "coder::coder"


def _route_task(shared: Dict[str, Any]) -> str:
    """Return the qualified agent name best suited for the current task."""
    text = ""
    for key in ("task", "user_request", "query"):
        text = shared.get(key, "")
        if text:
            break
    if not text:
        messages = shared.get("messages", [])
        if messages:
            last = messages[-1]
            text = last.get("content", "") if isinstance(last, dict) else str(last)

    lower = text.lower()
    for keywords, agent_qname in _ROUTING_RULES:
        if any(kw in lower for kw in keywords):
            return agent_qname
    return _DEFAULT_AGENT


class MicroManagerRouterNode(Node):
    """Determine which sub-agent should handle the task."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return _route_task(shared)

    def exec(self, target_agent: str) -> str:
        return target_agent

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        shared["_mm_target_agent"] = exec_res
        logger.debug("MicroManager routing to: %s", exec_res)
        return "delegate"


class MicroManagerDelegateNode(Node):
    """Resolve the chosen sub-agent from the registry and run its flow."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("_mm_target_agent", _DEFAULT_AGENT)

    def exec(self, target_agent: str) -> Any:
        return target_agent

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        registry = shared.get("_registry")
        if registry is None:
            logger.warning(
                "MicroManager: shared['_registry'] is not set; cannot delegate to '%s'. Returning without execution.",
                exec_res,
            )
            shared["_mm_error"] = f"Registry not available; cannot delegate to {exec_res}"
            return "done"

        try:
            agent_def = registry.agents.resolve(exec_res)
        except RegistryError as exc:
            logger.error("MicroManager: could not resolve agent '%s': %s", exec_res, exc)
            shared["_mm_error"] = str(exc)
            return "done"

        flow = getattr(agent_def, "flow_instance", None)
        if flow is None:
            logger.error(
                "MicroManager: agent '%s' has no flow_instance; it may not be a programmatic agent.",
                exec_res,
            )
            shared["_mm_error"] = f"Agent {exec_res} has no flow_instance"
            return "done"

        logger.info("MicroManager delegating to '%s'", exec_res)
        flow.run(shared)
        return "done"


def create_flow() -> Flow:
    """Return a fully wired MicroManager orchestrating Flow."""
    router = MicroManagerRouterNode()
    delegate = MicroManagerDelegateNode()

    router - "delegate" >> delegate  # type: ignore[operator]

    return Flow(start=router)