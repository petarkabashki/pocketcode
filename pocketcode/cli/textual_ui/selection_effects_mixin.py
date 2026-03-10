from __future__ import annotations


class TextualAppSelectionEffectsMixin:
    def _set_active_profile_effect(self, profile_name: str) -> None:
        if hasattr(self._engine, "set_last_used_active_profile"):
            self._engine.set_last_used_active_profile(profile_name)
        else:
            self._engine.set_active_agent_profile(profile_name)

    def _set_active_mode_effect(self, mode_name: str | None) -> None:
        if hasattr(self._engine, "set_last_used_mode"):
            self._engine.set_last_used_mode(mode_name)
        else:
            self._engine.set_mode(mode_name)

    def _set_global_llm_override_effect(self, profile_name: str | None) -> None:
        if hasattr(self._engine, "set_last_used_global_llm_profile"):
            self._engine.set_last_used_global_llm_profile(profile_name)
        else:
            self._engine.set_global_llm_override(profile_name)

    def _set_session_confirmation_default_effect(self, default_policy: str | None) -> None:
        if hasattr(self._engine, "set_last_used_session_confirmation_default"):
            self._engine.set_last_used_session_confirmation_default(default_policy)
        else:
            self._engine.set_session_confirmation_default(default_policy)

    def _save_system_settings_effect(
        self,
        *,
        theme_name: str,
        workspace_view: str,
        default_agent: str | None,
        default_llm_profile: str | None,
        control_presentation: str,
    ) -> str:
        if not hasattr(self._engine, "save_system_settings"):
            raise ValueError("This runtime does not support saving system settings.")
        return self._engine.save_system_settings(
            theme_name=theme_name,
            workspace_view=workspace_view,
            default_agent=default_agent,
            default_llm_profile=default_llm_profile,
            control_presentation=control_presentation,
        )

    def _set_default_agent_effect(self, agent_name: str | None) -> None:
        if agent_name:
            self._engine.set_agent(agent_name)

    def _clone_asset_effect(self, asset_name: str, new_name: str):
        if asset_name == "agent":
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                raise ValueError("No active agent to clone.")
            cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
            cloned = cloner(active_profile.name, new_name)
            self._engine.set_active_agent_profile(new_name)
            self._refresh_suggestions()
            return cloned

        if asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                raise ValueError("No active LLM profile to clone.")
            if not hasattr(self._engine, "clone_llm_profile"):
                raise ValueError("This runtime does not support cloning LLM profiles.")
            cloned = self._engine.clone_llm_profile(profile_name, new_name)
            self._engine.set_global_llm_override(new_name)
            self._refresh_suggestions()
            return cloned

        if asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                raise ValueError("No active mode to clone.")
            if not hasattr(self._engine, "clone_mode"):
                raise ValueError("This runtime does not support cloning modes.")
            target_path = self._engine.clone_mode(active_mode.name, new_name)
            self._set_active_mode_effect(new_name)
            self._refresh_suggestions()
            return target_path

        raise ValueError(f"Unsupported clone target: {asset_name}")

    def _clone_markdown_asset_effect(self, asset_kind: str, source_name: str, new_name: str):
        if not hasattr(self._engine, "clone_markdown_asset"):
            raise ValueError("This runtime does not support cloning markdown assets.")
        cloned = self._engine.clone_markdown_asset(asset_kind, source_name, new_name)
        self._refresh_suggestions()
        return cloned

    def _delete_asset_effect(self, asset_name: str):
        if asset_name == "agent":
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                raise ValueError("No active agent selected.")
            if not hasattr(self._engine, "delete_agent_profile"):
                raise ValueError("This runtime does not support deleting agent profiles.")
            target_path = self._engine.delete_agent_profile(active_profile.name)
            self._refresh_suggestions()
            return active_profile.name, target_path

        if asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                raise ValueError("No active LLM profile selected.")
            if not hasattr(self._engine, "delete_llm_profile"):
                raise ValueError("This runtime does not support deleting LLM profiles.")
            target_path = self._engine.delete_llm_profile(profile_name)
            self._refresh_suggestions()
            return profile_name, target_path

        if asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                raise ValueError("No active mode selected.")
            if not hasattr(self._engine, "delete_mode"):
                raise ValueError("This runtime does not support deleting modes.")
            target_path = self._engine.delete_mode(active_mode.name)
            self._refresh_suggestions()
            return active_mode.name, target_path

        raise ValueError(f"Unsupported delete target: {asset_name}")

    def _delete_markdown_asset_effect(self, asset_kind: str, asset_name: str):
        if not hasattr(self._engine, "delete_markdown_asset"):
            raise ValueError("This runtime does not support deleting markdown assets.")
        deleted = self._engine.delete_markdown_asset(asset_kind, asset_name)
        self._refresh_suggestions()
        return deleted

    def _update_markdown_asset_effect(self, asset_kind: str, asset_name: str, markdown_text: str):
        if not hasattr(self._engine, "update_markdown_asset"):
            raise ValueError("This runtime does not support editing markdown assets.")
        updated = self._engine.update_markdown_asset(asset_kind, asset_name, markdown_text=markdown_text)
        self._refresh_suggestions()
        return updated

    def _save_selection_preset_effect(self, preset_name: str) -> str:
        if not hasattr(self._engine, "save_textual_selection_preset"):
            raise ValueError("This runtime does not support selection presets.")
        return self._engine.save_textual_selection_preset(preset_name)

    def _apply_selection_preset_effect(self, preset_name: str) -> None:
        if not hasattr(self._engine, "apply_textual_selection_preset"):
            raise ValueError("This runtime does not support selection presets.")
        self._engine.apply_textual_selection_preset(preset_name)

    def _delete_selection_preset_effect(self, preset_name: str) -> None:
        if not hasattr(self._engine, "delete_textual_selection_preset"):
            raise ValueError("This runtime does not support selection presets.")
        self._engine.delete_textual_selection_preset(preset_name)

    def _start_new_session_effect(self):
        if not hasattr(self._engine, "start_new_session"):
            raise ValueError("This runtime does not support saved sessions.")
        return self._engine.start_new_session()

    def _resume_saved_session_effect(self, session_id: str):
        if not hasattr(self._engine, "resume_session"):
            raise ValueError("This runtime does not support saved sessions.")
        return self._engine.resume_session(session_id)

    def _delete_saved_session_effect(self, session_id: str):
        if not hasattr(self._engine, "delete_session"):
            raise ValueError("This runtime does not support saved sessions.")
        return self._engine.delete_session(session_id)

    def _clear_saved_sessions_effect(self) -> int:
        if not hasattr(self._engine, "clear_saved_sessions"):
            raise ValueError("This runtime does not support saved sessions.")
        return int(self._engine.clear_saved_sessions())

    def _get_saved_session_details_effect(self, session_id: str):
        if not hasattr(self._engine, "get_saved_session_details"):
            raise ValueError("This runtime does not support saved sessions.")
        return self._engine.get_saved_session_details(session_id)

    def _clear_saved_session_debugger_breakpoints_effect(self, session_id: str):
        if not hasattr(self._engine, "clear_saved_session_debugger_breakpoints"):
            raise ValueError("This runtime does not support saved sessions.")
        return self._engine.clear_saved_session_debugger_breakpoints(session_id)
