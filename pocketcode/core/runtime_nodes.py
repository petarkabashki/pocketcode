from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict

from pocketflow import Node

from pocketcode.core.prompt_loader import coerce_str_list
from pocketcode.core.runtime_models import WorkflowNodeDefinition

if TYPE_CHECKING:
    from pocketcode.core.workflow_runtime import WorkflowRuntime

logger = logging.getLogger(__name__)


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
            p = self.prep(shared_store)
            if p.get("halt"):
                return self.post(shared_store, p, None)
            
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
                 return self.post(shared_store, p, step_transition)

            e = self.exec(shared_store) # Passing shared_store as prep_res for now to simplify
            return self.post(shared_store, p, e if e is not None else step_transition)
        except Exception as exc:
            logger.error(
                "Error while executing node '%s': %s",
                self.node_definition.node_id,
                exc,
                exc_info=True,
            )
            shared_store["error_message"] = f"Node '{self.node_definition.node_id}' failed: {exc}"
            return "error"

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
