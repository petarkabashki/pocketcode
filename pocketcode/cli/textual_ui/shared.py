from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import yaml

NO_LLM = "__none__"
UNSET_OPTION = "__unset__"
INHERIT_POLICY = "__inherit__"
LOADING_OPTION = "__loading__"
MAX_OUTPUT_LINES = 400
DEFAULT_MAIN_INPUT_PLACEHOLDER = "Type a request or /command. F2 history F5 views F10 details"
SKILL_GROUP_PREFIX = "__skill_group__:"
TEXTUAL_VIEWS = {
    "chat": {
        "label": "Chat",
        "description": "Output console and conversation history",
    },
    "run": {
        "label": "Run",
        "description": "Run inspector and effective runtime state",
    },
}
VIEW_TITLES = {
    "chat": "Conversation",
    "run": "Run Inspector",
}


@dataclass(frozen=True)
class TextualThemePalette:
    name: str
    label: str
    app_bg: str
    text_primary: str
    text_muted: str
    surface_1: str
    surface_2: str
    border: str
    accent: str
    success: str
    warning: str
    error: str
    info: str
    input_border: str


def _theme_css(palette: TextualThemePalette) -> str:
    return f"""
    Screen.theme-{palette.name} {{
        background: {palette.app_bg};
        color: {palette.text_primary};
    }}

    Screen.theme-{palette.name} #topbar {{
        background: {palette.surface_2};
        border-bottom: solid {palette.accent};
    }}

    Screen.theme-{palette.name} Footer {{
        background: {palette.surface_1};
        color: {palette.text_primary};
    }}

    Screen.theme-{palette.name} .view {{
        background: {palette.surface_1};
        border: round {palette.border};
    }}

    Screen.theme-{palette.name} #view-title {{
        background: {palette.surface_2};
        color: {palette.text_primary};
        border: round {palette.accent};
    }}

    Screen.theme-{palette.name} .card,
    Screen.theme-{palette.name} #output,
    Screen.theme-{palette.name} #run-preview,
    Screen.theme-{palette.name} #inspector-prompts {{
        background: {palette.surface_2};
        border: round {palette.border};
        color: {palette.text_primary};
    }}

    Screen.theme-{palette.name} #main-input {{
        border: round {palette.input_border};
    }}

    Screen.theme-{palette.name} VerticalScroll:focus {{
        border: round {palette.input_border};
    }}
    """


THEME_PALETTES = {
    "ocean": TextualThemePalette(
        name="ocean",
        label="Ocean",
        app_bg="#0f172a",
        text_primary="#e2e8f0",
        text_muted="#93c5fd",
        surface_1="#111827",
        surface_2="#082f49",
        border="#334155",
        accent="#0ea5e9",
        success="#22c55e",
        warning="#f59e0b",
        error="#f87171",
        info="#38bdf8",
        input_border="#f59e0b",
    ),
    "forest": TextualThemePalette(
        name="forest",
        label="Forest",
        app_bg="#0b1510",
        text_primary="#ecfccb",
        text_muted="#bef264",
        surface_1="#102018",
        surface_2="#16351f",
        border="#365314",
        accent="#65a30d",
        success="#84cc16",
        warning="#eab308",
        error="#fb7185",
        info="#4ade80",
        input_border="#84cc16",
    ),
    "ember": TextualThemePalette(
        name="ember",
        label="Ember",
        app_bg="#1a120c",
        text_primary="#ffedd5",
        text_muted="#fdba74",
        surface_1="#22140d",
        surface_2="#3b1d10",
        border="#9a3412",
        accent="#fb923c",
        success="#f59e0b",
        warning="#fb923c",
        error="#f97316",
        info="#fdba74",
        input_border="#fb923c",
    ),
}

THEME_OPTIONS = {name: palette.label for name, palette in THEME_PALETTES.items()}
THEME_CSS = "\n".join(_theme_css(palette) for palette in THEME_PALETTES.values())

WORKSPACE_VIEWS = {
    "balanced": {"label": "Balanced", "view": "chat", "right": True},
    "chat_focus": {"label": "Chat Focus", "view": "chat", "right": True},
    "minimal": {"label": "Minimal", "view": "chat", "right": False},
    "review": {"label": "Review", "view": "run", "right": True},
}


def _tool_group_name(tool_name: str) -> str:
    cleaned = str(tool_name).strip()
    if not cleaned:
        return "other"
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


