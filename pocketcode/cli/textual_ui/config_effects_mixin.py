from __future__ import annotations


class TextualAppConfigEffectsMixin:
    def _clone_agent_for_edit_effect(self, source_name: str, new_name: str):
        cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
        cloned = cloner(source_name, new_name)
        self._engine.set_active_agent_profile(new_name)
        self._refresh_suggestions()
        return cloned

    def _clone_llm_for_edit_effect(self, source_name: str, new_name: str):
        if not hasattr(self._engine, "clone_llm_profile"):
            raise ValueError("This runtime does not support cloning LLM profiles.")
        cloned = self._engine.clone_llm_profile(source_name, new_name)
        self._engine.set_global_llm_override(new_name)
        self._refresh_suggestions()
        return cloned

    def _save_workspace_agent_profile_effect(
        self,
        profile_name: str,
        *,
        llm_profile: str | None,
        tools: list[str] | None,
        extra_prompts: list[str],
        tool_confirmation_default: str | None,
        tool_confirmation_overrides: dict[str, str],
    ) -> None:
        updater = getattr(self._engine, "update_agent", None) or getattr(self._engine, "update_agent_profile")
        updater(
            profile_name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=tool_confirmation_overrides,
        )
        self._refresh_suggestions()

    def _update_mode_effect(self, mode_name: str, text: str):
        if not hasattr(self._engine, "update_mode"):
            raise ValueError("This runtime does not support editing modes.")
        target_path = self._engine.update_mode(mode_name, markdown_text=text)
        self._refresh_suggestions()
        return target_path

    def _update_llm_profile_effect(self, profile_name: str, profile_config: dict[str, object]) -> None:
        if not hasattr(self._engine, "update_llm_profile"):
            raise ValueError("This runtime does not support editing LLM profiles.")
        self._engine.update_llm_profile(profile_name, profile_config=profile_config)
        self._refresh_suggestions()

    def _set_profile_tool_policies_effect(self, profile_name: str, overrides: dict[str, str]) -> None:
        self._engine.set_last_used_profile_tool_policies(profile_name, overrides)

    def _reset_profile_tool_policies_effect(self, profile_name: str) -> None:
        self._engine.reset_last_used_profile_tool_policies(profile_name)

    def _reset_profile_tool_defaults_effect(self, profile_name: str) -> None:
        if hasattr(self._engine, "reset_last_used_profile_tools"):
            self._engine.reset_last_used_profile_tools(profile_name)

    def _reset_profile_tool_policy_defaults_effect(self, profile_name: str) -> None:
        if hasattr(self._engine, "reset_last_used_profile_tool_policies"):
            self._engine.reset_last_used_profile_tool_policies(profile_name)