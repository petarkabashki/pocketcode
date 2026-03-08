from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from .shared import PickerOption


class TextualAppControlCenterMixin:
    def _asset_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        session_default = self._engine.session_confirmation_overrides.get("default_policy") or "inherit"
        active_skill_names = tuple(
            str(getattr(skill, "name", skill))
            for skill in (
                self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else []
            )
        )
        available_skill_count = len(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else 0
        preset_count = len(self._engine.list_textual_selection_presets()) if hasattr(
            self._engine, "list_textual_selection_presets"
        ) else 0
        saved_sessions = self._engine.list_saved_sessions() if hasattr(self._engine, "list_saved_sessions") else []
        active_session = self._engine.get_active_session_info() if hasattr(self._engine, "get_active_session_info") else {}
        return (
            PickerOption(
                value="profile",
                label=f"Agent: {active_profile.name if active_profile else 'none'}",
                description="Switch, edit, clone, or delete the active agent profile",
                search_text="agent profile active edit clone delete",
            ),
            PickerOption(
                value="mode",
                label=f"Mode: {active_mode.name if active_mode else 'none'}",
                description="Switch, clear, edit, clone, or delete a mode",
                search_text="mode preset switch clear edit clone delete",
            ),
            PickerOption(
                value="llm",
                label=f"LLM: {self._engine.global_llm_override or 'inherit'}",
                description="Switch, edit, clone, or delete the active LLM profile",
                search_text="llm model profile override edit clone delete",
            ),
            PickerOption(
                value="skills",
                label=(
                    f"Skills: {', '.join(active_skill_names)}"
                    if active_skill_names
                    else f"Skills: none ({available_skill_count} available)"
                ),
                description="Enable or disable runtime skills",
                search_text="skills capability packs selection",
            ),
            PickerOption(
                value="tools",
                label=f"Tools: {active_profile.name if active_profile else 'none'}",
                description="Edit the active agent tool allowlist",
                search_text="tools allowlist selection groups",
            ),
            PickerOption(
                value="tool_policies",
                label=f"Tool Policies: {active_profile.name if active_profile else 'none'}",
                description="Edit per-tool confirmation overrides",
                search_text="tool policy confirmation overrides",
            ),
            PickerOption(
                value="presets",
                label=f"Selection Presets: {preset_count}",
                description="Save, load, or delete whole selection snapshots",
                search_text="selection preset snapshot save load delete",
            ),
            PickerOption(
                value="session_confirm",
                label=f"Session confirmation: {session_default}",
                description="Set the default session confirmation policy",
                search_text="session confirm tool policy",
            ),
            PickerOption(
                value="sessions",
                label=(
                    f"Sessions: {active_session.get('title')}"
                    if isinstance(active_session, dict) and active_session.get("title")
                    else f"Sessions: {len(saved_sessions)} saved"
                ),
                description="Start a new session or resume saved workspace history",
                search_text="sessions history resume new",
            ),
            PickerOption(
                value="system_settings",
                label="System Settings",
                description="Theme, workspace view, and default agent/LLM saved to pocketcode.yml",
                search_text="system settings theme workspace view default agent llm config save",
            ),
        )

    def _open_asset_picker(self) -> None:
        self._show_picker(
            title="Control Center",
            options=self._asset_category_options(),
            current_value=None,
            on_select=self._handle_asset_picker_selection,
            help_text="Choose a category, then drill into the action you want.",
        )

    def _handle_asset_picker_selection(self, selected_value: str) -> None:
        options = self._asset_action_options(selected_value)
        if not options:
            self._write_error(f"Unsupported asset picker target: {selected_value}")
            return
        self.call_after_refresh(lambda: self._open_asset_action_picker(selected_value, options))

    def _asset_action_options(self, category: str) -> tuple[PickerOption, ...]:
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if category == "profile":
            return (
                PickerOption("select", "Switch Active Profile", search_text="select switch active profile"),
                PickerOption("edit", "Edit Current Profile", search_text="edit agent profile yaml"),
                PickerOption("clone", "Clone Current Profile", search_text="clone agent profile workspace"),
                PickerOption("delete", "Delete Current Profile", search_text="delete remove workspace agent"),
            )
        if category == "mode":
            options = [
                PickerOption("select", "Switch Active Mode", search_text="select switch mode"),
                PickerOption("edit", "Edit Current Mode", search_text="edit mode markdown"),
                PickerOption("clone", "Clone Current Mode", search_text="clone mode"),
                PickerOption("delete", "Delete Current Mode", search_text="delete remove mode"),
            ]
            if active_mode is not None:
                options.insert(1, PickerOption("clear", "Clear Active Mode", search_text="clear reset active mode"))
            return tuple(options)
        if category == "llm":
            return (
                PickerOption("select", "Switch Global LLM", search_text="select switch llm"),
                PickerOption("edit", "Edit Current LLM", search_text="edit llm profile yaml"),
                PickerOption("clone", "Clone Current LLM", search_text="clone llm profile"),
                PickerOption("delete", "Delete Current LLM", search_text="delete remove workspace llm profile"),
            )
        if category == "skills":
            return (PickerOption("select", "Select Skills", search_text="skills selection"),)
        if category == "tools":
            return (PickerOption("select", "Edit Allowed Tools", search_text="tool selection allowlist"),)
        if category == "tool_policies":
            return (PickerOption("edit", "Edit Tool Policies", search_text="tool policy overrides"),)
        if category == "presets":
            return (
                PickerOption("save", "Save Current as Preset", search_text="save current selection preset"),
                PickerOption("load", "Load Preset", search_text="load selection preset"),
                PickerOption("delete", "Delete Preset", search_text="delete selection preset"),
            )
        if category == "session_confirm":
            return (PickerOption("select", "Set Session Confirmation", search_text="session confirmation"),)
        if category == "sessions":
            return (
                PickerOption("new", "Start New Session", search_text="start new session"),
                PickerOption("resume", "Resume Saved Session", search_text="resume saved session history"),
                PickerOption("delete", "Delete Saved Session", search_text="delete saved session history"),
                PickerOption("clear_all", "Clear Previous Sessions", search_text="clear previous saved sessions"),
            )
        if category == "system_settings":
            return (PickerOption("open", "Open System Settings", search_text="system settings"),)
        return ()

    def _open_asset_action_picker(self, category: str, options: tuple[PickerOption, ...]) -> None:
        self._show_picker(
            title=f"{category.replace('_', ' ').title()} Actions",
            options=options,
            current_value=None,
            on_select=lambda action: self._handle_asset_action_selection(category, action),
            help_text="Choose the action to run for this category.",
        )

    def _handle_asset_action_selection(self, category: str, action: str) -> None:
        if category == "profile":
            if action == "select":
                self._open_profile_picker()
                return
            if action == "edit":
                self._open_agent_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone Agent Profile",
                    placeholder="my-agent-safe",
                    help_text="Enter the new workspace name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("agent", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("agent")
                return
        if category == "mode":
            if action == "select":
                self._open_mode_picker()
                return
            if action == "clear":
                self._set_active_mode_effect(None)
                self._write_info("Mode cleared.")
                self._commit_engine_ui_update()
                return
            if action == "edit":
                self._open_mode_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone Mode",
                    placeholder="review-copy",
                    help_text="Enter the new mode name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("mode", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("mode")
                return
        if category == "llm":
            if action == "select":
                self._open_llm_picker()
                return
            if action == "edit":
                self._open_llm_profile_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone LLM Profile",
                    placeholder="my-llm-profile",
                    help_text="Enter the new workspace name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("llm", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("llm")
                return
        if category == "skills" and action == "select":
            self._open_skill_selection_picker()
            return
        if category == "tools" and action == "select":
            self._open_tool_selection_picker()
            return
        if category == "tool_policies" and action == "edit":
            self._open_tool_policy_editor()
            return
        if category == "presets":
            if action == "save":
                self._open_name_prompt(
                    title="Save Selection Preset",
                    placeholder="review-session",
                    help_text="Enter the preset name.",
                    on_submit=self._save_selection_preset,
                )
                return
            if action == "load":
                self._open_selection_preset_picker("load")
                return
            if action == "delete":
                self._open_selection_preset_picker("delete")
                return
        if category == "session_confirm" and action == "select":
            self._open_session_confirmation_picker()
            return
        if category == "sessions":
            if action == "new":
                session = self._start_new_session_effect()
                self._write_info(f"Started new session: {session.get('session_id')}")
                self._commit_engine_ui_update()
                return
            if action == "resume":
                self._open_saved_session_picker()
                return
            if action == "delete":
                self._open_saved_session_picker(action="delete")
                return
            if action == "clear_all":
                self._confirm_clear_saved_sessions()
                return
        if category == "system_settings" and action == "open":
            self._open_system_settings_screen()
            return
        self._write_error(f"Unsupported {category} action: {action}")

    def _open_saved_session_picker(self, action: str = "resume") -> None:
        if not hasattr(self._engine, "list_saved_sessions"):
            self._write_error("This runtime does not support saved sessions.")
            return
        sessions = self._engine.list_saved_sessions()
        resumable = [item for item in sessions if item.get("is_resumable")]
        if not resumable:
            self._write_error("No saved sessions are available to resume.")
            return
        options = tuple(
            PickerOption(
                str(item.get("session_id") or ""),
                str(item.get("title") or item.get("session_id") or "Unnamed session"),
                description=str(item.get("updated_at") or ""),
                search_text="saved session history",
            )
            for item in resumable
        )
        self._show_picker(
            title="Resume Saved Session" if action == "resume" else "Delete Saved Session",
            options=options,
            current_value=None,
            on_select=self._resume_saved_session if action == "resume" else self._confirm_delete_saved_session,
            help_text=(
                "Choose a saved session to resume."
                if action == "resume"
                else "Choose a saved session to delete."
            ),
            empty_message="No saved sessions are available.",
        )

    def _resume_saved_session(self, session_id: str) -> None:
        session = self._resume_saved_session_effect(session_id)
        self._write_info(f"Resumed session: {session.get('session_id')}")

    def _confirm_delete_saved_session(self, session_id: str) -> None:
        self._show_picker(
            title="Delete Saved Session",
            options=(
                PickerOption("delete", f"Delete {session_id}", search_text="confirm delete"),
                PickerOption("cancel", "Cancel"),
            ),
            current_value=None,
            on_select=lambda value: self._delete_saved_session(session_id) if value == "delete" else None,
            help_text="Delete the selected saved session. The active session is protected.",
        )

    def _delete_saved_session(self, session_id: str) -> None:
        deleted = self._delete_saved_session_effect(session_id)
        self._write_info(f"Deleted session: {deleted.get('session_id')}")

    def _confirm_clear_saved_sessions(self) -> None:
        self._show_picker(
            title="Clear Previous Sessions",
            options=(
                PickerOption("clear", "Clear previous sessions", search_text="confirm clear sessions"),
                PickerOption("cancel", "Cancel"),
            ),
            current_value=None,
            on_select=lambda value: self._clear_saved_sessions() if value == "clear" else None,
            help_text="Remove all saved sessions except the active one.",
        )

    def _clear_saved_sessions(self) -> None:
        removed = self._clear_saved_sessions_effect()
        self._write_info(f"Cleared {removed} saved session{'s' if removed != 1 else ''}.")
