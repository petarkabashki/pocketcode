from __future__ import annotations

import asyncio
import io
import logging
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any, Dict, Iterable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Input,
    OptionList,
    Select,
    SelectionList,
    Static,
    Switch,
    TextArea,
)

from pocketcode.cli.command_handler import handle_command, list_command_suggestions
from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import (
    describe_interaction_request,
    interaction_placeholder,
    parse_interaction_response,
)
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunHandle

logger = logging.getLogger(__name__)

AUTO_AGENT = "__auto__"
DEFAULT_PROFILE = "__default__"
NO_LLM = "__none__"
INHERIT_POLICY = "__inherit__"
LOADING_OPTION = "__loading__"
NO_TOOL = "__no_tool__"
MAX_OUTPUT_LINES = 400
VIEW_TITLES = {
    "chat": "Chat Workspace",
    "control": "Control Center",
    "profiles": "Edit Agent",
    "context": "Context Builder",
    "run": "Run Inspector",
}
THEME_OPTIONS = {
    "ocean": "Ocean",
    "forest": "Forest",
    "ember": "Ember",
}
WORKSPACE_MODES = {
    "balanced": {"label": "Balanced", "view": "chat", "left": True, "right": True},
    "chat_focus": {"label": "Chat Focus", "view": "chat", "left": False, "right": True},
    "control_desk": {"label": "Control Desk", "view": "control", "left": True, "right": True},
    "minimal": {"label": "Minimal", "view": "chat", "left": False, "right": False},
    "review": {"label": "Review", "view": "run", "left": True, "right": True},
}


def _build_stats_text(status: Dict[str, Any]) -> str:
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    llm_usage = run_summary.get("llm_usage", {}) if isinstance(run_summary, dict) else {}
    cost = run_summary.get("llm_cost_usd", 0.0) if isinstance(run_summary, dict) else 0.0
    session_confirm = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or "inherit"
    return (
        f"Tokens in={llm_usage.get('prompt_tokens', 0)} "
        f"out={llm_usage.get('completion_tokens', 0)} total={llm_usage.get('total_tokens', 0)} | "
        f"Cost=${float(cost):.6f} | Session confirm={session_confirm}"
    )


def _build_status_text(status: Dict[str, Any], current_view: str) -> str:
    runtime_flow = status.get("runtime_workflow") or "internal-flow"
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    flow_display = str(status.get("selected_flow") or status.get("flow") or "auto")

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
    active_agent = status.get("active_agent") or status.get("active_agent_profile") or "none"
    return (
        f"Runtime flow: {runtime_flow} | Flow: {flow_display} | "
        f"Agent: {active_agent} | LLM: {current_llm_profile} ({current_llm_model}) | "
        f"View: {VIEW_TITLES.get(current_view, current_view)}"
    )


def _build_view_title_text(view_name: str) -> str:
    return (
        f"{VIEW_TITLES.get(view_name, view_name)} | "
        "Runtime controls live in Control. Agent edits live in Edit Agent."
    )


def _build_profile_editor_hint(active_profile: Any) -> str:
    if active_profile is None:
        return "Select a flow or agent to edit agent settings."
    if active_profile.source == "workspace":
        return f"Editing workspace agent '{active_profile.name}'. Save persists tools, prompts, and LLM."
    return f"Agent '{active_profile.name}' is plugin/synthesised. Clone it to a workspace agent to edit."


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


def _cycle_value(values: list[Any], current: Any, step: int, *, missing_index: int) -> Any:
    if not values:
        raise ValueError("Cannot cycle an empty value list.")
    try:
        idx = values.index(current)
    except ValueError:
        idx = missing_index
    return values[(idx + step) % len(values)]


@dataclass(frozen=True)
class SelectViewState:
    options: tuple[tuple[str, str], ...]
    value: str


@dataclass(frozen=True)
class TextualUIState:
    theme_name: str
    current_view: str
    left_panel_visible: bool
    right_panel_visible: bool
    header_details_visible: bool
    header_toggle_label: str
    status_text: str
    stats_text: str
    view_title_text: str
    workspace_mode_select: SelectViewState
    theme_select: SelectViewState
    agent_select: SelectViewState
    profile_select: SelectViewState
    llm_select: SelectViewState
    session_confirm_select: SelectViewState
    auto_confirm_tools: bool
    profile_editor_hint: str
    clone_disabled: bool
    profile_llm_select: SelectViewState
    profile_confirm_select: SelectViewState
    profile_allow_all_tools: bool
    profile_allow_all_tools_disabled: bool
    profile_tool_options: tuple[tuple[str, str, bool], ...]
    profile_tool_list_disabled: bool
    profile_policy_tool_select: SelectViewState
    profile_policy_value_select: SelectViewState
    profile_policy_summary_text: str
    profile_prompts_text: str
    profile_prompts_disabled: bool
    save_profile_disabled: bool
    inspector_summary_text: str
    inspector_context_text: str
    inspector_tools_text: str
    inspector_prompts_text: str
    profile_list_names: tuple[str, ...]
    profile_list_labels: tuple[str, ...]
    context_preview_text: str
    run_preview_text: str


