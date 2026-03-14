from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from pocketcode.core.stackvm_parser import StackVmAstSpan, StackVmSourceToken, parse_stackvm_source_with_spans, tokenize_stackvm_source


EffectKind = Literal["pure", "state", "tool", "prompt", "handoff", "final", "llm", "control"]
HostSurface = Literal["core", "portable_host", "pocketcoder_host"]

_VALID_WORKFLOW_SPEC_KEYS = {
    "payload_file", "delegate_target", "missing_case", "kind",
    "prompt_prefix", "value_path", "options", "attrs",
    "match_mode", "prepare_expr", "continue_rules", "caller_value_expr",
    "caller_field_specs", "caller_rules", "delegate_base_expr", "delegate_rules",
    "role", "policy"
}

_VALID_WORKFLOW_FAMILY_SECTIONS = {
    "shared", "router.continue", "caller.answer", "caller.route", 
    "caller.finalize", "delegate.answer", "delegate.route", "delegate.finalize"
}


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
    explicit_signature: tuple[list[str], list[str]] | None = None


@dataclass
class _AbstractValue:
    kind: str
    literal: Any = None
    quotation: list[Any] | None = None
    data: Any = None
    keys: dict[str, str] | None = None
    enums: dict[str, list[Any]] | None = None
    enum_values: list[Any] | None = None

    def clone(self) -> "_AbstractValue":
        return _AbstractValue(
            kind=self.kind,
            literal=self.literal,
            quotation=self.quotation,
            data=self.data,
            keys=dict(self.keys) if self.keys is not None else None,
            enums=dict(self.enums) if self.enums is not None else None,
            enum_values=list(self.enum_values) if self.enum_values is not None else None,
        )


