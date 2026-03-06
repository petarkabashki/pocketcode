from __future__ import annotations

from types import SimpleNamespace

from pocketcode.cli.textual_app import (
    _build_output_text,
    _build_profile_editor_hint,
    _build_stats_text,
    _build_status_text,
    _build_view_title_text,
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
            "agent": "coder::coder",
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

        assert "Agent: coder::coder" in text
        assert "Profile: coder.safe" in text
        assert "LLM: fast (gpt-test)" in text
        assert "View: Control Center" in text

    def test_view_title_text_matches_named_view(self):
        assert _build_view_title_text("run").startswith("Run Inspector | ")

    def test_profile_editor_hint_tracks_profile_source(self):
        workspace_profile = SimpleNamespace(name="coder.safe", source="workspace")
        plugin_profile = SimpleNamespace(name="coder.default", source="plugin")

        assert _build_profile_editor_hint(None) == "Select an agent or profile to edit profile settings."
        assert "Editing workspace profile 'coder.safe'" in _build_profile_editor_hint(workspace_profile)
        assert "Clone it to a workspace profile to edit" in _build_profile_editor_hint(plugin_profile)


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
