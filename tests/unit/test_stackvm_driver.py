from __future__ import annotations

from pathlib import Path

from pocketcode.core.stackvm_driver import (
    StackVmStandaloneHostConfig,
    StackVmStandaloneRuntime,
    StackVmStandaloneSession,
    build_stackvm_standalone_host_config,
    compile_stackvm_program,
    compile_stackvm_program_target,
    create_stackvm_standalone_runtime,
    create_stackvm_standalone_runtime_target,
    create_stackvm_standalone_session,
    create_stackvm_standalone_session_target,
    restore_stackvm_standalone_session,
    restore_stackvm_standalone_session_target,
    run_compiled_stackvm_program,
    run_stackvm_program,
    run_stackvm_program_target,
)
from pocketcode.core.stackvm_stdlib import load_stackvm_stdlib_manifest, validate_stackvm_stdlib_manifest


def test_run_stackvm_program_answers_from_request(tmp_path: Path):
    result = run_stackvm_program(
        source='[ request answer ] "main" define\n',
        entry="main",
        request="hello standalone",
        workspace_root=tmp_path,
        agent_name="demo.standalone",
    )

    assert result.output == "hello standalone"
    assert result.final_answer == "hello standalone"
    assert result.run_summary["current_agent"] == "demo.standalone"
    assert result.last_vm_analysis["standalone_script_compatible"] is True
    assert result.run_summary["stackvm_runtime"] == {
        "path": "standalone-script",
        "source": "standalone-vm",
        "standalone_session_active": False,
    }
    assert result.run_summary["stackvm_static_runtime_correlation"]["runtime_scope_count"] == 0


