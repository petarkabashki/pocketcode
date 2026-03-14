from __future__ import annotations

import asyncio
from contextlib import contextmanager
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from pocketcode.core.schema_tools import apply_schema_value, validate_schema_value
from pocketcode.core.stackvm_parser import StackVmAstSpan, parse_stackvm_source_with_spans, serialize_stackvm_ast
from pocketcode.core.stackvm_host import (
    PocketCoderStackVmHostAdapter,
    StackVmHostAdapter,
    StackVmHostContext,
    coerce_prompt_interaction_request,
    coerce_tool_arguments,
)
from pocketcode.core.runtime_effects import (
    ask_user_effect,
    call_tool_effect,
    final_answer_effect,
    handoff_effect,
    transition_effect,
    transition_from_runtime_effect,
)
from pocketcode.core.stackvm_expander import expand_stackvm_source
from pocketcode.core.stackvm_validator import validate_stackvm_ast


@dataclass
class StackVmExecutionResult:
    source_files: list[str] = field(default_factory=list)
    effect: dict[str, Any] | None = None

    @property
    def transition(self) -> str | None:
        return transition_from_runtime_effect(self.effect)


class StackVmIllegalChildEffectError(RuntimeError):
    pass


_MISSING = object()


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


def _stack_delta(before: list[Any], after: list[Any]) -> dict[str, Any]:
    common = 0
    while common < len(before) and common < len(after) and before[common] == after[common]:
        common += 1
    return {
        "depth_change": len(after) - len(before),
        "popped": before[common:],
        "pushed": after[common:],
    }


