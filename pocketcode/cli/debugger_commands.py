from __future__ import annotations

import ast
import shlex
from typing import Any, Dict


def split_debugger_command(command: str) -> list[str]:
    text = str(command or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return [text]


def parse_debug_step_count(args: list[str]) -> int | None:
    if not args:
        return 1
    if len(args) != 1:
        return None
    try:
        count = int(args[0])
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None


def build_debugger_until_predicate(
    args: list[str],
) -> tuple[Any, str] | None:
    if not args:
        return None
    target = args[0].lower()
    rest = args[1:]

    if target == "node" and len(rest) == 1:
        node_id = rest[0]
        return (
            lambda event, _snapshot, node_id=node_id: str(event.get("node_id") or "") == node_id,
            f"until node {node_id}",
        )

    if target == "agent" and len(rest) == 1:
        agent_name = rest[0]
        return (
            lambda event, snapshot, agent_name=agent_name: (
                str(event.get("agent") or snapshot.get("active_agent") or "") == agent_name
            ),
            f"until agent {agent_name}",
        )

    if target == "tool" and len(rest) == 1:
        tool_name = rest[0]
        return (
            lambda event, snapshot, tool_name=tool_name: (
                str(event.get("tool") or lookup_path(snapshot, "pending_tool.name") or "") == tool_name
            ),
            f"until tool {tool_name}",
        )

    if target == "event" and len(rest) == 1:
        event_type = rest[0]
        return (
            lambda event, _snapshot, event_type=event_type: str(event.get("type") or "") == event_type,
            f"until event {event_type}",
        )

    if target in {"handoff", "error", "answer", "ask"} and not rest:
        event_map = {
            "handoff": "handoff",
            "error": "runtime_error",
            "answer": "final_answer",
            "ask": "ask_user",
        }
        event_type = event_map[target]
        return (
            lambda event, _snapshot, event_type=event_type: str(event.get("type") or "") == event_type,
            f"until event {event_type}",
        )

    if target == "when" and rest:
        parsed = parse_debugger_condition(" ".join(rest))
        if parsed is None:
            return None
        lhs, operator, rhs = parsed

        def _predicate(
            event: Dict[str, Any],
            snapshot: Dict[str, Any],
            *,
            lhs: str = lhs,
            operator: str = operator,
            rhs: Any = rhs,
        ) -> bool:
            value = resolve_debugger_value(lhs, event=event, snapshot=snapshot)
            if operator == "==":
                return value == rhs
            if operator == "!=":
                return value != rhs
            return False

        return (_predicate, f"until when {lhs} {operator} {rhs!r}")

    return None


def build_debugger_predicate_from_label(label: str) -> tuple[Any, str] | None:
    text = str(label or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("until "):
        text = text[6:].strip()
    elif lowered.startswith("break "):
        text = text[6:].strip()
    return build_debugger_until_predicate(split_debugger_command(text))


def parse_debugger_condition(expression: str) -> tuple[str, str, Any] | None:
    text = str(expression or "").strip()
    for operator in ("==", "!="):
        if operator not in text:
            continue
        lhs, rhs = text.split(operator, 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        if not lhs or not rhs:
            return None
        return lhs, operator, coerce_debugger_literal(rhs)
    return None


def coerce_debugger_literal(raw: str) -> Any:
    text = str(raw or "").strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None
    try:
        return ast.literal_eval(text)
    except Exception:
        return text.strip("\"'")


def resolve_debugger_value(path: str, *, event: Dict[str, Any], snapshot: Dict[str, Any]) -> Any:
    normalized = str(path or "").strip()
    if not normalized:
        return None
    if normalized.startswith("event."):
        return lookup_path(event, normalized[len("event."):])
    if normalized.startswith("snapshot."):
        return lookup_path(snapshot, normalized[len("snapshot."):])

    event_value = lookup_path(event, normalized)
    if event_value is not None:
        return event_value
    return lookup_path(snapshot, normalized)


def lookup_path(value: Any, path: str) -> Any:
    current = value
    for segment in [part.strip() for part in str(path or "").split(".") if part.strip()]:
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current
