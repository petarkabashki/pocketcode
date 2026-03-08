from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Literal

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
    focused_surface_id: str | None
    hovered_block_ref: str | None
    selected_surface_block_indices: tuple[tuple[str, int], ...]
    expanded_block_refs: tuple[str, ...]
    engine: TextualEngineSnapshot


@dataclass(frozen=True)
class TextualRuntimeState:
    busy: bool
    run_status: str
    active_modal_kind: str | None
    active_modal_title: str | None
    pending_input_request: dict[str, Any] | None
    live_run_events: tuple[str, ...]
    output_blocks: tuple["OutputBlock", ...]
    output_lines: tuple[str, ...]
    trimmed_output_line_count: int
    last_assistant_response: str
    main_input_placeholder: str


OutputKind = Literal[
    "assistant",
    "code",
    "error",
    "info",
    "runtime",
    "tool_call",
    "tool_result",
    "user",
    "warning",
]


@dataclass(frozen=True)
class OutputBlock:
    kind: OutputKind
    text: str
    title: str | None = None
    language: str | None = None


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
class SetFocusedSurfaceAction:
    surface_id: str | None


@dataclass(frozen=True)
class ToggleRightPanelAction:
    pass


@dataclass(frozen=True)
class SetHoveredBlockAction:
    block_ref: str | None


@dataclass(frozen=True)
class SetSelectedSurfaceBlockAction:
    surface_id: str
    block_index: int


@dataclass(frozen=True)
class ToggleExpandedBlockAction:
    surface_id: str
    block_index: int


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
class AppendOutputBlockAction:
    block: OutputBlock
    plain_text: str | None = None
    assistant_response: str | None = None
    include_in_transcript: bool = True


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
    | SetFocusedSurfaceAction
    | ToggleRightPanelAction
    | SetHoveredBlockAction
    | SetSelectedSurfaceBlockAction
    | ToggleExpandedBlockAction
)


def make_surface_block_ref(surface_id: str, block_index: int) -> str:
    return f"{surface_id}:{int(block_index)}"


TextualRuntimeAction = (
    SetBusyAction
    | SetRunStatusAction
    | OpenModalAction
    | CloseModalAction
    | SetPendingInputRequestAction
    | RememberRunEventAction
    | AppendOutputBlockAction
    | AppendConsoleLineAction
    | ClearConsoleAction
    | SetMainInputPlaceholderAction
)


def _trim_output_blocks(blocks: list[OutputBlock], max_items: int) -> tuple[list[OutputBlock], int]:
    if max_items <= 0:
        return [], len(blocks)
    overflow = max(0, len(blocks) - max_items)
    if overflow == 0:
        return list(blocks), 0
    return list(blocks[overflow:]), overflow


def _normalize_output_block(block: OutputBlock) -> OutputBlock:
    return OutputBlock(
        kind=str(block.kind),
        text=str(block.text),
        title=str(block.title) if block.title else None,
        language=str(block.language) if block.language else None,
    )


def _infer_output_block_from_line(line: str) -> OutputBlock:
    normalized = str(line)
    prefixes: tuple[tuple[str, OutputKind, str | None], ...] = (
        ("assistant> ", "assistant", "Assistant"),
        ("you> ", "user", "You"),
        ("error> ", "error", "Error"),
        ("warning> ", "warning", "Warning"),
        ("info> ", "info", "Info"),
        ("runtime> ", "runtime", "Runtime"),
    )
    for prefix, kind, title in prefixes:
        if normalized.startswith(prefix):
            return OutputBlock(kind=kind, text=normalized[len(prefix) :], title=title)
    return OutputBlock(kind="info", text=normalized, title=None)


def _plain_text_for_output_block(block: OutputBlock) -> str:
    prefixes = {
        "assistant": "assistant> ",
        "code": "code> ",
        "user": "you> ",
        "error": "error> ",
        "warning": "warning> ",
        "runtime": "runtime> ",
        "info": "info> ",
        "tool_call": "tool> ",
        "tool_result": "tool-result> ",
    }
    return f"{prefixes.get(block.kind, '')}{block.text}"


