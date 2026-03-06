from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pocketcode.cli.command_handler import handle_command


class _EngineStub:
    def list_agents(self):
        return []

    def list_llm_profiles(self):
        return []

    def list_agent_profiles(self, agent_name=None):
        return []


class _EditableProfileEngineStub(_EngineStub):
    def __init__(self):
        self.profile = SimpleNamespace(
            name="coder.safe",
            agent="coder::coder",
            source="workspace",
            source_path=Path("/tmp/coder.safe.yaml"),
            llm_profile="fast",
            extra_prompts=["prompts/base.md"],
            tools=["tool.read"],
            tool_confirmation={
                "default": "confirm",
                "overrides": {"tool.write": "deny"},
            },
        )
        self.updated_calls = []

    def get_agent_profile(self, name=None):
        if name == self.profile.name or name is None:
            return self.profile
        return None

    def list_tools_for_agent(self, agent_name):
        assert agent_name == self.profile.agent
        return ["tool.read", "tool.write", "tool.search"]

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
        self.updated_calls.append(
            {
                "name": name,
                "llm_profile": llm_profile,
                "tools": tools,
                "extra_prompts": extra_prompts,
                "tool_confirmation_default": tool_confirmation_default,
                "tool_confirmation_overrides": tool_confirmation_overrides,
            }
        )


class TestCommandHandlerParsing:
    def test_context_add_snippet_uses_shell_style_quoting(self):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            '/context add snippet note "line one with spaces"',
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        assert cli_context["snippets"] == {"note": "line one with spaces"}

    def test_invalid_quoted_command_returns_parse_error(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            '/context add snippet note "unterminated',
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Command parse error" in captured.out


class TestAgentEditingCommands:
    def test_agent_tools_set_updates_allowed_tools(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe set tool.read tool.search",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read", "tool.search"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]
        captured = capsys.readouterr()
        assert "allowed tools updated" in captured.out

    def test_agent_tools_all_clears_allowlist(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe all",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls[0]["tools"] is None
        captured = capsys.readouterr()
        assert "now allows all tools" in captured.out

    def test_agent_policy_default_updates_profile_default(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy default coder.safe allow",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "allow",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]
        captured = capsys.readouterr()
        assert "default tool policy set to: allow" in captured.out

    def test_agent_policy_tool_updates_per_tool_override(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy tool coder.safe tool.search confirm",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {
                    "tool.write": "deny",
                    "tool.search": "confirm",
                },
            }
        ]
        captured = capsys.readouterr()
        assert "tool.search -> confirm" in captured.out

    def test_agent_policy_tool_reset_removes_override(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy tool coder.safe tool.write reset",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {},
            }
        ]
        captured = capsys.readouterr()
        assert "tool.write -> inherit" in captured.out

    def test_agent_tools_rejects_unknown_tool_name(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe set tool.read tool.ghost",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == []
        captured = capsys.readouterr()
        assert "unknown tool(s)" in captured.out
