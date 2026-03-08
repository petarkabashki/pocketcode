from __future__ import annotations

import asyncio
import io
import logging
from contextlib import redirect_stdout

from textual.widgets import Button, Input, OptionList, Select, SelectionList, Switch, TextArea

from pocketcode.cli.command_handler import handle_command
from pocketcode.cli.user_interaction import interaction_placeholder, parse_interaction_response

from .shared import LOADING_OPTION, SKILL_GROUP_PREFIX

logger = logging.getLogger(__name__)


class TextualAppInteractionMixin:
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
        if self._pending_input_request is not None and self._active_run is not None:
            request_id = str(
                self._pending_input_request.get("request_id")
                or self._pending_input_request.get("prompt_id")
                or ""
            )
            if self._pending_input_request.get("type") == "interaction_requested":
                try:
                    response_payload = parse_interaction_response(self._pending_input_request, text)
                except ValueError as exc:
                    self._write_error(str(exc))
                    self._set_main_input_placeholder(interaction_placeholder(self._pending_input_request))
                    return
                display_text = str(response_payload.get("label") or text)
                self._write_user(display_text)
                resolved = bool(request_id) and self._active_run.resolve_interaction(request_id, response_payload)
            else:
                self._write_user(text)
                resolved = bool(request_id) and self._active_run.resolve_user_input(request_id, text)
            if not resolved:
                self._write_error("The pending prompt is no longer active.")
            self._pending_input_request = None
            self._set_main_input_placeholder()
            return
        normalized_text = text.lower()
        if self._busy and normalized_text not in {"/stop", "/cancel"}:
            self._write_info("A run is already in progress.")
            return

        try:
            if text.startswith("/"):
                self._busy = True
                self._write_user(text)
                if text.lower() == "/copy":
                    self.action_copy_last_response()
                    return
                if text.lower() == "/copy-all":
                    self.action_copy_output()
                    return
                command_output, should_exit = await asyncio.to_thread(self._run_command_capture, text)
                if command_output:
                    self._write_info(command_output)
                if should_exit:
                    self.exit()
                    return
                self._sync_ui_from_engine()
            else:
                self._busy = True
                self._write_user(text)
                self._active_run = self._engine.start_request(
                    text,
                    self._cli_context,
                    bridge_user_input=True,
                )
                self._live_run_status = "running"
                self._refresh_ui()
        except Exception as exc:
            logger.error("Failed to process Textual input: %s", exc, exc_info=True)
            self._write_error(str(exc))
        finally:
            if self._active_run is None:
                self._busy = False
            input_widget.focus()
            if self._active_run is None:
                self._sync_ui_from_engine()

    def _run_command_capture(self, command_input: str) -> tuple[str, bool]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = handle_command(
                command_input=command_input,
                engine=self._engine,
                cli_context=self._cli_context,
                active_run=self._active_run,
            )

        text = output.getvalue().strip()
        should_exit = result == "__exit__"
        return text, should_exit

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "view-control-button":
            self.action_view_control()
        elif button_id == "view-run-button":
            self.action_view_run()
        elif button_id == "control-center-button":
            self.action_pick_asset()
        elif button_id in {"edit-asset-button", "edit-asset-button-secondary"}:
            self.action_edit_asset()
        elif button_id in {"clone-asset-button", "clone-asset-button-secondary"}:
            self.action_clone_asset()
        elif button_id == "reload-button":
            self.action_reload_runtime()
        elif button_id == "goto-chat-button":
            self.action_view_chat()
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
            if widget_id == "workspace-mode-select":
                self._apply_workspace_mode_selection(value)
            elif widget_id == "theme-select":
                self._apply_theme_selection(value)
            elif widget_id == "profile-select":
                self._apply_profile_selection(value)
            elif widget_id == "llm-select":
                self._apply_llm_selection(value)
            elif widget_id == "session-confirm-select":
                self._apply_session_confirmation_selection(value)
            self._sync_ui_from_engine()
        except Exception as exc:
            self._write_error(str(exc))
            self._sync_ui_from_engine()

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
            self._sync_ui_from_engine()

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
            self._sync_ui_from_engine()

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
            self._refresh_suggestions()
            self._sync_ui_from_engine()

    def _handle_inspector_tool_toggle(self, event: SelectionList.SelectionToggled, value: str) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent profile selected.")
            self._sync_ui_from_engine()
            return
        current_agent = str(getattr(active_profile, "agent", "") or self._engine.get_current_agent() or "")
        available_tools, _, grouped_values, _ = self._build_tool_picker_model(
            agent_name=current_agent,
            active_profile=active_profile,
        )
        if not available_tools:
            self._write_error("No tools are available for the active agent.")
            self._sync_ui_from_engine()
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
            self._refresh_suggestions()
            self._sync_ui_from_engine()

    def action_view_chat(self) -> None:
        self._current_view = "chat"
        self._refresh_ui()

    def action_view_control(self) -> None:
        self._current_view = "control"
        self._refresh_ui()

    def action_view_run(self) -> None:
        self._current_view = "run"
        self._refresh_ui()

    def action_edit_asset(self) -> None:
        self._open_edit_asset_picker()

    def action_clone_asset(self) -> None:
        self._open_clone_asset_picker()

    def action_pick_asset(self) -> None:
        self._open_asset_picker()

    def action_toggle_right_panel(self) -> None:
        self._show_right_panel = not self._show_right_panel
        self._workspace_mode = "balanced"
        self._write_info(f"Inspector panel {'shown' if self._show_right_panel else 'hidden'}.")
        self._refresh_ui()

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._refresh_suggestions()
            self._write_info("Reloaded plugins, agents, tools, and LLM mappings.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_clear_output(self) -> None:
        self._output_lines = []
        self._trimmed_output_line_count = 0
        self._load_text_area_text(self.query_one("#output", TextArea), "")
        self._write_info("Cleared output.")

    def action_copy_output(self) -> None:
        if not self._output_lines:
            self._write_error("No output to copy.")
            return
        text = "\n".join(self._output_lines)
        try:
            self.copy_to_clipboard(text)
            self._write_info("Copied full console output to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_copy_last_response(self) -> None:
        if not self._last_assistant_response:
            self._write_error("No assistant response available to copy.")
            return
        try:
            self.copy_to_clipboard(self._last_assistant_response)
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
