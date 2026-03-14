from __future__ import annotations

from pathlib import Path

from pocketcode.core.engine import PocketCodeEngine


def _make_engine(workspace_root: Path) -> PocketCodeEngine:
    (workspace_root / ".pocketcode" / "flows").mkdir(parents=True, exist_ok=True)
    config = {
        "llm": {"providers": {}, "profiles": {}},
        "runtime": {
            "default_agent": None,
            "auto_confirm_tools": True,
            "require_tool_confirmation": False,
        },
    }
    return PocketCodeEngine(config=config, workspace_root=workspace_root)


def _qualified_flow_name(engine: PocketCodeEngine, suffix: str) -> str:
    return next(name for name in engine.list_flows() if name.endswith(f".{suffix}"))


def test_create_stackvm_flow_with_agent_can_be_inspected_and_run(tmp_path: Path):
    engine = _make_engine(tmp_path)

    created = engine.create_stackvm_flow("vm_triage", entry="decide", agent_name="vm_triage.safe")
    flow_name = _qualified_flow_name(engine, "vm_triage")

    assert created["name"] == "vm_triage"
    assert created["entry"] == "decide"
    assert created["agent"]["name"] == "vm_triage.safe"

    details = engine.inspect_stackvm_target("flow", flow_name)
    assert details["execution_mode"] == "vm"
    assert details["vm_entry"] == "decide"
    assert "StackVM flow vm_triage ready." in details["source"]
    assert details["diagnostic_count"] == 0
    assert details["effect_kinds"] == ["final"]
    assert details["stdlib_modules_requested"] == []
    assert details["stdlib_modules_resolved"] == []

    result = engine.run_stackvm_target("flow", flow_name, debug=True)
    assert result["output"] == "StackVM flow vm_triage ready."
    assert result["trace_count"] > 0
    assert result["run_summary"]["vm_diagnostic_count"] == 0


def test_create_stackvm_script_can_be_updated_inspected_and_run(tmp_path: Path):
    engine = _make_engine(tmp_path)

    created = engine.create_stackvm_script("hello", entry="main")
    assert created["path"].name == "hello.vm"

    updated = engine.update_stackvm_script(
        "hello",
        source_text='[ "script ok" answer ] "main" define\n',
    )
    assert updated["path"].name == "hello.vm"

    details = engine.inspect_stackvm_target("script", "hello")
    assert details["execution_mode"] == "vm"
    assert details["source_files"]
    assert details["effect_kinds"] == ["final"]
    assert details["stdlib_modules_requested"] == []
    assert details["stdlib_modules_resolved"] == []

    result = engine.run_stackvm_target("script", "hello", debug=True)
    assert result["output"] == "script ok"
    assert result["trace_count"] > 0
    assert result["trace"][3]["scope"] == "main > word:main"
    assert result["trace"][3]["stack_delta"] == {"depth_change": 1, "popped": [], "pushed": ["script ok"]}
    assert result["trace"][3]["location"] == "line 1, cols 3-13"
    assert result["trace"][3]["authored_location"] == "line 1, cols 3-13"
    assert result["run_summary"]["vm_effect_kinds"] == ["final"]
    assert result["run_summary"]["current_agent"] == "__stackvm_script__.hello"
    assert result["run_summary"]["runtime_effect_history"][0]["source"] == "standalone-vm"
    assert result["run_summary"]["stackvm_runtime"] == {
        "path": "standalone-script",
        "source": "standalone-vm",
        "standalone_session_active": False,
    }


def test_inspect_stackvm_flow_warns_when_stdlib_alias_is_missing_from_manifest(tmp_path: Path):
    engine = _make_engine(tmp_path)
    created = engine.create_stackvm_flow("stdlib_missing", entry="router.route")

    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "ghost.vm").write_text(
        '\n'.join(
            [
                '"stdlib.ghost" module',
                '[ "ghost ok" ] "message" define',
                '"message" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.1.0",
                "module_root: vm/stdlib",
                "modules: []",
            ]
        ),
        encoding="utf-8",
    )

    created["path"].write_text(
        "\n".join(
            [
                "---",
                "name: stdlib_missing",
                "execution_mode: vm",
                "vm_entry: router.route",
                "vm_modules:",
                "  - stdlib.ghost",
                "---",
                "",
                "```vm",
                '"router" module',
                '"stdlib.ghost.message" import',
                '[ message answer ] "route" define',
                '"route" export',
                "```",
            ]
        ),
        encoding="utf-8",
    )
    engine.reload()
    flow_name = _qualified_flow_name(engine, "stdlib_missing")

    details = engine.inspect_stackvm_target("flow", flow_name)

    assert details["stdlib_modules_requested"] == []
    assert details["stdlib_unresolved_refs"] == ["stdlib.ghost"]
    assert details["warning_count"] == 1
    assert details["warnings"][0]["code"] == "stdlib-module-missing"


