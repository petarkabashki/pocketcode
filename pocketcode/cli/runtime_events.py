from __future__ import annotations

from typing import Any, Dict


def format_runtime_event(event: Dict[str, Any]) -> str:
    event_type = str(event.get("type") or "")
    message = ""
    if event_type == "run_started":
        message = f"Run started for agent {event.get('agent') or 'auto'}."
    elif event_type == "agent_turn_started":
        execution_mode = str(event.get("execution_mode") or "").strip()
        mode_suffix = f" ({execution_mode})" if execution_mode else ""
        message = f"Agent turn started: {event.get('agent')}.{mode_suffix}"
    elif event_type == "agent_turn_completed":
        message = f"Agent turn completed: {event.get('agent')} -> {event.get('transition')}."
    elif event_type == "llm_call_started":
        message = (
            f"LLM call started for {event.get('agent')} using profile "
            f"{event.get('profile')}."
        )
    elif event_type == "llm_call_completed":
        model = event.get("model") or "-"
        raw_usage = event.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        cost = event.get("estimated_cost_usd")
        cost_suffix = f", ${float(cost):.6f}" if isinstance(cost, (int, float)) else ""
        message = (
            f"LLM call completed on {model} "
            f"({usage.get('total_tokens', 0)} tokens{cost_suffix})."
        )
    elif event_type == "tool_confirmation_requested":
        message = str(event.get("prompt") or f"Tool confirmation requested: {event.get('tool')}.")
    elif event_type == "tool_started":
        message = f"Tool call: {event.get('tool')}({_format_inline_value(event.get('arguments'))})."
    elif event_type == "tool_subprocess_started":
        message = f"Tool subprocess started: {event.get('tool')} (pid={event.get('pid')})."
    elif event_type == "tool_subprocess_terminated":
        message = (
            f"Tool subprocess terminated: {event.get('tool')} "
            f"(pid={event.get('pid')}, reason={event.get('reason')})."
        )
    elif event_type == "tool_timeout":
        message = (
            f"Tool timeout: {event.get('tool')} exceeded "
            f"{event.get('timeout_seconds')}s."
        )
    elif event_type == "tool_finished":
        state = "succeeded" if event.get("success") else "failed"
        summary = _summarize_tool_result(event.get("result"))
        message = f"Tool {event.get('tool')} {state}: {summary}."
    elif event_type == "handoff":
        context_mode = event.get("context_mode") or "whole"
        return_to_caller = "yes" if event.get("return_to_caller") else "no"
        message = (
            f"Handoff: {event.get('source_agent') or '-'} -> {event.get('target_agent')} "
            f"(context={context_mode}, return={return_to_caller})."
        )
    elif event_type == "handoff_return":
        message = (
            f"Handoff return: {event.get('source_agent')} <- {event.get('target_agent')} "
            f"(transition={event.get('return_transition') or 'continue'})."
        )
    elif event_type == "node_started":
        message = (
            f"Node started: {event.get('node_id')} "
            f"({event.get('node_kind') or 'node'})."
        )
    elif event_type == "node_completed":
        message = (
            f"Node completed: {event.get('node_id')} "
            f"-> {event.get('transition') or 'continue'}."
        )
    elif event_type == "ask_user":
        message = f"Agent requested user answer: {event.get('question')}."
    elif event_type == "final_answer":
        message = f"Final answer prepared by {event.get('agent')}."
    elif event_type == "interaction_requested":
        kind = event.get("kind") or "text"
        message = f"Input required ({kind}): {event.get('prompt')}."
    elif event_type == "interaction_received":
        message = "Input received."
    elif event_type == "session_started":
        message = f"Session started: {event.get('title') or event.get('session_id')}."
    elif event_type == "session_resumed":
        message = f"Session resumed: {event.get('title') or event.get('session_id')}."
    elif event_type == "session_saved":
        message = (
            f"Session saved: {event.get('title') or event.get('session_id')} "
            f"({event.get('transcript_entries', 0)} entries)."
        )
    elif event_type == "session_deleted":
        message = f"Session deleted: {event.get('title') or event.get('session_id')}."
    elif event_type == "session_cleared":
        message = f"Session history cleared: removed {event.get('count', 0)} session(s)."
    elif event_type == "user_input_requested":
        message = f"Input required: {event.get('prompt')}."
    elif event_type == "user_input_received":
        message = "Input received."
    elif event_type == "runtime_error":
        message = f"Runtime error: {event.get('message')}."
    elif event_type == "run_cancel_requested":
        message = f"Run cancellation requested: {event.get('reason')}."
    elif event_type == "run_cancelled":
        message = f"Run cancelled: {event.get('reason')}."
    elif event_type == "run_completed":
        message = "Run completed."
    elif event_type == "run_failed":
        message = f"Run failed: {event.get('error')}."
    if not message:
        return ""
    return _with_step_prefix(message, event)


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


def _with_step_prefix(message: str, event: Dict[str, Any]) -> str:
    step_index = event.get("step_index")
    if isinstance(step_index, int) and step_index > 0:
        return f"Step {step_index}: {message}"
    return message
