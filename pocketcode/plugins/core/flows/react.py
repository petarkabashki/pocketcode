"""
ReAct agent PocketFlow factory.

Implements the Reason -> Act -> Observe cycle as a native pocketflow Flow composed
of four Node subclasses:

    ReasonNode --(call_tool)--> ActNode --> ObserveNode --(reason)--> ReasonNode
         |                                       |
         | (final_answer / ask_user)             | (final_answer)
         v                                       v
      FinalNode                              FinalNode

The flow is self-contained: tool calls are executed inside ActNode via
``_tool_runtime`` injected into the shared store by AgentRuntime, and LLM calls
are made inside ReasonNode via ``_llm_router``.

Requirements in shared store (injected by AgentRuntime._run_pocketflow_agent):
    _llm_router            : LlmRouter instance
    _tool_runtime          : ToolRuntime instance
    _agent_tool_definitions: list[dict] - pre-computed tool descriptions
    _agent_llm_profile     : str - resolved LLM profile name

State written to shared store:
    react_trace       : list[dict] - accumulated Reason/Act/Observe steps
    last_observation  : str - most recent tool result
    react_step_count  : int - guard counter against infinite loops
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

import yaml
from pocketflow import Flow, Node

logger = logging.getLogger(__name__)

_DEFAULT_MAX_STEPS = 64
_YAML_BLOCK_RE = re.compile(r"```(?:yaml)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _parse_yaml_response(text: str) -> Dict[str, Any]:
    """Extract and parse the first YAML block (or the whole text) from *text*."""
    match = _YAML_BLOCK_RE.search(text)
    candidate = match.group(1) if match else text
    parsed = yaml.safe_load(candidate)
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _to_yaml(obj: Any) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=False).strip()


class ReasonNode(Node):
    """Calls the LLM with the current ReAct context and decides the next step."""

    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        llm_router = shared.get("_llm_router")
        if llm_router is None:
            raise RuntimeError(
                "'_llm_router' is not present in the shared store. "
                "The ReAct agent requires an LLM router to operate."
            )
        return shared

    def exec(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        llm_router = shared["_llm_router"]
        profile = shared.get("_agent_llm_profile") or llm_router.default_profile_name
        tool_defs = shared.get("_agent_tool_definitions", [])
        trace = shared.get("react_trace", [])
        last_obs = shared.get("last_observation", "")

        context_block: Dict[str, Any] = {
            "request": shared.get("initial_request", shared.get("task", "")),
            "trace": trace,
            "last_observation": last_obs if last_obs else None,
            "cli_context": shared.get("formatted_cli_context", "None provided."),
        }
        context_block = {k: v for k, v in context_block.items() if v is not None}

        response_schema = {
            "action": "call_tool | final_answer | ask_user",
            "tool": "tool name - required when action=call_tool",
            "arguments": {"key": "value when action=call_tool"},
            "answer": "string - required when action=final_answer",
            "question": "string - required when action=ask_user",
            "reasoning": "optional brief explanation of this step",
        }

        prompt = "\n\n".join(
            [
                "You are a ReAct agent. Reason step-by-step, call tools as needed, "
                "then produce a final answer when you have enough information.",
                "Context (YAML):",
                _to_yaml(context_block),
                "Available tools:",
                _to_yaml(tool_defs) if tool_defs else "  (none)",
                "Respond ONLY with YAML matching this schema exactly:",
                _to_yaml(response_schema),
            ]
        )

        response_text = llm_router.generate(profile_name=profile, prompt=prompt)
        return _parse_yaml_response(response_text)

    def post(self, shared: Dict[str, Any], prep_res: Any, exec_res: Dict[str, Any]) -> str:
        decision = exec_res
        action = str(decision.get("action", "")).strip().lower()
        reasoning = decision.get("reasoning", "")

        trace = shared.setdefault("react_trace", [])
        step_count = shared.get("react_step_count", 0)
        shared["react_step_count"] = step_count + 1

        if action == "call_tool":
            tool_name = decision.get("tool") or decision.get("tool_name")
            arguments = decision.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            trace.append(
                {
                    "step": step_count + 1,
                    "reason": reasoning,
                    "action": "call_tool",
                    "tool": tool_name,
                    "arguments": arguments,
                }
            )
            shared["pending_tool"] = {
                "name": str(tool_name) if tool_name else "",
                "arguments": arguments,
            }
            return "call_tool"

        if action == "ask_user":
            question = decision.get("question", "")
            shared["question_to_ask"] = str(question)
            trace.append({"step": step_count + 1, "reason": reasoning, "action": "ask_user", "question": question})
            return "ask_user"

        answer = decision.get("answer", "")
        shared["final_answer"] = str(answer)
        trace.append({"step": step_count + 1, "reason": reasoning, "action": "final_answer", "answer": answer})
        return "final_answer"


class ActNode(Node):
    """Executes the pending tool call and stores the raw result."""

    def prep(self, shared: Dict[str, Any]) -> Dict[str, Any]:
        return shared.get("pending_tool", {})

    def exec(self, pending_tool: Dict[str, Any]) -> Dict[str, Any]:
        return pending_tool

    def post(self, shared: Dict[str, Any], prep_res: Any, exec_res: Dict[str, Any]) -> str:
        tool_runtime = shared.get("_tool_runtime")
        pending_tool = exec_res

        tool_name = pending_tool.get("name", "")
        arguments = pending_tool.get("arguments", {})

        if not tool_runtime or not tool_name:
            observation = f"Tool execution skipped: tool_runtime={tool_runtime!r}, tool={tool_name!r}"
            logger.warning("ActNode: %s", observation)
            shared["last_observation"] = observation
            shared.pop("pending_tool", None)
            return "observe"

        try:
            result = tool_runtime.execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                shared_store=shared,
                auto_confirm=bool(shared.get("auto_confirm_tools", False)),
                agent_name=str(shared.get("active_agent")) if shared.get("active_agent") else None,
            )
            shared["last_observation"] = str(result)
        except Exception as exc:
            shared["last_observation"] = f"Tool error: {exc}"
            logger.exception("ActNode: tool '%s' raised an exception", tool_name)

        shared.pop("pending_tool", None)
        return "observe"


class ObserveNode(Node):
    """Records the observation in the trace and decides whether to continue looping."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("last_observation", "")

    def exec(self, observation: str) -> str:
        return observation

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        observation = exec_res
        trace = shared.setdefault("react_trace", [])
        if trace:
            trace[-1]["observation"] = observation

        max_steps = int(shared.get("max_agent_steps", _DEFAULT_MAX_STEPS))
        step_count = int(shared.get("react_step_count", 0))
        if step_count >= max_steps:
            logger.warning(
                "ObserveNode: react_step_count (%d) reached max_agent_steps (%d). Terminating loop.",
                step_count,
                max_steps,
            )
            shared["final_answer"] = (
                f"Maximum reasoning steps ({max_steps}) reached without a final answer."
            )
            return "final_answer"

        return "reason"


class FinalNode(Node):
    """Terminal node - ensures final_answer or question_to_ask is in shared store."""

    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("final_answer") or shared.get("question_to_ask") or ""

    def exec(self, result: str) -> str:
        return result

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        if not shared.get("final_answer") and not shared.get("question_to_ask"):
            shared["final_answer"] = exec_res or "No answer produced."
        return "final_answer"


def create_flow() -> Flow:
    """Return a ReAct agent Flow."""
    reason = ReasonNode()
    act = ActNode()
    observe = ObserveNode()
    final = FinalNode()

    reason - "call_tool" >> act
    reason - "final_answer" >> final
    reason - "ask_user" >> final
    act - "observe" >> observe
    observe - "reason" >> reason
    observe - "final_answer" >> final

    return Flow(start=reason)