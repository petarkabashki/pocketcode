import pytest
from pathlib import Path
from pocketcode.core.agent_profile_manager import AgentProfileManager
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.workspace_catalog import WorkspaceCatalog
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.tool_runtime import ToolRuntime
from unittest.mock import MagicMock

def test_self_contained_markdown_agent_execution(tmp_path):
    # 1. Create a self-contained agent file
    profiles_dir = tmp_path / ".pocketcode" / "agents"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "hybrid.md").write_text(
        """---
name: hybrid
vm_source: |
  [ "Hybrid execution success." answer ] "main" define
vm_entry: main
---
Hybrid prompt.
""",
        encoding="utf-8",
    )

    # 2. Setup AgentProfileManager and load
    apm = AgentProfileManager(tmp_path)
    # We need to simulate the initial empty flow definitions
    apm.load({})
    
    # 3. Verify registration
    profile = apm.get("hybrid")
    assert profile is not None
    assert profile.flow == "agents.hybrid"
    
    flow_def = apm._flow_definitions.get("agents.hybrid")
    assert flow_def is not None

    # 4. Setup Runtime to execute it
    plugin_manager = MagicMock(spec=WorkspaceCatalog)
    llm_router = MagicMock(spec=LlmRouter)
    tool_runtime = MagicMock(spec=ToolRuntime)
    
    # Inject our self-contained flow and agent into the mock plugin manager
    plugin_manager.agents = {"agents.hybrid": flow_def, "hybrid": flow_def}
    plugin_manager.flows = plugin_manager.agents
    plugin_manager.resolve_tools_for_agent.return_value = []
    
    runtime = AgentRuntime(
        catalog=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={}
    )
    
    shared_store = {
        "active_agent": "hybrid",
        "initial_request": "test"
    }
    
    # 5. Run
    runtime.run(shared_store)
    
    # 6. Assert execution result
    assert shared_store.get("final_output") == "Hybrid execution success."
