from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import yaml

NO_LLM = "__none__"
NO_MODE = "__none_mode__"
UNSET_OPTION = "__unset__"
INHERIT_POLICY = "__inherit__"
LOADING_OPTION = "__loading__"
MAX_OUTPUT_LINES = 400
SKILL_GROUP_PREFIX = "__skill_group__:"
TEXTUAL_VIEWS = {
    "chat": {
        "label": "Chat",
        "description": "Output console and conversation history",
    },
    "control": {
        "label": "Control",
        "description": "Runtime controls and Textual workspace settings",
    },
    "run": {
        "label": "Run",
        "description": "Run inspector and effective runtime state",
    },
}
VIEW_TITLES = {
    "control": "Control Center",
    "run": "Run Inspector",
}
THEME_OPTIONS = {
    "ocean": "Ocean",
    "forest": "Forest",
    "ember": "Ember",
}
WORKSPACE_VIEWS = {
    "balanced": {"label": "Balanced", "view": "chat", "right": True},
    "chat_focus": {"label": "Chat Focus", "view": "chat", "right": True},
    "control_desk": {"label": "Control Desk", "view": "control", "right": True},
    "minimal": {"label": "Minimal", "view": "chat", "right": False},
    "review": {"label": "Review", "view": "run", "right": True},
}


def _tool_group_name(tool_name: str) -> str:
    cleaned = str(tool_name).strip()
    if not cleaned:
        return "other"
    if "::" in cleaned:
        return cleaned.split("::", 1)[0]
    if "." in cleaned:
        return cleaned.split(".", 1)[0]
    return "other"


def _build_stats_text(status: Dict[str, Any]) -> str:
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    llm_usage = run_summary.get("llm_usage", {}) if isinstance(run_summary, dict) else {}
    cost = run_summary.get("llm_cost_usd", 0.0) if isinstance(run_summary, dict) else 0.0
    session_confirm = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or "inherit"
    text = (
        f"Tokens in={llm_usage.get('prompt_tokens', 0)} "
        f"out={llm_usage.get('completion_tokens', 0)} total={llm_usage.get('total_tokens', 0)} | "
        f"Cost=${float(cost):.6f} | Session confirm={session_confirm}"
    )
    active_session = status.get("active_session", {}) if isinstance(status, dict) else {}
    session_title = active_session.get("title") if isinstance(active_session, dict) else None
    if session_title:
        text = f"{text} | Session={session_title}"
    return text


def _resolve_status_display_parts(status: Dict[str, Any]) -> tuple[str, str, str, str]:
    runtime_flow = status.get("runtime_flow") or "internal-flow"
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}

    current_llm_profile = str(
        status.get("selected_llm_profile")
        or status.get("global_llm_override")
        or status.get("default_llm_profile")
        or "none"
    )
    last_llm_profile = run_summary.get("current_llm_profile") if isinstance(run_summary, dict) else None
    current_llm_model = (
        run_summary.get("current_llm_model")
        if isinstance(run_summary, dict) and last_llm_profile == current_llm_profile
        else "-"
    )
    active_agent = (
        status.get("selected_agent")
        or status.get("agent")
        or status.get("active_agent")
        or status.get("active_agent_profile")
        or "none"
    )
    return str(runtime_flow), str(active_agent), str(current_llm_profile), str(current_llm_model or "-")


def _build_status_text(status: Dict[str, Any], current_view: str) -> str:
    runtime_flow, active_agent, current_llm_profile, current_llm_model = _resolve_status_display_parts(status)
    return f"Runtime flow: {runtime_flow} | Agent: {active_agent} | LLM: {current_llm_profile} ({current_llm_model})"


def _build_header_summary_text(status: Dict[str, Any]) -> str:
    runtime_flow, _, _, _ = _resolve_status_display_parts(status)
    return f"Runtime flow: {runtime_flow}"


def _build_header_agent_text(status: Dict[str, Any]) -> str:
    _, active_agent, _, _ = _resolve_status_display_parts(status)
    return f"Agent: {active_agent}"


def _build_header_llm_text(status: Dict[str, Any]) -> str:
    _, _, current_llm_profile, current_llm_model = _resolve_status_display_parts(status)
    return f"LLM: {current_llm_profile} ({current_llm_model})"


def _build_view_title_text(view_name: str) -> str:
    return VIEW_TITLES.get(view_name, "")


def _build_profile_editor_hint(active_profile: Any) -> str:
    if active_profile is None:
        return "Select an agent to edit agent settings."
    if active_profile.source == "workspace":
        return f"Editing workspace agent '{active_profile.name}'. Save persists tools, skills, prompts, and LLM."
    return f"Agent '{active_profile.name}' is plugin/synthesised. Clone it to a workspace agent to edit."


def _dump_yaml_text(payload: Dict[str, Any]) -> str:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()
    return text or "{}"


def _load_yaml_mapping(text: str, *, label: str) -> Dict[str, Any]:
    loaded = yaml.safe_load(text) if text.strip() else {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a YAML mapping.")
    return loaded


def _trim_output_lines(lines: list[str], max_lines: int) -> tuple[list[str], int]:
    if max_lines <= 0:
        return [], len(lines)
    overflow = max(0, len(lines) - max_lines)
    if overflow == 0:
        return list(lines), 0
    return list(lines[overflow:]), overflow


def _build_output_text(lines: list[str], trimmed_line_count: int) -> str:
    if trimmed_line_count <= 0:
        return "\n".join(lines)
    notice = f"info> [output history trimmed: showing last {len(lines)} lines]"
    return "\n".join([notice, *lines]) if lines else notice


@dataclass(frozen=True)
class SelectViewState:
    options: tuple[tuple[str, str], ...]
    value: str


@dataclass(frozen=True)
class TextualUIState:
    theme_name: str
    current_view: str
    right_panel_visible: bool
    status_text: str
    header_agent_text: str
    header_llm_text: str
    view_title_text: str
    workspace_view_select: SelectViewState
    theme_select: SelectViewState
    profile_select: SelectViewState
    llm_select: SelectViewState
    session_confirm_select: SelectViewState
    auto_confirm_tools: bool
    inspector_summary_text: str
    inspector_context_text: str
    inspector_sessions_text: str
    skill_list_options: tuple[tuple[str, str, bool], ...]
    tool_list_options: tuple[tuple[str, str, bool], ...]
    inspector_prompts_text: str
    profile_list_names: tuple[str, ...]
    profile_list_labels: tuple[str, ...]
    run_preview_text: str


@dataclass(frozen=True)
class PickerOption:
    value: str
    label: str
    description: str = ""
    search_text: str = ""
