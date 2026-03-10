from __future__ import annotations

from typing import Any, Dict
import yaml

from pocketcode.cli.runtime_events import format_runtime_event

from .shared import _build_output_text, _build_stats_text
from .store import OutputBlock, TextualRuntimeState


def select_output_text(state: TextualRuntimeState) -> str:
    return _build_output_text(list(state.output_lines), state.trimmed_output_line_count)


def select_modal_label(state: TextualRuntimeState) -> str:
    if not state.active_modal_kind:
        return "none"
    return state.active_modal_title or state.active_modal_kind


def select_inspector_summary_text(
    *,
    runtime_state: TextualRuntimeState,
    status: Dict[str, Any],
    active_profile: Any,
    active_skill_names: tuple[str, ...],
    global_llm_override: str | None,
    auto_confirm_tools: bool,
) -> str:
    session_default = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or "__inherit__"
    active_profile_name = active_profile.name if active_profile else None
    run_summary = status.get("last_run_summary", {})
    if not isinstance(run_summary, dict):
        run_summary = {}
    summary_lines = [
        f"Agent: {active_profile_name or 'none'}",
        f"Internal flow: {status.get('runtime_flow') or 'internal-flow'}",
        f"Agent source: {active_profile.source if active_profile else '-'}",
        f"Global LLM: {global_llm_override or 'inherit'}",
        f"Skills: {', '.join(active_skill_names) if active_skill_names else 'none'}",
        f"Auto-confirm: {'on' if auto_confirm_tools else 'off'}",
        f"Session confirm: {session_default}",
        f"Session debug breaks: {len(status.get('session_debugger_breakpoints', []) or [])}",
        f"Modal: {select_modal_label(runtime_state)}",
        f"Runtime events: {run_summary.get('runtime_event_count', 0)}",
        f"Runtime steps: {run_summary.get('step_count', 0)}",
        _build_stats_text(status),
    ]
    if active_profile and active_profile.description:
        summary_lines.append(f"Agent note: {active_profile.description}")
    active_session = status.get("active_session", {}) if isinstance(status, dict) else {}
    if isinstance(active_session, dict) and active_session.get("title"):
        summary_lines.append(
            f"Active session: {active_session.get('title')} ({active_session.get('session_id') or '-'})"
        )
    warning_labels: list[str] = []
    for item in run_summary.get("vm_validation_warnings", []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        location = _build_warning_location_label(item)
        warning_labels.append(f"{code}@{location}" if location else code)
    if warning_labels:
        summary_lines.append(f"VM warnings: {'; '.join(warning_labels)}")
    return "\n".join(summary_lines)


def select_inspector_summary_blocks(
    *,
    runtime_state: TextualRuntimeState,
    status: Dict[str, Any],
    active_profile: Any,
    active_skill_names: tuple[str, ...],
    global_llm_override: str | None,
    auto_confirm_tools: bool,
) -> tuple[OutputBlock, ...]:
    return (
        OutputBlock(
            kind="info",
            title="Inspector Summary",
            text=select_inspector_summary_text(
                runtime_state=runtime_state,
                status=status,
                active_profile=active_profile,
                active_skill_names=active_skill_names,
                global_llm_override=global_llm_override,
                auto_confirm_tools=auto_confirm_tools,
            ),
        ),
    )


def _format_debugger_summary(debugger_state: Dict[str, Any]) -> list[str]:
    snapshot = debugger_state.get("snapshot", {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    pause_event = debugger_state.get("pause_event", {})
    if not isinstance(pause_event, dict):
        pause_event = {}
    breakpoints = debugger_state.get("breakpoints", ())
    lines = [
        f"attached: {'yes' if debugger_state.get('attached') else 'no'}",
        f"paused: {'yes' if debugger_state.get('paused') else 'no'}",
        f"active_agent: {snapshot.get('active_agent') or 'unknown'}",
    ]
    if snapshot.get("active_node_id"):
        lines.append(
            f"active_node: {snapshot.get('active_node_id')} ({snapshot.get('active_node_kind') or 'node'})"
        )
    if pause_event:
        lines.append(f"pause_event: {format_runtime_event(pause_event)}")
    if debugger_state.get("until_label"):
        lines.append(f"stop_condition: {debugger_state.get('until_label')}")
    lines.append(f"breakpoints: {len(tuple(breakpoints))}")
    lines.append(f"runtime_event_count: {snapshot.get('runtime_event_count', 0)}")
    lines.append(f"step_count: {snapshot.get('step_count', 0)}")
    return lines


def select_run_preview_text(
    state: TextualRuntimeState,
    status: Dict[str, Any],
    *,
    debugger_state: Dict[str, Any] | None = None,
) -> str:
    run_summary = status.get("last_run_summary", {})
    if not isinstance(run_summary, dict):
        run_summary = {}

    lines = [
        f"live_run_status: {state.run_status}",
        f"active_modal: {state.active_modal_kind or 'none'}",
        f"active_modal_title: {state.active_modal_title or '-'}",
        f"internal_flow: {status.get('runtime_flow') or 'internal-flow'}",
        f"active_agent: {status.get('agent') or 'auto'}",
        f"active_profile: {status.get('active_agent_profile') or 'none'}",
        f"global_llm_override: {status.get('global_llm_override') or 'none'}",
        f"agent_path: {run_summary.get('agent_path', [])}",
        f"current_llm_profile: {run_summary.get('current_llm_profile') or 'none'}",
        f"current_llm_model: {run_summary.get('current_llm_model') or '-'}",
        f"llm_usage: {run_summary.get('llm_usage', {})}",
        f"llm_cost_usd: {run_summary.get('llm_cost_usd', 0.0)}",
        f"runtime_event_count: {run_summary.get('runtime_event_count', 0)}",
        f"step_count: {run_summary.get('step_count', 0)}",
        f"vm_validation_warning_count: {run_summary.get('vm_validation_warning_count', 0)}",
        f"vm_validation_warnings: {run_summary.get('vm_validation_warnings', [])}",
        f"context_stats: {run_summary.get('context_stats', {})}",
        f"session_confirmation: {status.get('session_tool_confirmation_overrides', {})}",
    ]
    if isinstance(debugger_state, dict):
        lines.append("debugger:")
        lines.extend(f"- {item}" for item in _format_debugger_summary(debugger_state))
    step_timeline = _format_run_steps(run_summary.get("steps", []), limit=8)
    if step_timeline:
        lines.append("steps:")
        lines.extend(f"- {item}" for item in step_timeline)
    if state.live_run_events:
        lines.append("live_events:")
        lines.extend(f"- {item}" for item in state.live_run_events[-8:])
    return "\n".join(lines)


def _dump_preview_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        dumped = yaml.safe_dump(value, sort_keys=False, allow_unicode=False).strip()
        return dumped or repr(value)
    return repr(value)


def _build_warning_location_label(item: Dict[str, Any]) -> str:
    span = item.get("span")
    if isinstance(span, dict):
        start_line = span.get("start_line")
        start_column = span.get("start_column")
        end_line = span.get("end_line")
        end_column = span.get("end_column")
        if all(isinstance(value, int) and value > 0 for value in (start_line, start_column, end_line, end_column)):
            if start_line == end_line:
                if start_column == end_column:
                    return f"{start_line}:{start_column}"
                return f"{start_line}:{start_column}-{end_column}"
            return f"{start_line}:{start_column}-{end_line}:{end_column}"
    return str(item.get("location") or "").strip()


def _format_run_steps(raw_steps: Any, *, limit: int) -> list[str]:
    if not isinstance(raw_steps, list):
        return []

    rendered: list[str] = []
    for step in raw_steps[-max(limit, 0) :]:
        if not isinstance(step, dict):
            continue
        index = step.get("index")
        kind = str(step.get("kind") or "step")
        status = str(step.get("status") or "completed")
        summary = str(step.get("summary") or step.get("label") or kind)
        duration = step.get("duration_ms")
        duration_suffix = f" [{float(duration):.1f}ms]" if isinstance(duration, (int, float)) else ""
        rendered.append(f"{index}. {kind} ({status}){duration_suffix} {summary}")
    return rendered


def select_run_preview_blocks(
    state: TextualRuntimeState,
    status: Dict[str, Any],
    *,
    debugger_state: Dict[str, Any] | None = None,
) -> tuple[OutputBlock, ...]:
    run_summary = status.get("last_run_summary", {})
    if not isinstance(run_summary, dict):
        run_summary = {}

    overview_lines = [
        f"live_run_status: {state.run_status}",
        f"active_modal: {state.active_modal_kind or 'none'}",
        f"internal_flow: {status.get('runtime_flow') or 'internal-flow'}",
        f"active_agent: {status.get('agent') or 'auto'}",
        f"active_profile: {status.get('active_agent_profile') or 'none'}",
        f"global_llm_override: {status.get('global_llm_override') or 'none'}",
    ]

    blocks: list[OutputBlock] = [
        OutputBlock(kind="info", title="Run Preview", text="\n".join(overview_lines)),
        OutputBlock(
            kind="code",
            title="Run Summary",
            text=_dump_preview_value(
                {
                    "agent_path": run_summary.get("agent_path", []),
                    "current_llm_profile": run_summary.get("current_llm_profile") or "none",
                    "current_llm_model": run_summary.get("current_llm_model") or "-",
                    "llm_usage": run_summary.get("llm_usage", {}),
                    "llm_cost_usd": run_summary.get("llm_cost_usd", 0.0),
                    "runtime_event_count": run_summary.get("runtime_event_count", 0),
                    "step_count": run_summary.get("step_count", 0),
                    "vm_validation_warning_count": run_summary.get("vm_validation_warning_count", 0),
                    "vm_validation_warnings": run_summary.get("vm_validation_warnings", []),
                    "context_stats": run_summary.get("context_stats", {}),
                    "session_confirmation": status.get("session_tool_confirmation_overrides", {}),
                }
            ),
            language="yaml",
        ),
    ]
    if isinstance(debugger_state, dict):
        blocks.append(
            OutputBlock(
                kind="code",
                title="Debugger",
                text="\n".join(_format_debugger_summary(debugger_state)),
                language="text",
            )
        )
        for item in tuple(debugger_state.get("breakpoints", ())):
            if not isinstance(item, dict):
                continue
            breakpoint_id = item.get("id")
            label = str(item.get("label") or "").strip()
            if breakpoint_id is None or not label:
                continue
            blocks.append(
                OutputBlock(
                    kind="code",
                    title=f"Breakpoint #{int(breakpoint_id)}",
                    text=label,
                    language="text",
                )
            )
    step_timeline = _format_run_steps(run_summary.get("steps", []), limit=12)
    if step_timeline:
        blocks.append(
            OutputBlock(
                kind="code",
                title="Step Timeline",
                text="\n".join(step_timeline),
                language="text",
            )
        )
    if state.live_run_events:
        blocks.append(
            OutputBlock(
                kind="code",
                title="Recent Live Events",
                text="\n".join(state.live_run_events[-8:]),
                language="text",
            )
        )
    return tuple(blocks)


def select_context_preview(cli_context: Dict[str, Any]) -> str:
    if not any(cli_context.values()):
        return "No context selected."

    lines: list[str] = []
    for label, key in (("Files", "files"), ("Folders", "folders"), ("URLs", "urls")):
        values = sorted(cli_context.get(key, set()) or set())
        if values:
            lines.append(f"{label}:")
            lines.extend(f"- {value}" for value in values)
    snippets = cli_context.get("snippets", {})
    if isinstance(snippets, dict) and snippets:
        lines.append("Snippets:")
        for name, content in sorted(snippets.items()):
            lines.append(f"- {name}: {content}")
    return "\n".join(lines)


def select_context_summary(status: Dict[str, Any], cli_context: Dict[str, Any]) -> str:
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
    if not isinstance(context_stats, dict):
        context_stats = {}

    lines = [
        f"session_id: {status.get('active_session_id') or '-'}",
        f"session_title: {status.get('active_session_title') or '-'}",
        f"files: {context_stats.get('files', len(cli_context.get('files', set()) or set()))}",
        f"folders: {context_stats.get('folders', len(cli_context.get('folders', set()) or set()))}",
        f"urls: {context_stats.get('urls', len(cli_context.get('urls', set()) or set()))}",
        f"snippets: {context_stats.get('snippets', len(cli_context.get('snippets', {}) or {}))}",
        f"snippet_chars: {context_stats.get('snippet_chars', 0)}",
        "",
        select_context_preview(cli_context),
    ]
    return "\n".join(lines)


def select_context_blocks(status: Dict[str, Any], cli_context: Dict[str, Any]) -> tuple[OutputBlock, ...]:
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
    if not isinstance(context_stats, dict):
        context_stats = {}

    overview = {
        "session_id": status.get("active_session_id") or "-",
        "session_title": status.get("active_session_title") or "-",
        "files": context_stats.get("files", len(cli_context.get("files", set()) or set())),
        "folders": context_stats.get("folders", len(cli_context.get("folders", set()) or set())),
        "urls": context_stats.get("urls", len(cli_context.get("urls", set()) or set())),
        "snippets": context_stats.get("snippets", len(cli_context.get("snippets", {}) or {})),
        "snippet_chars": context_stats.get("snippet_chars", 0),
    }
    preview = select_context_preview(cli_context)
    blocks = [
        OutputBlock(kind="code", title="Context Summary", text=_dump_preview_value(overview), language="yaml"),
    ]
    if preview.strip():
        blocks.append(OutputBlock(kind="code", title="Context Preview", text=preview, language="text"))
    return tuple(blocks)


def select_saved_sessions_summary(sessions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> str:
    if sessions is None:
        return "Saved session history is unavailable."
    if not sessions:
        return "No saved sessions."
    lines: list[str] = []
    for item in sessions[:8]:
        marker = "*" if item.get("is_active") else "-"
        lines.append(
            f"{marker} {item.get('title') or '-'} | {item.get('session_id') or '-'} | {item.get('updated_at') or '-'}"
        )
    if len(sessions) > 8:
        lines.append(f"... {len(sessions) - 8} more")
    return "\n".join(lines)


def select_saved_sessions_blocks(
    sessions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[OutputBlock, ...]:
    if sessions is None:
        return (OutputBlock(kind="info", title="Saved Sessions", text="Saved session history is unavailable."),)
    if not sessions:
        return (OutputBlock(kind="info", title="Saved Sessions", text="No saved sessions."),)

    summary_items = []
    for item in sessions[:8]:
        summary_items.append(
            {
                "active": bool(item.get("is_active")),
                "title": item.get("title") or "-",
                "session_id": item.get("session_id") or "-",
                "updated_at": item.get("updated_at") or "-",
            }
        )
    return (
        OutputBlock(kind="code", title="Saved Sessions", text=_dump_preview_value(summary_items), language="yaml"),
    )


def select_prompt_summary(prompt_sources: tuple[str, ...], active_profile: Any) -> str:
    extra_prompts = list(active_profile.extra_prompts) if active_profile else []
    lines: list[str] = []
    if prompt_sources:
        lines.append("Agent prompt sources:")
        lines.extend(f"- {path}" for path in prompt_sources)
    if extra_prompts:
        lines.append("Profile extra prompts:")
        lines.extend(f"- {path}" for path in extra_prompts)
    if not lines:
        return "No prompt sources registered."
    return "\n".join(lines)


def select_prompt_summary_blocks(prompt_sources: tuple[str, ...], active_profile: Any) -> tuple[OutputBlock, ...]:
    extra_prompts = list(active_profile.extra_prompts) if active_profile else []
    payload = {
        "agent_prompt_sources": list(prompt_sources),
        "profile_extra_prompts": extra_prompts,
    }
    if not prompt_sources and not extra_prompts:
        return (OutputBlock(kind="info", title="Prompt Sources", text="No prompt sources registered."),)
    return (
        OutputBlock(kind="code", title="Prompt Sources", text=_dump_preview_value(payload), language="yaml"),
    )
