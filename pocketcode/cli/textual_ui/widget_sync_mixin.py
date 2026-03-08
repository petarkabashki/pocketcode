from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from typing import Iterable

from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, Select, SelectionList, Static, Switch, TextArea
from textual.widgets import ContentSwitcher

from .shared import LOADING_OPTION, THEME_OPTIONS, TextualUIState


class TextualAppWidgetSyncMixin:
    def _apply_theme_name(self, theme_name: str) -> None:
        for class_name in [f"theme-{name}" for name in THEME_OPTIONS]:
            self.screen.remove_class(class_name)
        self.screen.add_class(f"theme-{theme_name}")

    def _apply_panel_visibility(self, *, right_visible: bool) -> None:
        self.query_one("#right-panel", VerticalScroll).display = right_visible

    def _apply_view_state(self, view_name: str, view_title_text: str) -> None:
        self.query_one("#view-switcher", ContentSwitcher).current = f"view-{view_name}"
        title_widget = self.query_one("#view-title", Static)
        title_widget.display = bool(view_title_text)
        self._set_static_text(title_widget, view_title_text)

    def _apply_ui_state(self, state: TextualUIState) -> None:
        previous = self._ui_state
        if previous is None or previous.theme_name != state.theme_name:
            self._apply_theme_name(state.theme_name)
        if previous is None or previous.right_panel_visible != state.right_panel_visible:
            self._apply_panel_visibility(right_visible=state.right_panel_visible)
        if (
            previous is None
            or previous.current_view != state.current_view
            or previous.view_title_text != state.view_title_text
        ):
            self._apply_view_state(state.current_view, state.view_title_text)

        self._syncing_controls = True
        try:
            self._set_select_options(
                self.query_one("#workspace-view-select", Select),
                state.workspace_view_select.options,
                state.workspace_view_select.value,
            )
            self._set_select_options(
                self.query_one("#theme-select", Select),
                state.theme_select.options,
                state.theme_select.value,
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
        finally:
            self._syncing_controls = False

        self._profile_list_names = list(state.profile_list_names)
        self._set_option_list_labels(self.query_one("#profile-list", OptionList), state.profile_list_labels)
        self._set_selection_list_options(self.query_one("#skill-list", SelectionList), state.skill_list_options)
        self._set_selection_list_options(self.query_one("#inspector-tools", SelectionList), state.tool_list_options)
        self._set_static_text(self.query_one("#inspector-summary", Static), state.inspector_summary_text)
        self._set_text_area_text(self.query_one("#inspector-context", TextArea), state.inspector_context_text)
        self._set_text_area_text(self.query_one("#inspector-sessions", TextArea), state.inspector_sessions_text)
        self._set_text_area_text(self.query_one("#inspector-prompts", TextArea), state.inspector_prompts_text)
        self._set_text_area_text(self.query_one("#run-preview", TextArea), state.run_preview_text)
        self.query_one("#main-input", Input).placeholder = state.main_input_placeholder

        self._ui_state = state

    def _set_select_options(self, widget: Select, options: Iterable[tuple[str, str]], value: str) -> None:
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
        widget.disabled = len(option_tuple) == 1 and option_tuple[0][1] == LOADING_OPTION
        self._selection_list_state_cache[cache_key] = option_tuple