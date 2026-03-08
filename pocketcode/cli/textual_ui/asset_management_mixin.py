from __future__ import annotations

from typing import Any

from .picker_screens import ToolSelectionScreen
from .shared import PickerOption


class TextualAppAssetManagementMixin:
    def _save_inspector_skill_selection(self) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent selected.")
            return
        selected_skills = sorted(self._active_skill_name_set())

        def _persist(profile_name: str) -> None:
            if not hasattr(self._engine, "save_agent_profile_skills"):
                self._write_error("This runtime does not support saving agent skills.")
                return
            self._engine.save_agent_profile_skills(profile_name, selected_skills)
            self._commit_engine_ui_update(refresh_suggestions=True)
            self._write_info(
                f"Saved inspector skills to workspace agent '{profile_name}': "
                f"{', '.join(selected_skills) if selected_skills else 'none'}."
            )

        self._ensure_workspace_agent_profile(
            action_label="saving inspector skills",
            on_ready=_persist,
        )

    def _save_inspector_tool_selection(self) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent selected.")
            return
        selected_tools = None if active_profile.tools is None else sorted(active_profile.tools)

        def _persist(profile_name: str) -> None:
            if not hasattr(self._engine, "save_agent_profile_tools"):
                self._write_error("This runtime does not support saving agent tools.")
                return
            self._engine.save_agent_profile_tools(profile_name, selected_tools)
            self._commit_engine_ui_update(refresh_suggestions=True)
            self._write_info(
                f"Saved inspector tools to workspace agent '{profile_name}': "
                f"{', '.join(selected_tools) if selected_tools else 'all'}."
            )

        self._ensure_workspace_agent_profile(
            action_label="saving inspector tools",
            on_ready=_persist,
        )

    def _clone_selected_asset(self, asset_name: str, new_name: str) -> None:
        cloned = self._clone_asset_effect(asset_name, new_name)
        if asset_name == "agent":
            target_path = getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active agent to {target_path}.")
            else:
                self._write_info(f"Cloned active agent to workspace agent '{new_name}'.")
        elif asset_name == "llm":
            target_path = cloned.get("source_path") if isinstance(cloned, dict) else getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active LLM profile to {target_path}.")
            else:
                self._write_info(f"Cloned active LLM profile to workspace profile '{new_name}'.")
        elif asset_name == "mode":
            self._write_info(f"Cloned active mode to {cloned}.")
        else:
            self._write_error(f"Unsupported clone target: {asset_name}")
            return

        self._commit_engine_ui_update(refresh_suggestions=True)

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
        deleted_name, target_path = self._delete_asset_effect(asset_name)
        if asset_name == "agent":
            self._write_info(f"Deleted workspace agent '{deleted_name}' from {target_path}.")
        elif asset_name == "llm":
            self._write_info(f"Deleted workspace LLM profile '{deleted_name}' from {target_path}.")
        elif asset_name == "mode":
            self._write_info(f"Deleted mode '{deleted_name}' from {target_path}.")
        else:
            self._write_error(f"Unsupported delete target: {asset_name}")
            return
        self._commit_engine_ui_update(refresh_suggestions=True)

    def _save_selection_preset(self, preset_name: str) -> None:
        target_path = self._save_selection_preset_effect(preset_name)
        self._write_info(f"Saved selection preset '{preset_name}' to {target_path}.")
        self._commit_engine_ui_update()

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
            self._apply_selection_preset_effect(preset_name)
            self._write_info(f"Loaded selection preset '{preset_name}'.")
        elif action == "delete":
            self._delete_selection_preset_effect(preset_name)
            self._write_info(f"Deleted selection preset '{preset_name}'.")
        else:
            self._write_error(f"Unsupported preset action: {action}")
            return
        self._commit_engine_ui_update()

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
        available_tools, picker_options, grouped_values, initial_selected_values = self._build_tool_picker_model(
            agent_name=current_agent,
            active_profile=active_profile,
        )
        if not available_tools:
            self._write_error("No tools are available for the active agent.")
            return

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

        self._present_tool_selection_modal(
            title="Edit Allowed Tools",
            tools=tuple(picker_options),
            selected_values=initial_selected_values,
            help_text=(
                "Apply saves last-used tools. Reset clears last-used overrides. "
                "Save as Default writes the workspace agent YAML."
            ),
            grouped_values=grouped_values,
            on_submit=_handle_selection,
        )

    def _open_skill_selection_picker(self) -> None:
        available_skills = tuple(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else ()
        if not available_skills:
            self._write_error("No skills are available.")
            return
        active_profile = self._engine.active_agent_profile
        profile_name = active_profile.name if active_profile is not None else None
        picker_options, grouped_values, selected_values = self._build_skill_picker_options(
            available_skills,
            selected_skills=self._active_skill_name_set(),
        )

        def _handle_selection(payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            action = str(payload.get("action") or "")
            selected_values = payload.get("values", [])
            selected_set = {value for value in selected_values if not self._is_skill_group_value(value)}
            selected_skill_names = sorted(selected_set)
            if action == "apply":
                if profile_name and hasattr(self._engine, "set_last_used_profile_skills"):
                    self._engine.set_last_used_profile_skills(profile_name, selected_skill_names)
                    self._write_info(
                        f"Saved skills for '{profile_name}': {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                    )
                else:
                    self._engine.set_last_used_skills(selected_skill_names)
                    self._write_info(
                        f"Saved last-used skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                    )
            elif action == "reset":
                if profile_name and hasattr(self._engine, "reset_last_used_profile_skills"):
                    self._engine.reset_last_used_profile_skills(profile_name)
                else:
                    self._engine.reset_last_used_skills()
                active_skills = sorted(self._active_skill_name_set())
                if profile_name:
                    self._write_info(
                        f"Reset skills for '{profile_name}': {', '.join(active_skills) if active_skills else 'none'}."
                    )
                else:
                    self._write_info(f"Reset skills to defaults: {', '.join(active_skills) if active_skills else 'none'}.")
            elif action == "save_default":
                if profile_name and hasattr(self._engine, "set_last_used_profile_skills"):
                    self._engine.set_last_used_profile_skills(profile_name, selected_skill_names)
                else:
                    self._engine.set_last_used_skills(selected_skill_names)
                self._engine.save_default_skills(selected_skill_names)
                self._write_info(
                    f"Saved default skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                )
            self._commit_engine_ui_update(refresh_suggestions=True)

        self._present_tool_selection_modal(
            title="Select Skills",
            tools=tuple(picker_options),
            selected_values=selected_values,
            help_text=(
                "Apply saves skills for the active profile when one is selected. "
                "Reset restores that profile's fallback skills. "
                "Save as Default writes the default skill set to pocketcode.yml."
            ),
            empty_message="No matching skills.",
            filter_placeholder="Filter skills...",
            grouped_values=grouped_values,
            on_submit=_handle_selection,
        )
