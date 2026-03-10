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
            "last_run_summary": {},
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


def test_one_shot_status_verbose_prints_vm_warning_messages(monkeypatch):
    engine = _EngineStub()
    engine.status = lambda: {
        "runtime_flow": "internal-router",
        "flow": "core::react",
        "agent": "coder.safe",
        "mode": None,
        "skills": [],
        "global_llm_override": engine.global_llm_override,
        "agent_llm_overrides": {},
        "handoff_llm_overrides": {},
        "config_llm_overrides": {},
        "default_llm_profile": "balanced",
        "tool_confirmation": {},
        "session_tool_confirmation_overrides": {},
            "last_run_summary": {
                "vm_validation_warnings": [
                    {
                        "code": "legacy-tool-loop",
                        "message": "Prefer tool-once.",
                        "location": "line 4, cols 1-12",
                        "span": {
                            "start_line": 4,
                            "start_column": 1,
                            "end_line": 4,
                            "end_column": 12,
                        },
                    },
                ]
            },
        }

    exit_code, stdout, _, _ = _run_cli(monkeypatch, ["--prompt", "/status verbose"], engine=engine)

    assert exit_code == 0
    assert "VM Validation Warnings: legacy-tool-loop" in stdout
    assert "- legacy-tool-loop (line 4, cols 1-12): Prefer tool-once." in stdout


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


def test_build_debugger_until_predicate_supports_node_and_condition_matching():
    predicate_config = main_module._build_debugger_until_predicate(["node", "review"])
    assert predicate_config is not None
    predicate, label = predicate_config

    assert label == "until node review"
    assert predicate({"type": "node_completed", "node_id": "review"}, {}) is True
    assert predicate({"type": "node_completed", "node_id": "start"}, {}) is False

    condition_config = main_module._build_debugger_until_predicate(
        ["when", "pending_tool.name", "==", "core.write_file"]
    )
    assert condition_config is not None
    condition, condition_label = condition_config

    assert "pending_tool.name" in condition_label
    assert condition({}, {"pending_tool": {"name": "core.write_file"}}) is True
    assert condition({}, {"pending_tool": {"name": "core.read_file"}}) is False


def test_parse_debug_step_count_accepts_positive_integer_and_rejects_invalid_values():
    assert main_module._parse_debug_step_count([]) == 1
    assert main_module._parse_debug_step_count(["5"]) == 5
    assert main_module._parse_debug_step_count(["0"]) is None
    assert main_module._parse_debug_step_count(["one"]) is None


def test_print_debug_breakpoints_renders_saved_breakpoints(capsys):
    class _Handle:
        def list_debug_breakpoints(self):
            return [
                {"id": 1, "label": "until node review"},
                {"id": 2, "label": "until tool core.write_file"},
            ]

    main_module._print_debug_breakpoints(_Handle())

    captured = capsys.readouterr()
    assert "[debug] Breakpoints:" in captured.out
    assert "1. until node review" in captured.out
    assert "2. until tool core.write_file" in captured.out


def test_print_debug_pause_renders_active_node_details(capsys):
    main_module._print_debug_pause(
        {"type": "node_completed", "node_id": "review", "node_kind": "tool", "transition": "final_answer"},
        {
            "active_agent": "graph.agent",
            "active_node_id": "review",
            "active_node_kind": "tool",
            "step_count": 2,
            "runtime_event_count": 4,
        },
    )

    captured = capsys.readouterr()
    assert "[debug] Active agent: graph.agent" in captured.out
    assert "[debug] Active node: review (tool)" in captured.out
