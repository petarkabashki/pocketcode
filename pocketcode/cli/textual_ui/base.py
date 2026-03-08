from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from typing import Any, Dict

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import Button, ContentSwitcher, Footer, Input, OptionList, Select, SelectionList, Static, Switch, TextArea

from pocketcode.cli.command_handler import list_command_suggestions
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunHandle

from .shared import INHERIT_POLICY, LOADING_OPTION, THEME_OPTIONS, TextualUIState, WORKSPACE_MODES


class TextualAppBase(App[None]):
    BINDINGS = [
        Binding("tab", "complete_input", "Complete Input", priority=True),
        Binding("f1", "view_chat", "Chat", priority=True),
        Binding("f3", "edit_asset", "Edit", priority=True),
        Binding("f4", "clone_asset", "Clone", priority=True),
        Binding("f5", "view_run", "Run", priority=True),
        Binding("f6", "pick_asset", "Control", priority=True),
        Binding("f10", "toggle_right_panel", "Toggle Inspector"),
        Binding("alt+1", "view_chat", "Chat", show=False),
        Binding("alt+2", "view_control", "Control", show=False),
        Binding("alt+5", "view_run", "Run", show=False),
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
    Screen.theme-ocean #profile-tools-summary,
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
    Screen.theme-forest #profile-tools-summary,
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
    Screen.theme-ember #profile-tools-summary,
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
        content-align: right middle;
    }

    #workspace {
        height: 1fr;
        padding: 0;
    }

    #main-column {
        width: 1fr;
        min-width: 60;
        margin: 0;
    }

    #right-panel {
        width: 46;
        min-width: 40;
        max-width: 52;
    }

    #view-tabs {
        height: auto;
        margin-bottom: 1;
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

    .section-header {
        height: auto;
        align: left middle;
        margin: 0;
    }

    .section-header .section-title {
        width: 1fr;
    }

    .section-save-button {
        min-width: 8;
        width: 8;
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
        width: auto;
        min-width: 12;
        margin-bottom: 0;
    }

    #profile-list,
    #skill-list,
    #inspector-tools {
        height: 12;
        margin-bottom: 0;
        border: round #334155;
        background: #020617;
    }

    #profile-tools-summary {
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

    #run-preview,
    #inspector-context,
    #inspector-prompts {
        height: 10;
        border: round #334155;
        background: #020617;
        color: #e2e8f0;
    }

    #run-preview,
    #inspector-context,
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
        system_settings = (
            engine.get_system_settings()
            if hasattr(engine, "get_system_settings")
            else {
                "theme_name": "ocean",
                "workspace_mode": "balanced",
                "default_agent": None,
                "default_llm_profile": None,
            }
        )
        self._busy = False
        self._active_run: RunHandle | None = None
        self._pending_input_request: dict[str, Any] | None = None
        self._live_run_status = "idle"
        self._live_run_events: list[str] = []
        self._show_right_panel = True
        self._current_view = "chat"
        self._theme_name = str(system_settings.get("theme_name") or "ocean")
        self._workspace_mode = str(system_settings.get("workspace_mode") or "balanced")
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
        self._ui_state: TextualUIState | None = None
        self._apply_workspace_mode(self._workspace_mode, announce=False)

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
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
                            yield Button("Control Center", id="control-center-button", variant="primary")
                            yield Button("Reload Runtime", id="reload-button", variant="primary")
                            yield Button("Return to Chat", id="goto-chat-button")
                    with VerticalScroll(id="view-run", classes="view view-scroll"):
                        yield Static("Last run summary and effective runtime state.", classes="hint")
                        yield TextArea("", id="run-preview", read_only=True)
                yield Input(
                    id="main-input",
                    placeholder="Type a request or /command. F1 chat F3 edit F4 clone F5 run F6 control",
                )
            with VerticalScroll(id="right-panel", classes="view"):
                yield Static("Inspector", classes="panel-title")
                yield Static("", id="inspector-summary", classes="card")
                yield Static("Session Context", classes="section-title")
                yield TextArea("", id="inspector-context", read_only=True)
                yield Static("Saved Sessions", classes="section-title")
                yield TextArea("", id="inspector-sessions", read_only=True)
                yield Static("Available Agent Profiles", classes="section-title")
                yield OptionList(id="profile-list")
                with Horizontal(classes="section-header"):
                    yield Static("Skills", classes="section-title")
                    yield Button("Save", id="inspector-skill-save-button", classes="section-save-button")
                yield SelectionList(id="skill-list")
                with Horizontal(classes="section-header"):
                    yield Static("Allowed Tools", classes="section-title")
                    yield Button("Save", id="inspector-tool-save-button", classes="section-save-button")
                yield SelectionList(id="inspector-tools")
                yield Static("Prompt Sources", classes="section-title")
                yield TextArea("", id="inspector-prompts", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_suggestions()
        self._refresh_ui()
        self.set_interval(0.1, self._drain_run_events)
        self.query_one("#main-input", Input).focus()

    def _refresh_suggestions(self) -> None:
        words = list_command_suggestions(self._engine)
        self._suggestions = words
        self.query_one("#main-input", Input).suggester = SuggestFromList(words, case_sensitive=False)
