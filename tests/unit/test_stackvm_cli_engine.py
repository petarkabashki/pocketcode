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

    result = engine.run_stackvm_target("flow", flow_name, debug=True)
    assert result["output"] == "StackVM flow vm_triage ready."
    assert result["trace_count"] > 0


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

    result = engine.run_stackvm_target("script", "hello", debug=True)
    assert result["output"] == "script ok"
    assert result["trace_count"] > 0
