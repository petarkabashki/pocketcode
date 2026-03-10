from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from dataclasses import replace
from typing import Any, Dict

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import Button, ContentSwitcher, Footer, Input, OptionList, RichLog, Select, SelectionList, Static, Switch, TextArea

from pocketcode.cli.command_handler import list_command_suggestions
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunHandle

from .shared import (
    DEFAULT_MAIN_INPUT_PLACEHOLDER,
    INHERIT_POLICY,
    LOADING_OPTION,
    THEME_CSS,
    THEME_OPTIONS,
    TextualUIState,
    WORKSPACE_VIEWS,
)
from .store import (
    AppendConsoleLineAction,
    AppendOutputBlockAction,
    CloseModalAction,
    ClearConsoleAction,
    HydrateEngineAction,
    OpenModalAction,
    RememberRunEventAction,
    SetBusyAction,
    SetCurrentViewAction,
    SetFocusedSurfaceAction,
    SetHoveredBlockAction,
    SetMainInputPlaceholderAction,
    SetPendingInputRequestAction,
    SetRightPanelVisibleAction,
    SetRunStatusAction,
    SetSelectedSurfaceBlockAction,
    SetThemeAction,
    ToggleExpandedBlockAction,
    SetWorkspaceViewAction,
    TextualCliAction,
    TextualCliState,
    OutputBlock,
    TextualRuntimeAction,
    TextualRuntimeState,
    capture_engine_snapshot,
    make_initial_cli_state,
    make_initial_runtime_state,
    reduce_textual_cli_actions,
    reduce_textual_cli_state,
    reduce_textual_runtime_actions,
    reduce_textual_runtime_state,
)


