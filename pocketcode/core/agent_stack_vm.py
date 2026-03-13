from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from pocketcode.core.stackvm_expander import expand_stackvm_source
from pocketcode.core.stackvm_validator import validate_stackvm_ast


@dataclass
class StackVmExecutionResult:
    transition: str | None = None
    source_files: list[str] = field(default_factory=list)


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


def _snapshot_vm_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _snapshot_vm_value(item, depth=depth + 1)
            for key, item in list(value.items())[:16]
        }
    if isinstance(value, (list, tuple)):
        return [_snapshot_vm_value(item, depth=depth + 1) for item in list(value)[:16]]
    return repr(value)


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


def _clone_for_child(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clone_for_child(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_for_child(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_for_child(item) for item in value)
    if isinstance(value, set):
        return {_clone_for_child(item) for item in value}
    return value


class AgentStackVM:
    def __init__(self, shared_store: dict[str, Any] | None = None):
        self.stack: list[Any] = []
        self.store = shared_store if shared_store is not None else {}
        self.words: dict[str, Callable[..., Any]] = {}
        self._user_word_defs: dict[str, list[Any]] = {}
        self._host_context: StackVmHostContext | None = None
        self._register_builtins()

    def register_word(self, name: str, func: Callable[..., Any]) -> None:
        self.words[str(name)] = func

    async def eval(self, code_string: str) -> None:
        expanded = expand_stackvm_source(code_string)
        validate_stackvm_ast(expanded.ast)
        await self.execute_ast(expanded.ast)

    async def execute_word(self, word_name: str) -> None:
        if word_name not in self.words:
            raise ValueError(f"Unknown word: '{word_name}'")
        await self._call_word(self.words[word_name])
        self._record_trace("word", word=word_name)

    async def execute_ast(self, ast: list[Any]) -> None:
        for item in ast:
            if isinstance(item, list):
                self.stack.append(item)
                self._record_trace("push-quotation", value=item)
                continue
            token_type, token_value = item
            if token_type in {"str", "int", "float", "bool", "none"}:
                self.stack.append(token_value)
                self._record_trace("push-literal", token_type=token_type, value=token_value)
                continue
            if token_type == "sym":
                if token_value not in self.words:
                    raise ValueError(f"Unknown word: '{token_value}'")
                await self._call_word(self.words[token_value])
                self._record_trace("word", word=token_value)

    def _record_trace(self, op: str, **payload: Any) -> None:
        if not self.store.get("stackvm_trace_enabled"):
            return
        trace = self.store.setdefault("vm_trace", [])
        if not isinstance(trace, list):
            return
        trace.append(
            {
                "op": str(op),
                **{key: _snapshot_vm_value(value) for key, value in payload.items()},
                "stack": _snapshot_vm_value(list(self.stack)),
            }
        )

    def register_host_words(self, *, host_context: StackVmHostContext, result: StackVmExecutionResult) -> None:
        self._host_context = host_context

        def _set_transition(name: str) -> None:
            result.transition = name

        def answer() -> None:
            answer_text = self.stack.pop() if self.stack else ""
            self.store["final_answer"] = str(answer_text)
            _set_transition("final_answer")

        def ask_user() -> None:
            question = self.stack.pop() if self.stack else ""
            self.store["question_to_ask"] = str(question)
            _set_transition("ask_user")

        async def prompt_user() -> None:
            question = str(self.stack.pop() if self.stack else "")
            interaction_handler = self.store.get("interaction_handler")
            legacy_user_input_handler = self.store.get("user_input_handler")

            if callable(interaction_handler):
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
            elif callable(legacy_user_input_handler):
                response = legacy_user_input_handler(question)
                if inspect.isawaitable(response):
                    response = await response
                payload = {"kind": "text", "value": response, "raw_input": response}
            else:
                raise RuntimeError("prompt-user requires an interaction_handler or user_input_handler in the shared store.")

            self.store["last_user_prompt"] = question
            self.store["last_user_interaction"] = payload
            self.store["last_user_value"] = _extract_vm_interaction_value(payload)
            self.store["last_user_input"] = _coerce_vm_interaction_value(payload)
            self.stack.append(self.store["last_user_input"])

        async def prompt_interaction() -> None:
            request = self.stack.pop() if self.stack else {}
            if isinstance(request, str):
                parsed = yaml.safe_load(request) if request.strip() else {}
                request = parsed if isinstance(parsed, dict) else {}
            if not isinstance(request, dict):
                raise RuntimeError("prompt-interaction expects a mapping or YAML mapping string.")

            interaction_handler = self.store.get("interaction_handler")
            legacy_user_input_handler = self.store.get("user_input_handler")

            if callable(interaction_handler):
                response = interaction_handler(request)
                if inspect.isawaitable(response):
                    response = await response
                payload = dict(response) if isinstance(response, dict) else {"value": response, "raw_input": response}
            elif callable(legacy_user_input_handler):
                kind = str(request.get("kind") or "text").strip().lower()
                if kind != "text":
                    raise RuntimeError("Legacy user_input_handler only supports text interactions.")
                prompt = str(request.get("prompt") or "")
                response = legacy_user_input_handler(prompt)
                if inspect.isawaitable(response):
                    response = await response
                payload = {"kind": "text", "value": response, "raw_input": response}
            else:
                raise RuntimeError("prompt-interaction requires an interaction_handler or user_input_handler in the shared store.")

            extracted_value = _extract_vm_interaction_value(payload)
            self.store["last_user_prompt"] = str(request.get("prompt") or "")
            self.store["last_user_request"] = dict(request)
            self.store["last_user_interaction"] = payload
            self.store["last_user_value"] = extracted_value
            self.stack.append(extracted_value)

        def handoff() -> None:
            target = self.stack.pop() if self.stack else ""
            self.store["pending_handoff_agent"] = str(target)
            _set_transition("handoff")

        def tool_request() -> None:
            arguments = self.stack.pop() if self.stack else {}
            tool_name = self.stack.pop() if self.stack else ""
            if isinstance(arguments, str):
                parsed = yaml.safe_load(arguments) if arguments.strip() else {}
                arguments = parsed if isinstance(parsed, dict) else {}
            if not isinstance(arguments, dict):
                arguments = {}
            self.store["pending_tool"] = {
                "name": str(tool_name),
                "arguments": arguments,
                "requested_by": host_context.agent_name,
            }
            _set_transition("call_tool")

        async def llm_call() -> None:
            prompt = str(self.stack.pop() if self.stack else "")
            full_prompt = host_context.system_prompt.strip()
            if full_prompt:
                full_prompt = f"{full_prompt}\n\n{prompt}" if prompt else full_prompt
            else:
                full_prompt = prompt
            profile_name = host_context.llm_profile or getattr(host_context.llm_router, "default_profile_name", None)
            _emit_runtime_event(
                self.store,
                "llm_call_started",
                agent=host_context.agent_name,
                profile=profile_name,
                prompt_text=full_prompt,
            )
            response = host_context.llm_router.generate(profile_name=profile_name, prompt=full_prompt)
            generation_info = None
            if hasattr(host_context.llm_router, "get_last_generation_info"):
                info = host_context.llm_router.get_last_generation_info()
                if isinstance(info, dict):
                    generation_info = info
            _accumulate_llm_usage(
                shared_store=self.store,
                agent_name=host_context.agent_name,
                profile_name=profile_name,
                generation_info=generation_info,
            )
            usage = generation_info.get("usage", {}) if isinstance(generation_info, dict) else {}
            estimated_cost = generation_info.get("estimated_cost_usd", 0.0) if isinstance(generation_info, dict) else 0.0
            _emit_runtime_event(
                self.store,
                "llm_call_completed",
                agent=host_context.agent_name,
                profile=profile_name,
                model=generation_info.get("model") if isinstance(generation_info, dict) else None,
                usage=usage if isinstance(usage, dict) else {},
                estimated_cost_usd=estimated_cost if isinstance(estimated_cost, (int, float)) else 0.0,
                prompt_text=full_prompt,
                response_text=response,
            )
            self.stack.append(response)

        self.register_word("answer", answer)
        self.register_word("ask-user", ask_user)
        self.register_word("prompt-user", prompt_user)
        self.register_word("prompt-interaction", prompt_interaction)
        self.register_word("handoff", handoff)
        self.register_word("tool-request", tool_request)
        self.register_word("transition", lambda: _set_transition(str(self.stack.pop() if self.stack else "continue")))
        self.register_word("llm-call", llm_call)
        self.register_word("system-prompt", lambda: self.stack.append(host_context.system_prompt))
        self.register_word("llm-profile", lambda: self.stack.append(host_context.llm_profile))
        self.register_word("tool-definitions", lambda: self.stack.append(list(host_context.tool_definitions)))
        self.register_word("request", lambda: self.stack.append(self.store.get("initial_request", "")))
        self.register_word("last-tool-result", lambda: self.stack.append(self.store.get("last_tool_result")))
        self.register_word("last-tool-route", lambda: self.stack.append(self.store.get("last_tool_route")))
        self.register_word("results", lambda: self.stack.append(self.store.get("results", {})))
        self.register_word("active-session-transcript", self._active_session_transcript)
        self.register_word("active-session-transcript-text", self._active_session_transcript_text)

    async def _call_word(self, func: Callable[..., Any]) -> None:
        if inspect.iscoroutinefunction(func):
            await func()
            return
        result = func()
        if inspect.isawaitable(result):
            await result

    def _register_builtins(self) -> None:
        self.register_word("dup", lambda: self.stack.append(self.stack[-1]))
        self.register_word("drop", lambda: self.stack.pop())
        self.register_word("swap", self._swap)
        self.register_word("over", lambda: self.stack.append(self.stack[-2]))
        self.register_word("stack-depth", lambda: self.stack.append(len(self.stack)))
        self.register_word("stack-empty?", lambda: self.stack.append(len(self.stack) == 0))
        self.register_word("can-pop?", lambda: self.stack.append(len(self.stack) >= 1))
        self.register_word("can-dup?", lambda: self.stack.append(len(self.stack) >= 1))
        self.register_word("can-swap?", lambda: self.stack.append(len(self.stack) >= 2))
        self.register_word("can-over?", lambda: self.stack.append(len(self.stack) >= 2))
        self.register_word("print", lambda: print(f"[VM] {self.stack.pop()}"))
        self.register_word("concat", self._concat)
        self.register_word("join", self._join)
        self.register_word("+", self._add)
        self.register_word("-", self._subtract)
        self.register_word("*", self._multiply)
        self.register_word("/", self._divide)
        self.register_word("len", self._len)
        self.register_word("empty?", self._empty)
        self.register_word("contains?", self._contains)
        self.register_word("success?", self._success)
        self.register_word("failure?", self._failure)
        self.register_word("int>", self._to_int)
        self.register_word("float>", self._to_float)
        self.register_word("bool>", self._to_bool)
        self.register_word("str>", self._to_str)
        self.register_word("not", lambda: self.stack.append(not self.stack.pop()))
        self.register_word("none?", lambda: self.stack.append(self.stack.pop() is None))
        self.register_word("=", lambda: self.stack.append(self.stack.pop() == self.stack.pop()))
        self.register_word(">", self._greater_than)
        self.register_word("<", self._less_than)
        self.register_word(">=", self._greater_equal)
        self.register_word("<=", self._less_equal)
        self.register_word("yaml>", lambda: self.stack.append(yaml.safe_load(str(self.stack.pop() if self.stack else ""))))
        self.register_word("dict-get", self._dict_get)
        self.register_word("dict-get?", self._dict_get_safe)
        self.register_word("get-in", self._get_in)
        self.register_word("get-in?", self._get_in_safe)
        self.register_word("dict-set", self._dict_set)
        self.register_word("set-in", self._set_in)
        self.register_word("set-in?", self._set_in_safe)
        self.register_word("list-get", self._list_get)
        self.register_word("list-get?", self._list_get_safe)
        self.register_word("list-set", self._list_set)
        self.register_word("keys", self._keys)
        self.register_word("values", self._values)
        self.register_word("list-append", self._list_append)
        self.register_word("store-set", self._store_set)
        self.register_word("store-get", self._store_get)
        self.register_word("shared!", self._store_path_set)
        self.register_word("shared!?", self._store_path_set_safe)
        self.register_word("shared@", self._store_path_get)
        self.register_word("call", self._builtin_call)
        self.register_word("if", self._builtin_if)
        self.register_word("while", self._builtin_while)
        self.register_word("switch", self._builtin_switch)
        self.register_word("cond", self._builtin_cond)
        self.register_word("fallback", self._builtin_fallback)
        self.register_word("parallel-map", self._builtin_parallel_map)
        self.register_word("reduce", self._builtin_reduce)
        self.register_word("define", self._builtin_define)

    def _swap(self) -> None:
        first = self.stack.pop()
        second = self.stack.pop()
        self.stack.extend([first, second])

    def _concat(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(str(left) + str(right))

    def _join(self) -> None:
        separator = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"join expects a list or tuple, got {type(values)!r}")
        self.stack.append(str(separator).join(str(value) for value in values))

    def _add(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left + right)

    def _subtract(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left - right)

    def _multiply(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left * right)

    def _divide(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left / right)

    def _len(self) -> None:
        value = self.stack.pop()
        try:
            self.stack.append(len(value))
        except TypeError as exc:
            raise TypeError(f"len expects a sized value, got {type(value)!r}") from exc

    def _empty(self) -> None:
        value = self.stack.pop()
        try:
            self.stack.append(len(value) == 0)
        except TypeError as exc:
            raise TypeError(f"empty? expects a sized value, got {type(value)!r}") from exc

    def _contains(self) -> None:
        needle = self.stack.pop()
        haystack = self.stack.pop()
        self.stack.append(needle in haystack)

    def _success(self) -> None:
        value = self.stack.pop()
        if isinstance(value, dict):
            self.stack.append(value.get("success") is not False)
            return
        self.stack.append(bool(value))

    def _failure(self) -> None:
        value = self.stack.pop()
        if isinstance(value, dict):
            self.stack.append(value.get("success") is False)
            return
        self.stack.append(not bool(value))

    def _to_int(self) -> None:
        value = self.stack.pop()
        if isinstance(value, str):
            value = value.strip()
        self.stack.append(int(value))

    def _to_float(self) -> None:
        value = self.stack.pop()
        if isinstance(value, str):
            value = value.strip()
        self.stack.append(float(value))

    def _to_bool(self) -> None:
        value = self.stack.pop()
        if isinstance(value, bool):
            self.stack.append(value)
            return
        if value is None:
            self.stack.append(False)
            return
        if isinstance(value, (int, float)):
            self.stack.append(bool(value))
            return
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                self.stack.append(True)
                return
            if normalized in {"false", "0", "no", "off", ""}:
                self.stack.append(False)
                return
            raise ValueError(f"bool> cannot coerce string value {value!r}")
        self.stack.append(bool(value))

    def _to_str(self) -> None:
        self.stack.append(str(self.stack.pop()))

    def _greater_than(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left > right)

    def _less_than(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left < right)

    def _greater_equal(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left >= right)

    def _less_equal(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        self.stack.append(left <= right)

    def _dict_get(self) -> None:
        key = self.stack.pop()
        mapping = self.stack.pop()
        if not isinstance(mapping, dict):
            raise TypeError(f"dict-get expects a dict, got {type(mapping)!r}")
        self.stack.append(mapping.get(key))

    def _dict_get_safe(self) -> None:
        key = self.stack.pop()
        mapping = self.stack.pop()
        if not isinstance(mapping, dict):
            self.stack.append(None)
            return
        self.stack.append(mapping.get(key))

    def _get_in(self) -> None:
        path = self.stack.pop()
        current = self.stack.pop()
        self.stack.append(_lookup_segments(current, _normalize_path_segments(path)))

    def _get_in_safe(self) -> None:
        path = self.stack.pop()
        current = self.stack.pop()
        try:
            segments = _normalize_path_segments(path)
        except TypeError:
            self.stack.append(None)
            return
        self.stack.append(_lookup_segments(current, segments))

    def _dict_set(self) -> None:
        value = self.stack.pop()
        key = self.stack.pop()
        mapping = self.stack.pop()
        if not isinstance(mapping, dict):
            raise TypeError(f"dict-set expects a dict, got {type(mapping)!r}")
        mapping[key] = value
        self.stack.append(mapping)

    def _set_in(self) -> None:
        path = self.stack.pop()
        value = self.stack.pop()
        container = self.stack.pop()
        _assign_segments(container, _normalize_path_segments(path), value)
        self.stack.append(container)

    def _set_in_safe(self) -> None:
        path = self.stack.pop()
        value = self.stack.pop()
        container = self.stack.pop()
        try:
            segments = _normalize_path_segments(path)
            _assign_segments(container, segments, value)
        except (TypeError, ValueError, IndexError):
            self.stack.append(None)
            return
        self.stack.append(container)

    def _list_get(self) -> None:
        index = self.stack.pop()
        container = self.stack.pop()
        if not isinstance(container, list):
            raise TypeError(f"list-get expects a list, got {type(container)!r}")
        if not isinstance(index, int):
            raise TypeError(f"list-get expects an integer index, got {type(index)!r}")
        self.stack.append(container[index])

    def _list_get_safe(self) -> None:
        index = self.stack.pop()
        container = self.stack.pop()
        if not isinstance(container, list) or not isinstance(index, int):
            self.stack.append(None)
            return
        if index < 0 or index >= len(container):
            self.stack.append(None)
            return
        self.stack.append(container[index])

    def _list_set(self) -> None:
        value = self.stack.pop()
        index = self.stack.pop()
        container = self.stack.pop()
        if not isinstance(container, list):
            raise TypeError(f"list-set expects a list, got {type(container)!r}")
        if not isinstance(index, int):
            raise TypeError(f"list-set expects an integer index, got {type(index)!r}")
        container[index] = value
        self.stack.append(container)

    def _keys(self) -> None:
        mapping = self.stack.pop()
        if not isinstance(mapping, dict):
            raise TypeError(f"keys expects a dict, got {type(mapping)!r}")
        self.stack.append(list(mapping.keys()))

    def _values(self) -> None:
        mapping = self.stack.pop()
        if not isinstance(mapping, dict):
            raise TypeError(f"values expects a dict, got {type(mapping)!r}")
        self.stack.append(list(mapping.values()))

    def _list_append(self) -> None:
        value = self.stack.pop()
        container = self.stack.pop()
        if not isinstance(container, list):
            raise TypeError(f"list-append expects a list, got {type(container)!r}")
        container.append(value)
        self.stack.append(container)

    def _store_set(self) -> None:
        key = str(self.stack.pop())
        value = self.stack.pop()
        self.store[key] = value

    def _store_get(self) -> None:
        key = str(self.stack.pop())
        self.stack.append(self.store.get(key, ""))

    def _store_path_get(self) -> None:
        path = str(self.stack.pop())
        self.stack.append(_lookup_path(self.store, path))

    def _store_path_set(self) -> None:
        path = str(self.stack.pop())
        value = self.stack.pop()
        _assign_path(self.store, path, value)

    def _store_path_set_safe(self) -> None:
        raw_path = self.stack.pop()
        value = self.stack.pop()
        try:
            _assign_segments(self.store, _normalize_path_segments(raw_path), value)
        except (TypeError, ValueError, IndexError):
            self.stack.append(None)
            return
        self.stack.append(self.store)

    def _load_active_session_transcript(self) -> list[dict[str, Any]]:
        session_manager = self.store.get("_session_manager")
        session_id = str(self.store.get("active_session_id") or "").strip()
        if session_manager is None or not session_id:
            return []
        try:
            record = session_manager.load_session(session_id)
        except Exception:
            return []

        entries: list[dict[str, Any]] = []
        for item in list(getattr(record, "transcript", []) or []):
            if hasattr(item, "as_dict"):
                entries.append(dict(item.as_dict()))
            elif isinstance(item, dict):
                entries.append(dict(item))
        return entries

    def _active_session_transcript(self) -> None:
        self.stack.append(self._load_active_session_transcript())

    def _active_session_transcript_text(self) -> None:
        keep_last = int(self.stack.pop()) if self.stack else 0
        entries = self._load_active_session_transcript()
        if keep_last > 0:
            entries = entries[-keep_last:]

        lines: list[str] = []
        for entry in entries:
            role = str(entry.get("role") or "system").strip().lower()
            content = " ".join(str(entry.get("content") or "").split())
            if not content:
                continue
            if role == "user":
                label = "User"
            elif role == "assistant":
                label = "Assistant"
            else:
                label = "System"
            lines.append(f"{label}: {content}")
        self.stack.append("\n".join(lines))

    async def _builtin_call(self) -> None:
        quotation_ast = self.stack.pop()
        await self.execute_ast(quotation_ast)

    async def _builtin_if(self) -> None:
        false_ast = self.stack.pop()
        true_ast = self.stack.pop()
        condition = self.stack.pop()
        await self.execute_ast(true_ast if condition else false_ast)

    async def _builtin_while(self) -> None:
        body_ast = self.stack.pop()
        condition_ast = self.stack.pop()
        while True:
            await self.execute_ast(condition_ast)
            if not self.stack.pop():
                break
            await self.execute_ast(body_ast)

    async def _builtin_switch(self) -> None:
        cases_ast = self.stack.pop()
        target_value = self.stack.pop()
        pairs = self._normalize_case_pairs(cases_ast, word_name="switch")

        default_action: list[Any] | None = None
        for case_node, action_ast in pairs:
            case_value = self._extract_case_literal(case_node, word_name="switch")
            if case_value == "default":
                if default_action is None:
                    default_action = action_ast
                continue
            if case_value == target_value:
                await self.execute_ast(action_ast)
                return

        if default_action is not None:
            await self.execute_ast(default_action)

    async def _builtin_cond(self) -> None:
        cases_ast = self.stack.pop()
        pairs = self._normalize_case_pairs(cases_ast, word_name="cond")

        for condition_ast, action_ast in pairs:
            if not isinstance(condition_ast, list):
                raise TypeError("cond expects each condition to be a quotation.")
            await self.execute_ast(condition_ast)
            if not self.stack:
                raise RuntimeError("cond condition did not leave a value on the stack.")
            if self.stack.pop():
                await self.execute_ast(action_ast)
                return

    async def _builtin_fallback(self) -> None:
        fallback_ast = self.stack.pop()
        primary_ast = self.stack.pop()
        if not isinstance(primary_ast, list) or not isinstance(fallback_ast, list):
            raise TypeError("fallback expects primary and fallback quotations.")

        stack_snapshot = list(self.stack)
        try:
            await self.execute_ast(primary_ast)
        except Exception:
            self.stack[:] = stack_snapshot
            await self.execute_ast(fallback_ast)

    async def _builtin_parallel_map(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("parallel-map expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"parallel-map expects a list or tuple, got {type(values)!r}")

        async def _run_item(item: Any) -> Any:
            child_vm = self._make_child_vm()
            child_vm.stack.append(item)
            await child_vm.execute_ast(quotation_ast)
            child_vm._raise_if_child_requested_transition(combinator_name="parallel-map")
            return child_vm.stack.pop() if child_vm.stack else None

        results = await asyncio.gather(*(_run_item(item) for item in values))
        self.stack.append(list(results))

    async def _builtin_reduce(self) -> None:
        quotation_ast = self.stack.pop()
        accumulator = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("reduce expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"reduce expects a list or tuple, got {type(values)!r}")

        for item in values:
            child_vm = self._make_child_vm()
            child_vm.stack.append(accumulator)
            child_vm.stack.append(item)
            await child_vm.execute_ast(quotation_ast)
            child_vm._raise_if_child_requested_transition(combinator_name="reduce")
            accumulator = child_vm.stack.pop() if child_vm.stack else None

        self.stack.append(accumulator)

    def _builtin_define(self) -> None:
        word_name = str(self.stack.pop())
        quotation_ast = self.stack.pop()

        if not isinstance(quotation_ast, list):
            raise TypeError("define expects a quotation before the word name.")

        self._define_user_word(word_name, quotation_ast)

    def _define_user_word(self, word_name: str, quotation_ast: list[Any]) -> None:
        self._user_word_defs[str(word_name)] = quotation_ast

        async def custom_user_word(ast: list[Any] = quotation_ast) -> None:
            await self.execute_ast(ast)

        self.register_word(str(word_name), custom_user_word)

    def _make_child_vm(self) -> AgentStackVM:
        child_vm = AgentStackVM(shared_store=_clone_for_child(self.store))
        if self._host_context is not None:
            child_vm.register_host_words(
                host_context=self._host_context,
                result=StackVmExecutionResult(),
            )
        for word_name, word_ast in self._user_word_defs.items():
            child_vm._define_user_word(word_name, word_ast)
        return child_vm

    def _normalize_case_pairs(self, cases_ast: Any, *, word_name: str) -> list[tuple[Any, list[Any]]]:
        if not isinstance(cases_ast, list):
            raise TypeError(f"{word_name} expects a quotation containing case/action pairs.")
        if len(cases_ast) % 2 != 0:
            raise ValueError(f"{word_name} expects an even number of case/action entries.")

        pairs: list[tuple[Any, list[Any]]] = []
        for index in range(0, len(cases_ast), 2):
            case_node = cases_ast[index]
            action_ast = cases_ast[index + 1]
            if not isinstance(action_ast, list):
                raise TypeError(f"{word_name} expects each action to be a quotation.")
            pairs.append((case_node, action_ast))
        return pairs

    def _extract_case_literal(self, case_node: Any, *, word_name: str) -> Any:
        if isinstance(case_node, list):
            raise TypeError(f"{word_name} case values must be literals, not quotations.")
        if not isinstance(case_node, tuple) or len(case_node) != 2:
            raise TypeError(f"{word_name} encountered an invalid case entry.")
        token_type, token_value = case_node
        if token_type == "sym":
            return str(token_value)
        return token_value

    def _raise_if_child_requested_transition(self, *, combinator_name: str) -> None:
        if self.store.get("pending_tool"):
            raise RuntimeError(f"{combinator_name} child quotations cannot schedule tool requests.")
        if self.store.get("pending_handoff_agent"):
            raise RuntimeError(f"{combinator_name} child quotations cannot perform handoffs.")
        if self.store.get("question_to_ask"):
            raise RuntimeError(f"{combinator_name} child quotations cannot ask the user.")
        if self.store.get("final_answer"):
            raise RuntimeError(f"{combinator_name} child quotations cannot finalize answers.")
def _lookup_path(mapping: dict[str, Any], path: str) -> Any:
    return _lookup_segments(mapping, _normalize_path_segments(path))


def _assign_path(mapping: dict[str, Any], path: str, value: Any) -> None:
    _assign_segments(mapping, _normalize_path_segments(path), value)


def _normalize_path_segments(path: str | list[Any]) -> list[str | int]:
    if isinstance(path, str):
        raw_segments: list[Any] = [part for part in path.split(".") if part]
    elif isinstance(path, list):
        raw_segments = path
    else:
        raise TypeError(f"Path must be a string or list, got {type(path)!r}")

    segments: list[str | int] = []
    for segment in raw_segments:
        if isinstance(segment, int):
            segments.append(segment)
            continue
        text = str(segment)
        if text.isdigit():
            segments.append(int(text))
            continue
        segments.append(text)
    return segments


def _lookup_segments(current: Any, segments: list[str | int]) -> Any:
    for segment in segments:
        if isinstance(current, dict) and isinstance(segment, str):
            current = current.get(segment)
            continue
        if isinstance(current, list) and isinstance(segment, int):
            if segment < 0 or segment >= len(current):
                return None
            current = current[segment]
            continue
        return None
    return current


def _assign_segments(container: Any, segments: list[str | int], value: Any) -> None:
    if not segments:
        raise ValueError("StackVM shared path cannot be empty.")

    current = container
    for index, segment in enumerate(segments[:-1]):
        next_segment = segments[index + 1]
        expected_next = [] if isinstance(next_segment, int) else {}

        if isinstance(current, dict) and isinstance(segment, str):
            next_value = current.get(segment)
            if not isinstance(next_value, (dict, list)):
                next_value = list(expected_next) if isinstance(expected_next, list) else dict(expected_next)
                current[segment] = next_value
            current = next_value
            continue

        if isinstance(current, list) and isinstance(segment, int):
            if segment < 0:
                raise IndexError("Negative StackVM list indices are not supported for mutation.")
            while len(current) <= segment:
                current.append([] if isinstance(next_segment, int) else {})
            next_value = current[segment]
            if not isinstance(next_value, (dict, list)):
                next_value = [] if isinstance(next_segment, int) else {}
                current[segment] = next_value
            current = next_value
            continue

        raise TypeError(f"Cannot traverse path segment {segment!r} on {type(current)!r}")

    final_segment = segments[-1]
    if isinstance(current, dict) and isinstance(final_segment, str):
        current[final_segment] = value
        return
    if isinstance(current, list) and isinstance(final_segment, int):
        if final_segment < 0:
            raise IndexError("Negative StackVM list indices are not supported for mutation.")
        while len(current) <= final_segment:
            current.append(None)
        current[final_segment] = value
        return
    raise TypeError(f"Cannot assign path segment {final_segment!r} on {type(current)!r}")
