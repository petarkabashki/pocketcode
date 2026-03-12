from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

import re
from typing import Any, Callable

from .editor_screens import NameInputScreen, TextEditorScreen, ToolPolicyEditorScreen
from .shared import INHERIT_POLICY, PickerOption, _dump_yaml_text, _load_yaml_mapping


class TextualAppConfigEditingMixin:
    def _active_profile_policy_overrides(self, active_profile: Any) -> dict[str, str]:
        if not active_profile or not isinstance(active_profile.tool_confirmation, dict):
            return {}
        raw_overrides = active_profile.tool_confirmation.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            return {}
        return {
            str(tool_name): str(policy)
            for tool_name, policy in raw_overrides.items()
            if policy is not None
        }

    def _active_profile_default_confirmation(self, active_profile: Any) -> str | None:
        if not active_profile or not isinstance(active_profile.tool_confirmation, dict):
            return None
        value = active_profile.tool_confirmation.get("default")
        return str(value) if value else None

    def _suggest_workspace_agent_name(self, source_name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(source_name)).strip("-._")
        return f"{slug or 'agent'}-workspace"

    def _suggest_workspace_llm_name(self, source_name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(source_name)).strip("-._")
        return f"{slug or 'llm'}-workspace"

    def _ensure_workspace_agent_profile(self, *, action_label: str, on_ready: Callable[[str], None]) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent selected.")
            return
        if active_profile.source == "workspace":
            on_ready(active_profile.name)
            return
        self._open_name_prompt(
            title=f"Clone Agent Before {action_label.title()}",
            placeholder=self._suggest_workspace_agent_name(active_profile.name),
            help_text="This agent has no workspace YAML yet. Enter the workspace name / filename to clone it first.",
            on_submit=lambda value: self._clone_agent_for_edit(
                active_profile.name,
                value,
                action_label=action_label,
                on_ready=on_ready,
            ),
        )

    def _ensure_workspace_llm_profile(self, *, action_label: str, on_ready: Callable[[str], None]) -> None:
        profile_name = self._current_llm_profile_name()
        if not profile_name:
            self._write_error("No active LLM profile available to edit.")
            return
        profile = getattr(self._engine, "get_llm_profile", lambda name=None: None)(profile_name)
        if profile is None:
            self._write_error(f"Unknown LLM profile '{profile_name}'.")
            return
        if profile.get("source") == "workspace":
            on_ready(profile_name)
            return
        self._open_name_prompt(
            title=f"Clone LLM Before {action_label.title()}",
            placeholder=self._suggest_workspace_llm_name(profile_name),
            help_text="This LLM profile has no workspace YAML yet. Enter the workspace name / filename to clone it first.",
            on_submit=lambda value: self._clone_llm_for_edit(
                profile_name,
                value,
                action_label=action_label,
                on_ready=on_ready,
            ),
        )

    def _clone_agent_for_edit(
        self,
        source_name: str,
        new_name: str,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        cloned = self._clone_agent_for_edit_effect(source_name, new_name)
        target_path = getattr(cloned, "source_path", None)
        if target_path:
            self._write_info(f"Cloned agent '{source_name}' to {target_path} for {action_label}.")
        else:
            self._write_info(f"Cloned agent '{source_name}' to workspace agent '{new_name}' for {action_label}.")
        self.call_after_refresh(lambda: on_ready(new_name))

    def _clone_llm_for_edit(
        self,
        source_name: str,
        new_name: str,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        cloned = self._clone_llm_for_edit_effect(source_name, new_name)
        target_path = cloned.get("source_path") if isinstance(cloned, dict) else getattr(cloned, "source_path", None)
        if target_path:
            self._write_info(f"Cloned LLM profile '{source_name}' to {target_path} for {action_label}.")
        else:
            self._write_info(f"Cloned LLM profile '{source_name}' to workspace profile '{new_name}' for {action_label}.")
        self.call_after_refresh(lambda: on_ready(new_name))

    def _save_workspace_agent_profile(
        self,
        profile_name: str,
        *,
        llm_profile: str | None,
        tools: list[str] | None,
        extra_prompts: list[str],
        tool_confirmation_default: str | None,
        tool_confirmation_overrides: dict[str, str],
    ) -> None:
        self._save_workspace_agent_profile_effect(
            profile_name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=tool_confirmation_overrides,
        )
        self._commit_engine_ui_update()

    def _edit_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        llm_profile = self._current_llm_profile_name()
        flow_asset_count = len(self._engine.list_markdown_assets("flow")) if hasattr(self._engine, "list_markdown_assets") else 0
        tool_asset_count = len(self._engine.list_markdown_assets("tool")) if hasattr(self._engine, "list_markdown_assets") else 0
        return (
            PickerOption(
                "agent",
                f"Agent Config: {active_profile.name if active_profile else 'none'}",
                description="Edit active agent llm, prompts, and default confirmation",
                search_text="agent config llm prompts confirmation",
            ),
            PickerOption(
                "flow_asset",
                f"Flow Assets: {flow_asset_count}",
                description="Edit a workspace markdown flow asset",
                search_text="flow asset markdown edit workspace",
            ),
            PickerOption(
                "tool_asset",
                f"Tool Assets: {tool_asset_count}",
                description="Edit a workspace markdown tool asset",
                search_text="tool asset markdown edit workspace",
            ),
            PickerOption(
                "llm",
                f"LLM Config: {llm_profile or 'none'}",
                description="Edit the current LLM profile config",
                search_text="llm config provider model parameters",
            ),
            PickerOption(
                "tools",
                f"Tool Selection: {active_profile.name if active_profile else 'none'}",
                description="Edit the active agent tool allowlist",
                search_text="tool selection allowlist",
            ),
            PickerOption(
                "tool_policies",
                f"Tool Policies: {active_profile.name if active_profile else 'none'}",
                description="Edit per-tool confirmation overrides",
                search_text="tool policies overrides confirmation",
            ),
        )

    def _clone_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        llm_profile = self._current_llm_profile_name()
        flow_asset_count = len(self._engine.list_markdown_assets("flow")) if hasattr(self._engine, "list_markdown_assets") else 0
        tool_asset_count = len(self._engine.list_markdown_assets("tool")) if hasattr(self._engine, "list_markdown_assets") else 0
        return (
            PickerOption(
                "agent",
                f"Agent Config: {active_profile.name if active_profile else 'none'}",
                description="Clone the active agent profile into the workspace",
                search_text="clone agent profile workspace",
            ),
            PickerOption(
                "flow_asset",
                f"Flow Assets: {flow_asset_count}",
                description="Clone a workspace markdown flow asset",
                search_text="clone flow asset markdown workspace",
            ),
            PickerOption(
                "tool_asset",
                f"Tool Assets: {tool_asset_count}",
                description="Clone a workspace markdown tool asset",
                search_text="clone tool asset markdown workspace",
            ),
            PickerOption(
                "llm",
                f"LLM Config: {llm_profile or 'none'}",
                description="Clone the current LLM profile into the workspace",
                search_text="clone llm profile workspace",
            ),
        )

    def _open_edit_asset_picker(self) -> None:
        self._show_picker(
            title="Edit Asset",
            options=self._edit_category_options(),
            current_value=None,
            on_select=self._handle_edit_asset_selection,
            help_text="Choose which config asset to edit.",
        )

    def _open_clone_asset_picker(self) -> None:
        self._show_picker(
            title="Clone Asset",
            options=self._clone_category_options(),
            current_value=None,
            on_select=self._handle_clone_asset_selection,
            help_text="Choose which config asset to clone.",
        )

    def _open_name_prompt(
        self,
        *,
        title: str,
        placeholder: str,
        help_text: str,
        on_submit: Callable[[str], None],
    ) -> None:
        self._present_name_input_modal(
            title=title,
            placeholder=placeholder,
            help_text=help_text,
            on_submit=on_submit,
        )

    def _open_text_editor(
        self,
        *,
        title: str,
        help_text: str,
        initial_text: str,
        on_submit: Callable[[str], None],
    ) -> None:
        self._present_text_editor_modal(
            title=title,
            help_text=help_text,
            initial_text=initial_text,
            on_submit=on_submit,
        )

    def _handle_edit_asset_selection(self, selected_value: str) -> None:
        openers = {
            "agent": self._open_agent_editor,
            "flow_asset": self._open_markdown_flow_asset_editor,
            "tool_asset": self._open_markdown_tool_asset_editor,
            "llm": self._open_llm_profile_editor,
            "tools": self._open_tool_selection_picker,
            "tool_policies": self._open_tool_policy_editor,
        }
        opener = openers.get(selected_value)
        if opener is None:
            self._write_error(f"Unsupported edit target: {selected_value}")
            return
        self.call_after_refresh(opener)

    def _handle_clone_asset_selection(self, selected_value: str) -> None:
        placeholder = "new-name"
        if selected_value == "agent":
            placeholder = "my-agent-safe"
        elif selected_value == "flow_asset":
            self._open_markdown_asset_clone_picker("flow")
            return
        elif selected_value == "tool_asset":
            self._open_markdown_asset_clone_picker("tool")
            return
        elif selected_value == "llm":
            placeholder = "my-llm-profile"
        self._open_name_prompt(
            title=f"Clone {selected_value.replace('_', ' ').title()}",
            placeholder=placeholder,
            help_text="Enter the new workspace name / filename.",
            on_submit=lambda value: self._clone_selected_asset(selected_value, value),
        )

    def _open_agent_editor(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            self._ensure_workspace_agent_profile(
                action_label="editing agent settings",
                on_ready=self._open_agent_editor,
            )
            return
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        payload = {
            "llm_profile": active_profile.llm_profile,
            "extra_prompts": list(active_profile.extra_prompts),
            "tool_confirmation_default": self._active_profile_default_confirmation(active_profile),
        }
        self._open_text_editor(
            title=f"Edit Agent Config: {profile_name}",
            help_text="Edit llm_profile, extra_prompts, and tool_confirmation_default as YAML. Ctrl+S saves.",
            initial_text=_dump_yaml_text(payload),
            on_submit=lambda text: self._apply_agent_yaml_edit(profile_name, text),
        )

    def _apply_agent_yaml_edit(self, profile_name: str, text: str) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")

        data = _load_yaml_mapping(text, label="Agent config")
        allowed_keys = {"llm_profile", "extra_prompts", "tool_confirmation_default"}
        unexpected = sorted(set(data) - allowed_keys)
        if unexpected:
            raise ValueError(f"Unsupported agent config keys: {', '.join(unexpected)}")

        llm_value = data.get("llm_profile", active_profile.llm_profile)
        llm_profile = str(llm_value).strip() if llm_value not in {None, ""} else None

        prompts_value = data.get("extra_prompts", list(active_profile.extra_prompts))
        if prompts_value is None:
            extra_prompts: list[str] = []
        elif isinstance(prompts_value, list):
            extra_prompts = [str(item).strip() for item in prompts_value if str(item).strip()]
        else:
            raise ValueError("Agent config 'extra_prompts' must be a list.")

        default_value = data.get(
            "tool_confirmation_default",
            self._active_profile_default_confirmation(active_profile),
        )
        if default_value in {None, "", "inherit", INHERIT_POLICY}:
            tool_confirmation_default = None
        else:
            tool_confirmation_default = str(default_value).strip()
            if tool_confirmation_default not in {"allow", "confirm", "deny"}:
                raise ValueError("tool_confirmation_default must be allow, confirm, deny, or null.")

        tools = list(active_profile.tools) if active_profile.tools is not None else None
        overrides = self._active_profile_policy_overrides(active_profile)
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=overrides,
        )
        self._write_info(f"Saved workspace agent '{profile_name}'.")

    def _workspace_markdown_asset_options(self, asset_kind: str) -> tuple[PickerOption, ...]:
        if not hasattr(self._engine, "list_markdown_assets"):
            return ()
        names = self._engine.list_markdown_assets(asset_kind)
        return tuple(
            PickerOption(
                name,
                name,
                description=f"Workspace markdown {asset_kind} asset",
                search_text=f"{asset_kind} markdown asset workspace",
            )
            for name in names
        )

    def _open_markdown_asset_picker(
        self,
        *,
        asset_kind: str,
        title: str,
        help_text: str,
        on_select: Callable[[str], None],
    ) -> None:
        options = self._workspace_markdown_asset_options(asset_kind)
        if not options:
            self._write_error(f"No workspace markdown {asset_kind} assets are available.")
            return
        self._show_picker(
            title=title,
            options=options,
            current_value=None,
            on_select=on_select,
            help_text=help_text,
            empty_message=f"No workspace markdown {asset_kind} assets are available.",
        )

    def _open_markdown_flow_asset_editor(self, asset_name: str | None = None) -> None:
        if asset_name is None:
            self._open_markdown_asset_picker(
                asset_kind="flow",
                title="Edit Flow Asset",
                help_text="Choose a workspace markdown flow asset to edit.",
                on_select=self._open_markdown_flow_asset_editor,
            )
            return
        asset = self._engine.get_markdown_asset("flow", asset_name)
        self._open_text_editor(
            title=f"Edit Flow Asset: {asset_name}",
            help_text="Edit the flow markdown asset. Ctrl+S saves.",
            initial_text=asset["text"],
            on_submit=lambda text: self._apply_markdown_asset_edit("flow", asset_name, text),
        )

    def _open_markdown_tool_asset_editor(self, asset_name: str | None = None) -> None:
        if asset_name is None:
            self._open_markdown_asset_picker(
                asset_kind="tool",
                title="Edit Tool Asset",
                help_text="Choose a workspace markdown tool asset to edit.",
                on_select=self._open_markdown_tool_asset_editor,
            )
            return
        asset = self._engine.get_markdown_asset("tool", asset_name)
        self._open_text_editor(
            title=f"Edit Tool Asset: {asset_name}",
            help_text="Edit the tool markdown asset. Ctrl+S saves.",
            initial_text=asset["text"],
            on_submit=lambda text: self._apply_markdown_asset_edit("tool", asset_name, text),
        )

    def _apply_markdown_asset_edit(self, asset_kind: str, asset_name: str, text: str) -> None:
        updated = self._update_markdown_asset_effect(asset_kind, asset_name, text)
        self._write_info(f"Saved {asset_kind} asset '{asset_name}' to {updated['path']}.")

    def _open_llm_profile_editor(self) -> None:
        self._ensure_workspace_llm_profile(
            action_label="editing llm config",
            on_ready=self._open_workspace_llm_profile_editor,
        )

    def _open_workspace_llm_profile_editor(self, profile_name: str) -> None:
        profile = getattr(self._engine, "get_llm_profile", lambda name=None: None)(profile_name)
        if profile is None:
            self._write_error(f"Unknown LLM profile '{profile_name}'.")
            return
        self._open_text_editor(
            title=f"Edit LLM Config: {profile_name}",
            help_text="Edit provider, model, and parameters as YAML. Ctrl+S saves.",
            initial_text=_dump_yaml_text(profile.get("config", {})),
            on_submit=lambda text: self._apply_llm_yaml_edit(profile_name, text),
        )

    def _apply_llm_yaml_edit(self, profile_name: str, text: str) -> None:
        data = _load_yaml_mapping(text, label="LLM config")
        self._update_llm_profile_effect(profile_name, data)
        self._write_info(f"Saved workspace LLM profile '{profile_name}'.")

    def _open_tool_policy_editor(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            profile_name = active_profile.name
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        overrides = self._active_profile_policy_overrides(active_profile)
        initial_text = _dump_yaml_text(overrides) if overrides else "{}"

        def _handle_submit(payload: dict[str, str] | None) -> None:
            if payload is None:
                return
            action = payload.get("action")
            text = payload.get("text", "")
            try:
                if action == "apply":
                    overrides = self._parse_tool_policy_yaml(text)
                    self._set_profile_tool_policies_effect(profile_name, overrides)
                    self._write_info(f"Saved last-used tool confirmation overrides for '{profile_name}'.")
                elif action == "reset":
                    self._reset_profile_tool_policies_effect(profile_name)
                    self._write_info(f"Reset tool confirmation overrides for '{profile_name}' to defaults.")
                elif action == "save_default":
                    self._ensure_workspace_agent_profile(
                        action_label="saving tool policy defaults",
                        on_ready=lambda target_name: self._apply_tool_policy_yaml_edit(target_name, text),
                    )
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._commit_engine_ui_update()

        self._present_tool_policy_editor_modal(
            title=f"Edit Tool Policies: {profile_name}",
            help_text="Apply saves last-used overrides. Reset clears them. Save as Default writes the workspace agent YAML.",
            initial_text=initial_text,
            on_submit=_handle_submit,
        )

    def _parse_tool_policy_yaml(self, text: str) -> dict[str, str]:
        data = _load_yaml_mapping(text, label="Tool policy overrides")
        normalized: dict[str, str] = {}
        for tool_name, policy in data.items():
            if not str(tool_name).strip():
                raise ValueError("Tool policy keys must be non-empty strings.")
            policy_value = str(policy).strip()
            if policy_value not in {"allow", "confirm", "deny"}:
                raise ValueError("Tool policy values must be allow, confirm, or deny.")
            normalized[str(tool_name)] = policy_value
        return normalized

    def _apply_tool_policy_yaml_edit(self, profile_name: str, text: str) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized = self._parse_tool_policy_yaml(text)

        tools = list(active_profile.tools) if active_profile.tools is not None else None
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=active_profile.llm_profile,
            tools=tools,
            extra_prompts=list(active_profile.extra_prompts),
            tool_confirmation_default=self._active_profile_default_confirmation(active_profile),
            tool_confirmation_overrides=normalized,
        )
        self._reset_profile_tool_policy_defaults_effect(profile_name)
        self._write_info(f"Saved tool confirmation overrides for '{profile_name}'.")

    def _save_tool_selection_default(self, profile_name: str, tools: list[str] | None) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=active_profile.llm_profile,
            tools=tools,
            extra_prompts=list(active_profile.extra_prompts),
            tool_confirmation_default=self._active_profile_default_confirmation(active_profile),
            tool_confirmation_overrides=self._active_profile_policy_overrides(active_profile),
        )
        self._reset_profile_tool_defaults_effect(profile_name)
        self._write_info(
            f"Saved default tool allowlist for '{profile_name}': "
            f"{'all tools' if tools is None else f'{len(tools)} selected'}."
        )
