import pytest
import os
from pathlib import Path
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.config.loader import load_settings
from pocketflow import Flow

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
    
    # 2. Add the plugins directory to plugin_paths if not present
    # By default, PluginManager might look in .pocketcode/plugins
    # We want it to find pocketcode/plugins/template
    plugin_paths = config.get("runtime", {}).get("plugin_paths", [])
    if "pocketcode/plugins" not in plugin_paths:
        plugin_paths.append("pocketcode/plugins")
    config.setdefault("runtime", {})["plugin_paths"] = plugin_paths

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
