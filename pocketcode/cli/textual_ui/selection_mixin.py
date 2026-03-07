from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from .editor_screens import SystemSettingsScreen
from .shared import INHERIT_POLICY, NO_LLM, NO_MODE, PickerOption, THEME_OPTIONS, WORKSPACE_MODES


class TextualAppSelectionMixin:
    def _open_profile_picker(self) -> None:
        profile_names = tuple(dict.fromkeys(self._profile_cycle()))
        active_profile = self._engine.active_agent_profile
        options: list[PickerOption] = []
        for profile_name in profile_names:
            profile = None
            try:
                if hasattr(self._engine, "get_agent"):
                    profile = self._engine.get_agent(profile_name)
                elif hasattr(self._engine, "get_agent_profile"):
                    profile = self._engine.get_agent_profile(profile_name)
            except Exception:
                profile = None
            description_parts = [
                str(getattr(profile, "agent", "") or ""),
                str(getattr(profile, "source", "") or ""),
            ]
            description = " | ".join(part for part in description_parts if part)
            options.append(
                PickerOption(
                    profile_name,
                    profile_name,
                    description=description,
                    search_text=getattr(profile, "agent", "") if profile is not None else "",
                )
            )
        self._show_picker(
            title="Select Active Agent Profile",
            options=options,
            current_value=active_profile.name if active_profile is not None else None,
            on_select=self._apply_profile_selection,
            help_text="Choose the active agent profile.",
            empty_message="No agent profiles are available.",
        )

    def _open_mode_picker(self) -> None:
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        options = [PickerOption(NO_MODE, "(clear)", "Disable the active mode")]
        options.extend(PickerOption(name, name) for name in self._engine.list_modes())
        self._show_picker(
            title="Select Active Mode",
            options=tuple(options),
            current_value=active_mode.name if active_mode is not None else NO_MODE,
            on_select=self._apply_mode_selection,
            help_text="Choose the active runtime mode. Clear falls back to the selected agent profile.",
            empty_message="No modes are available.",
        )

    def _open_llm_picker(self) -> None:
        self._show_picker(
            title="Select Global LLM Override",
            options=(PickerOption(NO_LLM, "Inherit", "Use the engine default"),)
            + tuple(PickerOption(name, name) for name in self._engine.list_llm_profiles()),
            current_value=self._engine.global_llm_override or NO_LLM,
            on_select=self._apply_llm_selection,
            help_text="Choose the active runtime LLM override. Inherit falls back to the default resolution chain.",
            empty_message="No LLM profiles are available.",
        )

    def _open_workspace_mode_picker(self) -> None:
        self._show_picker(
            title="Select Workspace Mode",
            options=tuple(
                PickerOption(mode_name, config["label"], f"View: {config['view']}")
                for mode_name, config in WORKSPACE_MODES.items()
            ),
            current_value=self._workspace_mode,
            on_select=self._apply_workspace_mode_selection,
            help_text="Choose a layout preset for the Textual workspace.",
        )

    def _open_theme_picker(self) -> None:
        self._show_picker(
            title="Select Theme",
            options=tuple(PickerOption(theme_name, theme_label) for theme_name, theme_label in THEME_OPTIONS.items()),
            current_value=self._theme_name,
            on_select=self._apply_theme_selection,
            help_text="Choose a theme preset for the Textual workspace.",
        )

    def _open_session_confirmation_picker(self) -> None:
        current_value = self._engine.session_confirmation_overrides.get("default_policy") or INHERIT_POLICY
        self._show_picker(
            title="Select Session Confirmation Default",
            options=(
                PickerOption(INHERIT_POLICY, "Inherit", "Use config or agent defaults"),
                PickerOption("allow", "Allow"),
                PickerOption("confirm", "Confirm"),
                PickerOption("deny", "Deny"),
            ),
            current_value=current_value,
            on_select=self._apply_session_confirmation_selection,
            help_text="Choose the default confirmation policy for tools in this session.",
        )

    def _apply_profile_selection(self, selected_value: str) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is not None and active_profile.name == selected_value:
            return
        if hasattr(self._engine, "set_last_used_active_profile"):
            self._engine.set_last_used_active_profile(selected_value)
        else:
            self._engine.set_active_agent_profile(selected_value)
        self._write_info(f"Activated agent profile: {selected_value}")

    def _apply_mode_selection(self, selected_value: str) -> None:
        target_mode = None if selected_value == NO_MODE else selected_value
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if active_mode is not None and target_mode == active_mode.name:
            return
        if active_mode is None and target_mode is None:
            return
        if hasattr(self._engine, "set_last_used_mode"):
            self._engine.set_last_used_mode(target_mode)
        else:
            self._engine.set_mode(target_mode)
        self._write_info(f"Mode: {target_mode or 'none'}")

    def _apply_llm_selection(self, selected_value: str) -> None:
        target_llm = None if selected_value == NO_LLM else selected_value
        if target_llm == self._engine.global_llm_override:
            return
        if hasattr(self._engine, "set_last_used_global_llm_profile"):
            self._engine.set_last_used_global_llm_profile(target_llm)
        else:
            self._engine.set_global_llm_override(target_llm)
        self._write_info(f"Global LLM override: {self._engine.global_llm_override or 'inherit'}")

    def _apply_workspace_mode_selection(self, selected_value: str) -> None:
        if selected_value == self._workspace_mode:
            return
        self._apply_workspace_mode(selected_value, announce=True)

    def _apply_theme_selection(self, selected_value: str) -> None:
        if selected_value == self._theme_name:
            return
        self._theme_name = selected_value
        self._write_info(f"Theme preset: {THEME_OPTIONS.get(selected_value, selected_value)}.")

    def _apply_session_confirmation_selection(self, selected_value: str) -> None:
        target_default = None if selected_value == INHERIT_POLICY else selected_value
        current_default = self._engine.session_confirmation_overrides.get("default_policy")
        if target_default == current_default:
            return
        if hasattr(self._engine, "set_last_used_session_confirmation_default"):
            self._engine.set_last_used_session_confirmation_default(target_default)
        else:
            self._engine.set_session_confirmation_default(target_default)
        self._write_info(
            f"Session confirmation default: "
            f"{self._engine.session_confirmation_overrides.get('default_policy') or 'inherit'}"
        )

    def _open_system_settings_screen(self) -> None:
        settings = (
            self._engine.get_system_settings()
            if hasattr(self._engine, "get_system_settings")
            else {
                "theme_name": self._theme_name,
                "workspace_mode": self._workspace_mode,
                "default_agent": None,
                "default_llm_profile": None,
            }
        )

        def _handle_submit(payload: dict[str, str | None] | None) -> None:
            if payload is None:
                return
            try:
                self._apply_system_settings(payload)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            SystemSettingsScreen(
                theme_name=str(settings.get("theme_name") or self._theme_name),
                workspace_mode=str(settings.get("workspace_mode") or self._workspace_mode),
                default_agent=str(settings.get("default_agent")) if settings.get("default_agent") else None,
                default_llm_profile=(
                    str(settings.get("default_llm_profile")) if settings.get("default_llm_profile") else None
                ),
                available_agents=self._engine.list_agents(),
                available_llm_profiles=self._engine.list_llm_profiles(),
            ),
            callback=_handle_submit,
        )

    def _apply_system_settings(self, payload: dict[str, str | None]) -> None:
        theme_name = str(payload.get("theme_name") or self._theme_name)
        workspace_mode = str(payload.get("workspace_mode") or self._workspace_mode)
        default_agent = str(payload.get("default_agent")) if payload.get("default_agent") else None
        default_llm_profile = str(payload.get("default_llm_profile")) if payload.get("default_llm_profile") else None

        if not hasattr(self._engine, "save_system_settings"):
            raise ValueError("This runtime does not support saving system settings.")

        config_path = self._engine.save_system_settings(
            theme_name=theme_name,
            workspace_mode=workspace_mode,
            default_agent=default_agent,
            default_llm_profile=default_llm_profile,
        )
        self._theme_name = theme_name
        self._apply_workspace_mode(workspace_mode, announce=False)
        if default_agent:
            self._engine.set_agent(default_agent)
        self._refresh_suggestions()
        self._write_info(f"Applied system settings and saved to {config_path}.")