def test_run_compiled_stackvm_program_supports_prompt_and_tool_hooks(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "demo.echo" "{text: ping}" yaml> tool-call "text" dict-get prompt-user answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    class _ToolRuntime:
        tools = {"demo.echo": object()}

        def describe_tools(self, tool_names):
            return [{"name": name} for name in tool_names]

        def execute_tool(self, tool_name, arguments, shared_store, auto_confirm=False, agent_name=None):
            assert tool_name == "demo.echo"
            assert arguments == {"text": "ping"}
            assert agent_name == "demo.portable"
            return {"success": True, "text": "pong"}

    interaction_requests: list[dict[str, object]] = []

    def _interaction_handler(request):
        interaction_requests.append(dict(request))
        return {"kind": "text", "value": "typed response", "raw_input": "typed response"}

    result = run_compiled_stackvm_program(
        compiled=compiled,
        request="ignored",
        workspace_root=tmp_path,
        agent_name="demo.portable",
        host_config=StackVmStandaloneHostConfig(
            tool_runtime=_ToolRuntime(),
            interaction_handler=_interaction_handler,
            auto_confirm_tools=True,
        ),
    )

    assert result.output == "typed response"
    assert result.last_tool_result == {"success": True, "text": "pong"}
    assert interaction_requests == [{"kind": "text", "prompt": "pong", "allow_empty": True}]
    assert result.run_summary["runtime_effect_history"][-1]["source"] == "standalone-vm"


def test_build_stackvm_standalone_host_config_derives_tool_definitions():
    class _ToolRuntime:
        tools = {"demo.echo": object(), "demo.other": object()}

        def describe_tools(self, tool_names):
            return [{"name": name} for name in tool_names]

    config = build_stackvm_standalone_host_config(
        tool_runtime=_ToolRuntime(),
        auto_confirm_tools=True,
    )

    assert config.auto_confirm_tools is True
    assert config.tool_definitions == [{"name": "demo.echo"}, {"name": "demo.other"}]


def test_create_stackvm_standalone_runtime_reuses_compiled_program_with_fresh_seeded_store(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "count" 0 shared-or 1 + dup "count" shared! answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    runtime = create_stackvm_standalone_runtime(
        compiled=compiled,
        workspace_root=tmp_path,
        agent_name="demo.runtime",
        shared_store_seed={"prefix": "seeded"},
    )

    assert isinstance(runtime, StackVmStandaloneRuntime)

    first = runtime.run(request="first")
    second = runtime.run(request="second")

    assert first.output == "1"
    assert second.output == "1"
    assert first.shared_store["prefix"] == "seeded"
    assert second.shared_store["prefix"] == "seeded"
    assert first.shared_store["run_id"] != second.shared_store["run_id"]


def test_run_compiled_stackvm_program_supports_llm_hook_and_usage_summary(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "Summarize this" llm-call answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    class _Router:
        default_profile_name = "default"

        def generate(self, *, profile_name, prompt):
            assert profile_name == "default"
            assert prompt == "System line\n\nSummarize this"
            return "llm result"

        def get_last_generation_info(self):
            return {
                "model": "gpt-test",
                "profile_name": "default",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                "estimated_cost_usd": 0.01,
            }

    result = run_compiled_stackvm_program(
        compiled=compiled,
        workspace_root=tmp_path,
        host_config=StackVmStandaloneHostConfig(
            llm_router=_Router(),
            system_prompt="System line",
        ),
    )

    assert result.output == "llm result"
    assert result.run_summary["llm_usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert result.run_summary["llm_cost_usd"] == 0.01


def test_run_compiled_stackvm_program_host_config_merges_with_explicit_overrides(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "Say hi" llm-call answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    class _Router:
        default_profile_name = "default"

        def generate(self, *, profile_name, prompt):
            assert profile_name == "override"
            assert prompt == "Override prompt\n\nSay hi"
            return "override result"

        def get_last_generation_info(self):
            return {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    result = run_compiled_stackvm_program(
        compiled=compiled,
        workspace_root=tmp_path,
        host_config=StackVmStandaloneHostConfig(
            llm_router=_Router(),
            llm_profile="default",
            system_prompt="Base prompt",
        ),
        llm_profile="override",
        system_prompt="Override prompt",
    )

    assert result.output == "override result"


def test_create_stackvm_standalone_runtime_target_compiles_once_and_runs_module_target(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "decorate.vm").write_text(
        '\n'.join(
            [
                '"stdlib.decorate" module',
                '[ "decorated: " swap concat ] "prefix" define',
                '"prefix" export',
            ]
        ),
        encoding="utf-8",
    )
    namespace_vm_root = tmp_path / "example_ns" / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.decorate.prefix" import',
                '[ request prefix answer ] "main" define',
                '"main" export',
            ]
        ),
        encoding="utf-8",
    )

    runtime = create_stackvm_standalone_runtime_target(
        vm_entry="router.main",
        vm_modules=["stdlib.decorate", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
        workspace_root=tmp_path,
        agent_name="demo.module_runtime",
    )

    first = runtime.run(request="hello")
    second = runtime.run(request="again")

    assert first.output == "decorated: hello"
    assert second.output == "decorated: again"
    assert any(path.endswith("vm/stdlib/decorate.vm") for path in runtime.compiled.source_files)


def test_create_stackvm_standalone_session_persists_shared_state_and_transcript(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "count" 0 shared-or 1 + dup "count" shared! "count" shared@ answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    runtime = create_stackvm_standalone_runtime(
        compiled=compiled,
        workspace_root=tmp_path,
        agent_name="demo.session_runtime",
    )
    session = create_stackvm_standalone_session(runtime=runtime, title="Demo Session")

    assert isinstance(session, StackVmStandaloneSession)

    first = session.run(request="hello")
    second = session.run(request="again")

    assert first.output == "1"
    assert second.output == "2"
    assert session.shared_store_state["count"] == 2
    assert [item["role"] for item in session.transcript] == ["user", "assistant", "user", "assistant"]
    assert session.shared_store_state["standalone_transcript_text"] == (
        "User: hello\nAssistant: 1\nUser: again\nAssistant: 2"
    )
    summary = second.run_summary["standalone_session"]
    assert summary["active"] is True
    assert summary["session_id"] == session.session_id
    assert summary["title"] == "Demo Session"
    assert summary["transcript_entries"] == 3
    assert summary["transcript_chars"] == len("User: hello\nAssistant: 1\nUser: again")
    assert summary["persistent_key_count"] >= 1


def test_create_stackvm_standalone_session_target_runs_module_program_with_seeded_transcript(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "decorate.vm").write_text(
        '\n'.join(
            [
                '"stdlib.decorate" module',
                '[ "seen: " swap concat ] "prefix" define',
                '"prefix" export',
            ]
        ),
        encoding="utf-8",
    )
    namespace_vm_root = tmp_path / "example_ns" / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.decorate.prefix" import',
                '[ "standalone_transcript_text" shared@ prefix answer ] "main" define',
                '"main" export',
            ]
        ),
        encoding="utf-8",
    )

    session = create_stackvm_standalone_session_target(
        vm_entry="router.main",
        vm_modules=["stdlib.decorate", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
        workspace_root=tmp_path,
        transcript=[{"role": "user", "content": "before"}],
    )

    result = session.run(request="next")

    assert result.output == "seen: User: before\nUser: next"
    assert session.transcript[-1]["role"] == "assistant"


def test_stackvm_standalone_session_snapshot_and_restore(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "count" 0 shared-or 1 + dup "count" shared! answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    runtime = create_stackvm_standalone_runtime(
        compiled=compiled,
        workspace_root=tmp_path,
        agent_name="demo.snapshot_runtime",
    )
    session = create_stackvm_standalone_session(runtime=runtime, title="Snapshot Session")
    session.run(request="first")
    snapshot = session.snapshot()

    restored = restore_stackvm_standalone_session(runtime=runtime, snapshot=snapshot)
    result = restored.run(request="second")

    assert restored.session_id == session.session_id
    assert restored.title == "Snapshot Session"
    assert result.output == "2"
    assert [item["content"] for item in restored.transcript] == ["first", "1", "second", "2"]


def test_restore_stackvm_standalone_session_target_restores_module_session(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "decorate.vm").write_text(
        '\n'.join(
            [
                '"stdlib.decorate" module',
                '[ "memory: " swap concat ] "prefix" define',
                '"prefix" export',
            ]
        ),
        encoding="utf-8",
    )
    namespace_vm_root = tmp_path / "example_ns" / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.decorate.prefix" import',
                '[ "standalone_transcript_text" shared@ prefix answer ] "main" define',
                '"main" export',
            ]
        ),
        encoding="utf-8",
    )

    original = create_stackvm_standalone_session_target(
        vm_entry="router.main",
        vm_modules=["stdlib.decorate", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
        workspace_root=tmp_path,
        transcript=[{"role": "user", "content": "before"}],
    )
    original.run(request="next")
    snapshot = original.snapshot()

    restored = restore_stackvm_standalone_session_target(
        snapshot=snapshot,
        vm_entry="router.main",
        vm_modules=["stdlib.decorate", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
        workspace_root=tmp_path,
    )
    result = restored.run(request="after")

    assert result.output.startswith("memory: User: before")
    assert "User: next" in result.output
    assert "User: after" in result.output


def test_compile_stackvm_program_target_loads_vm_modules_from_workspace_root(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "greeting.vm").write_text(
        '\n'.join(
            [
                '"stdlib.greeting" module',
                '[ "hello from stdlib" ] "message" define',
                '"message" export',
            ]
        ),
        encoding="utf-8",
    )
    namespace_vm_root = tmp_path / "example_ns" / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.greeting.message" import',
                '[ message answer ] "main" define',
                '"main" export',
            ]
        ),
        encoding="utf-8",
    )

    compiled = compile_stackvm_program_target(
        vm_entry="router.main",
        vm_modules=["stdlib.greeting", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
    )

    assert compiled.entry == "router.main"
    assert '"stdlib.greeting.message" define' in compiled.source
    assert any(path.endswith("vm/stdlib/greeting.vm") for path in compiled.source_files)
    assert compiled.expansion_metadata["expansion_trace"] == []


def test_run_stackvm_program_target_executes_loaded_vm_module_program(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "decorate.vm").write_text(
        '\n'.join(
            [
                '"stdlib.decorate" module',
                '[ "decorated: " swap concat ] "prefix" define',
                '"prefix" export',
            ]
        ),
        encoding="utf-8",
    )
    namespace_vm_root = tmp_path / "example_ns" / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.decorate.prefix" import',
                '[ request prefix answer ] "main" define',
                '"main" export',
            ]
        ),
        encoding="utf-8",
    )

    result = run_stackvm_program_target(
        vm_entry="router.main",
        vm_modules=["stdlib.decorate", "vm/router"],
        base_dir=tmp_path / "example_ns",
        search_roots=[tmp_path],
        request="hello",
        workspace_root=tmp_path,
        agent_name="demo.module",
    )

    assert result.output == "decorated: hello"
    assert result.final_answer == "decorated: hello"
    assert result.run_summary["current_agent"] == "demo.module"
    assert any(path.endswith("vm/stdlib/decorate.vm") for path in result.last_vm_sources)


