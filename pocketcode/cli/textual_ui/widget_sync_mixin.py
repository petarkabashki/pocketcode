from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from typing import Iterable

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import ContentSwitcher
from textual.widgets import Button, Input, OptionList, Select, SelectionList, Static
from textual.widgets.option_list import Option

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
    def _apply_inline_prompt_state(self, state: TextualUIState) -> None:
        title = "Input Submitted" if state.inline_prompt_resolved else "Input Required"
        for suffix in ("chat", "run"):
            container = self.query_one(f"#inline-prompt-{suffix}", Vertical)
            container.display = state.inline_prompt_visible
            self._set_static_text(
                self.query_one(f"#inline-prompt-title-{suffix}", Static),
                title,
            )
            self._set_static_text(
                self.query_one(f"#inline-prompt-prompt-{suffix}", Static),
                state.inline_prompt_prompt,
            )
            self._set_static_text(
                self.query_one(f"#inline-prompt-help-{suffix}", Static),
                state.inline_prompt_help,
            )
            summary_widget = self.query_one(f"#inline-prompt-summary-{suffix}", Static)
            self._set_static_text(summary_widget, state.inline_prompt_summary_text)
            summary_widget.display = state.inline_prompt_resolved and bool(state.inline_prompt_summary_text)

            input_widget = self.query_one(f"#inline-prompt-input-{suffix}", Input)
            input_widget.display = state.inline_prompt_visible and not state.inline_prompt_resolved and state.inline_prompt_kind == "text"
            input_widget.placeholder = state.inline_prompt_placeholder
            if input_widget.value != state.inline_prompt_text_value:
                input_widget.value = state.inline_prompt_text_value
                input_widget.cursor_position = len(input_widget.value)

            option_widget = self.query_one(f"#inline-prompt-options-{suffix}", OptionList)
            option_widget.display = (
                state.inline_prompt_visible
                and not state.inline_prompt_resolved
                and state.inline_prompt_kind in {"buttons", "radio"}
            )
            self._set_option_list_options(
                option_widget,
                state.inline_prompt_select_options or (("No options available", LOADING_OPTION),),
                state.inline_prompt_selected_value or LOADING_OPTION,
            )
            option_widget.disabled = not state.inline_prompt_select_options

            checklist_widget = self.query_one(f"#inline-prompt-checklist-{suffix}", SelectionList)
            checklist_widget.display = (
                state.inline_prompt_visible
                and not state.inline_prompt_resolved
                and state.inline_prompt_kind == "checklist"
            )
            self._set_selection_list_options(
                checklist_widget,
                state.inline_prompt_checklist_options or (("No options available", LOADING_OPTION, False),),
            )
            checklist_widget.disabled = not state.inline_prompt_checklist_options

            submit_button = self.query_one(f"#inline-prompt-submit-{suffix}", Button)
            submit_button.display = state.inline_prompt_visible and not state.inline_prompt_resolved
            submit_button.label = state.inline_prompt_submit_label
            submit_button.disabled = (
                not state.inline_prompt_visible
                or state.inline_prompt_resolved
                or (
                    state.inline_prompt_kind in {"buttons", "radio"}
                    and not state.inline_prompt_select_options
                )
                or (
                    state.inline_prompt_kind == "checklist"
                    and not state.inline_prompt_checklist_options
                )
            )

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

    def _apply_debugger_controls_state(
        self,
        *,
        attached: bool,
        paused: bool,
        breakpoint_count: int,
        state: TextualUIState,
    ) -> None:
        controls = self.query_one("#debugger-controls", Horizontal)
        controls.display = attached

        next_button = self.query_one("#debug-next-button", Button)
        continue_button = self.query_one("#debug-continue-button", Button)
        add_break_button = self.query_one("#debug-add-break-button", Button)
        clear_selected_break_button = self.query_one("#debug-clear-selected-break-button", Button)
        clear_breaks_button = self.query_one("#debug-clear-breaks-button", Button)
        status_button = self.query_one("#debug-status-button", Button)
        breaks_button = self.query_one("#debug-breaks-button", Button)
        quit_button = self.query_one("#debug-quit-button", Button)

        next_button.disabled = not paused
        continue_button.disabled = not paused
        add_break_button.disabled = not attached
        clear_selected_break_button.disabled = not attached or state.selected_debugger_breakpoint_id is None
        clear_breaks_button.disabled = not attached or breakpoint_count <= 0
        status_button.disabled = not attached
        breaks_button.disabled = not attached
        quit_button.disabled = not attached
        breaks_button.label = f"Breaks ({int(breakpoint_count)})"
        clear_selected_break_button.label = (
            "Clear Selected"
            if state.selected_debugger_breakpoint_id is None
            else f"Clear #{int(state.selected_debugger_breakpoint_id)}"
        )
        clear_breaks_button.label = "Clear Breaks" if breakpoint_count <= 0 else f"Clear ({int(breakpoint_count)})"

    def _apply_debugger_inline_editor_state(self, state: TextualUIState) -> None:
        editor = self.query_one("#debugger-inline-controls", Vertical)
        editor.display = state.debugger_inline_breakpoint_visible
        self._set_static_text(
            self.query_one("#debugger-inline-help", Static),
            state.debugger_inline_breakpoint_help,
        )
        self._set_select_options(
            self.query_one("#debugger-inline-type-select", Select),
            (
                ("Node", "node"),
                ("Agent", "agent"),
                ("Tool", "tool"),
                ("Event", "event"),
                ("Handoff", "handoff"),
                ("Error", "error"),
                ("Answer", "answer"),
                ("Ask", "ask"),
                ("Condition", "when"),
            ),
            state.debugger_inline_breakpoint_type,
        )
        value_input = self.query_one("#debugger-inline-value-input", Input)
        value_input.placeholder = state.debugger_inline_breakpoint_placeholder
        if value_input.value != state.debugger_inline_breakpoint_value:
            value_input.value = state.debugger_inline_breakpoint_value
            value_input.cursor_position = len(value_input.value)
        value_required = state.debugger_inline_breakpoint_type in {"node", "agent", "tool", "event", "when"}
        value_input.disabled = not value_required
        self.query_one("#debugger-inline-cancel-button", Button).disabled = not state.debugger_inline_breakpoint_visible
        self.query_one("#debugger-inline-apply-button", Button).label = (
            "Add Breakpoint"
            if value_required
            else f"Add {state.debugger_inline_breakpoint_type.title()} Break"
        )

    def _sync_output_widget(self, *, force: bool = False) -> None:
        blocks = self._runtime_state.output_blocks
        selected_index = self._selected_surface_block_index("output", blocks)
        hovered_index = self._hovered_surface_block_index("output", blocks)
        expanded_refs = self._surface_expanded_block_refs("output", blocks)
        cache_key = (self._cli_state.theme_name, selected_index, hovered_index, expanded_refs, blocks)
        if not force and self._output_render_cache == cache_key:
            return
        output_widget = self.query_one("#output", VerticalScroll)
        output_widget.query("*").remove()
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
        for index, renderable in enumerate(renderables):
            s = Static(renderable)
            s.block_surface_id = "output"
            s.block_index = index
            output_widget.mount(s)
        output_widget.scroll_end(animate=False)
        self._output_render_cache = cache_key

    def _sync_run_preview_widget(self, blocks: tuple, *, force: bool = False) -> None:
        selected_index = self._selected_surface_block_index("run-preview", blocks)
        hovered_index = self._hovered_surface_block_index("run-preview", blocks)
        expanded_refs = self._surface_expanded_block_refs("run-preview", blocks)
        cache_key = (self._cli_state.theme_name, selected_index, hovered_index, expanded_refs, tuple(blocks))
        if not force and self._run_preview_render_cache == cache_key:
            return
        preview_widget = self.query_one("#run-preview", VerticalScroll)
        preview_widget.query("*").remove()
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
        for index, renderable in enumerate(renderables):
            s = Static(renderable)
            s.block_surface_id = "run-preview"
            s.block_index = index
            preview_widget.mount(s)
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
        widget = self.query_one(f"#{widget_id}", VerticalScroll)
        widget.query("*").remove()
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
        for index, renderable in enumerate(renderables):
            s = Static(renderable)
            s.block_surface_id = widget_id
            s.block_index = index
            widget.mount(s)
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
        if (
            previous is None
            or previous.debugger_attached != state.debugger_attached
            or previous.debugger_paused != state.debugger_paused
            or previous.debugger_breakpoint_count != state.debugger_breakpoint_count
        ):
            self._apply_debugger_controls_state(
                attached=state.debugger_attached,
                paused=state.debugger_paused,
                breakpoint_count=state.debugger_breakpoint_count,
                state=state,
            )
        if (
            previous is None
            or previous.debugger_inline_breakpoint_visible != state.debugger_inline_breakpoint_visible
            or previous.debugger_inline_breakpoint_type != state.debugger_inline_breakpoint_type
            or previous.debugger_inline_breakpoint_placeholder != state.debugger_inline_breakpoint_placeholder
            or previous.debugger_inline_breakpoint_help != state.debugger_inline_breakpoint_help
            or previous.debugger_inline_breakpoint_value != state.debugger_inline_breakpoint_value
        ):
            self._apply_debugger_inline_editor_state(state)
        if (
            previous is None
            or previous.inline_prompt_visible != state.inline_prompt_visible
            or previous.inline_prompt_resolved != state.inline_prompt_resolved
            or previous.inline_prompt_kind != state.inline_prompt_kind
            or previous.inline_prompt_prompt != state.inline_prompt_prompt
            or previous.inline_prompt_help != state.inline_prompt_help
            or previous.inline_prompt_placeholder != state.inline_prompt_placeholder
            or previous.inline_prompt_submit_label != state.inline_prompt_submit_label
            or previous.inline_prompt_text_value != state.inline_prompt_text_value
            or previous.inline_prompt_selected_value != state.inline_prompt_selected_value
            or previous.inline_prompt_selected_values != state.inline_prompt_selected_values
            or previous.inline_prompt_summary_text != state.inline_prompt_summary_text
            or previous.inline_prompt_select_options != state.inline_prompt_select_options
            or previous.inline_prompt_checklist_options != state.inline_prompt_checklist_options
        ):
            self._apply_inline_prompt_state(state)
        self.query_one("#main-input", Input).placeholder = state.main_input_placeholder
        self._sync_output_widget(force=previous is None)
        self._sync_run_preview_widget(state.run_preview_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-summary", state.inspector_summary_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-context", state.inspector_context_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-sessions", state.inspector_sessions_blocks, force=previous is None)
        self._sync_rich_log_widget("inspector-prompts", state.inspector_prompt_blocks, force=previous is None)

        self._ui_state = state
    def _set_static_text(self, widget: Static, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.update(text)
        self._text_state_cache[cache_key] = text

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

    def _set_option_list_options(
        self,
        widget: OptionList,
        options: Iterable[tuple[str, str]],
        selected_value: str,
    ) -> None:
        option_tuple = tuple((str(label), str(value)) for label, value in options)
        cache_key = widget.id or ""
        cache_value = (option_tuple, str(selected_value))
        if self._option_list_state_cache.get(cache_key) == cache_value:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options([Option(label, id=value) for label, value in option_tuple])
            highlighted = next((index for index, (_, value) in enumerate(option_tuple) if value == str(selected_value)), 0)
            widget.highlighted = highlighted if highlighted < len(option_tuple) else None
        else:
            widget.highlighted = None
        self._option_list_state_cache[cache_key] = cache_value

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
