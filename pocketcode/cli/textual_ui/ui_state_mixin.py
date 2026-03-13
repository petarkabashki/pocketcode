from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from .selectors import (
    select_context_blocks,
    select_context_summary,
    select_inspector_summary_blocks,
    select_inspector_summary_text,
    select_prompt_summary_blocks,
    select_prompt_summary,
    select_run_preview_blocks,
    select_run_preview_text,
    select_saved_sessions_blocks,
    select_saved_sessions_summary,
)
from .shared import (
    LOADING_OPTION,
    SelectViewState,
    TextualUIState,
    _build_header_agent_text,
    _build_header_llm_text,
    _build_navigation_status_text,
    _build_pointer_hint_text,
    _build_view_title_text,
)


class TextualAppUiStateMixin:
    def _build_navigation_status_text(self, *, status: dict, run_preview_blocks: tuple[Any, ...]) -> str:
        surface_id = getattr(self._cli_state, "focused_surface_id", None)
        if surface_id is None and hasattr(self, "_resolve_expansion_surface_id"):
            surface_id = self._resolve_expansion_surface_id()
        surface_blocks = self._surface_blocks(surface_id) if surface_id and hasattr(self, "_surface_blocks") else ()
        if surface_id == "run-preview":
            surface_blocks = run_preview_blocks
        compactable_indices = (
            self._surface_compactable_indices(surface_blocks)
            if surface_blocks and hasattr(self, "_surface_compactable_indices")
            else ()
        )
        selected_index = (
            self._resolve_selected_compactable_block_index(surface_id)
            if surface_id and hasattr(self, "_resolve_selected_compactable_block_index")
            else None
        )
        selected_position = None
        if selected_index in compactable_indices:
            selected_position = compactable_indices.index(int(selected_index)) + 1
        expanded = False
        if surface_id and selected_index is not None:
            expanded_refs = set(getattr(self._cli_state, "expanded_block_refs", ()))
            expanded = f"{surface_id}:{int(selected_index)}" in expanded_refs
        return _build_navigation_status_text(
            surface_id=surface_id,
            selected_position=selected_position,
            compactable_count=len(compactable_indices),
            expanded=expanded,
        )

    def _build_pointer_hint_text(self, *, run_preview_blocks: tuple[Any, ...]) -> str:
        surface_id = getattr(self._cli_state, "focused_surface_id", None)
        if surface_id is None and hasattr(self, "_resolve_expansion_surface_id"):
            surface_id = self._resolve_expansion_surface_id()
        surface_blocks = self._surface_blocks(surface_id) if surface_id and hasattr(self, "_surface_blocks") else ()
        if surface_id == "run-preview":
            surface_blocks = run_preview_blocks
        compactable_indices = (
            self._surface_compactable_indices(surface_blocks)
            if surface_blocks and hasattr(self, "_surface_compactable_indices")
            else ()
        )
        hovered_position = None
        hovered_ref = getattr(self._cli_state, "hovered_block_ref", None)
        if surface_id and hovered_ref and str(hovered_ref).startswith(f"{surface_id}:"):
            try:
                hovered_index = int(str(hovered_ref).split(":", 1)[1])
            except (TypeError, ValueError):
                hovered_index = None
            if hovered_index in compactable_indices:
                hovered_position = compactable_indices.index(int(hovered_index)) + 1
        return _build_pointer_hint_text(
            surface_id=surface_id,
            hovered_position=hovered_position,
            compactable_count=len(compactable_indices),
        )

    def _build_ui_state(self) -> TextualUIState:
        snapshot = self._cli_state.engine
        status = snapshot.status
        current_agent = snapshot.current_agent
        active_profile = snapshot.active_profile
        prompt_sources = tuple(self._engine.get_agent_prompt_sources(current_agent)) if current_agent else ()
        active_profile_name = active_profile.name if active_profile else None
        active_skill_names = snapshot.active_skill_names

        effective_llm_profile = (
            active_profile.llm_profile
            if active_profile is not None and active_profile.llm_profile
            else self._engine.global_llm_override or status.get("default_llm_profile") or "none"
        )
        status_for_display = dict(status)
        status_for_display.setdefault("selected_agent", active_profile_name or "none")
        status_for_display.setdefault("selected_llm_profile", effective_llm_profile)
        debugger_state = self._current_textual_debugger_state() if hasattr(self, "_current_textual_debugger_state") else None
        debugger_attached = bool(isinstance(debugger_state, dict) and debugger_state.get("attached"))
        debugger_paused = bool(isinstance(debugger_state, dict) and debugger_state.get("paused"))
        debugger_breakpoint_count = len(tuple(debugger_state.get("breakpoints", ()))) if isinstance(debugger_state, dict) else 0
        run_preview_blocks = select_run_preview_blocks(self._runtime_state, status, debugger_state=debugger_state)
        selected_debugger_breakpoint_id = (
            self._selected_textual_breakpoint_id(run_preview_blocks=run_preview_blocks)
            if hasattr(self, "_selected_textual_breakpoint_id")
            else None
        )

        return TextualUIState(
            theme_name=self._cli_state.theme_name,
            current_view=self._cli_state.current_view,
            right_panel_visible=self._cli_state.right_panel_visible,
            main_input_placeholder=self._runtime_state.main_input_placeholder,
            status_text=self._build_navigation_status_text(status=status, run_preview_blocks=run_preview_blocks),
            footer_hint_text=self._build_pointer_hint_text(run_preview_blocks=run_preview_blocks),
            header_agent_text=_build_header_agent_text(status_for_display),
            header_llm_text=_build_header_llm_text(status_for_display),
            view_title_text=_build_view_title_text(self._cli_state.current_view),
            debugger_attached=debugger_attached,
            debugger_paused=debugger_paused,
            debugger_breakpoint_count=debugger_breakpoint_count,
            selected_debugger_breakpoint_id=selected_debugger_breakpoint_id,
            debugger_inline_breakpoint_visible=bool(
                debugger_attached
                and getattr(self, "_control_presentation", "inline") == "inline"
                and getattr(self, "_debugger_inline_breakpoint_visible", False)
            ),
            debugger_inline_breakpoint_type=str(getattr(self, "_debugger_inline_breakpoint_type", "node")),
            debugger_inline_breakpoint_placeholder=str(
                getattr(self, "_debugger_inline_breakpoint_placeholder", "review_route")
            ),
            debugger_inline_breakpoint_help=str(
                getattr(self, "_debugger_inline_breakpoint_help", "Choose a breakpoint type and enter a target if required.")
            ),
            debugger_inline_breakpoint_value=str(getattr(self, "_debugger_inline_breakpoint_value", "")),
            inline_prompt_visible=bool(getattr(self, "_inline_prompt_visible", False)),
            inline_prompt_resolved=bool(getattr(self, "_inline_prompt_resolved", False)),
            inline_prompt_kind=str(getattr(self, "_inline_prompt_kind", "text")),
            inline_prompt_prompt=str(getattr(self, "_inline_prompt_prompt", "")),
            inline_prompt_help=str(getattr(self, "_inline_prompt_help", "")),
            inline_prompt_placeholder=str(getattr(self, "_inline_prompt_placeholder", "")),
            inline_prompt_submit_label=str(getattr(self, "_inline_prompt_submit_label", "Submit")),
            inline_prompt_text_value=str(getattr(self, "_inline_prompt_text_value", "")),
            inline_prompt_selected_value=str(getattr(self, "_inline_prompt_selected_value", "")),
            inline_prompt_selected_values=tuple(
                str(item) for item in getattr(self, "_inline_prompt_selected_values", ())
            ),
            inline_prompt_summary_text=str(getattr(self, "_inline_prompt_summary_text", "")),
            inline_prompt_select_options=tuple(
                (str(label), str(value))
                for label, value in getattr(self, "_inline_prompt_select_options", ())
            ),
            inline_prompt_checklist_options=tuple(
                (str(label), str(value), bool(selected))
                for label, value, selected in getattr(self, "_inline_prompt_checklist_options", ())
            ),
            workspace_view_select=SelectViewState(
                options=(("Unavailable", LOADING_OPTION),),
                value=LOADING_OPTION,
            ),
            theme_select=SelectViewState(
                options=(("Unavailable", LOADING_OPTION),),
                value=LOADING_OPTION,
            ),
            profile_select=SelectViewState(
                options=(("Unavailable", LOADING_OPTION),),
                value=LOADING_OPTION,
            ),
            llm_select=SelectViewState(
                options=(("Unavailable", LOADING_OPTION),),
                value=LOADING_OPTION,
            ),
            session_confirm_select=SelectViewState(
                options=(("Unavailable", LOADING_OPTION),),
                value=LOADING_OPTION,
            ),
            auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            inspector_summary_blocks=select_inspector_summary_blocks(
                runtime_state=self._runtime_state,
                status=status,
                active_profile=active_profile,
                active_skill_names=active_skill_names,
                global_llm_override=self._engine.global_llm_override,
                auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            ),
            inspector_summary_text=select_inspector_summary_text(
                runtime_state=self._runtime_state,
                status=status,
                active_profile=active_profile,
                active_skill_names=active_skill_names,
                global_llm_override=self._engine.global_llm_override,
                auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            ),
            inspector_context_blocks=select_context_blocks(status, self._cli_context),
            inspector_context_text=select_context_summary(status, self._cli_context),
            inspector_sessions_blocks=select_saved_sessions_blocks(
                self._engine.list_saved_sessions() if hasattr(self._engine, "list_saved_sessions") else None
            ),
            inspector_sessions_text=select_saved_sessions_summary(
                self._engine.list_saved_sessions() if hasattr(self._engine, "list_saved_sessions") else None
            ),
            skill_list_options=(),
            tool_list_options=(),
            inspector_prompt_blocks=select_prompt_summary_blocks(prompt_sources, active_profile),
            inspector_prompts_text=select_prompt_summary(prompt_sources, active_profile),
            profile_list_names=(),
            profile_list_labels=(),
            run_preview_blocks=run_preview_blocks,
            run_preview_text=select_run_preview_text(self._runtime_state, status, debugger_state=debugger_state),
        )
