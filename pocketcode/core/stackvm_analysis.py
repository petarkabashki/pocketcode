from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from pocketcode.core.stackvm_parser import StackVmAstSpan, StackVmSourceToken, parse_stackvm_source_with_spans, tokenize_stackvm_source


EffectKind = Literal["pure", "state", "tool", "prompt", "handoff", "final", "llm", "control"]
HostSurface = Literal["core", "portable_host", "pocketcoder_host"]


@dataclass(frozen=True)
class StackVmStackEffect:
    pops: int
    pushes: int | None = None
    notes: str = ""


@dataclass(frozen=True)
class StackVmWordMetadata:
    name: str
    stack_effect: StackVmStackEffect
    effect_kind: EffectKind
    summary: str = ""
    output_shape: tuple[str, ...] = ()
    host_surface: HostSurface = "core"
    definition_span: StackVmAstSpan | None = None


@dataclass
class _AbstractValue:
    kind: str
    literal: Any = None
    quotation: list[Any] | None = None
    data: Any = None


@dataclass
class _AnalysisState:
    stack: list[_AbstractValue] = field(default_factory=list)
    effects: set[str] = field(default_factory=set)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    required_inputs: int = 0
    max_stack_depth: int = 0

    def clone(self) -> _AnalysisState:
        return _AnalysisState(
            stack=[
                _AbstractValue(kind=value.kind, literal=value.literal, quotation=value.quotation, data=value.data)
                for value in self.stack
            ],
            effects=set(self.effects),
            diagnostics=list(self.diagnostics),
            required_inputs=self.required_inputs,
            max_stack_depth=self.max_stack_depth,
        )


