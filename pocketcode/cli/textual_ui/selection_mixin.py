from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from .editor_screens import SystemSettingsScreen
from .shared import INHERIT_POLICY, NO_LLM, NO_MODE, PickerOption, TEXTUAL_VIEWS, THEME_OPTIONS, WORKSPACE_VIEWS


class TextualAppSelectionMixin:
    def _open_view_picker(self) -> None:
        self._show_picker(
            title="Select View",
            options=tuple(
                PickerOption(view_name, config["label"], config["description"])
                for view_name, config in TEXTUAL_VIEWS.items()
            ),
            current_value=self._cli_state.current_view,
            on_select=self._apply_view_selection,
            help_text="Choose the active Textual view.",
        )

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

    def _open_workspace_view_picker(self) -> None:
        self._show_picker(
            title="Select Workspace View",
            options=tuple(
                PickerOption(mode_name, config["label"], f"View: {config['view']}")
                for mode_name, config in WORKSPACE_VIEWS.items()
            ),
            current_value=self._cli_state.workspace_view,
            on_select=self._apply_workspace_view_selection,
            help_text="Choose a layout preset for the Textual workspace.",
        )

    def _open_theme_picker(self) -> None:
        self._show_picker(
            title="Select Theme",
            options=tuple(PickerOption(theme_name, theme_label) for theme_name, theme_label in THEME_OPTIONS.items()),
            current_value=self._cli_state.theme_name,
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
        self._set_active_profile_effect(selected_value)
        self._write_info(f"Activated agent profile: {selected_value}")

    def _apply_mode_selection(self, selected_value: str) -> None:
        target_mode = None if selected_value == NO_MODE else selected_value
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if active_mode is not None and target_mode == active_mode.name:
            return
        if active_mode is None and target_mode is None:
            return
        self._set_active_mode_effect(target_mode)
        self._write_info(f"Mode: {target_mode or 'none'}")

    def _apply_llm_selection(self, selected_value: str) -> None:
        target_llm = None if selected_value == NO_LLM else selected_value
        if target_llm == self._engine.global_llm_override:
            return
        self._set_global_llm_override_effect(target_llm)
        self._write_info(f"Global LLM override: {self._engine.global_llm_override or 'inherit'}")

    def _apply_workspace_view_selection(self, selected_value: str) -> None:
        if selected_value == self._cli_state.workspace_view:
            return
        self._apply_workspace_view(selected_value, announce=True)

    def _apply_theme_selection(self, selected_value: str) -> None:
        if selected_value == self._cli_state.theme_name:
            return
        self._set_cli_theme_name(selected_value)
        self._write_info(f"Theme preset: {THEME_OPTIONS.get(selected_value, selected_value)}.")

    def _apply_session_confirmation_selection(self, selected_value: str) -> None:
        target_default = None if selected_value == INHERIT_POLICY else selected_value
        current_default = self._engine.session_confirmation_overrides.get("default_policy")
        if target_default == current_default:
            return
        self._set_session_confirmation_default_effect(target_default)
        self._write_info(
            f"Session confirmation default: "
            f"{self._engine.session_confirmation_overrides.get('default_policy') or 'inherit'}"
        )

    def _open_system_settings_screen(self) -> None:
        settings = (
            self._engine.get_system_settings()
            if hasattr(self._engine, "get_system_settings")
            else {
                "theme_name": self._cli_state.theme_name,
                "workspace_view": self._cli_state.workspace_view,
                "default_agent": None,
                "default_llm_profile": None,
            }
        )

        self._present_system_settings_modal(
            theme_name=str(settings.get("theme_name") or self._cli_state.theme_name),
            workspace_view=str(
                settings.get("workspace_view") or settings.get("workspace_mode") or self._cli_state.workspace_view
            ),
            default_agent=str(settings.get("default_agent")) if settings.get("default_agent") else None,
            default_llm_profile=(
                str(settings.get("default_llm_profile")) if settings.get("default_llm_profile") else None
            ),
            control_presentation=str(
                settings.get("control_presentation")
                or ("modal" if settings.get("user_input_popups") else getattr(self, "_control_presentation", "inline"))
            ),
            available_agents=self._engine.list_agents(),
            available_llm_profiles=self._engine.list_llm_profiles(),
            on_submit=self._apply_system_settings,
        )

    def _apply_system_settings(self, payload: dict[str, object]) -> None:
        theme_name = str(payload.get("theme_name") or self._cli_state.theme_name)
        workspace_view = str(
            payload.get("workspace_view") or payload.get("workspace_mode") or self._cli_state.workspace_view
        )
        default_agent = str(payload.get("default_agent")) if payload.get("default_agent") else None
        default_llm_profile = str(payload.get("default_llm_profile")) if payload.get("default_llm_profile") else None
        control_presentation = str(payload.get("control_presentation") or getattr(self, "_control_presentation", "inline"))

        config_path = self._save_system_settings_effect(
            theme_name=theme_name,
            workspace_view=workspace_view,
            default_agent=default_agent,
            default_llm_profile=default_llm_profile,
            control_presentation=control_presentation,
        )
        with self._batch_engine_ui_update(refresh_suggestions=True):
            self._set_cli_theme_name(theme_name)
            self._apply_workspace_view(workspace_view, announce=False)
            self._set_default_agent_effect(default_agent)
            self._control_presentation = "modal" if control_presentation == "modal" else "inline"
            if self._control_presentation == "modal":
                self._debugger_inline_breakpoint_visible = False
            self._write_info(f"Applied system settings and saved to {config_path}.")

    def _apply_view_selection(self, selected_value: str) -> None:
        self._set_current_view(selected_value, announce=True)
