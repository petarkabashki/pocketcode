from __future__ import annotations

import io
import sys
from typing import Any, cast

from pocketcode import main as main_module


class _EngineStub:
    def __init__(self):
        self.set_flow_calls = []
        self.global_llm_override = None
        self.auto_confirm_tools = False

    def status(self):
        return {
            "runtime_flow": "internal-router",
            "flow": "core::react",
            "agent": "coder.safe",
            "mode": None,
            "skills": [],
            "global_llm_override": self.global_llm_override,
            "agent_llm_overrides": {},
            "handoff_llm_overrides": {},
            "config_llm_overrides": {},
            "default_llm_profile": "balanced",
            "tool_confirmation": {},
            "session_tool_confirmation_overrides": {},
        }

    def set_flow(self, flow_name):
        self.set_flow_calls.append(flow_name)

    def set_global_llm_override(self, profile_name):
        self.global_llm_override = profile_name


def _run_cli(monkeypatch, argv, engine=None):
    engine = engine or _EngineStub()
    stdout = io.StringIO()
    stderr = io.StringIO()

    monkeypatch.setattr(main_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(main_module, "resolve_settings_path", lambda config_path, cwd: "/tmp/pocketcode.yml")
    monkeypatch.setattr(
        main_module,
        "load_settings",
        lambda settings_path, workspace_root: {"runtime": {}, "llm": {}},
    )
    monkeypatch.setattr(main_module, "_configure_logging", lambda log_level, stream=True: None)
    monkeypatch.setattr(main_module, "PocketCodeEngine", lambda config, workspace_root: engine)
    monkeypatch.setattr(sys, "argv", ["pocketcode", *argv])
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"isatty": lambda self: True, "read": lambda self: ""})())

    exit_code = 0
    try:
        main_module.run()
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1

    return exit_code, stdout.getvalue(), stderr.getvalue(), engine


def test_print_startup_uses_agent_centered_labels(capsys):
    main_module._print_startup(cast(Any, _EngineStub()))

    captured = capsys.readouterr()
    assert "Pocketcode runtime ready." in captured.out
    assert "Internal flow: internal-router" in captured.out
    assert "workflow" not in captured.out.lower()


def test_one_shot_help_omits_textual_only_commands(monkeypatch):
    exit_code, stdout, _, _ = _run_cli(monkeypatch, ["--prompt", "/help"])

    assert exit_code == 0
    assert "/copy" not in stdout
    assert "Textual UI shortcuts" not in stdout
    assert "workflow" not in stdout.lower()


def test_one_shot_status_uses_agent_centered_labels(monkeypatch):
    exit_code, stdout, _, _ = _run_cli(monkeypatch, ["--prompt", "/status"])

    assert exit_code == 0
    assert "Internal flow: internal-router" in stdout
    assert "Agent: coder.safe" in stdout
    assert "workflow" not in stdout.lower()


def test_one_shot_textual_command_reports_scope(monkeypatch):
    exit_code, stdout, _, _ = _run_cli(monkeypatch, ["--prompt", "/copy"])

    assert exit_code == 0
    assert "available only in the Textual UI" in stdout


def test_removed_workflow_flag_is_rejected(monkeypatch):
    exit_code, _, stderr, _ = _run_cli(monkeypatch, ["--workflow", "legacy", "--prompt", "/help"])

    assert exit_code == 2
    assert "unrecognized arguments: --workflow legacy" in stderr


def test_removed_agent_flag_alias_is_rejected(monkeypatch):
    exit_code, _, stderr, _ = _run_cli(monkeypatch, ["--agent", "core::react", "--prompt", "/help"])

    assert exit_code == 2
    assert "unrecognized arguments: --agent core::react" in stderr
