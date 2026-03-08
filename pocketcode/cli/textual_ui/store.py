from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

from .shared import DEFAULT_MAIN_INPUT_PLACEHOLDER, MAX_OUTPUT_LINES, _trim_output_lines


@dataclass(frozen=True)
class TextualEngineSnapshot:
    status: Dict[str, Any]
    current_agent: str | None
    active_profile: Any
    active_skill_names: tuple[str, ...]


@dataclass(frozen=True)
class TextualCliState:
    theme_name: str
    workspace_view: str
    current_view: str
    right_panel_visible: bool
    engine: TextualEngineSnapshot


@dataclass(frozen=True)
class TextualRuntimeState:
    busy: bool
    run_status: str
    active_modal_kind: str | None
    active_modal_title: str | None
    pending_input_request: dict[str, Any] | None
    live_run_events: tuple[str, ...]
    output_lines: tuple[str, ...]
    trimmed_output_line_count: int
    last_assistant_response: str
    main_input_placeholder: str


@dataclass(frozen=True)
class HydrateEngineAction:
    snapshot: TextualEngineSnapshot


@dataclass(frozen=True)
class SetThemeAction:
    theme_name: str


@dataclass(frozen=True)
class SetWorkspaceViewAction:
    workspace_view: str


@dataclass(frozen=True)
class SetCurrentViewAction:
    current_view: str


@dataclass(frozen=True)
class SetRightPanelVisibleAction:
    visible: bool


@dataclass(frozen=True)
class ToggleRightPanelAction:
    pass


@dataclass(frozen=True)
class SetBusyAction:
    busy: bool


@dataclass(frozen=True)
class SetRunStatusAction:
    run_status: str


@dataclass(frozen=True)
class OpenModalAction:
    modal_kind: str
    modal_title: str | None


@dataclass(frozen=True)
class CloseModalAction:
    pass


@dataclass(frozen=True)
class SetPendingInputRequestAction:
    pending_input_request: dict[str, Any] | None


@dataclass(frozen=True)
class RememberRunEventAction:
    text: str


@dataclass(frozen=True)
class AppendConsoleLineAction:
    line: str
    assistant_response: str | None = None


@dataclass(frozen=True)
class ClearConsoleAction:
    pass


@dataclass(frozen=True)
class SetMainInputPlaceholderAction:
    placeholder: str


TextualCliAction = (
    HydrateEngineAction
    | SetThemeAction
    | SetWorkspaceViewAction
    | SetCurrentViewAction
    | SetRightPanelVisibleAction
    | ToggleRightPanelAction
)


TextualRuntimeAction = (
    SetBusyAction
    | SetRunStatusAction
    | OpenModalAction
    | CloseModalAction
    | SetPendingInputRequestAction
    | RememberRunEventAction
    | AppendConsoleLineAction
    | ClearConsoleAction
    | SetMainInputPlaceholderAction
)


def capture_engine_snapshot(engine: Any) -> TextualEngineSnapshot:
    status = engine.status() if hasattr(engine, "status") else {}
    current_agent = engine.get_current_agent() if hasattr(engine, "get_current_agent") else None
    active_profile = getattr(engine, "active_agent_profile", None)
    active_skill_names = tuple(
        str(getattr(skill, "name", skill))
        for skill in (engine.get_active_skills() if hasattr(engine, "get_active_skills") else [])
    )
    return TextualEngineSnapshot(
        status=dict(status) if isinstance(status, dict) else {},
        current_agent=str(current_agent) if current_agent else None,
        active_profile=active_profile,
        active_skill_names=active_skill_names,
    )


def make_initial_cli_state(
    *,
    theme_name: str,
    workspace_view: str,
    current_view: str,
    right_panel_visible: bool,
    engine: Any,
) -> TextualCliState:
    return TextualCliState(
        theme_name=str(theme_name),
        workspace_view=str(workspace_view),
        current_view=str(current_view),
        right_panel_visible=bool(right_panel_visible),
        engine=capture_engine_snapshot(engine),
    )


def make_initial_runtime_state() -> TextualRuntimeState:
    return TextualRuntimeState(
        busy=False,
        run_status="idle",
        active_modal_kind=None,
        active_modal_title=None,
        pending_input_request=None,
        live_run_events=(),
        output_lines=(),
        trimmed_output_line_count=0,
        last_assistant_response="",
        main_input_placeholder=DEFAULT_MAIN_INPUT_PLACEHOLDER,
    )


def reduce_textual_cli_state(state: TextualCliState, action: TextualCliAction) -> TextualCliState:
    if isinstance(action, HydrateEngineAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            engine=action.snapshot,
        )
    if isinstance(action, SetThemeAction):
        return TextualCliState(
            theme_name=str(action.theme_name),
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            engine=state.engine,
        )
    if isinstance(action, SetWorkspaceViewAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=str(action.workspace_view),
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            engine=state.engine,
        )
    if isinstance(action, SetCurrentViewAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=str(action.current_view),
            right_panel_visible=state.right_panel_visible,
            engine=state.engine,
        )
    if isinstance(action, SetRightPanelVisibleAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=bool(action.visible),
            engine=state.engine,
        )
    if isinstance(action, ToggleRightPanelAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=not state.right_panel_visible,
            engine=state.engine,
        )
    return state


def reduce_textual_cli_actions(
    state: TextualCliState,
    actions: Iterable[TextualCliAction],
) -> TextualCliState:
    next_state = state
    for action in actions:
        next_state = reduce_textual_cli_state(next_state, action)
    return next_state


def reduce_textual_runtime_state(
    state: TextualRuntimeState,
    action: TextualRuntimeAction,
) -> TextualRuntimeState:
    if isinstance(action, SetBusyAction):
        return TextualRuntimeState(
            busy=bool(action.busy),
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, SetRunStatusAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=str(action.run_status),
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, OpenModalAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=str(action.modal_kind),
            active_modal_title=str(action.modal_title) if action.modal_title else None,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, CloseModalAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=None,
            active_modal_title=None,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, SetPendingInputRequestAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=(
                dict(action.pending_input_request)
                if isinstance(action.pending_input_request, dict)
                else None
            ),
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, RememberRunEventAction):
        next_events = tuple((*state.live_run_events, str(action.text))[-25:])
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=next_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, AppendConsoleLineAction):
        trimmed_lines, trimmed_now = _trim_output_lines(
            list((*state.output_lines, str(action.line))),
            MAX_OUTPUT_LINES,
        )
        assistant_response = (
            str(action.assistant_response)
            if action.assistant_response is not None
            else state.last_assistant_response
        )
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=tuple(trimmed_lines),
            trimmed_output_line_count=state.trimmed_output_line_count + trimmed_now,
            last_assistant_response=assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, ClearConsoleAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=(),
            trimmed_output_line_count=0,
            last_assistant_response="",
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, SetMainInputPlaceholderAction):
        placeholder = str(action.placeholder or DEFAULT_MAIN_INPUT_PLACEHOLDER)
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=placeholder,
        )
    return state


def reduce_textual_runtime_actions(
    state: TextualRuntimeState,
    actions: Iterable[TextualRuntimeAction],
) -> TextualRuntimeState:
    next_state = state
    for action in actions:
        next_state = reduce_textual_runtime_state(next_state, action)
    return next_state