def get_stackvm_word_metadata(*, include_host_words: bool = True) -> dict[str, StackVmWordMetadata]:
    metadata: dict[str, StackVmWordMetadata] = {
        "dup": StackVmWordMetadata("dup", StackVmStackEffect(1, 2), "pure"),
        "drop": StackVmWordMetadata("drop", StackVmStackEffect(1, 0), "pure"),
        "swap": StackVmWordMetadata("swap", StackVmStackEffect(2, 2), "pure"),
        "over": StackVmWordMetadata("over", StackVmStackEffect(2, 3), "pure"),
        "stack-depth": StackVmWordMetadata("stack-depth", StackVmStackEffect(0, 1), "pure", output_shape=("int",)),
        "stack-empty?": StackVmWordMetadata("stack-empty?", StackVmStackEffect(0, 1), "pure", output_shape=("bool",)),
        "can-pop?": StackVmWordMetadata("can-pop?", StackVmStackEffect(0, 1), "pure", output_shape=("bool",)),
        "can-dup?": StackVmWordMetadata("can-dup?", StackVmStackEffect(0, 1), "pure", output_shape=("bool",)),
        "can-swap?": StackVmWordMetadata("can-swap?", StackVmStackEffect(0, 1), "pure", output_shape=("bool",)),
        "can-over?": StackVmWordMetadata("can-over?", StackVmStackEffect(0, 1), "pure", output_shape=("bool",)),
        "print": StackVmWordMetadata("print", StackVmStackEffect(1, 0), "control"),
        "concat": StackVmWordMetadata("concat", StackVmStackEffect(2, 1), "pure", output_shape=("str",)),
        "join": StackVmWordMetadata("join", StackVmStackEffect(2, 1), "pure", output_shape=("str",)),
        "+": StackVmWordMetadata("+", StackVmStackEffect(2, 1), "pure"),
        "-": StackVmWordMetadata("-", StackVmStackEffect(2, 1), "pure"),
        "*": StackVmWordMetadata("*", StackVmStackEffect(2, 1), "pure"),
        "/": StackVmWordMetadata("/", StackVmStackEffect(2, 1), "pure"),
        "len": StackVmWordMetadata("len", StackVmStackEffect(1, 1), "pure", output_shape=("int",)),
        "empty?": StackVmWordMetadata("empty?", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "contains?": StackVmWordMetadata("contains?", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "success?": StackVmWordMetadata("success?", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "failure?": StackVmWordMetadata("failure?", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "int>": StackVmWordMetadata("int>", StackVmStackEffect(1, 1), "pure", output_shape=("int",)),
        "float>": StackVmWordMetadata("float>", StackVmStackEffect(1, 1), "pure", output_shape=("float",)),
        "bool>": StackVmWordMetadata("bool>", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "str>": StackVmWordMetadata("str>", StackVmStackEffect(1, 1), "pure", output_shape=("str",)),
        "not": StackVmWordMetadata("not", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "none?": StackVmWordMetadata("none?", StackVmStackEffect(1, 1), "pure", output_shape=("bool",)),
        "=": StackVmWordMetadata("=", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        ">": StackVmWordMetadata(">", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "<": StackVmWordMetadata("<", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        ">=": StackVmWordMetadata(">=", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "<=": StackVmWordMetadata("<=", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "yaml>": StackVmWordMetadata("yaml>", StackVmStackEffect(1, 1), "pure"),
        "yaml<": StackVmWordMetadata("yaml<", StackVmStackEffect(1, 1), "pure", output_shape=("str",)),
        "dict-get": StackVmWordMetadata("dict-get", StackVmStackEffect(2, 1), "pure"),
        "dict-get?": StackVmWordMetadata("dict-get?", StackVmStackEffect(2, 1), "pure"),
        "get-in": StackVmWordMetadata("get-in", StackVmStackEffect(2, 1), "pure"),
        "get-in?": StackVmWordMetadata("get-in?", StackVmStackEffect(2, 1), "pure"),
        "dict-set": StackVmWordMetadata("dict-set", StackVmStackEffect(3, 1), "pure"),
        "set-in": StackVmWordMetadata("set-in", StackVmStackEffect(3, 1), "pure"),
        "set-in?": StackVmWordMetadata("set-in?", StackVmStackEffect(3, 1), "pure"),
        "list-get": StackVmWordMetadata("list-get", StackVmStackEffect(2, 1), "pure"),
        "list-get?": StackVmWordMetadata("list-get?", StackVmStackEffect(2, 1), "pure"),
        "list-set": StackVmWordMetadata("list-set", StackVmStackEffect(3, 1), "pure"),
        "keys": StackVmWordMetadata("keys", StackVmStackEffect(1, 1), "pure", output_shape=("unknown",)),
        "values": StackVmWordMetadata("values", StackVmStackEffect(1, 1), "pure", output_shape=("unknown",)),
        "merge": StackVmWordMetadata("merge", StackVmStackEffect(2, 1), "pure", output_shape=("unknown",)),
        "map": StackVmWordMetadata("map", StackVmStackEffect(2, 1), "pure", output_shape=("list",)),
        "flat-map": StackVmWordMetadata("flat-map", StackVmStackEffect(2, 1), "pure", output_shape=("list",)),
        "filter": StackVmWordMetadata("filter", StackVmStackEffect(2, 1), "pure", output_shape=("list",)),
        "find": StackVmWordMetadata("find", StackVmStackEffect(2, 1), "pure", output_shape=("unknown",)),
        "any?": StackVmWordMetadata("any?", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "all?": StackVmWordMetadata("all?", StackVmStackEffect(2, 1), "pure", output_shape=("bool",)),
        "sort-by": StackVmWordMetadata("sort-by", StackVmStackEffect(2, 1), "pure", output_shape=("list",)),
        "group-by": StackVmWordMetadata("group-by", StackVmStackEffect(2, 1), "pure", output_shape=("dict",)),
        "schema-check": StackVmWordMetadata("schema-check", StackVmStackEffect(2, 1), "pure", output_shape=("dict",)),
        "schema-apply": StackVmWordMetadata("schema-apply", StackVmStackEffect(2, 1), "pure", output_shape=("dict",)),
        "list-append": StackVmWordMetadata("list-append", StackVmStackEffect(2, 1), "pure"),
        "store-set": StackVmWordMetadata("store-set", StackVmStackEffect(2, 0), "state"),
        "store-get": StackVmWordMetadata("store-get", StackVmStackEffect(1, 1), "state"),
        "shared!": StackVmWordMetadata("shared!", StackVmStackEffect(2, 0), "state"),
        "shared!?": StackVmWordMetadata("shared!?", StackVmStackEffect(2, 1), "state"),
        "shared@": StackVmWordMetadata("shared@", StackVmStackEffect(1, 1), "state"),
        "match": StackVmWordMetadata("match", StackVmStackEffect(2, None), "control"),
    }

    if include_host_words:
        metadata.update(
            {
                "answer": StackVmWordMetadata("answer", StackVmStackEffect(1, 0), "final", host_surface="portable_host"),
                "ask-user": StackVmWordMetadata("ask-user", StackVmStackEffect(1, 0), "prompt", host_surface="portable_host"),
                "prompt-user": StackVmWordMetadata("prompt-user", StackVmStackEffect(1, 1), "prompt", host_surface="portable_host"),
                "prompt-interaction": StackVmWordMetadata("prompt-interaction", StackVmStackEffect(1, 1), "prompt", host_surface="portable_host"),
                "handoff": StackVmWordMetadata("handoff", StackVmStackEffect(1, 0), "handoff", host_surface="pocketcoder_host"),
                "tool-call": StackVmWordMetadata("tool-call", StackVmStackEffect(2, 1), "tool", output_shape=("unknown",), host_surface="portable_host"),
                "tool-request": StackVmWordMetadata("tool-request", StackVmStackEffect(2, 0), "tool", host_surface="pocketcoder_host"),
                "transition": StackVmWordMetadata("transition", StackVmStackEffect(1, 0), "control", host_surface="portable_host"),
                "llm-call": StackVmWordMetadata("llm-call", StackVmStackEffect(1, 1), "llm", host_surface="portable_host"),
                "system-prompt": StackVmWordMetadata("system-prompt", StackVmStackEffect(0, 1), "pure", output_shape=("str",), host_surface="portable_host"),
                "llm-profile": StackVmWordMetadata("llm-profile", StackVmStackEffect(0, 1), "pure", host_surface="portable_host"),
                "tool-definitions": StackVmWordMetadata("tool-definitions", StackVmStackEffect(0, 1), "pure", output_shape=("unknown",), host_surface="portable_host"),
                "request": StackVmWordMetadata("request", StackVmStackEffect(0, 1), "state", output_shape=("str",), host_surface="portable_host"),
                "last-tool-result": StackVmWordMetadata("last-tool-result", StackVmStackEffect(0, 1), "state", host_surface="portable_host"),
                "last-tool-route": StackVmWordMetadata("last-tool-route", StackVmStackEffect(0, 1), "state", host_surface="portable_host"),
                "results": StackVmWordMetadata("results", StackVmStackEffect(0, 1), "state", host_surface="portable_host"),
                "active-session-transcript": StackVmWordMetadata("active-session-transcript", StackVmStackEffect(0, 1), "state", output_shape=("unknown",), host_surface="pocketcoder_host"),
                "active-session-transcript-text": StackVmWordMetadata("active-session-transcript-text", StackVmStackEffect(1, 1), "state", output_shape=("str",), host_surface="pocketcoder_host"),
            }
        )

    return metadata


def analyze_stackvm_ast(
    ast: list[Any],
    *,
    source: str | None = None,
    include_host_words: bool = True,
    authored_spans: list[StackVmAstSpan] | None = None,
) -> dict[str, Any]:
    effective_authored_spans = authored_spans
    if effective_authored_spans is None and source:
        try:
            _parsed_ast, effective_authored_spans = parse_stackvm_source_with_spans(source)
        except Exception:
            effective_authored_spans = None
    analyzer = _StackVmAnalyzer(include_host_words=include_host_words, source=source, authored_spans=effective_authored_spans)
    state = analyzer.analyze_nodes(ast, node_spans=effective_authored_spans)
    effect_kinds = sorted(kind for kind in state.effects if kind not in {"pure", "control"})
    host_surfaces_used = sorted(surface for surface in analyzer.host_surfaces if surface != "core")
    pocketcoder_host_words_used = sorted(analyzer.pocketcoder_host_words)
    return {
        "diagnostics": state.diagnostics,
        "diagnostic_count": len(state.diagnostics),
        "effect_kinds": effect_kinds,
        "host_surfaces_used": host_surfaces_used,
        "pocketcoder_host_words_used": pocketcoder_host_words_used,
        "standalone_script_compatible": len(pocketcoder_host_words_used) == 0,
        "max_stack_depth": state.max_stack_depth,
        "final_min_stack_depth": len(state.stack),
        "final_stack_shape": [value.kind for value in state.stack],
        "analysis_decisions": list(analyzer.analysis_decisions),
        "shape_flow": list(analyzer.shape_flow),
        "scope_summaries": list(analyzer.scope_summaries),
        "word_metadata_summary": {
            name: {
                "pops": metadata.stack_effect.pops,
                "pushes": metadata.stack_effect.pushes,
                "effect_kind": metadata.effect_kind,
                "output_shape": list(metadata.output_shape),
                "host_surface": metadata.host_surface,
                "definition_location": metadata.definition_span.span.location if isinstance(metadata.definition_span, StackVmAstSpan) else None,
            }
            for name, metadata in sorted(analyzer.user_words.items())
        },
    }


class _StackVmAnalyzer:
    def __init__(self, *, include_host_words: bool, source: str | None, authored_spans: list[StackVmAstSpan] | None):
        self.include_host_words = include_host_words
        self.source = source
        self.builtin_words = get_stackvm_word_metadata(include_host_words=include_host_words)
        self.user_words: dict[str, StackVmWordMetadata] = {}
        self.user_word_asts: dict[str, list[Any]] = {}
        self._inference_stack: set[str] = set()
        self.host_surfaces: set[str] = set()
        self.pocketcoder_host_words: set[str] = set()
        self.analysis_decisions: list[dict[str, Any]] = []
        self.shape_flow: list[dict[str, Any]] = []
        self.scope_summaries: list[dict[str, Any]] = []
        self._record_shape_flow = True
        self._symbol_tokens = [token for token in tokenize_stackvm_source(source or "") if token.raw not in {"[", "]"}]
        self._symbol_index = 0
        self._authored_symbol_spans = _flatten_ast_spans(authored_spans or [])
        self._authored_symbol_index = 0
        self._token_authored_spans: dict[tuple[int, int, int, int], StackVmAstSpan] = {}
        self._current_node_span: StackVmAstSpan | None = None

    def analyze_nodes(
        self,
        nodes: list[Any],
        *,
        initial_stack: list[_AbstractValue] | None = None,
        node_spans: list[StackVmAstSpan] | None = None,
        depth: int = 0,
        scope: str = "main",
        anchor_token: StackVmSourceToken | None = None,
        consume_tokens: bool = True,
        summary_extra: dict[str, Any] | None = None,
    ) -> _AnalysisState:
        state = _AnalysisState(stack=list(initial_stack or []))
        state.max_stack_depth = len(state.stack)
        for index, node in enumerate(nodes):
            node_span = node_spans[index] if node_spans and index < len(node_spans) else None
            self._analyze_node(node, state, depth=depth, scope=scope, consume_tokens=consume_tokens, node_span=node_span)
            state.max_stack_depth = max(state.max_stack_depth, len(state.stack))
        self._record_scope_summary(
            scope=scope,
            kind="region",
            input_stack=list(initial_stack or []),
            output_state=state,
            extra=summary_extra,
            token=anchor_token,
        )
        return state

    def _analyze_node(self, node: Any, state: _AnalysisState, *, depth: int, scope: str, consume_tokens: bool, node_span: StackVmAstSpan | None) -> None:
        previous_node_span = self._current_node_span
        self._current_node_span = node_span
        try:
            if isinstance(node, list):
                state.stack.append(_AbstractValue(kind="quotation", quotation=node, data=node_span))
                self._record_step(op="quotation", label="[ ... ]", depth=depth, scope=scope, state=state)
                return

            if not isinstance(node, tuple) or len(node) != 2:
                state.diagnostics.append(
                    {
                        "code": "dynamic-stack-shape",
                        "severity": "warning",
                        "message": f"Unsupported StackVM AST node {node!r}.",
                    }
                )
                self._record_step(op="unsupported", label=repr(node), depth=depth, scope=scope, state=state)
                return

            token_type, token_value = node
            if token_type in {"str", "int", "float", "bool", "none"}:
                state.stack.append(_AbstractValue(kind=token_type, literal=token_value, data=node_span))
                self._record_step(op="literal", label=repr(token_value), depth=depth, scope=scope, state=state)
                return
            if token_type != "sym":
                state.stack.append(_AbstractValue(kind="unknown", data=node_span))
                self._record_step(op="literal", label=str(token_value), depth=depth, scope=scope, state=state)
                return

            word_name = str(token_value)
            symbol_token = self._next_symbol_token(word_name) if consume_tokens else None
            if word_name == "define":
                self._analyze_define(state, symbol_token=symbol_token)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "call":
                self._analyze_call(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "dup":
                self._analyze_dup(state, symbol_token=symbol_token)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "swap":
                self._analyze_swap(state, symbol_token=symbol_token)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "over":
                self._analyze_over(state, symbol_token=symbol_token)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "yaml>":
                self._analyze_yaml_parse(state, symbol_token=symbol_token)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "dict-get":
                self._analyze_dict_get(state, symbol_token=symbol_token, safe_on_nondict=False)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "dict-get?":
                self._analyze_dict_get(state, symbol_token=symbol_token, safe_on_nondict=True)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "list-get":
                self._analyze_list_get(state, symbol_token=symbol_token, safe=False)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "list-get?":
                self._analyze_list_get(state, symbol_token=symbol_token, safe=True)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "get-in":
                self._analyze_get_in(state, symbol_token=symbol_token, safe=False)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "get-in?":
                self._analyze_get_in(state, symbol_token=symbol_token, safe=True)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "if":
                self._analyze_if(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "while":
                self._analyze_while(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "switch":
                self._analyze_switch(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "cond":
                self._analyze_cond(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "match":
                self._analyze_match(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "fallback":
                self._analyze_fallback(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "map":
                self._analyze_map(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "flat-map":
                self._analyze_flat_map(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "filter":
                self._analyze_filter(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "find":
                self._analyze_find(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "any?":
                self._analyze_any_all(state, symbol_token=symbol_token, depth=depth, scope=scope, word_name="any?")
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "all?":
                self._analyze_any_all(state, symbol_token=symbol_token, depth=depth, scope=scope, word_name="all?")
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "sort-by":
                self._analyze_sort_by(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "group-by":
                self._analyze_group_by(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "parallel-map":
                self._analyze_parallel_map(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return
            if word_name == "reduce":
                self._analyze_reduce(state, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return

            if word_name in self.user_word_asts:
                self._analyze_user_word_call(state, word_name=word_name, symbol_token=symbol_token, depth=depth, scope=scope)
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return

            metadata = self.builtin_words.get(word_name)
            if metadata is None:
                state.diagnostics.append(self._make_diagnostic("unknown-word-contract", "warning", f"No static contract is available for word '{word_name}'.", word=word_name, token=symbol_token))
                state.effects.add("control")
                self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
                return

            self._ensure_inputs(state, metadata.stack_effect.pops, word_name=word_name, token=symbol_token)
            self._pop_values(state, metadata.stack_effect.pops)
            if metadata.output_shape:
                for kind in metadata.output_shape:
                    state.stack.append(_AbstractValue(kind=kind))
            elif metadata.stack_effect.pushes is not None:
                for _ in range(metadata.stack_effect.pushes):
                    state.stack.append(_AbstractValue(kind="unknown"))
            state.effects.add(metadata.effect_kind)
            self.host_surfaces.add(metadata.host_surface)
            if metadata.host_surface == "pocketcoder_host":
                self.pocketcoder_host_words.add(word_name)
            self._record_step(op="word", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)
        finally:
            self._current_node_span = previous_node_span

    def _analyze_define(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 2, word_name="define", token=symbol_token)
        word_name_value = self._pop_value(state)
        quotation_value = self._pop_value(state)
        if quotation_value.kind != "quotation" or quotation_value.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "define expects a quotation before the word name.", word="define", token=symbol_token))
            return
        if word_name_value.kind != "str" or not str(word_name_value.literal or "").strip():
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "define expects a literal string word name.", word="define", token=symbol_token))
            return
        word_name = str(word_name_value.literal)
        self.user_word_asts[word_name] = quotation_value.quotation
        definition_span = quotation_value.data if isinstance(quotation_value.data, StackVmAstSpan) else None
        self.user_words[word_name] = self._infer_user_word(word_name, quotation_value.quotation, definition_span=definition_span)

    def _analyze_call(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 1, word_name="call", token=symbol_token)
        quotation_value = self._pop_value(state)
        if quotation_value.kind != "quotation" or quotation_value.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "call expects a quotation.", word="call", token=symbol_token))
            return
        called = self.analyze_nodes(
            quotation_value.quotation,
            initial_stack=list(state.stack),
            depth=depth + 1,
            scope=f"{scope} > call",
            anchor_token=symbol_token,
        )
        state.stack = called.stack
        state.effects.update(called.effects)
        state.diagnostics.extend(called.diagnostics)
        state.required_inputs = max(state.required_inputs, called.required_inputs)
        state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_dup(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 1, word_name="dup", token=symbol_token)
        value = self._pop_value(state)
        state.stack.append(_clone_abstract_value(value))
        state.stack.append(_clone_abstract_value(value))
        state.effects.add("pure")

    def _analyze_swap(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 2, word_name="swap", token=symbol_token)
        top = self._pop_value(state)
        below = self._pop_value(state)
        state.stack.append(_clone_abstract_value(top))
        state.stack.append(_clone_abstract_value(below))
        state.effects.add("pure")

    def _analyze_over(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 2, word_name="over", token=symbol_token)
        top = self._pop_value(state)
        below = self._pop_value(state)
        state.stack.append(_clone_abstract_value(below))
        state.stack.append(_clone_abstract_value(top))
        state.stack.append(_clone_abstract_value(below))
        state.effects.add("pure")

    def _analyze_yaml_parse(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 1, word_name="yaml>", token=symbol_token)
        value = self._pop_value(state)
        if value.kind == "str" and isinstance(value.literal, str):
            try:
                parsed = yaml.safe_load(value.literal)
            except Exception:
                state.stack.append(_AbstractValue(kind="unknown"))
            else:
                state.stack.append(_abstract_from_python_value(parsed))
        else:
            state.stack.append(_AbstractValue(kind="unknown"))
        state.effects.add("pure")

    def _analyze_dict_get(
        self,
        state: _AnalysisState,
        *,
        symbol_token: StackVmSourceToken | None,
        safe_on_nondict: bool,
    ) -> None:
        word_name = "dict-get?" if safe_on_nondict else "dict-get"
        self._ensure_inputs(state, 2, word_name=word_name, token=symbol_token)
        key = self._pop_value(state)
        mapping = self._pop_value(state)
        extracted = _lookup_dict_entry(mapping, key)
        if extracted is None:
            state.stack.append(_AbstractValue(kind="none", literal=None))
        else:
            state.stack.append(extracted)
        state.effects.add("pure")

    def _analyze_list_get(
        self,
        state: _AnalysisState,
        *,
        symbol_token: StackVmSourceToken | None,
        safe: bool,
    ) -> None:
        word_name = "list-get?" if safe else "list-get"
        self._ensure_inputs(state, 2, word_name=word_name, token=symbol_token)
        index = self._pop_value(state)
        container = self._pop_value(state)
        extracted = _lookup_list_entry(container, index, safe=safe)
        if extracted is None:
            state.stack.append(_AbstractValue(kind="none", literal=None))
        else:
            state.stack.append(extracted)
        state.effects.add("pure")

    def _analyze_get_in(
        self,
        state: _AnalysisState,
        *,
        symbol_token: StackVmSourceToken | None,
        safe: bool,
    ) -> None:
        word_name = "get-in?" if safe else "get-in"
        self._ensure_inputs(state, 2, word_name=word_name, token=symbol_token)
        path = self._pop_value(state)
        container = self._pop_value(state)
        extracted = _lookup_path_entry(container, path)
        if extracted is None:
            state.stack.append(_AbstractValue(kind="none", literal=None))
        else:
            state.stack.append(extracted)
        state.effects.add("pure")

    def _analyze_if(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="if", token=symbol_token)
        false_value = self._pop_value(state)
        true_value = self._pop_value(state)
        self._pop_value(state)
        branch_stack = list(state.stack)
        true_state = self._analyze_optional_quotation(true_value, branch_stack, word_name="if", depth=depth + 1, scope=f"{scope} > if:true", anchor_token=symbol_token)
        false_state = self._analyze_optional_quotation(false_value, branch_stack, word_name="if", depth=depth + 1, scope=f"{scope} > if:false", anchor_token=symbol_token)
        self._merge_branch_states(state, true_state, false_state)
        self._record_merge_summary(
            scope=f"{scope} > if:merge",
            input_stack=branch_stack,
            branch_states=[true_state, false_state],
            merged_stack=state.stack,
            extra={"reason": "conditional-branch-merge", "precision": "merged"},
            token=symbol_token,
        )

    def _analyze_user_word_call(
        self,
        state: _AnalysisState,
        *,
        word_name: str,
        symbol_token: StackVmSourceToken | None,
        depth: int,
        scope: str,
    ) -> None:
        metadata = self.user_words.get(word_name)
        quotation_ast = self.user_word_asts.get(word_name)
        if metadata is None or quotation_ast is None:
            state.diagnostics.append(
                self._make_diagnostic("unknown-word-contract", "warning", f"No static contract is available for word '{word_name}'.", word=word_name, token=symbol_token)
            )
            state.effects.add("control")
            return
        self._ensure_inputs(state, metadata.stack_effect.pops, word_name=word_name, token=symbol_token)
        called = self.analyze_nodes(
            quotation_ast,
            initial_stack=list(state.stack),
            node_spans=list(metadata.definition_span.children) if isinstance(metadata.definition_span, StackVmAstSpan) else None,
            depth=depth + 1,
            scope=f"{scope} > word:{word_name}",
            anchor_token=symbol_token,
            consume_tokens=False,
            summary_extra={"definition_location": metadata.definition_span.span.location} if isinstance(metadata.definition_span, StackVmAstSpan) else None,
        )
        state.stack = called.stack
        state.effects.update(called.effects)
        state.diagnostics.extend(called.diagnostics)
        state.required_inputs = max(state.required_inputs, called.required_inputs)
        state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_while(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="while", token=symbol_token)
        body_value = self._pop_value(state)
        condition_value = self._pop_value(state)
        loop_stack = list(state.stack)
        cond_state = self._analyze_optional_quotation(
            condition_value,
            loop_stack,
            word_name="while",
            depth=depth + 1,
            scope=f"{scope} > while:condition",
            anchor_token=symbol_token,
        )
        condition_shape_preserving = False
        if cond_state.stack:
            cond_state.stack.pop()
            condition_shape_preserving = _stacks_shape_compatible(cond_state.stack, loop_stack)
        else:
            cond_state.diagnostics.append(
                self._make_diagnostic("dynamic-stack-shape", "warning", "while condition quotation may not leave a boolean-like result.", word="while", token=symbol_token)
            )
        body_state = self._analyze_optional_quotation(
            body_value,
            cond_state.stack,
            word_name="while",
            depth=depth + 1,
            scope=f"{scope} > while:body",
            anchor_token=symbol_token,
        )
        state.effects.update(cond_state.effects | body_state.effects)
        state.diagnostics.extend(cond_state.diagnostics)
        state.diagnostics.extend(body_state.diagnostics)
        body_shape_preserving = _stacks_shape_compatible(body_state.stack, loop_stack)
        if condition_shape_preserving and body_shape_preserving:
            state.stack = list(loop_stack)
        else:
            state.diagnostics.append(
                self._make_diagnostic("dynamic-stack-shape", "warning", "while uses conservative stack analysis; final stack depth is approximate.", word="while", token=symbol_token)
            )
            state.stack = _merge_stacks(loop_stack, body_state.stack)
        state.max_stack_depth = max(state.max_stack_depth, cond_state.max_stack_depth, body_state.max_stack_depth)
        self._record_merge_summary(
            scope=f"{scope} > while:merge",
            input_stack=loop_stack,
            branch_states=[_AnalysisState(stack=list(loop_stack)), body_state],
            merged_stack=state.stack,
            extra={
                "reason": "shape-preserving-loop" if condition_shape_preserving and body_shape_preserving else "conservative-loop-merge",
                "precision": "precise" if condition_shape_preserving and body_shape_preserving else "conservative",
                "condition_shape_preserving": condition_shape_preserving,
                "body_shape_preserving": body_shape_preserving,
            },
            token=symbol_token,
        )

    def _analyze_switch(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="switch", token=symbol_token)
        cases_value = self._pop_value(state)
        self._pop_value(state)
        base_stack = list(state.stack)
        extracted_switch = _extract_switch_actions(cases_value.quotation)
        action_asts = extracted_switch["actions"]
        if not action_asts:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "switch cases could not be analyzed statically.", word="switch", token=symbol_token))
            return
        branch_states = [
            self.analyze_nodes(
                action_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                scope=f"{scope} > switch:case{index}",
                anchor_token=symbol_token,
            )
            for index, action_ast in enumerate(action_asts, start=1)
        ]
        if not extracted_switch["has_default"]:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
        self._merge_many_branch_states(state, branch_states)
        self._record_merge_summary(
            scope=f"{scope} > switch:merge",
            input_stack=base_stack,
            branch_states=branch_states,
            merged_stack=state.stack,
            extra={
                "has_default": extracted_switch["has_default"],
                "reason": "exhaustive-switch-merge" if extracted_switch["has_default"] else "optional-no-match-path",
                "precision": "merged" if extracted_switch["has_default"] else "optional-path",
            },
            token=symbol_token,
        )

    def _analyze_cond(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 1, word_name="cond", token=symbol_token)
        cases_value = self._pop_value(state)
        base_stack = list(state.stack)
        branch_pairs = _extract_case_pairs(cases_value.quotation)
        if not branch_pairs:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "cond cases could not be analyzed statically.", word="cond", token=symbol_token))
            return
        branch_states: list[_AnalysisState] = []
        has_default_branch = False
        for index, (condition_ast, action_ast) in enumerate(branch_pairs, start=1):
            if _condition_is_unconditional_true(condition_ast):
                has_default_branch = True
            cond_state = self.analyze_nodes(
                condition_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                scope=f"{scope} > cond:condition{index}",
                anchor_token=symbol_token,
            )
            if cond_state.stack:
                cond_state.stack.pop()
            else:
                cond_state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "cond condition quotation may not leave a result.", word="cond", token=symbol_token))
            action_state = self.analyze_nodes(
                action_ast,
                initial_stack=list(cond_state.stack),
                depth=depth + 1,
                scope=f"{scope} > cond:action{index}",
                anchor_token=symbol_token,
            )
            action_state.effects.update(cond_state.effects)
            action_state.diagnostics = list(cond_state.diagnostics) + list(action_state.diagnostics)
            branch_states.append(action_state)
        if not has_default_branch:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
        self._merge_many_branch_states(state, branch_states)
        self._record_merge_summary(
            scope=f"{scope} > cond:merge",
            input_stack=base_stack,
            branch_states=branch_states,
            merged_stack=state.stack,
            extra={
                "has_default_branch": has_default_branch,
                "reason": "exhaustive-cond-merge" if has_default_branch else "optional-no-match-path",
                "precision": "merged" if has_default_branch else "optional-path",
            },
            token=symbol_token,
        )

    def _analyze_fallback(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="fallback", token=symbol_token)
        fallback_value = self._pop_value(state)
        primary_value = self._pop_value(state)
        base_stack = list(state.stack)
        primary_state = self._analyze_optional_quotation(primary_value, base_stack, word_name="fallback", depth=depth + 1, scope=f"{scope} > fallback:primary", anchor_token=symbol_token)
        fallback_state = self._analyze_optional_quotation(fallback_value, base_stack, word_name="fallback", depth=depth + 1, scope=f"{scope} > fallback:fallback", anchor_token=symbol_token)
        self._merge_branch_states(state, primary_state, fallback_state)
        self._record_merge_summary(
            scope=f"{scope} > fallback:merge",
            input_stack=base_stack,
            branch_states=[primary_state, fallback_state],
            merged_stack=state.stack,
            extra={"reason": "fallback-recovery-merge", "precision": "merged"},
            token=symbol_token,
        )

    def _analyze_match(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="match", token=symbol_token)
        cases_value = self._pop_value(state)
        self._pop_value(state)
        base_stack = list(state.stack)
        branch_pairs = _extract_match_pairs(cases_value.quotation)
        if not branch_pairs:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "match cases could not be analyzed statically.", word="match", token=symbol_token))
            return
        branch_states: list[_AnalysisState] = []
        has_wildcard_branch = False
        for index, (pattern_node, action_ast) in enumerate(branch_pairs, start=1):
            if _case_is_match_wildcard(pattern_node):
                has_wildcard_branch = True
            action_state = self.analyze_nodes(
                action_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                scope=f"{scope} > match:case{index}",
                anchor_token=symbol_token,
            )
            branch_states.append(action_state)
        if not has_wildcard_branch:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
        self._merge_many_branch_states(state, branch_states)
        self._record_merge_summary(
            scope=f"{scope} > match:merge",
            input_stack=base_stack,
            branch_states=branch_states,
            merged_stack=state.stack,
            extra={
                "has_wildcard_branch": has_wildcard_branch,
                "reason": "exhaustive-match-merge" if has_wildcard_branch else "optional-no-match-path",
                "precision": "merged" if has_wildcard_branch else "optional-path",
            },
            token=symbol_token,
        )

    def _analyze_parallel_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="parallel-map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="parallel-map",
            depth=depth + 1,
            scope=f"{scope} > parallel-map:child",
            anchor_token=symbol_token,
        )
        illegal_effects = sorted(kind for kind in child_state.effects if kind not in {"pure", "control"})
        if illegal_effects:
            state.diagnostics.append(self._make_diagnostic("illegal-child-effect", "warning", "parallel-map child quotation may emit disallowed effects: " + ", ".join(illegal_effects) + ".", word="parallel-map", token=symbol_token, extra={"effect_kinds": illegal_effects}))
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="unknown"))

    def _analyze_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="map",
            depth=depth + 1,
            scope=f"{scope} > map:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="map", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="list"))

    def _analyze_flat_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="flat-map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="flat-map",
            depth=depth + 1,
            scope=f"{scope} > flat-map:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="flat-map", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="list"))

    def _analyze_filter(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="filter", token=symbol_token)
        quotation_value = self._pop_value(state)
        values = self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="filter",
            depth=depth + 1,
            scope=f"{scope} > filter:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="filter", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_clone_abstract_value(values if values.kind != "quotation" else _AbstractValue(kind="unknown")))

    def _analyze_find(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="find", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="find",
            depth=depth + 1,
            scope=f"{scope} > find:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="find", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="unknown"))

    def _analyze_any_all(
        self,
        state: _AnalysisState,
        *,
        symbol_token: StackVmSourceToken | None,
        depth: int,
        scope: str,
        word_name: str,
    ) -> None:
        self._ensure_inputs(state, 2, word_name=word_name, token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name=word_name,
            depth=depth + 1,
            scope=f"{scope} > {word_name}:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name=word_name, token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="bool"))

    def _analyze_sort_by(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="sort-by", token=symbol_token)
        quotation_value = self._pop_value(state)
        values = self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="sort-by",
            depth=depth + 1,
            scope=f"{scope} > sort-by:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="sort-by", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_clone_abstract_value(values if values.kind == "list" else _AbstractValue(kind="list")))

    def _analyze_group_by(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="group-by", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="group-by",
            depth=depth + 1,
            scope=f"{scope} > group-by:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="group-by", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="dict"))

    def _analyze_reduce(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="reduce", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown"), _AbstractValue(kind="unknown")],
            word_name="reduce",
            depth=depth + 1,
            scope=f"{scope} > reduce:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="reduce", token=symbol_token)
        if len(child_state.stack) < 1:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "reduce child quotation may not leave a next accumulator value.", word="reduce", token=symbol_token))
        elif len(child_state.stack) > 1:
            state.diagnostics.append(
                self._make_diagnostic(
                    "reduce-child-arity",
                    "warning",
                    "reduce child quotation should leave exactly one next accumulator value.",
                    word="reduce",
                    token=symbol_token,
                )
            )
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="unknown"))

    def _diagnose_illegal_child_effects(
        self,
        state: _AnalysisState,
        child_state: _AnalysisState,
        *,
        word_name: str,
        token: StackVmSourceToken | None,
    ) -> None:
        illegal_effects = sorted(kind for kind in child_state.effects if kind not in {"pure", "control"})
        if illegal_effects:
            state.diagnostics.append(
                self._make_diagnostic(
                    "illegal-child-effect",
                    "warning",
                    f"{word_name} child quotation may emit disallowed effects: " + ", ".join(illegal_effects) + ".",
                    word=word_name,
                    token=token,
                    extra={"effect_kinds": illegal_effects},
                )
            )

    def _infer_user_word(self, word_name: str, quotation_ast: list[Any], *, definition_span: StackVmAstSpan | None) -> StackVmWordMetadata:
        if word_name in self._inference_stack:
            return StackVmWordMetadata(word_name, StackVmStackEffect(0, None), "control", summary="recursive")
        self._inference_stack.add(word_name)
        try:
            previous_recording = self._record_shape_flow
            self._record_shape_flow = False
            inferred = self.analyze_nodes(
                quotation_ast,
                node_spans=list(definition_span.children) if isinstance(definition_span, StackVmAstSpan) else None,
                scope=f"infer:{word_name}",
                consume_tokens=False,
            )
            effect_kind = _primary_effect_kind(inferred.effects)
            return StackVmWordMetadata(
                word_name,
                StackVmStackEffect(inferred.required_inputs, len(inferred.stack)),
                effect_kind,
                output_shape=tuple(value.kind for value in inferred.stack),
                host_surface="core",
                definition_span=definition_span,
            )
        finally:
            self._record_shape_flow = previous_recording
            self._inference_stack.discard(word_name)

    def _analyze_optional_quotation(
        self,
        value: _AbstractValue,
        initial_stack: list[_AbstractValue],
        *,
        word_name: str,
        depth: int,
        scope: str,
        anchor_token: StackVmSourceToken | None = None,
    ) -> _AnalysisState:
        if value.kind != "quotation" or value.quotation is None:
            state = _AnalysisState(stack=list(initial_stack))
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", f"{word_name} expects quotation operands for static analysis.", word=word_name))
            return state
        return self.analyze_nodes(value.quotation, initial_stack=list(initial_stack), depth=depth, scope=scope, anchor_token=anchor_token)

    def _merge_branch_states(self, state: _AnalysisState, first: _AnalysisState, second: _AnalysisState) -> None:
        self._merge_many_branch_states(state, [first, second])

    def _merge_many_branch_states(self, state: _AnalysisState, branches: list[_AnalysisState]) -> None:
        if not branches:
            return
        merged_stack = list(branches[0].stack)
        merged_effects: set[str] = set()
        merged_diagnostics: list[dict[str, Any]] = []
        max_depth = state.max_stack_depth
        required_inputs = state.required_inputs
        for branch in branches:
            merged_stack = _merge_stacks(merged_stack, branch.stack)
            merged_effects.update(branch.effects)
            merged_diagnostics.extend(branch.diagnostics)
            max_depth = max(max_depth, branch.max_stack_depth)
            required_inputs = max(required_inputs, branch.required_inputs)
        state.stack = merged_stack
        state.effects.update(merged_effects)
        state.diagnostics.extend(merged_diagnostics)
        state.max_stack_depth = max_depth
        state.required_inputs = required_inputs

    def _ensure_inputs(self, state: _AnalysisState, count: int, *, word_name: str, token: StackVmSourceToken | None = None) -> None:
        if len(state.stack) >= count:
            return
        deficit = count - len(state.stack)
        state.required_inputs += deficit
        state.stack = [_AbstractValue(kind="unknown") for _ in range(deficit)] + state.stack
        state.diagnostics.append(self._make_diagnostic("stack-underflow", "error", f"Word '{word_name}' requires {count} stack values but only {count - deficit} are guaranteed here.", word=word_name, token=token))

    def _pop_values(self, state: _AnalysisState, count: int) -> list[_AbstractValue]:
        return [self._pop_value(state) for _ in range(count)]

    def _pop_value(self, state: _AnalysisState) -> _AbstractValue:
        if not state.stack:
            return _AbstractValue(kind="unknown")
        return state.stack.pop()

    def _next_symbol_token(self, raw: str) -> StackVmSourceToken | None:
        while self._symbol_index < len(self._symbol_tokens):
            token = self._symbol_tokens[self._symbol_index]
            self._symbol_index += 1
            authored_span = None
            if self._authored_symbol_index < len(self._authored_symbol_spans):
                authored_span = self._authored_symbol_spans[self._authored_symbol_index]
            self._authored_symbol_index += 1
            if authored_span is not None:
                self._token_authored_spans[_token_key(token)] = authored_span
            if token.raw == raw:
                return token
        return None

    def _make_diagnostic(
        self,
        code: str,
        severity: str,
        message: str,
        *,
        word: str | None = None,
        token: StackVmSourceToken | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        diagnostic: dict[str, Any] = {
            "code": code,
            "severity": severity,
            "message": message,
        }
        if word:
            diagnostic["word"] = word
        if token is not None:
            diagnostic["location"] = _format_token_location(token)
            diagnostic["span"] = {
                "start_line": token.line,
                "start_column": token.column,
                "end_line": token.end_line,
                "end_column": token.end_column,
            }
            authored_span = self._token_authored_spans.get(_token_key(token))
            if authored_span is not None:
                diagnostic["authored_location"] = authored_span.span.location
                diagnostic["authored_span"] = {
                    "start_line": authored_span.span.start_line,
                    "start_column": authored_span.span.start_column,
                    "end_line": authored_span.span.end_line,
                    "end_column": authored_span.span.end_column,
                }
        self._record_authored_fallback(diagnostic, token)
        if extra:
            diagnostic.update(extra)
        return diagnostic

    def _record_authored_fallback(self, payload: dict[str, Any], token: StackVmSourceToken | None = None) -> None:
        if token is not None or self._current_node_span is None:
            return
        payload.setdefault("authored_location", self._current_node_span.span.location)
        payload.setdefault(
            "authored_span",
            {
                "start_line": self._current_node_span.span.start_line,
                "start_column": self._current_node_span.span.start_column,
                "end_line": self._current_node_span.span.end_line,
                "end_column": self._current_node_span.span.end_column,
            },
        )

    def _record_step(
        self,
        *,
        op: str,
        label: str,
        depth: int,
        scope: str,
        state: _AnalysisState,
        token: StackVmSourceToken | None = None,
    ) -> None:
        if not self._record_shape_flow:
            return
        step: dict[str, Any] = {
            "op": op,
            "label": label,
            "depth": depth,
            "scope": scope,
            "stack_shape": [value.kind for value in state.stack],
        }
        if token is not None:
            step["location"] = _format_token_location(token)
            authored_span = self._token_authored_spans.get(_token_key(token))
            if authored_span is not None:
                step["authored_location"] = authored_span.span.location
        self._record_authored_fallback(step, token)
        self.shape_flow.append(step)

    def _record_scope_summary(
        self,
        *,
        scope: str,
        kind: str,
        input_stack: list[_AbstractValue],
        output_state: _AnalysisState,
        extra: dict[str, Any] | None = None,
        token: StackVmSourceToken | None = None,
    ) -> None:
        if not self._record_shape_flow:
            return
        summary: dict[str, Any] = {
            "scope": scope,
            "kind": kind,
            "input_stack_shape": [value.kind for value in input_stack],
            "output_stack_shape": [value.kind for value in output_state.stack],
            "effect_kinds": sorted(kind for kind in output_state.effects if kind not in {"pure", "control"}),
            "diagnostic_count": len(output_state.diagnostics),
            "unknown_output_count": sum(1 for value in output_state.stack if value.kind == "unknown"),
            "shape_preserved": _stacks_shape_compatible(list(input_stack), output_state.stack),
        }
        if token is not None:
            summary["location"] = _format_token_location(token)
            authored_span = self._token_authored_spans.get(_token_key(token))
            if authored_span is not None:
                summary["authored_location"] = authored_span.span.location
        if extra:
            summary.update(extra)
        self.scope_summaries.append(summary)
        if summary["unknown_output_count"] > 0:
            self._record_decision(
                scope=scope,
                category="precision",
                reason="unknown-output-shape",
                detail=f"Scope leaves {summary['unknown_output_count']} unknown stack value(s).",
                severity="info",
                token=token,
            )

    def _record_merge_summary(
        self,
        *,
        scope: str,
        input_stack: list[_AbstractValue],
        branch_states: list[_AnalysisState],
        merged_stack: list[_AbstractValue],
        extra: dict[str, Any] | None = None,
        token: StackVmSourceToken | None = None,
    ) -> None:
        if not self._record_shape_flow:
            return
        summary: dict[str, Any] = {
            "scope": scope,
            "kind": "merge",
            "input_stack_shape": [value.kind for value in input_stack],
            "branch_output_shapes": [[value.kind for value in branch.stack] for branch in branch_states],
            "merged_stack_shape": [value.kind for value in merged_stack],
            "branch_count": len(branch_states),
            "unknown_output_count": sum(1 for value in merged_stack if value.kind == "unknown"),
        }
        if token is not None:
            summary["location"] = _format_token_location(token)
            authored_span = self._token_authored_spans.get(_token_key(token))
            if authored_span is not None:
                summary["authored_location"] = authored_span.span.location
        if extra:
            summary.update(extra)
        self.scope_summaries.append(summary)
        reason = str(summary.get("reason") or "branch-merge")
        precision = str(summary.get("precision") or "merged")
        severity = "warning" if precision == "conservative" else "info"
        if reason == "optional-no-match-path":
            detail = "Analyzer kept an explicit path where no branch matched."
        elif reason == "shape-preserving-loop":
            detail = "Loop condition and body preserved stack shape, so the loop summary stayed precise."
        elif reason == "conservative-loop-merge":
            detail = "Loop body changed stack shape, so the analyzer fell back to a conservative merge."
        elif reason == "fallback-recovery-merge":
            detail = "Analyzer merged the primary path with the fallback recovery path."
        else:
            detail = "Analyzer merged multiple branch outcomes into one parent stack shape."
        if summary["unknown_output_count"] > 0:
            detail += f" Merged result includes {summary['unknown_output_count']} unknown stack value(s)."
        self._record_decision(
            scope=scope,
            category="merge",
            reason=reason,
            detail=detail,
            severity=severity,
            token=token,
        )

    def _record_decision(
        self,
        *,
        scope: str,
        category: str,
        reason: str,
        detail: str,
        severity: str,
        token: StackVmSourceToken | None = None,
    ) -> None:
        if not self._record_shape_flow:
            return
        decision = {
            "scope": scope,
            "category": category,
            "reason": reason,
            "detail": detail,
            "severity": severity,
        }
        if token is not None:
            decision["location"] = _format_token_location(token)
            authored_span = self._token_authored_spans.get(_token_key(token))
            if authored_span is not None:
                decision["authored_location"] = authored_span.span.location
        self.analysis_decisions.append(decision)


def _merge_stacks(left: list[_AbstractValue], right: list[_AbstractValue]) -> list[_AbstractValue]:
    merged: list[_AbstractValue] = []
    for left_value, right_value in zip(left, right):
        if left_value.kind == right_value.kind and left_value.literal == right_value.literal:
            merged.append(
                _AbstractValue(
                    kind=left_value.kind,
                    literal=left_value.literal,
                    quotation=left_value.quotation,
                    data=left_value.data,
                )
            )
        else:
            merged.append(_AbstractValue(kind="unknown"))
    return merged


def _stacks_equivalent(left: list[_AbstractValue], right: list[_AbstractValue]) -> bool:
    if len(left) != len(right):
        return False
    return all(
        left_value.kind == right_value.kind and left_value.literal == right_value.literal
        for left_value, right_value in zip(left, right)
    )


def _clone_abstract_value(value: _AbstractValue) -> _AbstractValue:
    return _AbstractValue(kind=value.kind, literal=value.literal, quotation=value.quotation, data=value.data)


def _stacks_shape_compatible(left: list[_AbstractValue], right: list[_AbstractValue]) -> bool:
    if len(left) != len(right):
        return False
    return all(_values_shape_compatible(left_value, right_value) for left_value, right_value in zip(left, right))


def _values_shape_compatible(left: _AbstractValue, right: _AbstractValue) -> bool:
    if left.kind == right.kind:
        return True
    if left.kind == "unknown" or right.kind == "unknown":
        return True
    return False


def _abstract_from_python_value(value: Any) -> _AbstractValue:
    if value is None:
        return _AbstractValue(kind="none", literal=None, data=None)
    if isinstance(value, bool):
        return _AbstractValue(kind="bool", literal=value, data=value)
    if isinstance(value, int) and not isinstance(value, bool):
        return _AbstractValue(kind="int", literal=value, data=value)
    if isinstance(value, float):
        return _AbstractValue(kind="float", literal=value, data=value)
    if isinstance(value, str):
        return _AbstractValue(kind="str", literal=value, data=value)
    if isinstance(value, list):
        return _AbstractValue(kind="list", data=value)
    if isinstance(value, dict):
        return _AbstractValue(kind="dict", data=value)
    return _AbstractValue(kind="unknown")


def _lookup_dict_entry(mapping: _AbstractValue, key: _AbstractValue) -> _AbstractValue | None:
    if mapping.kind != "dict" or not isinstance(mapping.data, dict):
        return None
    lookup_key = key.literal if key.kind in {"str", "int", "float", "bool", "none"} else key.data
    if lookup_key not in mapping.data:
        return None
    return _abstract_from_python_value(mapping.data.get(lookup_key))


def _lookup_list_entry(container: _AbstractValue, index: _AbstractValue, *, safe: bool) -> _AbstractValue | None:
    if container.kind != "list" or not isinstance(container.data, list):
        return None
    if index.kind != "int" or not isinstance(index.literal, int):
        return None
    if index.literal < 0 or index.literal >= len(container.data):
        return None
    return _abstract_from_python_value(container.data[index.literal])


def _lookup_path_entry(container: _AbstractValue, path: _AbstractValue) -> _AbstractValue | None:
    segments = _normalize_lookup_path(path)
    if segments is None:
        return None
    current = container.data if container.kind in {"dict", "list", "str", "int", "float", "bool", "none"} else None
    if current is None and container.kind not in {"dict", "list"}:
        current = container.literal
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue
        if isinstance(current, list):
            if not isinstance(segment, int) or segment < 0 or segment >= len(current):
                return None
            current = current[segment]
            continue
        return None
    return _abstract_from_python_value(current)


def _normalize_lookup_path(path: _AbstractValue) -> list[Any] | None:
    raw = path.literal if path.kind in {"str", "int"} else path.data
    if isinstance(raw, int):
        return [raw]
    if not isinstance(raw, str):
        return None
    parts: list[Any] = []
    for segment in raw.split("."):
        if segment == "":
            return None
        if segment.isdigit():
            parts.append(int(segment))
        else:
            parts.append(segment)
    return parts


def _extract_case_pairs(cases_ast: list[Any] | None) -> list[tuple[list[Any], list[Any]]]:
    if not isinstance(cases_ast, list) or len(cases_ast) % 2 != 0:
        return []
    pairs: list[tuple[list[Any], list[Any]]] = []
    for index in range(0, len(cases_ast), 2):
        condition_ast = cases_ast[index]
        action_ast = cases_ast[index + 1]
        if not isinstance(condition_ast, list) or not isinstance(action_ast, list):
            return []
        pairs.append((condition_ast, action_ast))
    return pairs


def _extract_match_pairs(cases_ast: list[Any] | None) -> list[tuple[Any, list[Any]]]:
    if not isinstance(cases_ast, list) or len(cases_ast) % 2 != 0:
        return []
    pairs: list[tuple[Any, list[Any]]] = []
    for index in range(0, len(cases_ast), 2):
        pattern_node = cases_ast[index]
        action_ast = cases_ast[index + 1]
        if not isinstance(action_ast, list):
            return []
        pairs.append((pattern_node, action_ast))
    return pairs


def _case_is_match_wildcard(case_node: Any) -> bool:
    if isinstance(case_node, tuple) and len(case_node) == 2:
        token_type, token_value = case_node
        if token_type == "sym":
            return str(token_value) == "_"
        return token_type == "str" and str(token_value) == "_"
    if isinstance(case_node, list) and len(case_node) == 1 and isinstance(case_node[0], tuple):
        token_type, token_value = case_node[0]
        if token_type == "sym":
            return str(token_value) == "_"
        return token_type == "str" and str(token_value) == "_"
    return False


def _extract_switch_actions(cases_ast: list[Any] | None) -> dict[str, Any]:
    if not isinstance(cases_ast, list) or len(cases_ast) % 2 != 0:
        return {"actions": [], "has_default": False}
    actions: list[list[Any]] = []
    has_default = False
    for index in range(1, len(cases_ast), 2):
        case_node = cases_ast[index - 1]
        action_ast = cases_ast[index]
        if not isinstance(action_ast, list):
            return {"actions": [], "has_default": False}
        if _case_is_default(case_node):
            has_default = True
        actions.append(action_ast)
    return {"actions": actions, "has_default": has_default}


def _primary_effect_kind(effects: set[str]) -> EffectKind:
    for kind in ("final", "handoff", "tool", "prompt", "llm", "state", "control", "pure"):
        if kind in effects:
            return kind
    return "pure"


def _case_is_default(node: Any) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] == "str" and node[1] == "default"


def _condition_is_unconditional_true(condition_ast: list[Any]) -> bool:
    return len(condition_ast) == 1 and isinstance(condition_ast[0], tuple) and condition_ast[0] == ("bool", True)


def _format_token_location(token: StackVmSourceToken) -> str:
    if token.line == token.end_line:
        if token.column == token.end_column:
            return f"line {token.line}, col {token.column}"
        return f"line {token.line}, cols {token.column}-{token.end_column}"
    return f"line {token.line}, col {token.column} to line {token.end_line}, col {token.end_column}"


def _flatten_ast_spans(spans: list[StackVmAstSpan]) -> list[StackVmAstSpan]:
    flattened: list[StackVmAstSpan] = []
    for span in spans:
        if span.children:
            flattened.extend(_flatten_ast_spans(list(span.children)))
        else:
            flattened.append(span)
    return flattened


def _token_key(token: StackVmSourceToken) -> tuple[int, int, int, int]:
    return (token.line, token.column, token.end_line, token.end_column)
