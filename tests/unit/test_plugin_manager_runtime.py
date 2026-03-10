from __future__ import annotations

from pathlib import Path

from pocketcode.core.plugin_manager import PluginManager


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_manager(tmp_path: Path) -> PluginManager:
    plugins_root = tmp_path / "plugins"
    return PluginManager(
        config={"runtime": {"plugin_paths": [str(plugins_root)]}},
        workspace_root=tmp_path,
    )


def _make_workspace_plugin_manager(tmp_path: Path) -> PluginManager:
    return PluginManager(
        config={"runtime": {"plugin_paths": [".pocketcode/plugins"]}},
        workspace_root=tmp_path,
    )


class TestPluginManagerRuntimeLoading:
    def test_repo_stackvm_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_example.review")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common"]
        assert flow_def.vm_files == ["vm/tool_loop.md"]

    def test_repo_stackvm_handoff_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        router_def = manager.agents.resolve("stackvm_handoff_example.router")
        delegate_def = manager.agents.resolve("stackvm_handoff_example.delegate")
        assert router_def.execution_mode == "vm"
        assert router_def.vm_entry == "route"
        assert router_def.vm_modules == ["vm/router"]
        assert delegate_def.flow_instance is not None

    def test_repo_stackvm_resilient_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        router_def = manager.agents.resolve("stackvm_resilient_example.router")
        fallback_def = manager.agents.resolve("stackvm_resilient_example.fallback")
        assert router_def.execution_mode == "vm"
        assert router_def.vm_entry == "decide"
        assert router_def.vm_modules == ["vm/common", "vm/router"]
        assert fallback_def.flow_instance is not None

    def test_repo_stackvm_config_router_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        router_def = manager.agents.resolve("stackvm_config_router_example.router")
        delegate_def = manager.agents.resolve("stackvm_config_router_example.delegate")
        fallback_def = manager.agents.resolve("stackvm_config_router_example.fallback")
        assert router_def.execution_mode == "vm"
        assert router_def.vm_entry == "decide"
        assert router_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.flow_instance is not None
        assert fallback_def.flow_instance is not None

    def test_repo_stackvm_nested_router_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        router_def = manager.agents.resolve("stackvm_nested_router_example.router")
        delegate_def = manager.agents.resolve("stackvm_nested_router_example.delegate")
        fallback_def = manager.agents.resolve("stackvm_nested_router_example.fallback")
        assert router_def.execution_mode == "vm"
        assert router_def.vm_entry == "decide"
        assert router_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.flow_instance is not None
        assert fallback_def.flow_instance is not None

    def test_repo_stackvm_tool_normalize_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_tool_normalize_example.normalize")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common", "vm/router"]

    def test_repo_stackvm_normalize_handoff_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        router_def = manager.agents.resolve("stackvm_normalize_handoff_example.normalize")
        enabled_def = manager.agents.resolve("stackvm_normalize_handoff_example.enabled_delegate")
        disabled_def = manager.agents.resolve("stackvm_normalize_handoff_example.disabled_delegate")
        assert router_def.execution_mode == "vm"
        assert router_def.vm_entry == "decide"
        assert router_def.vm_modules == ["vm/common", "vm/router"]
        assert enabled_def.flow_instance is not None
        assert disabled_def.flow_instance is not None

    def test_repo_stackvm_normalize_ask_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_normalize_ask_example.normalize")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common", "vm/router"]

    def test_repo_stackvm_normalize_confirm_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_normalize_confirm_example.normalize")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common", "vm/router"]

    def test_repo_stackvm_buttons_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_buttons_example.normalize")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common", "vm/router"]

    def test_repo_stackvm_prompt_return_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_prompt_return_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_prompt_return_example.confirm_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_repo_stackvm_delegate_return_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_delegate_return_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_delegate_return_example.confirm_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_repo_stackvm_checklist_return_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_checklist_return_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_checklist_return_example.checklist_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_repo_stackvm_radio_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        flow_def = manager.agents.resolve("stackvm_radio_example.normalize")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common", "vm/router"]

    def test_repo_stackvm_checklist_handoff_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_checklist_handoff_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_checklist_handoff_example.delegate_route")
        approve_def = manager.agents.resolve("stackvm_checklist_handoff_example.approve_route")
        review_def = manager.agents.resolve("stackvm_checklist_handoff_example.review_route")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.flow_instance is not None
        assert approve_def.flow_instance is not None
        assert review_def.flow_instance is not None

    def test_repo_stackvm_structured_return_routing_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_structured_return_routing_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_structured_return_routing_example.confirm_delegate")
        approve_def = manager.agents.resolve("stackvm_structured_return_routing_example.approve_route")
        escalate_def = manager.agents.resolve("stackvm_structured_return_routing_example.escalate_route")
        review_def = manager.agents.resolve("stackvm_structured_return_routing_example.review_route")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]
        assert approve_def.flow_instance is not None
        assert escalate_def.flow_instance is not None
        assert review_def.flow_instance is not None

    def test_repo_stackvm_structured_return_finalize_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_structured_return_finalize_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_structured_return_finalize_example.confirm_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_repo_stackvm_nested_structured_return_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_nested_structured_return_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_nested_structured_return_example.confirm_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_repo_stackvm_nested_structured_return_routing_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_nested_structured_return_routing_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_nested_structured_return_routing_example.confirm_delegate")
        approve_def = manager.agents.resolve("stackvm_nested_structured_return_routing_example.approve_route")
        escalate_def = manager.agents.resolve("stackvm_nested_structured_return_routing_example.escalate_route")
        review_def = manager.agents.resolve("stackvm_nested_structured_return_routing_example.review_route")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]
        assert approve_def.flow_instance is not None
        assert escalate_def.flow_instance is not None
        assert review_def.flow_instance is not None

    def test_repo_stackvm_multistage_pipeline_example_plugin_loads(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[2]
        examples_root = repo_root / "examples"
        manager = PluginManager(
            config={"runtime": {"plugin_paths": [str(examples_root)]}},
            workspace_root=tmp_path,
        )

        manager.load()

        normalize_def = manager.agents.resolve("stackvm_multistage_pipeline_example.normalize")
        delegate_def = manager.agents.resolve("stackvm_multistage_pipeline_example.confirm_delegate")
        assert normalize_def.execution_mode == "vm"
        assert normalize_def.vm_entry == "decide"
        assert normalize_def.vm_modules == ["vm/common", "vm/router"]
        assert delegate_def.execution_mode == "vm"
        assert delegate_def.vm_entry == "decide"
        assert delegate_def.vm_modules == ["vm/delegate"]

    def test_disabled_plugin_directory_is_not_loaded(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "hidden.disabled"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: hidden",
                    'description: "disabled plugin"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "hidden.planner" not in manager.agents

    def test_reload_refreshes_dynamic_tool_modules(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "reloadplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: reloadplug",
                    'description: "reload test"',
                    "tools:",
                    '  greet: "tools/greet.py:greet"',
                ]
            ),
        )
        tool_file = plugin_root / "tools" / "greet.py"
        _write(tool_file, "def greet():\n    return 'v1'\n")

        manager = _make_manager(tmp_path)
        manager.load()
        assert manager.tools.resolve("reloadplug.greet")() == "v1"

        _write(tool_file, "def greet():\n    return 'v2'\n")
        manager.load()
        assert manager.tools.resolve("reloadplug.greet")() == "v2"

    def test_manifest_markdown_tool_loads_metadata_and_handler(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "marktool"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: marktool",
                    'description: "markdown tool test"',
                    "tools:",
                    '  greet: "tools/greet.md"',
                ]
            ),
        )
        _write(
            plugin_root / "tools" / "greet.md",
            """---
handler: greet.py:greet
description: Greeting tool
---

```yaml schema
type: object
properties:
  name:
    type: string
required:
  - name
```
""",
        )
        _write(
            plugin_root / "tools" / "greet.py",
            "def greet(name):\n    return f'hello {name}'\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("marktool.greet").execute(name="Ada") == "hello Ada"

    def test_manifest_markdown_flow_loads_prompt_and_graph_metadata(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "markflow"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: markflow",
                    'description: "markdown flow test"',
                    "flows:",
                    "  planner:",
                    '    markdown: "flows/planner.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.md",
            """---
module: planner.py
entry_fn: create_flow
llm_profile: fast
---
Plan carefully.

```mermaid graph
graph TD
  Start --> End
```
""",
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.agents.resolve("markflow.planner")
        assert flow_def.system_prompt == "Plan carefully."
        assert flow_def.metadata["markdown_graphs"][0]["language"] == "mermaid"

    def test_manifest_markdown_vm_flow_loads_vm_definition(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "vmflow"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: vmflow",
                    'description: "markdown vm flow test"',
                    "flows:",
                    "  planner:",
                    '    markdown: "flows/planner.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.md",
            """---
name: planner
llm_profile: fast
---
Plan carefully.

```vm
"done" answer
```
""",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.agents.resolve("vmflow.planner")
        assert flow_def.execution_mode == "vm"
        assert flow_def.flow_instance is None
        assert flow_def.vm_source == '"done" answer'

    def test_manifest_markdown_vm_flow_preserves_module_refs(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "vmflowrefs"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: vmflowrefs",
                    'description: "markdown vm flow refs test"',
                    "flows:",
                    "  planner:",
                    '    markdown: "flows/planner.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.md",
            """---
name: planner
vm_entry: decide
vm_modules:
  - vm/common
vm_files:
  - vm/tail.md
---

```vm
[ "ok" answer ] "decide" define
```
""",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.agents.resolve("vmflowrefs.planner")
        assert flow_def.execution_mode == "vm"
        assert flow_def.vm_entry == "decide"
        assert flow_def.vm_modules == ["vm/common"]
        assert flow_def.vm_files == ["vm/tail.md"]

    def test_manifest_markdown_graph_flow_builds_executable_flow_instance(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "graphflow"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: graphflow",
                    'description: "markdown graph flow test"',
                    "flows:",
                    "  planner:",
                    '    markdown: "flows/planner.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.md",
            """---
nodes:
    route:
        kind: route
        transition_key: requested_path
    "yes":
        kind: output
        message: Approved
    "no":
        kind: output
        message: Rejected
---

```mermaid graph
graph TD
    route -->|yes| yes
    route -->|no| no
```
""",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.agents.resolve("graphflow.planner")
        shared = {"requested_path": "yes"}

        assert flow_def.flow_instance is not None
        assert flow_def.flow_instance.run(shared) == "final_answer"
        assert shared["final_answer"] == "Approved"

    def test_workspace_markdown_tool_is_loaded(self, tmp_path):
        _write(
            tmp_path / ".pocketcode" / "tools" / "helpers" / "echo.md",
            """---
handler: echo.py:echo_text
description: Echo helper
---

```yaml schema
type: object
properties:
  text:
    type: string
required:
  - text
```
""",
        )
        _write(
            tmp_path / ".pocketcode" / "tools" / "helpers" / "echo.py",
            "def echo_text(text):\n    return {'text': text}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("workspace.helpers.echo").execute(text="ok") == {"text": "ok"}

    def test_workspace_markdown_vm_flow_is_loaded(self, tmp_path):
        _write(
            tmp_path / ".pocketcode" / "flows" / "triage.md",
            """---
name: triage
description: Workspace VM flow
---

```vm
"Workspace flow ready" answer
```
""",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.flows.resolve("workspace.triage")
        assert flow_def.execution_mode == "vm"
        assert flow_def.flow_instance is None
        assert flow_def.vm_source == '"Workspace flow ready" answer'

    def test_workspace_markdown_flow_is_loaded(self, tmp_path):
        _write(
            tmp_path / ".pocketcode" / "flows" / "triage.md",
            """---
name: triage
nodes:
    start:
        kind: noop
    done:
        kind: output
        message: Workspace flow ready
---

```mermaid graph
graph TD
    start --> done
```
""",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        flow_def = manager.flows.resolve("workspace.triage")
        shared = {}
        assert flow_def.flow_instance is not None
        assert flow_def.flow_instance.run(shared) == "final_answer"
        assert shared["final_answer"] == "Workspace flow ready"

    def test_prompt_registry_loads_manifest_prompts(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "promptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: promptplug",
                    'description: "prompt test"',
                    "prompts:",
                    '  system: "prompts/system.md"',
                ]
            ),
        )
        _write(plugin_root / "prompts" / "system.md", "You are promptplug.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.prompts.resolve("promptplug.system") == "You are promptplug.\n"

    def test_workspace_prompt_registry_loads_dot_pocketcode_prompts(self, tmp_path):
        _write(tmp_path / ".pocketcode" / "prompts" / "shared.md", "Shared workspace prompt.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.prompts.resolve("workspace.shared") == "Shared workspace prompt.\n"
        assert manager.prompts.resolve("resource_root.pocketcode.shared") == "Shared workspace prompt.\n"

    def test_additional_resource_root_prompts_and_tools_are_loaded(self, tmp_path):
        _write(tmp_path / ".pocketflow" / "prompts" / "review.md", "Flow review prompt.\n")
        _write(
            tmp_path / ".pocketflow" / "tools" / "extras.py",
            "def pocketflow_tool():\n"
            "    return {'success': True, 'source': 'pocketflow'}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.prompts.resolve("resource_root.pocketflow.review") == "Flow review prompt.\n"
        assert manager.tools.resolve("resource_root.pocketflow.pocketflow_tool")() == {
            "success": True,
            "source": "pocketflow",
        }

    def test_plugins_inside_additional_resource_root_are_auto_discovered(self, tmp_path):
        plugin_root = tmp_path / ".pocketflow" / "plugins" / "flowplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: flowplug",
                    'description: "resource-root plugin"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "flowplug.planner" in manager.agents

    def test_workspace_ignore_rules_filter_and_reinclude_workspace_resources(self, tmp_path):
        _write(
            tmp_path / ".pocketcode" / ".pocketcodeignore",
            "\n".join(
                [
                    "prompts/*.md",
                    "!prompts/keep.md",
                    "tools/*.py",
                    "!tools/keep.py",
                ]
            ),
        )
        _write(tmp_path / ".pocketcode" / "prompts" / "drop.md", "Drop.\n")
        _write(tmp_path / ".pocketcode" / "prompts" / "keep.md", "Keep.\n")
        _write(
            tmp_path / ".pocketcode" / "tools" / "drop.py",
            "def drop_tool(text):\n"
            "    return {'success': True, 'result': text}\n",
        )
        _write(
            tmp_path / ".pocketcode" / "tools" / "keep.py",
            "def keep_tool(text):\n"
            "    return {'success': True, 'result': text}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "workspace.drop" not in manager.prompts
        assert manager.prompts.resolve("workspace.keep") == "Keep.\n"
        assert "workspace.drop_tool" not in manager.tools
        assert manager.tools.resolve("workspace.keep_tool")("ok") == {
            "success": True,
            "result": "ok",
        }

    def test_workspace_prompt_files_are_available_to_plugin_agents(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspacepromptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspacepromptplug",
                    'description: "workspace prompt fallback test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompt_files:",
                    '      - "shared.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(tmp_path / ".pocketcode" / "prompts" / "shared.md", "Use the shared workspace instructions.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("workspacepromptplug.planner").system_prompt == "Use the shared workspace instructions."

    def test_prompt_resource_refs_are_available_to_plugin_agents(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "promptrefplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: promptrefplug",
                    'description: "prompt resource ref test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompt_files:",
                    '      - "prompt:resource_root.pocketcode.shared"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(tmp_path / ".pocketcode" / "prompts" / "shared.md", "Prompt ref instructions.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("promptrefplug.planner").system_prompt == "Prompt ref instructions."

    def test_dot_pocketcode_ignore_applies_to_workspace_plugin_resources(self, tmp_path):
        plugin_root = tmp_path / ".pocketcode" / "plugins" / "workspaceignore"
        _write(
            tmp_path / ".pocketcode" / ".pocketcodeignore",
            "\n".join(
                [
                    "plugins/workspaceignore/prompts/*.md",
                    "!plugins/workspaceignore/prompts/keep.md",
                    "plugins/workspaceignore/tools/*.py",
                    "!plugins/workspaceignore/tools/keep.py",
                ]
            ),
        )
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceignore",
                    'description: "workspace plugin ignore test"',
                    "tools:",
                    '  drop_tool: "tools/drop.py:drop_tool"',
                    '  keep_tool: "tools/keep.py:keep_tool"',
                    "prompts:",
                    '  drop: "prompts/drop.md"',
                    '  keep: "prompts/keep.md"',
                ]
            ),
        )
        _write(plugin_root / "tools" / "drop.py", "def drop_tool():\n    return 'drop'\n")
        _write(plugin_root / "tools" / "keep.py", "def keep_tool():\n    return 'keep'\n")
        _write(plugin_root / "prompts" / "drop.md", "Drop.\n")
        _write(plugin_root / "prompts" / "keep.md", "Keep.\n")

        manager = _make_workspace_plugin_manager(tmp_path)
        manager.load()

        assert "workspaceignore.drop_tool" not in manager.tools
        assert manager.tools.resolve("workspaceignore.keep_tool")() == "keep"
        assert "workspaceignore.drop" not in manager.prompts
        assert manager.prompts.resolve("workspaceignore.keep") == "Keep.\n"

    def test_workspace_dot_pocketcode_tools_register_and_are_visible_to_all_agents(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspaceplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceplug",
                    'description: "workspace tool fallback test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(
            tmp_path / ".pocketcode" / "tools" / "shared_tools.py",
            "def workspace_echo(text):\n"
            "    return {'success': True, 'result': text}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("workspace.workspace_echo")("hello") == {
            "success": True,
            "result": "hello",
        }
        assert "workspace.workspace_echo" in manager.resolve_tools_for_agent("workspaceplug::planner")
        assert "workspace.workspace_echo" in manager.resolve_tools_for_agent("flow:workspaceplug.planner")

    def test_typed_tool_refs_in_flow_manifest_resolve(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "typedtoolplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: typedtoolplug",
                    'description: "typed tool ref test"',
                    "tools:",
                    '  planner_tool: "tools/planner_tool.py:planner_tool"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    tools:",
                    '      - "tool:planner_tool"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(
            plugin_root / "tools" / "planner_tool.py",
            "def planner_tool():\n"
            "    return {'success': True}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.resolve_tools_for_agent("flow:typedtoolplug.planner") == ["typedtoolplug.planner_tool"]
        assert manager.agents.resolve("typedtoolplug.planner").tools == ["typedtoolplug.planner_tool"]

    def test_invalid_handoff_agents_are_dropped_after_load(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "handoffplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: handoffplug",
                    'description: "handoff validation test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    handoff_agents:",
                    '      - "missing"',
                    '      - "router"',
                    "  router:",
                    '    module: "flows/router.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        planner_flow = (
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n"
        )
        _write(plugin_root / "flows" / "planner.py", planner_flow)
        _write(plugin_root / "flows" / "router.py", planner_flow)

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("handoffplug.planner").handoff_agents == ["handoffplug.router"]

    def test_invalid_default_agent_prompt_refs_are_dropped_after_load(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "defaultpromptplug"
        _write(tmp_path / ".pocketcode" / "prompts" / "keep.md", "Keep prompt.\n")
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: defaultpromptplug",
                    'description: "default prompt validation test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    default_agent:",
                    '      name: "defaultpromptplug::planner"',
                    "      extra_prompts:",
                    '        - "prompt:resource_root.pocketcode.missing"',
                    '        - "prompt:resource_root.pocketcode.keep"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        default_agent = manager.agents.resolve("defaultpromptplug.planner").default_agent_profile
        assert default_agent is not None
        assert default_agent.extra_prompts == ["prompt:resource_root.pocketcode.keep"]

    def test_workspace_tools_support_explicit_tool_exports(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspaceexports"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceexports",
                    'description: "workspace tool export test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(
            tmp_path / ".pocketcode" / "tools" / "exports.py",
            "class PickTool:\n"
            "    name = 'pick'\n"
            "    def __call__(self):\n"
            "        return {'success': True, 'picked': True}\n\n"
            "def ignored_tool():\n"
            "    return {'success': True, 'ignored': True}\n\n"
            "TOOLS = {'pick_tool': PickTool()}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("workspace.pick_tool")() == {
            "success": True,
            "picked": True,
        }
        assert "workspace.pick_tool" in manager.resolve_tools_for_agent("workspaceexports::planner")

    def test_workspace_level_ignore_rules_apply_to_external_plugin_resources(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "ignoreplug"
        _write(
            tmp_path / ".pocketcodeignore",
            "\n".join(
                [
                    "ignoreplug/tools/*.py",
                    "!ignoreplug/tools/keep.py",
                    "ignoreplug/prompts/*.md",
                    "!ignoreplug/prompts/keep.md",
                ]
            ),
        )
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: ignoreplug",
                    'description: "ignore test"',
                    "tools:",
                    '  drop_tool: "tools/drop.py:drop_tool"',
                    '  keep_tool: "tools/keep.py:keep_tool"',
                    "prompts:",
                    '  drop: "prompts/drop.md"',
                    '  keep: "prompts/keep.md"',
                ]
            ),
        )
        _write(plugin_root / "tools" / "drop.py", "def drop_tool():\n    return 'drop'\n")
        _write(plugin_root / "tools" / "keep.py", "def keep_tool():\n    return 'keep'\n")
        _write(plugin_root / "prompts" / "drop.md", "Drop.\n")
        _write(plugin_root / "prompts" / "keep.md", "Keep.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert "ignoreplug.drop_tool" not in manager.tools
        assert manager.tools.resolve("ignoreplug.keep_tool")() == "keep"
        assert "ignoreplug.drop" not in manager.prompts
        assert manager.prompts.resolve("ignoreplug.keep") == "Keep.\n"

    def test_agent_prompts_alias_loads_system_prompt(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "agentpromptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: agentpromptplug",
                    'description: "agent prompt test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompts:",
                    '      - "prompts/system.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(plugin_root / "prompts" / "system.md", "Plan carefully.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("agentpromptplug.planner").system_prompt == "Plan carefully."

    def test_invalid_manifest_plugin_is_skipped(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "brokenplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: brokenplug",
                    'description: "broken"',
                    "flows:",
                    "  broken:",
                    '    module: "flows/broken.py"',
                ]
            ),
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "brokenplug.broken" not in manager.agents
