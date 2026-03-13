from __future__ import annotations

import logging

from textual import events
from textual.widget import Widget
from textual.widgets import Button, Input, OptionList, RichLog, SelectionList

from pocketcode.cli.user_interaction import interaction_placeholder
from pocketcode.core.user_interaction import normalize_interaction_request

from .shared import LOADING_OPTION

logger = logging.getLogger(__name__)

EXPANDABLE_SURFACE_IDS = (
    "output",
    "run-preview",
    "inspector-summary",
    "inspector-context",
    "inspector-sessions",
    "inspector-prompts",
)

INLINE_PROMPT_INPUT_IDS = {"inline-prompt-input-chat", "inline-prompt-input-run"}
INLINE_PROMPT_OPTION_IDS = {"inline-prompt-options-chat", "inline-prompt-options-run"}
INLINE_PROMPT_CHECKLIST_IDS = {"inline-prompt-checklist-chat", "inline-prompt-checklist-run"}
INLINE_PROMPT_SUBMIT_IDS = {"inline-prompt-submit-chat", "inline-prompt-submit-run"}


class TextualAppInteractionMixin:
    def on_focus(self, event: events.Focus) -> None:
        control = getattr(event, "control", None)
        widget_id = control.id if isinstance(control, Widget) else None
        focused_surface_id = widget_id if widget_id in EXPANDABLE_SURFACE_IDS else None
        if getattr(self._cli_state, "focused_surface_id", None) == focused_surface_id:
            return
        self._set_cli_focused_surface(focused_surface_id)
        self._commit_ui_update()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        control = getattr(event, "control", None)
        if not isinstance(control, RichLog):
            return
        surface_id = control.id or ""
        if surface_id not in EXPANDABLE_SURFACE_IDS:
            return
        control.focus()
        self._set_cli_focused_surface(surface_id)
        content_offset = event.get_content_offset(control)
        self._select_surface_block_from_pointer(
            surface_id,
            pointer_y=int(getattr(content_offset, "y", getattr(event, "y", 0))),
            widget_height=max(1, control.content_region.height or control.size.height),
            scroll_y=float(getattr(control, "scroll_y", 0.0)),
        )

    def on_mouse_move(self, event: events.MouseMove) -> None:
        control = getattr(event, "control", None)
        if not isinstance(control, RichLog):
            self._set_hovered_block_if_needed(None)
            return
        surface_id = control.id or ""
        if surface_id not in EXPANDABLE_SURFACE_IDS:
            self._set_hovered_block_if_needed(None)
            return
        content_offset = event.get_content_offset(control)
        line_number = int(max(0.0, float(getattr(control, "scroll_y", 0.0))) + max(0, int(getattr(content_offset, "y", 0))))
        block_index = self._surface_block_index_from_line(surface_id, line_number)
        if block_index is None:
            self._set_hovered_block_if_needed(None)
            return
        self._set_hovered_block_if_needed(f"{surface_id}:{block_index}")

    def on_leave(self, event: events.Leave) -> None:
        control = getattr(event, "control", None)
        widget_id = control.id if isinstance(control, Widget) else None
        hovered_ref = getattr(self._cli_state, "hovered_block_ref", None)
        if hovered_ref is None:
            return
        if widget_id and str(hovered_ref).startswith(f"{widget_id}:"):
            self._set_hovered_block_if_needed(None)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._handle_surface_scroll_event(event)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._handle_surface_scroll_event(event)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        widget_id = event.input.id or ""
        if widget_id == "main-input":
            await self._handle_main_input(event.value)
        elif widget_id == "debugger-inline-value-input":
            self.action_debug_inline_add_breakpoint()
        elif widget_id in INLINE_PROMPT_INPUT_IDS:
            self._submit_inline_pending_input()

    async def _handle_main_input(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text:
            return

        input_widget = self.query_one("#main-input", Input)
        input_widget.value = ""
        pending_input_request = self._runtime_state.pending_input_request
        if pending_input_request is None and self._active_run is not None and self._active_run.is_debug_paused:
            if self._handle_textual_debugger_input(text):
                self._remember_entry_history(text)
                input_widget.focus()
                return
        if pending_input_request is not None and self._active_run is not None:
            if pending_input_request.get("type") == "interaction_requested":
                try:
                    resolved, display_text = self._resolve_pending_input_effect(text, pending_input_request)
                except ValueError as exc:
                    self._write_error(str(exc))
                    if getattr(self, "_control_presentation", "inline") != "modal":
                        self._show_inline_pending_input(dict(pending_input_request), initial_text=text)
                    self._set_main_input_placeholder(interaction_placeholder(pending_input_request))
                    return
            else:
                resolved, display_text = self._resolve_pending_input_effect(text, pending_input_request)
            self._remember_entry_history(text)
            if not resolved:
                self._write_error("The pending prompt is no longer active.")
            elif getattr(self, "_control_presentation", "inline") != "modal":
                self._show_inline_prompt_result(display_text)
            self._set_pending_input_request(None)
            self._set_main_input_placeholder()
            return
        normalized_text = text.lower()
        if self._is_busy and normalized_text not in {"/stop", "/cancel"}:
            self._write_info("A run is already in progress.")
            return

        try:
            if text.startswith("/"):
                self._clear_inline_prompt_display()
                self._set_runtime_busy(True)
                self._remember_entry_history(text)
                self._write_user(text)
                if text.lower() == "/copy":
                    self.action_copy_last_response()
                    return
                if text.lower() == "/copy-all":
                    self.action_copy_output()
                    return
                command_output, should_exit = await self._execute_command_effect(text)
                if command_output:
                    self._write_info(command_output)
                self._drain_queued_textual_actions()
                if should_exit:
                    self.exit()
                    return
            else:
                with self._batch_ui_update():
                    self._clear_inline_prompt_display()
                    self._set_runtime_busy(True)
                    self._remember_entry_history(text)
                    self._write_user(text)
                    self._start_request_effect(text)
                    self._set_runtime_status("running")
        except Exception as exc:
            logger.error("Failed to process Textual input: %s", exc, exc_info=True)
            self._write_error(str(exc))
        finally:
            if self._active_run is None:
                self._set_runtime_busy(False)
            input_widget.focus()
            if self._active_run is None:
                self._commit_engine_ui_update(refresh_suggestions=True)

    def _coerce_inline_prompt_tokens(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text:
            return []
        if "," in text:
            return [segment.strip() for segment in text.split(",") if segment.strip()]
        return [text]

    def _inline_prompt_option_label(self, option) -> str:
        label = str(option.label)
        description = str(option.description or "").strip()
        return f"{label} [{description}]" if description else label

    def _inline_prompt_help_text(self, kind: str, description: str) -> str:
        if description:
            return description
        if kind == "checklist":
            return "Use arrows and Space to toggle options, then apply."
        if kind in {"buttons", "radio"}:
            return "Choose one option, then submit."
        return "Submit the requested input for the active run."

    def _show_inline_pending_input(self, request: dict[str, object], *, initial_text: str = "") -> None:
        request_type = str(request.get("type") or "")
        prompt = str(request.get("prompt") or "Provide input")

        if request_type == "interaction_requested":
            normalized = normalize_interaction_request(request)
            defaults = self._coerce_inline_prompt_tokens(initial_text or normalized.default)
            self._inline_prompt_kind = normalized.kind
            self._inline_prompt_prompt = normalized.prompt
            self._inline_prompt_help = self._inline_prompt_help_text(normalized.kind, normalized.description)
            self._inline_prompt_placeholder = interaction_placeholder(request)
            self._inline_prompt_submit_label = normalized.submit_label or (
                "Apply" if normalized.kind == "checklist" else "Submit"
            )
            self._inline_prompt_select_options = tuple(
                (self._inline_prompt_option_label(option), str(option.id))
                for option in normalized.options
            )
            if normalized.kind == "checklist":
                selected_tokens = set(defaults)
                self._inline_prompt_selected_values = tuple(
                    str(option.id)
                    for option in normalized.options
                    if option.id in selected_tokens or str(option.value) in selected_tokens
                )
                selected_ids = set(self._inline_prompt_selected_values)
                self._inline_prompt_checklist_options = tuple(
                    (
                        self._inline_prompt_option_label(option),
                        str(option.id),
                        option.id in selected_ids,
                    )
                    for option in normalized.options
                )
                self._inline_prompt_selected_value = ""
                self._inline_prompt_text_value = ""
            elif normalized.kind in {"buttons", "radio"}:
                selected_value = ""
                if normalized.options:
                    selected_value = str(normalized.options[0].id)
                    if defaults:
                        for option in normalized.options:
                            if option.id in defaults or str(option.value) in defaults:
                                selected_value = str(option.id)
                                break
                self._inline_prompt_selected_value = selected_value
                self._inline_prompt_selected_values = ()
                self._inline_prompt_checklist_options = ()
                self._inline_prompt_text_value = ""
            else:
                self._inline_prompt_text_value = initial_text or (defaults[0] if defaults else "")
                self._inline_prompt_selected_value = ""
                self._inline_prompt_selected_values = ()
                self._inline_prompt_checklist_options = ()
        else:
            self._inline_prompt_kind = "text"
            self._inline_prompt_prompt = prompt
            self._inline_prompt_help = str(request.get("description") or "Submit the requested input for the active run.")
            self._inline_prompt_placeholder = prompt
            self._inline_prompt_submit_label = str(request.get("submit_label") or "Submit")
            self._inline_prompt_text_value = str(initial_text)
            self._inline_prompt_selected_value = ""
            self._inline_prompt_selected_values = ()
            self._inline_prompt_select_options = ()
            self._inline_prompt_checklist_options = ()

        self._inline_prompt_visible = True
        self._inline_prompt_resolved = False
        self._inline_prompt_summary_text = ""
        if self._current_view not in {"chat", "run"}:
            self._set_current_view("chat", refresh=False)
        self.call_after_refresh(self._focus_inline_pending_input_control)

    def _focus_inline_pending_input_control(self) -> None:
        if not getattr(self, "_inline_prompt_visible", False) or getattr(self, "_inline_prompt_resolved", False):
            return
        suffix = "run" if self._current_view == "run" else "chat"
        if self._inline_prompt_kind == "text":
            widget = self.query_one(f"#inline-prompt-input-{suffix}", Input)
            widget.focus()
            widget.cursor_position = len(widget.value)
            return
        if self._inline_prompt_kind in {"buttons", "radio"}:
            self.query_one(f"#inline-prompt-options-{suffix}", OptionList).focus()
            return
        self.query_one(f"#inline-prompt-checklist-{suffix}", SelectionList).focus()

    def _show_inline_prompt_result(self, summary_text: str) -> None:
        self._inline_prompt_visible = True
        self._inline_prompt_resolved = True
        self._inline_prompt_summary_text = str(summary_text)
        self._inline_prompt_text_value = ""
        self._inline_prompt_selected_value = ""
        self._inline_prompt_selected_values = ()
        self._inline_prompt_checklist_options = ()

    def _clear_inline_prompt_display(self) -> None:
        self._inline_prompt_visible = False
        self._inline_prompt_resolved = False
        self._inline_prompt_kind = "text"
        self._inline_prompt_prompt = ""
        self._inline_prompt_help = ""
        self._inline_prompt_placeholder = ""
        self._inline_prompt_submit_label = "Submit"
        self._inline_prompt_text_value = ""
        self._inline_prompt_selected_value = ""
        self._inline_prompt_selected_values = ()
        self._inline_prompt_summary_text = ""
        self._inline_prompt_select_options = ()
        self._inline_prompt_checklist_options = ()

    def _inline_pending_input_value(self) -> str:
        if self._inline_prompt_kind == "checklist":
            return ",".join(self._inline_prompt_selected_values)
        if self._inline_prompt_kind in {"buttons", "radio"}:
            return self._inline_prompt_selected_value
        return self._inline_prompt_text_value

    def _submit_inline_pending_input(self) -> None:
        if self._active_run is None:
            self._write_error("The pending prompt is no longer active.")
            return
        pending_input_request = self._runtime_state.pending_input_request
        if pending_input_request is None:
            self._write_error("The pending prompt is no longer active.")
            return
        value = self._inline_pending_input_value()
        try:
            resolved, display_text = self._resolve_pending_input_effect(value, pending_input_request)
        except ValueError as exc:
            self._write_error(str(exc))
            self.call_after_refresh(self._focus_inline_pending_input_control)
            return
        self._remember_entry_history(value)
        if not resolved:
            self._write_error("The pending prompt is no longer active.")
            return
        self._set_pending_input_request(None)
        self._set_main_input_placeholder()
        self._clear_inline_prompt_display()
        self._commit_ui_update()

    def _should_open_pending_input_modal(self, request: dict[str, object] | None) -> bool:
        if not isinstance(request, dict):
            return False
        if getattr(self, "_control_presentation", "inline") != "modal":
            return False
        if self._runtime_state.active_modal_kind is not None:
            return False
        if self._active_run is None:
            return False
        request_type = str(request.get("type") or "")
        return request_type in {"interaction_requested", "user_input_requested"}

    def _present_pending_input_modal(self, request: dict[str, object], *, initial_text: str = "") -> None:
        if not self._should_open_pending_input_modal(request):
            return
        request_type = str(request.get("type") or "")
        if request_type == "interaction_requested" and str(request.get("kind") or "text") != "text":
            self._present_interaction_controls_modal(
                title="Input Required",
                request=request,
                on_submit=lambda value: self._submit_pending_input_from_modal(value, dict(request)),
            )
            return

        prompt = str(request.get("prompt") or "Provide input")
        placeholder = interaction_placeholder(request) if request_type == "interaction_requested" else prompt
        help_text = str(request.get("description") or "Submit the requested input for the active run.")
        submit_label = str(request.get("submit_label") or "Submit")
        self._present_prompt_input_modal(
            title="Input Required",
            prompt=prompt,
            help_text=help_text,
            placeholder=placeholder,
            initial_text=initial_text,
            submit_label=submit_label,
            on_submit=lambda value: self._submit_pending_input_from_modal(value, dict(request)),
        )

    def _submit_pending_input_from_modal(self, value: str, request: dict[str, object]) -> None:
        if self._active_run is None:
            self._write_error("The pending prompt is no longer active.")
            return
        pending_input_request = self._runtime_state.pending_input_request
        if pending_input_request is None:
            self._write_error("The pending prompt is no longer active.")
            return
        request_id = str(
            request.get("request_id")
            or request.get("prompt_id")
            or ""
        )
        pending_request_id = str(
            pending_input_request.get("request_id")
            or pending_input_request.get("prompt_id")
            or ""
        )
        if request_id and pending_request_id and request_id != pending_request_id:
            self._write_error("A different prompt is now active.")
            return
        try:
            resolved, display_text = self._resolve_pending_input_effect(value, pending_input_request)
        except ValueError as exc:
            self._write_error(str(exc))
            self.call_after_refresh(lambda: self._present_pending_input_modal(dict(pending_input_request), initial_text=value))
            return
        self._remember_entry_history(value)
        if not resolved:
            self._write_error("The pending prompt is no longer active.")
            return
        self._set_pending_input_request(None)
        self._set_main_input_placeholder()
        if getattr(self, "_control_presentation", "inline") != "modal":
            self._show_inline_prompt_result(display_text)
        self.query_one("#main-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "debug-next-button":
            self.action_debug_next()
        elif button_id == "debug-continue-button":
            self.action_debug_continue()
        elif button_id == "debug-add-break-button":
            self.action_debug_add_breakpoint()
        elif button_id == "debug-clear-selected-break-button":
            self.action_debug_clear_selected_breakpoint()
        elif button_id == "debug-clear-breaks-button":
            self.action_debug_clear_breakpoints()
        elif button_id == "debug-status-button":
            self.action_debug_status()
        elif button_id == "debug-breaks-button":
            self.action_debug_breakpoints()
        elif button_id == "debug-quit-button":
            self.action_debug_quit()
        elif button_id == "debugger-inline-apply-button":
            self.action_debug_inline_add_breakpoint()
        elif button_id == "debugger-inline-cancel-button":
            self._hide_inline_debugger_breakpoint_editor()
        elif button_id in INLINE_PROMPT_SUBMIT_IDS:
            self._submit_inline_pending_input()

    def on_key(self, event) -> None:
        if event.key != "space" or not isinstance(self.focused, SelectionList):
            return
        if self.focused.disabled or not self.focused.option_count:
            return
        event.prevent_default()
        event.stop()
        if self.focused.highlighted is None:
            self.focused.highlighted = 0
        self.focused.action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id in INLINE_PROMPT_OPTION_IDS:
            option_id = getattr(event, "option_id", None)
            if option_id is None:
                option_index = getattr(event, "option_index", getattr(event, "index", None))
                if option_index is None or option_index >= len(self._inline_prompt_select_options):
                    return
                self._inline_prompt_selected_value = str(self._inline_prompt_select_options[option_index][1])
            else:
                self._inline_prompt_selected_value = str(option_id)
            self._commit_ui_update()
            return

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        list_id = event.selection_list.id or ""
        if list_id in INLINE_PROMPT_CHECKLIST_IDS and not event.selection_list.disabled:
            selected_values: list[str] = []
            for selected in event.selection_list.selected:
                value = str(selected)
                if value != LOADING_OPTION:
                    selected_values.append(value)
            self._inline_prompt_selected_values = tuple(selected_values)
            self._inline_prompt_checklist_options = tuple(
                (label, value, value in self._inline_prompt_selected_values)
                for label, value, _ in self._inline_prompt_checklist_options
            )
            self._commit_ui_update()
        return

    def action_pick_view(self) -> None:
        self._open_view_picker()

    def action_toggle_right_panel(self) -> None:
        next_visible = not self._cli_state.right_panel_visible
        with self._batch_ui_update():
            self._set_cli_right_panel_visible(next_visible)
            self._write_info(f"Details panel {'shown' if next_visible else 'hidden'}.")

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._write_info("Reloaded resource roots, namespaces, agents, tools, skills, and LLM mappings.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._commit_engine_ui_update(refresh_suggestions=True)

    def action_clear_output(self) -> None:
        self._clear_console_state()
        self.query_one("#output", RichLog).clear()
        self._output_render_cache = None
        self._write_info("Cleared output.")

    def action_toggle_expanded_surface(self) -> None:
        surface_id = self._resolve_expansion_surface_id()
        if not surface_id:
            self._write_info("No expandable Rich panel is active in the current view.")
            return
        block_index = self._resolve_selected_compactable_block_index(surface_id)
        if block_index is None:
            self._write_info("The current panel has no compacted content to expand.")
            return
        self._set_cli_selected_surface_block(surface_id, block_index)
        self._toggle_cli_expanded_block(surface_id, block_index)
        self._commit_ui_update()

    def action_focus_next_rich_surface(self) -> None:
        self._cycle_rich_surface_focus(direction=1)

    def action_focus_previous_rich_surface(self) -> None:
        self._cycle_rich_surface_focus(direction=-1)

    def action_focus_next_compactable_block(self) -> None:
        self._cycle_surface_block_selection(direction=1)

    def action_focus_previous_compactable_block(self) -> None:
        self._cycle_surface_block_selection(direction=-1)

    def action_copy_output(self) -> None:
        if not self._runtime_state.output_lines:
            self._write_error("No output to copy.")
            return
        text = "\n".join(self._runtime_state.output_lines)
        try:
            self.copy_to_clipboard(text)
            self._write_info("Copied full console output to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_copy_last_response(self) -> None:
        if not self._runtime_state.last_assistant_response:
            self._write_error("No assistant response available to copy.")
            return
        try:
            self.copy_to_clipboard(self._runtime_state.last_assistant_response)
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

    def _resolve_expansion_surface_id(self) -> str | None:
        focused_surface_id = getattr(self._cli_state, "focused_surface_id", None)
        if focused_surface_id in EXPANDABLE_SURFACE_IDS:
            return str(focused_surface_id)
        focused = self.focused
        if isinstance(focused, Widget):
            widget_id = focused.id or ""
            if widget_id in EXPANDABLE_SURFACE_IDS:
                return widget_id
        if self._current_view == "run":
            return "run-preview"
        if self._current_view == "chat":
            return "output"
        if self._show_right_panel:
            return "inspector-summary"
        return None

    def _surface_blocks(self, surface_id: str) -> tuple:
        if surface_id == "output":
            return self._runtime_state.output_blocks
        if self._ui_state is None:
            return ()
        mapping = {
            "run-preview": self._ui_state.run_preview_blocks,
            "inspector-summary": self._ui_state.inspector_summary_blocks,
            "inspector-context": self._ui_state.inspector_context_blocks,
            "inspector-sessions": self._ui_state.inspector_sessions_blocks,
            "inspector-prompts": self._ui_state.inspector_prompt_blocks,
        }
        return tuple(mapping.get(surface_id, ()))

    def _surface_compactable_block_indices(self, surface_id: str) -> tuple[int, ...]:
        return self._surface_compactable_indices(self._surface_blocks(surface_id))

    def _resolve_selected_compactable_block_index(self, surface_id: str) -> int | None:
        compactable_indices = self._surface_compactable_block_indices(surface_id)
        if not compactable_indices:
            return None
        selected_map = dict(self._cli_state.selected_surface_block_indices)
        selected_index = selected_map.get(surface_id)
        if selected_index in compactable_indices:
            return int(selected_index)
        return compactable_indices[0]

    def _visible_rich_surface_ids(self) -> tuple[str, ...]:
        surfaces: list[str] = []
        if self._current_view == "chat":
            surfaces.append("output")
        elif self._current_view == "run":
            surfaces.append("run-preview")
        if self._show_right_panel:
            surfaces.extend(
                [
                    "inspector-summary",
                    "inspector-context",
                    "inspector-sessions",
                    "inspector-prompts",
                ]
            )
        return tuple(surfaces)

    def _cycle_rich_surface_focus(self, *, direction: int) -> None:
        surface_ids = self._visible_rich_surface_ids()
        if not surface_ids:
            return
        focused = self.focused
        focused_id = focused.id if isinstance(focused, Widget) else None
        if focused_id in surface_ids:
            current_index = surface_ids.index(str(focused_id))
            next_index = (current_index + direction) % len(surface_ids)
        else:
            next_index = 0 if direction > 0 else -1
        self.query_one(f"#{surface_ids[next_index]}", RichLog).focus()

    def _cycle_surface_block_selection(self, *, direction: int) -> None:
        surface_id = self._resolve_expansion_surface_id()
        if not surface_id:
            self._write_info("No Rich panel is active for block navigation.")
            return
        compactable_indices = self._surface_compactable_block_indices(surface_id)
        if not compactable_indices:
            self._write_info("The current panel has no compacted blocks to select.")
            return
        selected_map = dict(self._cli_state.selected_surface_block_indices)
        current_index = selected_map.get(surface_id)
        if current_index in compactable_indices:
            current_position = compactable_indices.index(int(current_index))
            next_position = (current_position + direction) % len(compactable_indices)
        else:
            next_position = 0 if direction > 0 else -1
        self._set_cli_selected_surface_block(surface_id, compactable_indices[next_position])
        self._commit_ui_update()

    def _handle_surface_scroll_event(self, event: events.MouseEvent) -> None:
        control = getattr(event, "control", None)
        if not isinstance(control, RichLog):
            return
        surface_id = control.id or ""
        if surface_id not in EXPANDABLE_SURFACE_IDS:
            return
        self._set_cli_focused_surface(surface_id)
        self.set_timer(0, lambda surface_id=surface_id: self._select_surface_block_from_scroll(surface_id))

    def _compactable_block_index_for_fraction(self, surface_id: str, fraction: float) -> int | None:
        compactable_indices = self._surface_compactable_block_indices(surface_id)
        if not compactable_indices:
            return None
        normalized = max(0.0, min(1.0, float(fraction)))
        if len(compactable_indices) == 1:
            return compactable_indices[0]
        position = int(round(normalized * (len(compactable_indices) - 1)))
        return compactable_indices[position]

    def _set_selected_surface_block_if_needed(self, surface_id: str, block_index: int | None) -> None:
        if block_index is None:
            return
        selected_map = dict(self._cli_state.selected_surface_block_indices)
        if selected_map.get(surface_id) == block_index:
            return
        self._set_cli_selected_surface_block(surface_id, block_index)
        self._commit_ui_update()

    def _set_hovered_block_if_needed(self, block_ref: str | None) -> None:
        if getattr(self._cli_state, "hovered_block_ref", None) == block_ref:
            return
        self._set_cli_hovered_block(block_ref)
        self._commit_ui_update()

    def _select_surface_block_from_pointer(
        self,
        surface_id: str,
        *,
        pointer_y: int,
        widget_height: int,
        scroll_y: float = 0.0,
    ) -> None:
        line_number = int(max(0.0, scroll_y) + max(0, pointer_y))
        if self._select_surface_block_from_line(surface_id, line_number):
            return
        if widget_height <= 1:
            fraction = 0.0
        else:
            fraction = max(0.0, min(1.0, float(pointer_y) / float(widget_height - 1)))
        self._set_selected_surface_block_if_needed(
            surface_id,
            self._compactable_block_index_for_fraction(surface_id, fraction),
        )

    def _surface_block_index_from_line(self, surface_id: str, line_number: int) -> int | None:
        spans = self._surface_render_spans(surface_id) if hasattr(self, "_surface_render_spans") else ()
        compactable_indices = set(self._surface_compactable_block_indices(surface_id))
        for span in spans:
            if span.block_index not in compactable_indices:
                continue
            if span.start_line <= line_number <= span.end_line:
                return span.block_index
        return None

    def _select_surface_block_from_line(self, surface_id: str, line_number: int) -> bool:
        block_index = self._surface_block_index_from_line(surface_id, line_number)
        if block_index is None:
            return False
        self._set_selected_surface_block_if_needed(surface_id, block_index)
        return True

    def _select_surface_block_from_scroll(self, surface_id: str) -> None:
        compactable_indices = self._surface_compactable_block_indices(surface_id)
        if not compactable_indices:
            return
        widget = self.query_one(f"#{surface_id}", RichLog)
        viewport_height = max(1, widget.content_region.height or widget.size.height)
        virtual_height = max(viewport_height, int(getattr(widget.virtual_size, "height", viewport_height)))
        center_line = int(float(getattr(widget, "scroll_y", 0.0)) + (viewport_height / 2.0))
        if self._select_surface_block_from_line(surface_id, center_line):
            return
        if virtual_height <= viewport_height:
            fraction = 0.0
        else:
            scroll_y = float(getattr(widget, "scroll_y", 0.0))
            center_line = min(float(virtual_height), scroll_y + (viewport_height / 2.0))
            fraction = center_line / float(virtual_height)
        self._set_selected_surface_block_if_needed(
            surface_id,
            self._compactable_block_index_for_fraction(surface_id, fraction),
        )
