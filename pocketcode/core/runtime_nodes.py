from __future__ import annotations

"""Legacy runtime nodes for the older graph workflow runtime.

New markdown-authored flows are compiled into the current manifest-backed flow
model instead of introducing new node kinds here.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict

from pocketflow import Node, Flow, AsyncFlow

from pocketcode.core.prompt_loader import coerce_str_list
from pocketcode.core.runtime_models import WorkflowNodeDefinition, AgentDefinition

if TYPE_CHECKING:
    from pocketcode.core.workflow_runtime import WorkflowRuntime

logger = logging.getLogger(__name__)


class PocketFlowAgent(Node):
    """Bridge between AgentDefinition and pocketflow.Flow/AsyncFlow."""
    def __init__(self, agent_definition: AgentDefinition, runtime: "WorkflowRuntime"):
        super().__init__()
        self.agent_definition = agent_definition
        self.runtime = runtime
        self.flow: Flow | AsyncFlow = agent_definition.flow_instance

    def _run(self, shared: Dict[str, Any]) -> Any:
        # The runtime will handle the orchestration call to this node
        return self.flow.run(shared)


class BaseRuntimeNode(Node):
    def __init__(self, node_definition: WorkflowNodeDefinition, runtime: "WorkflowRuntime"):
        super().__init__()
        self.node_definition = node_definition
        self.runtime = runtime

    def prep(self, shared_store: Dict[str, Any]) -> Dict[str, Any]:
        pre_handlers = coerce_str_list(self.node_definition.attributes.get("pre"))
        transition, halt = self.runtime._run_handler_references(
            pre_handlers,
            shared_store,
            phase="node:pre",
            node_definition=self.node_definition
        )
        return {"halt": halt, "transition_override": transition}

    def exec(self, prep_res: Dict[str, Any]) -> Any:
        # This will be overridden by subclasses
        return None

    def post(self, shared_store: Dict[str, Any], prep_res: Dict[str, Any], exec_res: Any) -> str | None:
        transition = exec_res if exec_res is not None else prep_res.get("transition_override")
        
        post_handlers = coerce_str_list(self.node_definition.attributes.get("post"))
        final_transition, _ = self.runtime._run_handler_references(
            post_handlers,
            shared_store,
            phase="node:post",
            node_definition=self.node_definition,
            transition=transition
        )
        return final_transition

    def _run(self, shared_store: Dict[str, Any]) -> str | None:
        try:
            node_kind = str(self.node_definition.attributes.get("kind", self.node_definition.attributes.get("type", "node"))).strip().lower()
            self._emit_runtime_event(
                shared_store,
                "node_started",
                node_id=self.node_definition.node_id,
                node_kind=node_kind,
                agent=shared_store.get("active_agent"),
            )
            shared_store["active_node_id"] = self.node_definition.node_id
            shared_store["active_node_kind"] = node_kind
            self.runtime._raise_if_cancelled(shared_store)
            p = self.prep(shared_store)
            if p.get("halt"):
                self.runtime._raise_if_cancelled(shared_store)
                transition = self.post(shared_store, p, None)
                self._emit_runtime_event(
                    shared_store,
                    "node_completed",
                    node_id=self.node_definition.node_id,
                    node_kind=node_kind,
                    agent=shared_store.get("active_agent"),
                    transition=transition,
                )
                return transition

            # Run "steps" as part of core logic or as actual exec
            step_handlers = coerce_str_list(self.node_definition.attributes.get("steps"))
            step_transition, step_halt = self.runtime._run_handler_references(
                step_handlers,
                shared_store,
                phase="node:steps",
                node_definition=self.node_definition,
                transition=p.get("transition_override")
            )

            if step_halt:
                self.runtime._raise_if_cancelled(shared_store)
                transition = self.post(shared_store, p, step_transition)
                self._emit_runtime_event(
                    shared_store,
                    "node_completed",
                    node_id=self.node_definition.node_id,
                    node_kind=node_kind,
                    agent=shared_store.get("active_agent"),
                    transition=transition,
                )
                return transition

            self.runtime._raise_if_cancelled(shared_store)
            exec_result = self.exec(shared_store)
            self.runtime._raise_if_cancelled(shared_store)
            transition = self.post(shared_store, p, exec_result if exec_result is not None else step_transition)
            self._emit_runtime_event(
                shared_store,
                "node_completed",
                node_id=self.node_definition.node_id,
                node_kind=node_kind,
                agent=shared_store.get("active_agent"),
                transition=transition,
            )
            return transition
        except Exception as exc:
            logger.error(
                "Error while executing node '%s': %s",
                self.node_definition.node_id,
                exc,
                exc_info=True,
            )
            shared_store["error_message"] = f"Node '{self.node_definition.node_id}' failed: {exc}"
            return "error"

    def _emit_runtime_event(self, shared_store: Dict[str, Any], event_type: str, **payload: Any) -> None:
        handler = shared_store.get("runtime_event_handler")
        if callable(handler):
            handler(event_type, **payload)

class StartRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_start_node(self.node_definition, shared_store)

class AgentRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_agent_node(self.node_definition, shared_store)

class ToolRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_tool_node(self.node_definition, shared_store)

class HandoffRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_handoff_node(self.node_definition, shared_store)

class OutputRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_output_node(self.node_definition, shared_store)

class EndRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_end_node(self.node_definition, shared_store)

class PythonRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_python_node(self.node_definition, shared_store)

class FlowRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_flow_node(self.node_definition, shared_store)

class NoopRuntimeNode(BaseRuntimeNode):
    def exec(self, _shared_store: Dict[str, Any]) -> str | None:
        return str(self.node_definition.attributes.get("transition", "continue"))

class CustomKindRuntimeNode(BaseRuntimeNode):
    def __init__(
        self,
        node_definition: WorkflowNodeDefinition,
        runtime: "WorkflowRuntime",
        handler: Callable[..., Any],
    ):
        super().__init__(node_definition=node_definition, runtime=runtime)
        self._handler = handler

    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        return self.runtime._run_custom_node(
            node_definition=self.node_definition,
            shared_store=shared_store,
            handler=self._handler,
        )

class UnsupportedRuntimeNode(BaseRuntimeNode):
    def exec(self, shared_store: Dict[str, Any]) -> str | None:
        kind = str(self.node_definition.attributes.get("kind", "agent")).strip().lower()
        shared_store["error_message"] = (
            f"Unsupported node kind '{kind}' on node '{self.node_definition.node_id}'."
        )
        return "error"


def create_runtime_node(
    *,
    node_definition: WorkflowNodeDefinition,
    runtime: "WorkflowRuntime",
) -> BaseRuntimeNode:
    kind = str(node_definition.attributes.get("kind", "agent")).strip().lower()

    if kind in {"noop", "pass"}:
        return NoopRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "start":
        return StartRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "agent":
        return AgentRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "tool":
        return ToolRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "handoff":
        return HandoffRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "output":
        return OutputRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "end":
        return EndRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind == "python":
        return PythonRuntimeNode(node_definition=node_definition, runtime=runtime)
    if kind in {"flow", "composite"}:
        return FlowRuntimeNode(node_definition=node_definition, runtime=runtime)

    custom_handler = runtime._plugins.node_handlers.get(kind)
    if custom_handler:
        return CustomKindRuntimeNode(
            node_definition=node_definition,
            runtime=runtime,
            handler=custom_handler.handler,
        )

    return UnsupportedRuntimeNode(node_definition=node_definition, runtime=runtime)