class PocketCodeTextualApp(App[None]):
    BINDINGS = [
        Binding("tab", "complete_input", "Complete Input", priority=True),
        Binding("f1", "view_chat", "Chat", priority=True),
        Binding("f2", "view_control", "Control", priority=True),
        Binding("f3", "view_profiles", "Edit Agent", priority=True),
        Binding("f4", "view_context", "Context", priority=True),
        Binding("f5", "view_run", "Run", priority=True),
        Binding("f7", "next_profile", "Next Agent Profile", priority=True),
        Binding("shift+f7", "prev_profile", "Prev Agent Profile", priority=True),
        Binding("f8", "next_llm", "Next LLM", priority=True),
        Binding("shift+f8", "prev_llm", "Prev LLM", priority=True),
        Binding("f9", "toggle_left_panel", "Toggle Nav"),
        Binding("f10", "toggle_right_panel", "Toggle Inspector"),
        Binding("f11", "toggle_header", "Toggle Header"),
        Binding("ctrl+p", "next_profile", "Next Agent Profile", priority=True),
        Binding("ctrl+shift+p", "prev_profile", "Prev Agent Profile", priority=True),
        Binding("ctrl+w", "next_workspace_mode", "Next Mode"),
        Binding("alt+1", "view_chat", "Chat"),
        Binding("alt+2", "view_control", "Control"),
        Binding("alt+3", "view_profiles", "Edit Agent"),
        Binding("alt+4", "view_context", "Context"),
        Binding("alt+5", "view_run", "Run"),
        Binding("ctrl+shift+a", "copy_output", "Copy Output"),
        Binding("ctrl+y", "copy_last_response", "Copy Last"),
        Binding("ctrl+r", "reload_runtime", "Reload"),
        Binding("ctrl+l", "clear_output", "Clear Output"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: #0f172a;
        color: #e2e8f0;
    }

    Screen.theme-ocean {
        background: #0f172a;
        color: #e2e8f0;
    }

    Screen.theme-ocean #topbar {
        background: #082f49;
        border-bottom: solid #0ea5e9;
    }

    Screen.theme-ocean Footer {
        background: #111827;
        color: #dbeafe;
    }

    Screen.theme-ocean #status {
        background: #0b4f6c;
        color: #f8fafc;
    }

    Screen.theme-ocean #stats {
        background: #1f2937;
        color: #d1fae5;
    }

    Screen.theme-ocean .sidebar,
    Screen.theme-ocean .view {
        background: #111827;
        border: round #334155;
    }

    Screen.theme-ocean #view-title {
        background: #082f49;
        color: #e0f2fe;
        border: round #0ea5e9;
    }

    Screen.theme-ocean .card,
    Screen.theme-ocean #output,
    Screen.theme-ocean #profile-list,
    Screen.theme-ocean #profile-tool-list,
    Screen.theme-ocean #profile-prompts,
    Screen.theme-ocean #context-preview,
    Screen.theme-ocean #run-preview,
    Screen.theme-ocean #inspector-tools,
    Screen.theme-ocean #inspector-prompts {
        background: #020617;
        border: round #334155;
        color: #e2e8f0;
    }

    Screen.theme-ocean #main-input {
        border: round #f59e0b;
    }

    Screen.theme-forest {
        background: #0b1510;
        color: #ecfccb;
    }

    Screen.theme-forest #topbar {
        background: #16351f;
        border-bottom: solid #65a30d;
    }

    Screen.theme-forest Footer {
        background: #14532d;
        color: #dcfce7;
    }

    Screen.theme-forest #status {
        background: #14532d;
        color: #f0fdf4;
    }

    Screen.theme-forest #stats {
        background: #1f2937;
        color: #d9f99d;
    }

    Screen.theme-forest .sidebar,
    Screen.theme-forest .view {
        background: #102018;
        border: round #365314;
    }

    Screen.theme-forest #view-title {
        background: #16351f;
        color: #dcfce7;
        border: round #65a30d;
    }

    Screen.theme-forest .card,
    Screen.theme-forest #output,
    Screen.theme-forest #profile-list,
    Screen.theme-forest #profile-tool-list,
    Screen.theme-forest #profile-prompts,
    Screen.theme-forest #context-preview,
    Screen.theme-forest #run-preview,
    Screen.theme-forest #inspector-tools,
    Screen.theme-forest #inspector-prompts {
        background: #09110d;
        border: round #365314;
        color: #ecfccb;
    }

    Screen.theme-forest #main-input {
        border: round #84cc16;
    }

    Screen.theme-ember {
        background: #1a120c;
        color: #ffedd5;
    }

    Screen.theme-ember #topbar {
        background: #3b1d10;
        border-bottom: solid #fb923c;
    }

    Screen.theme-ember Footer {
        background: #7c2d12;
        color: #ffedd5;
    }

    Screen.theme-ember #status {
        background: #9a3412;
        color: #fff7ed;
    }

    Screen.theme-ember #stats {
        background: #3f1d0f;
        color: #fed7aa;
    }

    Screen.theme-ember .sidebar,
    Screen.theme-ember .view {
        background: #22140d;
        border: round #9a3412;
    }

    Screen.theme-ember #view-title {
        background: #3b1d10;
        color: #ffedd5;
        border: round #fb923c;
    }

    Screen.theme-ember .card,
    Screen.theme-ember #output,
    Screen.theme-ember #profile-list,
    Screen.theme-ember #profile-tool-list,
    Screen.theme-ember #profile-prompts,
    Screen.theme-ember #context-preview,
    Screen.theme-ember #run-preview,
    Screen.theme-ember #inspector-tools,
    Screen.theme-ember #inspector-prompts {
        background: #120b07;
        border: round #9a3412;
        color: #ffedd5;
    }

    Screen.theme-ember #main-input {
        border: round #fb923c;
    }

    Footer {
        height: 1;
        padding: 0 1;
        background: #111827;
        color: #dbeafe;
    }

    #topbar {
        height: auto;
        padding: 0 1;
        background: #082f49;
        border-bottom: solid #0ea5e9;
    }

    #topbar-main {
        height: 1;
        padding: 0;
        content-align: left middle;
    }

    #status {
        width: 1fr;
        height: 1;
        padding: 0;
        color: #f8fafc;
        content-align: left middle;
        text-style: bold;
    }

    #toggle-header-button {
        width: auto;
        min-width: 14;
        margin: 0;
    }

    #header-details {
        height: auto;
        margin-bottom: 0;
    }

    #stats {
        height: 1;
        padding: 0;
        background: #1f2937;
        color: #d1fae5;
        content-align: left middle;
    }

    #workspace {
        height: 1fr;
        padding: 0;
    }

    .sidebar {
        width: 28;
        min-width: 20;
        border: round #334155;
        background: #111827;
        padding: 0;
    }

    #main-column {
        width: 1fr;
        min-width: 60;
        margin: 0;
    }

    #view-title {
        height: 3;
        padding: 0 1;
        margin-bottom: 1;
        border: round #0ea5e9;
        background: #082f49;
        color: #e0f2fe;
        content-align: left middle;
        text-style: bold;
    }

    #view-switcher {
        height: 1fr;
    }

    .view {
        height: 1fr;
        border: round #334155;
        background: #111827;
        padding: 0 1;
    }

    .view-scroll {
        height: 1fr;
    }

    #output {
        height: 1fr;
        border: round #0ea5e9;
        background: #020617;
        color: #e2e8f0;
    }

    #main-input {
        margin-top: 0;
        border: round #f59e0b;
    }

    .panel-title {
        height: auto;
        margin-bottom: 0;
        color: #f8fafc;
        text-style: bold;
    }

    .section-title {
        margin: 0 0 0 0;
        color: #93c5fd;
        text-style: bold;
    }

    .field-label {
        margin-top: 0;
        color: #cbd5e1;
    }

    .hint {
        color: #fcd34d;
        margin-bottom: 0;
    }

    .card {
        border: round #475569;
        background: #0b1220;
        padding: 0;
        margin-bottom: 0;
    }

    .button-row {
        height: auto;
        margin-top: 0;
    }

    Button {
        width: 1fr;
        margin-bottom: 0;
    }

    #shortcut-list {
        color: #cbd5e1;
    }

    #profile-list {
        height: 10;
        margin-bottom: 0;
        border: round #334155;
        background: #020617;
    }

    #profile-tool-list {
        height: 12;
        border: round #334155;
        background: #020617;
    }

    #profile-policy-summary {
        height: 6;
        border: round #334155;
        background: #020617;
        color: #e2e8f0;
    }

    #profile-prompts,
    #context-preview,
    #run-preview,
    #inspector-context,
    #inspector-tools,
    #inspector-prompts {
        height: 10;
        border: round #334155;
        background: #020617;
        color: #e2e8f0;
    }

    #context-preview,
    #run-preview,
    #inspector-context,
    #inspector-tools,
    #inspector-prompts {
        height: 10;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(self, engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
        super().__init__()
        self._engine = engine
        self._cli_context = cli_context
        self._busy = False
        self._active_run: RunHandle | None = None
        self._pending_input_request: dict[str, Any] | None = None
        self._live_run_status = "idle"
        self._live_run_events: list[str] = []
        self._show_header_details = True
        self._show_left_panel = True
        self._show_right_panel = True
        self._current_view = "chat"
        self._theme_name = "ocean"
        self._workspace_mode = "balanced"
        self._output_lines: list[str] = []
        self._trimmed_output_line_count = 0
        self._last_assistant_response: str = ""
        self._suggestions: list[str] = []
        self._profile_list_names: list[str] = []
        self._syncing_controls = False
        self._select_state_cache: dict[str, tuple[tuple[tuple[str, str], ...], str]] = {}
        self._text_state_cache: dict[str, str] = {}
        self._option_list_state_cache: dict[str, tuple[str, ...]] = {}
        self._selection_list_state_cache: dict[str, tuple[tuple[str, str, bool], ...]] = {}
        self._draft_profile_name: str | None = None
        self._draft_profile_tool_overrides: dict[str, str] = {}
        self._selected_profile_policy_tool: str | None = None
        self._ui_state: TextualUIState | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="topbar"):
            with Horizontal(id="topbar-main"):
                yield Static(id="status")
                yield Button("Hide Details", id="toggle-header-button")
            with Vertical(id="header-details"):
                yield Static(id="stats")
        with Horizontal(id="workspace"):
            with VerticalScroll(id="left-panel", classes="sidebar"):
                yield Static("Workspace Views", classes="panel-title")
                yield Button("Chat", id="view-chat-button", variant="primary")
                yield Button("Control", id="view-control-button")
                yield Button("Edit Agent", id="view-profiles-button")
                yield Button("Context", id="view-context-button")
                yield Button("Run", id="view-run-button")
                yield Static("Shortcuts", classes="section-title")
                yield Static(
                    "F1..F5 switch views\n"
                    "F7/F8 next agent profile/LLM\n"
                    "Shift+F7/F8 previous agent profile/LLM\n"
                    "F9/F10 toggle panels\n"
                    "F11 toggle second header row\n"
                    "Ctrl+W cycle mode\n"
                    "Alt+1..5 switch views\n"
                    "Ctrl+R reload runtime",
                    id="shortcut-list",
                    classes="card",
                )
            with Vertical(id="main-column"):
                yield Static(id="view-title")
                with ContentSwitcher(initial="view-chat", id="view-switcher"):
                    with Vertical(id="view-chat", classes="view"):
                        yield TextArea("", id="output", read_only=True)
                    with VerticalScroll(id="view-control", classes="view view-scroll"):
                        yield Static("Runtime controls apply immediately.", classes="hint")
                        yield Static("Workspace Mode", classes="field-label")
                        yield Select(
                            [(item["label"], key) for key, item in WORKSPACE_MODES.items()],
                            id="workspace-mode-select",
                            allow_blank=False,
                            value=self._workspace_mode,
                        )
                        yield Static("Theme Preset", classes="field-label")
                        yield Select(
                            [(label, key) for key, label in THEME_OPTIONS.items()],
                            id="theme-select",
                            allow_blank=False,
                            value=self._theme_name,
                        )
                        yield Static("Active Agent", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="agent-select", allow_blank=False)
                        yield Static("Active Agent Profile", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="profile-select", allow_blank=False)
                        yield Static("Global LLM Override", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="llm-select", allow_blank=False)
                        yield Static("Session Confirmation Default", classes="field-label")
                        yield Select(
                            [
                                ("inherit", INHERIT_POLICY),
                                ("allow", "allow"),
                                ("confirm", "confirm"),
                                ("deny", "deny"),
                            ],
                            id="session-confirm-select",
                            allow_blank=False,
                        )
                        yield Static("Auto-Confirm Tools", classes="field-label")
                        yield Switch(value=False, id="auto-confirm-switch")
                        with Horizontal(classes="button-row"):
                            yield Button("Reload Runtime", id="reload-button", variant="primary")
                            yield Button("Open Edit Agent", id="goto-profiles-button")
                            yield Button("Open Run Inspector", id="goto-run-button")
                    with VerticalScroll(id="view-profiles", classes="view view-scroll"):
                        yield Static("Active agent settings save back to workspace YAML.", classes="hint")
                        yield Static("", id="profile-editor-hint", classes="hint")
                        yield Static("Clone Active Agent To Workspace", classes="field-label")
                        yield Input(id="clone-profile-name", placeholder="my-agent-safe")
                        yield Button("Clone Active Agent", id="clone-profile-button", variant="primary")
                        yield Static("Agent LLM", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="profile-llm-select", allow_blank=False)
                        yield Static("Agent Confirmation Default", classes="field-label")
                        yield Select(
                            [
                                ("inherit", INHERIT_POLICY),
                                ("allow", "allow"),
                                ("confirm", "confirm"),
                                ("deny", "deny"),
                            ],
                            id="profile-confirm-select",
                            allow_blank=False,
                        )
                        yield Static("Allow All Agent Tools", classes="field-label")
                        yield Switch(value=True, id="profile-all-tools-switch")
                        yield Static("Allowed Tools", classes="field-label")
                        yield SelectionList(id="profile-tool-list")
                        yield Static("Tool Policy Target", classes="field-label")
                        yield Select([("(no tools)", NO_TOOL)], id="profile-policy-tool-select", allow_blank=False)
                        yield Static("Selected Tool Policy Override", classes="field-label")
                        yield Select(
                            [
                                ("inherit", INHERIT_POLICY),
                                ("allow", "allow"),
                                ("confirm", "confirm"),
                                ("deny", "deny"),
                            ],
                            id="profile-tool-policy-select",
                            allow_blank=False,
                        )
                        yield Static("Tool Policy Overrides", classes="field-label")
                        yield TextArea("", id="profile-policy-summary", read_only=True)
                        yield Static("Extra Prompt Paths (one path per line)", classes="field-label")
                        yield TextArea("", id="profile-prompts")
                        yield Button("Save Agent", id="save-profile-button", variant="success")
                    with VerticalScroll(id="view-context", classes="view view-scroll"):
                        yield Static("Context controls update the next request scope.", classes="hint")
                        yield Static("Context Type", classes="field-label")
                        yield Select(
                            [
                                ("file", "file"),
                                ("folder", "folder"),
                                ("url", "url"),
                                ("snippet", "snippet"),
                            ],
                            id="context-type-select",
                            allow_blank=False,
                            value="file",
                        )
                        yield Static("Context Name (snippet only)", classes="field-label")
                        yield Input(id="context-name-input", placeholder="snippet-name")
                        yield Static("Context Value", classes="field-label")
                        yield Input(id="context-value-input", placeholder="/path/to/file or https://example.com")
                        with Horizontal(classes="button-row"):
                            yield Button("Add", id="context-add-button", variant="primary")
                            yield Button("Remove", id="context-remove-button", variant="warning")
                            yield Button("Clear Type", id="context-clear-type-button")
                            yield Button("Clear All", id="context-clear-all-button", variant="error")
                        yield Static("Current Context", classes="section-title")
                        yield TextArea("", id="context-preview", read_only=True)
                    with VerticalScroll(id="view-run", classes="view view-scroll"):
                        yield Static("Last run summary and effective runtime state.", classes="hint")
                        yield TextArea("", id="run-preview", read_only=True)
                yield Input(
                    id="main-input",
                    placeholder=(
                        "Type a request or /command. F1..F5=view F7/F8 next agent profile/LLM "
                        "F9/F10=panels F11=header"
                    ),
                )
            with VerticalScroll(id="right-panel", classes="sidebar"):
                yield Static("Inspector", classes="panel-title")
                yield Static("", id="inspector-summary", classes="card")
                yield Static("Session Context", classes="section-title")
                yield TextArea("", id="inspector-context", read_only=True)
                yield Static("Agents For Active Flow", classes="section-title")
                yield OptionList(id="profile-list")
                yield Static("Active Tools", classes="section-title")
                yield TextArea("", id="inspector-tools", read_only=True)
                yield Static("Prompt Sources", classes="section-title")
                yield TextArea("", id="inspector-prompts", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_suggestions()
        self._refresh_ui()
        self.set_interval(0.1, self._drain_run_events)
        self._write_info(
            "Pocketcode workspace ready. F1..F5 switch views, F7/F8 move forward through agent profile-LLM, Shift+F7/F8 move backward, and F11 toggles the second header row."
        )
        self.query_one("#main-input", Input).focus()

    def _refresh_suggestions(self) -> None:
        words = list_command_suggestions(self._engine)
        self._suggestions = words
        self.query_one("#main-input", Input).suggester = SuggestFromList(words, case_sensitive=False)

    def _ensure_profile_policy_draft(self, active_profile: Any) -> dict[str, str]:
        profile_name = active_profile.name if active_profile else None
        if profile_name != self._draft_profile_name:
            overrides: dict[str, str] = {}
            if active_profile and isinstance(active_profile.tool_confirmation, dict):
                raw_overrides = active_profile.tool_confirmation.get("overrides", {})
                if isinstance(raw_overrides, dict):
                    overrides = {
                        str(tool_name): str(policy)
                        for tool_name, policy in raw_overrides.items()
                        if policy is not None
                    }
            self._draft_profile_name = profile_name
            self._draft_profile_tool_overrides = overrides
            self._selected_profile_policy_tool = None
        return dict(self._draft_profile_tool_overrides)

    def _resolve_profile_policy_tool(self, tool_names: tuple[str, ...]) -> str:
        if self._selected_profile_policy_tool in tool_names:
            return str(self._selected_profile_policy_tool)
        self._selected_profile_policy_tool = tool_names[0] if tool_names else None
        return self._selected_profile_policy_tool or NO_TOOL

    def _render_profile_policy_summary(self, overrides: dict[str, str]) -> str:
        if not overrides:
            return "No per-tool confirmation overrides. Tools inherit the agent default."
        lines = ["Per-tool confirmation overrides:"]
        for tool_name in sorted(overrides):
            lines.append(f"- {tool_name}: {overrides[tool_name]}")
        return "\n".join(lines)

    def _build_ui_state(self) -> TextualUIState:
        status = self._engine.status()
        current_agent = self._engine.get_current_agent()
        active_profile = self._engine.active_agent_profile
        current_agent_profiles = tuple(self._engine.list_agent_profiles(current_agent)) if current_agent else ()
        current_agent_tools = tuple(self._engine.list_tools_for_agent(current_agent)) if current_agent else ()
        prompt_sources = tuple(self._engine.get_agent_prompt_sources(current_agent)) if current_agent else ()
        active_profile_name = active_profile.name if active_profile else None
        target_agent = active_profile.agent if active_profile is not None else current_agent
        if target_agent == current_agent:
            target_agent_tools = current_agent_tools
        else:
            target_agent_tools = tuple(self._engine.list_tools_for_agent(target_agent)) if target_agent else ()

        llm_profile_names = tuple(str(name) for name in status.get("available_llm_profiles", []))
        available_agents = tuple(str(agent) for agent in status.get("available_flows", status.get("available_agents", [])))
        session_default = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or INHERIT_POLICY
        profile_default = (
            active_profile.tool_confirmation.get("default")
            if active_profile and isinstance(active_profile.tool_confirmation, dict)
            else None
        )
        editable = bool(active_profile and active_profile.source == "workspace")
        profile_allow_all_tools = active_profile.tools is None if active_profile else True
        allowed_tools = set(active_profile.tools) if active_profile and active_profile.tools is not None else set(target_agent_tools)
        profile_tool_options = tuple(
            (tool_name, tool_name, tool_name in allowed_tools) for tool_name in target_agent_tools
        )
        profile_tool_overrides = self._ensure_profile_policy_draft(active_profile)
        selected_policy_tool = self._resolve_profile_policy_tool(target_agent_tools)
        selected_policy_value = (
            profile_tool_overrides.get(selected_policy_tool, INHERIT_POLICY)
            if selected_policy_tool != NO_TOOL
            else INHERIT_POLICY
        )
        selected_profile = (
            active_profile.name
            if active_profile is not None and active_profile.agent == current_agent
            else DEFAULT_PROFILE
        )
        summary_lines = [
            f"Flow: {current_agent or 'auto'}",
            f"Agent: {active_profile_name or 'none'}",
            f"Agent source: {active_profile.source if active_profile else '-'}",
            f"Global LLM: {self._engine.global_llm_override or 'inherit'}",
            f"Auto-confirm: {'on' if self._engine.auto_confirm_tools else 'off'}",
            f"Session confirm: {session_default}",
        ]
        if active_profile and active_profile.description:
            summary_lines.append(f"Agent note: {active_profile.description}")

        profile_list_labels = tuple(
            f"{'* ' if active_profile_name == profile_name else '  '}{profile_name}"
            for profile_name in current_agent_profiles
        ) or ("No agents for the active flow",)

        effective_llm_profile = (
            active_profile.llm_profile
            if active_profile is not None and active_profile.llm_profile
            else self._engine.global_llm_override or status.get("default_llm_profile") or "none"
        )
        status_for_display = dict(status)
        status_for_display["selected_flow"] = target_agent or current_agent or "auto"
        status_for_display["selected_llm_profile"] = effective_llm_profile

        return TextualUIState(
            theme_name=self._theme_name,
            current_view=self._current_view,
            left_panel_visible=self._show_left_panel,
            right_panel_visible=self._show_right_panel,
            header_details_visible=self._show_header_details,
            header_toggle_label="Hide Details" if self._show_header_details else "Show Details",
            status_text=_build_status_text(status_for_display, self._current_view),
            stats_text=_build_stats_text(status),
            view_title_text=_build_view_title_text(self._current_view),
            workspace_mode_select=SelectViewState(
                options=tuple((item["label"], key) for key, item in WORKSPACE_MODES.items()),
                value=self._workspace_mode,
            ),
            theme_select=SelectViewState(
                options=tuple((label, key) for key, label in THEME_OPTIONS.items()),
                value=self._theme_name,
            ),
            agent_select=SelectViewState(
                options=(("auto", AUTO_AGENT),) + tuple((agent, agent) for agent in available_agents),
                value=current_agent or AUTO_AGENT,
            ),
            profile_select=SelectViewState(
                options=(("(default for agent)", DEFAULT_PROFILE),)
                + tuple((profile_name, profile_name) for profile_name in current_agent_profiles),
                value=selected_profile,
            ),
            llm_select=SelectViewState(
                options=(("(inherit)", NO_LLM),) + tuple((name, name) for name in llm_profile_names),
                value=self._engine.global_llm_override or NO_LLM,
            ),
            session_confirm_select=SelectViewState(
                options=(
                    ("inherit", INHERIT_POLICY),
                    ("allow", "allow"),
                    ("confirm", "confirm"),
                    ("deny", "deny"),
                ),
                value=session_default,
            ),
            auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            profile_editor_hint=_build_profile_editor_hint(active_profile),
            clone_disabled=active_profile is None,
            profile_llm_select=SelectViewState(
                options=(("(inherit)", NO_LLM),) + tuple((name, name) for name in llm_profile_names),
                value=active_profile.llm_profile if active_profile and active_profile.llm_profile else NO_LLM,
            ),
            profile_confirm_select=SelectViewState(
                options=(
                    ("inherit", INHERIT_POLICY),
                    ("allow", "allow"),
                    ("confirm", "confirm"),
                    ("deny", "deny"),
                ),
                value=profile_default or INHERIT_POLICY,
            ),
            profile_allow_all_tools=profile_allow_all_tools,
            profile_allow_all_tools_disabled=not editable,
            profile_tool_options=profile_tool_options,
            profile_tool_list_disabled=not editable or profile_allow_all_tools,
            profile_policy_tool_select=SelectViewState(
                options=tuple((tool_name, tool_name) for tool_name in target_agent_tools) or (("(no tools)", NO_TOOL),),
                value=selected_policy_tool,
            ),
            profile_policy_value_select=SelectViewState(
                options=(
                    ("inherit", INHERIT_POLICY),
                    ("allow", "allow"),
                    ("confirm", "confirm"),
                    ("deny", "deny"),
                ),
                value=selected_policy_value,
            ),
            profile_policy_summary_text=self._render_profile_policy_summary(profile_tool_overrides),
            profile_prompts_text="\n".join(active_profile.extra_prompts) if active_profile else "",
            profile_prompts_disabled=not editable,
            save_profile_disabled=not editable,
            inspector_summary_text="\n".join(summary_lines),
            inspector_context_text=self._render_context_summary(status),
            inspector_tools_text=self._render_tool_summary(current_agent, active_profile, list(current_agent_tools)),
            inspector_prompts_text=self._render_prompt_summary({"prompt_sources": list(prompt_sources)}, active_profile),
            profile_list_names=current_agent_profiles,
            profile_list_labels=profile_list_labels,
            context_preview_text=self._render_context_preview(),
            run_preview_text=self._render_run_preview(status),
        )

    def _apply_theme_name(self, theme_name: str) -> None:
        for class_name in [f"theme-{name}" for name in THEME_OPTIONS]:
            self.screen.remove_class(class_name)
        self.screen.add_class(f"theme-{theme_name}")

    def _apply_panel_visibility(self, *, left_visible: bool, right_visible: bool) -> None:
        self.query_one("#left-panel", VerticalScroll).display = left_visible
        self.query_one("#right-panel", VerticalScroll).display = right_visible

    def _apply_view_state(self, view_name: str, view_title_text: str) -> None:
        self.query_one("#view-switcher", ContentSwitcher).current = f"view-{view_name}"
        self._set_static_text(self.query_one("#view-title", Static), view_title_text)
        for button_id, target_view in {
            "#view-chat-button": "chat",
            "#view-control-button": "control",
            "#view-profiles-button": "profiles",
            "#view-context-button": "context",
            "#view-run-button": "run",
        }.items():
            button = self.query_one(button_id, Button)
            button.variant = "primary" if target_view == view_name else "default"

    def _apply_ui_state(self, state: TextualUIState) -> None:
        previous = self._ui_state
        if previous is None or previous.theme_name != state.theme_name:
            self._apply_theme_name(state.theme_name)
        if (
            previous is None
            or previous.left_panel_visible != state.left_panel_visible
            or previous.right_panel_visible != state.right_panel_visible
        ):
            self._apply_panel_visibility(
                left_visible=state.left_panel_visible,
                right_visible=state.right_panel_visible,
            )
        if (
            previous is None
            or previous.current_view != state.current_view
            or previous.view_title_text != state.view_title_text
        ):
            self._apply_view_state(state.current_view, state.view_title_text)

        self.query_one("#header-details", Vertical).display = state.header_details_visible
        self.query_one("#toggle-header-button", Button).label = state.header_toggle_label
        self._set_static_text(self.query_one("#status", Static), state.status_text)
        self._set_static_text(self.query_one("#stats", Static), state.stats_text)

        self._syncing_controls = True
        try:
            self._set_select_options(
                self.query_one("#workspace-mode-select", Select),
                state.workspace_mode_select.options,
                state.workspace_mode_select.value,
            )
            self._set_select_options(
                self.query_one("#theme-select", Select),
                state.theme_select.options,
                state.theme_select.value,
            )
            self._set_select_options(
                self.query_one("#agent-select", Select),
                state.agent_select.options,
                state.agent_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-select", Select),
                state.profile_select.options,
                state.profile_select.value,
            )
            self._set_select_options(
                self.query_one("#llm-select", Select),
                state.llm_select.options,
                state.llm_select.value,
            )
            self._set_select_options(
                self.query_one("#session-confirm-select", Select),
                state.session_confirm_select.options,
                state.session_confirm_select.value,
            )
            self.query_one("#auto-confirm-switch", Switch).value = state.auto_confirm_tools
            self._set_select_options(
                self.query_one("#profile-llm-select", Select),
                state.profile_llm_select.options,
                state.profile_llm_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-confirm-select", Select),
                state.profile_confirm_select.options,
                state.profile_confirm_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-policy-tool-select", Select),
                state.profile_policy_tool_select.options,
                state.profile_policy_tool_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-tool-policy-select", Select),
                state.profile_policy_value_select.options,
                state.profile_policy_value_select.value,
            )
            profile_all_tools = self.query_one("#profile-all-tools-switch", Switch)
            profile_all_tools.value = state.profile_allow_all_tools
        finally:
            self._syncing_controls = False

        self._set_static_text(self.query_one("#profile-editor-hint", Static), state.profile_editor_hint)
        self.query_one("#clone-profile-name", Input).disabled = state.clone_disabled
        self.query_one("#clone-profile-button", Button).disabled = state.clone_disabled
        self.query_one("#profile-llm-select", Select).disabled = state.save_profile_disabled
        self.query_one("#profile-confirm-select", Select).disabled = state.save_profile_disabled
        self.query_one("#profile-all-tools-switch", Switch).disabled = state.profile_allow_all_tools_disabled
        self._set_selection_list_options(
            self.query_one("#profile-tool-list", SelectionList),
            state.profile_tool_options,
        )
        self.query_one("#profile-tool-list", SelectionList).disabled = state.profile_tool_list_disabled
        self.query_one("#profile-policy-tool-select", Select).disabled = state.save_profile_disabled
        self.query_one("#profile-tool-policy-select", Select).disabled = (
            state.save_profile_disabled or state.profile_policy_tool_select.value == NO_TOOL
        )
        self._set_text_area_text(
            self.query_one("#profile-policy-summary", TextArea),
            state.profile_policy_summary_text,
        )
        self._set_text_area_text(self.query_one("#profile-prompts", TextArea), state.profile_prompts_text)
        self.query_one("#profile-prompts", TextArea).disabled = state.profile_prompts_disabled
        self.query_one("#save-profile-button", Button).disabled = state.save_profile_disabled

        self._profile_list_names = list(state.profile_list_names)
        self._set_option_list_labels(self.query_one("#profile-list", OptionList), state.profile_list_labels)
        self._set_static_text(self.query_one("#inspector-summary", Static), state.inspector_summary_text)
        self._set_text_area_text(self.query_one("#inspector-context", TextArea), state.inspector_context_text)
        self._set_text_area_text(self.query_one("#inspector-tools", TextArea), state.inspector_tools_text)
        self._set_text_area_text(self.query_one("#inspector-prompts", TextArea), state.inspector_prompts_text)
        self._set_text_area_text(self.query_one("#context-preview", TextArea), state.context_preview_text)
        self._set_text_area_text(self.query_one("#run-preview", TextArea), state.run_preview_text)

        self._ui_state = state

    def _refresh_ui(self) -> None:
        self._apply_ui_state(self._build_ui_state())

    def _write_info(self, text: str) -> None:
        self._append_output_line(f"info> {text}")

    def _write_error(self, text: str) -> None:
        self._append_output_line(f"error> {text}")

    def _write_user(self, text: str) -> None:
        self._append_output_line(f"you> {text}")

    def _write_assistant(self, text: str) -> None:
        self._append_output_line(f"assistant> {text}")
        self._last_assistant_response = text

    def _append_output_line(self, line: str) -> None:
        self._output_lines.append(line)
        output_widget = self.query_one("#output", TextArea)
        trimmed_lines, trimmed_now = _trim_output_lines(self._output_lines, MAX_OUTPUT_LINES)
        if trimmed_now:
            self._trimmed_output_line_count += trimmed_now
            self._output_lines = trimmed_lines
            self._load_text_area_text(
                output_widget,
                _build_output_text(self._output_lines, self._trimmed_output_line_count),
            )
        elif len(self._output_lines) == 1:
            self._load_text_area_text(
                output_widget,
                _build_output_text(self._output_lines, self._trimmed_output_line_count),
            )
        else:
            output_widget.insert(f"\n{line}")
            self._text_state_cache[output_widget.id or ""] = _build_output_text(
                self._output_lines,
                self._trimmed_output_line_count,
            )
        output_widget.scroll_end(animate=False)

    def _apply_workspace_mode(self, mode_name: str, *, announce: bool) -> None:
        config = WORKSPACE_MODES.get(mode_name)
        if config is None:
            return
        self._workspace_mode = mode_name
        self._show_left_panel = bool(config["left"])
        self._show_right_panel = bool(config["right"])
        self._current_view = str(config["view"])
        if announce:
            self._write_info(f"Workspace mode: {config['label']}.")

    def _render_context_preview(self) -> str:
        if not any(self._cli_context.values()):
            return "No context selected."

        lines: list[str] = []
        for label, key in (
            ("Files", "files"),
            ("Folders", "folders"),
            ("URLs", "urls"),
        ):
            values = sorted(self._cli_context.get(key, set()) or set())
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {value}" for value in values)
        snippets = self._cli_context.get("snippets", {})
        if isinstance(snippets, dict) and snippets:
            lines.append("Snippets:")
            for name, content in sorted(snippets.items()):
                lines.append(f"- {name}: {content}")
        return "\n".join(lines)

    def _render_run_preview(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {})
        if not isinstance(run_summary, dict):
            run_summary = {}

        lines = [
            f"live_run_status: {self._live_run_status}",
            f"runtime_workflow: {status.get('runtime_workflow') or 'internal-flow'}",
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
        if self._live_run_events:
            lines.append("live_events:")
            lines.extend(f"- {item}" for item in self._live_run_events[-8:])
        return "\n".join(lines)

    def _render_context_summary(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
        if not isinstance(context_stats, dict):
            context_stats = {}

        lines = [
            f"files: {context_stats.get('files', len(self._cli_context.get('files', set()) or set()))}",
            f"folders: {context_stats.get('folders', len(self._cli_context.get('folders', set()) or set()))}",
            f"urls: {context_stats.get('urls', len(self._cli_context.get('urls', set()) or set()))}",
            f"snippets: {context_stats.get('snippets', len(self._cli_context.get('snippets', {}) or {}))}",
            f"snippet_chars: {context_stats.get('snippet_chars', 0)}",
            "",
            self._render_context_preview(),
        ]
        return "\n".join(lines)

    def _render_tool_summary(
        self,
        agent_name: str | None,
        active_profile: Any,
        tool_names: list[str] | None = None,
    ) -> str:
        if not agent_name:
            return "No agent selected."
        if tool_names is None:
            tool_names = self._engine.list_tools_for_agent(agent_name)
        if not tool_names:
            return "No tools available."
        allowed = set(active_profile.tools) if active_profile and active_profile.tools is not None else None
        lines: list[str] = []
        if allowed is None:
            lines.append("Tool scope: unrestricted")
        else:
            lines.append("Tool scope: profile allowlist")
        for tool_name in tool_names:
            marker = "[x]" if allowed is None or tool_name in allowed else "[ ]"
            lines.append(f"{marker} {tool_name}")
        return "\n".join(lines)

    def _render_prompt_summary(self, agent_meta: Dict[str, Any], active_profile: Any) -> str:
        agent_prompts = agent_meta.get("prompt_sources", []) if isinstance(agent_meta, dict) else []
        extra_prompts = list(active_profile.extra_prompts) if active_profile else []
        lines: list[str] = []
        if agent_prompts:
            lines.append("Agent prompt sources:")
            lines.extend(f"- {path}" for path in agent_prompts)
        if extra_prompts:
            lines.append("Profile extra prompts:")
            lines.extend(f"- {path}" for path in extra_prompts)
        if not lines:
            return "No prompt sources registered."
        return "\n".join(lines)

    def _set_select_options(
        self,
        widget: Select,
        options: Iterable[tuple[str, str]],
        value: str,
    ) -> None:
        option_list = [(str(label), str(option_value)) for label, option_value in options]
        cache_key = widget.id or ""
        option_tuple = tuple(option_list)
        if self._select_state_cache.get(cache_key) == (option_tuple, value):
            return
        widget.set_options(option_list)
        try:
            widget.value = value
        except Exception:
            if option_list:
                widget.value = option_list[0][1]
                value = option_list[0][1]
        self._select_state_cache[cache_key] = (option_tuple, value)

    def _set_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.text = text
        self._text_state_cache[cache_key] = text

    def _load_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.load_text(text)
        self._text_state_cache[cache_key] = text

    def _set_static_text(self, widget: Static, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.update(text)
        self._text_state_cache[cache_key] = text

    def _set_option_list_labels(self, widget: OptionList, labels: Iterable[str]) -> None:
        option_tuple = tuple(str(label) for label in labels)
        cache_key = widget.id or ""
        if self._option_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        self._option_list_state_cache[cache_key] = option_tuple

    def _set_selection_list_options(
        self,
        widget: SelectionList,
        options: Iterable[tuple[str, str, bool]],
    ) -> None:
        option_tuple = tuple((str(label), str(value), bool(selected)) for label, value, selected in options)
        cache_key = widget.id or ""
        if self._selection_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        self._selection_list_state_cache[cache_key] = option_tuple

    def _sync_ui_from_engine(self) -> None:
        self._refresh_ui()

    def _set_main_input_placeholder(self, prompt: str | None = None) -> None:
        input_widget = self.query_one("#main-input", Input)
        input_widget.placeholder = prompt or (
            "Type a request or /command. F1..F5=view F7/F8 next agent profile/LLM "
            "F9/F10=panels F11=header"
        )

    def _profile_cycle(self) -> list[str]:
        profile_names: list[str] = []
        for agent_name in self._engine.list_agents():
            profile_names.extend(self._engine.list_agent_profiles(agent_name))
        return profile_names

    def _remember_run_event(self, text: str) -> None:
        self._live_run_events.append(text)
        if len(self._live_run_events) > 25:
            self._live_run_events = self._live_run_events[-25:]

    def _drain_run_events(self) -> None:
        if self._active_run is None:
            return
        events = self._active_run.drain_events()
        if not events:
            return
        should_refresh = False
        for event in events:
            should_refresh = self._consume_run_event(event) or should_refresh
        if should_refresh:
            self._refresh_ui()

    def _consume_run_event(self, event: Dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "")
        message = self._format_runtime_event(event)
        if message:
            self._remember_run_event(message)
            self._write_info(message)

        if event_type == "interaction_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(interaction_placeholder(event))
            if event.get("kind") != "text":
                self._write_info(describe_interaction_request(event))
            return True
        if event_type == "interaction_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "user_input_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(str(event.get("prompt") or "Provide input"))
            return True
        if event_type == "user_input_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "run_completed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._write_assistant(str(event.get("output") or ""))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_failed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "failed"
            self._set_main_input_placeholder()
            self._write_error(str(event.get("error") or "Request failed."))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_cancelled":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._sync_ui_from_engine()
            return False
        if event_type in {"run_started", "agent_turn_started", "llm_call_started", "tool_started", "handoff"}:
            self._live_run_status = "running"
        if event_type == "run_cancel_requested":
            self._live_run_status = "stopping"
        return True

    def _format_runtime_event(self, event: Dict[str, Any]) -> str:
        return format_runtime_event(event)

    def _sync_profile_policy_controls(self) -> None:
        selected_tool = str(self.query_one("#profile-policy-tool-select", Select).value)
        selected_policy = (
            self._draft_profile_tool_overrides.get(selected_tool, INHERIT_POLICY)
            if selected_tool != NO_TOOL
            else INHERIT_POLICY
        )
        self._syncing_controls = True
        try:
            self.query_one("#profile-tool-policy-select", Select).value = selected_policy
        finally:
            self._syncing_controls = False
        self.query_one("#profile-tool-policy-select", Select).disabled = (
            self.query_one("#save-profile-button", Button).disabled or selected_tool == NO_TOOL
        )
        self._set_text_area_text(
            self.query_one("#profile-policy-summary", TextArea),
            self._render_profile_policy_summary(self._draft_profile_tool_overrides),
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        widget_id = event.input.id or ""
        if widget_id == "main-input":
            await self._handle_main_input(event.value)
            return
        if widget_id == "clone-profile-name":
            self._clone_active_profile()
            return
        if widget_id == "context-value-input":
            self._add_context_item()

    async def _handle_main_input(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text:
            return

        input_widget = self.query_one("#main-input", Input)
        input_widget.value = ""
        if self._pending_input_request is not None and self._active_run is not None:
            self._write_user(text)
            request_id = str(
                self._pending_input_request.get("request_id")
                or self._pending_input_request.get("prompt_id")
                or ""
            )
            if self._pending_input_request.get("type") == "interaction_requested":
                try:
                    response_payload = parse_interaction_response(self._pending_input_request, text)
                except ValueError as exc:
                    self._write_error(str(exc))
                    self._set_main_input_placeholder(interaction_placeholder(self._pending_input_request))
                    return
                resolved = bool(request_id) and self._active_run.resolve_interaction(request_id, response_payload)
            else:
                resolved = bool(request_id) and self._active_run.resolve_user_input(request_id, text)
            if not resolved:
                self._write_error("The pending prompt is no longer active.")
            self._pending_input_request = None
            self._set_main_input_placeholder()
            return
        normalized_text = text.lower()
        if self._busy and normalized_text not in {"/stop", "/cancel"}:
            self._write_info("A run is already in progress.")
            return

        try:
            if text.startswith("/"):
                self._busy = True
                self._write_user(text)
                if text.lower() == "/copy":
                    self.action_copy_last_response()
                    return
                if text.lower() == "/copy-all":
                    self.action_copy_output()
                    return
                command_output, should_exit = await asyncio.to_thread(self._run_command_capture, text)
                if command_output:
                    self._write_info(command_output)
                if should_exit:
                    self.exit()
                    return
                self._sync_ui_from_engine()
            else:
                self._busy = True
                self._write_user(text)
                self._active_run = self._engine.start_request(
                    text,
                    self._cli_context,
                    bridge_user_input=True,
                )
                self._live_run_status = "running"
                self._refresh_ui()
        except Exception as exc:
            logger.error("Failed to process Textual input: %s", exc, exc_info=True)
            self._write_error(str(exc))
        finally:
            if self._active_run is None:
                self._busy = False
            input_widget.focus()
            if self._active_run is None:
                self._sync_ui_from_engine()

    def _run_command_capture(self, command_input: str) -> tuple[str, bool]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = handle_command(
                command_input=command_input,
                engine=self._engine,
                cli_context=self._cli_context,
                active_run=self._active_run,
            )

        text = output.getvalue().strip()
        should_exit = result == "__exit__"
        return text, should_exit

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "view-chat-button":
            self.action_view_chat()
        elif button_id == "view-control-button":
            self.action_view_control()
        elif button_id == "view-profiles-button":
            self.action_view_profiles()
        elif button_id == "view-context-button":
            self.action_view_context()
        elif button_id == "view-run-button":
            self.action_view_run()
        elif button_id == "toggle-header-button":
            self.action_toggle_header()
        elif button_id == "reload-button":
            self.action_reload_runtime()
        elif button_id == "goto-profiles-button":
            self.action_view_profiles()
        elif button_id == "goto-run-button":
            self.action_view_run()
        elif button_id == "clone-profile-button":
            self._clone_active_profile()
        elif button_id == "save-profile-button":
            self._save_active_profile()
        elif button_id == "context-add-button":
            self._add_context_item()
        elif button_id == "context-remove-button":
            self._remove_context_item()
        elif button_id == "context-clear-type-button":
            self._clear_context(selected_only=True)
        elif button_id == "context-clear-all-button":
            self._clear_context(selected_only=False)

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._syncing_controls:
            return

        if event.select.value != event.value:
            return

        widget_id = event.select.id or ""
        value = str(event.value)
        if value == LOADING_OPTION:
            return
        try:
            if widget_id == "workspace-mode-select":
                self._apply_workspace_mode(value, announce=True)
            elif widget_id == "theme-select":
                self._theme_name = value
                self._write_info(f"Theme preset: {THEME_OPTIONS.get(value, value)}.")
            if widget_id == "agent-select":
                target_agent = None if value == AUTO_AGENT else value
                if target_agent == self._engine.get_current_agent():
                    return
                self._engine.set_agent(target_agent)
                self._write_info(
                    f"Selected agent: {self._engine.get_current_agent() or 'auto'}"
                )
            elif widget_id == "profile-select":
                if value == DEFAULT_PROFILE:
                    current_agent = self._engine.get_current_agent()
                    if current_agent:
                        self._engine.set_agent(current_agent)
                        self._write_info(f"Activated default agent for {current_agent}.")
                else:
                    active_profile = self._engine.active_agent_profile
                    if (
                        active_profile is not None
                        and active_profile.agent == self._engine.get_current_agent()
                        and active_profile.name == value
                    ):
                        return
                    self._engine.set_active_agent_profile(value)
                    self._write_info(f"Activated agent: {value}")
            elif widget_id == "llm-select":
                target_llm = None if value == NO_LLM else value
                if target_llm == self._engine.global_llm_override:
                    return
                self._engine.set_global_llm_override(target_llm)
                self._write_info(
                    f"Global LLM override: {self._engine.global_llm_override or 'inherit'}"
                )
            elif widget_id == "session-confirm-select":
                target_default = None if value == INHERIT_POLICY else value
                current_default = self._engine.session_confirmation_overrides.get("default_policy")
                if target_default == current_default:
                    return
                self._engine.set_session_confirmation_default(target_default)
                self._write_info(
                    f"Session confirmation default: "
                    f"{self._engine.session_confirmation_overrides.get('default_policy') or 'inherit'}"
                )
            elif widget_id == "profile-policy-tool-select":
                target_tool = None if value == NO_TOOL else value
                if target_tool == self._selected_profile_policy_tool:
                    return
                self._selected_profile_policy_tool = target_tool
                self._sync_profile_policy_controls()
                return
            elif widget_id == "profile-tool-policy-select":
                selected_tool = str(self.query_one("#profile-policy-tool-select", Select).value)
                if selected_tool != NO_TOOL:
                    if value == INHERIT_POLICY:
                        self._draft_profile_tool_overrides.pop(selected_tool, None)
                    else:
                        self._draft_profile_tool_overrides[selected_tool] = value
                    self._sync_profile_policy_controls()
                return
            self._sync_ui_from_engine()
        except Exception as exc:
            self._write_error(str(exc))
            self._sync_ui_from_engine()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._syncing_controls:
            return

        switch_id = event.switch.id or ""
        if switch_id == "auto-confirm-switch":
            self._engine.auto_confirm_tools = bool(event.value)
            state = "enabled" if event.value else "disabled"
            self._write_info(f"Auto-confirm tools {state}.")
            self._sync_ui_from_engine()
        elif switch_id == "profile-all-tools-switch":
            editable = bool(
                self._engine.active_agent_profile
                and self._engine.active_agent_profile.source == "workspace"
            )
            selection_list = self.query_one("#profile-tool-list", SelectionList)
            selection_list.disabled = not editable or bool(event.value)

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        if event.selection_list.id != "profile-tool-list":
            return
        if self._syncing_controls:
            return
        option_index = getattr(event, "selection_index", getattr(event, "index", None))
        if option_index is None:
            return
        option = event.selection_list.get_option_at_index(option_index)
        checked = bool(option.value in event.selection_list.selected)
        state = "allowed" if checked else "blocked"
        self._write_info(f"Tool {option.value} marked {state} for the active profile draft.")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "profile-list":
            return
        option_index = getattr(event, "option_index", getattr(event, "index", None))
        if option_index is None or option_index >= len(self._profile_list_names):
            return
        profile_name = self._profile_list_names[option_index]
        try:
            self._engine.set_active_agent_profile(profile_name)
            self._write_info(f"Activated agent: {profile_name}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def _clone_active_profile(self) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent to clone.")
            return

        new_name = self.query_one("#clone-profile-name", Input).value.strip()
        if not new_name:
            self._write_error("Enter a new workspace profile name before cloning.")
            return

        try:
            cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
            cloned = cloner(active_profile.name, new_name)
            self._engine.set_active_agent_profile(new_name)
            self._draft_profile_name = None
            self.query_one("#clone-profile-name", Input).value = ""
            target_path = getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active agent to {target_path}.")
            else:
                self._write_info(f"Cloned active agent to workspace agent '{new_name}'.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._refresh_suggestions()
            self._sync_ui_from_engine()

    def _save_active_profile(self) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent selected.")
            return
        if active_profile.source != "workspace":
            self._write_error(f"Agent '{active_profile.name}' must be cloned to the workspace before saving edits.")
            return

        try:
            tools = None
            if not self.query_one("#profile-all-tools-switch", Switch).value:
                tools = sorted(str(value) for value in self.query_one("#profile-tool-list", SelectionList).selected)
            prompt_lines = [
                line.strip()
                for line in self.query_one("#profile-prompts", TextArea).text.splitlines()
                if line.strip()
            ]
            llm_value = str(self.query_one("#profile-llm-select", Select).value)
            confirm_value = str(self.query_one("#profile-confirm-select", Select).value)
            updater = getattr(self._engine, "update_agent", None) or getattr(self._engine, "update_agent_profile")
            updater(
                active_profile.name,
                llm_profile=None if llm_value == NO_LLM else llm_value,
                tools=tools,
                extra_prompts=prompt_lines,
                tool_confirmation_default=None if confirm_value == INHERIT_POLICY else confirm_value,
                tool_confirmation_overrides=dict(self._draft_profile_tool_overrides),
            )
            self._draft_profile_name = None
            self._write_info(f"Saved workspace agent '{active_profile.name}'.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._refresh_suggestions()
            self._sync_ui_from_engine()

    def _add_context_item(self) -> None:
        context_type = str(self.query_one("#context-type-select", Select).value)
        name = self.query_one("#context-name-input", Input).value.strip()
        value = self.query_one("#context-value-input", Input).value.strip()
        if not value:
            self._write_error("Enter a context value before adding.")
            return

        if context_type == "file":
            self._cli_context["files"].add(value)
        elif context_type == "folder":
            self._cli_context["folders"].add(value)
        elif context_type == "url":
            self._cli_context["urls"].add(value)
        elif context_type == "snippet":
            if not name:
                self._write_error("Snippets require a name.")
                return
            self._cli_context["snippets"][name] = value
        else:
            self._write_error(f"Unsupported context type: {context_type}")
            return

        self.query_one("#context-name-input", Input).value = ""
        self.query_one("#context-value-input", Input).value = ""
        self._write_info(f"Added {context_type} context.")
        self._refresh_ui()

    def _remove_context_item(self) -> None:
        context_type = str(self.query_one("#context-type-select", Select).value)
        name = self.query_one("#context-name-input", Input).value.strip()
        value = self.query_one("#context-value-input", Input).value.strip()
        removed = False

        if context_type == "file" and value:
            removed = value in self._cli_context["files"]
            self._cli_context["files"].discard(value)
        elif context_type == "folder" and value:
            removed = value in self._cli_context["folders"]
            self._cli_context["folders"].discard(value)
        elif context_type == "url" and value:
            removed = value in self._cli_context["urls"]
            self._cli_context["urls"].discard(value)
        elif context_type == "snippet" and name:
            removed = name in self._cli_context["snippets"]
            self._cli_context["snippets"].pop(name, None)
        else:
            self._write_error("Provide the context name/value to remove.")
            return

        message = "Removed" if removed else "No matching"
        self._write_info(f"{message} {context_type} context entry.")
        self._refresh_ui()

    def _clear_context(self, *, selected_only: bool) -> None:
        if selected_only:
            context_type = str(self.query_one("#context-type-select", Select).value)
            if context_type == "file":
                self._cli_context["files"].clear()
            elif context_type == "folder":
                self._cli_context["folders"].clear()
            elif context_type == "url":
                self._cli_context["urls"].clear()
            elif context_type == "snippet":
                self._cli_context["snippets"].clear()
            self._write_info(f"Cleared {context_type} context.")
        else:
            self._cli_context["files"].clear()
            self._cli_context["folders"].clear()
            self._cli_context["urls"].clear()
            self._cli_context["snippets"].clear()
            self._write_info("Cleared all context.")
        self._refresh_ui()

    def action_view_chat(self) -> None:
        self._current_view = "chat"
        self._refresh_ui()

    def action_view_control(self) -> None:
        self._current_view = "control"
        self._refresh_ui()

    def action_view_profiles(self) -> None:
        self._current_view = "profiles"
        self._refresh_ui()

    def action_view_context(self) -> None:
        self._current_view = "context"
        self._refresh_ui()

    def action_view_run(self) -> None:
        self._current_view = "run"
        self._refresh_ui()

    def action_toggle_left_panel(self) -> None:
        self._show_left_panel = not self._show_left_panel
        self._workspace_mode = "balanced"
        self._write_info(f"Navigation panel {'shown' if self._show_left_panel else 'hidden'}.")
        self._refresh_ui()

    def action_toggle_right_panel(self) -> None:
        self._show_right_panel = not self._show_right_panel
        self._workspace_mode = "balanced"
        self._write_info(f"Inspector panel {'shown' if self._show_right_panel else 'hidden'}.")
        self._refresh_ui()

    def action_toggle_header(self) -> None:
        self._show_header_details = not self._show_header_details
        state = "shown" if self._show_header_details else "hidden"
        self._write_info(f"Second header row {state}.")
        self._refresh_ui()

    def action_next_workspace_mode(self) -> None:
        mode_names = list(WORKSPACE_MODES.keys())
        try:
            idx = mode_names.index(self._workspace_mode)
        except ValueError:
            idx = 0
        next_mode = mode_names[(idx + 1) % len(mode_names)]
        self._apply_workspace_mode(next_mode, announce=True)
        self._sync_ui_from_engine()

    def action_next_profile(self) -> None:
        profiles = self._profile_cycle()
        if not profiles:
            self._write_error("No agent profiles are available.")
            return

        current_profile_name = self._engine.active_agent_profile.name if self._engine.active_agent_profile else None
        next_profile = _cycle_value(profiles, current_profile_name, 1, missing_index=-1)

        try:
            self._engine.set_active_agent_profile(next_profile)
            self._write_info(f"Activated agent profile: {next_profile}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_prev_profile(self) -> None:
        profiles = self._profile_cycle()
        if not profiles:
            self._write_error("No agent profiles are available.")
            return

        current_profile_name = self._engine.active_agent_profile.name if self._engine.active_agent_profile else None
        prev_profile = _cycle_value(profiles, current_profile_name, -1, missing_index=0)

        try:
            self._engine.set_active_agent_profile(prev_profile)
            self._write_info(f"Activated agent profile: {prev_profile}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_next_llm(self) -> None:
        try:
            profiles = self._engine.list_llm_profiles()
            if not profiles:
                self._write_error("No LLM profiles are available.")
                return

            current = self._engine.global_llm_override
            cycle = [None] + profiles
            next_value = _cycle_value(cycle, current, 1, missing_index=0)

            self._engine.set_global_llm_override(next_value)
            self._write_info(
                f"Global LLM override: {next_value if next_value is not None else 'inherit'}"
            )
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_prev_llm(self) -> None:
        try:
            profiles = self._engine.list_llm_profiles()
            if not profiles:
                self._write_error("No LLM profiles are available.")
                return

            current = self._engine.global_llm_override
            cycle = [None] + profiles
            prev_value = _cycle_value(cycle, current, -1, missing_index=0)

            self._engine.set_global_llm_override(prev_value)
            self._write_info(
                f"Global LLM override: {prev_value if prev_value is not None else 'inherit'}"
            )
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._refresh_suggestions()
            self._write_info("Reloaded plugins, agents, tools, and LLM mappings.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_clear_output(self) -> None:
        self._output_lines = []
        self._trimmed_output_line_count = 0
        self._load_text_area_text(self.query_one("#output", TextArea), "")
        self._write_info("Cleared output.")

    def action_copy_output(self) -> None:
        if not self._output_lines:
            self._write_error("No output to copy.")
            return
        text = "\n".join(self._output_lines)
        try:
            self.copy_to_clipboard(text)
            self._write_info("Copied full console output to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_copy_last_response(self) -> None:
        if not self._last_assistant_response:
            self._write_error("No assistant response available to copy.")
            return
        try:
            self.copy_to_clipboard(self._last_assistant_response)
            self._write_info("Copied last assistant response to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_complete_input(self) -> None:
        input_widget = self.query_one("#main-input", Input)
        prefix = input_widget.value
        if not prefix:
            return

        lowered_prefix = prefix.lower()
        for suggestion in self._suggestions:
            if suggestion.lower().startswith(lowered_prefix):
                input_widget.value = suggestion
                input_widget.cursor_position = len(suggestion)
                return


def run_textual_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    app = PocketCodeTextualApp(engine=engine, cli_context=cli_context)
    app.run()
