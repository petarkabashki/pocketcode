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


def test_stackvm_agent_execution():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    agent_def = AgentDefinition(
        name="vm-agent",
        execution_mode="vm",
        vm_source='"hello from vm" answer',
        metadata={},
    )

    plugin_manager.agents = {"vm-agent": agent_def}
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-agent",
        "initial_request": "hello",
    }

    runtime.run(shared_store)

    assert shared_store.get("final_answer") == "hello from vm"
    assert shared_store.get("final_output") == "hello from vm"


def test_stackvm_agent_tool_roundtrip():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = [
        {"name": "workspace.echo", "description": "Echo text", "schema": {"type": "object"}}
    ]
    tool_runtime.execute_tool.return_value = {"success": True, "text": "echoed from tool"}
    plugin_manager.resolve_tools_for_agent.return_value = ["workspace.echo"]

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    agent_def = AgentDefinition(
        name="vm-tool-agent",
        execution_mode="vm",
        vm_source='last-tool-result none? [ "workspace.echo" "text: ping" yaml> tool-request ] [ "last_tool_result.text" shared@ answer ] if',
        tools=["workspace.echo"],
        metadata={},
    )

    plugin_manager.agents = {"vm-tool-agent": agent_def}
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-tool-agent",
        "initial_request": "ping",
    }

    runtime.run(shared_store)

    tool_runtime.execute_tool.assert_called_once()
    assert shared_store.get("last_tool_failed") is False
    assert shared_store.get("last_tool_result") == {"success": True, "text": "echoed from tool"}
    assert shared_store.get("final_output") == "echoed from tool"


def test_stackvm_agent_handoff_roundtrip():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    delegate_flow = Flow(start=_ArchitectNode())
    vm_agent = AgentDefinition(
        name="vm-router",
        execution_mode="vm",
        vm_source='"delegate.agent" handoff',
        metadata={},
    )
    delegate_agent = AgentDefinition(
        name="delegate.agent",
        is_programmatic=True,
        flow_instance=delegate_flow,
        metadata={"plugin_name": "delegate", "plugin": "delegate"},
    )

    plugin_manager.agents = {
        "vm-router": vm_agent,
        "delegate.agent": delegate_agent,
    }
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-router",
        "initial_request": "handoff me",
    }

    runtime.run(shared_store)

    assert shared_store.get("handoff_history") == ["delegate.agent"]
    assert shared_store.get("final_output") == "architect plan ready"


def test_stackvm_agent_ask_user_transition():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    vm_agent = AgentDefinition(
        name="vm-ask-agent",
        execution_mode="vm",
        vm_source='"Need confirmation?" ask-user',
        metadata={},
    )

    plugin_manager.agents = {"vm-ask-agent": vm_agent}
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-ask-agent",
        "initial_request": "ask me",
    }

    runtime.run(shared_store)

    assert shared_store.get("question_to_ask") == "Need confirmation?"
    assert shared_store.get("final_output") == "Question: Need confirmation?"


def test_stackvm_agent_prompt_user_continues_when_interaction_handler_is_present():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    vm_agent = AgentDefinition(
        name="vm-prompt-agent",
        execution_mode="vm",
        vm_source='"Proceed?" prompt-user "Result: " swap concat answer',
        metadata={},
    )

    plugin_manager.agents = {"vm-prompt-agent": vm_agent}
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-prompt-agent",
        "initial_request": "prompt me",
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "text"),
            "value": "yes",
            "raw_input": "yes",
        },
    }

    runtime.run(shared_store)

    assert shared_store.get("last_user_prompt") == "Proceed?"
    assert shared_store.get("last_user_input") == "yes"
    assert shared_store.get("final_output") == "Result: yes"


def test_stackvm_agent_prompt_interaction_continues_with_button_value():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    vm_agent = AgentDefinition(
        name="vm-interaction-agent",
        execution_mode="vm",
        vm_source='"{kind: buttons, prompt: Choose action, options: [{id: approve, label: Approve, value: approve}, {id: delegate, label: Delegate, value: delegate}]}" prompt-interaction "Result: " swap concat answer',
        metadata={},
    )

    plugin_manager.agents = {"vm-interaction-agent": vm_agent}
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-interaction-agent",
        "initial_request": "prompt me",
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "buttons"),
            "value": "delegate",
            "values": ["delegate"],
            "selected_options": [{"id": "delegate", "label": "Delegate", "value": "delegate"}],
            "raw_input": "delegate",
        },
    }

    runtime.run(shared_store)

    assert shared_store.get("last_user_prompt") == "Choose action"
    assert shared_store.get("last_user_value") == "delegate"
    assert shared_store.get("final_output") == "Result: delegate"


