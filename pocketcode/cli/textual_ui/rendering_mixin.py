from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator

from textual.widgets import Input, TextArea

from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import describe_interaction_request, interaction_placeholder

from .picker_screens import AssetPickerScreen
from .selectors import select_output_text
from .shared import PickerOption, TEXTUAL_VIEWS, WORKSPACE_VIEWS
from .store import SetCurrentViewAction, SetRightPanelVisibleAction, SetWorkspaceViewAction


class TextualAppRenderingMixin:
    def _render_profile_policy_summary(self, overrides: dict[str, str]) -> str:
        if not overrides:
            return "No per-tool confirmation overrides. Tools inherit the agent default."
        lines = ["Per-tool confirmation overrides:"]
        for tool_name in sorted(overrides):
            lines.append(f"- {tool_name}: {overrides[tool_name]}")
        return "\n".join(lines)

    def _apply_ui_commit(
        self,
        *,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> None:
        if refresh_suggestions:
            self._refresh_suggestions()
        if hydrate_engine:
            self._hydrate_cli_state_from_engine()
        self._apply_ui_state(self._build_ui_state())

    def _commit_ui_update(
        self,
        *,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> None:
        if self._ui_commit_batch_depth > 0:
            self._ui_commit_requested = True
            self._ui_commit_refresh_suggestions = self._ui_commit_refresh_suggestions or refresh_suggestions
            self._ui_commit_hydrate_engine = self._ui_commit_hydrate_engine or hydrate_engine
            return
        self._apply_ui_commit(
            hydrate_engine=hydrate_engine,
            refresh_suggestions=refresh_suggestions,
        )

    def _commit_engine_ui_update(
        self,
        *,
        refresh_suggestions: bool = False,
    ) -> None:
        self._commit_ui_update(
            hydrate_engine=True,
            refresh_suggestions=refresh_suggestions,
        )

    @contextmanager
    def _batch_ui_update(
        self,
        *,
        commit: bool = True,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> Iterator[None]:
        self._ui_commit_batch_depth += 1
        if commit:
            self._ui_commit_requested = True
        self._ui_commit_refresh_suggestions = self._ui_commit_refresh_suggestions or refresh_suggestions
        self._ui_commit_hydrate_engine = self._ui_commit_hydrate_engine or hydrate_engine
        try:
            yield
        finally:
            self._ui_commit_batch_depth -= 1
            if self._ui_commit_batch_depth == 0 and self._ui_commit_requested:
                pending_hydrate_engine = self._ui_commit_hydrate_engine
                pending_refresh_suggestions = self._ui_commit_refresh_suggestions
                self._ui_commit_requested = False
                self._ui_commit_hydrate_engine = False
                self._ui_commit_refresh_suggestions = False
                self._apply_ui_commit(
                    hydrate_engine=pending_hydrate_engine,
                    refresh_suggestions=pending_refresh_suggestions,
                )

    @contextmanager
    def _batch_engine_ui_update(
        self,
        *,
        commit: bool = True,
        refresh_suggestions: bool = False,
    ) -> Iterator[None]:
        with self._batch_ui_update(
            commit=commit,
            hydrate_engine=True,
            refresh_suggestions=refresh_suggestions,
        ):
            yield

    def _refresh_ui(self) -> None:
        self._commit_ui_update()

    def _write_info(self, text: str) -> None:
        self._append_output_line(f"info> {text}")

    def _write_error(self, text: str) -> None:
        self._append_output_line(f"error> {text}")

    def _write_user(self, text: str) -> None:
        self._append_output_line(f"you> {text}")

    def _write_assistant(self, text: str) -> None:
        self._append_output_line(f"assistant> {text}", assistant_response=text)

    def _append_output_line(self, line: str, *, assistant_response: str | None = None) -> None:
        self._append_console_line(line, assistant_response=assistant_response)
        output_widget = self.query_one("#output", TextArea)
        text = select_output_text(self._runtime_state)
        self._load_text_area_text(output_widget, text)
        output_widget.scroll_end(animate=False)

    def _set_current_view(self, view_name: str, *, announce: bool = False, refresh: bool = True) -> None:
        if view_name not in TEXTUAL_VIEWS:
            raise ValueError(f"Unknown view '{view_name}'. Available: {sorted(TEXTUAL_VIEWS)}")
        if view_name == self._cli_state.current_view:
            return
        self._set_cli_current_view(view_name)
        if announce:
            self._write_info(f"View: {TEXTUAL_VIEWS[view_name]['label']}.")
        if refresh:
            self._refresh_ui()

    def _apply_workspace_view(self, view_name: str, *, announce: bool) -> None:
        config = WORKSPACE_VIEWS.get(view_name)
        if config is None:
            return
        target_view = str(config["view"])
        if target_view not in TEXTUAL_VIEWS:
            return
        self._dispatch_cli_actions(
            SetWorkspaceViewAction(workspace_view=view_name),
            SetRightPanelVisibleAction(visible=bool(config["right"])),
            SetCurrentViewAction(current_view=target_view),
        )
        if announce:
            self._write_info(f"Workspace View: {config['label']}.")

    def _set_main_input_placeholder(self, prompt: str | None = None) -> None:
        input_widget = self.query_one("#main-input", Input)
        self._set_runtime_input_placeholder(prompt)
        input_widget.placeholder = self._runtime_state.main_input_placeholder

    def _profile_cycle(self) -> list[str]:
        profile_names: list[str] = []
        for agent_name in self._engine.list_agents():
            profile_names.extend(self._engine.list_agent_profiles(agent_name))
        return profile_names

    def _remember_run_event(self, text: str) -> None:
        self._remember_runtime_event(text)

    def _drain_run_events(self) -> None:
        events = self._drain_active_run_effect()
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
            self._set_pending_input_request(event)
            self._set_runtime_status("waiting_for_input")
            self._set_main_input_placeholder(interaction_placeholder(event))
            if event.get("kind") != "text":
                self._write_info(describe_interaction_request(event))
            return True
        if event_type == "interaction_received":
            self._set_runtime_status("running")
            self._set_main_input_placeholder()
            return True
        if event_type == "user_input_requested":
            self._set_pending_input_request(event)
            self._set_runtime_status("waiting_for_input")
            self._set_main_input_placeholder(str(event.get("prompt") or "Provide input"))
            return True
        if event_type == "user_input_received":
            self._set_runtime_status("running")
            self._set_main_input_placeholder()
            return True
        if event_type == "run_completed":
            with self._batch_engine_ui_update():
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("idle")
                self._set_main_input_placeholder()
                self._write_assistant(str(event.get("output") or ""))
            return False
        if event_type == "run_failed":
            with self._batch_engine_ui_update():
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("failed")
                self._set_main_input_placeholder()
                self._write_error(str(event.get("error") or "Request failed."))
            return False
        if event_type == "run_cancelled":
            with self._batch_engine_ui_update():
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("idle")
                self._set_main_input_placeholder()
            return False
        if event_type in {"run_started", "agent_turn_started", "llm_call_started", "tool_started", "handoff"}:
            self._set_runtime_status("running")
        if event_type == "run_cancel_requested":
            self._set_runtime_status("stopping")
        return True

    def _format_runtime_event(self, event: Dict[str, Any]) -> str:
        return format_runtime_event(event)

    def _show_picker(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None,
        on_select: Callable[[str], None],
        help_text: str = "Use arrows to move, Enter to select, Esc to close.",
        empty_message: str = "No matching options.",
    ) -> None:
        option_list = tuple(options)
        if not option_list:
            self._write_error(f"No options available for {title.lower()}.")
            return
        self._present_asset_picker_modal(
            title=title,
            options=option_list,
            current_value=current_value,
            on_select=on_select,
            help_text=help_text,
            empty_message=empty_message,
        )
