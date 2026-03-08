from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from typing import Any, Callable, Dict, Iterable

from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, Select, SelectionList, Static, Switch, TextArea
from textual.widgets import ContentSwitcher

from pocketcode.cli.command_handler import _skill_group_name
from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import describe_interaction_request, interaction_placeholder

from .picker_screens import AssetPickerScreen
from .shared import (
    INHERIT_POLICY,
    LOADING_OPTION,
    MAX_OUTPUT_LINES,
    NO_LLM,
    PickerOption,
    SKILL_GROUP_PREFIX,
    SelectViewState,
    THEME_OPTIONS,
    TextualUIState,
    WORKSPACE_MODES,
    _build_header_agent_text,
    _build_header_llm_text,
    _build_output_text,
    _build_stats_text,
    _build_view_title_text,
    _tool_group_name,
    _trim_output_lines,
)


class TextualAppRenderingMixin:
    def _selection_list_options_from_picker_options(
        self,
        picker_options: Iterable[PickerOption],
        *,
        selected_values: set[str],
    ) -> tuple[tuple[str, str, bool], ...]:
        return tuple(
            (option.label, option.value, option.value in selected_values)
            for option in picker_options
        )

    def _render_profile_policy_summary(self, overrides: dict[str, str]) -> str:
        if not overrides:
            return "No per-tool confirmation overrides. Tools inherit the agent default."
        lines = ["Per-tool confirmation overrides:"]
        for tool_name in sorted(overrides):
            lines.append(f"- {tool_name}: {overrides[tool_name]}")
        return "\n".join(lines)

    def _current_llm_profile_name(self) -> str | None:
        status = self._engine.status()
        current = (
            status.get("selected_llm_profile")
            or status.get("global_llm_override")
            or status.get("default_llm_profile")
        )
        return str(current) if current else None

    def _build_skill_picker_options(
        self,
        skill_names: Iterable[str],
        *,
        selected_skills: set[str],
    ) -> tuple[list[PickerOption], dict[str, tuple[str, ...]], set[str]]:
        skill_groups = self._skill_group_members(skill_names)
        grouped_values = {
            self._skill_group_value(group_name): member_values
            for group_name, member_values in skill_groups.items()
        }
        picker_options: list[PickerOption] = []
        initial_selected_values = set(selected_skills)
        for group_name, member_values in skill_groups.items():
            group_value = self._skill_group_value(group_name)
            if member_values and all(member_value in selected_skills for member_value in member_values):
                initial_selected_values.add(group_value)
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
        return picker_options, grouped_values, initial_selected_values

    def _build_tool_picker_model(
        self,
        *,
        agent_name: str | None,
        active_profile: Any,
    ) -> tuple[tuple[str, ...], list[PickerOption], dict[str, tuple[str, ...]], set[str]]:
        if not agent_name or active_profile is None:
            return (), [], {}, set()
        available_tools = tuple(self._engine.list_tools_for_agent(agent_name))
        if not available_tools:
            return (), [], {}, set()
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
        return available_tools, picker_options, grouped_values, initial_selected_values

    def _build_ui_state(self) -> TextualUIState:
        status = self._engine.status()
        current_agent = self._engine.get_current_agent()
        active_profile = self._engine.active_agent_profile
        all_profile_names = tuple(dict.fromkeys(self._profile_cycle()))
        prompt_sources = tuple(self._engine.get_agent_prompt_sources(current_agent)) if current_agent else ()
        active_profile_name = active_profile.name if active_profile else None
        active_skill_names = tuple(
            str(getattr(skill, "name", skill))
            for skill in (
                self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else []
            )
        )
        skill_picker_options, _, selected_skill_values = self._build_skill_picker_options(
            status.get("available_skills", []) or [],
            selected_skills=set(active_skill_names),
        )
        tool_picker_options: list[PickerOption] = []
        selected_tool_values: set[str] = set()
        if active_profile is None:
            tool_list_options = (("No active agent profile selected", LOADING_OPTION, False),)
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
        summary_lines = [
            f"Agent: {active_profile_name or 'none'}",
            f"Internal flow: {status.get('runtime_flow') or 'internal-flow'}",
            f"Agent source: {active_profile.source if active_profile else '-'}",
            f"Global LLM: {self._engine.global_llm_override or 'inherit'}",
            f"Skills: {', '.join(active_skill_names) if active_skill_names else 'none'}",
            f"Auto-confirm: {'on' if self._engine.auto_confirm_tools else 'off'}",
            f"Session confirm: {session_default}",
            _build_stats_text(status),
        ]
        if active_profile and active_profile.description:
            summary_lines.append(f"Agent note: {active_profile.description}")
        active_session = status.get("active_session", {}) if isinstance(status, dict) else {}
        if isinstance(active_session, dict) and active_session.get("title"):
            summary_lines.append(
                f"Active session: {active_session.get('title')} ({active_session.get('session_id') or '-'})"
            )

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
            theme_name=self._theme_name,
            current_view=self._current_view,
            right_panel_visible=self._show_right_panel,
            status_text="",
            header_agent_text=_build_header_agent_text(status_for_display),
            header_llm_text=_build_header_llm_text(status_for_display),
            view_title_text=_build_view_title_text(self._current_view),
            workspace_mode_select=SelectViewState(
                options=tuple((item["label"], key) for key, item in WORKSPACE_MODES.items()),
                value=self._workspace_mode,
            ),
            theme_select=SelectViewState(
                options=tuple((label, key) for key, label in THEME_OPTIONS.items()),
                value=self._theme_name,
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
            inspector_summary_text="\n".join(summary_lines),
            inspector_context_text=self._render_context_summary(status),
            inspector_sessions_text=self._render_saved_sessions_summary(status),
            skill_list_options=self._selection_list_options_from_picker_options(
                skill_picker_options,
                selected_values=selected_skill_values,
            )
            if skill_picker_options
            else (("No skills available", LOADING_OPTION, False),),
            tool_list_options=tool_list_options,
            inspector_prompts_text=self._render_prompt_summary({"prompt_sources": list(prompt_sources)}, active_profile),
            profile_list_names=all_profile_names,
            profile_list_labels=profile_list_labels,
            run_preview_text=self._render_run_preview(status),
        )

    def _apply_theme_name(self, theme_name: str) -> None:
        for class_name in [f"theme-{name}" for name in THEME_OPTIONS]:
            self.screen.remove_class(class_name)
        self.screen.add_class(f"theme-{theme_name}")

    def _apply_panel_visibility(self, *, right_visible: bool) -> None:
        self.query_one("#right-panel", VerticalScroll).display = right_visible

    def _apply_view_state(self, view_name: str, view_title_text: str) -> None:
        self.query_one("#view-switcher", ContentSwitcher).current = f"view-{view_name}"
        title_widget = self.query_one("#view-title", Static)
        title_widget.display = bool(view_title_text)
        self._set_static_text(title_widget, view_title_text)

    def _apply_ui_state(self, state: TextualUIState) -> None:
        previous = self._ui_state
        if previous is None or previous.theme_name != state.theme_name:
            self._apply_theme_name(state.theme_name)
        if previous is None or previous.right_panel_visible != state.right_panel_visible:
            self._apply_panel_visibility(right_visible=state.right_panel_visible)
        if (
            previous is None
            or previous.current_view != state.current_view
            or previous.view_title_text != state.view_title_text
        ):
            self._apply_view_state(state.current_view, state.view_title_text)

        self._syncing_controls = True
        try:
            self._set_select_options(
                self.query_one("#workspace-mode-select", Select),
                state.workspace_mode_select.options,
                state.workspace_mode_select.value,
            )
            self._set_select_options(
                self.query_one("#theme-select", Select),
                state.theme_select.options,
                state.theme_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-select", Select),
                state.profile_select.options,
                state.profile_select.value,
            )
            self._set_select_options(
                self.query_one("#llm-select", Select),
                state.llm_select.options,
                state.llm_select.value,
            )
            self._set_select_options(
                self.query_one("#session-confirm-select", Select),
                state.session_confirm_select.options,
                state.session_confirm_select.value,
            )
            self.query_one("#auto-confirm-switch", Switch).value = state.auto_confirm_tools
        finally:
            self._syncing_controls = False

        self._profile_list_names = list(state.profile_list_names)
        self._set_option_list_labels(self.query_one("#profile-list", OptionList), state.profile_list_labels)
        self._set_selection_list_options(self.query_one("#skill-list", SelectionList), state.skill_list_options)
        self._set_selection_list_options(self.query_one("#inspector-tools", SelectionList), state.tool_list_options)
        self._set_static_text(self.query_one("#inspector-summary", Static), state.inspector_summary_text)
        self._set_text_area_text(self.query_one("#inspector-context", TextArea), state.inspector_context_text)
        self._set_text_area_text(self.query_one("#inspector-sessions", TextArea), state.inspector_sessions_text)
        self._set_text_area_text(self.query_one("#inspector-prompts", TextArea), state.inspector_prompts_text)
        self._set_text_area_text(self.query_one("#run-preview", TextArea), state.run_preview_text)

        self._ui_state = state

    def _refresh_ui(self) -> None:
        self._apply_ui_state(self._build_ui_state())

    def _write_info(self, text: str) -> None:
        self._append_output_line(f"info> {text}")

    def _write_error(self, text: str) -> None:
        self._append_output_line(f"error> {text}")

    def _write_user(self, text: str) -> None:
        self._append_output_line(f"you> {text}")

    def _write_assistant(self, text: str) -> None:
        self._append_output_line(f"assistant> {text}")
        self._last_assistant_response = text

    def _append_output_line(self, line: str) -> None:
        self._output_lines.append(line)
        output_widget = self.query_one("#output", TextArea)
        trimmed_lines, trimmed_now = _trim_output_lines(self._output_lines, MAX_OUTPUT_LINES)
        if trimmed_now:
            self._trimmed_output_line_count += trimmed_now
            self._output_lines = trimmed_lines
        text = _build_output_text(self._output_lines, self._trimmed_output_line_count)
        self._load_text_area_text(output_widget, text)
        output_widget.scroll_end(animate=False)

    def _apply_workspace_mode(self, mode_name: str, *, announce: bool) -> None:
        config = WORKSPACE_MODES.get(mode_name)
        if config is None:
            return
        self._workspace_mode = mode_name
        self._show_right_panel = bool(config["right"])
        self._current_view = str(config["view"])
        if announce:
            self._write_info(f"Workspace mode: {config['label']}.")

    def _render_context_preview(self) -> str:
        if not any(self._cli_context.values()):
            return "No context selected."

        lines: list[str] = []
        for label, key in (("Files", "files"), ("Folders", "folders"), ("URLs", "urls")):
            values = sorted(self._cli_context.get(key, set()) or set())
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {value}" for value in values)
        snippets = self._cli_context.get("snippets", {})
        if isinstance(snippets, dict) and snippets:
            lines.append("Snippets:")
            for name, content in sorted(snippets.items()):
                lines.append(f"- {name}: {content}")
        return "\n".join(lines)

    def _render_run_preview(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {})
        if not isinstance(run_summary, dict):
            run_summary = {}

        lines = [
            f"live_run_status: {self._live_run_status}",
            f"internal_flow: {status.get('runtime_flow') or 'internal-flow'}",
            f"active_agent: {status.get('agent') or 'auto'}",
            f"active_profile: {status.get('active_agent_profile') or 'none'}",
            f"global_llm_override: {status.get('global_llm_override') or 'none'}",
            f"agent_path: {run_summary.get('agent_path', [])}",
            f"current_llm_profile: {run_summary.get('current_llm_profile') or 'none'}",
            f"current_llm_model: {run_summary.get('current_llm_model') or '-'}",
            f"llm_usage: {run_summary.get('llm_usage', {})}",
            f"llm_cost_usd: {run_summary.get('llm_cost_usd', 0.0)}",
            f"context_stats: {run_summary.get('context_stats', {})}",
            f"session_confirmation: {status.get('session_tool_confirmation_overrides', {})}",
        ]
        if self._live_run_events:
            lines.append("live_events:")
            lines.extend(f"- {item}" for item in self._live_run_events[-8:])
        return "\n".join(lines)

    def _render_context_summary(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
        if not isinstance(context_stats, dict):
            context_stats = {}

        lines = [
            f"session_id: {status.get('active_session_id') or '-'}",
            f"session_title: {status.get('active_session_title') or '-'}",
            f"files: {context_stats.get('files', len(self._cli_context.get('files', set()) or set()))}",
            f"folders: {context_stats.get('folders', len(self._cli_context.get('folders', set()) or set()))}",
            f"urls: {context_stats.get('urls', len(self._cli_context.get('urls', set()) or set()))}",
            f"snippets: {context_stats.get('snippets', len(self._cli_context.get('snippets', {}) or {}))}",
            f"snippet_chars: {context_stats.get('snippet_chars', 0)}",
            "",
            self._render_context_preview(),
        ]
        return "\n".join(lines)

    def _render_saved_sessions_summary(self, status: Dict[str, Any]) -> str:
        if not hasattr(self._engine, "list_saved_sessions"):
            return "Saved session history is unavailable."
        sessions = self._engine.list_saved_sessions()
        if not sessions:
            return "No saved sessions."
        lines: list[str] = []
        for item in sessions[:8]:
            marker = "*" if item.get("is_active") else "-"
            lines.append(
                f"{marker} {item.get('title') or '-'} | {item.get('session_id') or '-'} | {item.get('updated_at') or '-'}"
            )
        if len(sessions) > 8:
            lines.append(f"... {len(sessions) - 8} more")
        return "\n".join(lines)

    def _render_prompt_summary(self, agent_meta: Dict[str, Any], active_profile: Any) -> str:
        agent_prompts = agent_meta.get("prompt_sources", []) if isinstance(agent_meta, dict) else []
        extra_prompts = list(active_profile.extra_prompts) if active_profile else []
        lines: list[str] = []
        if agent_prompts:
            lines.append("Agent prompt sources:")
            lines.extend(f"- {path}" for path in agent_prompts)
        if extra_prompts:
            lines.append("Profile extra prompts:")
            lines.extend(f"- {path}" for path in extra_prompts)
        if not lines:
            return "No prompt sources registered."
        return "\n".join(lines)

    def _skill_group_value(self, group_name: str) -> str:
        return f"{SKILL_GROUP_PREFIX}{group_name}"

    def _is_skill_group_value(self, value: str) -> bool:
        return str(value).startswith(SKILL_GROUP_PREFIX)

    def _skill_group_members(self, skill_names: Iterable[str]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for skill_name in sorted({str(name) for name in skill_names}):
            grouped.setdefault(_skill_group_name(skill_name), []).append(skill_name)
        return {group_name: tuple(grouped[group_name]) for group_name in sorted(grouped)}

    def _tool_group_path(self, tool_name: str, tool_detail: Dict[str, Any] | None = None) -> tuple[str, ...]:
        if isinstance(tool_detail, dict):
            raw_group_path = tool_detail.get("group_path")
            if isinstance(raw_group_path, (list, tuple)):
                normalized = tuple(str(part).strip() for part in raw_group_path if str(part).strip())
                if normalized:
                    return normalized
        return (_tool_group_name(tool_name),)

    def _build_nested_tool_picker_options(
        self,
        tool_names: Iterable[str],
        *,
        selected_tools: set[str],
        tool_details: dict[str, Dict[str, Any]] | None = None,
    ) -> tuple[list[PickerOption], dict[str, tuple[str, ...]], set[str]]:
        grouped_values_by_path: dict[tuple[str, ...], list[str]] = {}
        child_groups: dict[tuple[str, ...], set[str]] = {}
        leaf_tools: dict[tuple[str, ...], list[str]] = {}

        for tool_name in sorted({str(name) for name in tool_names}):
            group_path = self._tool_group_path(tool_name, (tool_details or {}).get(tool_name))
            leaf_tools.setdefault(group_path, []).append(tool_name)
            for depth in range(1, len(group_path) + 1):
                prefix = group_path[:depth]
                grouped_values_by_path.setdefault(prefix, []).append(tool_name)
                parent = group_path[: depth - 1]
                child_groups.setdefault(parent, set()).add(group_path[depth - 1])

        picker_options: list[PickerOption] = []
        grouped_values: dict[str, tuple[str, ...]] = {}
        initial_selected_values = set(selected_tools)

        def _append_group(path: tuple[str, ...], depth: int) -> None:
            member_values = tuple(sorted(dict.fromkeys(grouped_values_by_path.get(path, []))))
            if not member_values:
                return
            group_value = self._skill_group_value("/".join(path))
            grouped_values[group_value] = member_values
            if all(member_value in selected_tools for member_value in member_values):
                initial_selected_values.add(group_value)
            group_label = f"{'  ' * depth}Group: {path[-1]}"
            group_search = " ".join(path)
            picker_options.append(
                PickerOption(
                    group_value,
                    group_label,
                    description=f"Toggle all {len(member_values)} tools in {' / '.join(path)}",
                    search_text=f"{group_search} group {' '.join(member_values)}",
                )
            )
            for child_name in sorted(child_groups.get(path, set())):
                _append_group(path + (child_name,), depth + 1)
            for member_value in sorted(leaf_tools.get(path, [])):
                picker_options.append(
                    PickerOption(
                        member_value,
                        f"{'  ' * (depth + 1)}{member_value}",
                        description=f"Group: {' / '.join(path)}",
                        search_text=f"{member_value} {group_search}",
                    )
                )

        for group_name in sorted(child_groups.get((), set())):
            _append_group((group_name,), 0)

        return picker_options, grouped_values, initial_selected_values

    def _active_skill_name_set(self) -> set[str]:
        return {
            str(getattr(skill, "name", skill))
            for skill in (self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else [])
        }

    def _set_select_options(self, widget: Select, options: Iterable[tuple[str, str]], value: str) -> None:
        option_list = [(str(label), str(option_value)) for label, option_value in options]
        cache_key = widget.id or ""
        option_tuple = tuple(option_list)
        if self._select_state_cache.get(cache_key) == (option_tuple, value):
            return
        widget.set_options(option_list)
        try:
            widget.value = value
        except Exception:
            if option_list:
                widget.value = option_list[0][1]
                value = option_list[0][1]
        self._select_state_cache[cache_key] = (option_tuple, value)

    def _set_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.text = text
        self._text_state_cache[cache_key] = text

    def _load_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.load_text(text)
        self._text_state_cache[cache_key] = text

    def _set_static_text(self, widget: Static, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.update(text)
        self._text_state_cache[cache_key] = text

    def _set_option_list_labels(self, widget: OptionList, labels: Iterable[str]) -> None:
        option_tuple = tuple(str(label) for label in labels)
        cache_key = widget.id or ""
        if self._option_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        self._option_list_state_cache[cache_key] = option_tuple

    def _set_selection_list_options(
        self,
        widget: SelectionList,
        options: Iterable[tuple[str, str, bool]],
    ) -> None:
        option_tuple = tuple((str(label), str(value), bool(selected)) for label, value, selected in options)
        cache_key = widget.id or ""
        if self._selection_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        widget.disabled = len(option_tuple) == 1 and option_tuple[0][1] == LOADING_OPTION
        self._selection_list_state_cache[cache_key] = option_tuple

    def _sync_ui_from_engine(self) -> None:
        self._refresh_ui()

    def _set_main_input_placeholder(self, prompt: str | None = None) -> None:
        input_widget = self.query_one("#main-input", Input)
        input_widget.placeholder = prompt or "Type a request or /command. F1 chat F3 edit F4 clone F5 run F6 control"

    def _profile_cycle(self) -> list[str]:
        profile_names: list[str] = []
        for agent_name in self._engine.list_agents():
            profile_names.extend(self._engine.list_agent_profiles(agent_name))
        return profile_names

    def _remember_run_event(self, text: str) -> None:
        self._live_run_events.append(text)
        if len(self._live_run_events) > 25:
            self._live_run_events = self._live_run_events[-25:]

    def _drain_run_events(self) -> None:
        if self._active_run is None:
            return
        events = self._active_run.drain_events() or []
        if not events:
            return
        should_refresh = False
        for event in events:
            should_refresh = self._consume_run_event(event) or should_refresh
        if should_refresh:
            self._refresh_ui()

    def _consume_run_event(self, event: Dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "")
        message = self._format_runtime_event(event)
        if message:
            self._remember_run_event(message)
            self._write_info(message)

        if event_type == "interaction_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(interaction_placeholder(event))
            if event.get("kind") != "text":
                self._write_info(describe_interaction_request(event))
            return True
        if event_type == "interaction_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "user_input_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(str(event.get("prompt") or "Provide input"))
            return True
        if event_type == "user_input_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "run_completed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._write_assistant(str(event.get("output") or ""))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_failed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "failed"
            self._set_main_input_placeholder()
            self._write_error(str(event.get("error") or "Request failed."))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_cancelled":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._sync_ui_from_engine()
            return False
        if event_type in {"run_started", "agent_turn_started", "llm_call_started", "tool_started", "handoff"}:
            self._live_run_status = "running"
        if event_type == "run_cancel_requested":
            self._live_run_status = "stopping"
        return True

    def _format_runtime_event(self, event: Dict[str, Any]) -> str:
        return format_runtime_event(event)

    def _show_picker(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None,
        on_select: Callable[[str], None],
        help_text: str = "Use arrows to move, Enter to select, Esc to close.",
        empty_message: str = "No matching options.",
    ) -> None:
        option_list = tuple(options)
        if not option_list:
            self._write_error(f"No options available for {title.lower()}.")
            return

        def _handle_selection(selected_value: str | None) -> None:
            if selected_value is None:
                return
            try:
                on_select(selected_value)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            AssetPickerScreen(
                title=title,
                options=option_list,
                current_value=current_value,
                help_text=help_text,
                empty_message=empty_message,
            ),
            callback=_handle_selection,
        )