def test_stackvm_agent_prompted_delegate_handoff_roundtrip():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    agents: NamespaceRegistry[AgentDefinition] = NamespaceRegistry()

    caller_agent = AgentDefinition(
        name="caller",
        execution_mode="vm",
        vm_entry="decide",
        vm_source=(
            '[ "last_delegated_result" shared@ none? '
            '[ "{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml> '
            '"pending_handoff_policy" store-set "prompt.delegate" handoff ] '
            '[ "Caller received: " "last_delegated_result" shared@ "answer" dict-get concat answer ] if ] '
            '"decide" define'
        ),
        metadata={"plugin_name": "prompt", "plugin": "prompt"},
    )
    delegate_agent = AgentDefinition(
        name="delegate",
        execution_mode="vm",
        vm_entry="decide",
        vm_source=(
            '[ "{kind: buttons, prompt: Choose action, options: '
            '[{id: approve, label: Approve, value: approve}, {id: reject, label: Reject, value: reject}]}" '
            'prompt-interaction dup "approve" = '
            '[ drop "delegate approved" answer ] '
            '[ drop "delegate rejected" answer ] if ] "decide" define'
        ),
        metadata={"plugin_name": "prompt", "plugin": "prompt"},
    )

    agents.register("prompt", "caller", caller_agent)
    agents.register("prompt", "delegate", delegate_agent)
    plugin_manager.agents = agents
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "prompt.caller",
        "initial_request": "delegate prompt",
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "buttons"),
            "value": "approve",
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    }

    runtime.run(shared_store)

    assert shared_store.get("final_output") == "Caller received: delegate approved"
    assert shared_store.get("last_delegated_result", {}).get("answer") == "delegate approved"
    assert shared_store.get("handoff_history") == ["prompt.delegate"]


def test_stackvm_agent_checklist_delegate_handoff_roundtrip():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = []
    plugin_manager.resolve_tools_for_agent.return_value = []

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    agents: NamespaceRegistry[AgentDefinition] = NamespaceRegistry()

    caller_agent = AgentDefinition(
        name="caller",
        execution_mode="vm",
        vm_entry="decide",
        vm_source=(
            '[ "last_delegated_result" shared@ none? '
            '[ "{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml> '
            '"pending_handoff_policy" store-set "prompt.checklist_delegate" handoff ] '
            '[ "Caller received tools: " "last_delegated_result" shared@ "answer" dict-get concat answer ] if ] '
            '"decide" define'
        ),
        metadata={"plugin_name": "prompt", "plugin": "prompt"},
    )
    delegate_agent = AgentDefinition(
        name="checklist_delegate",
        execution_mode="vm",
        vm_entry="decide",
        vm_source=(
            '[ "{kind: checklist, prompt: Pick tools, options: '
            '[{id: git, label: Git, value: git}, {id: search, label: Search, value: search}, {id: context, label: Context, value: context}], min_selected: 1}" '
            'prompt-interaction dup "selected_tools" store-set ", " join "delegate picked " swap concat answer ] "decide" define'
        ),
        metadata={"plugin_name": "prompt", "plugin": "prompt"},
    )

    agents.register("prompt", "caller", caller_agent)
    agents.register("prompt", "checklist_delegate", delegate_agent)
    plugin_manager.agents = agents
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "prompt.caller",
        "initial_request": "delegate checklist",
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "checklist"),
            "value": ["git", "search"],
            "values": ["git", "search"],
            "selected_options": [
                {"id": "git", "label": "Git", "value": "git"},
                {"id": "search", "label": "Search", "value": "search"},
            ],
            "raw_input": "git,search",
        },
    }

    runtime.run(shared_store)

    assert shared_store.get("selected_tools") == ["git", "search"]
    assert shared_store.get("last_user_value") == ["git", "search"]
    assert shared_store.get("final_output") == "Caller received tools: delegate picked git, search"
    assert shared_store.get("last_delegated_result", {}).get("answer") == "delegate picked git, search"


def test_stackvm_agent_failure_branch_handoff():
    plugin_manager = MagicMock(spec=PluginManager)
    llm_router = MagicMock(spec=LlmRouter)
    llm_router.default_profile_name = "default"
    tool_runtime = MagicMock(spec=ToolRuntime)
    tool_runtime.describe_tools.return_value = [{"name": "core.read_file", "schema": {"type": "object"}}]
    tool_runtime.execute_tool.return_value = {"success": False, "error": "missing file"}
    plugin_manager.resolve_tools_for_agent.return_value = ["core.read_file"]

    runtime = AgentRuntime(
        plugin_manager=plugin_manager,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        runtime_config={},
    )

    vm_agent = AgentDefinition(
        name="vm-resilient",
        execution_mode="vm",
        tools=["core.read_file"],
        vm_source='last-tool-result none? [ "core.read_file" "{path: nope.md}" yaml> tool-request ] [ last-tool-result failure? [ "fallback.agent" handoff ] [ "unexpected" answer ] if ] if',
        metadata={},
    )
    fallback_agent = AgentDefinition(
        name="fallback.agent",
        is_programmatic=True,
        flow_instance=Flow(start=_ArchitectNode()),
        metadata={"plugin_name": "fallback", "plugin": "fallback"},
    )

    plugin_manager.agents = {
        "vm-resilient": vm_agent,
        "fallback.agent": fallback_agent,
    }
    plugin_manager.plugins = {}

    shared_store = {
        "active_agent": "vm-resilient",
        "initial_request": "recover",
    }

    runtime.run(shared_store)

    tool_runtime.execute_tool.assert_called_once()
    assert shared_store.get("last_tool_failed") is True
    assert shared_store.get("handoff_history") == ["fallback.agent"]
    assert shared_store.get("last_tool_result") == {"success": False, "error": "missing file"}
    assert shared_store.get("final_output") == "architect plan ready"
