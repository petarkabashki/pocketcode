from __future__ import annotations

from typing import Any, Dict


def format_runtime_event(event: Dict[str, Any]) -> str:
    event_type = str(event.get("type") or "")
    if event_type == "run_started":
        return f"Run started for agent {event.get('agent') or 'auto'}."
    if event_type == "agent_turn_started":
        execution_mode = str(event.get("execution_mode") or "").strip()
        mode_suffix = f" ({execution_mode})" if execution_mode else ""
        return f"Agent turn started: {event.get('agent')}.{mode_suffix}"
    if event_type == "agent_turn_completed":
        return f"Agent turn completed: {event.get('agent')} -> {event.get('transition')}."
    if event_type == "llm_call_started":
        return (
            f"LLM call started for {event.get('agent')} using profile "
            f"{event.get('profile')}."
        )
    if event_type == "llm_call_completed":
        model = event.get("model") or "-"
        raw_usage = event.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        cost = event.get("estimated_cost_usd")
        cost_suffix = f", ${float(cost):.6f}" if isinstance(cost, (int, float)) else ""
        return (
            f"LLM call completed on {model} "
            f"({usage.get('total_tokens', 0)} tokens{cost_suffix})."
        )
    if event_type == "tool_confirmation_requested":
        return (
            f"Tool confirmation requested: {event.get('tool')} "
            f"{_format_arguments(event.get('arguments'))}."
        )
    if event_type == "tool_started":
        return f"Tool call: {event.get('tool')}({_format_inline_value(event.get('arguments'))})."
    if event_type == "tool_subprocess_started":
        return f"Tool subprocess started: {event.get('tool')} (pid={event.get('pid')})."
    if event_type == "tool_subprocess_terminated":
        return (
            f"Tool subprocess terminated: {event.get('tool')} "
            f"(pid={event.get('pid')}, reason={event.get('reason')})."
        )
    if event_type == "tool_timeout":
        return (
            f"Tool timeout: {event.get('tool')} exceeded "
            f"{event.get('timeout_seconds')}s."
        )
    if event_type == "tool_finished":
        state = "succeeded" if event.get("success") else "failed"
        summary = _summarize_tool_result(event.get("result"))
        return f"Tool {event.get('tool')} {state}: {summary}."
    if event_type == "handoff":
        context_mode = event.get("context_mode") or "whole"
        return_to_caller = "yes" if event.get("return_to_caller") else "no"
        return (
            f"Handoff: {event.get('source_agent') or '-'} -> {event.get('target_agent')} "
            f"(context={context_mode}, return={return_to_caller})."
        )
    if event_type == "handoff_return":
        return (
            f"Handoff return: {event.get('source_agent')} <- {event.get('target_agent')} "
            f"(transition={event.get('return_transition') or 'continue'})."
        )
    if event_type == "ask_user":
        return f"Agent requested user answer: {event.get('question')}."
    if event_type == "final_answer":
        return f"Final answer prepared by {event.get('agent')}."
    if event_type == "interaction_requested":
        kind = event.get("kind") or "text"
        return f"Input required ({kind}): {event.get('prompt')}."
    if event_type == "interaction_received":
        return "Input received."
    if event_type == "user_input_requested":
        return f"Input required: {event.get('prompt')}."
    if event_type == "user_input_received":
        return "Input received."
    if event_type == "runtime_error":
        return f"Runtime error: {event.get('message')}."
    if event_type == "run_cancel_requested":
        return f"Run cancellation requested: {event.get('reason')}."
    if event_type == "run_cancelled":
        return f"Run cancelled: {event.get('reason')}."
    if event_type == "run_completed":
        return "Run completed."
    if event_type == "run_failed":
        return f"Run failed: {event.get('error')}."
    return ""


def _format_arguments(arguments: Any) -> str:
    if not isinstance(arguments, dict) or not arguments:
        return "with no arguments"
    return f"with {_format_inline_value(arguments)}"


def _summarize_tool_result(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("success") is False and result.get("error"):
            return str(result.get("error"))
        if "approved" in result:
            return f"approved={result.get('approved')}"
        if "value" in result:
            return f"value={_format_inline_value(result.get('value'))}"
        if "result" in result:
            return _format_inline_value(result.get("result"))
    return _format_inline_value(result)


def _format_inline_value(value: Any, *, limit: int = 120) -> str:
    text = repr(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."