import pytest
from typing import Any, Dict
from pocketflow import Node, Flow
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.runtime_models import AgentDefinition
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.namespace_registry import NamespaceRegistry
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


# ---------------------------------------------------------------------------
# SC-004: Full round-trip handoff sequence
# coder::coder → architect::architect → coder::coder
# ---------------------------------------------------------------------------

class _coderNode(Node):
    """Simulates coder::coder: first turn hands off to architect, second turn finalizes."""

    def exec(self, prep_res: Any) -> str:
        return "coder-exec"

    def post(self, shared: Dict[str, Any], prep_res: Any, exec_res: str) -> str:
        if shared.get("last_delegated_result"):
            # Second turn: architect returned — produce final answer.
            delegated = shared["last_delegated_result"]
            shared["final_answer"] = f"coder done; got from architect: {delegated.get('answer', '')}"
            return "final_answer"
        # First turn: hand off to architect with return_to_caller.
        shared["pending_handoff_agent"] = "architect.architect"
        shared["pending_handoff_policy"] = {
            "return_to_caller": True,
            "context_mode": "whole",
            "return_transition": "continue",
        }
        return "handoff"


class _ArchitectNode(Node):
    """Simulates architect::architect: produces a final answer and returns."""

    def exec(self, prep_res: Any) -> str:
        return "arch-exec"

    def post(self, shared: Dict[str, Any], prep_res: Any, exec_res: str) -> str:
        shared["final_answer"] = "architect plan ready"
        return "final_answer"


def test_sc004_handoff_roundtrip():
    """
    SC-004: Verify coder::coder → architect::architect → coder::coder round-trip
    completes without error using fully-qualified plugin::agent handoff references.
    """
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    tool_runtime = MagicMock(spec=ToolRuntime)

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    # Build a real NamespaceRegistry so that :: notation resolves correctly.
    agents: NamespaceRegistry[AgentDefinition] = NamespaceRegistry()

    coder_agent = AgentDefinition(
        name="coder",
        is_programmatic=True,
        flow_instance=Flow(start=_coderNode()),
        metadata={"plugin_name": "coder", "plugin": "coder"},
    )
    architect_agent = AgentDefinition(
        name="architect",
        is_programmatic=True,
        flow_instance=Flow(start=_ArchitectNode()),
        metadata={"plugin_name": "architect", "plugin": "architect"},
    )

    agents.register("coder", "coder", coder_agent)
    agents.register("architect", "architect", architect_agent)

    plugin_manager.agents = agents
    plugin_manager.plugins = {}

    shared_store: Dict[str, Any] = {
        "active_agent": "coder.coder",
        "initial_request": "implement the feature",
    }

    runtime.run(shared_store)

    # Must complete without error.
    assert not shared_store.get("error_message"), \
        f"Unexpected error in SC-004 roundtrip: {shared_store.get('error_message')}"

    # Final output must be set.
    assert shared_store.get("final_output"), "Expected final_output after SC-004 roundtrip"

    # The coder agent's final answer must mention the architect's response.
    final = shared_store.get("final_output", "")
    assert "architect plan ready" in final or "architect" in final.lower(), \
        f"Expected architect response in final output: {final!r}"
