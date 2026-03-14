from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeEffect:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


def serialize_runtime_effect(effect: RuntimeEffect | dict[str, Any] | None) -> dict[str, Any] | None:
    if effect is None:
        return None
    if isinstance(effect, RuntimeEffect):
        return asdict(effect)
    if isinstance(effect, dict):
        kind = str(effect.get("kind") or "").strip()
        payload = effect.get("payload", {}) if isinstance(effect.get("payload"), dict) else {}
        return {"kind": kind, "payload": dict(payload)}
    raise TypeError(f"Unsupported runtime effect {type(effect)!r}")


def transition_from_runtime_effect(effect: RuntimeEffect | dict[str, Any] | None) -> str | None:
    serialized = serialize_runtime_effect(effect)
    if not serialized:
        return None
    kind = str(serialized.get("kind") or "").strip()
    payload = serialized.get("payload", {}) if isinstance(serialized.get("payload"), dict) else {}
    if not kind:
        return None
    if kind == "transition":
        name = str(payload.get("name") or "").strip()
        return name or "continue"
    return kind


def final_answer_effect(answer: str) -> RuntimeEffect:
    return RuntimeEffect(kind="final_answer", payload={"answer": str(answer)})


def ask_user_effect(question: str) -> RuntimeEffect:
    return RuntimeEffect(kind="ask_user", payload={"question": str(question)})


def handoff_effect(target_agent: str) -> RuntimeEffect:
    return RuntimeEffect(kind="handoff", payload={"target_agent": str(target_agent)})


def call_tool_effect(*, tool_name: str, arguments: dict[str, Any], requested_by: str) -> RuntimeEffect:
    return RuntimeEffect(
        kind="call_tool",
        payload={
            "tool_name": str(tool_name),
            "arguments": dict(arguments),
            "requested_by": str(requested_by),
        },
    )


def transition_effect(name: str) -> RuntimeEffect:
    return RuntimeEffect(kind="transition", payload={"name": str(name)})