def test_run_compiled_stackvm_program_debug_trace_includes_source_locations(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ "hello" answer ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    result = run_compiled_stackvm_program(
        compiled=compiled,
        workspace_root=tmp_path,
        debug=True,
    )

    assert result.trace_count >= 5
    assert result.run_summary["vm_trace_scope_summaries"]
    assert any(item["scope"] == "main > word:main" for item in result.run_summary["vm_trace_scope_summaries"])
    assert result.trace[3]["scope"] == "main > word:main"
    assert result.trace[3]["stack_delta"] == {"depth_change": 1, "popped": [], "pushed": ["hello"]}
    assert result.trace[3]["location"] == "line 1, cols 3-9"
    assert result.trace[3]["authored_location"] == "line 1, cols 3-9"
    assert result.trace[4]["scope"] == "main > word:main"
    assert result.trace[4]["stack_delta"] == {"depth_change": -1, "popped": ["hello"], "pushed": []}
    assert result.trace[4]["location"] == "line 1, cols 11-16"
    assert result.trace[4]["authored_location"] == "line 1, cols 11-16"


def test_run_compiled_stackvm_program_debug_records_runtime_decisions(tmp_path: Path):
    compiled = compile_stackvm_program(
        source='[ True [ "yes" answer ] [ "no" answer ] if ] "main" define\n',
        source_files=["inline.vm"],
        entry="main",
    )

    result = run_compiled_stackvm_program(
        compiled=compiled,
        workspace_root=tmp_path,
        debug=True,
    )

    decisions = result.run_summary["vm_trace_decisions"]
    assert decisions
    assert decisions[0]["decision"] == "if-branch"
    assert decisions[0]["scope"] == "main > word:main > if:true"
    assert decisions[0]["value"] is True


def test_load_stackvm_stdlib_manifest_reads_workspace_manifest(tmp_path: Path):
    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.2.0",
                "module_root: vm/stdlib",
                "modules:",
                "  - name: stdlib.demo",
                "    ref: vm/stdlib/demo",
                "    file: vm/stdlib/demo.vm",
                "    summary: Demo helpers.",
                "    exports:",
                "      - one",
                "      - two",
                "    dependencies: []",
            ]
        ),
        encoding="utf-8",
    )

    manifest = load_stackvm_stdlib_manifest(tmp_path)

    assert manifest["package"] == "stackvm-stdlib"
    assert manifest["version"] == "0.2.0"
    assert manifest["module_root"] == "vm/stdlib"
    assert manifest["modules"][0]["name"] == "stdlib.demo"
    assert manifest["modules"][0]["exports"] == ["one", "two"]
    assert manifest["modules"][0]["dependencies"] == []


