from __future__ import annotations

import logging

from textual import events
from textual.widget import Widget
from textual.widgets import Button, Input, OptionList, RichLog, Select, SelectionList, Switch, TextArea

from pocketcode.cli.user_interaction import interaction_placeholder

from .shared import LOADING_OPTION, SKILL_GROUP_PREFIX

logger = logging.getLogger(__name__)

EXPANDABLE_SURFACE_IDS = (
    "output",
    "run-preview",
    "inspector-summary",
    "inspector-context",
    "inspector-sessions",
    "inspector-prompts",
)


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

    async def _handle_main_input(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text:
            return

        input_widget = self.query_one("#main-input", Input)
        input_widget.value = ""
        pending_input_request = self._runtime_state.pending_input_request
        if pending_input_request is not None and self._active_run is not None:
            if pending_input_request.get("type") == "interaction_requested":
                try:
                    resolved = self._resolve_pending_input_effect(text, pending_input_request)
                except ValueError as exc:
                    self._write_error(str(exc))
                    self._set_main_input_placeholder(interaction_placeholder(pending_input_request))
                    return
            else:
                resolved = self._resolve_pending_input_effect(text, pending_input_request)
            if not resolved:
                self._write_error("The pending prompt is no longer active.")
            self._set_pending_input_request(None)
            self._set_main_input_placeholder()
            return
        normalized_text = text.lower()
        if self._is_busy and normalized_text not in {"/stop", "/cancel"}:
            self._write_info("A run is already in progress.")
            return

        try:
            if text.startswith("/"):
                self._set_runtime_busy(True)
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
                    self._set_runtime_busy(True)
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "open-view-button":
            self.action_pick_view()
        elif button_id == "control-center-button":
            self.action_pick_asset()
        elif button_id in {"edit-asset-button", "edit-asset-button-secondary"}:
            self.action_edit_asset()
        elif button_id in {"clone-asset-button", "clone-asset-button-secondary"}:
            self.action_clone_asset()
        elif button_id == "reload-button":
            self.action_reload_runtime()
        elif button_id == "inspector-skill-save-button":
            self._save_inspector_skill_selection()
        elif button_id == "inspector-tool-save-button":
            self._save_inspector_tool_selection()

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._syncing_controls:
            return

        if event.select.value != event.value:
            return

        widget_id = event.select.id or ""
        value = str(event.value)
        if value == LOADING_OPTION:
            return
        try:
            if widget_id == "workspace-view-select":
                self._apply_workspace_view_selection(value)
            elif widget_id == "theme-select":
                self._apply_theme_selection(value)
            elif widget_id == "profile-select":
                self._apply_profile_selection(value)
            elif widget_id == "llm-select":
                self._apply_llm_selection(value)
            elif widget_id == "session-confirm-select":
                self._apply_session_confirmation_selection(value)
            self._commit_engine_ui_update()
        except Exception as exc:
            self._write_error(str(exc))
            self._commit_engine_ui_update()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._syncing_controls:
            return

        switch_id = event.switch.id or ""
        if switch_id == "auto-confirm-switch":
            if hasattr(self._engine, "set_last_used_auto_confirm_tools"):
                self._engine.set_last_used_auto_confirm_tools(bool(event.value))
            else:
                self._engine.auto_confirm_tools = bool(event.value)
            state = "enabled" if event.value else "disabled"
            self._write_info(f"Auto-confirm tools {state}.")
            self._commit_engine_ui_update()

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
        if event.option_list.id != "profile-list":
            return
        option_index = getattr(event, "option_index", getattr(event, "index", None))
        if option_index is None or option_index >= len(self._profile_list_names):
            return
        profile_name = self._profile_list_names[option_index]
        try:
            if hasattr(self._engine, "set_last_used_active_profile"):
                self._engine.set_last_used_active_profile(profile_name)
            else:
                self._engine.set_active_agent_profile(profile_name)
            self._write_info(f"Activated agent profile: {profile_name}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._commit_engine_ui_update()

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        list_id = event.selection_list.id or ""
        if list_id not in {"skill-list", "inspector-tools"} or event.selection_list.disabled:
            return
        option_index = getattr(event, "selection_index", getattr(event, "index", None))
        if option_index is None:
            return
        option = event.selection_list.get_option_at_index(option_index)
        value = str(option.value)
        if value == LOADING_OPTION:
            return
        if list_id == "inspector-tools":
            self._handle_inspector_tool_toggle(event, value)
            return
        skill_groups = self._skill_group_members(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else {}
        try:
            if self._is_skill_group_value(value):
                group_name = value[len(SKILL_GROUP_PREFIX):]
                member_values = skill_groups.get(group_name, ())
                if value in event.selection_list.selected:
                    for member_value in member_values:
                        self._engine.enable_skill(member_value)
                    self._write_info(f"Enabled skill group: {group_name} ({len(member_values)} skills).")
                else:
                    for member_value in member_values:
                        self._engine.disable_skill(member_value)
                    self._write_info(f"Disabled skill group: {group_name} ({len(member_values)} skills).")
            elif value in event.selection_list.selected:
                self._engine.enable_skill(value)
                self._write_info(f"Enabled skill: {value}")
            else:
                self._engine.disable_skill(value)
                self._write_info(f"Disabled skill: {value}")
            active_profile = self._engine.active_agent_profile
            selected_skills = sorted(self._active_skill_name_set())
            if active_profile is not None and hasattr(self._engine, "set_last_used_profile_skills"):
                self._engine.set_last_used_profile_skills(active_profile.name, selected_skills)
            elif hasattr(self._engine, "set_last_used_skills"):
                self._engine.set_last_used_skills(selected_skills)
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._commit_engine_ui_update(refresh_suggestions=True)

    def _handle_inspector_tool_toggle(self, event: SelectionList.SelectionToggled, value: str) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent profile selected.")
            self._commit_engine_ui_update()
            return
        current_agent = str(getattr(active_profile, "agent", "") or self._engine.get_current_agent() or "")
        available_tools, _, grouped_values, _ = self._build_tool_picker_model(
            agent_name=current_agent,
            active_profile=active_profile,
        )
        if not available_tools:
            self._write_error("No tools are available for the active agent.")
            self._commit_engine_ui_update()
            return

        selected_tools = set(available_tools if active_profile.tools is None else active_profile.tools)
        try:
            if self._is_skill_group_value(value):
                group_name = value[len(SKILL_GROUP_PREFIX):]
                member_values = grouped_values.get(value, ())
                if value in event.selection_list.selected:
                    selected_tools.update(member_values)
                    self._write_info(f"Enabled tool group: {group_name} ({len(member_values)} tools).")
                else:
                    selected_tools.difference_update(member_values)
                    self._write_info(f"Disabled tool group: {group_name} ({len(member_values)} tools).")
            elif value in event.selection_list.selected:
                selected_tools.add(value)
                self._write_info(f"Enabled tool: {value}")
            else:
                selected_tools.discard(value)
                self._write_info(f"Disabled tool: {value}")
            tools = None if len(selected_tools) >= len(available_tools) else sorted(selected_tools)
            self._engine.set_last_used_profile_tools(active_profile.name, tools)
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._commit_engine_ui_update(refresh_suggestions=True)

    def action_pick_view(self) -> None:
        self._open_view_picker()

    def action_edit_asset(self) -> None:
        self._open_edit_asset_picker()

    def action_clone_asset(self) -> None:
        self._open_clone_asset_picker()

    def action_pick_asset(self) -> None:
        self._open_asset_picker()

    def action_toggle_right_panel(self) -> None:
        next_visible = not self._cli_state.right_panel_visible
        with self._batch_ui_update():
            self._set_cli_workspace_view("balanced")
            self._set_cli_right_panel_visible(next_visible)
            self._write_info(f"Inspector panel {'shown' if next_visible else 'hidden'}.")

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._write_info("Reloaded plugins, agents, tools, and LLM mappings.")
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
