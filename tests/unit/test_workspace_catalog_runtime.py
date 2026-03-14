from __future__ import annotations

from pathlib import Path

from pocketcode.core.workspace_catalog import WorkspaceCatalog


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _manager_for(workspace_root: Path, *workspace_paths: str) -> WorkspaceCatalog:
    return WorkspaceCatalog(
        config={"runtime": {"workspace_paths": list(workspace_paths)}},
        workspace_root=workspace_root,
    )


def _example_namespace_paths() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    examples_root = repo_root / "examples"
    return [str(path) for path in sorted(examples_root.iterdir()) if path.is_dir()]


def test_examples_root_loads_stackvm_example_namespaces(tmp_path):
    manager = _manager_for(tmp_path, *_example_namespace_paths())

    manager.load()

    review_def = manager.agents.resolve("stackvm_example.review")
    normalize_def = manager.agents.resolve("stackvm_tool_normalize_example.normalize")
    handoff_def = manager.agents.resolve("stackvm_handoff_example.delegate")
    assert review_def.execution_mode == "vm"
    assert review_def.vm_modules == ["vm/common"]
    assert normalize_def.vm_module_prefixes == {"vm/common": "common"}
    assert review_def.vm_files == ["vm/tool_loop.md"]
    assert handoff_def.flow_instance is not None


def test_examples_root_loads_programmatic_route_wrappers(tmp_path):
    manager = _manager_for(tmp_path, *_example_namespace_paths())

    manager.load()

    approve_def = manager.agents.resolve("stackvm_structured_return_routing_example.approve_route")
    review_def = manager.agents.resolve("stackvm_checklist_handoff_example.review_route")
    assert approve_def.flow_instance is not None
    assert review_def.flow_instance is not None


def test_examples_root_loads_delegate_vm_wrappers(tmp_path):
    manager = _manager_for(tmp_path, *_example_namespace_paths())

    manager.load()

    delegate_def = manager.agents.resolve("stackvm_prompt_return_example.confirm_delegate")
    assert delegate_def.execution_mode == "vm"
    assert delegate_def.vm_modules == ["vm/delegate"]


def test_workspace_paths_can_point_to_multiple_namespace_roots(tmp_path):
    alpha = tmp_path / ".pocketcode" / "alpha"
    beta = tmp_path / ".pocketcode" / "beta"
    _write(alpha / "review.md", '---\n---\n```vm\n"alpha" answer\n```\n')
    _write(beta / "planner.md", '---\n---\n```vm\n"beta" answer\n```\n')

    manager = _manager_for(tmp_path, str(alpha), str(beta))
    manager.load()

    assert "alpha.review" in manager.agents
    assert "beta.planner" in manager.agents


