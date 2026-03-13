from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


COMMAND_VISIBILITIES = ("private", "delegated", "exported")


@dataclass(frozen=True)
class CommandSpec:
    name: str
    acp_action: str
    owner: str
    visibility: str = "exported"
    description: str = ""
    required_capabilities: tuple[str, ...] = ()
    payload_schema: Mapping[str, Any] = field(default_factory=dict)
    result_schema: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class CommandContext:
    engine: Any
    cli_context: dict[str, Any]
    caller_agent: str | None
    active_agent: str | None
    session_id: str | None
    capabilities: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CommandInvocation:
    command_name: str
    args: tuple[str, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    caller_agent: str | None = None
    active_agent: str | None = None
    session_id: str | None = None
    visibility: str | None = None
    capabilities: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class CommandResult:
    handled: bool
    output: str | None = None
    exit_requested: bool = False
    data: Mapping[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class CommandProvider(Protocol):
    def list_commands(self, *, visibility: str = "exported") -> list[CommandSpec]:
        ...

    def invoke(self, name: str, args: list[str], ctx: CommandContext) -> CommandResult:
        ...


def normalize_command_visibility(value: str | None) -> str:
    cleaned = str(value or "").strip().lower() or "exported"
    if cleaned not in COMMAND_VISIBILITIES:
        raise ValueError(
            f"Unsupported command visibility '{value}'. Expected one of: {', '.join(COMMAND_VISIBILITIES)}."
        )
    return cleaned


def command_result_from_mapping(raw: Mapping[str, Any] | None) -> CommandResult | None:
    if raw is None:
        return None
    handled = bool(raw.get("handled"))
    output = raw.get("output")
    exit_requested = bool(raw.get("exit_requested"))
    metadata = raw.get("metadata")
    return CommandResult(
        handled=handled,
        output=str(output) if output is not None else None,
        exit_requested=exit_requested,
        data=dict(raw.get("data") or {}) if isinstance(raw.get("data"), Mapping) else {},
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


class StaticCommandProvider:
    def __init__(self, *, commands: list[CommandSpec], handler: Any):
        self._commands = list(commands)
        self._handler = handler

    def list_commands(self, *, visibility: str = "exported") -> list[CommandSpec]:
        normalized = normalize_command_visibility(visibility)
        return [command for command in self._commands if command.visibility == normalized]

    def invoke(self, name: str, args: list[str], ctx: CommandContext) -> CommandResult:
        return self._handler(name, args, ctx)


def build_command_invocation(
    command_name: str,
    *,
    args: list[str] | tuple[str, ...] | None = None,
    caller_agent: str | None = None,
    active_agent: str | None = None,
    session_id: str | None = None,
    visibility: str | None = None,
    capabilities: set[str] | frozenset[str] | None = None,
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CommandInvocation:
    return CommandInvocation(
        command_name=str(command_name or "").strip().lstrip("/"),
        args=tuple(str(item) for item in (args or ())),
        payload=dict(payload or {}),
        caller_agent=str(caller_agent).strip() or None if caller_agent is not None else None,
        active_agent=str(active_agent).strip() or None if active_agent is not None else None,
        session_id=str(session_id).strip() or None if session_id is not None else None,
        visibility=str(visibility).strip().lower() or None if visibility is not None else None,
        capabilities=frozenset(str(item).strip() for item in (capabilities or set()) if str(item).strip()),
        metadata=dict(metadata or {}),
    )
