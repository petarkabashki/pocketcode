from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pocketcode.cli.textual_app import (
    PocketCodeTextualApp,
    _build_output_text,
    _build_profile_editor_hint,
    _build_stats_text,
    _build_status_text,
    _build_view_title_text,
    _cycle_value,
    _trim_output_lines,
)


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
    def test_status_text_includes_current_view(self):
        status = {
            "flow": "coder::coder",
            "agent": "coder.safe",
            "active_agent": "coder.safe",
            "active_agent_profile": "coder.safe",
            "global_llm_override": "fast",
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_agent": "coder::coder",
                "current_llm_profile": "fast",
                "current_llm_model": "gpt-test",
                "agent_path": [],
            },
        }

        text = _build_status_text(status, "control")

        assert "Flow: coder::coder" in text
        assert "Agent: coder.safe" in text
        assert "LLM: fast (gpt-test)" in text
        assert "View: Control Center" in text

    def test_view_title_text_matches_named_view(self):
        assert _build_view_title_text("run").startswith("Run Inspector | ")

    def test_profile_editor_hint_tracks_profile_source(self):
        workspace_profile = SimpleNamespace(name="coder.safe", source="workspace")
        plugin_profile = SimpleNamespace(name="coder.default", source="plugin")

        assert _build_profile_editor_hint(None) == "Select a flow or agent to edit agent settings."
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


class TestCycleValue:
    def test_cycle_value_moves_forward_from_missing_to_first_item(self):
        assert _cycle_value(["a", "b", "c"], "missing", 1, missing_index=-1) == "a"

    def test_cycle_value_moves_backward_from_missing_to_last_item(self):
        assert _cycle_value(["a", "b", "c"], "missing", -1, missing_index=0) == "c"

    def test_cycle_value_wraps_llm_cycle_backwards_from_inherit(self):
        assert _cycle_value([None, "fast", "smart"], None, -1, missing_index=0) == "smart"


class _TextualEngineStub:
    def __init__(self) -> None:
        self.current_agent = "a"
        self.active_agent_profile = self._profile("a", "a")
        self.global_llm_override = None
        self.auto_confirm_tools = False
        self.session_confirmation_overrides: dict[str, str | None] = {}
        self.set_agent_calls: list[str | None] = []
        self.set_active_agent_profile_calls: list[str] = []

    @staticmethod
    def _profile(name: str, agent: str) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            agent=agent,
            source="synthesised",
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

    def list_agent_profiles(self, agent_name=None):
        target = agent_name or self.current_agent
        return [target, f"{target}-safe"]

    def get_current_agent(self):
        return self.current_agent

    def set_agent(self, agent_name):
        self.set_agent_calls.append(agent_name)
        self.current_agent = agent_name
        if agent_name is None:
            self.active_agent_profile = None
            return
        self.active_agent_profile = self._profile(agent_name, agent_name)

    def set_active_agent_profile(self, name):
        self.set_active_agent_profile_calls.append(name)
        self.active_agent_profile = self._profile(name, self.current_agent)

    def list_tools_for_agent(self, agent_name):
        return ["tool.read", "tool.write"]

    def get_agent_prompt_sources(self, agent_name=None):
        return []

    def status(self):
        return {
            "available_llm_profiles": self.list_llm_profiles(),
            "available_flows": self.list_agents(),
            "available_agents": self.list_agent_profiles(),
            "session_tool_confirmation_overrides": self.session_confirmation_overrides,
            "flow": self.current_agent,
            "agent": self.active_agent_profile.name if self.active_agent_profile else None,
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
    def test_f6_selects_next_agent_without_reentering_selector_callbacks(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                engine.set_agent_calls.clear()
                engine.set_active_agent_profile_calls.clear()

                await pilot.press("f6")
                await pilot.pause(0.05)
                first_counts = (
                    len(engine.set_agent_calls),
                    len(engine.set_active_agent_profile_calls),
                )
                await pilot.pause(0.2)

                assert engine.get_current_agent() == "b"
                assert first_counts == (
                    len(engine.set_agent_calls),
                    len(engine.set_active_agent_profile_calls),
                )
                assert engine.set_agent_calls == ["b"]
                assert engine.set_active_agent_profile_calls == []

        asyncio.run(exercise())
