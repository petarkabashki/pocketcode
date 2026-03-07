from __future__ import annotations

from typing import Any

from .picker_screens import ToolSelectionScreen
from .shared import PickerOption


class TextualAppAssetManagementMixin:
    def _clone_selected_asset(self, asset_name: str, new_name: str) -> None:
        active_profile = self._engine.active_agent_profile
        if asset_name == "agent":
            if active_profile is None:
                self._write_error("No active agent to clone.")
                return
            cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
            cloned = cloner(active_profile.name, new_name)
            self._engine.set_active_agent_profile(new_name)
            target_path = getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active agent to {target_path}.")
            else:
                self._write_info(f"Cloned active agent to workspace agent '{new_name}'.")
        elif asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                self._write_error("No active LLM profile to clone.")
                return
            if not hasattr(self._engine, "clone_llm_profile"):
                self._write_error("This runtime does not support cloning LLM profiles.")
                return
            cloned = self._engine.clone_llm_profile(profile_name, new_name)
            self._engine.set_global_llm_override(new_name)
            target_path = cloned.get("source_path") if isinstance(cloned, dict) else getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active LLM profile to {target_path}.")
            else:
                self._write_info(f"Cloned active LLM profile to workspace profile '{new_name}'.")
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                self._write_error("No active mode to clone.")
                return
            if not hasattr(self._engine, "clone_mode"):
                self._write_error("This runtime does not support cloning modes.")
                return
            target_path = self._engine.clone_mode(active_mode.name, new_name)
            if hasattr(self._engine, "set_last_used_mode"):
                self._engine.set_last_used_mode(new_name)
            else:
                self._engine.set_mode(new_name)
            self._write_info(f"Cloned active mode to {target_path}.")
        else:
            self._write_error(f"Unsupported clone target: {asset_name}")
            return

        self._refresh_suggestions()
        self._sync_ui_from_engine()

    def _confirm_delete_current_asset(self, asset_name: str) -> None:
        current_name = None
        if asset_name == "agent":
            current_name = self._engine.active_agent_profile.name if self._engine.active_agent_profile else None
        elif asset_name == "llm":
            current_name = self._current_llm_profile_name()
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            current_name = active_mode.name if active_mode is not None else None
        if not current_name:
            self._write_error(f"No active {asset_name} selected.")
            return
        self._show_picker(
            title=f"Delete {asset_name.title()}",
            options=(
                PickerOption("delete", f"Delete {current_name}", search_text="confirm delete"),
                PickerOption("cancel", "Cancel"),
            ),
            current_value=None,
            on_select=lambda value: self._delete_current_asset(asset_name) if value == "delete" else None,
            help_text=f"Delete the current {asset_name} config if it is workspace-backed.",
        )

    def _delete_current_asset(self, asset_name: str) -> None:
        if asset_name == "agent":
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            if not hasattr(self._engine, "delete_agent_profile"):
                self._write_error("This runtime does not support deleting agent profiles.")
                return
            target_path = self._engine.delete_agent_profile(active_profile.name)
            self._write_info(f"Deleted workspace agent '{active_profile.name}' from {target_path}.")
        elif asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                self._write_error("No active LLM profile selected.")
                return
            if not hasattr(self._engine, "delete_llm_profile"):
                self._write_error("This runtime does not support deleting LLM profiles.")
                return
            target_path = self._engine.delete_llm_profile(profile_name)
            self._write_info(f"Deleted workspace LLM profile '{profile_name}' from {target_path}.")
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                self._write_error("No active mode selected.")
                return
            if not hasattr(self._engine, "delete_mode"):
                self._write_error("This runtime does not support deleting modes.")
                return
            target_path = self._engine.delete_mode(active_mode.name)
            self._write_info(f"Deleted mode '{active_mode.name}' from {target_path}.")
        else:
            self._write_error(f"Unsupported delete target: {asset_name}")
            return
        self._refresh_suggestions()
        self._sync_ui_from_engine()

    def _save_selection_preset(self, preset_name: str) -> None:
        if not hasattr(self._engine, "save_textual_selection_preset"):
            raise ValueError("This runtime does not support selection presets.")
        target_path = self._engine.save_textual_selection_preset(preset_name)
        self._write_info(f"Saved selection preset '{preset_name}' to {target_path}.")
        self._sync_ui_from_engine()

    def _selection_preset_options(self) -> tuple[PickerOption, ...]:
        if not hasattr(self._engine, "list_textual_selection_presets"):
            return ()
        preset_names = self._engine.list_textual_selection_presets()
        options: list[PickerOption] = []
        for preset_name in preset_names:
            snapshot = self._engine.get_textual_selection_preset(preset_name) if hasattr(
                self._engine, "get_textual_selection_preset"
            ) else {}
            description_parts = [
                f"mode={snapshot.get('active_mode')}" if isinstance(snapshot, dict) and snapshot.get("active_mode") else "",
                f"profile={snapshot.get('active_profile')}" if isinstance(snapshot, dict) and snapshot.get("active_profile") else "",
                f"llm={snapshot.get('global_llm_profile')}" if isinstance(snapshot, dict) and snapshot.get("global_llm_profile") else "",
            ]
            options.append(
                PickerOption(
                    preset_name,
                    preset_name,
                    description=" | ".join(part for part in description_parts if part),
                    search_text="selection preset snapshot",
                )
            )
        return tuple(options)

    def _open_selection_preset_picker(self, action: str) -> None:
        options = self._selection_preset_options()
        if not options:
            self._write_error("No selection presets are available.")
            return
        self._show_picker(
            title=f"{action.title()} Selection Preset",
            options=options,
            current_value=None,
            on_select=lambda preset_name: self._apply_selection_preset_action(action, preset_name),
            help_text=f"Choose a preset to {action}.",
            empty_message="No selection presets are available.",
        )

    def _apply_selection_preset_action(self, action: str, preset_name: str) -> None:
        if action == "load":
            if not hasattr(self._engine, "apply_textual_selection_preset"):
                self._write_error("This runtime does not support selection presets.")
                return
            self._engine.apply_textual_selection_preset(preset_name)
            self._write_info(f"Loaded selection preset '{preset_name}'.")
        elif action == "delete":
            if not hasattr(self._engine, "delete_textual_selection_preset"):
                self._write_error("This runtime does not support selection presets.")
                return
            self._engine.delete_textual_selection_preset(preset_name)
            self._write_info(f"Deleted selection preset '{preset_name}'.")
        else:
            self._write_error(f"Unsupported preset action: {action}")
            return
        self._sync_ui_from_engine()

    def _open_tool_selection_picker(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            profile_name = active_profile.name
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        current_agent = str(getattr(active_profile, "agent", "") or self._engine.get_current_agent() or "")
        available_tools = tuple(self._engine.list_tools_for_agent(current_agent)) if current_agent else ()
        if not available_tools:
            self._write_error("No tools are available for the active agent.")
            return
        selected_tools = set(available_tools if active_profile.tools is None else active_profile.tools)
        tool_details = (
            {tool_name: self._engine.describe_tool(tool_name) for tool_name in available_tools}
            if hasattr(self._engine, "describe_tool")
            else {}
        )
        picker_options, grouped_values, initial_selected_values = self._build_nested_tool_picker_options(
            available_tools,
            selected_tools=selected_tools,
            tool_details=tool_details,
        )

        def _handle_selection(payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            action = str(payload.get("action") or "")
            selected_values = payload.get("values", [])
            selected_set = {value for value in selected_values if not self._is_skill_group_value(value)}
            tools = None if len(selected_set) >= len(available_tools) else sorted(selected_set)
            if action == "apply":
                self._engine.set_last_used_profile_tools(profile_name, tools)
                self._write_info(
                    f"Saved last-used tool allowlist for '{profile_name}': "
                    f"{'all tools' if tools is None else f'{len(selected_set)} selected'}."
                )
            elif action == "reset":
                self._engine.reset_last_used_profile_tools(profile_name)
                self._write_info(f"Reset tool allowlist for '{profile_name}' to defaults.")
            elif action == "save_default":
                self._ensure_workspace_agent_profile(
                    action_label="saving tool defaults",
                    on_ready=lambda target_name: self._save_tool_selection_default(target_name, tools),
                )

        self.push_screen(
            ToolSelectionScreen(
                title="Edit Allowed Tools",
                tools=tuple(picker_options),
                selected_values=initial_selected_values,
                help_text=(
                    "Apply saves last-used tools. Reset clears last-used overrides. "
                    "Save as Default writes the workspace agent YAML."
                ),
                grouped_values=grouped_values,
            ),
            callback=_handle_selection,
        )

    def _open_skill_selection_picker(self) -> None:
        available_skills = tuple(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else ()
        if not available_skills:
            self._write_error("No skills are available.")
            return
        active_skill_names = self._active_skill_name_set()
        skill_groups = self._skill_group_members(available_skills)
        grouped_values = {
            self._skill_group_value(group_name): member_values
            for group_name, member_values in skill_groups.items()
        }
        picker_options: list[PickerOption] = []
        selected_values = set(active_skill_names)
        for group_name, member_values in skill_groups.items():
            group_value = self._skill_group_value(group_name)
            if member_values and all(member_value in active_skill_names for member_value in member_values):
                selected_values.add(group_value)
            picker_options.append(
                PickerOption(
                    group_value,
                    f"Group: {group_name}",
                    description=f"Toggle all {len(member_values)} skills in this group",
                    search_text=f"{group_name} group {' '.join(member_values)}",
                )
            )
            picker_options.extend(
                PickerOption(
                    skill_name,
                    f"  {skill_name}",
                    description=f"Group: {group_name}",
                    search_text=f"{skill_name} {group_name}",
                )
                for skill_name in member_values
            )

        def _handle_selection(payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            action = str(payload.get("action") or "")
            selected_values = payload.get("values", [])
            selected_set = {value for value in selected_values if not self._is_skill_group_value(value)}
            selected_skill_names = sorted(selected_set)
            if action == "apply":
                self._engine.set_last_used_skills(selected_skill_names)
                self._write_info(
                    f"Saved last-used skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                )
            elif action == "reset":
                self._engine.reset_last_used_skills()
                active_skills = sorted(self._active_skill_name_set())
                self._write_info(f"Reset skills to defaults: {', '.join(active_skills) if active_skills else 'none'}.")
            elif action == "save_default":
                self._engine.set_last_used_skills(selected_skill_names)
                self._engine.save_default_skills(selected_skill_names)
                self._write_info(
                    f"Saved default skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                )
            self._refresh_suggestions()
            self._sync_ui_from_engine()

        self.push_screen(
            ToolSelectionScreen(
                title="Select Skills",
                tools=tuple(picker_options),
                selected_values=selected_values,
                help_text=(
                    "Apply saves last-used skills. Reset restores default skills. "
                    "Save as Default writes the default skill set to pocketcode.yml."
                ),
                empty_message="No matching skills.",
                filter_placeholder="Filter skills...",
                grouped_values=grouped_values,
            ),
            callback=_handle_selection,
        )
