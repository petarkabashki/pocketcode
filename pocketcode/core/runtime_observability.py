from __future__ import annotations

import time
from typing import Any, Dict


def initialize_runtime_observability(shared_store: Dict[str, Any]) -> Dict[str, Any]:
    existing = shared_store.get("_runtime_observability")
    if isinstance(existing, dict):
        existing.setdefault("event_count", 0)
        existing.setdefault("step_counter", 0)
        existing.setdefault("steps", [])
        existing.setdefault("active_steps", {})
        return existing

    observability = {
        "event_count": 0,
        "step_counter": 0,
        "steps": [],
        "active_steps": {},
    }
    shared_store["_runtime_observability"] = observability
    return observability


def observe_runtime_event(
    shared_store: Dict[str, Any],
    event_type: str,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    observability = initialize_runtime_observability(shared_store)
    event_payload = dict(payload or {})
    observability["event_count"] = int(observability.get("event_count", 0)) + 1
    event_payload["event_index"] = int(observability["event_count"])
    emitted_at = time.perf_counter()

    step = _update_step_trace(
        observability=observability,
        event_type=str(event_type or ""),
        payload=event_payload,
        emitted_at=emitted_at,
    )
    if isinstance(step, dict):
        event_payload.setdefault("step_index", step.get("index"))
        event_payload.setdefault("step_kind", step.get("kind"))
        event_payload.setdefault("step_status", step.get("status"))
        event_payload.setdefault("step_label", step.get("label"))

    return event_payload


def build_runtime_observability_summary(shared_store: Dict[str, Any]) -> Dict[str, Any]:
    observability = initialize_runtime_observability(shared_store)
    steps = observability.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    return {
        "runtime_event_count": int(observability.get("event_count", 0)),
        "step_count": len(steps),
        "steps": [_public_step(step) for step in steps if isinstance(step, dict)],
    }


def _update_step_trace(
    *,
    observability: Dict[str, Any],
    event_type: str,
    payload: Dict[str, Any],
    emitted_at: float,
) -> Dict[str, Any] | None:
    if event_type == "agent_turn_started":
        return _start_step(
            observability,
            key=("agent_turn", str(payload.get("agent") or "")),
            kind="agent_turn",
            label=f"Agent turn: {payload.get('agent') or 'unknown'}",
            emitted_at=emitted_at,
            parent_step_index=None,
            details={
                "agent": payload.get("agent"),
                "execution_mode": payload.get("execution_mode"),
            },
        )

    if event_type == "node_started":
        return _start_step(
            observability,
            key=("node", str(payload.get("node_id") or "")),
            kind="node",
            label=f"Node: {payload.get('node_id') or 'unknown'}",
            emitted_at=emitted_at,
            parent_step_index=_active_step_index(observability, ("agent_turn", str(payload.get("agent") or ""))),
            details={
                "node_id": payload.get("node_id"),
                "node_kind": payload.get("node_kind"),
                "agent": payload.get("agent"),
            },
        )

    if event_type == "node_completed":
        return _complete_step(
            observability,
            key=("node", str(payload.get("node_id") or "")),
            emitted_at=emitted_at,
            status="completed",
            outcome={
                "node_id": payload.get("node_id"),
                "node_kind": payload.get("node_kind"),
                "transition": payload.get("transition"),
            },
            summary=f"Transition: {payload.get('transition') or 'continue'}",
        )

    if event_type == "agent_turn_completed":
        return _complete_step(
            observability,
            key=("agent_turn", str(payload.get("agent") or "")),
            emitted_at=emitted_at,
            status="completed",
            outcome={"transition": payload.get("transition")},
            summary=f"Transition: {payload.get('transition') or 'continue'}",
        )

    if event_type == "llm_call_started":
        agent_name = str(payload.get("agent") or "")
        return _start_step(
            observability,
            key=("llm_call", agent_name),
            kind="llm_call",
            label=f"LLM call: {agent_name or 'unknown'}",
            emitted_at=emitted_at,
            parent_step_index=_active_step_index(observability, ("agent_turn", agent_name)),
            details={
                "agent": payload.get("agent"),
                "profile": payload.get("profile"),
            },
        )

    if event_type == "llm_call_completed":
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
        model = payload.get("model") or "-"
        return _complete_step(
            observability,
            key=("llm_call", str(payload.get("agent") or "")),
            emitted_at=emitted_at,
            status="completed",
            outcome={
                "model": payload.get("model"),
                "profile": payload.get("profile"),
                "usage": usage,
                "estimated_cost_usd": payload.get("estimated_cost_usd"),
            },
            summary=f"Model: {model}, tokens: {total_tokens}",
        )

    if event_type == "tool_started":
        agent_name = str(payload.get("agent") or "")
        tool_name = str(payload.get("tool") or "")
        return _start_step(
            observability,
            key=("tool_call", agent_name, tool_name),
            kind="tool_call",
            label=f"Tool call: {tool_name or 'tool'}",
            emitted_at=emitted_at,
            parent_step_index=_active_step_index(observability, ("agent_turn", agent_name)),
            details={
                "agent": payload.get("agent"),
                "tool": payload.get("tool"),
                "arguments": _snapshot_value(payload.get("arguments")),
            },
        )

    if event_type == "tool_finished":
        tool_name = str(payload.get("tool") or "")
        result = payload.get("result")
        success = bool(payload.get("success"))
        return _complete_step(
            observability,
            key=("tool_call", str(payload.get("agent") or ""), tool_name),
            emitted_at=emitted_at,
            status="completed" if success else "failed",
            outcome={
                "tool": payload.get("tool"),
                "success": success,
                "result": _snapshot_value(result),
            },
            summary=f"{'Succeeded' if success else 'Failed'}: {_summarize_tool_result(result)}",
        )

    if event_type == "handoff":
        source_agent = str(payload.get("source_agent") or "")
        target_agent = str(payload.get("target_agent") or "")
        return _record_instant_step(
            observability,
            kind="handoff",
            label=f"Handoff: {source_agent or '-'} -> {target_agent or '-'}",
            emitted_at=emitted_at,
            status="completed",
            parent_step_index=_active_step_index(observability, ("agent_turn", source_agent)),
            details={
                "source_agent": payload.get("source_agent"),
                "target_agent": payload.get("target_agent"),
                "context_mode": payload.get("context_mode"),
                "return_to_caller": payload.get("return_to_caller"),
            },
            summary=(
                f"context={payload.get('context_mode') or 'whole'}, "
                f"return={'yes' if payload.get('return_to_caller') else 'no'}"
            ),
        )

    if event_type == "handoff_return":
        source_agent = str(payload.get("source_agent") or "")
        target_agent = str(payload.get("target_agent") or "")
        return _record_instant_step(
            observability,
            kind="handoff_return",
            label=f"Handoff return: {source_agent or '-'} <- {target_agent or '-'}",
            emitted_at=emitted_at,
            status="completed",
            parent_step_index=_active_step_index(observability, ("agent_turn", source_agent)),
            details={
                "source_agent": payload.get("source_agent"),
                "target_agent": payload.get("target_agent"),
                "return_transition": payload.get("return_transition"),
            },
            summary=f"Transition: {payload.get('return_transition') or 'continue'}",
        )

    if event_type == "runtime_error":
        agent_name = str(payload.get("agent") or payload.get("target_agent") or "")
        return _record_instant_step(
            observability,
            kind="runtime_error",
            label=f"Runtime error: {agent_name or 'runtime'}",
            emitted_at=emitted_at,
            status="failed",
            parent_step_index=_active_step_index(observability, ("agent_turn", agent_name)),
            details={
                "agent": payload.get("agent"),
                "target_agent": payload.get("target_agent"),
                "message": payload.get("message"),
            },
            summary=str(payload.get("message") or "Runtime error."),
        )

    return None


def _start_step(
    observability: Dict[str, Any],
    *,
    key: tuple[Any, ...],
    kind: str,
    label: str,
    emitted_at: float,
    parent_step_index: int | None,
    details: Dict[str, Any] | None = None,
    register_active: bool = True,
) -> Dict[str, Any]:
    observability["step_counter"] = int(observability.get("step_counter", 0)) + 1
    step = {
        "index": int(observability["step_counter"]),
        "kind": str(kind),
        "label": str(label),
        "status": "running",
        "parent_step_index": parent_step_index,
        "started_at_monotonic": float(emitted_at),
        "duration_ms": None,
        "summary": str(label),
        "details": dict(details or {}),
    }
    steps = observability.setdefault("steps", [])
    if isinstance(steps, list):
        steps.append(step)
    active_steps = observability.setdefault("active_steps", {})
    if register_active and isinstance(active_steps, dict):
        active_steps[key] = step["index"]
    return step


def _complete_step(
    observability: Dict[str, Any],
    *,
    key: tuple[Any, ...],
    emitted_at: float,
    status: str,
    outcome: Dict[str, Any] | None,
    summary: str,
) -> Dict[str, Any]:
    active_steps = observability.setdefault("active_steps", {})
    step_index = active_steps.pop(key, None) if isinstance(active_steps, dict) else None
    step = _step_by_index(observability, step_index)
    if step is None:
        step = _start_step(
            observability,
            key=key,
            kind=str(key[0] if key else "step"),
            label=str(summary or key[0] if key else "step"),
            emitted_at=emitted_at,
            parent_step_index=None,
            details={},
        )
        if isinstance(active_steps, dict):
            active_steps.pop(key, None)

    started_at = float(step.get("started_at_monotonic", emitted_at))
    step["status"] = str(status)
    step["duration_ms"] = max(0.0, round((float(emitted_at) - started_at) * 1000.0, 3))
    step["summary"] = str(summary or step.get("summary") or step.get("label") or step.get("kind") or "step")
    if isinstance(outcome, dict):
        details = step.get("details")
        if not isinstance(details, dict):
            details = {}
            step["details"] = details
        details["outcome"] = dict(outcome)
    return step


def _record_instant_step(
    observability: Dict[str, Any],
    *,
    kind: str,
    label: str,
    emitted_at: float,
    status: str,
    parent_step_index: int | None,
    details: Dict[str, Any] | None,
    summary: str,
) -> Dict[str, Any]:
    step = _start_step(
        observability,
        key=(kind, int(observability.get("step_counter", 0)) + 1),
        kind=kind,
        label=label,
        emitted_at=emitted_at,
        parent_step_index=parent_step_index,
        details=details,
        register_active=False,
    )
    step["status"] = str(status)
    step["duration_ms"] = 0.0
    step["summary"] = str(summary or label)
    return step


def _active_step_index(observability: Dict[str, Any], key: tuple[Any, ...]) -> int | None:
    active_steps = observability.get("active_steps")
    if not isinstance(active_steps, dict):
        return None
    step_index = active_steps.get(key)
    return int(step_index) if isinstance(step_index, int) else None


def _step_by_index(observability: Dict[str, Any], step_index: Any) -> Dict[str, Any] | None:
    if not isinstance(step_index, int) or step_index <= 0:
        return None
    steps = observability.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, dict) and step.get("index") == step_index:
            return step
    return None


def _public_step(step: Dict[str, Any]) -> Dict[str, Any]:
    details = step.get("details")
    if not isinstance(details, dict):
        details = {}
    return {
        "index": int(step.get("index", 0)),
        "kind": str(step.get("kind") or ""),
        "label": str(step.get("label") or ""),
        "status": str(step.get("status") or "completed"),
        "parent_step_index": step.get("parent_step_index"),
        "duration_ms": step.get("duration_ms"),
        "summary": str(step.get("summary") or ""),
        "details": _snapshot_value(details),
    }


def _snapshot_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _snapshot_value(item, depth=depth + 1)
            for key, item in list(value.items())[:16]
        }
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item, depth=depth + 1) for item in list(value)[:16]]
    return repr(value)


def _summarize_value(value: Any, *, limit: int = 96) -> str:
    text = repr(_snapshot_value(value))
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_tool_result(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("success") is False and result.get("error"):
            return str(result.get("error"))
        if "approved" in result:
            return f"approved={result.get('approved')}"
        if "value" in result:
            return f"value={_summarize_value(result.get('value'))}"
        if "result" in result:
            return _summarize_value(result.get("result"))
    return _summarize_value(result)