def test_validate_stackvm_stdlib_manifest_detects_export_drift(tmp_path: Path):
    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "demo.vm").write_text(
        "\n".join(
            [
                '"stdlib.demo" module',
                '[ "ok" ] "one" define',
                '"one" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.2.0",
                "module_root: vm/stdlib",
                "modules:",
                "  - name: stdlib.demo",
                "    ref: vm/stdlib/demo",
                "    file: vm/stdlib/demo.vm",
                "    summary: Demo helpers.",
                "    exports:",
                "      - one",
                "      - two",
                "    dependencies: []",
            ]
        ),
        encoding="utf-8",
    )

    report = validate_stackvm_stdlib_manifest(tmp_path)

    assert report["valid"] is False
    assert report["error_count"] == 1
    assert report["modules"][0]["valid"] is False
    assert "Manifest exports missing from module" in report["modules"][0]["errors"][0]


def test_validate_stackvm_stdlib_manifest_detects_dependency_drift(tmp_path: Path):
    stdlib_root = tmp_path / "vm" / "stdlib"
    stdlib_root.mkdir(parents=True, exist_ok=True)
    (stdlib_root / "other.vm").write_text(
        "\n".join(
            [
                '"stdlib.other" module',
                '[ "ok" ] "helper" define',
                '"helper" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "demo.vm").write_text(
        "\n".join(
            [
                '"stdlib.demo" module',
                '"stdlib.other.helper" import',
                '[ helper ] "one" define',
                '"one" export',
            ]
        ),
        encoding="utf-8",
    )
    (stdlib_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.2.0",
                "module_root: vm/stdlib",
                "modules:",
                "  - name: stdlib.other",
                "    ref: vm/stdlib/other",
                "    file: vm/stdlib/other.vm",
                "    summary: Other helpers.",
                "    exports:",
                "      - helper",
                "    dependencies: []",
                "  - name: stdlib.demo",
                "    ref: vm/stdlib/demo",
                "    file: vm/stdlib/demo.vm",
                "    summary: Demo helpers.",
                "    exports:",
                "      - one",
                "    dependencies: []",
            ]
        ),
        encoding="utf-8",
    )

    report = validate_stackvm_stdlib_manifest(tmp_path)

    assert report["valid"] is False
    demo = next(item for item in report["modules"] if item["name"] == "stdlib.demo")
    assert demo["actual_dependencies"] == ["stdlib.other"]
    assert any("Module imports missing from manifest dependencies" in error for error in demo["errors"])
