from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


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


TextualCliAction = (
    HydrateEngineAction
    | SetThemeAction
    | SetWorkspaceViewAction
    | SetCurrentViewAction
    | SetRightPanelVisibleAction
    | ToggleRightPanelAction
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