def test_resource_root_flat_namespace_pack_loads_multiple_namespaces(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(resource_root / "alpha.review.md", '---\n---\n```vm\n"alpha" answer\n```\n')
    _write(resource_root / "beta.plan.md", '---\n---\n```vm\n"beta" answer\n```\n')
    _write(resource_root / "alpha.shared.prompt.md", "Shared alpha prompt")
    _write(
        resource_root / "beta.echo.tool.py",
        "def echo_text(text):\n"
        "    return {'text': text}\n",
    )

    manager = _manager_for(tmp_path, str(resource_root))
    manager.load()

    assert "alpha.review" in manager.agents
    assert "beta.plan" in manager.agents
    assert manager.prompts.resolve("alpha.shared") == "Shared alpha prompt"
    assert manager.tools.resolve("beta.echo_text")(text="ok") == {"text": "ok"}


def test_workspace_markdown_program_can_reference_programmatic_flow_module(tmp_path):
    namespace_root = tmp_path / "sample"
    _write(
        namespace_root / "delegate.py",
        "from pocketflow import Flow, Node\n\n"
        "class _Start(Node):\n"
        "    def prep(self, shared):\n"
        "        return 'ok'\n\n"
        "    def exec(self, value):\n"
        "        return value\n\n"
        "    def post(self, shared, prep_res, exec_res):\n"
        "        shared['final_answer'] = exec_res\n"
        "        return 'final_answer'\n\n"
        "def create_flow():\n"
        "    return Flow(start=_Start())\n",
    )
    _write(
        namespace_root / "delegate.md",
        "\n".join(
            [
                "---",
                "module: delegate.py",
                "entry_fn: create_flow",
                "---",
            ]
        ),
    )

    manager = _manager_for(tmp_path, str(namespace_root))
    manager.load()

    flow_def = manager.agents.resolve("sample.delegate")
    assert flow_def.flow_instance is not None


def test_workspace_markdown_program_can_reference_namespace_tool_modules(tmp_path):
    namespace_root = tmp_path / "sample"
    _write(
        namespace_root / "echo.tool.py",
        "def echo_text(text):\n"
        "    return {'text': text}\n\n"
        "TOOLS = {'echo_text': echo_text}\n",
    )
    _write(
        namespace_root / "review.md",
        "\n".join(
            [
                "---",
                "tools:",
                "  - echo_text",
                "---",
                "",
                "```vm",
                '"ok" answer',
                "```",
            ]
        ),
    )

    manager = _manager_for(tmp_path, str(namespace_root))
    manager.load()

    flow_def = manager.agents.resolve("sample.review")
    assert flow_def.tools == ["sample.echo_text"]


def test_workspace_agents_collection_self_contained_agent_is_executable(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(resource_root / "agents" / "review.agent.md", "---\n---\nInline review prompt.\n\n```vm\n\"ok\" answer\n```\n")
    _write(resource_root / "agents" / "review.prompt.md", "Shared review prompt")
    _write(
        resource_root / "agents" / "review.tool.py",
        "def echo_text(text):\n"
        "    return {'text': text}\n",
    )

    manager = _manager_for(tmp_path)
    manager.load()

    flow_def = manager.agents.resolve("agents.review")
    assert flow_def.execution_mode == "vm"
    assert flow_def.tools == ["resource_root.pocketcode.echo_text"]
    assert "Inline review prompt." in flow_def.system_prompt
    assert "Shared review prompt" in flow_def.system_prompt


def test_workspace_namespace_root_self_contained_agent_registers_as_namespaced_program(tmp_path):
    namespace_root = tmp_path / "sample"
    _write(namespace_root / "reviewer.agent.md", "---\n---\nNamespace agent prompt.\n\n```vm\n\"ns ok\" answer\n```\n")

    manager = _manager_for(tmp_path, str(namespace_root))
    manager.load()

    flow_def = manager.agents.resolve("sample.reviewer")
    assert flow_def.execution_mode == "vm"
    assert flow_def.vm_source == '"ns ok" answer'


def test_resource_root_flat_namespace_pack_self_contained_agent_registers_namespace(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(resource_root / "alpha.review.agent.md", "---\n---\nPack agent prompt.\n\n```vm\n\"pack ok\" answer\n```\n")

    manager = _manager_for(tmp_path, str(resource_root))
    manager.load()

    flow_def = manager.agents.resolve("alpha.review")
    assert flow_def.execution_mode == "vm"
    assert flow_def.vm_source == '"pack ok" answer'


def test_resource_root_flat_conventions_load_prompts_tools_and_flows(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(resource_root / "review.prompt.md", "Review prompt")
    _write(
        resource_root / "review.tool.py",
        "def echo_text(text):\n"
        "    return {'text': text}\n",
    )
    _write(
        resource_root / "review.md",
        "---\n"
        "description: Flat review flow.\n"
        "---\n"
        "Inline prompt.\n\n"
        "```vm\n"
        '"ok" answer\n'
        "```\n",
    )
    _write(
        resource_root / "sample_tool.tool.py",
        "from pocketcode.core.interfaces import BaseTool\n\n"
        "class SampleTool(BaseTool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'sample_tool'\n\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'Sample tool.'\n\n"
        "    @property\n"
        "    def schema(self):\n"
        "        return {'type': 'object', 'properties': {}}\n\n"
        "    def execute(self, **kwargs):\n"
        "        return {'success': True}\n",
    )
    _write(
        resource_root / "sample_tool.tool.md",
        "---\n"
        "name: sample_tool\n"
        "handler: ./sample_tool.tool.py:SampleTool\n"
        "---\n"
        "Tool body.\n",
    )

    manager = _manager_for(tmp_path)
    manager.load()

    flow_def = manager.agents.resolve("resource_root.pocketcode.review")
    assert flow_def.tools == ["resource_root.pocketcode.echo_text"]
    assert "Inline prompt." in flow_def.system_prompt
    assert "Review prompt" in flow_def.system_prompt
    assert manager.prompts.resolve("resource_root.pocketcode.review") == "Review prompt"
    assert manager.tools.resolve("resource_root.pocketcode.sample_tool").name == "sample_tool"


def test_resource_root_collection_folders_load_prompts_and_tools(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(resource_root / "prompts" / "review.md", "Review prompt from folder")
    _write(
        resource_root / "tools" / "checks" / "echo.tool.py",
        "def echo_text(text):\n"
        "    return {'text': text}\n",
    )
    _write(
        resource_root / "tools" / "checks" / "sample.tool.py",
        "from pocketcode.core.interfaces import BaseTool\n\n"
        "class SampleTool(BaseTool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'sample'\n\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'Sample tool.'\n\n"
        "    @property\n"
        "    def schema(self):\n"
        "        return {'type': 'object', 'properties': {}}\n\n"
        "    def execute(self, **kwargs):\n"
        "        return {'success': True}\n",
    )
    _write(
        resource_root / "tools" / "checks" / "sample.tool.md",
        "---\n"
        "handler: ./sample.tool.py:SampleTool\n"
        "---\n"
        "Tool body.\n",
    )

    manager = _manager_for(tmp_path)
    manager.load()

    assert manager.prompts.resolve("resource_root.pocketcode.review") == "Review prompt from folder"
    assert manager.tools.resolve("resource_root.pocketcode.echo_text")(text="ok") == {"text": "ok"}
    assert manager.tools.resolve("resource_root.pocketcode.checks.sample").name == "checks.sample"


def test_resource_root_typed_tool_folder_loads_tools(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(
        resource_root / "tool.git" / "status.tool.py",
        "def git_status():\n"
        "    return {'ok': True}\n",
    )
    _write(
        resource_root / "tool.git" / "describe_impl.tool.py",
        "from pocketcode.core.interfaces import BaseTool\n\n"
        "class DescribeTool(BaseTool):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'describe'\n\n"
        "    @property\n"
        "    def description(self):\n"
        "        return 'Describe tool.'\n\n"
        "    @property\n"
        "    def schema(self):\n"
        "        return {'type': 'object', 'properties': {}}\n\n"
        "    def execute(self, **kwargs):\n"
        "        return {'ok': True}\n",
    )
    _write(
        resource_root / "tool.git" / "describe.tool.md",
        "---\n"
        "handler: ./describe_impl.tool.py:DescribeTool\n"
        "---\n"
        "Tool body.\n",
    )

    manager = _manager_for(tmp_path)
    manager.load()

    assert manager.tools.resolve("resource_root.pocketcode.git_status")() == {"ok": True}
    assert manager.tools.resolve("resource_root.pocketcode.git.describe").name == "git.describe"
