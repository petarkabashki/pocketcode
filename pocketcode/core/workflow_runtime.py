from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml
from pocketflow import Flow

from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.runtime_nodes import BaseRuntimeNode, create_runtime_node
from pocketcode.core.runtime_models import WorkflowDefinition, WorkflowNodeDefinition
from pocketcode.core.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)

_YAML_BLOCK_RE = re.compile(r"```(?:yaml)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class BaseWorkflowRuntime:
    def __init__(
        self,
        workflow_definition: WorkflowDefinition,
        plugin_manager: PluginManager,
        llm_router: LlmRouter,
        tool_runtime: ToolRuntime,
        runtime_config: Dict[str, Any],
        workflow_lookup: Callable[[str], "BaseWorkflowRuntime"] | None = None,
    ):
        self.definition = workflow_definition
        self._plugins = plugin_manager
        self._llm_router = llm_router
        self._tool_runtime = tool_runtime
        self._runtime_config = runtime_config
        self._workflow_lookup = workflow_lookup
        self._python_handler_cache: Dict[str, Callable[..., Any]] = {}

    def run(self, shared_store: Dict[str, Any]) -> str | None:
        raise NotImplementedError

    def _prepare_shared_store(self, shared_store: Dict[str, Any]) -> None:
        shared_store.setdefault("active_workflow", self.definition.name)
        shared_store.setdefault("workflow_default_agent", self.definition.default_agent)
        shared_store.setdefault("results", {})
        shared_store.setdefault("dynamic_llm_overrides", {})
        shared_store.setdefault("_workflow_stack", [])
        shared_store.setdefault("_active_flow_prompts", [])
        shared_store.setdefault("_handoff_stack", [])
        shared_store.setdefault("agent_trace", [])
        shared_store.setdefault("active_handoff_context_mode", "whole")
        shared_store.setdefault("llm_usage_totals", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        shared_store.setdefault("llm_cost_usd_total", 0.0)
        shared_store.setdefault("llm_calls", [])
        # FR-011: populate registry snapshot for PocketFlow agents (T028)
        if "_registry" not in shared_store:
            try:
                shared_store["_registry"] = self._plugins._holder.get()
            except AttributeError:
                shared_store["_registry"] = None

    def _push_workflow_context(self, shared_store: Dict[str, Any]) -> bool:
        shared_store["active_workflow"] = self.definition.name
        shared_store["workflow_default_agent"] = self.definition.default_agent

        workflow_stack = shared_store.setdefault("_workflow_stack", [])
        workflow_stack.append(self.definition.name)

        prompt_stack = shared_store.setdefault("_active_flow_prompts", [])
        prompt_pushed = False
        if self.definition.prompt:
            prompt_stack.append(self.definition.prompt)
            prompt_pushed = True

        return prompt_pushed

    def _pop_workflow_context(self, shared_store: Dict[str, Any], prompt_pushed: bool) -> None:
        workflow_stack = shared_store.get("_workflow_stack")
        if isinstance(workflow_stack, list) and workflow_stack:
            workflow_stack.pop()
            if workflow_stack:
                shared_store["active_workflow"] = workflow_stack[-1]
            else:
                shared_store["active_workflow"] = self.definition.name

        if prompt_pushed:
            prompt_stack = shared_store.get("_active_flow_prompts")
            if isinstance(prompt_stack, list) and prompt_stack:
                prompt_stack.pop()

    def _resolve_workflow_runtime(self, workflow_name: str) -> "BaseWorkflowRuntime":
        if self._workflow_lookup:
            return self._workflow_lookup(workflow_name)

        workflow_definition = self._plugins.workflows.get(workflow_name)
        if not workflow_definition:
            raise KeyError(f"Workflow '{workflow_name}' is not registered.")

        if workflow_definition.workflow_kind == "custom":
            return CustomWorkflowRuntime(
                workflow_definition=workflow_definition,
                plugin_manager=self._plugins,
                llm_router=self._llm_router,
                tool_runtime=self._tool_runtime,
                runtime_config=self._runtime_config,
                workflow_lookup=self._workflow_lookup,
            )

        return WorkflowRuntime(
            workflow_definition=workflow_definition,
            plugin_manager=self._plugins,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
            workflow_lookup=self._workflow_lookup,
        )

    def _run_handler_references(
        self,
        handler_references: List[str],
        shared_store: Dict[str, Any],
        *,
        phase: str,
        node_definition: WorkflowNodeDefinition | None = None,
        transition: str | None = None,
    ) -> tuple[str | None, bool]:
        current_transition = transition
        halt = False

        for handler_reference in handler_references:
            handler = self._resolve_python_handler(handler_reference)
            outcome = self._invoke_handler(
                handler=handler,
                shared_store=shared_store,
                node_definition=node_definition,
                phase=phase,
                transition=current_transition,
            )
            transition_override, should_halt = self._consume_handler_outcome(outcome, shared_store)

            if transition_override is not None:
                current_transition = transition_override
            halt = halt or should_halt

        return current_transition, halt

    def _consume_handler_outcome(
        self,
        outcome: Any,
        shared_store: Dict[str, Any],
    ) -> tuple[str | None, bool]:
        if isinstance(outcome, str):
            return outcome, False

        if isinstance(outcome, dict):
            updates = outcome.get("updates") or outcome.get("set")
            if isinstance(updates, dict):
                shared_store.update(updates)

            error = outcome.get("error")
            if error and not shared_store.get("error_message"):
                shared_store["error_message"] = str(error)

            transition = outcome.get("transition")
            halt = bool(outcome.get("halt") or outcome.get("stop") or outcome.get("skip_core"))
            return (str(transition) if transition is not None else None), halt

        return None, False

    def _resolve_python_handler(self, handler_reference: str) -> Callable[..., Any]:
        if handler_reference in self._python_handler_cache:
            return self._python_handler_cache[handler_reference]

        handler: Callable[..., Any]

        if ":" in handler_reference:
            path_part, function_name = handler_reference.split(":", 1)
            candidate_file = Path(path_part)
            if not candidate_file.is_absolute():
                candidate_file = (self.definition.plugin_root / path_part).resolve()

            if not candidate_file.is_file():
                raise FileNotFoundError(
                    f"Python node handler file not found for '{handler_reference}': {candidate_file}"
                )

            module_name = f"pocketcode_runtime_node_{abs(hash(str(candidate_file)))}"
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                spec = importlib.util.spec_from_file_location(module_name, candidate_file)
                if not spec or not spec.loader:
                    raise ImportError(f"Unable to create module spec for '{candidate_file}'")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            handler = getattr(module, function_name)
        else:
            if "." not in handler_reference:
                raise ValueError(
                    f"Handler '{handler_reference}' must be module.function or path.py:function."
                )
            module_name, function_name = handler_reference.rsplit(".", 1)
            module = importlib.import_module(module_name)
            handler = getattr(module, function_name)

        if not callable(handler):
            raise TypeError(f"Resolved handler '{handler_reference}' is not callable.")

        self._python_handler_cache[handler_reference] = handler
        return handler

    def _invoke_handler(
        self,
        handler: Callable[..., Any],
        shared_store: Dict[str, Any],
        node_definition: WorkflowNodeDefinition | None = None,
        agent_definition: Any | None = None,
        phase: str | None = None,
        transition: str | None = None,
    ) -> Any:
        signature = inspect.signature(handler)
        kwargs: Dict[str, Any] = {}

        if "shared_store" in signature.parameters:
            kwargs["shared_store"] = shared_store
        if "node" in signature.parameters:
            kwargs["node"] = node_definition
        if "agent_definition" in signature.parameters:
            kwargs["agent_definition"] = agent_definition
        if "agent" in signature.parameters and agent_definition is not None:
            kwargs["agent"] = agent_definition
        if "workflow" in signature.parameters:
            kwargs["workflow"] = self.definition
        if "definition" in signature.parameters:
            kwargs["definition"] = self.definition
        if "runtime" in signature.parameters:
            kwargs["runtime"] = self
        if "phase" in signature.parameters:
            kwargs["phase"] = phase
        if "transition" in signature.parameters:
            kwargs["transition"] = transition
        if "plugins" in signature.parameters:
            kwargs["plugins"] = self._plugins
        if "llm_router" in signature.parameters:
            kwargs["llm_router"] = self._llm_router
        if "tool_runtime" in signature.parameters:
            kwargs["tool_runtime"] = self._tool_runtime

        return handler(**kwargs)

    def _parse_yaml_mapping(self, text: str) -> Dict[str, Any]:
        match = _YAML_BLOCK_RE.search(text)
        candidate = match.group(1) if match else text

        parsed = yaml.safe_load(candidate)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected YAML mapping from LLM, got: {type(parsed)}")
        return parsed

    def _parse_inline_yaml(self, text: Any) -> Dict[str, Any]:
        if isinstance(text, dict):
            return text
        if not isinstance(text, str):
            return {}
        try:
            parsed = yaml.safe_load(text) if text else {}
        except yaml.YAMLError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _to_yaml(self, payload: Any) -> str:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()

    def _resolve_final_output(self, shared_store: Dict[str, Any]) -> str:
        if "final_answer" in shared_store and shared_store["final_answer"]:
            return str(shared_store["final_answer"])
        if "question_to_ask" in shared_store and shared_store["question_to_ask"]:
            return f"Question: {shared_store['question_to_ask']}"
        if "error_message" in shared_store and shared_store["error_message"]:
            return f"Error: {shared_store['error_message']}"
        if "last_tool_route_yaml" in shared_store and shared_store["last_tool_route_yaml"]:
            return f"Latest tool result:\n{shared_store['last_tool_route_yaml']}"
        return "No output generated."

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    def _normalize_handoff_context_mode(self, value: Any) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delegated", "scoped", "partial"}:
            return "delegated"
        return "whole"


class WorkflowRuntime(BaseWorkflowRuntime, Flow):
    def __init__(
        self,
        workflow_definition: WorkflowDefinition,
        plugin_manager: PluginManager,
        llm_router: LlmRouter,
        tool_runtime: ToolRuntime,
        runtime_config: Dict[str, Any],
        workflow_lookup: Callable[[str], BaseWorkflowRuntime] | None = None,
    ):
        BaseWorkflowRuntime.__init__(
            self,
            workflow_definition=workflow_definition,
            plugin_manager=plugin_manager,
            llm_router=llm_router,
            tool_runtime=tool_runtime,
            runtime_config=runtime_config,
            workflow_lookup=workflow_lookup,
        )
        Flow.__init__(self)
        self._compiled_nodes: Dict[str, BaseRuntimeNode] = {}
        self._transitions_by_source: Dict[str, List[str]] = defaultdict(list)
        self.start_node = self._compile_nodes()

    def _compile_nodes(self) -> BaseRuntimeNode:
        for node_id, node_definition in self.definition.nodes.items():
            self._compiled_nodes[node_id] = create_runtime_node(
                node_definition=node_definition,
                runtime=self,
            )

        for edge in self.definition.edges:
            if edge.source not in self._compiled_nodes or edge.target not in self._compiled_nodes:
                raise ValueError(
                    f"Workflow '{self.definition.name}' has edge referencing unknown node: {edge.source} -> {edge.target}"
                )
            self._transitions_by_source[edge.source].append(edge.transition)
            self._compiled_nodes[edge.source].next(self._compiled_nodes[edge.target], edge.transition)

        if self.definition.start_node not in self._compiled_nodes:
            raise ValueError(
                f"Workflow '{self.definition.name}' start node '{self.definition.start_node}' was not compiled."
            )

        return self._compiled_nodes[self.definition.start_node]

    def run(self, shared_store: Dict[str, Any]) -> str | None:
        return Flow.run(self, shared_store)

    def prep(self, shared_store: Dict[str, Any]) -> None:
        self._prepare_shared_store(shared_store)
        self._push_workflow_context(shared_store)
        transition, _ = self._run_handler_references(
            self.definition.pre_handlers,
            shared_store,
            phase="workflow:pre"
        )
        return {"transition": transition}

    def exec(self, prep_res: Dict[str, Any]) -> str | None:
        # Flow._orch is called after prep
        return None 

    def post(self, shared_store: Dict[str, Any], prep_res: Any, exec_res: Any) -> str | None:
        transition, _ = self._run_handler_references(
            self.definition.post_handlers,
            shared_store,
            phase="workflow:post",
            transition=exec_res
        )
        self._pop_workflow_context(shared_store, True) # TODO: check if prompt pushed
        return transition

    def available_transitions(self, node_id: str) -> List[str]:
        return list(dict.fromkeys(self._transitions_by_source.get(node_id, [])))

    def _run_start_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        if not shared_store.get("active_agent"):
            shared_store["active_agent"] = (
                node_definition.attributes.get("agent")
                or self.definition.default_agent
                or self._runtime_config.get("default_agent")
            )
        return str(node_definition.attributes.get("transition", "continue"))

    def _run_end_node(
        self,
        _node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> None:
        if not shared_store.get("final_output"):
            shared_store["final_output"] = self._resolve_final_output(shared_store)
        return None

    def _run_output_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        shared_store["final_output"] = self._resolve_final_output(shared_store)
        return str(node_definition.attributes.get("transition", "done"))

    def _run_handoff_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        # Use pocketflow native transitions for handoff
        source_agent = str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None
        target_agent = (
            shared_store.pop("pending_handoff_agent", None)
            or node_definition.attributes.get("agent")
            or shared_store.get("active_agent")
        )

        if not target_agent:
            shared_store["error_message"] = "Handoff requested but no target agent was provided."
            return str(node_definition.attributes.get("error_transition", "error"))

        target_agent = str(target_agent)
        if target_agent not in self._plugins.agents:
            shared_store["error_message"] = f"Handoff target agent '{target_agent}' is not registered."
            return str(node_definition.attributes.get("error_transition", "error"))

        handoff_policy = self._resolve_handoff_policy(
            source_agent=source_agent,
            target_agent=target_agent,
            node_definition=node_definition,
            shared_store=shared_store,
        )

        handoff_llm_profile = self._resolve_handoff_llm_profile(
            source_agent=source_agent,
            target_agent=target_agent,
            shared_store=shared_store,
        )
        if handoff_llm_profile:
            shared_store.setdefault("dynamic_llm_overrides", {})[target_agent] = handoff_llm_profile

        context_mode = self._normalize_handoff_context_mode(handoff_policy.get("context_mode"))
        delegated_context = shared_store.pop("pending_handoff_context", None)
        if delegated_context is None and "context" in handoff_policy:
            delegated_context = handoff_policy.get("context")

        if context_mode == "delegated":
            shared_store["active_handoff_context"] = delegated_context
        else:
            shared_store.pop("active_handoff_context", None)
        shared_store["active_handoff_context_mode"] = context_mode

        return_to_caller = self._coerce_bool(handoff_policy.get("return_to_caller"), default=False)
        if return_to_caller and source_agent:
            frame = {
                "source_agent": source_agent,
                "target_agent": target_agent,
                "context_mode": context_mode,
                "return_to_caller": True,
                "return_transition": str(handoff_policy.get("return_transition") or "continue"),
            }
            shared_store.setdefault("_handoff_stack", []).append(frame)

        shared_store["active_agent"] = target_agent
        shared_store["handoff_history"] = shared_store.get("handoff_history", []) + [target_agent]
        shared_store.setdefault("handoff_history_detailed", []).append(
            {
                "source": source_agent,
                "target": target_agent,
                "policy": handoff_policy,
            }
        )
        return str(handoff_policy.get("handoff_transition") or node_definition.attributes.get("transition", "continue"))

    def _resolve_handoff_policy(
        self,
        source_agent: str | None,
        target_agent: str,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> Dict[str, Any]:
        policy: Dict[str, Any] = {}

        if source_agent and source_agent in self._plugins.agents:
            source_definition = self._plugins.agents[source_agent]
            if isinstance(source_definition.default_handoff_policy, dict):
                policy.update(source_definition.default_handoff_policy)
            target_policy = source_definition.handoff_policies.get(target_agent)
            if isinstance(target_policy, dict):
                policy.update(target_policy)

        node_default_policy = self._parse_inline_yaml(node_definition.attributes.get("handoff_policy"))
        if isinstance(node_default_policy, dict):
            policy = {**node_default_policy, **policy}

        pending = shared_store.pop("pending_handoff_policy", None)
        if isinstance(pending, dict):
            policy.update(pending)

        if "context_mode" not in policy:
            policy["context_mode"] = node_definition.attributes.get("context_mode", "whole")
        if "return_to_caller" not in policy:
            policy["return_to_caller"] = node_definition.attributes.get("return_to_caller", False)

        return policy

    def _finalize_handoff_return(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str | None:
        stack = shared_store.get("_handoff_stack")
        if not isinstance(stack, list) or not stack:
            return None

        top = stack[-1]
        if not isinstance(top, dict):
            return None

        target_agent = top.get("target_agent")
        source_agent = top.get("source_agent")
        if not target_agent or not source_agent:
            return None
        if str(shared_store.get("active_agent") or "") != str(target_agent):
            return None

        stack.pop()

        delegated_result = {
            "from_agent": str(target_agent),
            "to_agent": str(source_agent),
            "answer": shared_store.get("final_answer"),
            "question": shared_store.get("question_to_ask"),
            "last_tool_route": shared_store.get("last_tool_route"),
            "last_agent_decision": shared_store.get("last_agent_decision"),
        }
        shared_store["last_delegated_result"] = delegated_result
        shared_store.setdefault("delegated_results", []).append(delegated_result)

        shared_store.pop("final_answer", None)
        shared_store.pop("question_to_ask", None)
        shared_store.pop("final_output", None)
        shared_store["active_agent"] = str(source_agent)
        shared_store.pop("active_handoff_context", None)
        shared_store["active_handoff_context_mode"] = "whole"

        return str(top.get("return_transition") or node_definition.attributes.get("transition", "continue"))

    def _run_tool_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        pending_tool = shared_store.get("pending_tool", {})
        if not isinstance(pending_tool, dict):
            pending_tool = {}

        fixed_tool_name = node_definition.attributes.get("tool")
        if fixed_tool_name:
            pending_tool = {
                "name": fixed_tool_name,
                "arguments": self._parse_inline_yaml(node_definition.attributes.get("arguments", "{}")),
            }

        tool_name = pending_tool.get("name")
        arguments = pending_tool.get("arguments", {})

        if not tool_name:
            shared_store["error_message"] = "Tool node reached without pending tool request."
            return str(node_definition.attributes.get("error_transition", "error"))

        if not isinstance(arguments, dict):
            shared_store["error_message"] = "Tool arguments must be a YAML mapping/object."
            shared_store.pop("pending_tool", None)
            return str(node_definition.attributes.get("error_transition", "error"))

        result = self._tool_runtime.execute_tool(
            tool_name=str(tool_name),
            arguments=arguments,
            shared_store=shared_store,
            auto_confirm=bool(shared_store.get("auto_confirm_tools", False)),
            agent_name=str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None,
        )

        route_payload = {
            "tool": str(tool_name),
            "arguments": arguments,
            "result": result,
        }
        shared_store["last_tool_route"] = route_payload
        shared_store["last_tool_route_yaml"] = self._to_yaml(route_payload)
        shared_store.setdefault("tool_history", []).append(route_payload)
        shared_store.pop("pending_tool", None)

        tool_success = True
        if isinstance(result, dict) and result.get("success") is False:
            tool_success = False
            shared_store["error_message"] = str(result.get("error") or "Tool reported failure.")

        if tool_success:
            return str(node_definition.attributes.get("success_transition", "success"))
        return str(node_definition.attributes.get("error_transition", "error"))

    def _run_flow_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        target_workflow = (
            node_definition.attributes.get("flow")
            or node_definition.attributes.get("workflow")
            or node_definition.attributes.get("target")
            or node_definition.attributes.get("ref")
        )
        if not target_workflow:
            shared_store["error_message"] = (
                f"Flow node '{node_definition.node_id}' is missing 'flow' or 'workflow' attribute."
            )
            return str(node_definition.attributes.get("error_transition", "error"))

        target_workflow = str(target_workflow)
        if target_workflow not in self._plugins.workflows:
            shared_store["error_message"] = f"Nested workflow '{target_workflow}' is not registered."
            return str(node_definition.attributes.get("error_transition", "error"))

        stack = shared_store.get("_workflow_stack", [])
        if not isinstance(stack, list):
            stack = []
            shared_store["_workflow_stack"] = stack

        max_depth = int(self._runtime_config.get("max_nested_flow_depth", 64))
        if len(stack) >= max_depth:
            shared_store["error_message"] = (
                f"Nested workflow depth limit exceeded ({max_depth}). Current stack: {stack}"
            )
            return str(node_definition.attributes.get("error_transition", "error"))

        nested_runtime = self._resolve_workflow_runtime(target_workflow)
        prior_error = shared_store.get("error_message")
        nested_transition = nested_runtime.run(shared_store)

        return_transition = self._finalize_handoff_return(node_definition, shared_store)
        if return_transition:
            return return_transition

        if isinstance(nested_transition, str) and nested_transition.strip():
            return nested_transition

        if shared_store.get("error_message") and shared_store.get("error_message") != prior_error:
            return str(node_definition.attributes.get("error_transition", "error"))

        return str(node_definition.attributes.get("transition", "continue"))

    def _run_custom_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> str:
        outcome = self._invoke_handler(
            handler=handler,
            shared_store=shared_store,
            node_definition=node_definition,
            phase="node:custom",
        )
        transition, _ = self._consume_handler_outcome(outcome, shared_store)
        if transition is not None:
            return transition
        return str(node_definition.attributes.get("transition", "continue"))

    def _run_agent_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        agent_name = (
            node_definition.attributes.get("agent")
            or shared_store.get("active_agent")
            or self.definition.default_agent
            or self._runtime_config.get("default_agent")
        )

        if not agent_name:
            shared_store["error_message"] = "No active agent could be resolved for the agent node."
            return "error"

        agent_name = str(agent_name)
        if agent_name not in self._plugins.agents:
            shared_store["error_message"] = f"Agent '{agent_name}' is not registered."
            return "error"

        shared_store["active_agent"] = agent_name
        shared_store.setdefault("agent_trace", []).append(
            {
                "workflow": self.definition.name,
                "node": node_definition.node_id,
                "agent": agent_name,
            }
        )
        agent_definition = self._plugins.agents[agent_name]

        # T028: Route through flow_instance when available (programmatic or factory agents)
        if agent_definition.flow_instance is not None:
            # Ensure _registry is available for cross-agent delegation
            if "_registry" not in shared_store:
                try:
                    shared_store["_registry"] = self._plugins._holder.get()
                except AttributeError:
                    shared_store["_registry"] = None
            try:
                agent_definition.flow_instance.run(shared_store)
            except Exception as exc:
                logger.error("PocketFlow agent '%s' raised: %s", agent_name, exc, exc_info=True)
                shared_store["error_message"] = str(exc)
                return "error"
            return str(shared_store.get("transition", "continue"))

        transition: str | None = None
        transition, pre_halt = self._run_handler_references(
            list(agent_definition.pre_handlers),
            shared_store,
            phase="agent:pre",
            node_definition=node_definition,
            transition=transition,
        )
        transition, step_halt = self._run_handler_references(
            list(agent_definition.step_handlers),
            shared_store,
            phase="agent:steps",
            node_definition=node_definition,
            transition=transition,
        )

        if pre_halt or step_halt:
            transition, _ = self._run_handler_references(
                list(agent_definition.post_handlers),
                shared_store,
                phase="agent:post",
                node_definition=node_definition,
                transition=transition,
            )
            return str(transition or node_definition.attributes.get("fallback_transition", "error"))

        agent_execution_mode = str(
            node_definition.attributes.get("agent_execution_mode") or agent_definition.execution_mode or "node"
        ).strip().lower()
        composite_workflow = (
            node_definition.attributes.get("agent_workflow")
            or node_definition.attributes.get("flow")
            or agent_definition.composite_workflow
        )

        if agent_execution_mode in {"flow", "composite"} and composite_workflow:
            transition = self._run_agent_composite_flow(
                node_definition=node_definition,
                shared_store=shared_store,
                agent_name=agent_name,
                target_workflow=str(composite_workflow),
            )
            transition, _ = self._run_handler_references(
                list(agent_definition.post_handlers),
                shared_store,
                phase="agent:post",
                node_definition=node_definition,
                transition=transition,
            )
            return str(transition or node_definition.attributes.get("transition", "continue"))

        allowed_tools = self._plugins.resolve_tools_for_agent(agent_name)
        tool_definitions = self._tool_runtime.describe_tools(allowed_tools)
        allowed_transitions = self.available_transitions(node_definition.node_id)

        llm_profile = self._resolve_llm_profile(agent_name, agent_definition, node_definition, shared_store)

        request_payload = {
            "workflow": self.definition.name,
            "node": node_definition.node_id,
            "agent": {
                "name": agent_name,
                "description": agent_definition.description,
                "handoff_agents": agent_definition.handoff_agents,
                "llm_profile": llm_profile,
            },
            "request": shared_store.get("initial_request", ""),
            "context": {
                "cli_context": shared_store.get("cli_context", {}),
                "formatted_cli_context": shared_store.get("formatted_cli_context", "None provided."),
                "last_tool_route": shared_store.get("last_tool_route"),
                "last_delegated_result": shared_store.get("last_delegated_result"),
                "handoff_context_mode": shared_store.get("active_handoff_context_mode", "whole"),
                "handoff_context": shared_store.get("active_handoff_context"),
                "results": shared_store.get("results", {}),
            },
            "routing": {
                "allowed_transitions": allowed_transitions,
                "tool_call_transition": "call_tool",
                "final_answer_transition": "final_answer",
                "handoff_transition": "handoff",
            },
            "tools": tool_definitions,
        }

        response_contract = {
            "action": "call_tool | final_answer | ask_user | handoff | transition",
            "tool": "tool name when action=call_tool",
            "arguments": {"...": "tool arguments when action=call_tool"},
            "answer": "string answer when action=final_answer",
            "question": "string question when action=ask_user",
            "agent": "target agent when action=handoff",
            "context": "optional delegated context object/string for handoff",
            "handoff_policy": {
                "return_to_caller": "bool",
                "context_mode": "whole | delegated",
                "return_transition": "transition label when returning to caller",
            },
            "transition": "optional explicit transition label",
            "llm_profile": "optional profile to use for the next agent turn",
        }

        system_prompt = self._build_agent_system_prompt(
            agent_name=agent_name,
            node_definition=node_definition,
            shared_store=shared_store,
        )

        prompt = "\n\n".join(
            [
                system_prompt,
                "Input YAML:",
                self._to_yaml(request_payload),
                "Return ONLY YAML. Follow this schema exactly:",
                self._to_yaml(response_contract),
            ]
        )

        response_text = self._llm_router.generate(profile_name=llm_profile, prompt=prompt)
        llm_generation_info = self._llm_router.get_last_generation_info()
        shared_store["last_llm_generation"] = llm_generation_info
        shared_store["last_llm_profile"] = llm_profile

        usage = llm_generation_info.get("usage", {}) if isinstance(llm_generation_info, dict) else {}
        totals = shared_store.setdefault(
            "llm_usage_totals",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        if isinstance(usage, dict) and isinstance(totals, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")

            if isinstance(prompt_tokens, (int, float)):
                totals["prompt_tokens"] = int(totals.get("prompt_tokens", 0)) + int(prompt_tokens)
            if isinstance(completion_tokens, (int, float)):
                totals["completion_tokens"] = int(totals.get("completion_tokens", 0)) + int(completion_tokens)
            if isinstance(total_tokens, (int, float)):
                totals["total_tokens"] = int(totals.get("total_tokens", 0)) + int(total_tokens)

        estimated_cost = llm_generation_info.get("estimated_cost_usd", 0.0) if isinstance(llm_generation_info, dict) else 0.0
        if isinstance(estimated_cost, (int, float)):
            shared_store["llm_cost_usd_total"] = float(shared_store.get("llm_cost_usd_total", 0.0)) + float(estimated_cost)

        shared_store.setdefault("llm_calls", []).append(
            {
                "workflow": self.definition.name,
                "node": node_definition.node_id,
                "agent": agent_name,
                "profile": llm_generation_info.get("profile_name") if isinstance(llm_generation_info, dict) else llm_profile,
                "model": llm_generation_info.get("model") if isinstance(llm_generation_info, dict) else None,
                "usage": usage if isinstance(usage, dict) else {},
                "estimated_cost_usd": estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
            }
        )
        decision = self._parse_yaml_mapping(response_text)

        shared_store["last_agent_response_raw"] = response_text
        shared_store["last_agent_decision"] = decision
        shared_store["last_agent_decision_yaml"] = self._to_yaml(decision)

        transition = self._apply_agent_decision(
            decision=decision,
            agent_name=agent_name,
            node_definition=node_definition,
            shared_store=shared_store,
        )

        transition, _ = self._run_handler_references(
            list(agent_definition.post_handlers),
            shared_store,
            phase="agent:post",
            node_definition=node_definition,
            transition=transition,
        )

        if allowed_transitions and transition not in allowed_transitions:
            shared_store["error_message"] = (
                f"Transition '{transition}' is not allowed from node '{node_definition.node_id}'. "
                f"Allowed transitions: {allowed_transitions}"
            )
            if "error" in allowed_transitions:
                return "error"

        return transition

    def _run_agent_composite_flow(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
        agent_name: str,
        target_workflow: str,
    ) -> str:
        if target_workflow not in self._plugins.workflows:
            shared_store["error_message"] = (
                f"Composite workflow '{target_workflow}' for agent '{agent_name}' is not registered."
            )
            return str(node_definition.attributes.get("error_transition", "error"))

        nested_runtime = self._resolve_workflow_runtime(target_workflow)
        prior_error = shared_store.get("error_message")
        nested_transition = nested_runtime.run(shared_store)

        if isinstance(nested_transition, str) and nested_transition.strip():
            return str(nested_transition)

        if shared_store.get("error_message") and shared_store.get("error_message") != prior_error:
            return str(node_definition.attributes.get("error_transition", "error"))

        return str(node_definition.attributes.get("transition", "continue"))

    def _build_agent_system_prompt(
        self,
        agent_name: str,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        sections: List[str] = []

        active_flow_prompts = shared_store.get("_active_flow_prompts", [])
        if isinstance(active_flow_prompts, list):
            for prompt in active_flow_prompts:
                if isinstance(prompt, str) and prompt.strip():
                    sections.append(prompt.strip())

        node_prompt = node_definition.attributes.get("prompt")
        if isinstance(node_prompt, str) and node_prompt.strip():
            sections.append(node_prompt.strip())

        agent_prompt = self._plugins.agents[agent_name].system_prompt
        if agent_prompt and agent_prompt.strip():
            sections.append(agent_prompt.strip())

        if not sections:
            sections.append(f"You are agent '{agent_name}'. Use tools and route actions reliably.")

        return "\n\n".join(list(dict.fromkeys(sections)))

    def _run_python_node(
        self,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        handler_reference = (
            node_definition.attributes.get("handler")
            or node_definition.attributes.get("run")
            or node_definition.attributes.get("code")
        )
        if not handler_reference:
            handler_reference = f"nodes/{node_definition.node_id}.py:run"

        try:
            handler = self._resolve_python_handler(str(handler_reference))
            outcome = self._invoke_handler(
                handler=handler,
                shared_store=shared_store,
                node_definition=node_definition,
                phase="node:python",
            )
        except Exception as exc:
            shared_store["error_message"] = f"Python node '{node_definition.node_id}' failed: {exc}"
            return str(node_definition.attributes.get("error_transition", "error"))

        transition, _ = self._consume_handler_outcome(outcome, shared_store)
        if transition is not None:
            return transition
        return str(node_definition.attributes.get("transition", "continue"))

    def _resolve_llm_profile(
        self,
        agent_name: str,
        agent_definition: Any,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        dynamic_overrides = shared_store.get("dynamic_llm_overrides", {})
        cli_agent_overrides = shared_store.get("cli_agent_llm_overrides", {})
        cli_node_overrides = shared_store.get("cli_node_llm_overrides", {})
        config_agent_overrides = shared_store.get("config_agent_llm_overrides", {})
        config_node_overrides = shared_store.get("config_node_llm_overrides", {})

        profile = self._resolve_node_override(cli_node_overrides, node_definition)
        if not profile:
            profile = self._resolve_node_override(config_node_overrides, node_definition)

        if not profile and isinstance(cli_agent_overrides, dict):
            profile = cli_agent_overrides.get(agent_name)
        if not profile and isinstance(config_agent_overrides, dict):
            profile = config_agent_overrides.get(agent_name)

        if not profile:
            profile = shared_store.get("cli_llm_override")

        if not profile and isinstance(dynamic_overrides, dict):
            profile = dynamic_overrides.get(agent_name)

        if not profile:
            profile = node_definition.attributes.get("llm_profile")

        if not profile:
            profile = agent_definition.llm_profile

        if not profile:
            profile = shared_store.get("default_llm_profile")

        if not profile:
            profile = self._llm_router.default_profile_name

        if not profile:
            raise ValueError("No LLM profile could be resolved.")

        return str(profile)

    def _resolve_node_override(
        self,
        override_map: Any,
        node_definition: WorkflowNodeDefinition,
    ) -> str | None:
        if not isinstance(override_map, dict):
            return None

        workflow_node_key = f"{self.definition.name}.{node_definition.node_id}"
        profile = override_map.get(workflow_node_key)
        if profile:
            return str(profile)

        profile = override_map.get(node_definition.node_id)
        if profile:
            return str(profile)

        return None

    def _resolve_handoff_llm_profile(
        self,
        source_agent: str | None,
        target_agent: str,
        shared_store: Dict[str, Any],
    ) -> str | None:
        if not source_agent:
            return None

        handoff_key = f"{source_agent}->{target_agent}"
        cli_handoff_overrides = shared_store.get("cli_handoff_llm_overrides", {})
        config_handoff_overrides = shared_store.get("config_handoff_llm_overrides", {})
        dynamic_overrides = shared_store.get("dynamic_llm_overrides", {})

        if isinstance(cli_handoff_overrides, dict) and cli_handoff_overrides.get(handoff_key):
            return str(cli_handoff_overrides[handoff_key])

        if isinstance(config_handoff_overrides, dict) and config_handoff_overrides.get(handoff_key):
            return str(config_handoff_overrides[handoff_key])

        if isinstance(dynamic_overrides, dict) and dynamic_overrides.get(target_agent):
            return str(dynamic_overrides[target_agent])

        return None

    def _apply_agent_decision(
        self,
        decision: Dict[str, Any],
        agent_name: str,
        node_definition: WorkflowNodeDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        action = str(decision.get("action", "")).strip().lower()
        transition_override = decision.get("transition")
        chosen_profile = decision.get("llm_profile")

        if chosen_profile:
            shared_store.setdefault("dynamic_llm_overrides", {})[agent_name] = str(chosen_profile)

        if not action and transition_override:
            return str(transition_override)

        if action == "call_tool":
            tool_name = decision.get("tool") or decision.get("tool_name")
            if not tool_name:
                raise ValueError("Agent selected action=call_tool but did not include 'tool'.")

            arguments = decision.get("arguments") or decision.get("args") or {}
            if not isinstance(arguments, dict):
                raise ValueError("Agent tool arguments must be a YAML mapping.")

            shared_store["pending_tool"] = {
                "name": str(tool_name),
                "arguments": arguments,
                "requested_by": agent_name,
            }
            return str(transition_override or "call_tool")

        if action == "final_answer":
            answer = decision.get("answer")
            shared_store["final_answer"] = str(answer) if answer is not None else ""
            return str(transition_override or "final_answer")

        if action == "ask_user":
            question = decision.get("question")
            shared_store["question_to_ask"] = str(question) if question is not None else ""
            return str(transition_override or "ask_user")

        if action == "handoff":
            target_agent = decision.get("agent")
            if not target_agent and isinstance(decision.get("handoff"), dict):
                target_agent = decision["handoff"].get("agent")
            if not target_agent:
                raise ValueError("Agent selected action=handoff but did not include target agent.")

            handoff_block = decision.get("handoff") if isinstance(decision.get("handoff"), dict) else {}
            shared_store["pending_handoff_agent"] = str(target_agent)
            handoff_context = (
                decision.get("context")
                or handoff_block.get("context")
                or handoff_block.get("delegated_context")
            )
            if handoff_context is not None:
                shared_store["pending_handoff_context"] = handoff_context

            handoff_policy = decision.get("handoff_policy") or handoff_block.get("policy")
            if isinstance(handoff_policy, dict):
                shared_store["pending_handoff_policy"] = dict(handoff_policy)

            handoff_profile = decision.get("llm_profile")
            if handoff_profile:
                shared_store.setdefault("dynamic_llm_overrides", {})[str(target_agent)] = str(handoff_profile)

            return str(transition_override or "handoff")

        if action == "transition":
            if not transition_override:
                raise ValueError("Agent selected action=transition without a transition label.")
            return str(transition_override)

        if action:
            return str(transition_override or action)

        return str(node_definition.attributes.get("fallback_transition", "error"))


class CustomWorkflowRuntime(BaseWorkflowRuntime):
    def run(self, shared_store: Dict[str, Any]) -> str | None:
        self._prepare_shared_store(shared_store)
        prompt_pushed = self._push_workflow_context(shared_store)
        transition: str | None = None

        try:
            transition, pre_halt = self._run_handler_references(
                self.definition.pre_handlers,
                shared_store,
                phase="workflow:pre",
                transition=transition,
            )
            transition, step_halt = self._run_handler_references(
                self.definition.step_handlers,
                shared_store,
                phase="workflow:steps",
                transition=transition,
            )

            if not (pre_halt or step_halt):
                outcome = self._run_custom_flow(shared_store)
                custom_transition, _ = self._consume_handler_outcome(outcome, shared_store)
                if custom_transition is not None:
                    transition = custom_transition

            transition, _ = self._run_handler_references(
                self.definition.post_handlers,
                shared_store,
                phase="workflow:post",
                transition=transition,
            )

            if transition is None:
                transition_value = self.definition.metadata.get("transition")
                if isinstance(transition_value, str) and transition_value.strip():
                    transition = transition_value.strip()

            return transition
        except Exception as exc:
            logger.error(
                "Error while executing custom workflow '%s': %s",
                self.definition.name,
                exc,
                exc_info=True,
            )
            shared_store["error_message"] = f"Custom workflow '{self.definition.name}' failed: {exc}"
            return "error"
        finally:
            self._pop_workflow_context(shared_store, prompt_pushed)

    def _run_custom_flow(self, shared_store: Dict[str, Any]) -> Any:
        target = self.definition.custom_flow
        if target is None:
            raise ValueError(f"Custom workflow '{self.definition.name}' has no custom_flow reference.")

        if inspect.isclass(target):
            target = target()

        if hasattr(target, "run") and callable(getattr(target, "run")):
            return self._invoke_handler(
                handler=getattr(target, "run"),
                shared_store=shared_store,
                node_definition=None,
                phase="workflow:custom_run",
            )

        if callable(target):
            outcome = self._invoke_handler(
                handler=target,
                shared_store=shared_store,
                node_definition=None,
                phase="workflow:custom_callable",
            )
            if hasattr(outcome, "run") and callable(getattr(outcome, "run")):
                return self._invoke_handler(
                    handler=getattr(outcome, "run"),
                    shared_store=shared_store,
                    node_definition=None,
                    phase="workflow:custom_callable_run",
                )
            return outcome

        raise TypeError(
            f"Custom workflow '{self.definition.name}' resolved to unsupported type: {type(target)}"
        )
