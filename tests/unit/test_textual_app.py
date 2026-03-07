from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pocketcode.cli.textual_app import (
    AssetPickerScreen,
    NameInputScreen,
    PocketCodeTextualApp,
    SystemSettingsScreen,
    TextEditorScreen,
    ToolPolicyEditorScreen,
    ToolSelectionScreen,
    _build_header_agent_text,
    _build_header_llm_text,
    _build_output_text,
    _build_profile_editor_hint,
    _build_stats_text,
    _build_status_text,
    _build_view_title_text,
    _trim_output_lines,
)
from textual.widgets import Input, SelectionList, Static


class TestTopStatsText:
    def test_stats_text_shows_runtime_counters_without_repeating_agent(self):
        status = {
            "agent": "core::react",
            "session_tool_confirmation_overrides": {"default_policy": "confirm"},
            "last_run_summary": {
                "current_agent": "core::reviewer",
                "llm_usage": {
                    "prompt_tokens": 128,
                    "completion_tokens": 64,
                    "total_tokens": 192,
                },
                "llm_cost_usd": 0.012345,
            },
        }

        text = _build_stats_text(status)

        assert text == "Tokens in=128 out=64 total=192 | Cost=$0.012345 | Session confirm=confirm"
        assert "Agent=" not in text
        assert "core::react" not in text
        assert "core::reviewer" not in text

    def test_stats_text_defaults_when_run_summary_is_missing(self):
        status = {}

        text = _build_stats_text(status)

        assert text == "Tokens in=0 out=0 total=0 | Cost=$0.000000 | Session confirm=inherit"


class TestUiTextHelpers:
    def test_status_text_matches_footer_format(self):
        status = {
            "flow": "coder::coder",
            "agent": "coder.safe",
            "selected_agent": "coder.safe",
            "active_agent": "coder.safe",
            "active_agent_profile": "coder.safe",
            "global_llm_override": "fast",
            "selected_flow": "architect::architect",
            "selected_llm_profile": "smart",
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_agent": "coder::coder",
                "current_llm_profile": "fast",
                "current_llm_model": "gpt-test",
                "agent_path": [],
            },
        }

        text = _build_status_text(status, "control")

        assert "Runtime flow: internal-flow" in text
        assert "Agent: coder.safe" in text
        assert "LLM: smart (-)" in text
        assert "Flow:" not in text

    def test_header_text_splits_summary_agent_and_llm(self):
        status = {
            "selected_agent": "coder.safe",
            "selected_llm_profile": "smart",
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_llm_profile": "smart",
                "current_llm_model": "gpt-test",
            },
        }

        assert _build_header_agent_text(status) == "Agent: coder.safe"
        assert _build_header_llm_text(status) == "LLM: smart (gpt-test)"

    def test_view_title_text_matches_named_view(self):
        assert _build_view_title_text("run") == "Run Inspector"
        assert _build_view_title_text("chat") == ""

    def test_profile_editor_hint_tracks_profile_source(self):
        workspace_profile = SimpleNamespace(name="coder.safe", source="workspace")
        plugin_profile = SimpleNamespace(name="coder.default", source="plugin")

        assert _build_profile_editor_hint(None) == "Select an agent to edit agent settings."
        assert "Editing workspace agent 'coder.safe'" in _build_profile_editor_hint(workspace_profile)
        assert "Clone it to a workspace agent to edit" in _build_profile_editor_hint(plugin_profile)


class TestOutputHistoryHelpers:
    def test_trim_output_lines_keeps_tail_with_overflow_count(self):
        lines, trimmed = _trim_output_lines(["l1", "l2", "l3"], 2)

        assert lines == ["l2", "l3"]
        assert trimmed == 1

    def test_build_output_text_adds_trim_notice_when_history_was_capped(self):
        text = _build_output_text(["info> ready", "assistant> ok"], 3)

        assert text == (
            "info> [output history trimmed: showing last 2 lines]\n"
            "info> ready\n"
            "assistant> ok"
        )


