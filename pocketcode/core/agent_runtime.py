from __future__ import annotations

import importlib
import importlib.util
import asyncio
import inspect
import logging
import sys
import threading
import types
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from pocketcode.core.catalog_metadata import namespace_name_from_metadata, namespace_root_from_metadata
from pocketcode.core.llm_yaml import parse_llm_yaml_mapping
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.workspace_catalog import WorkspaceCatalog
from pocketcode.core.prompt_loader import is_prompt_reference, resolve_prompt_reference
from pocketcode.core.run_handle import RunCancelledError
from pocketcode.core.agent_stack_vm import AgentStackVM, StackVmExecutionResult, StackVmHostContext
from pocketcode.core.stackvm_expander import expand_stackvm_ast
from pocketcode.core.stackvm_loader import load_stackvm_program_source
from pocketcode.core.stackvm_parser import parse_stackvm_source, serialize_stackvm_ast
from pocketcode.core.stackvm_validator import collect_stackvm_authoring_warnings, validate_stackvm_ast
from pocketcode.core.runtime_models import AgentDefinition, HOOK_PHASES, HookDefinition
from pocketcode.core.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Agent-only execution runtime.

    The runtime loop is the primary composition model:
    - agent turn (LLM or deterministic)
    - optional tool call
    - optional handoff to another agent
    - finalize answer or user question
    """

    def __init__(
        self,
        *,
        catalog: WorkspaceCatalog,
        llm_router: LlmRouter,
        tool_runtime: ToolRuntime,
        runtime_config: Dict[str, Any],
    ):
        self._catalog = catalog
        self._llm_router = llm_router
        self._tool_runtime = tool_runtime
        self._runtime_config = runtime_config
        self._python_handler_cache: Dict[str, Callable[..., Any]] = {}

    def run(self, shared_store: Dict[str, Any]) -> None:
        self._prepare_shared_store(shared_store)

        if not shared_store.get("active_agent"):
            raise RuntimeError("No active agent is set.")

        max_steps = int(self._runtime_config.get("max_agent_steps", 64))

        for _ in range(max_steps):
            self._raise_if_cancelled(shared_store)
            agent_name = str(shared_store.get("active_agent") or "").strip()
            if not agent_name:
                shared_store["error_message"] = "No active agent could be resolved."
                self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"])
                break
            if agent_name not in self._catalog.agents:
                shared_store["error_message"] = f"Agent '{agent_name}' is not registered."
                self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"], agent=agent_name)
                break

            transition = self._run_agent_turn(agent_name=agent_name, shared_store=shared_store)
            self._emit_event(
                shared_store,
                "agent_turn_completed",
                agent=agent_name,
                transition=transition,
            )

            if transition == "call_tool":
                self._run_tool_call(shared_store=shared_store)
                if shared_store.get("error_message"):
                    shared_store["final_output"] = self._resolve_final_output(shared_store)
                    break
                continue

            if transition == "handoff":
                self._run_handoff(shared_store=shared_store)
                if shared_store.get("error_message"):
                    shared_store["final_output"] = self._resolve_final_output(shared_store)
                    break
                continue

            if transition in {"final_answer", "ask_user"}:
                if self._finalize_handoff_return(shared_store=shared_store):
                    continue
                shared_store["final_output"] = self._resolve_final_output(shared_store)
                break

            if transition in {"continue", "next", "retry", "loop"}:
                continue

            if transition == "error":
                shared_store["final_output"] = self._resolve_final_output(shared_store)
                break

            # Unknown transitions default to continue for resilience.
            continue
        else:
            shared_store["error_message"] = (
                f"Agent runtime exceeded max steps ({max_steps})."
            )
            self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"])

        if not shared_store.get("final_output"):
            shared_store["final_output"] = self._resolve_final_output(shared_store)

    def _prepare_shared_store(self, shared_store: Dict[str, Any]) -> None:
        shared_store.setdefault("results", {})
        shared_store.setdefault("dynamic_llm_overrides", {})
        shared_store.setdefault("_handoff_stack", [])
        shared_store.setdefault("agent_trace", [])
        shared_store.setdefault("active_handoff_context_mode", "whole")
        shared_store.setdefault(
            "llm_usage_totals",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        shared_store.setdefault("llm_cost_usd_total", 0.0)
        shared_store.setdefault("llm_calls", [])
        # FR-011: populate registry snapshot for PocketFlow agents (T028)
        if "_registry" not in shared_store:
            try:
                shared_store["_registry"] = self._catalog._holder.get()
            except AttributeError:
                # Defensive: test doubles (MagicMock, etc.) may not have _holder
                shared_store["_registry"] = None

    def _emit_event(self, shared_store: Dict[str, Any], event_type: str, **payload: Any) -> None:
        handler = shared_store.get("runtime_event_handler")
        if callable(handler):
            handler(event_type, **payload)

    def _is_cancel_requested(self, shared_store: Dict[str, Any]) -> bool:
        value = shared_store.get("run_cancel_requested")
        if callable(value):
            return bool(value())
        return bool(value)

    def _get_cancel_reason(self, shared_store: Dict[str, Any]) -> str:
        value = shared_store.get("run_cancel_reason")
        if callable(value):
            value = value()
        if isinstance(value, str) and value.strip():
            return value
        return "Run cancelled by user."

    def _raise_if_cancelled(self, shared_store: Dict[str, Any]) -> None:
        if self._is_cancel_requested(shared_store):
            raise RunCancelledError(self._get_cancel_reason(shared_store))

    def _run_agent_turn(self, agent_name: str, shared_store: Dict[str, Any]) -> str:
        agent_definition = self._catalog.agents[agent_name]
        active_profile = self._get_active_profile_for_agent(agent_name, shared_store)

        shared_store["active_agent"] = agent_name
        shared_store.setdefault("agent_trace", []).append({"agent": agent_name})
        self._emit_event(
            shared_store,
            "agent_turn_started",
            agent=agent_name,
            execution_mode=agent_definition.execution_mode,
        )
        hook_transition = self._run_agent_hooks(
            phase="before_turn",
            agent_name=agent_name,
            agent_definition=agent_definition,
            active_profile=active_profile,
            shared_store=shared_store,
        )
        if hook_transition is not None:
            return hook_transition

        # Inject namespace context if available for this agent
        transition: str | None = None
        transition, pre_halt = self._run_handler_references(
            list(agent_definition.pre_handlers),
            shared_store,
            phase="agent:pre",
            agent_definition=agent_definition,
            transition=transition,
        )
        transition, step_halt = self._run_handler_references(
            list(agent_definition.step_handlers),
            shared_store,
            phase="agent:steps",
            agent_definition=agent_definition,
            transition=transition,
        )

        if pre_halt or step_halt:
            transition, _ = self._run_handler_references(
                list(agent_definition.post_handlers),
                shared_store,
                phase="agent:post",
                agent_definition=agent_definition,
                transition=transition,
            )
            return str(transition or "error")

        execution_mode = str(agent_definition.execution_mode or "llm").strip().lower()

        if execution_mode == "vm":
            transition = self._run_vm_agent(
                agent_name=agent_name,
                agent_definition=agent_definition,
                shared_store=shared_store,
            )
        elif agent_definition.flow_instance:
            transition = self._run_pocketflow_agent(
                agent_name=agent_name,
                agent_definition=agent_definition,
                shared_store=shared_store,
            )
        else:
            if execution_mode == "deterministic":
                transition = self._run_deterministic_agent(
                    agent_name=agent_name,
                    agent_definition=agent_definition,
                    shared_store=shared_store,
                )
            elif execution_mode == "composite":
                transition = self._run_composite_agent(
                    agent_name=agent_name,
                    agent_definition=agent_definition,
                    shared_store=shared_store,
                )
            else:
                transition = self._run_llm_agent(
                    agent_name=agent_name,
                    agent_definition=agent_definition,
                    shared_store=shared_store,
                )

        transition, _ = self._run_handler_references(
            list(agent_definition.post_handlers),
            shared_store,
            phase="agent:post",
            agent_definition=agent_definition,
            transition=transition,
        )
        after_turn_transition = self._run_agent_hooks(
            phase="after_turn",
            agent_name=agent_name,
            agent_definition=agent_definition,
            active_profile=active_profile,
            shared_store=shared_store,
        )
        if after_turn_transition is not None:
            return after_turn_transition

        return str(transition or "continue")

    def _resolve_hook_definitions(
        self,
        *,
        active_profile: Any,
        agent_name: str,
    ) -> list[HookDefinition]:
        hook_refs = list(getattr(active_profile, "hooks", None) or [])
        if not hook_refs:
            return []
        context_namespace = self._resolve_profile_namespace_name(active_profile) or self._context_namespace_for_agent(agent_name)
        resolved: list[HookDefinition] = []
        seen: set[str] = set()
        for hook_ref in hook_refs:
            try:
                qualified_name = self._catalog.hooks.qualify(str(hook_ref), context_namespace=context_namespace)
                if qualified_name in seen:
                    continue
                seen.add(qualified_name)
                hook_definition = self._catalog.hooks.resolve(qualified_name)
                resolved.append(hook_definition)
            except Exception:
                logger.warning("Skipping unresolved hook '%s' for agent '%s'.", hook_ref, agent_name)
        return resolved

    def _run_agent_hooks(
        self,
        *,
        phase: str,
        agent_name: str,
        agent_definition: AgentDefinition,
        active_profile: Any,
        shared_store: Dict[str, Any],
    ) -> str | None:
        if phase not in HOOK_PHASES:
            return None
        hook_definitions = self._resolve_hook_definitions(active_profile=active_profile, agent_name=agent_name)
        if not hook_definitions:
            return None
        for hook_definition in hook_definitions:
            vm_source = (hook_definition.phases or {}).get(phase)
            if not vm_source:
                continue
            shared_store["active_hook"] = hook_definition.name
            shared_store["active_hook_phase"] = phase
            transition = self._execute_hook_vm(
                hook_definition=hook_definition,
                vm_source=vm_source,
                agent_name=agent_name,
                agent_definition=agent_definition,
                shared_store=shared_store,
            )
            if transition in {"call_tool", "handoff", "final_answer", "ask_user", "error"}:
                return transition
        return None

    def _execute_hook_vm(
        self,
        *,
        hook_definition: HookDefinition,
        vm_source: str,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str | None:
        tool_names = list(shared_store.get("active_allowed_tools") or self._catalog.resolve_tools_for_agent(agent_name))
        tool_definitions = self._tool_runtime.describe_tools(tool_names)
        llm_profile = self._resolve_llm_profile(agent_name, agent_definition, shared_store)
        system_prompt = self._build_agent_system_prompt(agent_name=agent_name)
        overlay_prompt = self._resolve_overlay_prompt_content(
            active_profile=self._get_active_profile_for_agent(agent_name, shared_store),
            shared_store=shared_store,
        )
        if overlay_prompt:
            system_prompt = f"{system_prompt}\n\n{overlay_prompt}"
        result = StackVmExecutionResult()
        vm = AgentStackVM(shared_store=shared_store)
        vm.register_host_words(
            host_context=StackVmHostContext(
                agent_name=agent_name,
                llm_router=self._llm_router,
                tool_runtime=self._tool_runtime,
                llm_profile=llm_profile,
                system_prompt=system_prompt,
                tool_definitions=tool_definitions,
            ),
            result=result,
        )
        try:
            asyncio.run(vm.eval(vm_source))
        except Exception as exc:
            logger.warning("Hook '%s' phase '%s' failed: %s", hook_definition.name, shared_store.get("active_hook_phase"), exc)
            return "error"
        return result.transition

    def _run_pocketflow_agent(
        self,
        *,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        """Executes a programmatic pocketflow.Flow-based agent."""
        try:
            # Inject runtime services for programmatic flows (e.g., react_agent).
            # Use setdefault so test doubles can inject their own instances.
            shared_store.setdefault("_llm_router", self._llm_router)
            shared_store.setdefault("_tool_runtime", self._tool_runtime)
            active_profile = self._get_active_profile_for_agent(agent_name, shared_store)

            # Pre-compute tool definitions for the active agent each turn.
            try:
                _allowed = self._resolve_effective_tool_names(
                    agent_name=agent_name,
                    active_profile=active_profile,
                    shared_store=shared_store,
                )
                shared_store["active_allowed_tools"] = list(_allowed)
                shared_store["_agent_tool_definitions"] = self._tool_runtime.describe_tools(_allowed)
            except Exception:
                shared_store.setdefault("_agent_tool_definitions", [])

            # Resolve the LLM profile for this agent turn.
            try:
                shared_store["_agent_llm_profile"] = self._resolve_llm_profile(
                    agent_name, agent_definition, shared_store
                )
            except Exception:
                pass

            # T017: inject system prompt with extra_prompts for pocketflow agents.
            _pf_base_prompt = self._build_agent_system_prompt(agent_name=agent_name)
            _pf_extra = self._resolve_overlay_prompt_content(
                active_profile=active_profile,
                shared_store=shared_store,
            )
            shared_store["_agent_system_prompt"] = (
                _pf_base_prompt + "\n\n" + _pf_extra if _pf_extra else _pf_base_prompt
            )

            # PocketFlow returns the transition string or None
            # T011, T028 implementation
            outcome = agent_definition.flow_instance.run(shared_store)
            
            if isinstance(outcome, str):
                return outcome
            
            if isinstance(outcome, dict):
                 return self._apply_agent_decision(
                    decision=outcome,
                    agent_name=agent_name,
                    shared_store=shared_store,
                )
            
            # Default to continue if nothing specific returned but flow finished
            return "continue"
        except Exception as e:
            logger.exception(f"Error executing PocketFlow agent '{agent_name}': {e}")
            shared_store["error_message"] = f"Flow execution failed: {e}"
            return "error"

    def _run_vm_agent(
        self,
        *,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        try:
            shared_store.setdefault("_llm_router", self._llm_router)
            shared_store.setdefault("_tool_runtime", self._tool_runtime)
            active_profile = self._get_active_profile_for_agent(agent_name, shared_store)

            try:
                allowed_tools = self._resolve_effective_tool_names(
                    agent_name=agent_name,
                    active_profile=active_profile,
                    shared_store=shared_store,
                )
                shared_store["active_allowed_tools"] = list(allowed_tools)
                shared_store["_agent_tool_definitions"] = self._tool_runtime.describe_tools(allowed_tools)
            except Exception:
                shared_store.setdefault("_agent_tool_definitions", [])

            try:
                shared_store["_agent_llm_profile"] = self._resolve_llm_profile(
                    agent_name, agent_definition, shared_store
                )
            except Exception:
                pass

            base_prompt = self._build_agent_system_prompt(agent_name=agent_name)
            extra_prompt = self._resolve_overlay_prompt_content(
                active_profile=active_profile,
                shared_store=shared_store,
            )
            shared_store["_agent_system_prompt"] = (
                base_prompt + "\n\n" + extra_prompt if extra_prompt else base_prompt
            )

            metadata = dict(agent_definition.metadata or {})
            search_roots: list[Path] = []
            markdown_path = metadata.get("markdown_path")
            namespace_root = metadata.get("namespace_root")
            resource_root = metadata.get("resource_root")
            if markdown_path:
                search_roots.append(Path(str(markdown_path)).resolve().parent)
            if namespace_root:
                search_roots.append(Path(str(namespace_root)).resolve())
            if resource_root:
                search_roots.append(Path(str(resource_root)).resolve())

            source, source_files = load_stackvm_program_source(
                vm_source=agent_definition.vm_source,
                vm_entry=agent_definition.vm_entry,
                vm_module=agent_definition.vm_module,
                vm_modules=agent_definition.vm_modules,
                vm_file=agent_definition.vm_file,
                vm_files=agent_definition.vm_files,
                base_dir=search_roots[0] if search_roots else Path.cwd(),
                search_roots=search_roots,
            )
            if not source.strip() and not agent_definition.vm_entry:
                raise ValueError(f"VM agent '{agent_name}' has no executable StackVM source.")

            expanded_ast: list[Any] = []
            validation_warnings: list[dict[str, str]] = []
            expansion_metadata = {
                "expansion_count": 0,
                "macro_names": [],
                "builtin_macro_names": [],
                "gensym_count": 0,
                "expansion_trace": [],
            }
            if source.strip():
                source_ast = parse_stackvm_source(source)
                validation_warnings = collect_stackvm_authoring_warnings(source_ast, source=source)
                expanded = expand_stackvm_ast(source_ast)
                validate_stackvm_ast(expanded.ast)
                expanded_ast = expanded.ast
                used_macro_names = list(dict.fromkeys(expanded.expansion_trace))
                builtin_macro_names = [
                    name
                    for name in used_macro_names
                    if name in expanded.macros and expanded.macros[name].builtin
                ]
                expansion_metadata = {
                    "expansion_count": expanded.expansion_count,
                    "macro_names": used_macro_names,
                    "builtin_macro_names": builtin_macro_names,
                    "gensym_count": expanded.gensym_count,
                    "expansion_trace": list(expanded.expansion_trace),
                }

            result = StackVmExecutionResult(source_files=source_files)
            host_context = StackVmHostContext(
                agent_name=agent_name,
                llm_router=self._llm_router,
                tool_runtime=self._tool_runtime,
                llm_profile=shared_store.get("_agent_llm_profile"),
                system_prompt=shared_store.get("_agent_system_prompt", ""),
                tool_definitions=list(shared_store.get("_agent_tool_definitions", [])),
            )
            vm = AgentStackVM(shared_store=shared_store)
            vm.register_host_words(host_context=host_context, result=result)
            self._run_stackvm_program(vm=vm, ast=expanded_ast, entry=agent_definition.vm_entry)
            shared_store["last_vm_sources"] = list(source_files)
            shared_store["last_vm_source"] = source
            shared_store["last_vm_expanded_source"] = serialize_stackvm_ast(expanded_ast) if expanded_ast else ""
            shared_store["last_vm_expansion_metadata"] = expansion_metadata
            shared_store["last_vm_validation_warnings"] = list(validation_warnings)

            if result.transition:
                return result.transition
            if shared_store.get("pending_tool"):
                return "call_tool"
            if shared_store.get("pending_handoff_agent"):
                return "handoff"
            if shared_store.get("question_to_ask"):
                return "ask_user"
            if shared_store.get("final_answer"):
                return "final_answer"
            if vm.stack and isinstance(vm.stack[-1], str):
                return str(vm.stack[-1])
            return "continue"
        except Exception as exc:
            logger.exception("Error executing StackVM agent '%s': %s", agent_name, exc)
            shared_store["error_message"] = f"VM execution failed: {exc}"
            return "error"

    def _run_stackvm_program(self, *, vm: AgentStackVM, ast: list[Any], entry: str | None) -> None:
        async def _runner() -> None:
            if ast:
                await vm.execute_ast(ast)
            if entry:
                await vm.execute_word(entry)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_runner())
            return

        thread_error: dict[str, BaseException] = {}

        def _thread_runner() -> None:
            try:
                asyncio.run(_runner())
            except BaseException as exc:  # pragma: no cover - reraised in caller thread
                thread_error["exc"] = exc

        worker = threading.Thread(target=_thread_runner, name="stackvm-runner")
        worker.start()
        worker.join()
        if "exc" in thread_error:
            raise thread_error["exc"]

    def _run_deterministic_agent(
        self,
        *,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        handler_ref = agent_definition.deterministic_handler
        if not handler_ref:
            shared_store["error_message"] = (
                f"Deterministic agent '{agent_name}' is missing deterministic_handler."
            )
            return "error"

        handler = self._resolve_python_handler(
            handler_reference=handler_ref,
            namespace_root=Path(str(agent_definition.metadata.get("namespace_root", ""))).resolve()
            if agent_definition.metadata.get("namespace_root")
            else None,
        )
        outcome = self._invoke_handler(
            handler=handler,
            shared_store=shared_store,
            agent_definition=agent_definition,
            phase="agent:deterministic",
        )

        if isinstance(outcome, str):
            return outcome

        if isinstance(outcome, dict):
            return self._apply_agent_decision(
                decision=outcome,
                agent_name=agent_name,
                shared_store=shared_store,
            )

        shared_store["error_message"] = (
            f"Deterministic agent '{agent_name}' returned unsupported output type {type(outcome)}."
        )
        return "error"

    def _run_composite_agent(
        self,
        *,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        sub_agents = [a for a in agent_definition.composite_agents if a in self._catalog.agents]
        if not sub_agents:
            shared_store["error_message"] = (
                f"Composite agent '{agent_name}' has no valid composite_agents configured."
            )
            return "error"

        state = shared_store.setdefault("_composite_state", {})
        if not isinstance(state, dict):
            state = {}
            shared_store["_composite_state"] = state

        index = int(state.get(agent_name, 0))
        if index < len(sub_agents):
            target = sub_agents[index]
            state[agent_name] = index + 1
            shared_store["pending_handoff_agent"] = target
            shared_store["pending_handoff_policy"] = {
                "return_to_caller": True,
                "context_mode": "whole",
                "return_transition": "continue",
            }
            return "handoff"

        state[agent_name] = 0
        delegated = shared_store.get("last_delegated_result", {})
        if isinstance(delegated, dict):
            answer = delegated.get("answer")
            question = delegated.get("question")
            if answer:
                shared_store["final_answer"] = str(answer)
                return "final_answer"
            if question:
                shared_store["question_to_ask"] = str(question)
                return "ask_user"

        return "continue"

    def _run_llm_agent(
        self,
        *,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        active_profile = self._get_active_profile_for_agent(agent_name, shared_store)
        hook_transition = self._run_agent_hooks(
            phase="before_llm",
            agent_name=agent_name,
            agent_definition=agent_definition,
            active_profile=active_profile,
            shared_store=shared_store,
        )
        if hook_transition is not None:
            return hook_transition
        allowed_tools = self._resolve_effective_tool_names(
            agent_name=agent_name,
            active_profile=active_profile,
            shared_store=shared_store,
        )
        shared_store["active_allowed_tools"] = list(allowed_tools)
        tool_definitions = self._tool_runtime.describe_tools(allowed_tools)

        llm_profile = self._resolve_llm_profile(agent_name, agent_definition, shared_store)

        request_payload = {
            "agent": {
                "name": agent_name,
                "description": agent_definition.description,
                "handoff_agents": agent_definition.handoff_agents,
                "execution_mode": agent_definition.execution_mode,
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

        system_prompt = self._build_agent_system_prompt(agent_name=agent_name)
        # T017: append active profile and enabled skill prompt overlays.
        _ep_content = self._resolve_overlay_prompt_content(
            active_profile=active_profile,
            shared_store=shared_store,
        )
        if _ep_content:
            system_prompt = system_prompt + "\n\n" + _ep_content
        prompt = "\n\n".join(
            [
                system_prompt,
                "Input YAML:",
                self._to_yaml(request_payload),
                "Return ONLY YAML. Follow this schema exactly:",
                self._to_yaml(response_contract),
            ]
        )

        self._emit_event(
            shared_store,
            "llm_call_started",
            agent=agent_name,
            profile=llm_profile,
            prompt_text=prompt,
        )
        self._raise_if_cancelled(shared_store)
        response_text = self._llm_router.generate(profile_name=llm_profile, prompt=prompt)
        self._raise_if_cancelled(shared_store)
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

        estimated_cost = (
            llm_generation_info.get("estimated_cost_usd", 0.0)
            if isinstance(llm_generation_info, dict)
            else 0.0
        )
        if isinstance(estimated_cost, (int, float)):
            shared_store["llm_cost_usd_total"] = float(shared_store.get("llm_cost_usd_total", 0.0)) + float(estimated_cost)

        shared_store.setdefault("llm_calls", []).append(
            {
                "agent": agent_name,
                "profile": llm_generation_info.get("profile_name") if isinstance(llm_generation_info, dict) else llm_profile,
                "model": llm_generation_info.get("model") if isinstance(llm_generation_info, dict) else None,
                "usage": usage if isinstance(usage, dict) else {},
                "estimated_cost_usd": estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
            }
        )
        self._emit_event(
            shared_store,
            "llm_call_completed",
            agent=agent_name,
            profile=llm_profile,
            model=llm_generation_info.get("model") if isinstance(llm_generation_info, dict) else None,
            usage=usage if isinstance(usage, dict) else {},
            estimated_cost_usd=estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
            prompt_text=prompt,
            response_text=response_text,
        )

        decision = self._parse_yaml_mapping(response_text)
        shared_store["last_agent_response_raw"] = response_text
        shared_store["last_agent_decision"] = decision
        shared_store["last_agent_decision_yaml"] = self._to_yaml(decision)

        transition = self._apply_agent_decision(
            decision=decision,
            agent_name=agent_name,
            shared_store=shared_store,
        )
        hook_transition = self._run_agent_hooks(
            phase="after_llm",
            agent_name=agent_name,
            agent_definition=agent_definition,
            active_profile=active_profile,
            shared_store=shared_store,
        )
        return hook_transition or transition

    def _run_tool_call(self, shared_store: Dict[str, Any]) -> None:
        self._raise_if_cancelled(shared_store)
        active_agent = str(shared_store.get("active_agent") or "").strip()
        agent_definition = self._catalog.agents.get(active_agent) if active_agent else None
        active_profile = (
            self._get_active_profile_for_agent(active_agent, shared_store)
            if active_agent and agent_definition is not None
            else None
        )
        if active_agent and agent_definition is not None and active_profile is not None:
            hook_transition = self._run_agent_hooks(
                phase="before_tool",
                agent_name=active_agent,
                agent_definition=agent_definition,
                active_profile=active_profile,
                shared_store=shared_store,
            )
            if hook_transition in {"final_answer", "ask_user", "handoff", "call_tool", "error"}:
                return
        pending_tool = shared_store.get("pending_tool", {})
        if not isinstance(pending_tool, dict):
            pending_tool = {}

        tool_name = pending_tool.get("name")
        arguments = pending_tool.get("arguments", {})

        if not tool_name:
            shared_store["error_message"] = "Tool action selected but no tool name was provided."
            self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"])
            return
        if not isinstance(arguments, dict):
            shared_store["error_message"] = "Tool arguments must be a mapping/object."
            self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"])
            return

        self._emit_event(
            shared_store,
            "tool_started",
            agent=str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None,
            tool=str(tool_name),
            arguments=arguments,
        )
        result = self._tool_runtime.execute_tool(
            tool_name=str(tool_name),
            arguments=arguments,
            shared_store=shared_store,
            auto_confirm=bool(shared_store.get("auto_confirm_tools", False)),
            agent_name=str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None,
        )
        self._raise_if_cancelled(shared_store)

        route_payload = {
            "tool": str(tool_name),
            "arguments": arguments,
            "result": result,
        }
        shared_store["last_tool_result"] = result
        shared_store["last_tool_route"] = route_payload
        shared_store["last_tool_route_yaml"] = self._to_yaml(route_payload)
        shared_store["last_tool_failed"] = bool(isinstance(result, dict) and result.get("success") is False)
        shared_store.setdefault("tool_history", []).append(route_payload)
        shared_store.pop("pending_tool", None)
        self._emit_event(
            shared_store,
            "tool_finished",
            agent=str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None,
            tool=str(tool_name),
            success=not (isinstance(result, dict) and result.get("success") is False),
            result=result,
        )
        if active_agent and agent_definition is not None and active_profile is not None:
            self._run_agent_hooks(
                phase="after_tool",
                agent_name=active_agent,
                agent_definition=agent_definition,
                active_profile=active_profile,
                shared_store=shared_store,
            )

    def _run_handoff(self, shared_store: Dict[str, Any]) -> None:
        source_agent = str(shared_store.get("active_agent")) if shared_store.get("active_agent") else None
        target_agent = shared_store.pop("pending_handoff_agent", None)

        if not target_agent:
            shared_store["error_message"] = "Handoff requested but no target agent was provided."
            self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"])
            return

        target_agent = str(target_agent)
        if target_agent not in self._catalog.agents:
            shared_store["error_message"] = f"Handoff target agent '{target_agent}' is not registered."
            self._emit_event(shared_store, "runtime_error", message=shared_store["error_message"], target_agent=target_agent)
            return

        handoff_policy = self._resolve_handoff_policy(
            source_agent=source_agent,
            target_agent=target_agent,
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
        self._emit_event(
            shared_store,
            "handoff",
            source_agent=source_agent,
            target_agent=target_agent,
            context_mode=context_mode,
            return_to_caller=return_to_caller,
        )

    def _finalize_handoff_return(self, shared_store: Dict[str, Any]) -> bool:
        stack = shared_store.get("_handoff_stack")
        if not isinstance(stack, list) or not stack:
            return False

        top = stack[-1]
        if not isinstance(top, dict):
            return False

        target_agent = top.get("target_agent")
        source_agent = top.get("source_agent")
        if not target_agent or not source_agent:
            return False
        if str(shared_store.get("active_agent") or "") != str(target_agent):
            return False

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
        self._emit_event(
            shared_store,
            "handoff_return",
            source_agent=str(source_agent),
            target_agent=str(target_agent),
            return_transition=str(top.get("return_transition") or "continue"),
        )

        return True

    def _resolve_handoff_policy(
        self,
        *,
        source_agent: str | None,
        target_agent: str,
        shared_store: Dict[str, Any],
    ) -> Dict[str, Any]:
        policy: Dict[str, Any] = {}

        if source_agent and source_agent in self._catalog.agents:
            source_definition = self._catalog.agents[source_agent]
            if isinstance(source_definition.default_handoff_policy, dict):
                policy.update(source_definition.default_handoff_policy)
            target_policy = source_definition.handoff_policies.get(target_agent)
            if isinstance(target_policy, dict):
                policy.update(target_policy)

        pending = shared_store.pop("pending_handoff_policy", None)
        if isinstance(pending, dict):
            policy.update(pending)

        if "context_mode" not in policy:
            policy["context_mode"] = "whole"
        if "return_to_caller" not in policy:
            policy["return_to_caller"] = False

        return policy

    def _resolve_handoff_llm_profile(
        self,
        *,
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

    def _resolve_llm_profile(
        self,
        agent_name: str,
        agent_definition: AgentDefinition,
        shared_store: Dict[str, Any],
    ) -> str:
        dynamic_overrides = shared_store.get("dynamic_llm_overrides", {})
        cli_agent_overrides = shared_store.get("cli_agent_llm_overrides", {})
        config_agent_overrides = shared_store.get("config_agent_llm_overrides", {})

        profile: Any = None

        if isinstance(cli_agent_overrides, dict):
            profile = cli_agent_overrides.get(agent_name)
        if not profile and isinstance(config_agent_overrides, dict):
            profile = config_agent_overrides.get(agent_name)
        if not profile:
            profile = shared_store.get("cli_llm_override")
        if not profile and isinstance(dynamic_overrides, dict):
            profile = dynamic_overrides.get(agent_name)
        # Tier 4.5: active agent profile llm_profile (FR-012 / T015).
        if not profile:
            _active_prof = self._get_active_profile_for_agent(agent_name, shared_store)
            if _active_prof and _active_prof.llm_profile:
                profile = _active_prof.llm_profile
        if not profile:
            profile = agent_definition.llm_profile
        if not profile:
            profile = shared_store.get("default_llm_profile")
        if not profile:
            profile = self._llm_router.default_profile_name

        if not profile:
            raise ValueError("No LLM profile could be resolved.")

        return str(profile)

    def _apply_agent_decision(
        self,
        *,
        decision: Dict[str, Any],
        agent_name: str,
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
            self._emit_event(
                shared_store,
                "final_answer",
                agent=agent_name,
                answer=shared_store["final_answer"],
            )
            return str(transition_override or "final_answer")

        if action == "ask_user":
            question = decision.get("question")
            shared_store["question_to_ask"] = str(question) if question is not None else ""
            self._emit_event(
                shared_store,
                "ask_user",
                agent=agent_name,
                question=shared_store["question_to_ask"],
            )
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

        return "error"

    def _build_agent_system_prompt(self, *, agent_name: str) -> str:
        agent_prompt = self._catalog.agents[agent_name].system_prompt
        if agent_prompt and agent_prompt.strip():
            return agent_prompt.strip()
        return f"You are agent '{agent_name}'. Use tools and route actions reliably."

    def _run_handler_references(
        self,
        handler_references: List[str],
        shared_store: Dict[str, Any],
        *,
        phase: str,
        agent_definition: AgentDefinition,
        transition: str | None = None,
    ) -> tuple[str | None, bool]:
        current_transition = transition
        halt = False
        namespace_root_value = agent_definition.metadata.get("namespace_root")
        namespace_root = Path(str(namespace_root_value)).resolve() if namespace_root_value else None

        for handler_reference in handler_references:
            self._raise_if_cancelled(shared_store)
            handler = self._resolve_python_handler(
                handler_reference=handler_reference,
                namespace_root=namespace_root,
            )
            outcome = self._invoke_handler(
                handler=handler,
                shared_store=shared_store,
                agent_definition=agent_definition,
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

    def _resolve_python_handler(
        self,
        *,
        handler_reference: str,
        namespace_root: Path | None,
    ) -> Callable[..., Any]:
        cache_key = f"{namespace_root}:{handler_reference}"
        if cache_key in self._python_handler_cache:
            return self._python_handler_cache[cache_key]

        if ":" in handler_reference:
            path_part, function_name = handler_reference.split(":", 1)
            candidate_file = Path(path_part)
            if not candidate_file.is_absolute():
                if namespace_root is None:
                    raise FileNotFoundError(
                        f"Cannot resolve relative handler path without namespace_root: {handler_reference}"
                    )
                candidate_file = (namespace_root / path_part).resolve()

            if not candidate_file.is_file():
                raise FileNotFoundError(
                    f"Python handler file not found for '{handler_reference}': {candidate_file}"
                )

            token = f"{candidate_file.resolve()}:{hash(candidate_file.read_bytes())}"
            module_name = f"pocketcode_runtime_agent_{abs(hash(token))}"
            sys.modules.pop(module_name, None)
            module = types.ModuleType(module_name)
            module.__file__ = str(candidate_file)
            sys.modules[module_name] = module
            source = candidate_file.read_text(encoding="utf-8")
            code = compile(source, str(candidate_file), "exec")
            exec(code, module.__dict__)

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

        self._python_handler_cache[cache_key] = handler
        return handler

    def _invoke_handler(
        self,
        *,
        handler: Callable[..., Any],
        shared_store: Dict[str, Any],
        agent_definition: AgentDefinition,
        phase: str | None,
        transition: str | None = None,
    ) -> Any:
        signature = inspect.signature(handler)
        kwargs: Dict[str, Any] = {}

        if "shared_store" in signature.parameters:
            kwargs["shared_store"] = shared_store
        if "agent_definition" in signature.parameters:
            kwargs["agent_definition"] = agent_definition
        if "agent" in signature.parameters:
            kwargs["agent"] = agent_definition
        if "runtime" in signature.parameters:
            kwargs["runtime"] = self
        if "phase" in signature.parameters:
            kwargs["phase"] = phase
        if "transition" in signature.parameters:
            kwargs["transition"] = transition
        if "catalog" in signature.parameters:
            kwargs["catalog"] = self._catalog
        if "llm_router" in signature.parameters:
            kwargs["llm_router"] = self._llm_router
        if "tool_runtime" in signature.parameters:
            kwargs["tool_runtime"] = self._tool_runtime

        return handler(**kwargs)

    def _parse_yaml_mapping(self, text: str) -> Dict[str, Any]:
        parsed = parse_llm_yaml_mapping(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected YAML mapping from LLM, got: {type(parsed)}")
        return parsed

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

    def _resolve_extra_prompts_content(self, profile: Any) -> str:
        """Read and concatenate extra_prompts files from *profile*.

        Resolves each path:
        1. Relative to ``profile.source_path.parent`` (workspace YAML file dir).
        2. Relative to the active namespace, when available.
        3. Relative to ``<workspace_root>/``, ``<workspace_root>/.pocketcode/``,
           and ``<workspace_root>/.pocketcode/prompts/``.

        Logs a WARNING and skips any path that cannot be resolved or read.
        """
        if profile is None or not profile.extra_prompts:
            return ""
        workspace_root = self._catalog.workspace_root
        namespace_root = self._resolve_profile_namespace_root(profile)
        context_namespace = self._resolve_profile_namespace_name(profile)
        parts: List[str] = []
        for path_str in profile.extra_prompts:
            if is_prompt_reference(path_str):
                try:
                    prompt_text, _ = resolve_prompt_reference(
                        path_str,
                        prompt_registry=self._catalog.prompts,
                        context_namespace=context_namespace,
                    )
                    if prompt_text:
                        parts.append(prompt_text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "extra_prompts: could not resolve prompt reference '%s' for profile '%s': %s. Skipping.",
                        path_str,
                        profile.name,
                        exc,
                    )
                continue
            resolved = None
            if profile.source_path is not None:
                candidate = profile.source_path.parent / path_str
                if candidate.is_file():
                    resolved = candidate
            if resolved is None and namespace_root is not None:
                candidate = namespace_root / path_str
                if candidate.is_file():
                    resolved = candidate
            if resolved is None:
                for base_dir in self._catalog._workspace_prompt_fallback_dirs():
                    candidate = base_dir / path_str
                    if candidate.is_file():
                        resolved = candidate
                        break
            if resolved is None:
                logger.warning(
                    "extra_prompts: could not resolve '%s' for profile '%s'. Skipping.",
                    path_str,
                    profile.name,
                )
                continue
            try:
                parts.append(resolved.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "extra_prompts: failed to read '%s': %s. Skipping.",
                    resolved,
                    exc,
                )
        return "\n\n".join(parts)

    def _resolve_overlay_prompt_content(
        self,
        *,
        active_profile: Any,
        shared_store: Dict[str, Any],
    ) -> str:
        parts: List[str] = []

        inline_prompt = str(getattr(active_profile, "inline_prompt", "") or "").strip()
        if inline_prompt:
            parts.append(inline_prompt)

        extra_prompt_text = self._resolve_extra_prompts_content(active_profile)
        if extra_prompt_text:
            parts.append(extra_prompt_text)

        for skill in shared_store.get("active_skills", []) or []:
            skill_prompt = str(getattr(skill, "inline_prompt", "") or "").strip()
            if skill_prompt:
                parts.append(skill_prompt)
            skill_extra = self._resolve_extra_prompts_content(skill)
            if skill_extra:
                parts.append(skill_extra)

        return "\n\n".join(part for part in parts if part)

    def _context_namespace_for_agent(self, agent_name: str | None) -> str | None:
        if not agent_name:
            return None
        agent_definition = self._catalog.agents.get(agent_name)
        if agent_definition is None:
            return None
        return namespace_name_from_metadata(
            getattr(agent_definition, "metadata", {}) or {},
            fallback_qualified_name=agent_name,
        )

    def _resolve_effective_tool_names(
        self,
        *,
        agent_name: str,
        active_profile: Any,
        shared_store: Dict[str, Any],
    ) -> List[str]:
        tool_names = list(self._catalog.resolve_tools_for_agent(agent_name))
        if active_profile is not None and active_profile.tools is not None:
            tool_names = [tool_name for tool_name in tool_names if tool_name in active_profile.tools]

        for tool_name in shared_store.get("active_skill_existing_tool_refs", []) or []:
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        for tool_name in shared_store.get("active_skill_tool_names", []) or []:
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        return tool_names

    def _get_active_profile_for_agent(self, agent_name: str, shared_store: Dict[str, Any]) -> Any:
        profile = shared_store.get("active_agent_profile")
        if profile is None:
            return None
        profile_agent = getattr(profile, "agent", None)
        normalized_agent_name = self._catalog.agents.qualify(agent_name)
        normalized_profile_agent = self._catalog.agents.qualify(profile_agent) if profile_agent else None
        return profile if normalized_profile_agent == normalized_agent_name else None

    def _resolve_profile_namespace_root(self, profile: Any) -> Path | None:
        agent_name = getattr(profile, "agent", None)
        if not isinstance(agent_name, str):
            return None
        agent_definition = self._catalog.agents.get(agent_name)
        if agent_definition is None:
            return None
        return namespace_root_from_metadata(getattr(agent_definition, "metadata", {}) or {})

    def _resolve_profile_namespace_name(self, profile: Any) -> str | None:
        agent_name = getattr(profile, "agent", None)
        if not isinstance(agent_name, str):
            return None
        agent_definition = self._catalog.agents.get(agent_name)
        if agent_definition is None:
            return None
        return namespace_name_from_metadata(
            getattr(agent_definition, "metadata", {}) or {},
            fallback_qualified_name=agent_name,
        )