class AgentStackVM:
    def __init__(self, shared_store: dict[str, Any] | None = None):
        self.stack: list[Any] = []
        self.store = shared_store if shared_store is not None else {}
        self.words: dict[str, Callable[..., Any]] = {}
        self._user_word_defs: dict[str, tuple[list[Any], list[StackVmAstSpan] | None, list[StackVmAstSpan] | None]] = {}
        self._quotation_trace_spans: dict[int, list[StackVmAstSpan]] = {}
        self._quotation_authored_spans: dict[int, list[StackVmAstSpan]] = {}
        self._host_context: StackVmHostContext | None = None
        self._host_adapter: StackVmHostAdapter | None = None
        self._trace_scope_stack: list[str] = ["main"]
        self._register_builtins()

    def register_word(self, name: str, func: Callable[..., Any]) -> None:
        self.words[str(name)] = func

    async def eval(self, code_string: str) -> None:
        expanded = expand_stackvm_source(code_string)
        validate_stackvm_ast(expanded.ast)
        expanded_source = serialize_stackvm_ast(expanded.ast)
        _, trace_spans = parse_stackvm_source_with_spans(expanded_source)
        await self.execute_ast(expanded.ast, trace_spans=trace_spans, authored_spans=list(expanded.ast_spans))

    async def execute_word(self, word_name: str) -> None:
        if word_name not in self.words:
            raise ValueError(f"Unknown word: '{word_name}'")
            
        run_handle = self.store.get("run_handle")
        if run_handle is not None and hasattr(run_handle, "set_active_vm"):
            run_handle.set_active_vm(self)
            
        try:
            stack_before = list(self.stack)
            await self._call_word(self.words[word_name])
            self._record_trace("word", word=word_name, stack_before=stack_before)
        finally:
            if run_handle is not None and hasattr(run_handle, "set_active_vm"):
                if run_handle.get_active_vm() is self:
                    run_handle.set_active_vm(None)

    async def execute_ast(
        self,
        ast: list[Any],
        *,
        trace_spans: list[StackVmAstSpan] | None = None,
        authored_spans: list[StackVmAstSpan] | None = None,
    ) -> None:
        run_handle = self.store.get("run_handle")
        if run_handle is not None and hasattr(run_handle, "set_active_vm"):
            run_handle.set_active_vm(self)
            
        try:
            for index, item in enumerate(ast):
                trace_span = trace_spans[index] if trace_spans and index < len(trace_spans) else None
                authored_span = authored_spans[index] if authored_spans and index < len(authored_spans) else None
                if isinstance(item, list):
                    stack_before = list(self.stack)
                    if trace_span is not None and trace_span.children:
                        self._quotation_trace_spans[id(item)] = list(trace_span.children)
                    if authored_span is not None and authored_span.children:
                        self._quotation_authored_spans[id(item)] = list(authored_span.children)
                    self.stack.append(item)
                    self._record_trace(
                        "push-quotation",
                        value=item,
                        trace_span=trace_span,
                        authored_span=authored_span,
                        stack_before=stack_before,
                    )
                    continue
                token_type, token_value = item
                if token_type in {"str", "int", "float", "bool", "none"}:
                    stack_before = list(self.stack)
                    self.stack.append(token_value)
                    self._record_trace(
                        "push-literal",
                        token_type=token_type,
                        value=token_value,
                        trace_span=trace_span,
                        authored_span=authored_span,
                        stack_before=stack_before,
                    )
                    continue
                if token_type == "sym":
                    if token_value not in self.words:
                        raise ValueError(f"Unknown word: '{token_value}'")
                    stack_before = list(self.stack)
                    await self._call_word(self.words[token_value])
                    self._record_trace(
                        "word",
                        word=token_value,
                        trace_span=trace_span,
                        authored_span=authored_span,
                        stack_before=stack_before,
                    )
        finally:
            if run_handle is not None and hasattr(run_handle, "set_active_vm"):
                if run_handle.get_active_vm() is self:
                    run_handle.set_active_vm(None)

    def _record_trace(
        self,
        op: str,
        *,
        trace_span: StackVmAstSpan | None = None,
        authored_span: StackVmAstSpan | None = None,
        stack_before: list[Any] | None = None,
        **payload: Any,
    ) -> None:
        if not self.store.get("stackvm_trace_enabled"):
            return
        trace = self.store.setdefault("vm_trace", [])
        if not isinstance(trace, list):
            return
        before_stack = list(stack_before or [])
        after_stack = list(self.stack)
        entry = {
            "op": str(op),
            **{key: _snapshot_vm_value(value) for key, value in payload.items()},
            "scope": self._current_trace_scope(),
            "depth": max(len(self._trace_scope_stack) - 1, 0),
            "stack_before": _snapshot_vm_value(before_stack),
            "stack_after": _snapshot_vm_value(after_stack),
            "stack_delta": _snapshot_vm_value(_stack_delta(before_stack, after_stack)),
            "stack": _snapshot_vm_value(after_stack),
        }
        if trace_span is not None and trace_span.span.location:
            entry["location"] = trace_span.span.location
        if authored_span is not None and authored_span.span.location:
            entry["authored_location"] = authored_span.span.location
        trace.append(entry)

    def _current_trace_scope(self) -> str:
        if not self._trace_scope_stack:
            return "main"
        return str(self._trace_scope_stack[-1] or "main")

    def _record_scope_summary(
        self,
        *,
        scope: str,
        depth: int,
        input_stack: list[Any],
        output_stack: list[Any],
        location: str | None = None,
        authored_location: str | None = None,
    ) -> None:
        if not self.store.get("stackvm_trace_enabled"):
            return
        summaries = self.store.setdefault("vm_trace_scope_summaries", [])
        if not isinstance(summaries, list):
            return
        summaries.append(
            {
                "scope": str(scope or "main"),
                "depth": int(depth),
                "input_stack": _snapshot_vm_value(list(input_stack)),
                "output_stack": _snapshot_vm_value(list(output_stack)),
                "stack_delta": _snapshot_vm_value(_stack_delta(list(input_stack), list(output_stack))),
                "shape_preserved": len(input_stack) == len(output_stack),
                "location": location,
                "authored_location": authored_location,
            }
        )

    def _record_runtime_decision(
        self,
        *,
        scope: str,
        decision: str,
        detail: str,
        value: Any = None,
    ) -> None:
        if not self.store.get("stackvm_trace_enabled"):
            return
        decisions = self.store.setdefault("vm_trace_decisions", [])
        if not isinstance(decisions, list):
            return
        entry = {
            "scope": str(scope or self._current_trace_scope()),
            "depth": max(len(self._trace_scope_stack) - 1, 0),
            "decision": str(decision),
            "detail": str(detail),
        }
        if value is not None:
            entry["value"] = _snapshot_vm_value(value)
        decisions.append(entry)

    @contextmanager
    def _trace_scope(
        self,
        suffix: str,
        *,
        trace_span: StackVmAstSpan | None = None,
        authored_span: StackVmAstSpan | None = None,
    ):
        parent = self._current_trace_scope()
        scope = str(suffix or "").strip()
        if not scope:
            yield parent
            return
        full_scope = scope if parent == scope or scope.startswith(parent) else f"{parent} > {scope}"
        input_stack = list(self.stack)
        self._trace_scope_stack.append(full_scope)
        try:
            yield full_scope
        finally:
            self._trace_scope_stack.pop()
            self._record_scope_summary(
                scope=full_scope,
                depth=max(len(self._trace_scope_stack), 0),
                input_stack=input_stack,
                output_stack=list(self.stack),
                location=trace_span.span.location if trace_span is not None else None,
                authored_location=authored_span.span.location if authored_span is not None else None,
            )

    def register_host_words(
        self,
        *,
        host_context: StackVmHostContext | None = None,
        result: StackVmExecutionResult | None = None,
        host_adapter: StackVmHostAdapter | None = None,
    ) -> None:
        if host_adapter is None:
            if host_context is None or result is None:
                raise TypeError("register_host_words requires either host_adapter or both host_context and result.")
            host_adapter = PocketCoderStackVmHostAdapter(
                shared_store=self.store,
                host_context=host_context,
                result=result,
            )
        self._host_adapter = host_adapter
        self._host_context = host_adapter.host_context

        def set_transition_word() -> None:
            transition_name = str(self.stack.pop() if self.stack else "continue")
            self._host_adapter.emit_effect(transition_effect(transition_name))

        def answer() -> None:
            answer_text = self.stack.pop() if self.stack else ""
            self._host_adapter.emit_effect(final_answer_effect(str(answer_text)))

        def ask_user() -> None:
            question = self.stack.pop() if self.stack else ""
            self._host_adapter.emit_effect(ask_user_effect(str(question)))

        async def prompt_user() -> None:
            question = str(self.stack.pop() if self.stack else "")
            self.stack.append(await self._host_adapter.prompt_text(question))

        async def prompt_interaction() -> None:
            request = coerce_prompt_interaction_request(self.stack.pop() if self.stack else {})
            self.stack.append(await self._host_adapter.prompt_interaction(request))

        def handoff() -> None:
            target = self.stack.pop() if self.stack else ""
            self._host_adapter.emit_effect(handoff_effect(str(target)))

        def tool_request() -> None:
            arguments = coerce_tool_arguments(self.stack.pop() if self.stack else {})
            tool_name = self.stack.pop() if self.stack else ""
            self._host_adapter.emit_effect(
                call_tool_effect(
                    tool_name=str(tool_name),
                    arguments=dict(arguments),
                    requested_by=self._host_context.agent_name,
                )
            )

        def tool_call() -> None:
            arguments = coerce_tool_arguments(self.stack.pop() if self.stack else {})
            tool_name = self.stack.pop() if self.stack else ""
            self.stack.append(self._host_adapter.execute_tool(str(tool_name), dict(arguments)))

        async def llm_call() -> None:
            prompt = str(self.stack.pop() if self.stack else "")
            self.stack.append(await self._host_adapter.llm_call(prompt))

        self.register_word("answer", answer)
        self.register_word("ask-user", ask_user)
        self.register_word("prompt-user", prompt_user)
        self.register_word("prompt-interaction", prompt_interaction)
        self.register_word("handoff", handoff)
        self.register_word("tool-request", tool_request)
        self.register_word("tool-call", tool_call)
        self.register_word("transition", set_transition_word)
        self.register_word("llm-call", llm_call)
        self.register_word("system-prompt", lambda: self.stack.append(self._host_context.system_prompt))
        self.register_word("llm-profile", lambda: self.stack.append(self._host_context.llm_profile))
        self.register_word("tool-definitions", lambda: self.stack.append(list(self._host_context.tool_definitions)))
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
        self.register_word("yaml<", self._to_yaml)
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
        self.register_word("merge", self._merge_mappings)
        self.register_word("schema-check", self._schema_check)
        self.register_word("schema-apply", self._schema_apply)
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
        self.register_word("match", self._builtin_match)
        self.register_word("fallback", self._builtin_fallback)
        self.register_word("map", self._builtin_map)
        self.register_word("flat-map", self._builtin_flat_map)
        self.register_word("filter", self._builtin_filter)
        self.register_word("find", self._builtin_find)
        self.register_word("any?", self._builtin_any)
        self.register_word("all?", self._builtin_all)
        self.register_word("sort-by", self._builtin_sort_by)
        self.register_word("group-by", self._builtin_group_by)
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
        b = self.stack.pop()
        a = self.stack.pop()
        self.stack.append(a + b)

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

    def _to_yaml(self) -> None:
        value = self.stack.pop() if self.stack else None
        dumped = yaml.safe_dump(value, default_flow_style=True, sort_keys=False)
        if dumped.endswith("\n...\n"):
            dumped = dumped[:-5]
        elif dumped.endswith("\n"):
            dumped = dumped[:-1]
        self.stack.append(dumped)

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

    def _merge_mappings(self) -> None:
        right = self.stack.pop()
        left = self.stack.pop()
        if not isinstance(left, dict):
            raise TypeError(f"merge expects a dict on the left, got {type(left)!r}")
        if not isinstance(right, dict):
            raise TypeError(f"merge expects a dict on the right, got {type(right)!r}")
        self.stack.append({**left, **right})

    def _schema_check(self) -> None:
        schema = self.stack.pop()
        value = self.stack.pop()
        if not isinstance(schema, dict):
            raise TypeError(f"schema-check expects a dict schema, got {type(schema)!r}")
        errors = validate_schema_value(value, schema, path="value")
        self.stack.append(
            {
                "success": len(errors) == 0,
                "value": value,
                "errors": list(errors),
            }
        )

    def _schema_apply(self) -> None:
        schema = self.stack.pop()
        value = self.stack.pop()
        if not isinstance(schema, dict):
            raise TypeError(f"schema-apply expects a dict schema, got {type(schema)!r}")
        coerced_value, errors = apply_schema_value(value, schema, path="value")
        self.stack.append(
            {
                "success": len(errors) == 0,
                "value": coerced_value,
                "errors": list(errors),
            }
        )

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
        with self._trace_scope("call"):
            await self.execute_ast(
                quotation_ast,
                trace_spans=self._quotation_trace_spans.get(id(quotation_ast)),
                authored_spans=self._quotation_authored_spans.get(id(quotation_ast)),
            )

    async def _builtin_if(self) -> None:
        false_ast = self.stack.pop()
        true_ast = self.stack.pop()
        condition = self.stack.pop()
        branch_ast = true_ast if condition else false_ast
        branch_scope = "if:true" if condition else "if:false"
        self._record_runtime_decision(
            scope=f"{self._current_trace_scope()} > {branch_scope}",
            decision="if-branch",
            detail="Selected true branch." if condition else "Selected false branch.",
            value=condition,
        )
        with self._trace_scope(branch_scope):
            await self.execute_ast(
                branch_ast,
                trace_spans=self._quotation_trace_spans.get(id(branch_ast)),
                authored_spans=self._quotation_authored_spans.get(id(branch_ast)),
            )

    async def _builtin_while(self) -> None:
        body_ast = self.stack.pop()
        condition_ast = self.stack.pop()
        iteration = 0
        while True:
            with self._trace_scope("while:condition"):
                await self.execute_ast(
                    condition_ast,
                    trace_spans=self._quotation_trace_spans.get(id(condition_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(condition_ast)),
                )
            condition_value = self.stack.pop()
            if not condition_value:
                self._record_runtime_decision(
                    scope=f"{self._current_trace_scope()} > while:condition",
                    decision="while-stop",
                    detail=f"Stopped loop after {iteration} iteration(s).",
                    value=condition_value,
                )
                break
            self._record_runtime_decision(
                scope=f"{self._current_trace_scope()} > while:body",
                decision="while-continue",
                detail=f"Entered loop body for iteration {iteration + 1}.",
                value=condition_value,
            )
            with self._trace_scope("while:body"):
                await self.execute_ast(
                    body_ast,
                    trace_spans=self._quotation_trace_spans.get(id(body_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(body_ast)),
                )
            iteration += 1

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
                self._record_runtime_decision(
                    scope=f"{self._current_trace_scope()} > switch:case",
                    decision="switch-match",
                    detail=f"Matched case {case_value!r}.",
                    value=target_value,
                )
                with self._trace_scope("switch:case"):
                    await self.execute_ast(
                        action_ast,
                        trace_spans=self._quotation_trace_spans.get(id(action_ast)),
                        authored_spans=self._quotation_authored_spans.get(id(action_ast)),
                    )
                return

        if default_action is not None:
            self._record_runtime_decision(
                scope=f"{self._current_trace_scope()} > switch:default",
                decision="switch-default",
                detail="Fell back to default case.",
                value=target_value,
            )
            with self._trace_scope("switch:default"):
                await self.execute_ast(
                    default_action,
                    trace_spans=self._quotation_trace_spans.get(id(default_action)),
                    authored_spans=self._quotation_authored_spans.get(id(default_action)),
                )
            return
        self._record_runtime_decision(
            scope=f"{self._current_trace_scope()} > switch",
            decision="switch-no-match",
            detail="No switch case matched and no default case was present.",
            value=target_value,
        )

    async def _builtin_cond(self) -> None:
        cases_ast = self.stack.pop()
        pairs = self._normalize_case_pairs(cases_ast, word_name="cond")

        for index, (condition_ast, action_ast) in enumerate(pairs, start=1):
            if not isinstance(condition_ast, list):
                raise TypeError("cond expects each condition to be a quotation.")
            with self._trace_scope("cond:condition"):
                await self.execute_ast(
                    condition_ast,
                    trace_spans=self._quotation_trace_spans.get(id(condition_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(condition_ast)),
                )
            if not self.stack:
                raise RuntimeError("cond condition did not leave a value on the stack.")
            condition_value = self.stack.pop()
            if condition_value:
                self._record_runtime_decision(
                    scope=f"{self._current_trace_scope()} > cond:action",
                    decision="cond-match",
                    detail=f"Condition {index} matched.",
                    value=condition_value,
                )
                with self._trace_scope("cond:action"):
                    await self.execute_ast(
                        action_ast,
                        trace_spans=self._quotation_trace_spans.get(id(action_ast)),
                        authored_spans=self._quotation_authored_spans.get(id(action_ast)),
                    )
                return
        self._record_runtime_decision(
            scope=f"{self._current_trace_scope()} > cond",
            decision="cond-no-match",
            detail="No cond condition matched.",
        )

    async def _builtin_match(self) -> None:
        cases_ast = self.stack.pop()
        target_value = self.stack.pop()
        pairs = self._normalize_case_pairs(cases_ast, word_name="match")

        for pattern_node, action_ast in pairs:
            pattern_value = await self._evaluate_match_pattern(pattern_node)
            bindings = _match_pattern_value(pattern_value, target_value)
            if bindings is None:
                continue
            self.store["match"] = dict(bindings)
            self.store["match_bindings"] = dict(bindings)
            for key, value in bindings.items():
                _assign_path(self.store, f"match.{key}", value)
            self._record_runtime_decision(
                scope=f"{self._current_trace_scope()} > match:action",
                decision="match-case",
                detail=f"Matched pattern with {len(bindings)} binding(s).",
                value=bindings,
            )
            with self._trace_scope("match:action"):
                await self.execute_ast(
                    action_ast,
                    trace_spans=self._quotation_trace_spans.get(id(action_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(action_ast)),
                )
            return
        self._record_runtime_decision(
            scope=f"{self._current_trace_scope()} > match",
            decision="match-no-case",
            detail="No match pattern matched the target value.",
            value=target_value,
        )

    async def _builtin_fallback(self) -> None:
        fallback_ast = self.stack.pop()
        primary_ast = self.stack.pop()
        if not isinstance(primary_ast, list) or not isinstance(fallback_ast, list):
            raise TypeError("fallback expects primary and fallback quotations.")

        stack_snapshot = list(self.stack)
        try:
            with self._trace_scope("fallback:primary"):
                await self.execute_ast(
                    primary_ast,
                    trace_spans=self._quotation_trace_spans.get(id(primary_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(primary_ast)),
                )
            self._record_runtime_decision(
                scope=f"{self._current_trace_scope()} > fallback:primary",
                decision="fallback-primary-succeeded",
                detail="Primary quotation completed without fallback.",
            )
        except StackVmIllegalChildEffectError:
            raise
        except Exception as exc:
            self._record_runtime_decision(
                scope=f"{self._current_trace_scope()} > fallback:fallback",
                decision="fallback-used",
                detail=f"Primary quotation raised {type(exc).__name__}; executing fallback.",
            )
            self.stack[:] = stack_snapshot
            with self._trace_scope("fallback:fallback"):
                await self.execute_ast(
                    fallback_ast,
                    trace_spans=self._quotation_trace_spans.get(id(fallback_ast)),
                    authored_spans=self._quotation_authored_spans.get(id(fallback_ast)),
                )

    async def _builtin_parallel_map(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("parallel-map expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"parallel-map expects a list or tuple, got {type(values)!r}")

        async def _run_item(item: Any) -> Any:
            child_vm = self._make_child_vm()
            child_vm._trace_scope_stack = [f"{self._current_trace_scope()} > parallel-map:child"]
            child_vm.stack.append(item)
            await child_vm.execute_ast(
                quotation_ast,
                trace_spans=self._quotation_trace_spans.get(id(quotation_ast)),
                authored_spans=self._quotation_authored_spans.get(id(quotation_ast)),
            )
            child_vm._raise_if_child_requested_transition(combinator_name="parallel-map")
            return child_vm.stack.pop() if child_vm.stack else None

        results = await asyncio.gather(*(_run_item(item) for item in values))
        self.stack.append(list(results))

    async def _builtin_map(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("map expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"map expects a list or tuple, got {type(values)!r}")

        results = [await self._run_unary_child_quotation(item, quotation_ast, combinator_name="map") for item in values]
        self.stack.append(results)

    async def _builtin_flat_map(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("flat-map expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"flat-map expects a list or tuple, got {type(values)!r}")

        flattened: list[Any] = []
        for item in values:
            mapped = await self._run_unary_child_quotation(item, quotation_ast, combinator_name="flat-map")
            if isinstance(mapped, (list, tuple)):
                flattened.extend(mapped)
            else:
                flattened.append(mapped)
        self.stack.append(flattened)

    async def _builtin_filter(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("filter expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"filter expects a list or tuple, got {type(values)!r}")

        results: list[Any] = []
        for item in values:
            include_item = await self._run_unary_child_quotation(item, quotation_ast, combinator_name="filter")
            if include_item:
                results.append(item)
        self.stack.append(results)

    async def _builtin_find(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("find expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"find expects a list or tuple, got {type(values)!r}")

        for item in values:
            include_item = await self._run_unary_child_quotation(item, quotation_ast, combinator_name="find")
            if include_item:
                self.stack.append(item)
                return
        self.stack.append(None)

    async def _builtin_any(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("any? expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"any? expects a list or tuple, got {type(values)!r}")

        for item in values:
            if await self._run_unary_child_quotation(item, quotation_ast, combinator_name="any?"):
                self.stack.append(True)
                return
        self.stack.append(False)

    async def _builtin_all(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("all? expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"all? expects a list or tuple, got {type(values)!r}")

        for item in values:
            if not await self._run_unary_child_quotation(item, quotation_ast, combinator_name="all?"):
                self.stack.append(False)
                return
        self.stack.append(True)

    async def _builtin_sort_by(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("sort-by expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"sort-by expects a list or tuple, got {type(values)!r}")

        keyed_values: list[tuple[Any, Any]] = []
        for item in values:
            sort_key = await self._run_unary_child_quotation(item, quotation_ast, combinator_name="sort-by")
            keyed_values.append((sort_key, item))
        keyed_values.sort(key=lambda pair: pair[0])
        self.stack.append([item for _, item in keyed_values])

    async def _builtin_group_by(self) -> None:
        quotation_ast = self.stack.pop()
        values = self.stack.pop()
        if not isinstance(quotation_ast, list):
            raise TypeError("group-by expects a quotation.")
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"group-by expects a list or tuple, got {type(values)!r}")

        grouped: dict[str, list[Any]] = {}
        for item in values:
            group_key = await self._run_unary_child_quotation(item, quotation_ast, combinator_name="group-by")
            grouped.setdefault(str(group_key), []).append(item)
        self.stack.append(grouped)

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
            child_vm._trace_scope_stack = [f"{self._current_trace_scope()} > reduce:child"]
            child_vm.stack.append(accumulator)
            child_vm.stack.append(item)
            await child_vm.execute_ast(
                quotation_ast,
                trace_spans=self._quotation_trace_spans.get(id(quotation_ast)),
                authored_spans=self._quotation_authored_spans.get(id(quotation_ast)),
            )
            child_vm._raise_if_child_requested_transition(combinator_name="reduce")
            accumulator = child_vm.stack.pop() if child_vm.stack else None

        self.stack.append(accumulator)

    def _builtin_define(self) -> None:
        word_name = str(self.stack.pop())
        quotation_ast = self.stack.pop()

        if not isinstance(quotation_ast, list):
            raise TypeError("define expects a quotation before the word name.")

        self._define_user_word(
            word_name,
            quotation_ast,
            trace_spans=self._quotation_trace_spans.get(id(quotation_ast)),
            authored_spans=self._quotation_authored_spans.get(id(quotation_ast)),
        )

    def _define_user_word(
        self,
        word_name: str,
        quotation_ast: list[Any],
        *,
        trace_spans: list[StackVmAstSpan] | None = None,
        authored_spans: list[StackVmAstSpan] | None = None,
    ) -> None:
        self._user_word_defs[str(word_name)] = (quotation_ast, trace_spans, authored_spans)
        if trace_spans is not None:
            self._quotation_trace_spans[id(quotation_ast)] = list(trace_spans)
        if authored_spans is not None:
            self._quotation_authored_spans[id(quotation_ast)] = list(authored_spans)

        async def custom_user_word(
            ast: list[Any] = quotation_ast,
            word_trace_spans: list[StackVmAstSpan] | None = trace_spans,
            word_authored_spans: list[StackVmAstSpan] | None = authored_spans,
        ) -> None:
            with self._trace_scope(f"word:{word_name}"):
                await self.execute_ast(ast, trace_spans=word_trace_spans, authored_spans=word_authored_spans)

        self.register_word(str(word_name), custom_user_word)

    async def _run_unary_child_quotation(self, item: Any, quotation_ast: list[Any], *, combinator_name: str) -> Any:
        child_vm = self._make_child_vm()
        child_vm._trace_scope_stack = [f"{self._current_trace_scope()} > {combinator_name}:child"]
        child_vm.stack.append(item)
        await child_vm.execute_ast(
            quotation_ast,
            trace_spans=self._quotation_trace_spans.get(id(quotation_ast)),
            authored_spans=self._quotation_authored_spans.get(id(quotation_ast)),
        )
        child_vm._raise_if_child_requested_transition(combinator_name=combinator_name)
        return child_vm.stack.pop() if child_vm.stack else None

    def _make_child_vm(self) -> AgentStackVM:
        child_vm = AgentStackVM(shared_store=_clone_for_child(self.store))
        if self._host_context is not None:
            child_vm.register_host_words(
                host_context=self._host_context,
                result=StackVmExecutionResult(),
            )
        for word_name, (word_ast, word_trace_spans, word_authored_spans) in self._user_word_defs.items():
            child_vm._define_user_word(
                word_name,
                word_ast,
                trace_spans=word_trace_spans,
                authored_spans=word_authored_spans,
            )
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

    async def _evaluate_match_pattern(self, pattern_node: Any) -> Any:
        if isinstance(pattern_node, list):
            child_vm = self._make_child_vm()
            child_vm._trace_scope_stack = [f"{self._current_trace_scope()} > match:pattern"]
            await child_vm.execute_ast(
                pattern_node,
                trace_spans=self._quotation_trace_spans.get(id(pattern_node)),
                authored_spans=self._quotation_authored_spans.get(id(pattern_node)),
            )
            return child_vm.stack.pop() if child_vm.stack else None
        if not isinstance(pattern_node, tuple) or len(pattern_node) != 2:
            raise TypeError("match encountered an invalid pattern entry.")
        token_type, token_value = pattern_node
        if token_type == "sym":
            return str(token_value)
        return token_value

    def _raise_if_child_requested_transition(self, *, combinator_name: str) -> None:
        if self.store.get("pending_tool"):
            raise StackVmIllegalChildEffectError(f"{combinator_name} child quotations cannot schedule tool requests.")
        if self.store.get("pending_handoff_agent"):
            raise StackVmIllegalChildEffectError(f"{combinator_name} child quotations cannot perform handoffs.")
        if self.store.get("question_to_ask"):
            raise StackVmIllegalChildEffectError(f"{combinator_name} child quotations cannot ask the user.")
        if self.store.get("final_answer"):
            raise StackVmIllegalChildEffectError(f"{combinator_name} child quotations cannot finalize answers.")


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


def _match_pattern_value(pattern: Any, value: Any, *, bindings: dict[str, Any] | None = None) -> dict[str, Any] | None:
    resolved = dict(bindings or {})

    if pattern == "_":
        return resolved

    if isinstance(pattern, str) and pattern.startswith("$*") and len(pattern) > 2:
        return _bind_match_value(resolved, pattern[2:], value)

    if isinstance(pattern, str) and pattern.startswith("$") and len(pattern) > 1:
        binding_name, expected_type = _parse_match_binding_pattern(pattern[1:])
        if expected_type is not None and not _match_value_has_type(value, expected_type):
            return None
        if not binding_name:
            return resolved if expected_type is not None else None
        matched = _bind_match_value(resolved, binding_name, value)
        if matched is None:
            return None
        resolved = matched
        return resolved

    if isinstance(pattern, dict):
        if not isinstance(value, dict):
            return None
        explicit_keys = [key for key in pattern.keys() if key != "$rest"]
        for key in explicit_keys:
            child_pattern = pattern[key]
            if key not in value:
                return None
            matched = _match_pattern_value(child_pattern, value[key], bindings=resolved)
            if matched is None:
                return None
            resolved = matched
        if "$rest" in pattern:
            rest_value = {key: child_value for key, child_value in value.items() if key not in explicit_keys}
            matched = _match_pattern_value(pattern["$rest"], rest_value, bindings=resolved)
            if matched is None:
                return None
            resolved = matched
        return resolved

    if isinstance(pattern, list):
        if not isinstance(value, list):
            return None
        rest_capture = None
        fixed_patterns = pattern
        if pattern and isinstance(pattern[-1], str) and pattern[-1].startswith("$*") and len(pattern[-1]) > 2:
            rest_capture = pattern[-1][2:]
            fixed_patterns = pattern[:-1]
            if len(value) < len(fixed_patterns):
                return None
        elif len(pattern) != len(value):
            return None
        for child_pattern, child_value in zip(fixed_patterns, value):
            matched = _match_pattern_value(child_pattern, child_value, bindings=resolved)
            if matched is None:
                return None
            resolved = matched
        if rest_capture is not None:
            matched = _bind_match_value(resolved, rest_capture, value[len(fixed_patterns):])
            if matched is None:
                return None
            resolved = matched
        return resolved

    return resolved if pattern == value else None


def _parse_match_binding_pattern(binding: str) -> tuple[str, str | None]:
    if ":" not in binding:
        return binding, None
    binding_name, expected_type = binding.split(":", 1)
    return binding_name, expected_type.strip().lower() or None


def _bind_match_value(bindings: dict[str, Any], name: str, value: Any) -> dict[str, Any] | None:
    existing = bindings.get(name, _MISSING)
    if existing is not _MISSING and existing != value:
        return None
    bindings[name] = value
    return bindings


def _match_value_has_type(value: Any, expected_type: str) -> bool:
    if expected_type == "any":
        return True
    if expected_type == "none":
        return value is None
    if expected_type == "bool":
        return isinstance(value, bool)
    if expected_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "float":
        return isinstance(value, float)
    if expected_type == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "dict":
        return isinstance(value, dict)
    return False


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
