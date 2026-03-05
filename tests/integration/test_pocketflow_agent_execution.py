import pytest
from typing import Any, Dict
from pocketflow import Node, Flow
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.runtime_models import AgentDefinition
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.tool_runtime import ToolRuntime
from unittest.mock import MagicMock

class SimpleNode(Node):
    def exec(self, prep_res: Any) -> str:
        # shared is not explicitly passed to exec/post in pocketflow.py Node base classes
        # but _run calls prep(shared), e=exec(p), post(shared, p, e).
        # Actually Node._run calls super()._run(shared) which is BaseNode._run(shared):
        # p=self.prep(shared); e=self._exec(p); return self.post(shared,p,e)
        return "final_answer"
    
    def post(self, shared, prep_res, exec_res):
        shared["visited_simple"] = True
        return exec_res

def test_pocketflow_agent_execution():
    # Setup
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    tool_runtime = MagicMock(spec=ToolRuntime)
    
    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={}
    )
    
    # Define a simple flow
    start_node = SimpleNode()
    flow = Flow(start=start_node)
    
    agent_def = AgentDefinition(
        name="test-flow-agent",
        is_programmatic=True,
        flow_instance=flow,
        metadata={}
    )
    
    plugin_manager.agents = {"test-flow-agent": agent_def}
    plugin_manager.plugins = {}
    
    shared_store = {
        "active_agent": "test-flow-agent",
        "initial_request": "hello"
    }
    
    # Run
    runtime.run(shared_store)
    
    # Assert
    assert shared_store.get("visited_simple") is True
    assert "final_output" in shared_store
