from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from typing import Iterable

from textual.containers import VerticalScroll
from textual.widgets import ContentSwitcher
from textual.widgets import Input, OptionList, RichLog, Select, SelectionList, Static, Switch, TextArea

from .renderables import (
    RenderedBlockSpan,
    block_is_compactable,
    has_compactable_output_blocks,
    measure_rendered_block_spans,
    render_output_blocks,
)
from .shared import LOADING_OPTION, THEME_OPTIONS, THEME_PALETTES, TextualUIState
from .store import make_surface_block_ref


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

    def _apply_header_state(self, *, status_text: str, header_agent_text: str, header_llm_text: str) -> None:
        self._set_static_text(self.query_one("#header-status", Static), status_text)
        self._set_static_text(self.query_one("#header-agent", Static), header_agent_text)
        self._set_static_text(self.query_one("#header-llm", Static), header_llm_text)

    def _apply_footer_hint_state(self, footer_hint_text: str) -> None:
        hint_widget = self.query_one("#footer-hint", Static)
        hint_widget.display = bool(footer_hint_text)
        self._set_static_text(hint_widget, footer_hint_text)

    def _sync_output_widget(self, *, force: bool = False) -> None:
        blocks = self._runtime_state.output_blocks
        selected_index = self._selected_surface_block_index("output", blocks)
        hovered_index = self._hovered_surface_block_index("output", blocks)
        expanded_refs = self._surface_expanded_block_refs("output", blocks)
        cache_key = (self._cli_state.theme_name, selected_index, hovered_index, expanded_refs, blocks)
        if not force and self._output_render_cache == cache_key:
            return
        output_widget = self.query_one("#output", RichLog)
        output_widget.clear()
        palette = THEME_PALETTES.get(self._cli_state.theme_name) or next(iter(THEME_PALETTES.values()))
        renderables = render_output_blocks(
            blocks,
            palette,
            surface_id="output",
            selected_block_index=selected_index,
            hovered_block_index=hovered_index,
            expanded_block_refs=expanded_refs,
        )
        self._set_surface_render_spans("output", renderables, width=output_widget.content_region.width or output_widget.size.width)
        for renderable in renderables:
            output_widget.write(renderable, scroll_end=False)
        output_widget.scroll_end(animate=False)
        self._output_render_cache = cache_key

    def _sync_run_preview_widget(self, blocks: tuple, *, force: bool = False) -> None:
        selected_index = self._selected_surface_block_index("run-preview", blocks)
        hovered_index = self._hovered_surface_block_index("run-preview", blocks)
        expanded_refs = self._surface_expanded_block_refs("run-preview", blocks)
        cache_key = (self._cli_state.theme_name, selected_index, hovered_index, expanded_refs, tuple(blocks))
        if not force and self._run_preview_render_cache == cache_key:
            return
        preview_widget = self.query_one("#run-preview", RichLog)
        preview_widget.clear()
        palette = THEME_PALETTES.get(self._cli_state.theme_name) or next(iter(THEME_PALETTES.values()))
        renderables = render_output_blocks(
            blocks,
            palette,
            surface_id="run-preview",
            selected_block_index=selected_index,
            hovered_block_index=hovered_index,
            expanded_block_refs=expanded_refs,
        )
        self._set_surface_render_spans(
            "run-preview",
            renderables,
            width=preview_widget.content_region.width or preview_widget.size.width,
        )
        for renderable in renderables:
            preview_widget.write(renderable, scroll_end=False)
        preview_widget.scroll_end(animate=False)
        self._run_preview_render_cache = cache_key

    def _sync_rich_log_widget(
        self,
        widget_id: str,
        blocks: tuple,
        *,
        force: bool = False,
    ) -> None:
        cache_attr = f"_{widget_id.replace('-', '_')}_render_cache"
        selected_index = self._selected_surface_block_index(widget_id, blocks)
        hovered_index = self._hovered_surface_block_index(widget_id, blocks)
        expanded_refs = self._surface_expanded_block_refs(widget_id, blocks)
        cache_key = (self._cli_state.theme_name, selected_index, hovered_index, expanded_refs, tuple(blocks))
        if not force and getattr(self, cache_attr) == cache_key:
            return
        widget = self.query_one(f"#{widget_id}", RichLog)
        widget.clear()
        palette = THEME_PALETTES.get(self._cli_state.theme_name) or next(iter(THEME_PALETTES.values()))
        renderables = render_output_blocks(
            blocks,
            palette,
            surface_id=widget_id,
            selected_block_index=selected_index,
            hovered_block_index=hovered_index,
            expanded_block_refs=expanded_refs,
        )
        self._set_surface_render_spans(
            widget_id,
            renderables,
            width=widget.content_region.width or widget.size.width,
        )
        for renderable in renderables:
            widget.write(renderable, scroll_end=False)
        widget.scroll_end(animate=False)
        setattr(self, cache_attr, cache_key)

    def _surface_has_compactable_blocks(self, widget_id: str, blocks: tuple) -> bool:
        return has_compactable_output_blocks(blocks)

    def _surface_compactable_indices(self, blocks: tuple) -> tuple[int, ...]:
        return tuple(index for index, block in enumerate(blocks) if block_is_compactable(block))

    def _selected_surface_block_index(self, widget_id: str, blocks: tuple) -> int | None:
        selected_map = dict(self._cli_state.selected_surface_block_indices)
        compactable_indices = self._surface_compactable_indices(blocks)
        selected_index = selected_map.get(widget_id)
        if selected_index in compactable_indices:
            return int(selected_index)
        return None

    def _surface_expanded_block_refs(self, widget_id: str, blocks: tuple) -> tuple[str, ...]:
        valid_refs = {make_surface_block_ref(widget_id, index) for index in self._surface_compactable_indices(blocks)}
        return tuple(ref for ref in self._cli_state.expanded_block_refs if ref in valid_refs)

    def _hovered_surface_block_index(self, widget_id: str, blocks: tuple) -> int | None:
        hovered_ref = getattr(self._cli_state, "hovered_block_ref", None)
        valid_refs = {make_surface_block_ref(widget_id, index): index for index in self._surface_compactable_indices(blocks)}
        if hovered_ref in valid_refs:
            return valid_refs[str(hovered_ref)]
        return None

    def _surface_render_spans(self, widget_id: str) -> tuple[RenderedBlockSpan, ...]:
        spans = self._rich_surface_line_span_cache.get(widget_id)
        return tuple(spans) if spans else ()

    def _set_surface_render_spans(
        self,
        widget_id: str,
        renderables: list,
        *,
        width: int,
    ) -> None:
        self._rich_surface_line_span_cache[widget_id] = measure_rendered_block_spans(renderables, width=width)

    def _apply_ui_state(self, state: TextualUIState) -> None:
        previous = self._ui_state
        if previous is None or previous.theme_name != state.theme_name:
            self._apply_theme_name(state.theme_name)
            self._sync_output_widget(force=True)
            self._sync_run_preview_widget(state.run_preview_blocks, force=True)
            self._sync_rich_log_widget("inspector-summary", state.inspector_summary_blocks, force=True)
            self._sync_rich_log_widget("inspector-context", state.inspector_context_blocks, force=True)
            self._sync_rich_log_widget("inspector-sessions", state.inspector_sessions_blocks, force=True)
            self._sync_rich_log_widget("inspector-prompts", state.inspector_prompt_blocks, force=True)
        if previous is None or previous.right_panel_visible != state.right_panel_visible:
            self._apply_panel_visibility(right_visible=state.right_panel_visible)
        if (
            previous is None
            or previous.current_view != state.current_view
            or previous.view_title_text != state.view_title_text
        ):
            self._apply_view_state(state.current_view, state.view_title_text)
        if (
            previous is None
            or previous.status_text != state.status_text
            or previous.footer_hint_text != state.footer_hint_text
            or previous.header_agent_text != state.header_agent_text
            or previous.header_llm_text != state.header_llm_text
        ):
            self._apply_header_state(
                status_text=state.status_text,
                header_agent_text=state.header_agent_text,
                header_llm_text=state.header_llm_text,
            )
            self._apply_footer_hint_state(state.footer_hint_text)

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
        self.query_one("#main-input", Input).placeholder = state.main_input_placeholder
        self._sync_output_widget(force=previous is None)
        self._sync_run_preview_widget(state.run_preview_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-summary", state.inspector_summary_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-context", state.inspector_context_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-sessions", state.inspector_sessions_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-prompts", state.inspector_prompt_blocks, force=previous is None)

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