class _TextualEngineStub:
    def __init__(self) -> None:
        self.current_agent = "a"
        self.active_agent_profile = self._profile("a", "a")
        self.global_llm_override = None
        self.auto_confirm_tools = False
        self.session_confirmation_overrides: dict[str, str | None] = {}
        self.set_agent_calls: list[str | None] = []
        self.set_active_agent_profile_calls: list[str] = []
        self.clone_agent_profile_calls: list[tuple[str, str]] = []
        self.clone_llm_profile_calls: list[tuple[str, str]] = []
        self.update_agent_profile_calls: list[dict[str, object]] = []
        self.update_llm_profile_calls: list[dict[str, object]] = []
        self.save_system_settings_calls: list[dict[str, object]] = []
        self.set_last_used_skill_calls: list[list[str]] = []
        self.reset_last_used_skill_calls = 0
        self.save_default_skills_calls: list[list[str]] = []
        self.set_last_used_profile_tools_calls: list[tuple[str, list[str] | None]] = []
        self.reset_last_used_profile_tools_calls: list[str] = []
        self.set_last_used_profile_tool_policy_calls: list[tuple[str, dict[str, str]]] = []
        self.reset_last_used_profile_tool_policy_calls: list[str] = []
        self.active_skills: list[str] = []
        self.skill_enabled: list[str] = []
        self.skill_disabled: list[str] = []
        self._profiles = {
            "a": self._profile("a", "a"),
            "a-safe": self._profile("a-safe", "a"),
            "b": self._profile("b", "b"),
            "b-safe": self._profile("b-safe", "b"),
            "c": self._profile("c", "c"),
            "c-safe": self._profile("c-safe", "c"),
        }

    @staticmethod
    def _profile(name: str, agent: str) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            agent=agent,
            source="workspace" if name.endswith("-safe") else "synthesised",
            description="",
            llm_profile=None,
            tools=None,
            tool_confirmation={},
            extra_prompts=[],
        )

    def list_agents(self):
        return ["a", "b", "c"]

    def list_llm_profiles(self):
        return ["fast", "smart"]

    def list_skills(self):
        return ["python-lint", "python-testing", "azure-prepare"]

    def get_active_skills(self):
        return [SimpleNamespace(name=name) for name in self.active_skills]

    def enable_skill(self, name):
        self.skill_enabled.append(name)
        if name not in self.active_skills:
            self.active_skills.append(name)

    def disable_skill(self, name):
        self.skill_disabled.append(name)
        self.active_skills = [skill for skill in self.active_skills if skill != name]

    def get_llm_profile(self, name=None):
        target = name or self.global_llm_override or "fast"
        sources = {
            "fast": "workspace",
            "smart": "plugin",
        }
        return {
            "name": target,
            "source": sources.get(target, "workspace"),
            "source_path": Path(f"/tmp/{target}.yaml"),
            "config": {
                "provider": "gemini",
                "model": target,
                "parameters": {"temperature": 0.2},
            },
        }

    def list_agent_profiles(self, agent_name=None):
        target = agent_name or self.current_agent
        return [
            profile.name
            for profile in self._profiles.values()
            if profile.agent == target
        ]

    def get_agent_profile(self, name=None, *, effective=True):
        if name is None:
            return self.active_agent_profile
        return self._profiles.get(name)

    def get_current_agent(self):
        return self.current_agent

    def set_agent(self, agent_name):
        self.set_agent_calls.append(agent_name)
        self.current_agent = agent_name
        if agent_name is None:
            self.active_agent_profile = None
            return
        self.active_agent_profile = self._profiles.get(agent_name, self._profile(agent_name, agent_name))

    def set_active_agent_profile(self, name):
        self.set_active_agent_profile_calls.append(name)
        self.active_agent_profile = self._profiles.get(name, self._profile(name, self.current_agent))
        self.current_agent = self.active_agent_profile.agent

    def clone_agent_profile(self, src_name, new_name):
        self.clone_agent_profile_calls.append((src_name, new_name))
        cloned = SimpleNamespace(
            name=new_name,
            agent=self.current_agent,
            source="workspace",
            description="",
            llm_profile=None,
            tools=None,
            tool_confirmation={},
            extra_prompts=[],
            source_path=Path(f"/tmp/{new_name}.yaml"),
        )
        self._profiles[new_name] = cloned
        return cloned

    def clone_llm_profile(self, src_name, new_name):
        self.clone_llm_profile_calls.append((src_name, new_name))
        return {
            "name": new_name,
            "source": "workspace",
            "source_path": Path(f"/tmp/{new_name}.yaml"),
            "config": {
                "provider": "gemini",
                "model": src_name,
                "parameters": {"temperature": 0.2},
            },
        }

    def update_agent_profile(
        self,
        name,
        *,
        llm_profile,
        tools,
        extra_prompts,
        tool_confirmation_default,
        tool_confirmation_overrides,
    ):
        self.update_agent_profile_calls.append(
            {
                "name": name,
                "llm_profile": llm_profile,
                "tools": tools,
                "extra_prompts": extra_prompts,
                "tool_confirmation_default": tool_confirmation_default,
                "tool_confirmation_overrides": tool_confirmation_overrides,
            }
        )

    def update_llm_profile(self, name, *, profile_config):
        self.update_llm_profile_calls.append(
            {
                "name": name,
                "profile_config": profile_config,
            }
        )

    def get_system_settings(self):
        return {
            "theme_name": "ocean",
            "workspace_mode": "balanced",
            "default_agent": "a",
            "default_llm_profile": "fast",
        }

    def save_system_settings(self, *, theme_name, workspace_mode, default_agent, default_llm_profile):
        self.save_system_settings_calls.append(
            {
                "theme_name": theme_name,
                "workspace_mode": workspace_mode,
                "default_agent": default_agent,
                "default_llm_profile": default_llm_profile,
            }
        )
        return Path("/tmp/pocketcode.yml")

    def set_last_used_skills(self, skill_names):
        normalized = list(skill_names)
        self.set_last_used_skill_calls.append(normalized)
        self.active_skills = normalized
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_skills(self):
        self.reset_last_used_skill_calls += 1
        self.active_skills = []
        return Path("/tmp/pocketcode.yml")

    def save_default_skills(self, skill_names):
        self.save_default_skills_calls.append(list(skill_names))
        return Path("/tmp/pocketcode.yml")

    def set_last_used_profile_tools(self, profile_name, tools):
        normalized = None if tools is None else list(tools)
        self.set_last_used_profile_tools_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tools = normalized
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tools = normalized
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_profile_tools(self, profile_name):
        self.reset_last_used_profile_tools_calls.append(profile_name)
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tools = None
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tools = None
        return Path("/tmp/pocketcode.yml")

    def set_last_used_profile_tool_policies(self, profile_name, overrides):
        normalized = dict(overrides)
        self.set_last_used_profile_tool_policy_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tool_confirmation = {"overrides": normalized}
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tool_confirmation = {"overrides": normalized}
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_profile_tool_policies(self, profile_name):
        self.reset_last_used_profile_tool_policy_calls.append(profile_name)
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tool_confirmation = {}
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tool_confirmation = {}
        return Path("/tmp/pocketcode.yml")

    def list_tools_for_agent(self, agent_name):
        return ["tool.read", "tool.write"]

    def get_agent_prompt_sources(self, agent_name=None):
        return []

    def status(self):
        return {
            "available_llm_profiles": self.list_llm_profiles(),
            "available_flows": self.list_agents(),
            "available_agents": self.list_agent_profiles(),
            "available_skills": self.list_skills(),
            "session_tool_confirmation_overrides": self.session_confirmation_overrides,
            "flow": self.current_agent,
            "agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "selected_agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "selected_llm_profile": self.global_llm_override or "fast",
            "active_agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "active_agent_profile": self.active_agent_profile.name if self.active_agent_profile else None,
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_agent": self.current_agent,
                "current_llm_profile": None,
                "current_llm_model": None,
                "agent_path": [],
            },
        }

    def describe_agent(self, agent_name=None):
        target = agent_name or self.current_agent
        return {
            "name": target,
            "description": "",
            "execution_mode": "",
            "prompt_sources": [],
            "profiles": self.list_agent_profiles(target),
            "tools": self.list_tools_for_agent(target),
        }

    def describe_tools_for_agent(self, agent_name):
        return []

    def set_global_llm_override(self, value):
        self.global_llm_override = value

    def set_session_confirmation_default(self, value):
        self.session_confirmation_overrides["default_policy"] = value


