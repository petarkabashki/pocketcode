import pytest
import copy
from typing import Any, Dict
from pocketflow import Node, Flow
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.runtime_models import AgentDefinition
from pocketcode.core.workspace_catalog import WorkspaceCatalog
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.tool_runtime import ToolRuntime
from unittest.mock import MagicMock

class DecisionNode(Node):
    def _run(self, shared):
        action = shared.get("requested_path", "path_a")
        # print(f"DEBUG: DecisionNode action={action}")
        return action

class PathANode(Node):
    def _run(self, shared):
        shared["visited_path"] = "A"
        return "final_answer"

class PathBNode(Node):
    def _run(self, shared):
        shared["visited_path"] = "B"
        return "final_answer"

def test_pocketflow_conditional_branching():
    catalog = MagicMock(spec=WorkspaceCatalog)
    llm_router = MagicMock(spec=LlmRouter)
    tool_runtime = MagicMock(spec=ToolRuntime)
    
    runtime = AgentRuntime(
        catalog=catalog,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={}
    )
    
    dec = DecisionNode()
    a = PathANode()
    b = PathBNode()
    
    dec.next(a, action="path_a")
    dec.next(b, action="path_b")
    
    flow = Flow(start=dec)
    
    agent_def = AgentDefinition(
        name="test-branch-agent",
        is_programmatic=True,
        flow_instance=flow,
        metadata={}
    )
    catalog.agents = {"test-branch-agent": agent_def}
    
    # Test Path A
    shared_a = {"active_agent": "test-branch-agent", "requested_path": "path_a"}
    runtime.run(shared_a)
    assert shared_a.get("visited_path") == "A"
    
    # Test Path B
    shared_b = {"active_agent": "test-branch-agent", "requested_path": "path_b"}
    runtime.run(shared_b)
    assert shared_b.get("visited_path") == "B"