def _surface_label(surface_id: str | None) -> str:
    labels = {
        "output": "Chat",
        "run-preview": "Run Preview",
        "inspector-summary": "Runtime Summary",
        "inspector-context": "Session Context",
        "inspector-sessions": "Session History",
        "inspector-prompts": "Prompt Sources",
    }
    return labels.get(str(surface_id or ""), "No panel")


def _build_navigation_status_text(
    *,
    surface_id: str | None,
    selected_position: int | None,
    compactable_count: int,
    expanded: bool,
) -> str:
    label = _surface_label(surface_id)
    if surface_id is None:
        return "Panel: none | Ctrl+Up/Down surfaces | Ctrl+Left/Right blocks | Ctrl+E expand"
    if compactable_count <= 0:
        return f"Panel: {label} | No compacted blocks | Ctrl+Up/Down surfaces"
    block_text = (
        f"Block {selected_position} of {compactable_count}"
        if selected_position is not None
        else f"Block 1 of {compactable_count}"
    )
    mode_text = "expanded" if expanded else "compact"
    status = (
        f"Panel: {label} | {block_text} | {mode_text} | "
        "Ctrl+Left/Right blocks | Ctrl+E toggle"
    )
    return status


def _build_pointer_hint_text(
    *,
    surface_id: str | None,
    hovered_position: int | None,
    compactable_count: int,
) -> str:
    if surface_id is None or hovered_position is None or compactable_count <= 0:
        return ""
    label = _surface_label(surface_id)
    return (
        f"Pointer: {label} hover on block {hovered_position} of {compactable_count}. "
        "Click selects it, wheel keeps selection aligned with the visible viewport."
    )


def _build_view_title_text(view_name: str) -> str:
    return VIEW_TITLES.get(view_name, "")


def _build_profile_editor_hint(active_profile: Any) -> str:
    if active_profile is None:
        return "Select an agent to edit agent settings."
    if active_profile.source == "workspace":
        return f"Editing workspace agent '{active_profile.name}'. Save persists tools, skills, prompts, and LLM."
    return f"Agent '{active_profile.name}' is built-in or synthesised. Clone it to a workspace agent to edit."


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
    main_input_placeholder: str
    status_text: str
    footer_hint_text: str
    header_agent_text: str
    header_llm_text: str
    view_title_text: str
    debugger_attached: bool
    debugger_paused: bool
    debugger_breakpoint_count: int
    selected_debugger_breakpoint_id: int | None
    debugger_inline_breakpoint_visible: bool
    debugger_inline_breakpoint_type: str
    debugger_inline_breakpoint_placeholder: str
    debugger_inline_breakpoint_help: str
    debugger_inline_breakpoint_value: str
    inline_prompt_visible: bool
    inline_prompt_resolved: bool
    inline_prompt_kind: str
    inline_prompt_prompt: str
    inline_prompt_help: str
    inline_prompt_placeholder: str
    inline_prompt_submit_label: str
    inline_prompt_text_value: str
    inline_prompt_selected_value: str
    inline_prompt_selected_values: tuple[str, ...]
    inline_prompt_summary_text: str
    inline_prompt_select_options: tuple[tuple[str, str], ...]
    inline_prompt_checklist_options: tuple[tuple[str, str, bool], ...]
    workspace_view_select: SelectViewState
    theme_select: SelectViewState
    profile_select: SelectViewState
    llm_select: SelectViewState
    session_confirm_select: SelectViewState
    auto_confirm_tools: bool
    inspector_summary_blocks: tuple[Any, ...]
    inspector_summary_text: str
    inspector_context_blocks: tuple[Any, ...]
    inspector_context_text: str
    inspector_sessions_blocks: tuple[Any, ...]
    inspector_sessions_text: str
    skill_list_options: tuple[tuple[str, str, bool], ...]
    tool_list_options: tuple[tuple[str, str, bool], ...]
    inspector_prompt_blocks: tuple[Any, ...]
    inspector_prompts_text: str
    profile_list_names: tuple[str, ...]
    profile_list_labels: tuple[str, ...]
    run_preview_blocks: tuple[Any, ...]
    run_preview_text: str


@dataclass(frozen=True)
class PickerOption:
    value: str
    label: str
    description: str = ""
    search_text: str = ""