@dataclass
class _AnalysisState:
    stack: list[_AbstractValue] = field(default_factory=list)
    effects: set[str] = field(default_factory=set)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    required_inputs: int = 0
    max_stack_depth: int = 0

    def clone(self) -> _AnalysisState:
        return _AnalysisState(
            stack=[value.clone() for value in self.stack],
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
        "final_stack_shape": [analyzer._summarize_value_for_display(value) for value in state.stack],
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
                "explicit_signature": metadata.explicit_signature,
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
        if_nesting_depth: int = 0,
        scope: str = "root",
        anchor_token: StackVmSourceToken | None = None,
        consume_tokens: bool = True,
        summary_extra: dict[str, Any] | None = None,
    ) -> _AnalysisState:
        state = _AnalysisState(
            stack=list(initial_stack or []),
            required_inputs=0,
            effects=set(),
            diagnostics=[],
            max_stack_depth=len(initial_stack or []),
        )

        has_if = any(self._is_symbol(node, "if") for node in nodes)
        if if_nesting_depth >= 2 and has_if:
            state.diagnostics.append(self._make_diagnostic(
                "nested-if-smell", "warning",
                "StackVM source uses deeply nested 'if' structures (> 2 levels). Consider using 'cond', 'switch', or 'match' for better readability.",
                token=anchor_token
            ))

        # Check for other stylistic smells
        self._check_stylistic_smells(nodes, state, anchor_token)

        previous_node_span = self._current_node_span
        try:
            for i, node in enumerate(nodes):
                self._current_node_span = node_spans[i] if node_spans and i < len(node_spans) else None
                
                # Update next level depth
                next_if_depth = if_nesting_depth + 1 if has_if else if_nesting_depth
                
                self._analyze_node(
                    node,
                    state,
                    depth=depth,
                    if_nesting_depth=next_if_depth,
                    scope=scope,
                    consume_tokens=consume_tokens,
                )
                state.max_stack_depth = max(state.max_stack_depth, len(state.stack))
        finally:
            self._current_node_span = previous_node_span

        self._record_scope_summary(
            scope=scope,
            kind="nodes",
            input_stack=initial_stack or [],
            output_state=state,
            extra=summary_extra,
            token=anchor_token,
        )
        return state

    def _matches_manual_dict_chain(self, nodes: list[Any], start_index: int) -> bool:
        """Detects repetitive manual dict-get patterns that should use project-fields."""
        if start_index + 2 >= len(nodes):
            return False
        
        # Pattern: dup "key" dict-get?
        return (
            self._is_symbol(nodes[start_index], "dup") and
            isinstance(nodes[start_index + 1], tuple) and nodes[start_index + 1][0] == "str" and
            (self._is_symbol(nodes[start_index + 2], "dict-get") or self._is_symbol(nodes[start_index + 2], "dict-get?"))
        )

    def _matches_manual_tool_loop(self, nodes: list[Any], start_index: int) -> bool:
        if start_index + 4 >= len(nodes):
            return False

        if not self._is_symbol(nodes[start_index], "last-tool-result"):
            return False
        if not self._is_symbol(nodes[start_index + 1], "none?"):
            return False

        request_branch = nodes[start_index + 2]
        later_branch = nodes[start_index + 3]
        if_node = nodes[start_index + 4]
        if not isinstance(request_branch, list) or not isinstance(later_branch, list):
            return False
        if not self._is_symbol(if_node, "if"):
            return False
        return self._contains_symbol(request_branch, "tool-request")

    def _matches_manual_prompt_route(self, nodes: list[Any], start_index: int) -> bool:
        if start_index + 3 >= len(nodes):
            return False

        request_expr = nodes[start_index]
        interaction_word = nodes[start_index + 1]
        cases = nodes[start_index + 2]
        switch_word = nodes[start_index + 3]

        if self._is_symbol(request_expr, "prompt-interaction"):
            return False
        if not self._is_symbol(interaction_word, "prompt-interaction"):
            return False
        if not isinstance(cases, list):
            return False
        return self._is_symbol(switch_word, "switch")

    def _contains_symbol(self, node: Any, symbol_name: str) -> bool:
        if self._is_symbol(node, symbol_name):
            return True
        if isinstance(node, list):
            return any(self._contains_symbol(item, symbol_name) for item in node)
        return False

    def _is_symbol(self, node: Any, symbol_name: str) -> bool:
        return isinstance(node, tuple) and len(node) == 2 and node[0] == "sym" and str(node[1]) == symbol_name
    def _check_stylistic_smells(self, nodes: list[Any], state: _AnalysisState, anchor_token: StackVmSourceToken | None) -> None:
        """Checks for various stylistic code smells in a list of nodes."""
        found_codes = set()
        for i in range(len(nodes)):
            if self._matches_manual_tool_loop(nodes, i):
                if "manual-tool-loop" not in found_codes:
                    state.diagnostics.append(self._make_diagnostic(
                        "manual-tool-loop", "warning",
                        "StackVM source uses the manual 'last-tool-result none?' tool loop pattern. Prefer the built-in 'tool-once' macro for tool-first flows.",
                        token=anchor_token
                    ))
                    found_codes.add("manual-tool-loop")
            
            if self._matches_manual_prompt_route(nodes, i):
                if "manual-prompt-route" not in found_codes:
                    state.diagnostics.append(self._make_diagnostic(
                        "manual-prompt-route", "warning",
                        "StackVM source uses the manual 'prompt-interaction' plus 'switch' routing pattern. Prefer the built-in 'prompt-route' macro for exact-match interaction routing.",
                        token=anchor_token
                    ))
                    found_codes.add("manual-prompt-route")
            
            if self._matches_manual_dict_chain(nodes, i):
                # Trigger warning if pattern found repeatedly in this block
                if sum(1 for j in range(len(nodes)) if self._matches_manual_dict_chain(nodes, j)) >= 2:
                    if "manual-dict-get-chain" not in found_codes:
                        state.diagnostics.append(self._make_diagnostic(
                            "manual-dict-get-chain", "warning",
                            "StackVM source uses repetitive manual 'dict-get' calls. Consider using the 'project-fields' or 'project-shared' macros to normalize state.",
                            token=anchor_token
                        ))
                        found_codes.add("manual-dict-get-chain")

    def _analyze_node(
        self,
        node: Any,
        state: _AnalysisState,
        *,
        depth: int,
        if_nesting_depth: int = 0,
        scope: str,
        consume_tokens: bool = True,
    ) -> None:
        if isinstance(node, list):
            # Recurse into nested quotation
            # We don't advance the global token pointer for list literals usually,
            # but they might be analyzed as quoted code.
            state.stack.append(_AbstractValue(kind="quotation", quotation=node, data=self._current_node_span))
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
            state.stack.append(_AbstractValue(kind=token_type, literal=token_value, data=self._current_node_span))
            self._record_step(op="literal", label=repr(token_value), depth=depth, scope=scope, state=state)
            return
        if token_type == "sig":
            state.stack.append(_AbstractValue(kind="sig", data=token_value))
            self._record_step(op="sig", label="( ... )", depth=depth, scope=scope, state=state)
            return
        if token_type != "sym":
            state.stack.append(_AbstractValue(kind="unknown", data=self._current_node_span))
            self._record_step(op="literal", label=str(token_value), depth=depth, scope=scope, state=state)
            return

        word_name = str(token_value)
        symbol_token = self._next_symbol_token(word_name) if consume_tokens else None
        
        self._record_step(op="call", label=word_name, depth=depth, scope=scope, state=state, token=symbol_token)

        if word_name == "define":
            self._analyze_define(state, symbol_token=symbol_token)
        elif word_name == "call":
            self._analyze_call(state, symbol_token=symbol_token, depth=depth, scope=scope)
        elif word_name == "dup":
            self._analyze_dup(state, symbol_token=symbol_token)
        elif word_name == "swap":
            self._analyze_swap(state, symbol_token=symbol_token)
        elif word_name == "over":
            self._analyze_over(state, symbol_token=symbol_token)
        elif word_name == "yaml>":
            self._analyze_yaml_parse(state, symbol_token=symbol_token)
        elif word_name == "dict-get":
            self._analyze_dict_get(state, symbol_token=symbol_token, safe_on_nondict=False)
        elif word_name == "dict-get?":
            self._analyze_dict_get(state, symbol_token=symbol_token, safe_on_nondict=True)
        elif word_name == "list-get":
            self._analyze_list_get(state, symbol_token=symbol_token, safe=False)
        elif word_name == "list-get?":
            self._analyze_list_get(state, symbol_token=symbol_token, safe=True)
        elif word_name == "get-in":
            self._analyze_get_in(state, symbol_token=symbol_token, safe=False)
        elif word_name == "get-in?":
            self._analyze_get_in(state, symbol_token=symbol_token, safe=True)
        elif word_name == "if":
            self._analyze_if(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "while":
            self._analyze_while(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "switch":
            self._analyze_switch(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "cond":
            self._analyze_cond(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "match":
            self._analyze_match(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "fallback":
            self._analyze_fallback(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "map":
            self._analyze_map(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "flat-map":
            self._analyze_flat_map(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "filter":
            self._analyze_filter(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "find":
            self._analyze_find(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "any?":
            self._analyze_any_all(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope, word_name="any?")
        elif word_name == "all?":
            self._analyze_any_all(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope, word_name="all?")
        elif word_name == "sort-by":
            self._analyze_sort_by(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "group-by":
            self._analyze_group_by(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "schema-check":
            self._analyze_schema_word(state, word_name=word_name, symbol_token=symbol_token)
        elif word_name == "schema-apply":
            self._analyze_schema_word(state, word_name=word_name, symbol_token=symbol_token)
        elif word_name == "validated-match":
            self._analyze_validated_match(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "schema-route":
            self._analyze_schema_route(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "project-fields":
            self._analyze_project_fields(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "project-shared":
            self._analyze_project_shared(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "handoff-rules":
            self._analyze_handoff_rules(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "handoff-switch":
            self._analyze_handoff_switch(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "prompt-route":
            self._analyze_prompt_route(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "prompt-store":
            self._analyze_prompt_store(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "prompt-store-text":
            self._analyze_prompt_store_text(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "ask-from":
            self._analyze_ask_from(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "stdlib.io.read-file-once" or word_name == "stdlib.io.read-yaml-file-once":
            self._analyze_stdlib_io_read_once(state, word_name=word_name, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name.startswith("define-choice-") or word_name.startswith("define-workflow-") or word_name.startswith("extend-workflow-"):
            self._analyze_workflow_builder(state, word_name=word_name, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name in {"use-workflow-spec", "use-workflow-family"}:
            self._analyze_workflow_usage(state, word_name=word_name, symbol_token=symbol_token, depth=depth, scope=scope)
        elif word_name == "workflow-spec":
            self._analyze_workflow_spec_inline(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name in {
            "answer-workflow-contract", "route-workflow-contract", 
            "finalize-workflow-contract", "continue-workflow-contract"
        }:
            self._analyze_workflow_contract_direct(state, word_name=word_name, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "return-flow":
            self._analyze_return_flow(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "return-answer-flow":
            self._analyze_return_answer_flow(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name in {
            "return-field-route-flow", "return-field-finalize-flow", "return-field-policy-flow",
            "return-policy-flow", "return-contract-flow", "normalized-return-flow"
        }:
            self._analyze_complex_return_flow(state, word_name=word_name, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name in {"stdlib.config.tool-content-yaml", "stdlib.normalize.tool-content-yaml"}:
            self._analyze_stdlib_simple_state_op(state, word_name=word_name, pops=0, pushes=1, symbol_token=symbol_token)
        elif word_name in {"stdlib.config.tool-content-schema-check", "stdlib.config.tool-content-schema-apply"}:
            self._analyze_stdlib_simple_state_op(state, word_name=word_name, pops=1, pushes=1, symbol_token=symbol_token)
        elif word_name in {"stdlib.normalize.normalize-item-titles", "stdlib.normalize.store-normalized-source", "stdlib.normalize.store-normalized-enabled"}:
            self._analyze_stdlib_simple_state_op(state, word_name=word_name, pops=1, pushes=0, symbol_token=symbol_token)
        elif word_name == "stdlib.normalize.store-normalized-summary":
            self._analyze_stdlib_simple_state_op(state, word_name=word_name, pops=0, pushes=1, symbol_token=symbol_token)
        elif word_name == "stdlib.normalize.format-selected-actions":
            self._analyze_stdlib_simple_state_op(state, word_name=word_name, pops=1, pushes=2, symbol_token=symbol_token)
        elif word_name == "record-fields":
            self._analyze_record_fields(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "parallel-map":
            self._analyze_parallel_map(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name == "reduce":
            self._analyze_reduce(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        elif word_name in self.user_word_asts:
            self._analyze_user_word_call(state, word_name=word_name, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)
        else:
            metadata = self.builtin_words.get(word_name)
            if metadata is None:
                state.diagnostics.append(self._make_diagnostic("unknown-word-contract", "warning", f"No static contract is available for word '{word_name}'.", word=word_name, token=symbol_token))
                state.effects.add("control")
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

    def _analyze_define(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None) -> None:
        if len(state.stack) >= 2 and state.stack[-2].kind == "sig":
            self._ensure_inputs(state, 3, word_name="define", token=symbol_token)
            word_name_value = self._pop_value(state)
            sig_value = self._pop_value(state)
            quotation_value = self._pop_value(state)
            signature_ast = sig_value.data
        else:
            self._ensure_inputs(state, 2, word_name="define", token=symbol_token)
            word_name_value = self._pop_value(state)
            quotation_value = self._pop_value(state)
            signature_ast = None

        if quotation_value.kind != "quotation" or quotation_value.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "define expects a quotation before the word name.", word="define", token=symbol_token))
            return
        if word_name_value.kind != "str" or not str(word_name_value.literal or "").strip():
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "define expects a literal string word name.", word="define", token=symbol_token))
            return
        word_name = str(word_name_value.literal)
        self.user_word_asts[word_name] = quotation_value.quotation
        definition_span = quotation_value.data if isinstance(quotation_value.data, StackVmAstSpan) else None
        
        explicit_sig = _parse_explicit_signature(signature_ast) if signature_ast else None
        
        self.user_words[word_name] = self._infer_user_word(
            word_name, 
            quotation_value.quotation, 
            definition_span=definition_span,
            explicit_sig=explicit_sig,
            symbol_token=symbol_token,
            call_state=state,
        )

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
        
        if mapping.keys is not None and key.kind == "str" and isinstance(key.literal, str):
            if key.literal not in mapping.keys:
                state.diagnostics.append(self._make_diagnostic(
                    "unknown-dict-key",
                    "warning",
                    f"Key '{key.literal}' is not statically known to exist in this dictionary.",
                    word=word_name,
                    token=symbol_token,
                ))
                extracted = _AbstractValue(kind="unknown")
            else:
                extracted = _AbstractValue(kind=mapping.keys[key.literal])
                if isinstance(mapping.data, dict):
                    if key.literal == "value" and mapping.data.get("schema_metadata") is not None:
                        metadata = mapping.data["schema_metadata"]
                        extracted.keys = metadata.get("keys")
                        extracted.enums = metadata.get("enums")
                        extracted.data = {"nested_metadata": metadata.get("nested")}
                    elif "nested_metadata" in mapping.data:
                        nested_defs = mapping.data["nested_metadata"]
                        if key.literal in nested_defs and nested_defs[key.literal] is not None:
                            info = nested_defs[key.literal]
                            extracted.keys = info.get("keys")
                            extracted.enums = info.get("enums")
                            extracted.data = {"nested_metadata": info.get("nested")}

                if mapping.enums and key.literal in mapping.enums:
                    extracted.enum_values = mapping.enums[key.literal]
        else:
            extracted = _lookup_dict_entry(mapping, key)
            if extracted is None:
                extracted = _AbstractValue(kind="none" if safe_on_nondict else "unknown")

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

        # Handle schema-aware recursive path lookup for literal strings
        if container.keys is not None and path.kind == "str" and isinstance(path.literal, str):
            segments = _normalize_lookup_path(path)
            if segments and isinstance(segments[0], str):
                first = segments[0]
                if first in container.keys and isinstance(container.data, dict):
                    current_meta = None
                    if first == "value" and "schema_metadata" in container.data:
                        current_meta = container.data["schema_metadata"]
                    elif "nested_metadata" in container.data and first in container.data["nested_metadata"]:
                        current_meta = container.data["nested_metadata"][first]

                    if current_meta is not None:
                        # Base case: just the first segment
                        if len(segments) == 1:
                            state.stack.append(_AbstractValue(
                                kind=container.keys[first],
                                keys=current_meta.get("keys"),
                                enums=current_meta.get("enums"),
                                data={"nested_metadata": current_meta.get("nested")}
                            ))
                            state.effects.add("pure")
                            return

                        # Recursive dive
                        for i in range(1, len(segments)):
                            seg = segments[i]
                            if not isinstance(seg, str) or seg not in current_meta.get("keys", {}):
                                break  # bail to generic lookup

                            kind = current_meta["keys"][seg]
                            if i == len(segments) - 1:
                                res = _AbstractValue(kind=kind)
                                info = current_meta.get("nested", {}).get(seg)
                                if info:
                                    res.keys = info.get("keys")
                                    res.enums = info.get("enums")
                                    res.data = {"nested_metadata": info.get("nested")}
                                elif seg in current_meta.get("enums", {}):
                                    res.enum_values = current_meta["enums"][seg]
                                state.stack.append(res)
                                state.effects.add("pure")
                                return

                            # Move deeper
                            if kind == "dict" and seg in current_meta.get("nested", {}):
                                current_meta = current_meta["nested"][seg]
                            else:
                                break

        extracted = _lookup_path_entry(container, path)
        if extracted is None:
            state.stack.append(_AbstractValue(kind="none", literal=None))
        else:
            state.stack.append(extracted)
        state.effects.add("pure")

    def _analyze_if(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="if", token=symbol_token)
        false_value = self._pop_value(state)
        true_value = self._pop_value(state)
        condition_value = self._pop_value(state)
        
        branch_stack = list(state.stack)
        true_state = self._analyze_optional_quotation(true_value, branch_stack, word_name="if", depth=depth + 1, if_nesting_depth=if_nesting_depth + 1, scope=f"{scope} > if:true", anchor_token=symbol_token)
        false_state = self._analyze_optional_quotation(false_value, branch_stack, word_name="if", depth=depth + 1, if_nesting_depth=if_nesting_depth + 1, scope=f"{scope} > if:false", anchor_token=symbol_token)
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
        if_nesting_depth: int,
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
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > word:{word_name}",
            anchor_token=symbol_token,
            consume_tokens=False,
            summary_extra={"definition_location": metadata.definition_span.span.location} if isinstance(metadata.definition_span, StackVmAstSpan) else None,
        )

        if metadata.explicit_signature:
            _, out_types = metadata.explicit_signature
            # Refine unknown types from replay with explicit signature types
            if len(called.stack) == len(out_types):
                for i, kind in enumerate(out_types):
                    if called.stack[i].kind == "unknown":
                        called.stack[i].kind = kind
            else:
                # Fallback to pure signature shape if replay stack depth is wrong
                called.stack = [_AbstractValue(kind=kind) for kind in out_types]

        state.stack = called.stack
        state.effects.update(called.effects)
        state.diagnostics.extend(called.diagnostics)
        state.required_inputs = max(state.required_inputs, called.required_inputs)
        state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_while(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="while", token=symbol_token)
        body_value = self._pop_value(state)
        condition_value = self._pop_value(state)
        loop_stack = list(state.stack)
        cond_state = self._analyze_optional_quotation(
            condition_value,
            loop_stack,
            word_name="while",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
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
            if_nesting_depth=if_nesting_depth,
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

    def _analyze_switch(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="switch", token=symbol_token)
        cases_value = self._pop_value(state)
        subject_value = self._pop_value(state)
        base_stack = list(state.stack)
        extracted_switch = _extract_switch_actions(cases_value.quotation)
        action_asts = extracted_switch["actions"]
        if not action_asts:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "switch cases could not be analyzed statically.", word="switch", token=symbol_token))
            return

        # Exhaustiveness Check
        is_exhaustive = extracted_switch["has_default"]
        if not is_exhaustive and subject_value.enum_values:
            # Check if all enum values are covered by literal cases
            handled_set = set(extracted_switch.get("case_values", []))
            if all(val in handled_set for val in subject_value.enum_values):
                is_exhaustive = True

        branch_states = [
            self.analyze_nodes(
                action_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > switch:case{index}",
                anchor_token=symbol_token,
            )
            for index, action_ast in enumerate(action_asts, start=1)
        ]
        if not is_exhaustive:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            if subject_value.enum_values:
                missing = sorted(set(subject_value.enum_values) - set(extracted_switch.get("case_values", [])))
                if missing:
                    state.diagnostics.append(
                        self._make_diagnostic(
                            "non-exhaustive-switch",
                            "warning",
                            f"switch is non-exhaustive for enum. Missing cases: {', '.join(map(str, missing))}",
                            word="switch",
                            token=symbol_token,
                        )
                    )

        self._merge_many_branch_states(state, branch_states)
        self._record_merge_summary(
            scope=f"{scope} > switch:merge",
            input_stack=base_stack,
            branch_states=branch_states,
            merged_stack=state.stack,
            extra={
                "reason": "exhaustive-switch-merge" if is_exhaustive else "optional-no-match-path",
                "precision": "merged" if is_exhaustive else "optional-path",
            },
            token=symbol_token,
        )

    def _analyze_cond(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
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
                if_nesting_depth=if_nesting_depth,
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
                if_nesting_depth=if_nesting_depth,
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

    def _analyze_fallback(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="fallback", token=symbol_token)
        fallback_value = self._pop_value(state)
        primary_value = self._pop_value(state)
        base_stack = list(state.stack)
        primary_state = self._analyze_optional_quotation(primary_value, base_stack, word_name="fallback", depth=depth + 1, if_nesting_depth=if_nesting_depth, scope=f"{scope} > fallback:primary", anchor_token=symbol_token)
        fallback_state = self._analyze_optional_quotation(fallback_value, base_stack, word_name="fallback", depth=depth + 1, if_nesting_depth=if_nesting_depth, scope=f"{scope} > fallback:fallback", anchor_token=symbol_token)
        self._merge_branch_states(state, primary_state, fallback_state)
        self._record_merge_summary(
            scope=f"{scope} > fallback:merge",
            input_stack=base_stack,
            branch_states=[primary_state, fallback_state],
            merged_stack=state.stack,
            extra={"reason": "fallback-recovery-merge", "precision": "merged"},
            token=symbol_token,
        )

    def _analyze_match(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="match", token=symbol_token)
        cases_value = self._pop_value(state)
        subject_value = self._pop_value(state)
        base_stack = list(state.stack)
        branch_pairs = _extract_match_pairs(cases_value.quotation)
        if not branch_pairs:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "match cases could not be analyzed statically.", word="match", token=symbol_token))
            return

        # Exhaustiveness Check for literal patterns
        is_exhaustive = any(_case_is_match_wildcard(p) for p, _ in branch_pairs)
        if not is_exhaustive and subject_value.enum_values:
            literal_patterns = set()
            for p, _ in branch_pairs:
                val = _extract_literal_pattern_value(p)
                if val is not None:
                    literal_patterns.add(val)
            if all(val in literal_patterns for val in subject_value.enum_values):
                is_exhaustive = True

        branch_states: list[_AnalysisState] = []
        has_wildcard_branch = False
        for index, (pattern_node, action_ast) in enumerate(branch_pairs, start=1):
            self._validate_match_pattern(state, subject_value, pattern_node, word="match", token=symbol_token)
            if _case_is_match_wildcard(pattern_node):
                has_wildcard_branch = True
            action_state = self.analyze_nodes(
                action_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > match:case{index}",
                anchor_token=symbol_token,
            )
            branch_states.append(action_state)
        if not is_exhaustive:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            if subject_value.enum_values:
                literal_patterns = set()
                for p, _ in branch_pairs:
                    val = _extract_literal_pattern_value(p)
                    if val is not None:
                        literal_patterns.add(val)
                missing = sorted(set(subject_value.enum_values) - literal_patterns)
                if missing:
                    state.diagnostics.append(
                        self._make_diagnostic(
                            "non-exhaustive-match",
                            "warning",
                            f"match is non-exhaustive for enum. Missing cases: {', '.join(map(str, missing))}",
                            word="match",
                            token=symbol_token,
                        )
                    )

        self._merge_many_branch_states(state, branch_states)
        self._record_merge_summary(
            scope=f"{scope} > match:merge",
            input_stack=base_stack,
            branch_states=branch_states,
            merged_stack=state.stack,
            extra={
                "has_wildcard_branch": is_exhaustive,
                "reason": "exhaustive-match-merge" if is_exhaustive else "optional-no-match-path",
                "precision": "merged" if is_exhaustive else "optional-path",
            },
            token=symbol_token,
        )

    def _analyze_parallel_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="parallel-map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="parallel-map",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > parallel-map:child",
            anchor_token=symbol_token,
        )
        illegal_effects = sorted(kind for kind in child_state.effects if kind not in {"pure", "control"})
        if illegal_effects:
            state.diagnostics.append(self._make_diagnostic("illegal-child-effect", "warning", "parallel-map child quotation may emit disallowed effects: " + ", ".join(illegal_effects) + ".", word="parallel-map", token=symbol_token, extra={"effect_kinds": illegal_effects}))
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="unknown"))

    def _analyze_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="map",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > map:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="map", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="list"))

    def _analyze_flat_map(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="flat-map", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="flat-map",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > flat-map:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="flat-map", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="list"))

    def _analyze_filter(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="filter", token=symbol_token)
        quotation_value = self._pop_value(state)
        values = self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="filter",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > filter:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="filter", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_clone_abstract_value(values if values.kind != "quotation" else _AbstractValue(kind="unknown")))

    def _analyze_find(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="find", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="find",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
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
        if_nesting_depth: int,
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
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > {word_name}:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name=word_name, token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="bool"))

    def _analyze_sort_by(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="sort-by", token=symbol_token)
        quotation_value = self._pop_value(state)
        values = self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="sort-by",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > sort-by:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="sort-by", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_clone_abstract_value(values if values.kind == "list" else _AbstractValue(kind="list")))

    def _analyze_group_by(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="group-by", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown")],
            word_name="group-by",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
            scope=f"{scope} > group-by:child",
            anchor_token=symbol_token,
        )
        self._diagnose_illegal_child_effects(state, child_state, word_name="group-by", token=symbol_token)
        state.effects.update(child_state.effects)
        state.diagnostics.extend(child_state.diagnostics)
        state.stack.append(_AbstractValue(kind="dict"))

    def _analyze_schema_word(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None) -> None:
        self._ensure_inputs(state, 2, word_name="schema-apply", token=symbol_token)
        schema_val = self._pop_value(state)
        target_val = self._pop_value(state)
        
        schema_metadata = None
        s_node = schema_val.literal if isinstance(schema_val.literal, dict) else schema_val.data
        if isinstance(s_node, dict):
            schema_metadata = _extract_schema_metadata(s_node)
        
        state.stack.append(_AbstractValue(
            kind="dict", 
            keys={"success": "bool", "value": "dict", "errors": "list"}, 
            data={"schema_metadata": schema_metadata}
        ))
        state.effects.add("pure")

    def _analyze_validated_match(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 4, word_name="validated-match", token=symbol_token)
        invalid_case_val = self._pop_value(state)
        cases_val = self._pop_value(state)
        result_expr_val = self._pop_value(state)
        envelope_val = self._pop_value(state)
        
        base_stack = list(state.stack)
        
        if result_expr_val.kind == "quotation" and result_expr_val.quotation is not None:
            self.analyze_nodes(
                result_expr_val.quotation,
                initial_stack=base_stack + [envelope_val.clone()],
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > validated-match:result_expr",
                anchor_token=symbol_token,
                consume_tokens=False,
            )

        subject_value = _AbstractValue(kind="dict")
        if isinstance(envelope_val.data, dict) and "schema_metadata" in envelope_val.data:
            metadata = envelope_val.data["schema_metadata"]
            if metadata:
                subject_value.keys = metadata.get("keys")
                subject_value.enums = metadata.get("enums")
                subject_value.data = {"nested_metadata": metadata.get("nested")}

        branch_pairs = _extract_match_pairs(cases_val.quotation)
        branch_states: list[_AnalysisState] = []
        for index, (pattern_node, action_ast) in enumerate(branch_pairs, start=1):
            self._validate_match_pattern(state, subject_value, pattern_node, word="validated-match", token=symbol_token)
            branch_states.append(self.analyze_nodes(
                action_ast, initial_stack=list(base_stack), depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > validated-match:case{index}", anchor_token=symbol_token,
            ))
            
        invalid_state = self._analyze_optional_quotation(
            invalid_case_val, base_stack + [envelope_val.clone()], word_name="validated-match",
            depth=depth + 1, if_nesting_depth=if_nesting_depth, scope=f"{scope} > validated-match:invalid", anchor_token=symbol_token
        )
        branch_states.append(invalid_state)
        
        if not any(_case_is_match_wildcard(p) for p, _ in branch_pairs):
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            
        self._merge_many_branch_states(state, branch_states)

    def _analyze_schema_route(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 5, word_name="schema-route", token=symbol_token)
        # Stack: envelope errors_path value_store_path cases invalid_case
        invalid_case_val = self._pop_value(state)
        cases_val = self._pop_value(state)
        value_store_path_val = self._pop_value(state)
        errors_path_val = self._pop_value(state)
        envelope_val = self._pop_value(state)
        
        state.effects.add("state")
        
        # Re-use validated-match logic for branching
        state.stack.append(envelope_val)
        state.stack.append(_AbstractValue(kind="quotation", quotation=[])) # dummy result_expr
        state.stack.append(cases_val)
        state.stack.append(invalid_case_val)
        self._analyze_validated_match(state, symbol_token=symbol_token, depth=depth, if_nesting_depth=if_nesting_depth, scope=scope)

    def _validate_match_pattern(self, state: _AnalysisState, subject: _AbstractValue, pattern_node: Any, *, word: str, token: StackVmSourceToken | None) -> None:
        if subject.keys is None:
            return
        pattern_data = _extract_match_pattern_literal(pattern_node)
        if isinstance(pattern_data, dict):
            self._check_match_key_recursive(state, subject, pattern_data, word=word, token=token)

    def _check_match_key_recursive(self, state: _AnalysisState, current_val: _AbstractValue, pattern_data: dict, *, word: str, token: StackVmSourceToken | None) -> None:
        if current_val.keys is None:
            return
        for key, sub_pattern in pattern_data.items():
            if str(key).startswith("$") or key == "$rest":
                continue
            if key not in current_val.keys:
                state.diagnostics.append(self._make_diagnostic(
                    "unknown-dict-key", "warning",
                    f"Pattern key '{key}' is not statically known to exist in the subject dictionary.",
                    word=word, token=token
                ))
                continue
            if isinstance(sub_pattern, dict) and isinstance(current_val.data, dict):
                nested_val = None
                if key == "value" and "schema_metadata" in current_val.data:
                    metadata = current_val.data["schema_metadata"]
                    nested_val = _AbstractValue(
                        kind="dict",
                        keys=metadata.get("keys"),
                        enums=metadata.get("enums"),
                        data={"nested_metadata": metadata.get("nested")}
                    )
                elif "nested_metadata" in current_val.data and key in current_val.data["nested_metadata"]:
                    info = current_val.data["nested_metadata"][key]
                    nested_val = _AbstractValue(
                        kind="dict",
                        keys=info.get("keys"),
                        enums=info.get("enums"),
                        data={"nested_metadata": info.get("nested")}
                    )

                if nested_val:
                    self._check_match_key_recursive(state, nested_val, sub_pattern, word=word, token=token)

    def _analyze_project_shared(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="project-shared", token=symbol_token)
        body_val = self._pop_value(state)
        projections_val = self._pop_value(state)
        subject_val = self._pop_value(state)

        if projections_val.kind == "quotation" and projections_val.quotation is not None:
            # Projections are pairs: [ quote ] "path"
            quotation = projections_val.quotation
            for i in range(0, len(quotation), 2):
                if i + 1 >= len(quotation):
                    break
                proj_quote_node = quotation[i]
                if isinstance(proj_quote_node, list):
                    # Project-shared runs each projection quotation against the subject
                    self.analyze_nodes(
                        proj_quote_node,
                        initial_stack=[subject_val.clone()],
                        depth=depth + 1,
                        if_nesting_depth=if_nesting_depth,
                        scope=f"{scope} > project-shared:proj{i // 2}",
                        anchor_token=symbol_token,
                        consume_tokens=False,
                    )

        if body_val.kind == "quotation" and body_val.quotation is not None:
            # Macros drop the subject container before executing the body
            called = self.analyze_nodes(
                body_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > project-shared:body",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_project_fields(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="project-fields", token=symbol_token)
        body_val = self._pop_value(state)
        specs_val = self._pop_value(state)
        subject_val = self._pop_value(state)

        if specs_val.kind == "quotation" and specs_val.quotation is not None:
            # Triples: source_path shared_path default
            quotation = specs_val.quotation
            for i in range(0, len(quotation), 3):
                if i + 2 >= len(quotation):
                    break
                path_node = quotation[i]
                path_str = _literal_string(path_node)
                if path_str and subject_val.keys is not None:
                    # Reuse path validation logic
                    path_abs = _AbstractValue(kind="str", literal=path_str)
                    self._check_dict_path(state, subject_val, path_abs, word="project-fields", token=symbol_token)

        if body_val.kind == "quotation" and body_val.quotation is not None:
            called = self.analyze_nodes(
                body_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > project-fields:body",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_handoff_rules(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="handoff-rules", token=symbol_token)
        self._pop_value(state) # band_path
        rules_val = self._pop_value(state)
        
        base_stack = list(state.stack)
        
        if rules_val.kind != "quotation" or rules_val.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "handoff-rules expects a rules quotation.", word="handoff-rules", token=symbol_token))
            return

        base_stack = list(state.stack)
        rules = rules_val.quotation
        branch_states: list[_AnalysisState] = []
        has_default_branch = False
        
        # Triplets: [cond] "band" "agent"
        for i in range(0, len(rules), 3):
            if i + 2 >= len(rules):
                break
            
            cond_ast = rules[i]
            if not isinstance(cond_ast, list):
                continue
                
            if _condition_is_unconditional_true(cond_ast):
                has_default_branch = True
                
            cond_state = self.analyze_nodes(
                cond_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > handoff-rules:condition{i // 3}",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            
            action_state = cond_state.clone()
            if action_state.stack:
                action_state.stack.pop() # pop condition result
            
            action_state.effects.add("state")
            action_state.effects.add("handoff")
            branch_states.append(action_state)
            
        if not has_default_branch:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            
        self._merge_many_branch_states(state, branch_states)

    def _analyze_handoff_switch(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="handoff-switch", token=symbol_token)
        cases_val = self._pop_value(state)
        value_expr_val = self._pop_value(state)
        
        if value_expr_val.kind == "quotation" and value_expr_val.quotation is not None:
            called = self.analyze_nodes(
                value_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > handoff-switch:value",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)
        else:
            state.stack.append(_AbstractValue(kind="unknown"))

        if cases_val.kind != "quotation" or cases_val.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "handoff-switch expects a cases quotation.", word="handoff-switch", token=symbol_token))
            return

        subject_value = self._pop_value(state)
        base_stack = list(state.stack)
        cases = cases_val.quotation
        branch_states: list[_AnalysisState] = []
        has_default = False
        
        for i in range(0, len(cases), 2):
            if i + 1 >= len(cases):
                break
            case_node = cases[i]
            if _case_is_default(case_node):
                has_default = True
            
            # Action: "agent" handoff
            action_state = _AnalysisState(stack=list(base_stack))
            action_state.effects.add("handoff")
            branch_states.append(action_state)
            
        # Exhaustiveness check for handoff-switch
        is_exhaustive = has_default
        if not is_exhaustive and subject_value.enum_values:
            case_values = []
            for i in range(0, len(cases), 2):
                val = _extract_literal_pattern_value(cases[i])
                if val is not None:
                    case_values.append(val)
            handled_set = set(case_values)
            if all(val in handled_set for val in subject_value.enum_values):
                is_exhaustive = True

        if not is_exhaustive:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            
        self._merge_many_branch_states(state, branch_states)

    def _analyze_prompt_route(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="prompt-route", token=symbol_token)
        cases_val = self._pop_value(state)
        request_expr_val = self._pop_value(state)

        if request_expr_val.kind == "quotation" and request_expr_val.quotation is not None:
            self.analyze_nodes(
                request_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > prompt-route:request",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
        
        state.effects.add("prompt")

        if cases_val.kind != "quotation" or cases_val.quotation is None:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "prompt-route expects a cases quotation.", word="prompt-route", token=symbol_token))
            return

        base_stack = list(state.stack)
        extracted_switch = _extract_switch_actions(cases_val.quotation)
        action_asts = extracted_switch["actions"]
        if not action_asts:
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", "prompt-route cases could not be analyzed statically.", word="prompt-route", token=symbol_token))
            return

        branch_states = [
            self.analyze_nodes(
                action_ast,
                initial_stack=list(base_stack),
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > prompt-route:case{index}",
                anchor_token=symbol_token,
            )
            for index, action_ast in enumerate(action_asts, start=1)
        ]
        
        if not extracted_switch["has_default"]:
            branch_states.append(_AnalysisState(stack=list(base_stack)))
            
        self._merge_many_branch_states(state, branch_states)

    def _analyze_prompt_store(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="prompt-store", token=symbol_token)
        body_val = self._pop_value(state)
        value_path_val = self._pop_value(state)
        request_expr_val = self._pop_value(state)

        if request_expr_val.kind == "quotation" and request_expr_val.quotation is not None:
            self.analyze_nodes(
                request_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > prompt-store:request",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
        
        state.effects.add("prompt")
        state.effects.add("state")

        if body_val.kind == "quotation" and body_val.quotation is not None:
            body_stack = list(state.stack)
            # Macro pushes prompt result to stack for the body
            body_stack.append(_AbstractValue(kind="unknown"))
            
            called = self.analyze_nodes(
                body_val.quotation,
                initial_stack=body_stack,
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > prompt-store:body",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)
        else:
            state.stack.append(_AbstractValue(kind="unknown"))

    def _analyze_ask_from(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 1, word_name="ask-from", token=symbol_token)
        question_expr_val = self._pop_value(state)

        if question_expr_val.kind == "quotation" and question_expr_val.quotation is not None:
            self.analyze_nodes(
                question_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > ask-from:question",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
        
        state.effects.add("prompt")

    def _analyze_prompt_store_text(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="prompt-store-text", token=symbol_token)
        body_val = self._pop_value(state)
        value_path_val = self._pop_value(state)
        question_expr_val = self._pop_value(state)

        if question_expr_val.kind == "quotation" and question_expr_val.quotation is not None:
            self.analyze_nodes(
                question_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > prompt-store-text:question",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
        
        state.effects.add("prompt")
        state.effects.add("state")

        if body_val.kind == "quotation" and body_val.quotation is not None:
            body_stack = list(state.stack)
            # prompt-store-text produces a string response
            body_stack.append(_AbstractValue(kind="str"))
            
            called = self.analyze_nodes(
                body_val.quotation,
                initial_stack=body_stack,
                depth=depth + 1,
                if_nesting_depth=if_nesting_depth,
                scope=f"{scope} > prompt-store-text:body",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)
        else:
            state.stack.append(_AbstractValue(kind="str"))

    def _analyze_stdlib_io_read_once(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name=word_name, token=symbol_token)
        later_turn_val = self._pop_value(state)
        expr_val = self._pop_value(state)

        if expr_val.kind == "quotation" and expr_val.quotation is not None:
            self.analyze_nodes(
                expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > {word_name}:expr",
                anchor_token=symbol_token,
                consume_tokens=False,
            )

        state.effects.add("tool")

        if later_turn_val.kind == "quotation" and later_turn_val.quotation is not None:
            called = self.analyze_nodes(
                later_turn_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > {word_name}:body",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)

    def _analyze_stdlib_simple_state_op(self, state: _AnalysisState, *, word_name: str, pops: int, pushes: int = 0, symbol_token: StackVmSourceToken | None) -> None:
        """Helper for simple stdlib words that perform state operations."""
        self._ensure_inputs(state, pops, word_name=word_name, token=symbol_token)
        self._pop_values(state, pops)
        for _ in range(pushes):
            state.stack.append(_AbstractValue(kind="unknown"))
        state.effects.add("state")

    _WORKFLOW_BUILDER_POP_COUNTS = {
        "define-workflow-spec": 2,
        "extend-workflow-spec": 3,
        "define-workflow-family": 2,
        "extend-workflow-family": 3,
        "define-choice-continue-spec": 10,
        "define-choice-answer-spec": 9,
        "define-choice-answer-family": 13,
        "define-choice-continue-answer-family": 18,
        "define-choice-route-family": 16,
        "define-choice-finalize-family": 15,
    }

    def _analyze_workflow_builder(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        pops = self._WORKFLOW_BUILDER_POP_COUNTS.get(word_name, 0)
        self._ensure_inputs(state, pops, word_name=word_name, token=symbol_token)
        args = self._pop_values(state, pops)
        args.reverse() # Maintain original parameter order for scope naming

        # Specific validation for generic spec/family builders
        if word_name in {"define-workflow-spec", "extend-workflow-spec"}:
            spec_arg = args[-1]
            if spec_arg.kind == "quotation" and spec_arg.quotation is not None:
                self._validate_workflow_spec_keys(state, spec_arg.quotation, symbol_token, word=word_name)
        elif word_name in {"define-workflow-family", "extend-workflow-family"}:
            family_arg = args[-1]
            if family_arg.kind == "quotation" and family_arg.quotation is not None:
                self._validate_workflow_family_sections(state, family_arg.quotation, symbol_token, word=word_name)

        for i, arg in enumerate(args):
            if arg.kind == "quotation" and arg.quotation is not None:
                # Analyze builder quotations in isolation to catch nested logic errors
                self.analyze_nodes(
                    arg.quotation,
                    initial_stack=[],
                    depth=depth + 1,
                    scope=f"{scope} > {word_name}:arg{i}",
                    anchor_token=symbol_token,
                    consume_tokens=False,
                )
        state.effects.add("control")

    def _analyze_workflow_spec_inline(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="workflow-spec", token=symbol_token)
        policy_val = self._pop_value(state)
        role_val = self._pop_value(state)
        spec_val = self._pop_value(state)
        
        if spec_val.kind == "quotation" and spec_val.quotation is not None:
            self._validate_workflow_spec_keys(state, spec_val.quotation, symbol_token, word="workflow-spec")
            # Recurse into inner logic
            for node in spec_val.quotation:
                if isinstance(node, list):
                    self.analyze_nodes(
                        node,
                        initial_stack=[],
                        depth=depth + 1,
                        scope=f"{scope} > workflow-spec:inner",
                        anchor_token=symbol_token,
                        consume_tokens=False,
                    )
        state.effects.add("control")

    def _analyze_workflow_contract_direct(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 1, word_name=word_name, token=symbol_token)
        spec_val = self._pop_value(state)
        if spec_val.kind == "quotation" and spec_val.quotation is not None:
            self._validate_workflow_spec_keys(state, spec_val.quotation, symbol_token, word=word_name)
            # Recurse into inner logic
            for node in spec_val.quotation:
                if isinstance(node, list):
                    self.analyze_nodes(
                        node,
                        initial_stack=[],
                        depth=depth + 1,
                        scope=f"{scope} > {word_name}:inner",
                        anchor_token=symbol_token,
                        consume_tokens=False,
                    )
        state.effects.add("control")

    def _validate_workflow_spec_keys(self, state: _AnalysisState, spec_ast: list[Any], token: StackVmSourceToken | None, *, word: str) -> None:
        if len(spec_ast) % 2 != 0:
            return
        for i in range(0, len(spec_ast), 2):
            key = _literal_string(spec_ast[i])
            if key and key not in _VALID_WORKFLOW_SPEC_KEYS:
                state.diagnostics.append(self._make_diagnostic(
                    "unknown-workflow-key", "warning",
                    f"Workflow spec contains unknown key '{key}'.",
                    word=word, token=token
                ))

    def _validate_workflow_family_sections(self, state: _AnalysisState, family_ast: list[Any], token: StackVmSourceToken | None, *, word: str) -> None:
        if len(family_ast) % 2 != 0:
            return
        for i in range(0, len(family_ast), 2):
            section = _literal_string(family_ast[i])
            if section and section not in _VALID_WORKFLOW_FAMILY_SECTIONS:
                state.diagnostics.append(self._make_diagnostic(
                    "unknown-workflow-key", "warning",
                    f"Workflow family contains unknown section '{section}'.",
                    word=word, token=token
                ))
            if i + 1 < len(family_ast):
                contract_node = family_ast[i + 1]
                if isinstance(contract_node, list):
                    self._validate_workflow_spec_keys(state, contract_node, token, word=word)

    def _analyze_workflow_usage(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None, depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name=word_name, token=symbol_token)
        # usage macros pop name, role, policy
        self._pop_values(state, 3)
        
        # Conservative effect tracking for unexpanded workflow usage
        state.effects.add("prompt")
        state.effects.add("handoff")
        state.effects.add("final")
        state.effects.add("state")

    def _analyze_record_fields(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 2, word_name="record-fields", token=symbol_token)
        field_specs_val = self._pop_value(state)
        base_expr_val = self._pop_value(state)

        if base_expr_val.kind == "quotation" and base_expr_val.quotation is not None:
            self.analyze_nodes(
                base_expr_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > record-fields:base",
                anchor_token=symbol_token,
                consume_tokens=False,
            )

        if field_specs_val.kind == "quotation" and field_specs_val.quotation is not None:
            # field_specs are pairs: path value_node
            quotation = field_specs_val.quotation
            for i in range(0, len(quotation), 2):
                if i + 1 >= len(quotation):
                    break
                val_node = quotation[i + 1]
                if isinstance(val_node, list):
                    # Evaluate value quotations against the stack context
                    self.analyze_nodes(
                        val_node,
                        initial_stack=list(state.stack),
                        depth=depth + 1,
                        scope=f"{scope} > record-fields:value{i // 2}",
                        anchor_token=symbol_token,
                        consume_tokens=False,
                    )

        # record-fields builds and leaves a dictionary on the stack
        state.stack.append(_AbstractValue(kind="dict"))
        state.effects.add("pure")

    def _analyze_return_flow(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 4, word_name="return-flow", token=symbol_token)
        resume_body_val = self._pop_value(state)
        self._pop_values(state, 3) # delegate_target, load_body, payload_file

        if resume_body_val.kind == "quotation" and resume_body_val.quotation is not None:
            # resume_body runs when the delegate returns, continuing with the stack as it was
            called = self.analyze_nodes(
                resume_body_val.quotation,
                initial_stack=list(state.stack),
                depth=depth + 1,
                scope=f"{scope} > return-flow:resume",
                anchor_token=symbol_token,
                consume_tokens=False,
            )
            state.stack = called.stack
            state.effects.update(called.effects)
            state.diagnostics.extend(called.diagnostics)
            state.required_inputs = max(state.required_inputs, called.required_inputs)
            state.max_stack_depth = max(state.max_stack_depth, called.max_stack_depth)
        
        state.effects.add("tool")
        state.effects.add("handoff")

    def _analyze_return_answer_flow(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 5, word_name="return-answer-flow", token=symbol_token)
        value_expr_val = self._pop_value(state)
        missing_case_val = self._pop_value(state)
        self._pop_values(state, 3) # delegate_target, load_body, payload_file

        if missing_case_val.kind == "quotation" and missing_case_val.quotation is not None:
            self.analyze_nodes(
                missing_case_val.quotation,
                initial_stack=[],
                depth=depth + 1,
                scope=f"{scope} > return-answer-flow:missing",
                anchor_token=symbol_token,
                consume_tokens=False,
            )

        if value_expr_val.kind == "quotation" and value_expr_val.quotation is not None:
            # value_expr formats the returned answer string
            self.analyze_nodes(
                value_expr_val.quotation,
                initial_stack=[_AbstractValue(kind="str")],
                depth=depth + 1,
                scope=f"{scope} > return-answer-flow:value",
                anchor_token=symbol_token,
                consume_tokens=False,
            )

        state.effects.add("tool")
        state.effects.add("handoff")
        state.effects.add("final")

    def _analyze_complex_return_flow(self, state: _AnalysisState, *, word_name: str, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        pop_counts = {
            "return-field-route-flow": 7,
            "return-field-finalize-flow": 6,
            "return-field-policy-flow": 8,
            "return-policy-flow": 8,
            "return-contract-flow": 8,
            "normalized-return-flow": 7,
        }
        pops = pop_counts.get(word_name, 0)
        self._ensure_inputs(state, pops, word_name=word_name, token=symbol_token)
        args = self._pop_values(state, pops)
        args.reverse() # Back to syntax order

        # Scan all provided quotations for nested effect violations or errors
        for i, arg in enumerate(args):
            if arg.kind == "quotation" and arg.quotation is not None:
                self.analyze_nodes(
                    arg.quotation,
                    initial_stack=[],
                    depth=depth + 1,
                    scope=f"{scope} > {word_name}:arg{i}",
                    anchor_token=symbol_token,
                    consume_tokens=False,
                )
        
        state.effects.add("tool")
        state.effects.add("handoff")
        state.effects.add("final")
        state.effects.add("state")

    def _check_dict_path(self, state: _AnalysisState, container: _AbstractValue, path: _AbstractValue, *, word: str, token: StackVmSourceToken | None) -> None:
        """Validates that a path exists in a dictionary with statically known keys."""
        if container.keys is None:
            return
        
        segments = _normalize_lookup_path(path)
        if not segments:
            return
            
        first = segments[0]
        if not isinstance(first, str):
            return

        if first not in container.keys:
            state.diagnostics.append(self._make_diagnostic(
                "unknown-dict-key", "warning",
                f"Key '{first}' is not statically known to exist in this dictionary.",
                word=word, token=token
            ))
            return
            
        # Recursive traversal into schema metadata
        if isinstance(container.data, dict):
            current_meta = None
            if first == "value" and "schema_metadata" in container.data:
                current_meta = container.data["schema_metadata"]
            elif "nested_metadata" in container.data and first in container.data["nested_metadata"]:
                current_meta = container.data["nested_metadata"][first]

            if current_meta is not None:
                for i in range(1, len(segments)):
                    seg = segments[i]
                    if not isinstance(seg, str):
                        break

                    if seg not in current_meta.get("keys", {}):
                        state.diagnostics.append(self._make_diagnostic(
                            "unknown-dict-key", "warning",
                            f"Key '{seg}' is not statically known to exist in the schema-validated data.",
                            word=word, token=token
                        ))
                        return

                    # Move deeper
                    kind = current_meta["keys"][seg]
                    if kind == "dict" and seg in current_meta.get("nested", {}):
                        current_meta = current_meta["nested"][seg]
                    else:
                        break

    def _analyze_reduce(self, state: _AnalysisState, *, symbol_token: StackVmSourceToken | None, depth: int, if_nesting_depth: int, scope: str) -> None:
        self._ensure_inputs(state, 3, word_name="reduce", token=symbol_token)
        quotation_value = self._pop_value(state)
        self._pop_value(state)
        self._pop_value(state)
        child_state = self._analyze_optional_quotation(
            quotation_value,
            [_AbstractValue(kind="unknown"), _AbstractValue(kind="unknown")],
            word_name="reduce",
            depth=depth + 1,
            if_nesting_depth=if_nesting_depth,
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

    def _infer_user_word(
        self,
        word_name: str,
        quotation_ast: list[Any],
        *,
        definition_span: StackVmAstSpan | None,
        explicit_sig: tuple[list[str], list[str]] | None = None,
        call_state: _AnalysisState | None = None,
        symbol_token: StackVmSourceToken | None = None,
    ) -> StackVmWordMetadata:
        if word_name in self._inference_stack:
            if explicit_sig:
                return StackVmWordMetadata(
                    word_name,
                    StackVmStackEffect(len(explicit_sig[0]), len(explicit_sig[1])),
                    "control",
                    summary="recursive",
                    output_shape=tuple(explicit_sig[1]),
                    explicit_signature=explicit_sig,
                )
            return StackVmWordMetadata(word_name, StackVmStackEffect(0, None), "control", summary="recursive")

        self._inference_stack.add(word_name)
        try:
            previous_recording = self._record_shape_flow
            self._record_shape_flow = False

            initial_stack = []
            if explicit_sig:
                for kind in explicit_sig[0]:
                    initial_stack.append(_AbstractValue(kind=kind))

            inferred = self.analyze_nodes(
                quotation_ast,
                initial_stack=initial_stack,
                node_spans=list(definition_span.children) if isinstance(definition_span, StackVmAstSpan) else None,
                scope=f"infer:{word_name}",
                consume_tokens=False,
            )

            if explicit_sig and call_state is not None:
                in_types, out_types = explicit_sig
                if inferred.required_inputs > 0:
                    call_state.diagnostics.append(self._make_diagnostic(
                        "signature-mismatch", "warning",
                        f"Helper '{word_name}' signature declares {len(in_types)} inputs but body requires {len(in_types) + inferred.required_inputs}.",
                        word=word_name, token=symbol_token
                    ))
                elif len(inferred.stack) != len(out_types):
                    call_state.diagnostics.append(self._make_diagnostic(
                        "signature-mismatch", "warning",
                        f"Helper '{word_name}' signature declares {len(out_types)} outputs but body leaves {len(inferred.stack)}.",
                        word=word_name, token=symbol_token
                    ))

            effect_kind = _primary_effect_kind(inferred.effects)

            pops = (len(explicit_sig[0]) + inferred.required_inputs) if explicit_sig else inferred.required_inputs
            pushes = len(explicit_sig[1]) if explicit_sig else len(inferred.stack)
            output_shape = tuple(explicit_sig[1]) if explicit_sig else tuple(self._summarize_value_for_display(value) for value in inferred.stack)

            return StackVmWordMetadata(
                word_name,
                StackVmStackEffect(pops, pushes),
                effect_kind,
                output_shape=output_shape,
                host_surface="core",
                definition_span=definition_span,
                explicit_signature=explicit_sig,
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
        if_nesting_depth: int = 0,
        scope: str,
        anchor_token: StackVmSourceToken | None = None,
    ) -> _AnalysisState:
        if value.kind != "quotation" or value.quotation is None:
            state = _AnalysisState(stack=list(initial_stack))
            state.diagnostics.append(self._make_diagnostic("dynamic-stack-shape", "warning", f"{word_name} expects quotation operands for static analysis.", word=word_name))
            return state
        return self.analyze_nodes(value.quotation, initial_stack=list(initial_stack), depth=depth, if_nesting_depth=if_nesting_depth, scope=scope, anchor_token=anchor_token)

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

    def _summarize_value_for_display(self, value: _AbstractValue) -> str:
        kind = value.kind
        suffix = ""
        if value.enum_values:
            variants = sorted(str(v) for v in value.enum_values)
            suffix = f"{{{'|'.join(variants)}}}"
        elif value.keys:
            key_details = sorted(f"{k}:{v}" for k, v in value.keys.items())
            suffix = f"{{{','.join(key_details)}}}"
        return f"{kind}{suffix}"

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
            "stack_shape": [self._summarize_value_for_display(value) for value in state.stack],
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
            "input_stack_shape": [self._summarize_value_for_display(value) for value in input_stack],
            "output_stack_shape": [self._summarize_value_for_display(value) for value in output_state.stack],
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
            "input_stack_shape": [self._summarize_value_for_display(value) for value in input_stack],
            "branch_output_shapes": [[self._summarize_value_for_display(value) for value in branch.stack] for branch in branch_states],
            "merged_stack_shape": [self._summarize_value_for_display(value) for value in merged_stack],
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
            keys = None
            if left_value.keys is not None and right_value.keys is not None:
                if left_value.keys == right_value.keys:
                    keys = dict(left_value.keys)
            
            enums = None
            if left_value.enums is not None and right_value.enums is not None:
                if left_value.enums == right_value.enums:
                    enums = dict(left_value.enums)

            merged.append(
                _AbstractValue(
                    kind=left_value.kind,
                    literal=left_value.literal,
                    quotation=left_value.quotation,
                    data=left_value.data,
                    keys=keys,
                    enums=enums,
                    enum_values=list(left_value.enum_values) if left_value.enum_values == right_value.enum_values and left_value.enum_values is not None else None,
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
    return value.clone()


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
        return {"actions": [], "has_default": False, "case_values": []}
    actions: list[list[Any]] = []
    case_values = []
    has_default = False
    for index in range(1, len(cases_ast), 2):
        case_node = cases_ast[index - 1]
        action_ast = cases_ast[index]
        if not isinstance(action_ast, list):
            return {"actions": [], "has_default": False, "case_values": []}
        if _case_is_default(case_node):
            has_default = True
        elif isinstance(case_node, tuple) and len(case_node) == 2:
            case_values.append(case_node[1])
        actions.append(action_ast)
    return {"actions": actions, "has_default": has_default, "case_values": case_values}


def _primary_effect_kind(effects: set[str]) -> EffectKind:
    for kind in ("final", "handoff", "tool", "prompt", "llm", "state", "control", "pure"):
        if kind in effects:
            return kind
    return "pure"


def _case_is_default(node: Any) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] == "str" and node[1] == "default"


def _extract_literal_pattern_value(pattern_node: Any) -> Any | None:
    if isinstance(pattern_node, tuple) and len(pattern_node) == 2 and pattern_node[0] in {"str", "int", "bool"}:
        return pattern_node[1]
    return None


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


def _parse_explicit_signature(sig_ast: list[Any]) -> tuple[list[str], list[str]] | None:
    in_types = []
    out_types = []
    target = in_types
    for item in sig_ast:
        if isinstance(item, tuple) and item[0] == "sym":
            sym = str(item[1])
            if sym == "--":
                target = out_types
            else:
                target.append(sym)
    return (in_types, out_types)


def _extract_schema_metadata(schema_node: dict[str, Any]) -> dict[str, Any]:
    """Recursively extracts key types, enums and nested property schemas."""
    keys: dict[str, str] = {}
    enums: dict[str, list[Any]] = {}
    nested: dict[str, dict[str, Any]] = {}

    properties = schema_node.get("properties")
    if not isinstance(properties, dict):
        return {"keys": keys, "enums": enums, "nested": nested}

    for k, v in properties.items():
        if not isinstance(v, dict):
            continue
        t = str(v.get("type", "unknown")).lower()
        if t == "integer":
            t = "int"
        elif t == "string":
            t = "str"
        elif t == "boolean":
            t = "bool"
        elif t == "number":
            t = "float"
        elif t in {"object", "dict"}:
            t = "dict"
        elif t in {"array", "list"}:
            t = "list"
        keys[k] = t

        enum_list = v.get("enum")
        if isinstance(enum_list, list):
            enums[k] = list(enum_list)

        if t == "dict" and "properties" in v:
            nested[k] = _extract_schema_metadata(v)

    return {"keys": keys, "enums": enums, "nested": nested}


def _extract_match_pattern_literal(node: Any) -> Any | None:
    if isinstance(node, list):
        if len(node) >= 2 and isinstance(node[0], tuple) and node[0][0] == "str":
            if isinstance(node[1], tuple) and node[1][0] == "sym" and str(node[1][1]) == "yaml>":
                try:
                    import yaml
                    return yaml.safe_load(node[0][1])
                except Exception:
                    return None
    return _extract_literal_pattern_value(node)