class TestTextualSelectStability:
    def test_asset_picker_supports_arrow_key_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6", "down", "enter")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)

                await pilot.press("down", "down", "enter")
                await pilot.pause(0.1)

                assert engine.global_llm_override == "smart"
                assert any("Global LLM override: smart" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_asset_picker_can_select_global_llm(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("llm")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("smart")
                await pilot.pause(0.1)

                assert engine.global_llm_override == "smart"
                assert any("Global LLM override: smart" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_header_uses_static_agent_and_llm_labels(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                assert isinstance(app.query_one("#header-agent", Static), Static)
                assert isinstance(app.query_one("#header-llm", Static), Static)
                assert len(app.query("#status")) == 0
                assert app._text_state_cache["header-agent"] == "Agent: a"
                assert app._text_state_cache["header-llm"] == "LLM: fast (-)"

        asyncio.run(exercise())


class TestToolSelectionPopup:
    def test_tool_picker_toggle_uses_selection_index_event_field(self):
        screen = ToolSelectionScreen(
            title="Edit Allowed Tools",
            tools=[SimpleNamespace(value="core.ask_user_input", label="core.ask_user_input", description="", search_text="")],
            selected_values=[],
        )
        selection_list = SimpleNamespace(
            id="tool-picker-list",
            disabled=False,
            selected={"core.ask_user_input"},
            get_option_at_index=lambda index: SimpleNamespace(value="core.ask_user_input"),
        )
        event = SimpleNamespace(selection_list=selection_list, selection_index=0)

        screen.on_selection_list_selection_toggled(event)

        assert screen._selected_values == {"core.ask_user_input"}

    def test_group_toggle_selects_all_group_members(self):
        screen = ToolSelectionScreen(
            title="Select Skills",
            tools=[
                SimpleNamespace(value="__skill_group__:python", label="Group: python", description="", search_text=""),
                SimpleNamespace(value="python-lint", label="  python-lint", description="", search_text=""),
                SimpleNamespace(value="python-testing", label="  python-testing", description="", search_text=""),
            ],
            selected_values=[],
            grouped_values={"__skill_group__:python": ("python-lint", "python-testing")},
        )
        selection_list = SimpleNamespace(
            id="tool-picker-list",
            disabled=False,
            selected={"__skill_group__:python"},
            get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:python"),
        )
        event = SimpleNamespace(selection_list=selection_list, selection_index=0)

        screen.on_selection_list_selection_toggled(event)

        assert screen._selected_values == {"__skill_group__:python", "python-lint", "python-testing"}

    def test_edit_shortcut_can_open_tool_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f3")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("tools")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen.query_one("#tool-picker-filter", Input).placeholder == "Filter tools..."

        asyncio.run(exercise())

    def test_tool_picker_ctrl_arrows_switch_between_filter_and_list(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = []
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen.focused.id == "tool-picker-filter"

                await pilot.press("ctrl+down")
                await pilot.pause(0.05)
                assert app.screen.focused.id == "tool-picker-list"

                await pilot.press("ctrl+up")
                await pilot.pause(0.05)
                assert app.screen.focused.id == "tool-picker-filter"

        asyncio.run(exercise())

    def test_tool_picker_space_toggles_highlighted_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = []
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                await pilot.press("ctrl+down", "space")
                await pilot.pause(0.05)

                assert "__skill_group__:tool" in app.screen._selected_values

        asyncio.run(exercise())

    def test_f6_select_can_open_skill_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("skills")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen._filter_placeholder == "Filter skills..."

        asyncio.run(exercise())

    def test_f6_select_can_open_tool_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("tools")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert any(option.label == "Group: tool" for option in app.screen._tools)

        asyncio.run(exercise())

    def test_f6_select_can_open_system_settings_screen(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("system_settings")
                await pilot.pause(0.1)

                assert isinstance(app.screen, SystemSettingsScreen)

        asyncio.run(exercise())


class TestProfileCloneAndSave:
    def test_clone_shortcut_promotes_workspace_agent(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("f4")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("agent")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("a-workspace")
                await pilot.pause(0.05)

                assert engine.clone_agent_profile_calls == [("a", "a-workspace")]
                assert engine.active_agent_profile.name == "a-workspace"

        asyncio.run(exercise())

    def test_edit_agent_popup_persists_workspace_agent_edits(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_agent_yaml_edit(
                    "a-safe",
                    "extra_prompts:\n  - prompts/review.md\n  - prompts/safety.md\n",
                )

                await pilot.pause(0.05)

                assert engine.update_agent_profile_calls == [
                    {
                        "name": "a-safe",
                        "llm_profile": None,
                        "tools": None,
                        "extra_prompts": ["prompts/review.md", "prompts/safety.md"],
                        "tool_confirmation_default": None,
                        "tool_confirmation_overrides": {},
                    }
                ]

        asyncio.run(exercise())

    def test_edit_agent_popup_clones_synthesised_agent_before_editing(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("f3")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("agent")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("a-workspace")
                await pilot.pause(0.1)

                assert engine.clone_agent_profile_calls == [("a", "a-workspace")]
                assert engine.active_agent_profile.name == "a-workspace"
                assert isinstance(app.screen, TextEditorScreen)

        asyncio.run(exercise())

    def test_edit_llm_popup_persists_workspace_llm_edits(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_llm_yaml_edit(
                    "fast",
                    "provider: gemini\nmodel: gemini-2.5-flash\nparameters:\n  temperature: 0.1\n",
                )
                await pilot.pause(0.05)

                assert engine.update_llm_profile_calls == [
                    {
                        "name": "fast",
                        "profile_config": {
                            "provider": "gemini",
                            "model": "gemini-2.5-flash",
                            "parameters": {"temperature": 0.1},
                        },
                    }
                ]

        asyncio.run(exercise())

    def test_tool_policy_popup_persists_workspace_agent_policy_overrides(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_tool_policy_yaml_edit("a-safe", "tool.write: deny\n")
                await pilot.pause(0.05)

                assert engine.update_agent_profile_calls[-1]["tool_confirmation_overrides"] == {"tool.write": "deny"}
                assert engine.reset_last_used_profile_tool_policy_calls == ["a-safe"]

        asyncio.run(exercise())

    def test_tool_selection_popup_saves_last_used_tools(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                app.screen.dismiss({"action": "apply", "values": ["tool.read"]})
                await pilot.pause(0.05)

                assert engine.set_last_used_profile_tools_calls == [("a-safe", ["tool.read"])]

        asyncio.run(exercise())

    def test_tool_policy_popup_can_open_policy_editor_screen(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_policy_editor()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolPolicyEditorScreen)

        asyncio.run(exercise())

    def test_system_settings_screen_applies_and_saves_defaults(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_system_settings(
                    {
                        "theme_name": "forest",
                        "workspace_mode": "review",
                        "default_agent": "b",
                        "default_llm_profile": "smart",
                    }
                )
                await pilot.pause(0.05)

                assert engine.save_system_settings_calls == [
                    {
                        "theme_name": "forest",
                        "workspace_mode": "review",
                        "default_agent": "b",
                        "default_llm_profile": "smart",
                    }
                ]
                assert engine.current_agent == "b"

        asyncio.run(exercise())


class TestInspectorToolFiltering:
    def test_inspector_hides_deselected_tools(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = ["tool.read"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                text = app.query_one("#inspector-tools").text

                assert "tool.read" in text
                assert "tool.write" not in text

        asyncio.run(exercise())

    def test_inspector_skill_list_reflects_enabled_skills(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.active_skills = ["python-lint", "python-testing"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                skill_list = app.query_one("#skill-list", SelectionList)

                assert "python-testing" in skill_list.selected
                assert "__skill_group__:python" in skill_list.selected

        asyncio.run(exercise())

    def test_inspector_skill_toggle_enables_selected_skill(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="skill-list",
                    disabled=False,
                    selected={"python-testing"},
                    get_option_at_index=lambda index: SimpleNamespace(value="python-testing"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.skill_enabled == ["python-testing"]
                assert engine.set_last_used_skill_calls[-1] == ["python-testing"]

        asyncio.run(exercise())

    def test_inspector_skill_group_toggle_enables_group_members(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="skill-list",
                    disabled=False,
                    selected={"__skill_group__:python"},
                    get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:python"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.skill_enabled == ["python-lint", "python-testing"]
                assert engine.set_last_used_skill_calls[-1] == ["python-lint", "python-testing"]

        asyncio.run(exercise())
