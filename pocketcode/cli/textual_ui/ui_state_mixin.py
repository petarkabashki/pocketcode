from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from .selectors import (
    select_context_summary,
    select_inspector_summary_text,
    select_prompt_summary,
    select_run_preview_text,
    select_saved_sessions_summary,
)
from .shared import (
    INHERIT_POLICY,
    LOADING_OPTION,
    NO_LLM,
    PickerOption,
    SelectViewState,
    THEME_OPTIONS,
    TextualUIState,
    WORKSPACE_VIEWS,
    _build_header_agent_text,
    _build_header_llm_text,
    _build_view_title_text,
)


class TextualAppUiStateMixin:
    def _build_ui_state(self) -> TextualUIState:
        snapshot = self._cli_state.engine
        status = snapshot.status
        current_agent = snapshot.current_agent
        active_profile = snapshot.active_profile
        all_profile_names = tuple(dict.fromkeys(self._profile_cycle()))
        prompt_sources = tuple(self._engine.get_agent_prompt_sources(current_agent)) if current_agent else ()
        active_profile_name = active_profile.name if active_profile else None
        active_skill_names = snapshot.active_skill_names
        skill_picker_options, _, selected_skill_values = self._build_skill_picker_options(
            status.get("available_skills", []) or [],
            selected_skills=set(active_skill_names),
        )
        tool_picker_options: list[PickerOption] = []
        selected_tool_values: set[str] = set()
        if active_profile is None:
            tool_list_options = self._empty_tool_list_options()
        else:
            _, tool_picker_options, _, selected_tool_values = self._build_tool_picker_model(
                agent_name=current_agent,
                active_profile=active_profile,
            )
            tool_list_options = (
                self._selection_list_options_from_picker_options(
                    tool_picker_options,
                    selected_values=selected_tool_values,
                )
                if tool_picker_options
                else (("No tools available for this agent", LOADING_OPTION, False),)
            )

        llm_profile_names = tuple(str(name) for name in status.get("available_llm_profiles", []))
        session_default = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or INHERIT_POLICY

        profile_list_labels = tuple(
            f"{'* ' if active_profile_name == profile_name else '  '}{profile_name}"
            for profile_name in all_profile_names
        ) or ("No agent profiles available",)

        effective_llm_profile = (
            active_profile.llm_profile
            if active_profile is not None and active_profile.llm_profile
            else self._engine.global_llm_override or status.get("default_llm_profile") or "none"
        )
        status_for_display = dict(status)
        status_for_display.setdefault("selected_agent", active_profile_name or "none")
        status_for_display.setdefault("selected_llm_profile", effective_llm_profile)
        profile_select_options = (
            tuple((profile_name, profile_name) for profile_name in all_profile_names)
            if all_profile_names
            else (("No agent profiles available", LOADING_OPTION),)
        )

        return TextualUIState(
            theme_name=self._cli_state.theme_name,
            current_view=self._cli_state.current_view,
            right_panel_visible=self._cli_state.right_panel_visible,
            main_input_placeholder=self._runtime_state.main_input_placeholder,
            status_text="",
            header_agent_text=_build_header_agent_text(status_for_display),
            header_llm_text=_build_header_llm_text(status_for_display),
            view_title_text=_build_view_title_text(self._cli_state.current_view),
            workspace_view_select=SelectViewState(
                options=tuple((item["label"], key) for key, item in WORKSPACE_VIEWS.items()),
                value=self._cli_state.workspace_view,
            ),
            theme_select=SelectViewState(
                options=tuple((label, key) for key, label in THEME_OPTIONS.items()),
                value=self._cli_state.theme_name,
            ),
            profile_select=SelectViewState(
                options=profile_select_options,
                value=active_profile_name or LOADING_OPTION,
            ),
            llm_select=SelectViewState(
                options=(("(inherit)", NO_LLM),) + tuple((name, name) for name in llm_profile_names),
                value=self._engine.global_llm_override or NO_LLM,
            ),
            session_confirm_select=SelectViewState(
                options=(
                    ("inherit", INHERIT_POLICY),
                    ("allow", "allow"),
                    ("confirm", "confirm"),
                    ("deny", "deny"),
                ),
                value=session_default,
            ),
            auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            inspector_summary_text=select_inspector_summary_text(
                runtime_state=self._runtime_state,
                status=status,
                active_profile=active_profile,
                active_skill_names=active_skill_names,
                global_llm_override=self._engine.global_llm_override,
                auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            ),
            inspector_context_text=select_context_summary(status, self._cli_context),
            inspector_sessions_text=select_saved_sessions_summary(
                self._engine.list_saved_sessions() if hasattr(self._engine, "list_saved_sessions") else None
            ),
            skill_list_options=self._selection_list_options_from_picker_options(
                skill_picker_options,
                selected_values=selected_skill_values,
            )
            if skill_picker_options
            else (("No skills available", LOADING_OPTION, False),),
            tool_list_options=tool_list_options,
            inspector_prompts_text=select_prompt_summary(prompt_sources, active_profile),
            profile_list_names=all_profile_names,
            profile_list_labels=profile_list_labels,
            run_preview_text=select_run_preview_text(self._runtime_state, status),
        )