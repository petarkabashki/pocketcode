from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import yaml

from pocketcode.core.runtime_effects import (
    RuntimeEffect,
    serialize_runtime_effect,
    transition_from_runtime_effect,
)


@dataclass(frozen=True)
class StackVmHostContext:
    agent_name: str
    llm_router: Any
    tool_runtime: Any
    llm_profile: str | None
    system_prompt: str
    tool_definitions: list[dict[str, Any]]


def _coerce_vm_interaction_value(response: Any) -> str:
    if isinstance(response, dict):
        value = response.get("value")
        if value is None:
            value = response.get("raw_input")
        return "" if value is None else str(value)
    return "" if response is None else str(response)


def _extract_vm_interaction_value(response: Any) -> Any:
    if isinstance(response, dict):
        kind = str(response.get("kind") or "").strip().lower()
        if kind == "checklist":
            values = response.get("values")
            if values is not None:
                return list(values) if isinstance(values, (list, tuple, set)) else values
        if "value" in response:
            return response.get("value")
        if "values" in response:
            values = response.get("values")
            return list(values) if isinstance(values, (list, tuple, set)) else values
        return response.get("raw_input")
    return response


def _emit_runtime_event(shared_store: dict[str, Any], event_type: str, **payload: Any) -> None:
    handler = shared_store.get("runtime_event_handler")
    if callable(handler):
        handler(event_type, **payload)


