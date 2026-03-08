from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from typing import Any, Dict, Iterable

from pocketcode.cli.command_handler import _skill_group_name

from .shared import LOADING_OPTION, PickerOption, SKILL_GROUP_PREFIX, _tool_group_name


class TextualAppPickerModelMixin:
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

    def _empty_tool_list_options(self) -> tuple[tuple[str, str, bool], ...]:
        return (("No active agent profile selected", LOADING_OPTION, False),)