class TextualAppBase(App[None]):
    BINDINGS = [
        Binding("f2", "pick_history", "History", priority=True),
        Binding("tab", "complete_input", "Complete Input", priority=True),
        Binding("ctrl+p", "history_previous", "Previous Entry", show=False, priority=True),
        Binding("ctrl+n", "history_next", "Next Entry", show=False, priority=True),
        Binding("f3", "edit_asset", "Edit", priority=True),
        Binding("f4", "clone_asset", "Clone", priority=True),
        Binding("f5", "pick_view", "Views", priority=True),
        Binding("f6", "pick_asset", "Control", priority=True),
        Binding("ctrl+up", "focus_previous_rich_surface", "Prev Panel"),
        Binding("ctrl+down", "focus_next_rich_surface", "Next Panel"),
        Binding("ctrl+left", "focus_previous_compactable_block", "Prev Block"),
        Binding("ctrl+right", "focus_next_compactable_block", "Next Block"),
        Binding("f10", "toggle_right_panel", "Toggle Inspector"),
        Binding("ctrl+shift+a", "copy_output", "Copy Output"),
        Binding("ctrl+y", "copy_last_response", "Copy Last"),
        Binding("f7", "debug_next", "Debug Next"),
        Binding("f8", "debug_continue", "Debug Continue"),
        Binding("f9", "debug_add_breakpoint", "Debug Break"),
        Binding("ctrl+g", "debug_status", "Debug Status"),
        Binding("ctrl+b", "debug_breakpoints", "Debug Breaks"),
        Binding("ctrl+k", "debug_clear_selected_breakpoint", "Debug Clear One"),
        Binding("ctrl+shift+b", "debug_clear_breakpoints", "Debug Clear"),
        Binding("ctrl+r", "reload_runtime", "Reload"),
        Binding("ctrl+e", "toggle_expanded_surface", "Expand Panel"),
        Binding("ctrl+l", "clear_output", "Clear Output"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: #0f172a;
        color: #e2e8f0;
    }
    """ + THEME_CSS + """

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

    #header-status {
        width: 1fr;
        color: #e0f2fe;
        text-style: bold;
    }

    #header-agent,
    #header-llm {
        width: auto;
        margin-left: 2;
    }

    #footer-hint {
        height: auto;
        min-height: 1;
        padding: 0 1;
        background: #0b1220;
        color: #93c5fd;
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

    #debugger-controls {
        height: auto;
        margin-bottom: 1;
    }

    #debugger-controls Button {
        min-width: 10;
    }

    #debugger-inline-controls {
        height: auto;
        margin-bottom: 1;
        border: round #334155;
        background: #0b1220;
        padding: 1;
    }

    #debugger-inline-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #debugger-inline-actions {
        height: auto;
        margin-top: 1;
    }

    .inline-prompt-controls {
        height: auto;
        margin-bottom: 1;
        border: round #334155;
        background: #0b1220;
        padding: 1;
    }

    .inline-prompt-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    .inline-prompt-prompt {
        color: #f8fafc;
        margin-bottom: 1;
    }

    .inline-prompt-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    .inline-prompt-summary {
        color: #f8fafc;
        border: round #475569;
        background: #020617;
        padding: 0 1;
    }

    #inline-prompt-options-chat,
    #inline-prompt-options-run,
    #inline-prompt-checklist-chat,
    #inline-prompt-checklist-run {
        height: auto;
        max-height: 8;
        border: round #334155;
        background: #020617;
        margin-bottom: 1;
    }

    .inline-prompt-actions {
        height: auto;
        margin-top: 1;
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
                "workspace_view": "balanced",
                "default_agent": None,
                "default_llm_profile": None,
            }
        )
        self._active_run: RunHandle | None = None
        self._runtime_state: TextualRuntimeState = make_initial_runtime_state()
        self._suggestions: list[str] = []
        self._queued_textual_actions: list[tuple[Any, ...]] = []
        self._profile_list_names: list[str] = []
        self._syncing_controls = False
        self._select_state_cache: dict[str, tuple[tuple[tuple[str, str], ...], str]] = {}
        self._text_state_cache: dict[str, str] = {}
        self._rich_surface_line_span_cache: dict[str, tuple[Any, ...]] = {}
        self._output_render_cache: tuple[str, tuple[OutputBlock, ...]] | None = None
        self._run_preview_render_cache: tuple[str, tuple[Any, ...]] | None = None
        self._inspector_summary_render_cache: tuple[str, tuple[Any, ...]] | None = None
        self._inspector_context_render_cache: tuple[str, tuple[Any, ...]] | None = None
        self._inspector_sessions_render_cache: tuple[str, tuple[Any, ...]] | None = None
        self._inspector_prompts_render_cache: tuple[str, tuple[Any, ...]] | None = None
        self._option_list_state_cache: dict[str, tuple[str, ...]] = {}
        self._selection_list_state_cache: dict[str, tuple[tuple[str, str, bool], ...]] = {}
        self._textual_debugger_active = False
        self._textual_debugger_last_pause_key: tuple[Any, ...] | None = None
        self._ui_commit_batch_depth = 0
        self._ui_commit_requested = False
        self._ui_commit_hydrate_engine = False
        self._ui_commit_refresh_suggestions = False
        self._ui_state: TextualUIState | None = None
        self._entry_history = list(engine.get_textual_entry_history()) if hasattr(engine, "get_textual_entry_history") else []
        self._entry_history_cursor: int | None = None
        self._entry_history_draft = ""
        self._suppress_history_input_reset = False
        self._control_presentation = (
            "modal"
            if str(
                system_settings.get("control_presentation")
                or ("modal" if system_settings.get("user_input_popups") else "inline")
            ).strip().lower()
            == "modal"
            else "inline"
        )
        self._debugger_inline_breakpoint_visible = False
        self._debugger_inline_breakpoint_type = "node"
        self._debugger_inline_breakpoint_value = ""
        self._debugger_inline_breakpoint_help = "Choose a breakpoint type and enter a target if required."
        self._debugger_inline_breakpoint_placeholder = "review_route"
        self._inline_prompt_visible = False
        self._inline_prompt_resolved = False
        self._inline_prompt_kind = "text"
        self._inline_prompt_prompt = ""
        self._inline_prompt_help = ""
        self._inline_prompt_placeholder = ""
        self._inline_prompt_submit_label = "Submit"
        self._inline_prompt_text_value = ""
        self._inline_prompt_selected_value = ""
        self._inline_prompt_selected_values: tuple[str, ...] = ()
        self._inline_prompt_summary_text = ""
        self._inline_prompt_select_options: tuple[tuple[str, str], ...] = ()
        self._inline_prompt_checklist_options: tuple[tuple[str, str, bool], ...] = ()
        self._cli_state: TextualCliState = make_initial_cli_state(
            theme_name=str(system_settings.get("theme_name") or "ocean"),
            workspace_view=str(system_settings.get("workspace_view") or system_settings.get("workspace_mode") or "balanced"),
            current_view="chat",
            right_panel_visible=True,
            engine=self._engine,
        )
        if isinstance(self._cli_context, dict):
            self._cli_context["textual_open_view_picker"] = self._queue_open_view_picker
            self._cli_context["textual_set_view"] = self._queue_set_view
            self._cli_context["textual_get_current_view"] = lambda: self._cli_state.current_view
            self._cli_context["debug_request_runner"] = self._enqueue_textual_debug_request
        self._apply_workspace_view(
            self._cli_state.workspace_view,
            announce=False,
            preserve_current_view=True,
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="topbar"):
            with Horizontal(id="topbar-main"):
                yield Static(id="header-status")
                yield Static(id="header-agent")
                yield Static(id="header-llm")
        with Horizontal(id="workspace"):
            with Vertical(id="main-column"):
                yield Static(id="view-title")
                with ContentSwitcher(initial="view-chat", id="view-switcher"):
                    with Vertical(id="view-chat", classes="view"):
                        with Vertical(id="inline-prompt-chat", classes="inline-prompt-controls hidden"):
                            yield Static("Input Required", id="inline-prompt-title-chat", classes="inline-prompt-title")
                            yield Static("", id="inline-prompt-prompt-chat", classes="inline-prompt-prompt")
                            yield Static("", id="inline-prompt-help-chat", classes="inline-prompt-help")
                            yield Input(id="inline-prompt-input-chat")
                            yield OptionList(id="inline-prompt-options-chat")
                            yield SelectionList(id="inline-prompt-checklist-chat")
                            yield Static("", id="inline-prompt-summary-chat", classes="inline-prompt-summary")
                            with Horizontal(id="inline-prompt-actions-chat", classes="inline-prompt-actions button-row"):
                                yield Button("Submit", id="inline-prompt-submit-chat", variant="primary")
                        yield RichLog(id="output", auto_scroll=False, wrap=True, markup=False)
                    with VerticalScroll(id="view-control", classes="view view-scroll"):
                        yield Static("Runtime controls apply immediately.", classes="hint")
                        yield Static("Workspace View", classes="field-label")
                        yield Select(
                            [(item["label"], key) for key, item in WORKSPACE_VIEWS.items()],
                            id="workspace-view-select",
                            allow_blank=False,
                            value=self._cli_state.workspace_view,
                        )
                        yield Static("Theme Preset", classes="field-label")
                        yield Select(
                            [(label, key) for key, label in THEME_OPTIONS.items()],
                            id="theme-select",
                            allow_blank=False,
                            value=self._cli_state.theme_name,
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
                            yield Button("Switch View", id="open-view-button", variant="primary")
                            yield Button("Control Center", id="control-center-button", variant="primary")
                            yield Button("Reload Runtime", id="reload-button", variant="primary")
                    with VerticalScroll(id="view-run", classes="view view-scroll"):
                        yield Static("Last run summary and effective runtime state.", classes="hint")
                        with Horizontal(id="debugger-controls", classes="button-row hidden"):
                            yield Button("Next", id="debug-next-button", variant="primary")
                            yield Button("Continue", id="debug-continue-button", variant="primary")
                            yield Button("Add Break", id="debug-add-break-button")
                            yield Button("Clear Selected", id="debug-clear-selected-break-button")
                            yield Button("Clear Breaks", id="debug-clear-breaks-button")
                            yield Button("Status", id="debug-status-button")
                            yield Button("Breaks", id="debug-breaks-button")
                            yield Button("Quit", id="debug-quit-button", variant="error")
                        with Vertical(id="debugger-inline-controls", classes="hidden"):
                            yield Static(
                                "Choose a breakpoint type and enter a target if required.",
                                id="debugger-inline-help",
                            )
                            yield Select(
                                [
                                    ("Node", "node"),
                                    ("Agent", "agent"),
                                    ("Tool", "tool"),
                                    ("Event", "event"),
                                    ("Handoff", "handoff"),
                                    ("Error", "error"),
                                    ("Answer", "answer"),
                                    ("Ask", "ask"),
                                    ("Condition", "when"),
                                ],
                                id="debugger-inline-type-select",
                                allow_blank=False,
                                value="node",
                            )
                            yield Input(
                                id="debugger-inline-value-input",
                                placeholder="review_route",
                            )
                            with Horizontal(id="debugger-inline-actions", classes="button-row"):
                                yield Button("Add Breakpoint", id="debugger-inline-apply-button", variant="primary")
                                yield Button("Cancel", id="debugger-inline-cancel-button")
                        with Vertical(id="inline-prompt-run", classes="inline-prompt-controls hidden"):
                            yield Static("Input Required", id="inline-prompt-title-run", classes="inline-prompt-title")
                            yield Static("", id="inline-prompt-prompt-run", classes="inline-prompt-prompt")
                            yield Static("", id="inline-prompt-help-run", classes="inline-prompt-help")
                            yield Input(id="inline-prompt-input-run")
                            yield OptionList(id="inline-prompt-options-run")
                            yield SelectionList(id="inline-prompt-checklist-run")
                            yield Static("", id="inline-prompt-summary-run", classes="inline-prompt-summary")
                            with Horizontal(id="inline-prompt-actions-run", classes="inline-prompt-actions button-row"):
                                yield Button("Submit", id="inline-prompt-submit-run", variant="primary")
                        yield RichLog(id="run-preview", auto_scroll=False, wrap=True, markup=False)
                yield Input(
                    id="main-input",
                    placeholder=DEFAULT_MAIN_INPUT_PLACEHOLDER,
                )
            with VerticalScroll(id="right-panel", classes="view"):
                yield Static("Inspector", classes="panel-title")
                yield RichLog(id="inspector-summary", auto_scroll=False, wrap=True, markup=False, classes="card")
                yield Static("Session Context", classes="section-title")
                yield RichLog(id="inspector-context", auto_scroll=False, wrap=True, markup=False)
                yield Static("Saved Sessions", classes="section-title")
                yield RichLog(id="inspector-sessions", auto_scroll=False, wrap=True, markup=False)
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
                yield RichLog(id="inspector-prompts", auto_scroll=False, wrap=True, markup=False)
            yield Static(id="footer-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._commit_ui_update(refresh_suggestions=True)
        self.set_interval(0.1, self._drain_run_events)
        self.query_one("#main-input", Input).focus()

    def _queue_open_view_picker(self) -> None:
        self._queued_textual_actions.append(("open_view_picker",))

    def _queue_set_view(self, view_name: str, *, announce: bool = False) -> None:
        self._queued_textual_actions.append(("set_view", view_name, announce))

    def _drain_queued_textual_actions(self) -> None:
        while self._queued_textual_actions:
            action = self._queued_textual_actions.pop(0)
            action_name = str(action[0]) if action else ""
            if action_name == "open_view_picker":
                self._open_view_picker()
            elif action_name == "set_view":
                _, view_name, announce = action
                self._set_current_view(str(view_name), announce=bool(announce))
            elif action_name == "start_debug_request":
                _, request = action
                self._start_debug_request_from_queue(str(request))

    def _refresh_suggestions(self) -> None:
        interface_name = self._cli_context.get("interface") if isinstance(self._cli_context, dict) else None
        words = list_command_suggestions(self._engine, interface_name=interface_name)
        self._suggestions = words
        self.query_one("#main-input", Input).suggester = SuggestFromList(words, case_sensitive=False)

    def _dispatch_cli_action(self, action: TextualCliAction) -> None:
        self._dispatch_cli_actions(action)

    def _dispatch_cli_actions(self, *actions: TextualCliAction) -> None:
        self._cli_state = reduce_textual_cli_actions(self._cli_state, actions)

    def _dispatch_runtime_action(self, action: TextualRuntimeAction) -> None:
        self._dispatch_runtime_actions(action)

    def _dispatch_runtime_actions(self, *actions: TextualRuntimeAction) -> None:
        self._runtime_state = reduce_textual_runtime_actions(self._runtime_state, actions)

    def _hydrate_cli_state_from_engine(self) -> None:
        self._dispatch_cli_action(HydrateEngineAction(snapshot=capture_engine_snapshot(self._engine)))

    def _set_cli_theme_name(self, theme_name: str) -> None:
        self._dispatch_cli_action(SetThemeAction(theme_name=str(theme_name)))

    def _set_cli_workspace_view(self, workspace_view: str) -> None:
        self._dispatch_cli_action(SetWorkspaceViewAction(workspace_view=str(workspace_view)))

    def _set_cli_current_view(self, current_view: str) -> None:
        self._dispatch_cli_action(SetCurrentViewAction(current_view=str(current_view)))

    def _set_cli_right_panel_visible(self, visible: bool) -> None:
        self._dispatch_cli_action(SetRightPanelVisibleAction(visible=bool(visible)))

    def _set_cli_focused_surface(self, surface_id: str | None) -> None:
        self._dispatch_cli_action(SetFocusedSurfaceAction(surface_id=surface_id))

    def _set_cli_hovered_block(self, block_ref: str | None) -> None:
        self._dispatch_cli_action(SetHoveredBlockAction(block_ref=block_ref))

    def _set_cli_selected_surface_block(self, surface_id: str, block_index: int) -> None:
        self._dispatch_cli_action(
            SetSelectedSurfaceBlockAction(surface_id=str(surface_id), block_index=int(block_index))
        )

    def _toggle_cli_expanded_block(self, surface_id: str, block_index: int) -> None:
        self._dispatch_cli_action(
            ToggleExpandedBlockAction(surface_id=str(surface_id), block_index=int(block_index))
        )

    def _set_runtime_busy(self, busy: bool) -> None:
        self._dispatch_runtime_action(SetBusyAction(busy=bool(busy)))

    def _set_runtime_status(self, run_status: str) -> None:
        self._dispatch_runtime_action(SetRunStatusAction(run_status=str(run_status)))

    def _open_runtime_modal(self, modal_kind: str, *, modal_title: str | None = None) -> None:
        self._dispatch_runtime_action(
            OpenModalAction(modal_kind=str(modal_kind), modal_title=modal_title)
        )

    def _close_runtime_modal(self) -> None:
        self._dispatch_runtime_action(CloseModalAction())

    def _set_pending_input_request(self, request: dict[str, Any] | None) -> None:
        self._dispatch_runtime_action(SetPendingInputRequestAction(pending_input_request=request))

    def _remember_runtime_event(self, text: str) -> None:
        self._dispatch_runtime_action(RememberRunEventAction(text=str(text)))

    def _append_console_line(self, line: str, *, assistant_response: str | None = None) -> None:
        self._dispatch_runtime_action(
            AppendConsoleLineAction(line=str(line), assistant_response=assistant_response)
        )

    def _append_output_block(
        self,
        block: OutputBlock,
        *,
        plain_text: str | None = None,
        assistant_response: str | None = None,
        include_in_transcript: bool = True,
    ) -> None:
        self._dispatch_runtime_action(
            AppendOutputBlockAction(
                block=block,
                plain_text=plain_text,
                assistant_response=assistant_response,
                include_in_transcript=bool(include_in_transcript),
            )
        )

    def _append_output_blocks(
        self,
        blocks: list[OutputBlock] | tuple[OutputBlock, ...],
        *,
        plain_text: str | None = None,
        assistant_response: str | None = None,
    ) -> None:
        if not blocks:
            return
        actions = []
        for index, block in enumerate(blocks):
            actions.append(
                AppendOutputBlockAction(
                    block=block,
                    plain_text=plain_text if index == 0 else None,
                    assistant_response=assistant_response if index == 0 else None,
                    include_in_transcript=(index == 0),
                )
            )
        self._dispatch_runtime_actions(*actions)

    def _clear_console_state(self) -> None:
        self._dispatch_runtime_action(ClearConsoleAction())

    def _set_runtime_input_placeholder(self, prompt: str | None = None) -> None:
        self._dispatch_runtime_action(SetMainInputPlaceholderAction(placeholder=prompt or ""))

    @property
    def _current_view(self) -> str:
        return self._cli_state.current_view

    @property
    def _theme_name(self) -> str:
        return self._cli_state.theme_name

    @property
    def _workspace_view(self) -> str:
        return self._cli_state.workspace_view

    @property
    def _show_right_panel(self) -> bool:
        return self._cli_state.right_panel_visible

    @property
    def _is_busy(self) -> bool:
        return self._runtime_state.busy

    @property
    def _busy(self) -> bool:
        return self._runtime_state.busy

    @_busy.setter
    def _busy(self, busy: bool) -> None:
        self._runtime_state = replace(self._runtime_state, busy=bool(busy))

    @property
    def _pending_input_request(self) -> dict[str, Any] | None:
        request = self._runtime_state.pending_input_request
        return dict(request) if isinstance(request, dict) else None

    @_pending_input_request.setter
    def _pending_input_request(self, request: dict[str, Any] | None) -> None:
        self._runtime_state = replace(
            self._runtime_state,
            pending_input_request=dict(request) if isinstance(request, dict) else None,
        )

    @property
    def _live_run_status(self) -> str:
        return self._runtime_state.run_status

    @_live_run_status.setter
    def _live_run_status(self, run_status: str) -> None:
        self._runtime_state = replace(self._runtime_state, run_status=str(run_status))

    @property
    def _live_run_events(self) -> list[str]:
        return list(self._runtime_state.live_run_events)

    @_live_run_events.setter
    def _live_run_events(self, events: list[str]) -> None:
        self._runtime_state = replace(
            self._runtime_state,
            live_run_events=tuple(str(item) for item in events),
        )

    @property
    def _output_lines(self) -> list[str]:
        return list(self._runtime_state.output_lines)

    @_output_lines.setter
    def _output_lines(self, lines: list[str]) -> None:
        self._runtime_state = replace(
            self._runtime_state,
            output_lines=tuple(str(line) for line in lines),
        )

    @property
    def _trimmed_output_line_count(self) -> int:
        return self._runtime_state.trimmed_output_line_count

    @_trimmed_output_line_count.setter
    def _trimmed_output_line_count(self, count: int) -> None:
        self._runtime_state = replace(self._runtime_state, trimmed_output_line_count=int(count))

    @property
    def _last_assistant_response(self) -> str:
        return self._runtime_state.last_assistant_response

    @_last_assistant_response.setter
    def _last_assistant_response(self, text: str) -> None:
        self._runtime_state = replace(self._runtime_state, last_assistant_response=str(text))