def test_update_markdown_flow_returns_stdlib_manifest_warnings(tmp_path: Path):
    engine = _make_engine(tmp_path)
    created = engine.create_stackvm_flow("stdlib_update", entry="router.route")

    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "ghost.vm").write_text(
        '\n'.join(
            [
                '"stdlib.ghost" module',
                '[ "ghost ok" ] "message" define',
                '"message" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.1.0",
                "module_root: vm/stdlib",
                "modules: []",
            ]
        ),
        encoding="utf-8",
    )

    updated = engine.update_markdown_asset(
        "flow",
        "stdlib_update",
        markdown_text="\n".join(
            [
                "---",
                "name: stdlib_update",
                "execution_mode: vm",
                "vm_entry: router.route",
                "vm_modules:",
                "  - stdlib.ghost",
                "---",
                "",
                "```vm",
                '"router" module',
                '"stdlib.ghost.message" import',
                '[ message answer ] "route" define',
                '"route" export',
                "```",
            ]
        ),
    )

    assert created["path"] == updated["path"]
    assert len(updated["warnings"]) == 1
    assert updated["warnings"][0]["code"] == "stdlib-module-missing"


def test_reload_status_reports_workspace_stdlib_manifest_warnings(tmp_path: Path):
    engine = _make_engine(tmp_path)
    created = engine.create_stackvm_flow("workspace_stdlib_missing", entry="router.route")

    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "ghost.vm").write_text(
        '\n'.join(
            [
                '"stdlib.ghost" module',
                '[ "ghost ok" ] "message" define',
                '"message" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.1.0",
                "module_root: vm/stdlib",
                "modules: []",
            ]
        ),
        encoding="utf-8",
    )

    created["path"].write_text(
        "\n".join(
            [
                "---",
                "name: workspace_stdlib_missing",
                "execution_mode: vm",
                "vm_entry: router.route",
                "vm_modules:",
                "  - stdlib.ghost",
                "---",
                "",
                "```vm",
                '"router" module',
                '"stdlib.ghost.message" import',
                '[ message answer ] "route" define',
                '"route" export',
                "```",
            ]
        ),
        encoding="utf-8",
    )

    engine.reload()
    status = engine.status()
    summary = status["workspace_stackvm_stdlib_summary"]

    assert summary["warning_count"] == 1
    assert summary["warnings"][0]["code"] == "stdlib-module-missing"
    assert summary["warnings"][0]["target_kind"] == "flow"


def test_run_stackvm_script_standalone_supports_portable_tool_call(tmp_path: Path):
    engine = _make_engine(tmp_path)
    engine.create_stackvm_script("tool_script", entry="main")
    engine.update_stackvm_script(
        "tool_script",
        source_text='[ "demo.echo" "{text: ping}" yaml> tool-call "text" dict-get answer ] "main" define\n',
    )

    class _ToolRuntime:
        tools = {"demo.echo": object()}

        def describe_tools(self, tool_names):
            return [{"name": name} for name in tool_names]

        def execute_tool(self, tool_name, arguments, shared_store, auto_confirm=False, agent_name=None):
            assert tool_name == "demo.echo"
            assert arguments == {"text": "ping"}
            assert agent_name == "__stackvm_script__.tool_script"
            return {"success": True, "text": "pong"}

    engine._tool_runtime = _ToolRuntime()
    result = engine.run_stackvm_target("script", "tool_script", debug=True)

    assert result["output"] == "pong"
    assert result["last_tool_result"] == {"success": True, "text": "pong"}
    assert result["run_summary"]["runtime_effect_history"][-1]["source"] == "standalone-vm"


def test_run_stackvm_script_standalone_supports_portable_llm_call(tmp_path: Path):
    engine = _make_engine(tmp_path)
    engine.create_stackvm_script("llm_script", entry="main")
    engine.update_stackvm_script(
        "llm_script",
        source_text='[ "Say hi" llm-call answer ] "main" define\n',
    )

    class _Router:
        default_profile_name = "default"

        def generate(self, *, profile_name, prompt):
            assert profile_name == "default"
            assert prompt == "Say hi"
            return "hello from llm"

        def get_last_generation_info(self):
            return {
                "model": "gpt-test",
                "profile_name": "default",
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                "estimated_cost_usd": 0.02,
            }

    engine._llm_router = _Router()
    result = engine.run_stackvm_target("script", "llm_script", debug=True)

    assert result["output"] == "hello from llm"
    assert result["run_summary"]["llm_usage"] == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