def _accumulate_llm_usage(
    *,
    shared_store: dict[str, Any],
    agent_name: str,
    profile_name: str | None,
    generation_info: dict[str, Any] | None,
) -> None:
    info = generation_info if isinstance(generation_info, dict) else {}
    usage = info.get("usage", {}) if isinstance(info.get("usage", {}), dict) else {}
    shared_store["last_llm_generation"] = info
    shared_store["last_llm_profile"] = profile_name

    totals = shared_store.setdefault(
        "llm_usage_totals",
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )
    if isinstance(totals, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if isinstance(prompt_tokens, (int, float)):
            totals["prompt_tokens"] = int(totals.get("prompt_tokens", 0)) + int(prompt_tokens)
        if isinstance(completion_tokens, (int, float)):
            totals["completion_tokens"] = int(totals.get("completion_tokens", 0)) + int(completion_tokens)
        if isinstance(total_tokens, (int, float)):
            totals["total_tokens"] = int(totals.get("total_tokens", 0)) + int(total_tokens)

    estimated_cost = info.get("estimated_cost_usd", 0.0)
    if isinstance(estimated_cost, (int, float)):
        shared_store["llm_cost_usd_total"] = float(shared_store.get("llm_cost_usd_total", 0.0)) + float(estimated_cost)
    else:
        estimated_cost = 0.0

    shared_store.setdefault("llm_calls", []).append(
        {
            "agent": agent_name,
            "profile": info.get("profile_name") if info else profile_name,
            "model": info.get("model") if info else None,
            "usage": usage,
            "estimated_cost_usd": float(estimated_cost),
        }
    )


class StackVmHostAdapter:
    def __init__(self, *, shared_store: dict[str, Any], host_context: StackVmHostContext, result: Any) -> None:
        self.shared_store = shared_store
        self.host_context = host_context
        self.result = result

    def emit_effect(self, effect: RuntimeEffect | dict[str, Any] | None) -> dict[str, Any] | None:
        raise NotImplementedError

    async def prompt_text(self, question: str) -> str:
        raise NotImplementedError

    async def prompt_interaction(self, request: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def llm_call(self, prompt: str) -> str:
        raise NotImplementedError

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError


class PocketCoderStackVmHostAdapter(StackVmHostAdapter):
    def emit_effect(self, effect: RuntimeEffect | dict[str, Any] | None) -> dict[str, Any] | None:
        serialized = serialize_runtime_effect(effect)
        self.result.effect = serialized
        self.shared_store["last_vm_effect"] = dict(serialized) if isinstance(serialized, dict) else None
        self.shared_store["last_vm_transition"] = transition_from_runtime_effect(serialized)
        self.shared_store["last_runtime_effect"] = dict(serialized) if isinstance(serialized, dict) else None

        runtime_history = self.shared_store.setdefault("runtime_effect_history", [])
        runtime_entry = {
            "agent": self.host_context.agent_name,
            "source": "vm",
            "transition": transition_from_runtime_effect(serialized),
            "effect": dict(serialized) if isinstance(serialized, dict) else None,
        }
        if isinstance(runtime_history, list):
            runtime_history.append(dict(runtime_entry))

        history = self.shared_store.setdefault("vm_effect_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "agent": self.host_context.agent_name,
                    "transition": runtime_entry["transition"],
                    "effect": dict(runtime_entry["effect"]) if isinstance(runtime_entry["effect"], dict) else None,
                }
            )

        if not isinstance(serialized, dict):
            return serialized

        kind = str(serialized.get("kind") or "").strip()
        payload = serialized.get("payload", {}) if isinstance(serialized.get("payload"), dict) else {}
        if kind == "final_answer":
            self.shared_store["final_answer"] = str(payload.get("answer") or "")
        elif kind == "ask_user":
            self.shared_store["question_to_ask"] = str(payload.get("question") or "")
        elif kind == "handoff":
            self.shared_store["pending_handoff_agent"] = str(payload.get("target_agent") or "")
        elif kind == "call_tool":
            self.shared_store["pending_tool"] = {
                "name": str(payload.get("tool_name") or ""),
                "arguments": dict(payload.get("arguments") or {}),
                "requested_by": str(payload.get("requested_by") or self.host_context.agent_name),
            }
        return serialized

    async def prompt_text(self, question: str) -> str:
        interaction_handler = self.shared_store.get("interaction_handler")
        if not callable(interaction_handler):
            raise RuntimeError("prompt-user requires an interaction_handler in the shared store.")

        response = interaction_handler(
            {
                "kind": "text",
                "prompt": question,
                "allow_empty": True,
            }
        )
        if inspect.isawaitable(response):
            response = await response
        payload = dict(response) if isinstance(response, dict) else {"value": response, "raw_input": response}

        self.shared_store["last_user_prompt"] = question
        self.shared_store["last_user_interaction"] = payload
        self.shared_store["last_user_value"] = _extract_vm_interaction_value(payload)
        self.shared_store["last_user_input"] = _coerce_vm_interaction_value(payload)
        return str(self.shared_store["last_user_input"])

    async def prompt_interaction(self, request: dict[str, Any]) -> Any:
        interaction_handler = self.shared_store.get("interaction_handler")
        if not callable(interaction_handler):
            raise RuntimeError("prompt-interaction requires an interaction_handler in the shared store.")

        response = interaction_handler(request)
        if inspect.isawaitable(response):
            response = await response
        payload = dict(response) if isinstance(response, dict) else {"value": response, "raw_input": response}

        extracted_value = _extract_vm_interaction_value(payload)
        self.shared_store["last_user_prompt"] = str(request.get("prompt") or "")
        self.shared_store["last_user_request"] = dict(request)
        self.shared_store["last_user_interaction"] = payload
        self.shared_store["last_user_value"] = extracted_value
        return extracted_value

    async def llm_call(self, prompt: str) -> str:
        full_prompt = self.host_context.system_prompt.strip()
        if full_prompt:
            full_prompt = f"{full_prompt}\n\n{prompt}" if prompt else full_prompt
        else:
            full_prompt = prompt

        profile_name = self.host_context.llm_profile or getattr(self.host_context.llm_router, "default_profile_name", None)
        _emit_runtime_event(
            self.shared_store,
            "llm_call_started",
            agent=self.host_context.agent_name,
            profile=profile_name,
            prompt_text=full_prompt,
        )
        response = self.host_context.llm_router.generate(profile_name=profile_name, prompt=full_prompt)
        generation_info = None
        if hasattr(self.host_context.llm_router, "get_last_generation_info"):
            info = self.host_context.llm_router.get_last_generation_info()
            if isinstance(info, dict):
                generation_info = info
        _accumulate_llm_usage(
            shared_store=self.shared_store,
            agent_name=self.host_context.agent_name,
            profile_name=profile_name,
            generation_info=generation_info,
        )
        usage = generation_info.get("usage", {}) if isinstance(generation_info, dict) else {}
        estimated_cost = generation_info.get("estimated_cost_usd", 0.0) if isinstance(generation_info, dict) else 0.0
        _emit_runtime_event(
            self.shared_store,
            "llm_call_completed",
            agent=self.host_context.agent_name,
            profile=profile_name,
            model=generation_info.get("model") if isinstance(generation_info, dict) else None,
            usage=usage if isinstance(usage, dict) else {},
            estimated_cost_usd=estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
            prompt_text=full_prompt,
            response_text=response,
        )
        return str(response)

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        tool_runtime = self.host_context.tool_runtime
        if tool_runtime is None:
            raise RuntimeError("tool-call requires a tool runtime in the current StackVM host adapter.")
        _emit_runtime_event(
            self.shared_store,
            "tool_started",
            agent=self.host_context.agent_name,
            tool=str(tool_name),
            arguments=dict(arguments),
        )
        result = tool_runtime.execute_tool(
            tool_name=str(tool_name),
            arguments=dict(arguments),
            shared_store=self.shared_store,
            auto_confirm=bool(self.shared_store.get("auto_confirm_tools", False)),
            agent_name=self.host_context.agent_name,
        )
        route_payload = {
            "tool": str(tool_name),
            "arguments": dict(arguments),
            "result": result,
        }
        self.shared_store["last_tool_result"] = result
        self.shared_store["last_tool_route"] = route_payload
        self.shared_store["last_tool_failed"] = bool(isinstance(result, dict) and result.get("success") is False)
        self.shared_store.setdefault("tool_history", []).append(route_payload)
        _emit_runtime_event(
            self.shared_store,
            "tool_finished",
            agent=self.host_context.agent_name,
            tool=str(tool_name),
            success=not (isinstance(result, dict) and result.get("success") is False),
            result=result,
        )
        return result


def coerce_prompt_interaction_request(raw_request: Any) -> dict[str, Any]:
    request = raw_request
    if isinstance(request, str):
        parsed = yaml.safe_load(request) if request.strip() else {}
        request = parsed if isinstance(parsed, dict) else {}
    if not isinstance(request, dict):
        raise RuntimeError("prompt-interaction expects a mapping or YAML mapping string.")
    return request


def coerce_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    arguments = raw_arguments
    if isinstance(arguments, str):
        parsed = yaml.safe_load(arguments) if arguments.strip() else {}
        arguments = parsed if isinstance(parsed, dict) else {}
    if not isinstance(arguments, dict):
        arguments = {}
    return arguments


class StandaloneStackVmHostAdapter(StackVmHostAdapter):
    """Minimal host adapter for standalone StackVM script execution.

    This adapter supports local VM execution and final answers without relying on
    the broader PocketCoder agent runtime contract. Runtime effects that require
    orchestration beyond the standalone VM process remain unsupported here.
    """

    _UNSUPPORTED_KINDS = {
        "handoff": "Standalone StackVM scripts cannot hand off to another agent.",
        "call_tool": "Standalone StackVM scripts cannot issue transition-based tool-request through the standalone adapter. Use tool-call for direct portable tool execution.",
    }

    def emit_effect(self, effect: RuntimeEffect | dict[str, Any] | None) -> dict[str, Any] | None:
        serialized = serialize_runtime_effect(effect)
        self.result.effect = serialized
        self.shared_store["last_vm_effect"] = dict(serialized) if isinstance(serialized, dict) else None
        self.shared_store["last_vm_transition"] = transition_from_runtime_effect(serialized)
        self.shared_store["last_runtime_effect"] = dict(serialized) if isinstance(serialized, dict) else None

        history = self.shared_store.setdefault("vm_effect_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "agent": self.host_context.agent_name,
                    "transition": transition_from_runtime_effect(serialized),
                    "effect": dict(serialized) if isinstance(serialized, dict) else None,
                }
            )
        runtime_history = self.shared_store.setdefault("runtime_effect_history", [])
        if isinstance(runtime_history, list):
            runtime_history.append(
                {
                    "agent": self.host_context.agent_name,
                    "source": "standalone-vm",
                    "transition": transition_from_runtime_effect(serialized),
                    "effect": dict(serialized) if isinstance(serialized, dict) else None,
                }
            )

        if not isinstance(serialized, dict):
            return serialized

        kind = str(serialized.get("kind") or "").strip()
        payload = serialized.get("payload", {}) if isinstance(serialized.get("payload"), dict) else {}
        if kind in self._UNSUPPORTED_KINDS:
            raise RuntimeError(self._UNSUPPORTED_KINDS[kind])
        if kind == "final_answer":
            self.shared_store["final_answer"] = str(payload.get("answer") or "")
        elif kind == "ask_user":
            self.shared_store["question_to_ask"] = str(payload.get("question") or "")
        return serialized

    async def prompt_text(self, question: str) -> str:
        interaction_handler = self.shared_store.get("interaction_handler")
        if not callable(interaction_handler):
            raise RuntimeError("Standalone StackVM scripts require interaction_handler to use prompt-user.")
        response = interaction_handler(
            {
                "kind": "text",
                "prompt": question,
                "allow_empty": True,
            }
        )
        if inspect.isawaitable(response):
            response = await response
        payload = dict(response) if isinstance(response, dict) else {"value": response, "raw_input": response}
        self.shared_store["last_user_prompt"] = question
        self.shared_store["last_user_interaction"] = payload
        self.shared_store["last_user_value"] = _extract_vm_interaction_value(payload)
        self.shared_store["last_user_input"] = _coerce_vm_interaction_value(payload)
        return str(self.shared_store["last_user_input"])

    async def prompt_interaction(self, request: dict[str, Any]) -> Any:
        interaction_handler = self.shared_store.get("interaction_handler")
        if not callable(interaction_handler):
            raise RuntimeError("Standalone StackVM scripts require interaction_handler to use prompt-interaction.")
        response = interaction_handler(request)
        if inspect.isawaitable(response):
            response = await response
        payload = dict(response) if isinstance(response, dict) else {"value": response, "raw_input": response}
        extracted_value = _extract_vm_interaction_value(payload)
        self.shared_store["last_user_prompt"] = str(request.get("prompt") or "")
        self.shared_store["last_user_request"] = dict(request)
        self.shared_store["last_user_interaction"] = payload
        self.shared_store["last_user_value"] = extracted_value
        return extracted_value

    async def llm_call(self, prompt: str) -> str:
        llm_router = self.host_context.llm_router
        if llm_router is None:
            raise RuntimeError("Standalone StackVM scripts require an llm router to use llm-call.")
        full_prompt = self.host_context.system_prompt.strip()
        if full_prompt:
            full_prompt = f"{full_prompt}\n\n{prompt}" if prompt else full_prompt
        else:
            full_prompt = prompt
        profile_name = self.host_context.llm_profile or getattr(llm_router, "default_profile_name", None)
        _emit_runtime_event(
            self.shared_store,
            "llm_call_started",
            agent=self.host_context.agent_name,
            profile=profile_name,
            prompt_text=full_prompt,
        )
        response = llm_router.generate(profile_name=profile_name, prompt=full_prompt)
        generation_info = None
        if hasattr(llm_router, "get_last_generation_info"):
            info = llm_router.get_last_generation_info()
            if isinstance(info, dict):
                generation_info = info
        _accumulate_llm_usage(
            shared_store=self.shared_store,
            agent_name=self.host_context.agent_name,
            profile_name=profile_name,
            generation_info=generation_info,
        )
        usage = generation_info.get("usage", {}) if isinstance(generation_info, dict) else {}
        estimated_cost = generation_info.get("estimated_cost_usd", 0.0) if isinstance(generation_info, dict) else 0.0
        _emit_runtime_event(
            self.shared_store,
            "llm_call_completed",
            agent=self.host_context.agent_name,
            profile=profile_name,
            model=generation_info.get("model") if isinstance(generation_info, dict) else None,
            usage=usage if isinstance(usage, dict) else {},
            estimated_cost_usd=estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
            prompt_text=full_prompt,
            response_text=response,
        )
        return str(response)

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        tool_runtime = self.host_context.tool_runtime
        if tool_runtime is None:
            raise RuntimeError("Standalone StackVM scripts require a tool runtime to use tool-call.")
        _emit_runtime_event(
            self.shared_store,
            "tool_started",
            agent=self.host_context.agent_name,
            tool=str(tool_name),
            arguments=dict(arguments),
        )
        result = tool_runtime.execute_tool(
            tool_name=str(tool_name),
            arguments=dict(arguments),
            shared_store=self.shared_store,
            auto_confirm=bool(self.shared_store.get("auto_confirm_tools", False)),
            agent_name=self.host_context.agent_name,
        )
        route_payload = {
            "tool": str(tool_name),
            "arguments": dict(arguments),
            "result": result,
        }
        self.shared_store["last_tool_result"] = result
        self.shared_store["last_tool_route"] = route_payload
        self.shared_store["last_tool_failed"] = bool(isinstance(result, dict) and result.get("success") is False)
        self.shared_store.setdefault("tool_history", []).append(route_payload)
        _emit_runtime_event(
            self.shared_store,
            "tool_finished",
            agent=self.host_context.agent_name,
            tool=str(tool_name),
            success=not (isinstance(result, dict) and result.get("success") is False),
            result=result,
        )
        return result
