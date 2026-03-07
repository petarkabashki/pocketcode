import pytest
from pathlib import Path
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.config.loader import load_settings
from pocketflow import Flow
from pocketcode.tools import GitStatusTool as PublicGitStatusTool
from pocketcode.plugins.core.tools.context_elephant_store_tools import (
    ReadContextElephantStoreFileTool as CoreReadContextTool,
)

def test_pocketflow_plugin_discovery(monkeypatch):
    """
    Verify that PluginManager can discover and load factory-based plugins
    specifically the 'template' plugin which now uses a PocketFlow factory.
    """
    # 0. Mock environment variables to satisfy config loader
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    # 1. Initialize PluginManager with real config and workspace root
    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)
    
    plugin_manager = PluginManager(config=config, workspace_root=workspace_root)
    
    # 3. Call load()
    plugin_manager.load()
    
    # 4. Verify that plugin_manager.agents["template-agent"] exists
    assert "template-agent" in plugin_manager.agents, f"template-agent should be discovered in agents. Found: {list(plugin_manager.agents.keys())}"
    
    agent = plugin_manager.agents["template-agent"]
    
    # 5. Verify that plugin_manager.agents["template-agent"].is_programmatic is True
    assert agent.is_programmatic is True, "template-agent should be marked as programmatic"
    
    # 6. Verify that plugin_manager.agents["template-agent"].flow_instance is an instance of pocketflow.Flow
    assert isinstance(agent.flow_instance, Flow), "agent.flow_instance should be an instance of pocketflow.Flow"
    
    # 7. Verify that plugin_manager.plugins["template"] exists
    assert "template" in plugin_manager.plugins, "template plugin should be discovered"
    
    # Optional: verify other metadata if needed
    assert agent.name == "template-agent"


def test_agent_namespace_migration(monkeypatch):
    """
    Verify that after the 004-agents-to-plugins migration:
    - core::react is the only agent registered under 'core'
    - coder::coder is registered under 'coder'
    - architect::architect is registered under 'architect'
    - asker::ask is registered under 'asker'
    - Old agents core::coder, core::architect, core::ask are absent
    """
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    plugin_manager = PluginManager(config=config, workspace_root=workspace_root)
    plugin_manager.load()

    all_agents = plugin_manager.agents.list_all()

    # New namespaces must be present (registry stores as "plugin.agent" with dot)
    assert "core.react" in all_agents, \
        f"core.react must be registered. Found: {all_agents}"
    assert "coder.coder" in all_agents, \
        f"coder.coder must be registered. Found: {all_agents}"
    assert "architect.architect" in all_agents, \
        f"architect.architect must be registered. Found: {all_agents}"
    assert "asker.ask" in all_agents, \
        f"asker.ask must be registered. Found: {all_agents}"

    # Also verify :: notation resolves correctly (normalised to . internally)
    assert "core::react" in plugin_manager.agents, \
        "core::react must be accessible via :: notation"
    assert "coder::coder" in plugin_manager.agents, \
        "coder::coder must be accessible via :: notation"
    assert "architect::architect" in plugin_manager.agents, \
        "architect::architect must be accessible via :: notation"
    assert "asker::ask" in plugin_manager.agents, \
        "asker::ask must be accessible via :: notation"

    # Old stale references must be absent
    assert "core.coder" not in all_agents, \
        "core.coder must NOT be registered after migration"
    assert "core.architect" not in all_agents, \
        "core.architect must NOT be registered after migration"
    assert "core.ask" not in all_agents, \
        "core.ask must NOT be registered after migration"

    # core::react must be a programmatic pocketflow agent
    react_agent = plugin_manager.agents["core::react"]
    assert isinstance(react_agent.flow_instance, Flow), \
        "core::react flow_instance must be a pocketflow.Flow"


def test_workspace_plugins_are_loaded_from_dot_pocketcode(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    plugin_manager = PluginManager(config=config, workspace_root=workspace_root)
    plugin_manager.load()

    all_tools = plugin_manager.tools.list_all()

    assert "workspace_git.git_status" in all_tools
    assert "workspace_context.read_context_elephant_store_file" in all_tools
    assert "core.git_status" not in all_tools
    assert "workspace_builder.plugin_builder" in plugin_manager.agents.list_all()
    assert "workspace_builder" in plugin_manager.plugin_roots

    resolved_tools = plugin_manager.resolve_tools_for_agent("core::react")
    assert "workspace_git.git_status" in resolved_tools
    assert "workspace_context.check_context_elephant_store_status" in resolved_tools


def test_workspace_builder_profile_is_available_from_engine(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    config = load_settings(workspace_root=workspace_root)

    engine = PocketCodeEngine(config=config, workspace_root=workspace_root)

    assert "workspace_builder::plugin_builder" in engine.list_available_agents()
    profile = engine.get_agent_profile("workspace_builder::plugin_builder")
    assert "workspace-level assets" in profile.description
    flow_def = engine._plugins.agents["workspace_builder::plugin_builder"]
    assert "Portability rules:" in flow_def.system_prompt
    assert "pocketcode/plugins/core/prompts/shared/general_rules.md" not in flow_def.system_prompt


def test_core_tool_import_paths_are_workspace_shims():
    assert "workspace_loader" in PublicGitStatusTool.__module__
    assert "workspace_loader" in CoreReadContextTool.__module__
