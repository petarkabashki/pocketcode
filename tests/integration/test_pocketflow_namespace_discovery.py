import pytest
from pathlib import Path
from pocketcode.core.workspace_catalog import WorkspaceCatalog
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.workspace_module_loader import load_workspace_module
from pocketcode.config.loader import load_settings
from pocketflow import Flow


def test_workspace_catalog_discovers_template_namespace(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    catalog = WorkspaceCatalog(config=config, workspace_root=workspace_root)
    catalog.load()

    assert "template.template-agent" in catalog.agents
    agent = catalog.agents["template.template-agent"]
    assert agent.execution_mode == "vm"
    assert agent.vm_entry == "decide"
    assert agent.name == "template-agent"


def test_agent_namespace_migration(monkeypatch):
    """
    Verify that the flat namespace catalog registers the expected built-in flows.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    catalog = WorkspaceCatalog(config=config, workspace_root=workspace_root)
    catalog.load()

    all_agents = catalog.agents.list_all()

    # New namespaces must be present (registry stores qualified ids as "namespace.agent").
    assert "core.react" in all_agents, \
        f"core.react must be registered. Found: {all_agents}"
    assert "coder.coder" in all_agents, \
        f"coder.coder must be registered. Found: {all_agents}"
    assert "architect.architect" in all_agents, \
        f"architect.architect must be registered. Found: {all_agents}"
    assert "asker.ask" in all_agents, \
        f"asker.ask must be registered. Found: {all_agents}"

    assert "core.coder" not in all_agents, \
        "core.coder must NOT be registered after migration"
    assert "core.architect" not in all_agents, \
        "core.architect must NOT be registered after migration"
    assert "core.ask" not in all_agents, \
        "core.ask must NOT be registered after migration"

    react_agent = catalog.agents["core.react"]
    assert isinstance(react_agent.flow_instance, Flow), \
        "core.react flow_instance must be a pocketflow.Flow"


def test_workspace_namespaces_are_loaded_from_dot_pocketcode(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    catalog = WorkspaceCatalog(config=config, workspace_root=workspace_root)
    catalog.load()

    all_tools = catalog.tools.list_all()

    assert "workspace_git.git_status" in all_tools
    assert "workspace_context.read_context_elephant_store_file" in all_tools
    assert "core.git_status" not in all_tools
    assert "workspace_builder.workspace_builder" in catalog.agents.list_all()
    assert "workspace_builder" in catalog.namespace_roots

    resolved_tools = catalog.resolve_tools_for_agent("core.react")
    assert "workspace_git.git_status" in resolved_tools
    assert "workspace_context.check_context_elephant_store_status" in resolved_tools


def test_workspace_builder_profile_is_available_from_engine(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    engine = PocketCodeEngine(config=config, workspace_root=workspace_root)

    assert "workspace_builder.workspace_builder" in engine.list_available_agents()
    profile = engine.get_agent_profile("workspace_builder.workspace_builder")
    assert profile.flow == "workspace_builder.workspace_builder"
    flow_def = engine._catalog.agents["workspace_builder.workspace_builder"]
    assert "workspace-level assets" in flow_def.description
    assert "Portability rules:" in flow_def.system_prompt
    assert "pocketcode/.pocketcore/core.shared.general_rules.prompt.md" not in flow_def.system_prompt


def test_core_tool_import_paths_are_workspace_shims():
    workspace_git = load_workspace_module(".pocketcode", "workspace_git.git.tool.py")
    workspace_context = load_workspace_module(
        ".pocketcode",
        "workspace_context.context_elephant_store_tools.tool.py",
    )

    assert "workspace_loader" in workspace_git.GitStatusTool.__module__
    assert workspace_context.ReadContextElephantStoreFileTool.__name__ == "ReadContextElephantStoreFileTool"