def _append_output_state(
    state: TextualRuntimeState,
    *,
    block: OutputBlock,
    plain_text: str | None = None,
    assistant_response: str | None = None,
    include_in_transcript: bool = True,
) -> TextualRuntimeState:
    next_block = _normalize_output_block(block)
    next_blocks, trimmed_blocks = _trim_output_blocks([*state.output_blocks, next_block], MAX_OUTPUT_LINES)
    if include_in_transcript:
        next_lines, trimmed_lines = _trim_output_lines(
            [*state.output_lines, plain_text if plain_text is not None else _plain_text_for_output_block(next_block)],
            MAX_OUTPUT_LINES,
        )
    else:
        next_lines, trimmed_lines = list(state.output_lines), 0
    response_text = state.last_assistant_response
    if assistant_response is not None:
        response_text = str(assistant_response)
    elif next_block.kind == "assistant":
        response_text = next_block.text
    return TextualRuntimeState(
        busy=state.busy,
        run_status=state.run_status,
        active_modal_kind=state.active_modal_kind,
        active_modal_title=state.active_modal_title,
        pending_input_request=state.pending_input_request,
        live_run_events=state.live_run_events,
        output_blocks=tuple(next_blocks),
        output_lines=tuple(next_lines),
        trimmed_output_line_count=state.trimmed_output_line_count + max(trimmed_blocks, trimmed_lines),
        last_assistant_response=response_text,
        main_input_placeholder=state.main_input_placeholder,
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
        focused_surface_id=None,
        hovered_block_ref=None,
        selected_surface_block_indices=(),
        expanded_block_refs=(),
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
        output_blocks=(),
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
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=action.snapshot,
        )
    if isinstance(action, SetThemeAction):
        return TextualCliState(
            theme_name=str(action.theme_name),
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetWorkspaceViewAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=str(action.workspace_view),
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetCurrentViewAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=str(action.current_view),
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetRightPanelVisibleAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=bool(action.visible),
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetFocusedSurfaceAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=str(action.surface_id) if action.surface_id else None,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, ToggleRightPanelAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=not state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetHoveredBlockAction):
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=str(action.block_ref) if action.block_ref else None,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, SetSelectedSurfaceBlockAction):
        selected_map = dict(state.selected_surface_block_indices)
        selected_map[str(action.surface_id)] = int(action.block_index)
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=tuple(sorted(selected_map.items())),
            expanded_block_refs=state.expanded_block_refs,
            engine=state.engine,
        )
    if isinstance(action, ToggleExpandedBlockAction):
        block_ref = make_surface_block_ref(str(action.surface_id), int(action.block_index))
        expanded_block_refs = set(state.expanded_block_refs)
        if block_ref in expanded_block_refs:
            expanded_block_refs.remove(block_ref)
        else:
            expanded_block_refs.add(block_ref)
        return TextualCliState(
            theme_name=state.theme_name,
            workspace_view=state.workspace_view,
            current_view=state.current_view,
            right_panel_visible=state.right_panel_visible,
            focused_surface_id=state.focused_surface_id,
            hovered_block_ref=state.hovered_block_ref,
            selected_surface_block_indices=state.selected_surface_block_indices,
            expanded_block_refs=tuple(sorted(expanded_block_refs)),
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
            output_blocks=state.output_blocks,
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
            output_blocks=state.output_blocks,
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
            output_blocks=state.output_blocks,
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
            output_blocks=state.output_blocks,
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
            output_blocks=state.output_blocks,
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
            output_blocks=state.output_blocks,
            output_lines=state.output_lines,
            trimmed_output_line_count=state.trimmed_output_line_count,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )
    if isinstance(action, AppendOutputBlockAction):
        return _append_output_state(
            state,
            block=action.block,
            plain_text=action.plain_text,
            assistant_response=action.assistant_response,
            include_in_transcript=action.include_in_transcript,
        )
    if isinstance(action, AppendConsoleLineAction):
        return _append_output_state(
            state,
            block=_infer_output_block_from_line(str(action.line)),
            plain_text=str(action.line),
            assistant_response=action.assistant_response,
        )
    if isinstance(action, ClearConsoleAction):
        return TextualRuntimeState(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_blocks=(),
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
            output_blocks=state.output_blocks,
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
