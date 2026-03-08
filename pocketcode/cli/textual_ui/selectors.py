from __future__ import annotations

from typing import Any, Dict

from .shared import _build_output_text, _build_stats_text
from .store import TextualRuntimeState


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
    summary_lines = [
        f"Agent: {active_profile_name or 'none'}",
        f"Internal flow: {status.get('runtime_flow') or 'internal-flow'}",
        f"Agent source: {active_profile.source if active_profile else '-'}",
        f"Global LLM: {global_llm_override or 'inherit'}",
        f"Skills: {', '.join(active_skill_names) if active_skill_names else 'none'}",
        f"Auto-confirm: {'on' if auto_confirm_tools else 'off'}",
        f"Session confirm: {session_default}",
        f"Modal: {select_modal_label(runtime_state)}",
        _build_stats_text(status),
    ]
    if active_profile and active_profile.description:
        summary_lines.append(f"Agent note: {active_profile.description}")
    active_session = status.get("active_session", {}) if isinstance(status, dict) else {}
    if isinstance(active_session, dict) and active_session.get("title"):
        summary_lines.append(
            f"Active session: {active_session.get('title')} ({active_session.get('session_id') or '-'})"
        )
    return "\n".join(summary_lines)


def select_run_preview_text(state: TextualRuntimeState, status: Dict[str, Any]) -> str:
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
        f"context_stats: {run_summary.get('context_stats', {})}",
        f"session_confirmation: {status.get('session_tool_confirmation_overrides', {})}",
    ]
    if state.live_run_events:
        lines.append("live_events:")
        lines.extend(f"- {item}" for item in state.live_run_events[-8:])
    return "\n".join(lines)


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