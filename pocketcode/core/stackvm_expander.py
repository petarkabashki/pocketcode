from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml

from pocketcode.core.stackvm_parser import (
    StackVmAstSpan,
    StackVmSourceSpan,
    parse_stackvm_source,
    parse_stackvm_source_with_spans,
    serialize_stackvm_ast,
)


StackVmAstNode = Any


@dataclass(frozen=True)
class MacroDefinition:
    name: str
    parameters: tuple[str, ...]
    template: list[StackVmAstNode]
    template_mode: str = "plain"
    builtin: bool = False
    definition_span: StackVmSourceSpan | None = None
    custom_expand: Callable[
        [dict[str, StackVmAstNode], dict[str, StackVmAstSpan], dict[str, int]],
        tuple[list[StackVmAstNode], list[StackVmAstSpan | None]],
    ] | None = None
    explicit_signature: list[Any] | None = None


@dataclass(frozen=True)
class StackVmExpansionFrame:
    macro_name: str
    builtin: bool
    depth: int
    call_site: str | None = None
    definition_site: str | None = None
    generated_by: str | None = None
    syntax_args: list[str] = field(default_factory=list)
    expanded_form: str = ""


@dataclass
class StackVmMacroExpansionError(Exception):
    message: str
    macro_trace: tuple[str, ...] = ()

    def __str__(self) -> str:
        if not self.macro_trace:
            return self.message
        return f"{self.message} (macro trace: {' -> '.join(self.macro_trace)})"


@dataclass
class StackVmExpansionResult:
    ast: list[StackVmAstNode]
    ast_spans: list[StackVmAstSpan] = field(default_factory=list)
    macros: dict[str, MacroDefinition] = field(default_factory=dict)
    expansion_count: int = 0
    gensym_count: int = 0
    expansion_trace: list[str] = field(default_factory=list)
    expansion_frames: list[StackVmExpansionFrame] = field(default_factory=list)


def expand_stackvm_source(code: str, *, max_expansion_depth: int = 32) -> StackVmExpansionResult:
    ast, source_spans = parse_stackvm_source_with_spans(code)
    return expand_stackvm_ast(ast, max_expansion_depth=max_expansion_depth, source_spans=source_spans)


def expand_stackvm_ast(
    ast: list[StackVmAstNode],
    *,
    max_expansion_depth: int = 32,
    macros: dict[str, MacroDefinition] | None = None,
    source_spans: list[StackVmAstSpan] | None = None,
    _depth: int = 0,
) -> StackVmExpansionResult:
    if _depth > max_expansion_depth:
        raise RecursionError(f"StackVM macro expansion exceeded max depth ({max_expansion_depth}).")

    registry = _builtin_macro_definitions()
    if macros:
        registry.update(macros)
    gensym_state = {"count": 0}
    expansion_trace: list[str] = []
    expansion_frames: list[StackVmExpansionFrame] = []
    expanded, expanded_spans, expansion_count = _expand_sequence(
        ast,
        macros=registry,
        max_expansion_depth=max_expansion_depth,
        depth=_depth,
        gensym_state=gensym_state,
        expansion_trace=expansion_trace,
        expansion_frames=expansion_frames,
        macro_stack=(),
        source_spans=source_spans,
        generated_by=None,
        inherited_call_site=None,
        inherited_call_span=None,
    )
    return StackVmExpansionResult(
        ast=expanded,
        ast_spans=expanded_spans,
        macros=registry,
        expansion_count=expansion_count,
        gensym_count=int(gensym_state["count"]),
        expansion_trace=expansion_trace,
        expansion_frames=expansion_frames,
    )


def _expand_sequence(
    items: list[StackVmAstNode],
    *,
    macros: dict[str, MacroDefinition],
    max_expansion_depth: int,
    depth: int,
    gensym_state: dict[str, int],
    expansion_trace: list[str],
    expansion_frames: list[StackVmExpansionFrame],
    macro_stack: tuple[str, ...],
    source_spans: list[StackVmAstSpan] | None,
    generated_by: str | None,
    inherited_call_site: str | None,
    inherited_call_span: StackVmSourceSpan | None,
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan], int]:
    output: list[StackVmAstNode] = []
    output_spans: list[StackVmAstSpan] = []
    expansion_count = 0

    for index, item in enumerate(items):
        item_span = source_spans[index] if source_spans and index < len(source_spans) else None
        if isinstance(item, list):
            nested, nested_spans, nested_expansion_count = _expand_sequence(
                item,
                macros=macros,
                max_expansion_depth=max_expansion_depth,
                depth=depth,
                gensym_state=gensym_state,
                expansion_trace=expansion_trace,
                expansion_frames=expansion_frames,
                macro_stack=macro_stack,
                source_spans=list(item_span.children) if item_span is not None else None,
                generated_by=generated_by,
                inherited_call_site=inherited_call_site,
                inherited_call_span=item_span.span if item_span is not None else inherited_call_span,
            )
            output.append(nested)
            output_spans.append(
                StackVmAstSpan(
                    span=item_span.span if item_span is not None else inherited_call_span or _unknown_span(),
                    children=tuple(nested_spans),
                )
            )
            expansion_count += nested_expansion_count
            continue

        if _is_symbol(item, "defmacro"):
            try:
                macro = _consume_macro_definition(output, output_spans, definition_span=item_span.span if item_span else None)
            except StackVmMacroExpansionError:
                raise
            except Exception as exc:
                raise _wrap_macro_error(exc, macro_stack) from exc
            macros[macro.name] = macro
            continue

        symbol_name = _symbol_name(item)
        if symbol_name and symbol_name in macros:
            macro = macros[symbol_name]
            try:
                if len(output) < len(macro.parameters):
                    raise ValueError(
                        f"StackVM macro '{macro.name}' expects {len(macro.parameters)} syntax arguments."
                    )
                args = [output.pop() for _ in macro.parameters]
                arg_spans = [output_spans.pop() for _ in macro.parameters]
                args.reverse()
                arg_spans.reverse()
                arguments = dict(zip(macro.parameters, args, strict=False))
                argument_spans = {
                    name: span
                    for name, span in zip(macro.parameters, arg_spans, strict=False)
                }
                substituted, substituted_spans = _substitute_template(
                    macro.template,
                    arguments,
                    argument_spans=argument_spans,
                )
                if macro.custom_expand is not None:
                    substituted, substituted_spans = macro.custom_expand(
                        arguments,
                        argument_spans,
                        gensym_state,
                    )
                elif macro.template_mode == "syntax":
                    substituted, substituted_spans = _expand_syntax_template(
                        macro.template,
                        arguments=arguments,
                        argument_spans=argument_spans,
                        gensym_state=gensym_state,
                    )
                expansion_trace.append(macro.name)
                frame = StackVmExpansionFrame(
                    macro_name=macro.name,
                    builtin=macro.builtin,
                    depth=depth,
                    call_site=_span_location(item_span.span) if item_span is not None else inherited_call_site,
                    definition_site=_span_location(macro.definition_span),
                    generated_by=generated_by,
                    syntax_args=[_serialize_compact(arg) for arg in args],
                    expanded_form=_serialize_compact(substituted),
                )
                expansion_frames.append(frame)
                call_span = item_span.span if item_span is not None else inherited_call_span
                generated_spans = _fill_missing_spans(substituted_spans, fallback_span=call_span)
                nested, nested_spans, nested_expansion_count = _expand_sequence(
                    substituted,
                    macros=macros,
                    max_expansion_depth=max_expansion_depth,
                    depth=depth + 1,
                    gensym_state=gensym_state,
                    expansion_trace=expansion_trace,
                    expansion_frames=expansion_frames,
                    macro_stack=(*macro_stack, macro.name),
                    source_spans=generated_spans,
                    generated_by=macro.name,
                    inherited_call_site=frame.call_site,
                    inherited_call_span=call_span,
                )
            except StackVmMacroExpansionError:
                raise
            except Exception as exc:
                raise _wrap_macro_error(exc, (*macro_stack, macro.name)) from exc
            output.extend(nested)
            output_spans.extend(nested_spans)
            expansion_count += 1 + nested_expansion_count
            continue

        output.append(item)
        output_spans.append(item_span or StackVmAstSpan(span=inherited_call_span or _unknown_span()))

    return output, output_spans, expansion_count


def _consume_macro_definition(
    output: list[StackVmAstNode],
    output_spans: list[StackVmAstSpan],
    *,
    definition_span: StackVmSourceSpan | None,
) -> MacroDefinition:
    if len(output) < 3:
        raise ValueError("StackVM defmacro expects parameter list, template quotation, and macro name.")

    name_node = output.pop()
    output_spans.pop()

    signature: list[Any] | None = None
    if output and isinstance(output[-1], tuple) and output[-1][0] == "sig":
        sig_node = output.pop()
        output_spans.pop()
        signature = sig_node[1]

    template_node = output.pop()
    output_spans.pop()
    template_mode = "plain"
    if _is_symbol(template_node, "syntax-quote"):
        template_mode = "syntax"
        if not output:
            raise ValueError("StackVM defmacro syntax-quote form is missing its template quotation.")
        template_node = output.pop()
        output_spans.pop()

    if not output:
        raise ValueError("StackVM defmacro is missing its parameter quotation.")
    params_node = output.pop()
    output_spans.pop()

    if not isinstance(params_node, list):
        raise TypeError("StackVM defmacro expects a quotation of parameter names.")
    if not isinstance(template_node, list):
        raise TypeError("StackVM defmacro expects a quotation template.")

    name = _literal_string(name_node)
    if not name:
        raise ValueError("StackVM defmacro requires a non-empty macro name.")

    params: list[str] = []
    for node in params_node:
        param_name = _symbol_name(node)
        if not param_name:
            raise TypeError("StackVM defmacro parameters must be symbols.")
        params.append(param_name)

    return MacroDefinition(
        name=name,
        parameters=tuple(params),
        template=_clone_nodes(template_node),
        template_mode=template_mode,
        definition_span=definition_span,
        explicit_signature=signature,
    )


def _substitute_template(
    template: list[StackVmAstNode],
    arguments: dict[str, StackVmAstNode],
    *,
    argument_spans: dict[str, StackVmAstSpan],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    items: list[StackVmAstNode] = []
    spans: list[StackVmAstSpan | None] = []
    for node in template:
        item, span = _substitute_node(node, arguments, argument_spans=argument_spans)
        items.append(item)
        spans.append(span)
    return items, spans


def _expand_syntax_template(
    template: list[StackVmAstNode],
    *,
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    return _expand_syntax_list(template, arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)


def _expand_syntax_list(
    items: list[StackVmAstNode],
    *,
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output: list[StackVmAstNode] = []
    output_spans: list[StackVmAstSpan | None] = []
    for item in items:
        if _is_compile_form(item, "unquote"):
            value, span = _evaluate_compile_expr(item[0], arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)
            output.append(value)
            output_spans.append(span)
            continue
        if _is_compile_form(item, "unquote-splice"):
            splice_value, splice_span = _evaluate_compile_expr(item[0], arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)
            if not isinstance(splice_value, list):
                raise TypeError("StackVM unquote-splice expects a quotation/list syntax value.")
            output.extend(_clone_nodes(splice_value))
            if splice_span is not None and splice_span.children:
                output_spans.extend(list(splice_span.children))
            else:
                output_spans.extend([splice_span] * len(splice_value))
            continue
        if _is_compile_form(item, "gensym"):
            value, span = _evaluate_compile_expr(item, arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)
            output.append(value)
            output_spans.append(span)
            continue
        if isinstance(item, list):
            nested, nested_spans = _expand_syntax_list(item, arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)
            output.append(nested)
            output_spans.append(StackVmAstSpan(span=_unknown_span(), children=tuple(span for span in nested_spans if span is not None)))
            continue
        output.append(_clone_node(item))
        output_spans.append(None)
    return output, output_spans


def _evaluate_compile_expr(
    node: StackVmAstNode,
    *,
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[StackVmAstNode, StackVmAstSpan | None]:
    symbol_name = _symbol_name(node)
    if symbol_name and symbol_name in arguments:
        return _clone_node(arguments[symbol_name]), argument_spans.get(symbol_name)

    if _is_compile_form(node, "gensym"):
        prefix = _literal_string(node[0]) or "gensym"
        gensym_state["count"] = int(gensym_state.get("count", 0)) + 1
        return ("sym", f"__{prefix}_{gensym_state['count']}"), None

    if isinstance(node, list):
        nested, nested_spans = _expand_syntax_list(node, arguments=arguments, argument_spans=argument_spans, gensym_state=gensym_state)
        return nested, StackVmAstSpan(span=_unknown_span(), children=tuple(span for span in nested_spans if span is not None))

    return _clone_node(node), None


def _substitute_node(
    node: StackVmAstNode,
    arguments: dict[str, StackVmAstNode],
    *,
    argument_spans: dict[str, StackVmAstSpan],
) -> tuple[StackVmAstNode, StackVmAstSpan | None]:
    if isinstance(node, list):
        items: list[StackVmAstNode] = []
        spans: list[StackVmAstSpan] = []
        for item in node:
            nested_item, nested_span = _substitute_node(item, arguments, argument_spans=argument_spans)
            items.append(nested_item)
            if nested_span is not None:
                spans.append(nested_span)
        return items, StackVmAstSpan(span=_unknown_span(), children=tuple(spans))

    symbol_name = _symbol_name(node)
    if symbol_name and symbol_name in arguments:
        return _clone_node(arguments[symbol_name]), argument_spans.get(symbol_name)
    return _clone_node(node), None


def _clone_nodes(items: list[StackVmAstNode]) -> list[StackVmAstNode]:
    return [_clone_node(item) for item in items]


def _clone_node(node: StackVmAstNode) -> StackVmAstNode:
    if isinstance(node, list):
        return [_clone_node(item) for item in node]
    return node


def _is_compile_form(node: StackVmAstNode, form_name: str) -> bool:
    return isinstance(node, list) and len(node) == 2 and _is_symbol(node[-1], form_name)


def _is_symbol(node: StackVmAstNode, symbol_name: str) -> bool:
    return _symbol_name(node) == symbol_name


def _symbol_name(node: StackVmAstNode) -> str | None:
    if isinstance(node, tuple) and len(node) == 2 and node[0] == "sym":
        return str(node[1])
    return None


def _literal_string(node: StackVmAstNode) -> str:
    if isinstance(node, tuple) and len(node) == 2 and node[0] in {"str", "sym"}:
        return str(node[1]).strip()
    return ""


def _literal_value(node: StackVmAstNode) -> Any:
    if isinstance(node, tuple) and len(node) == 2 and node[0] in {"str", "int", "float", "bool", "none"}:
        return node[1]
    raise TypeError(f"StackVM expected a plain literal value here, got {node!r}.")


def _dump_inline_yaml(value: Any) -> str:
    dumped = yaml.safe_dump(value, default_flow_style=True, sort_keys=False, width=10_000)
    if dumped.endswith("\n...\n"):
        dumped = dumped[:-5]
    elif dumped.endswith("\n"):
        dumped = dumped[:-1]
    return dumped


def _compile_choice_options(node: StackVmAstNode) -> list[dict[str, Any]]:
    if not isinstance(node, list):
        raise TypeError("StackVM choice option tables must be quotations of repeating id/label/value triples.")
    if len(node) % 3 != 0:
        raise ValueError("StackVM choice option tables expect repeating id/label/value triples.")
    options: list[dict[str, Any]] = []
    for index in range(0, len(node), 3):
        options.append(
            {
                "id": _literal_value(node[index]),
                "label": _literal_value(node[index + 1]),
                "value": _literal_value(node[index + 2]),
            }
        )
    return options


def _compile_choice_attrs(node: StackVmAstNode) -> dict[str, Any]:
    if not isinstance(node, list):
        raise TypeError("StackVM choice request attrs must be a quotation of repeating key/value pairs.")
    if len(node) % 2 != 0:
        raise ValueError("StackVM choice request attrs expect repeating key/value pairs.")
    attrs: dict[str, Any] = {}
    for index in range(0, len(node), 2):
        attrs[_literal_string(node[index])] = _literal_value(node[index + 1])
    return attrs


def _compile_field_specs(node: StackVmAstNode) -> list[tuple[StackVmAstNode, StackVmAstNode, StackVmAstNode]]:
    if not isinstance(node, list):
        raise TypeError("StackVM field specs must be a quotation of repeating source/store/default triplets.")
    if len(node) % 3 != 0:
        raise ValueError("StackVM field specs expect repeating source/store/default triplets.")
    specs: list[tuple[StackVmAstNode, StackVmAstNode, StackVmAstNode]] = []
    for index in range(0, len(node), 3):
        specs.append((node[index], node[index + 1], node[index + 2]))
    return specs


def _compile_record_field_specs(node: StackVmAstNode) -> list[tuple[StackVmAstNode, StackVmAstNode]]:
    if not isinstance(node, list):
        raise TypeError("StackVM record field specs must be a quotation of repeating path/value pairs.")
    if len(node) % 2 != 0:
        raise ValueError("StackVM record field specs expect repeating path/value pairs.")
    specs: list[tuple[StackVmAstNode, StackVmAstNode]] = []
    for index in range(0, len(node), 2):
        specs.append((node[index], node[index + 1]))
    return specs


def _compile_contract_items(node: StackVmAstNode) -> dict[str, StackVmAstNode]:
    if not isinstance(node, list):
        raise TypeError("StackVM workflow contracts must be quotations of repeating key/value pairs.")
    if len(node) % 2 != 0:
        raise ValueError("StackVM workflow contracts expect repeating key/value pairs.")
    contract: dict[str, StackVmAstNode] = {}
    for index in range(0, len(node), 2):
        key = _literal_string(node[index])
        if not key:
            raise TypeError("StackVM workflow contract keys must be plain strings.")
        contract[key] = node[index + 1]
    return contract


def _workflow_spec_registry(gensym_state: dict[str, int]) -> dict[str, StackVmAstNode]:
    registry = gensym_state.get("workflow_specs")
    if isinstance(registry, dict):
        return registry  # type: ignore[return-value]
    typed_registry: dict[str, StackVmAstNode] = {}
    gensym_state["workflow_specs"] = typed_registry  # type: ignore[assignment]
    return typed_registry


def _workflow_family_registry(gensym_state: dict[str, int]) -> dict[str, dict[str, StackVmAstNode]]:
    registry = gensym_state.get("workflow_families")
    if isinstance(registry, dict):
        return registry  # type: ignore[return-value]
    typed_registry: dict[str, dict[str, StackVmAstNode]] = {}
    gensym_state["workflow_families"] = typed_registry  # type: ignore[assignment]
    return typed_registry


def _merge_contract_items(
    base_contract: dict[str, StackVmAstNode],
    overrides_node: StackVmAstNode,
) -> dict[str, StackVmAstNode]:
    merged = dict(base_contract)
    merged.update(_compile_contract_items(overrides_node))
    return merged


def _compile_workflow_family_items(node: StackVmAstNode) -> dict[str, StackVmAstNode]:
    if not isinstance(node, list):
        raise TypeError("StackVM workflow families must be quotations of repeating section/value pairs.")
    if len(node) % 2 != 0:
        raise ValueError("StackVM workflow families expect repeating section/value pairs.")
    family: dict[str, StackVmAstNode] = {}
    for index in range(0, len(node), 2):
        key = _literal_string(node[index])
        if not key:
            raise TypeError("StackVM workflow family section keys must be plain strings.")
        value = node[index + 1]
        _compile_contract_items(value)
        family[key] = value
    return family


def _contract_node_from_mapping(contract: dict[str, StackVmAstNode]) -> list[StackVmAstNode]:
    return [
        item
        for key, value in contract.items()
        for item in (("str", key), _clone_node(value))
    ]


def _workflow_family_node_from_mapping(family: dict[str, StackVmAstNode]) -> list[StackVmAstNode]:
    return [
        item
        for key, value in family.items()
        for item in (("str", key), _clone_node(value))
    ]


def _require_contract_entry(
    contract: dict[str, StackVmAstNode],
    key: str,
    *,
    default: StackVmAstNode | None = None,
) -> StackVmAstNode:
    if key in contract:
        return contract[key]
    if default is not None:
        return default
    raise ValueError(f"StackVM workflow contract is missing required key '{key}'.")


def _serialize_runtime_value_expr(node: StackVmAstNode) -> str:
    if isinstance(node, list):
        return f'[ {_serialize_compact(node)} ] call'
    return _serialize_compact(node)


def _build_projection_quotation_from_field_specs(node: StackVmAstNode) -> str:
    projections: list[str] = []
    for source_path_node, store_path_node, default_node in _compile_field_specs(node):
        if isinstance(default_node, tuple) and len(default_node) == 2 and default_node[0] == "none":
            projection_expr = f'[ {_serialize_compact(source_path_node)} get-in? ]'
        else:
            projection_expr = (
                f'[ {_serialize_compact(source_path_node)} get-in? '
                f'dup none? [ drop {_serialize_compact(default_node)} ] [ ] if ]'
            )
        projections.append(f'{projection_expr} {_serialize_compact(store_path_node)}')
    return "[ " + " ".join(projections) + " ]"


def _build_record_fields_expression(
    base_expr_node: StackVmAstNode,
    field_specs_node: StackVmAstNode,
) -> str:
    operations: list[str] = [f'{_serialize_runtime_value_expr(base_expr_node)}']
    for path_node, value_node in _compile_record_field_specs(field_specs_node):
        operations.append(f'{_serialize_runtime_value_expr(value_node)} {_serialize_compact(path_node)} set-in')
    return " ".join(operations)


def _wrap_macro_error(exc: Exception, macro_trace: tuple[str, ...]) -> StackVmMacroExpansionError:
    if not macro_trace:
        raise exc
    if isinstance(exc, StackVmMacroExpansionError):
        if macro_trace:
            return StackVmMacroExpansionError(exc.message, (*macro_trace, *exc.macro_trace))
        return exc
    return StackVmMacroExpansionError(str(exc), macro_trace)


def _span_location(span: StackVmSourceSpan | None) -> str | None:
    if span is None:
        return None
    return span.location


def _build_generated_spans(
    items: list[StackVmAstNode],
    span: StackVmSourceSpan | None,
) -> list[StackVmAstSpan]:
    active_span = span or _unknown_span()
    spans: list[StackVmAstSpan] = []
    for item in items:
        if isinstance(item, list):
            children = _build_generated_spans(item, active_span)
            spans.append(StackVmAstSpan(span=active_span, children=tuple(children)))
        else:
            spans.append(StackVmAstSpan(span=active_span))
    return spans


def _fill_missing_spans(
    spans: list[StackVmAstSpan | None],
    *,
    fallback_span: StackVmSourceSpan | None,
) -> list[StackVmAstSpan]:
    filled: list[StackVmAstSpan] = []
    for span in spans:
        if span is None:
            filled.append(StackVmAstSpan(span=fallback_span or _unknown_span()))
            continue
        if span.children:
            filled.append(
                StackVmAstSpan(
                    span=span.span if span.span != _unknown_span() else (fallback_span or _unknown_span()),
                    children=tuple(_fill_missing_spans(list(span.children), fallback_span=fallback_span)),
                )
            )
            continue
        active_span = span.span if span.span != _unknown_span() else (fallback_span or _unknown_span())
        filled.append(StackVmAstSpan(span=active_span))
    return filled


def _unknown_span() -> StackVmSourceSpan:
    return StackVmSourceSpan(start_line=1, start_column=1, end_line=1, end_column=1)


def _serialize_compact(node: Any) -> str:
    if isinstance(node, list):
        return serialize_stackvm_ast(node)
    return serialize_stackvm_ast([node])


def _expand_builtin_handoff_rules(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    rules_node = arguments.get("rules")
    band_path_node = arguments.get("band_path")
    if not isinstance(rules_node, list):
        raise TypeError("StackVM handoff-rules expects a quotation of rule triplets.")

    if len(rules_node) % 3 != 0:
        raise ValueError("StackVM handoff-rules expects rules as repeating cond/band/agent triplets.")

    branches: list[str] = []
    rules_span = argument_spans.get("rules")
    branch_spans: list[StackVmAstSpan | None] = []
    band_path_source = _serialize_compact(band_path_node)
    child_spans = list(rules_span.children) if isinstance(rules_span, StackVmAstSpan) else []

    for index in range(0, len(rules_node), 3):
        cond_node = rules_node[index]
        band_node = rules_node[index + 1]
        agent_node = rules_node[index + 2]
        if not isinstance(cond_node, list):
            raise TypeError("StackVM handoff-rules condition entries must be quotations.")
        branches.append(
            f'[ {_serialize_compact(cond_node)} ] '
            f'[ {_serialize_compact(band_node)} {band_path_source} shared! {_serialize_compact(agent_node)} handoff ]'
        )
        branch_span = child_spans[index] if index < len(child_spans) else None
        branch_spans.extend([branch_span, branch_span])

    expanded = parse_stackvm_source(f'[ {" ".join(branches)} ] cond')
    return expanded, [StackVmAstSpan(span=_unknown_span(), children=tuple(span for span in branch_spans if span is not None)), None]


def _expand_builtin_handoff_switch(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    value_expr_node = arguments.get("value_expr")
    cases_node = arguments.get("cases")
    if not isinstance(cases_node, list):
        raise TypeError("StackVM handoff-switch expects a quotation of value/agent pairs.")
    if len(cases_node) % 2 != 0:
        raise ValueError("StackVM handoff-switch expects repeating value/agent pairs.")

    branches: list[str] = []
    cases_span = argument_spans.get("cases")
    child_spans = list(cases_span.children) if isinstance(cases_span, StackVmAstSpan) else []
    branch_spans: list[StackVmAstSpan | None] = []
    for index in range(0, len(cases_node), 2):
        value_node = cases_node[index]
        agent_node = cases_node[index + 1]
        branches.append(f'{_serialize_compact(value_node)} [ {_serialize_compact(agent_node)} handoff ]')
        branch_span = child_spans[index] if index < len(child_spans) else None
        branch_spans.extend([branch_span, branch_span])

    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(value_expr_node)} ] call [ {" ".join(branches)} ] switch'
    )
    value_span = argument_spans.get("value_expr")
    cases_ast_span = StackVmAstSpan(
        span=_unknown_span(),
        children=tuple(span for span in branch_spans if span is not None),
    )
    return expanded, [value_span, value_span, cases_ast_span, cases_ast_span, cases_ast_span, value_span]


def _expand_builtin_project_shared(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    projections_node = arguments.get("projections")
    body_node = arguments.get("body")
    if not isinstance(projections_node, list):
        raise TypeError("StackVM project-shared expects a quotation of projection/path pairs.")
    if len(projections_node) % 2 != 0:
        raise ValueError("StackVM project-shared expects repeating projection/path pairs.")

    gensym_state["count"] = int(gensym_state.get("count", 0)) + 1
    temp_name = f"__project_shared_{gensym_state['count']}"

    pieces = [f'dup "{temp_name}" store-set']
    for index in range(0, len(projections_node), 2):
        projection_node = projections_node[index]
        path_node = projections_node[index + 1]
        if not isinstance(projection_node, list):
            raise TypeError("StackVM project-shared projection entries must be quotations.")
        pieces.append(
            f'"{temp_name}" store-get '
            f'[ {_serialize_compact(projection_node)} ] call '
            f'{_serialize_compact(path_node)} shared!? drop'
        )
    pieces.append(f'drop None "{temp_name}" store-set')
    pieces.append(_serialize_compact(body_node))

    expanded = parse_stackvm_source(" ".join(pieces))
    projection_span = argument_spans.get("projections")
    body_span = argument_spans.get("body")
    child_spans = list(projection_span.children) if isinstance(projection_span, StackVmAstSpan) else []
    expanded_spans: list[StackVmAstSpan | None] = []
    for node in expanded:
        if isinstance(node, list) and body_span is not None:
            expanded_spans.append(body_span)
        elif isinstance(node, list) and child_spans:
            expanded_spans.append(child_spans[0])
        elif child_spans:
            expanded_spans.append(child_spans[0])
        else:
            expanded_spans.append(None)
    return expanded, expanded_spans


def _expand_builtin_finalize_from(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    value_expr_node = arguments.get("value_expr")
    expanded = parse_stackvm_source(f'[ {_serialize_compact(value_expr_node)} ] call answer')
    value_span = argument_spans.get("value_expr")
    return expanded, [value_span, value_span, value_span]


def _expand_builtin_prompt_store_contains_switch(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    request_expr_node = arguments.get("request_expr")
    value_path_node = arguments.get("value_path")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")
    if not isinstance(rules_node, list):
        raise TypeError("StackVM prompt-store-contains-switch expects a quotation of needle/body pairs.")
    if len(rules_node) % 2 != 0:
        raise ValueError("StackVM prompt-store-contains-switch expects repeating needle/body pairs.")

    def build_rule_chain(items: list[StackVmAstNode]) -> str:
        if not items:
            return "[ ]"
        needle_node = items[0]
        body_node = items[1]
        if not isinstance(body_node, list):
            raise TypeError("StackVM prompt-store-contains-switch branch bodies must be quotations.")
        if needle_node == ("str", "default") or _is_symbol(needle_node, "default"):
            return f'[ {_serialize_compact(body_node)} ] call'
        rest = build_rule_chain(items[2:])
        return (
            f'over {_serialize_compact(needle_node)} contains? '
            f'[ [ {_serialize_compact(body_node)} ] call ] '
            f'[ {rest} ] if'
        )

    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(request_expr_node)} ] call '
        'prompt-interaction '
        f'dup {_serialize_compact(value_path_node)} shared!? drop '
        f'[ {_serialize_compact(prepare_expr_node)} ] call '
        f'{build_rule_chain(rules_node)}'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_prompt_store_policy(
    arguments: dict[str, StackVmAstNode],
    argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    match_mode = _literal_string(arguments.get("match_mode"))
    if match_mode in {"exact", "switch"}:
        request_expr_node = arguments.get("request_expr")
        value_path_node = arguments.get("value_path")
        prepare_expr_node = arguments.get("prepare_expr")
        rules_node = arguments.get("rules")
        if not isinstance(rules_node, list):
            raise TypeError("StackVM prompt-store-policy expects a quotation of rules.")
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'[ {_serialize_compact(rules_node)} ] switch'
        )
        return expanded, [None] * len(expanded)

    if match_mode in {"contains", "membership"}:
        return _expand_builtin_prompt_store_contains_switch(arguments, argument_spans, gensym_state)

    raise ValueError("StackVM prompt-store-policy match_mode must be exact/switch or contains/membership.")


def _expand_builtin_returned_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    missing_case_node = arguments.get("missing_case")
    projections_node = arguments.get("projections")
    mode_node = arguments.get("mode")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")
    mode = _literal_string(mode_node)

    if mode in {"handoff", "route"}:
        if not isinstance(rules_node, list):
            raise TypeError("StackVM returned-policy in handoff mode expects a quotation of cases.")
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(missing_case_node)} ] '
            f'[ {_serialize_compact(projections_node)} ] '
            f'[ {_serialize_compact(value_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'returned-handoff-switch'
        )
        return expanded, [None] * len(expanded)

    if mode in {"finalize", "answer"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(missing_case_node)} ] '
            f'[ {_serialize_compact(projections_node)} ] '
            f'[ {_serialize_compact(value_expr_node)} ] '
            'returned-finalize'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM returned-policy mode must be handoff/route or finalize/answer.")


def _expand_builtin_prompt_return_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    request_expr_node = arguments.get("request_expr")
    value_path_node = arguments.get("value_path")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")
    match_mode = _literal_string(match_mode_node)

    if not isinstance(rules_node, list):
        raise TypeError("StackVM prompt-return-policy expects a quotation of rules.")
    if len(rules_node) % 2 != 0:
        raise ValueError("StackVM prompt-return-policy expects repeating rule/value pairs.")

    def build_exact_rules(items: list[StackVmAstNode]) -> str:
        branches: list[str] = []
        for index in range(0, len(items), 2):
            needle_node = items[index]
            body_node = items[index + 1]
            if not isinstance(body_node, list):
                raise TypeError("StackVM prompt-return-policy rule bodies must be quotations.")
            branches.append(
                f'{_serialize_compact(needle_node)} [ [ {_serialize_compact(body_node)} ] call answer ]'
            )
        return " ".join(branches)

    def build_contains_rules(items: list[StackVmAstNode]) -> str:
        if not items:
            return "[ ]"
        needle_node = items[0]
        body_node = items[1]
        if not isinstance(body_node, list):
            raise TypeError("StackVM prompt-return-policy rule bodies must be quotations.")
        if needle_node == ("str", "default") or _is_symbol(needle_node, "default"):
            return f'[ {_serialize_compact(body_node)} ] call answer'
        rest = build_contains_rules(items[2:])
        return (
            f'over {_serialize_compact(needle_node)} contains? '
            f'[ [ {_serialize_compact(body_node)} ] call answer ] '
            f'[ {rest} ] if'
        )

    if match_mode in {"exact", "switch"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'[ {build_exact_rules(rules_node)} ] switch'
        )
        return expanded, [None] * len(expanded)

    if match_mode in {"contains", "membership"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'{build_contains_rules(rules_node)}'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM prompt-return-policy match_mode must be exact/switch or contains/membership.")


def _expand_builtin_prompt_return_yaml_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    request_expr_node = arguments.get("request_expr")
    value_path_node = arguments.get("value_path")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")
    match_mode = _literal_string(match_mode_node)

    if not isinstance(rules_node, list):
        raise TypeError("StackVM prompt-return-yaml-policy expects a quotation of rules.")
    if len(rules_node) % 2 != 0:
        raise ValueError("StackVM prompt-return-yaml-policy expects repeating rule/value pairs.")

    def build_exact_rules(items: list[StackVmAstNode]) -> str:
        branches: list[str] = []
        for index in range(0, len(items), 2):
            needle_node = items[index]
            body_node = items[index + 1]
            if not isinstance(body_node, list):
                raise TypeError("StackVM prompt-return-yaml-policy rule bodies must be quotations.")
            branches.append(
                f'{_serialize_compact(needle_node)} [ [ {_serialize_compact(body_node)} ] call yaml< answer ]'
            )
        return " ".join(branches)

    def build_contains_rules(items: list[StackVmAstNode]) -> str:
        if not items:
            return "[ ]"
        needle_node = items[0]
        body_node = items[1]
        if not isinstance(body_node, list):
            raise TypeError("StackVM prompt-return-yaml-policy rule bodies must be quotations.")
        if needle_node == ("str", "default") or _is_symbol(needle_node, "default"):
            return f'[ {_serialize_compact(body_node)} ] call yaml< answer'
        rest = build_contains_rules(items[2:])
        return (
            f'over {_serialize_compact(needle_node)} contains? '
            f'[ [ {_serialize_compact(body_node)} ] call yaml< answer ] '
            f'[ {rest} ] if'
        )

    if match_mode in {"exact", "switch"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'[ {build_exact_rules(rules_node)} ] switch'
        )
        return expanded, [None] * len(expanded)

    if match_mode in {"contains", "membership"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'{build_contains_rules(rules_node)}'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM prompt-return-yaml-policy match_mode must be exact/switch or contains/membership.")


def _expand_builtin_prompt_return_merge_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    request_expr_node = arguments.get("request_expr")
    value_path_node = arguments.get("value_path")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")
    match_mode = _literal_string(match_mode_node)

    if not isinstance(rules_node, list):
        raise TypeError("StackVM prompt-return-merge-policy expects a quotation of rules.")
    if len(rules_node) % 2 != 0:
        raise ValueError("StackVM prompt-return-merge-policy expects repeating rule/value pairs.")

    def build_exact_rules(items: list[StackVmAstNode]) -> str:
        branches: list[str] = []
        for index in range(0, len(items), 2):
            needle_node = items[index]
            body_node = items[index + 1]
            if not isinstance(body_node, list):
                raise TypeError("StackVM prompt-return-merge-policy rule bodies must be quotations.")
            branches.append(
                f'{_serialize_compact(needle_node)} '
                f'[ [ {_serialize_compact(base_expr_node)} ] call [ {_serialize_compact(body_node)} ] call merge yaml< answer ]'
            )
        return " ".join(branches)

    def build_contains_rules(items: list[StackVmAstNode]) -> str:
        if not items:
            return "[ ]"
        needle_node = items[0]
        body_node = items[1]
        if not isinstance(body_node, list):
            raise TypeError("StackVM prompt-return-merge-policy rule bodies must be quotations.")
        if needle_node == ("str", "default") or _is_symbol(needle_node, "default"):
            return (
                f'[ {_serialize_compact(base_expr_node)} ] call '
                f'[ {_serialize_compact(body_node)} ] call merge yaml< answer'
            )
        rest = build_contains_rules(items[2:])
        return (
            f'over {_serialize_compact(needle_node)} contains? '
            f'[ [ {_serialize_compact(base_expr_node)} ] call [ {_serialize_compact(body_node)} ] call merge yaml< answer ] '
            f'[ {rest} ] if'
        )

    if match_mode in {"exact", "switch"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'[ {build_exact_rules(rules_node)} ] switch'
        )
        return expanded, [None] * len(expanded)

    if match_mode in {"contains", "membership"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] call '
            'prompt-interaction '
            f'dup {_serialize_compact(value_path_node)} shared!? drop '
            f'[ {_serialize_compact(prepare_expr_node)} ] call '
            f'{build_contains_rules(rules_node)}'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM prompt-return-merge-policy match_mode must be exact/switch or contains/membership.")


def _expand_builtin_prompt_decision(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode = _literal_string(arguments.get("output_mode"))
    request_expr_node = arguments.get("request_expr")
    value_path_node = arguments.get("value_path")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    if output_mode in {"answer", "text", "plain"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] '
            f'{_serialize_compact(value_path_node)} '
            f'{_serialize_compact(match_mode_node)} '
            f'[ {_serialize_compact(prepare_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'prompt-return-policy'
        )
        return expanded, [None] * len(expanded)

    if output_mode in {"yaml", "mapping"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] '
            f'{_serialize_compact(value_path_node)} '
            f'{_serialize_compact(match_mode_node)} '
            f'[ {_serialize_compact(prepare_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'prompt-return-yaml-policy'
        )
        return expanded, [None] * len(expanded)

    if output_mode in {"yaml-merge", "merge", "nested"}:
        expanded = parse_stackvm_source(
            f'[ {_serialize_compact(request_expr_node)} ] '
            f'{_serialize_compact(value_path_node)} '
            f'{_serialize_compact(match_mode_node)} '
            f'[ {_serialize_compact(prepare_expr_node)} ] '
            f'[ {_serialize_compact(base_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'prompt-return-merge-policy'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM prompt-decision output_mode must be answer/text/plain, yaml/mapping, or yaml-merge/merge/nested.")


def _expand_builtin_choice_request(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind = _literal_string(arguments.get("kind"))
    prompt_expr_node = arguments.get("prompt_expr")
    options = _compile_choice_options(arguments.get("options"))
    attrs = _compile_choice_attrs(arguments.get("attrs"))

    request: dict[str, Any] = {
        "kind": kind,
        "prompt": "placeholder",
        "options": options,
    }
    request.update(attrs)
    if kind == "checklist" and "min_selected" not in request:
        request["min_selected"] = 1

    request_yaml = json.dumps(_dump_inline_yaml(request))
    expanded = parse_stackvm_source(
        f"{request_yaml} yaml> "
        f'"prompt" [ {_serialize_compact(prompt_expr_node)} ] call dict-set'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_choice_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_expr_node = arguments.get("prompt_expr")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_expr_node)} ] '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        'choice-request ] '
        f'{_serialize_compact(value_path_node)} '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'prompt-store-policy'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_choice_decision(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode_node = arguments.get("output_mode")
    kind_node = arguments.get("kind")
    prompt_expr_node = arguments.get("prompt_expr")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(output_mode_node)} '
        f'[ {_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_expr_node)} ] '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        'choice-request ] '
        f'{_serialize_compact(value_path_node)} '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'prompt-decision'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_record_fields(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    base_expr_node = arguments.get("base_expr")
    field_specs_node = arguments.get("field_specs")
    expanded = parse_stackvm_source(_build_record_fields_expression(base_expr_node, field_specs_node))
    return expanded, [None] * len(expanded)


def _expand_builtin_choice_structured_decision(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_expr_node = arguments.get("prompt_expr")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    if not isinstance(rules_node, list):
        raise TypeError("StackVM choice-structured-decision expects a quotation of rules.")
    if len(rules_node) % 2 != 0:
        raise ValueError("StackVM choice-structured-decision expects repeating rule/value pairs.")

    transformed_rules: list[str] = []
    for index in range(0, len(rules_node), 2):
        needle_node = rules_node[index]
        field_specs_node = rules_node[index + 1]
        transformed_rules.append(
            f'{_serialize_compact(needle_node)} '
            f'[ [ {_serialize_compact(base_expr_node)} ] [ {_serialize_compact(field_specs_node)} ] record-fields ]'
        )

    expanded = parse_stackvm_source(
        '"yaml" '
        f'{_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_expr_node)} ] '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        '[ ] '
        f'[ {" ".join(transformed_rules)} ] '
        'choice-decision'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_choice_contract(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode = _literal_string(arguments.get("output_mode"))
    kind_node = arguments.get("kind")
    prompt_expr_node = arguments.get("prompt_expr")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    if output_mode in {"structured", "fields", "yaml-fields", "contract"}:
        expanded = parse_stackvm_source(
            f'{_serialize_compact(kind_node)} '
            f'[ {_serialize_compact(prompt_expr_node)} ] '
            f'{_serialize_compact(value_path_node)} '
            f'[ {_serialize_compact(options_node)} ] '
            f'[ {_serialize_compact(attrs_node)} ] '
            f'{_serialize_compact(match_mode_node)} '
            f'[ {_serialize_compact(prepare_expr_node)} ] '
            f'[ {_serialize_compact(base_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'choice-structured-decision'
        )
        return expanded, [None] * len(expanded)

    expanded = parse_stackvm_source(
        f'{_serialize_compact(arguments.get("output_mode"))} '
        f'{_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_expr_node)} ] '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'choice-decision'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_choice_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode = _literal_string(arguments.get("output_mode"))
    kind_node = arguments.get("kind")
    prompt_expr_node = arguments.get("prompt_expr")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    if output_mode in {"continue", "direct", "policy", "actions", "route-cases"}:
        expanded = parse_stackvm_source(
            f'{_serialize_compact(kind_node)} '
            f'[ {_serialize_compact(prompt_expr_node)} ] '
            f'{_serialize_compact(value_path_node)} '
            f'[ {_serialize_compact(options_node)} ] '
            f'[ {_serialize_compact(attrs_node)} ] '
            f'{_serialize_compact(match_mode_node)} '
            f'[ {_serialize_compact(prepare_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'choice-policy'
        )
        return expanded, [None] * len(expanded)

    expanded = parse_stackvm_source(
        f'{_serialize_compact(arguments.get("output_mode"))} '
        f'{_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_expr_node)} ] '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'choice-contract'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_summary_choice_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode_node = arguments.get("output_mode")
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(output_mode_node)} '
        f'{_serialize_compact(kind_node)} '
        f'[ {_serialize_compact(prompt_prefix_node)} "normalized.summary" shared@ concat ] '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'choice-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_summary_answer_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        '"answer" '
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        '[ ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'summary-choice-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_summary_structured_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        '"structured" '
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'summary-choice-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_delegate_answer_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'summary-answer-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_delegate_structured_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'summary-structured-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalize_loaded_payload(
    _arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    expanded = parse_stackvm_source(
        'payload-data "payload" store-set '
        '"payload" store-get normalize-item-titles '
        '"payload" store-get store-normalized-source '
        'store-normalized-summary'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalized_choice_router(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    output_mode_node = arguments.get("output_mode")
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    base_expr_node = arguments.get("base_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        '[ last-tool-result failure? '
        '[ "Could not load the payload." answer ] '
        '[ normalize-loaded-payload '
        f'{_serialize_compact(output_mode_node)} '
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(base_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'summary-choice-flow ] '
        'if ] '
        'stdlib.io.read-yaml-file-once'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalized_continue_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        '"continue" '
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        '[ ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'normalized-choice-router'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_router_continue_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    kind_node = arguments.get("kind")
    prompt_prefix_node = arguments.get("prompt_prefix")
    value_path_node = arguments.get("value_path")
    options_node = arguments.get("options")
    attrs_node = arguments.get("attrs")
    match_mode_node = arguments.get("match_mode")
    prepare_expr_node = arguments.get("prepare_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(kind_node)} '
        f'{_serialize_compact(prompt_prefix_node)} '
        f'{_serialize_compact(value_path_node)} '
        f'[ {_serialize_compact(options_node)} ] '
        f'[ {_serialize_compact(attrs_node)} ] '
        f'{_serialize_compact(match_mode_node)} '
        f'[ {_serialize_compact(prepare_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'normalized-continue-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_continue_workflow_contract(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    contract = _compile_contract_items(arguments.get("contract"))
    role = _literal_string(contract.get("role", ("str", "router")))
    if role not in {"router", "continue"}:
        raise ValueError("StackVM continue-workflow-contract role must be router/continue when provided.")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(_require_contract_entry(contract, "payload_file"))} '
        f'{_serialize_compact(_require_contract_entry(contract, "kind"))} '
        f'{_serialize_compact(_require_contract_entry(contract, "prompt_prefix"))} '
        f'{_serialize_compact(_require_contract_entry(contract, "value_path"))} '
        f'[ {_serialize_compact(_require_contract_entry(contract, "options"))} ] '
        f'[ {_serialize_compact(_require_contract_entry(contract, "attrs", default=[]))} ] '
        f'{_serialize_compact(_require_contract_entry(contract, "match_mode"))} '
        f'[ {_serialize_compact(_require_contract_entry(contract, "prepare_expr", default=[]))} ] '
        f'[ {_serialize_compact(_require_contract_entry(contract, "rules"))} ] '
        'router-continue-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_workflow_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    spec = _compile_contract_items(arguments.get("spec"))
    role = _literal_string(arguments.get("role"))
    policy = _literal_string(arguments.get("policy"))

    if role == "router":
        if policy != "continue":
            raise ValueError("StackVM workflow-spec role 'router' only supports policy 'continue'.")
        expanded = parse_stackvm_source(
            '[ '
            f'"payload_file" {_serialize_compact(_require_contract_entry(spec, "payload_file"))} '
            f'"kind" {_serialize_compact(_require_contract_entry(spec, "kind"))} '
            f'"prompt_prefix" {_serialize_compact(_require_contract_entry(spec, "prompt_prefix"))} '
            f'"value_path" {_serialize_compact(_require_contract_entry(spec, "value_path"))} '
            f'"options" [ {_serialize_compact(_require_contract_entry(spec, "options"))} ] '
            f'"attrs" [ {_serialize_compact(_require_contract_entry(spec, "attrs", default=[]))} ] '
            f'"match_mode" {_serialize_compact(_require_contract_entry(spec, "match_mode"))} '
            f'"prepare_expr" [ {_serialize_compact(_require_contract_entry(spec, "prepare_expr", default=[]))} ] '
            f'"rules" [ {_serialize_compact(_require_contract_entry(spec, "continue_rules"))} ] '
            '] continue-workflow-contract'
        )
        return expanded, [None] * len(expanded)

    if role == "caller":
        if policy == "answer":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "caller" '
                f'"payload_file" {_serialize_compact(_require_contract_entry(spec, "payload_file"))} '
                f'"delegate_target" {_serialize_compact(_require_contract_entry(spec, "delegate_target"))} '
                f'"missing_case" [ {_serialize_compact(_require_contract_entry(spec, "missing_case"))} ] '
                f'"value_expr" [ {_serialize_compact(_require_contract_entry(spec, "caller_value_expr"))} ] '
                '] answer-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        if policy == "route":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "caller" '
                f'"payload_file" {_serialize_compact(_require_contract_entry(spec, "payload_file"))} '
                f'"delegate_target" {_serialize_compact(_require_contract_entry(spec, "delegate_target"))} '
                f'"missing_case" [ {_serialize_compact(_require_contract_entry(spec, "missing_case"))} ] '
                f'"field_specs" [ {_serialize_compact(_require_contract_entry(spec, "caller_field_specs"))} ] '
                f'"value_expr" [ {_serialize_compact(_require_contract_entry(spec, "caller_value_expr"))} ] '
                f'"rules" [ {_serialize_compact(_require_contract_entry(spec, "caller_rules"))} ] '
                '] route-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        if policy == "finalize":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "caller" '
                f'"payload_file" {_serialize_compact(_require_contract_entry(spec, "payload_file"))} '
                f'"delegate_target" {_serialize_compact(_require_contract_entry(spec, "delegate_target"))} '
                f'"missing_case" [ {_serialize_compact(_require_contract_entry(spec, "missing_case"))} ] '
                f'"field_specs" [ {_serialize_compact(_require_contract_entry(spec, "caller_field_specs"))} ] '
                f'"value_expr" [ {_serialize_compact(_require_contract_entry(spec, "caller_value_expr"))} ] '
                '] finalize-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        raise ValueError("StackVM workflow-spec role 'caller' only supports answer/route/finalize policies.")

    if role == "delegate":
        if policy == "answer":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "delegate" '
                f'"kind" {_serialize_compact(_require_contract_entry(spec, "kind"))} '
                f'"prompt_prefix" {_serialize_compact(_require_contract_entry(spec, "prompt_prefix"))} '
                f'"value_path" {_serialize_compact(_require_contract_entry(spec, "value_path"))} '
                f'"options" [ {_serialize_compact(_require_contract_entry(spec, "options"))} ] '
                f'"attrs" [ {_serialize_compact(_require_contract_entry(spec, "attrs", default=[]))} ] '
                f'"match_mode" {_serialize_compact(_require_contract_entry(spec, "match_mode"))} '
                f'"prepare_expr" [ {_serialize_compact(_require_contract_entry(spec, "prepare_expr", default=[]))} ] '
                f'"rules" [ {_serialize_compact(_require_contract_entry(spec, "delegate_rules"))} ] '
                '] answer-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        if policy == "route":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "delegate" '
                f'"kind" {_serialize_compact(_require_contract_entry(spec, "kind"))} '
                f'"prompt_prefix" {_serialize_compact(_require_contract_entry(spec, "prompt_prefix"))} '
                f'"value_path" {_serialize_compact(_require_contract_entry(spec, "value_path"))} '
                f'"options" [ {_serialize_compact(_require_contract_entry(spec, "options"))} ] '
                f'"attrs" [ {_serialize_compact(_require_contract_entry(spec, "attrs", default=[]))} ] '
                f'"match_mode" {_serialize_compact(_require_contract_entry(spec, "match_mode"))} '
                f'"prepare_expr" [ {_serialize_compact(_require_contract_entry(spec, "prepare_expr", default=[]))} ] '
                f'"base_expr" [ {_serialize_compact(_require_contract_entry(spec, "delegate_base_expr"))} ] '
                f'"rules" [ {_serialize_compact(_require_contract_entry(spec, "delegate_rules"))} ] '
                '] route-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        if policy == "finalize":
            expanded = parse_stackvm_source(
                '[ '
                '"role" "delegate" '
                f'"kind" {_serialize_compact(_require_contract_entry(spec, "kind"))} '
                f'"prompt_prefix" {_serialize_compact(_require_contract_entry(spec, "prompt_prefix"))} '
                f'"value_path" {_serialize_compact(_require_contract_entry(spec, "value_path"))} '
                f'"options" [ {_serialize_compact(_require_contract_entry(spec, "options"))} ] '
                f'"attrs" [ {_serialize_compact(_require_contract_entry(spec, "attrs", default=[]))} ] '
                f'"match_mode" {_serialize_compact(_require_contract_entry(spec, "match_mode"))} '
                f'"prepare_expr" [ {_serialize_compact(_require_contract_entry(spec, "prepare_expr", default=[]))} ] '
                f'"base_expr" [ {_serialize_compact(_require_contract_entry(spec, "delegate_base_expr"))} ] '
                f'"rules" [ {_serialize_compact(_require_contract_entry(spec, "delegate_rules"))} ] '
                '] finalize-workflow-contract'
            )
            return expanded, [None] * len(expanded)
        raise ValueError("StackVM workflow-spec role 'delegate' only supports answer/route/finalize policies.")

    raise ValueError("StackVM workflow-spec role must be router, caller, or delegate.")


def _expand_builtin_define_workflow_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-workflow-spec requires a non-empty plain string name.")
    spec_node = arguments.get("spec")
    _compile_contract_items(spec_node)
    _workflow_spec_registry(gensym_state)[name] = _clone_node(spec_node)
    return [], []


def _expand_builtin_extend_workflow_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    base_name = _literal_string(arguments.get("base_name"))
    name = _literal_string(arguments.get("name"))
    if not base_name or not name:
        raise ValueError("StackVM extend-workflow-spec requires non-empty base and target names.")
    registry = _workflow_spec_registry(gensym_state)
    if base_name not in registry:
        raise ValueError(f"StackVM extend-workflow-spec could not find workflow spec '{base_name}'.")
    merged = _merge_contract_items(
        _compile_contract_items(registry[base_name]),
        arguments.get("overrides"),
    )
    registry[name] = [
        item
        for key, value in merged.items()
        for item in (("str", key), _clone_node(value))
    ]
    return [], []


def _expand_builtin_use_workflow_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    role = _literal_string(arguments.get("role"))
    policy = _literal_string(arguments.get("policy"))
    registry = _workflow_spec_registry(gensym_state)
    if name not in registry:
        raise ValueError(f"StackVM use-workflow-spec could not find workflow spec '{name}'.")
    spec_node = registry[name]
    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(spec_node)} ] '
        f'{_serialize_compact(("str", role))} '
        f'{_serialize_compact(("str", policy))} '
        'workflow-spec'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_define_workflow_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-workflow-family requires a non-empty plain string name.")
    family_node = arguments.get("family")
    compiled = _compile_workflow_family_items(family_node)
    _workflow_family_registry(gensym_state)[name] = {
        key: _clone_node(value)
        for key, value in compiled.items()
    }
    return [], []


def _expand_builtin_extend_workflow_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    base_name = _literal_string(arguments.get("base_name"))
    name = _literal_string(arguments.get("name"))
    if not base_name or not name:
        raise ValueError("StackVM extend-workflow-family requires non-empty base and target names.")
    registry = _workflow_family_registry(gensym_state)
    if base_name not in registry:
        raise ValueError(f"StackVM extend-workflow-family could not find workflow family '{base_name}'.")
    merged = dict(registry[base_name])
    merged.update(_compile_workflow_family_items(arguments.get("overrides")))
    registry[name] = {
        key: _clone_node(value)
        for key, value in merged.items()
    }
    return [], []


def _expand_builtin_use_workflow_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    role = _literal_string(arguments.get("role"))
    policy = _literal_string(arguments.get("policy"))
    if not name:
        raise ValueError("StackVM use-workflow-family requires a non-empty family name.")
    registry = _workflow_family_registry(gensym_state)
    if name not in registry:
        raise ValueError(f"StackVM use-workflow-family could not find workflow family '{name}'.")
    family = registry[name]
    section_key = f"{role}.{policy}"
    if section_key not in family:
        raise ValueError(
            f"StackVM use-workflow-family could not find section '{section_key}' in workflow family '{name}'."
        )
    merged_contract = _compile_contract_items(family.get("shared", []))
    merged_contract.update(_compile_contract_items(family[section_key]))
    spec_node = [
        item
        for key, value in merged_contract.items()
        for item in (("str", key), _clone_node(value))
    ]
    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(spec_node)} ] '
        f'{_serialize_compact(("str", role))} '
        f'{_serialize_compact(("str", policy))} '
        'workflow-spec'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_define_choice_continue_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-continue-spec requires a non-empty plain string name.")
    contract = {
        "payload_file": _clone_node(arguments.get("payload_file")),
        "kind": _clone_node(arguments.get("kind")),
        "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
        "value_path": _clone_node(arguments.get("value_path")),
        "options": _clone_node(arguments.get("options")),
        "attrs": _clone_node(arguments.get("attrs")),
        "match_mode": _clone_node(arguments.get("match_mode")),
        "prepare_expr": _clone_node(arguments.get("prepare_expr")),
        "continue_rules": _clone_node(arguments.get("rules")),
    }
    _workflow_spec_registry(gensym_state)[name] = _contract_node_from_mapping(contract)
    return [], []


def _expand_builtin_define_choice_answer_spec(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-answer-spec requires a non-empty plain string name.")
    contract = {
        "kind": _clone_node(arguments.get("kind")),
        "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
        "value_path": _clone_node(arguments.get("value_path")),
        "options": _clone_node(arguments.get("options")),
        "attrs": _clone_node(arguments.get("attrs")),
        "match_mode": _clone_node(arguments.get("match_mode")),
        "prepare_expr": _clone_node(arguments.get("prepare_expr")),
        "delegate_rules": _clone_node(arguments.get("delegate_rules")),
    }
    _workflow_spec_registry(gensym_state)[name] = _contract_node_from_mapping(contract)
    return [], []


def _expand_builtin_define_choice_answer_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-answer-family requires a non-empty plain string name.")
    family = {
        "caller.answer": _contract_node_from_mapping(
            {
                "payload_file": _clone_node(arguments.get("payload_file")),
                "delegate_target": _clone_node(arguments.get("delegate_target")),
                "missing_case": _clone_node(arguments.get("missing_case")),
                "caller_value_expr": _clone_node(arguments.get("caller_value_expr")),
            }
        ),
        "delegate.answer": _contract_node_from_mapping(
            {
                "kind": _clone_node(arguments.get("kind")),
                "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
                "value_path": _clone_node(arguments.get("value_path")),
                "options": _clone_node(arguments.get("options")),
                "attrs": _clone_node(arguments.get("attrs")),
                "match_mode": _clone_node(arguments.get("match_mode")),
                "prepare_expr": _clone_node(arguments.get("prepare_expr")),
                "delegate_rules": _clone_node(arguments.get("delegate_rules")),
            }
        ),
    }
    _workflow_family_registry(gensym_state)[name] = family
    return [], []


def _expand_builtin_define_choice_continue_answer_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-continue-answer-family requires a non-empty plain string name.")
    family = {
        "router.continue": _contract_node_from_mapping(
            {
                "payload_file": _clone_node(arguments.get("payload_file")),
                "kind": _clone_node(arguments.get("kind")),
                "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
                "value_path": _clone_node(arguments.get("value_path")),
                "options": _clone_node(arguments.get("options")),
                "attrs": _clone_node(arguments.get("attrs")),
                "match_mode": _clone_node(arguments.get("match_mode")),
                "prepare_expr": _clone_node(arguments.get("prepare_expr")),
                "continue_rules": _clone_node(arguments.get("continue_rules")),
            }
        ),
        "delegate.answer": _contract_node_from_mapping(
            {
                "kind": _clone_node(arguments.get("delegate_kind")),
                "prompt_prefix": _clone_node(arguments.get("delegate_prompt_prefix")),
                "value_path": _clone_node(arguments.get("delegate_value_path")),
                "options": _clone_node(arguments.get("delegate_options")),
                "attrs": _clone_node(arguments.get("delegate_attrs")),
                "match_mode": _clone_node(arguments.get("delegate_match_mode")),
                "prepare_expr": _clone_node(arguments.get("delegate_prepare_expr")),
                "delegate_rules": _clone_node(arguments.get("delegate_rules")),
            }
        ),
    }
    _workflow_family_registry(gensym_state)[name] = family
    return [], []


def _expand_builtin_define_choice_route_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-route-family requires a non-empty plain string name.")
    family = {
        "caller.route": _contract_node_from_mapping(
            {
                "payload_file": _clone_node(arguments.get("payload_file")),
                "delegate_target": _clone_node(arguments.get("delegate_target")),
                "missing_case": _clone_node(arguments.get("missing_case")),
                "caller_field_specs": _clone_node(arguments.get("caller_field_specs")),
                "caller_value_expr": _clone_node(arguments.get("caller_value_expr")),
                "caller_rules": _clone_node(arguments.get("caller_rules")),
            }
        ),
        "delegate.route": _contract_node_from_mapping(
            {
                "kind": _clone_node(arguments.get("kind")),
                "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
                "value_path": _clone_node(arguments.get("value_path")),
                "options": _clone_node(arguments.get("options")),
                "attrs": _clone_node(arguments.get("attrs")),
                "match_mode": _clone_node(arguments.get("match_mode")),
                "prepare_expr": _clone_node(arguments.get("prepare_expr")),
                "delegate_base_expr": _clone_node(arguments.get("delegate_base_expr")),
                "delegate_rules": _clone_node(arguments.get("delegate_rules")),
            }
        ),
    }
    _workflow_family_registry(gensym_state)[name] = family
    return [], []


def _expand_builtin_define_choice_finalize_family(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    name = _literal_string(arguments.get("name"))
    if not name:
        raise ValueError("StackVM define-choice-finalize-family requires a non-empty plain string name.")
    family = {
        "caller.finalize": _contract_node_from_mapping(
            {
                "payload_file": _clone_node(arguments.get("payload_file")),
                "delegate_target": _clone_node(arguments.get("delegate_target")),
                "missing_case": _clone_node(arguments.get("missing_case")),
                "caller_field_specs": _clone_node(arguments.get("caller_field_specs")),
                "caller_value_expr": _clone_node(arguments.get("caller_value_expr")),
            }
        ),
        "delegate.finalize": _contract_node_from_mapping(
            {
                "kind": _clone_node(arguments.get("kind")),
                "prompt_prefix": _clone_node(arguments.get("prompt_prefix")),
                "value_path": _clone_node(arguments.get("value_path")),
                "options": _clone_node(arguments.get("options")),
                "attrs": _clone_node(arguments.get("attrs")),
                "match_mode": _clone_node(arguments.get("match_mode")),
                "prepare_expr": _clone_node(arguments.get("prepare_expr")),
                "delegate_base_expr": _clone_node(arguments.get("delegate_base_expr")),
                "delegate_rules": _clone_node(arguments.get("delegate_rules")),
            }
        ),
    }
    _workflow_family_registry(gensym_state)[name] = family
    return [], []


def _expand_builtin_return_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    resume_body_node = arguments.get("resume_body")

    expanded = parse_stackvm_source(
        '"last_delegated_result" shared@ none? '
        f'[ {_serialize_compact(payload_file_node)} '
        '[ last-tool-result failure? '
        '[ "Could not load the payload." answer ] '
        f'[ [ {_serialize_compact(load_body_node)} ] call '
        f'{_serialize_compact(delegate_target_node)} return-handoff ] '
        'if ] '
        'stdlib.io.read-yaml-file-once ] '
        f'[ [ {_serialize_compact(resume_body_node)} ] call ] '
        'if'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_project_fields(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    field_specs_node = arguments.get("field_specs")
    body_node = arguments.get("body")
    expanded = parse_stackvm_source(
        f'{_build_projection_quotation_from_field_specs(field_specs_node)} '
        f'[ {_serialize_compact(body_node)} ] '
        'project-shared'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_returned_field_policy(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    mode_node = arguments.get("mode")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")
    expanded = parse_stackvm_source(
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'{_build_projection_quotation_from_field_specs(field_specs_node)} '
        f'{_serialize_compact(mode_node)} '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'returned-policy'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_return_contract_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode = _literal_string(arguments.get("output_mode"))
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")

    if output_mode in {"answer", "text", "plain"}:
        expanded = parse_stackvm_source(
            f'{_serialize_compact(payload_file_node)} '
            f'[ {_serialize_compact(load_body_node)} ] '
            f'{_serialize_compact(delegate_target_node)} '
            f'[ {_serialize_compact(missing_case_node)} ] '
            f'[ {_serialize_compact(value_expr_node)} ] '
            'return-answer-flow'
        )
        return expanded, [None] * len(expanded)

    if output_mode in {"route", "handoff"}:
        expanded = parse_stackvm_source(
            f'{_serialize_compact(payload_file_node)} '
            f'[ {_serialize_compact(load_body_node)} ] '
            f'{_serialize_compact(delegate_target_node)} '
            f'[ {_serialize_compact(missing_case_node)} ] '
            f'[ {_serialize_compact(field_specs_node)} ] '
            f'[ {_serialize_compact(value_expr_node)} ] '
            f'[ {_serialize_compact(rules_node)} ] '
            'return-field-route-flow'
        )
        return expanded, [None] * len(expanded)

    if output_mode in {"finalize", "structured-finalize"}:
        expanded = parse_stackvm_source(
            f'{_serialize_compact(payload_file_node)} '
            f'[ {_serialize_compact(load_body_node)} ] '
            f'{_serialize_compact(delegate_target_node)} '
            f'[ {_serialize_compact(missing_case_node)} ] '
            f'[ {_serialize_compact(field_specs_node)} ] '
            f'[ {_serialize_compact(value_expr_node)} ] '
            'return-field-finalize-flow'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM return-contract-flow output_mode must be answer/plain, route/handoff, or finalize.")


def _expand_builtin_normalized_return_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    output_mode_node = arguments.get("output_mode")
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(output_mode_node)} '
        f'{_serialize_compact(payload_file_node)} '
        '[ normalize-loaded-payload ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(field_specs_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'return-contract-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalized_answer_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    value_expr_node = arguments.get("value_expr")

    expanded = parse_stackvm_source(
        '"answer" '
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        '[ ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        '[ ] '
        'normalized-return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalized_route_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        '"route" '
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(field_specs_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'normalized-return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_normalized_finalize_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")

    expanded = parse_stackvm_source(
        '"finalize" '
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(field_specs_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        '[ ] '
        'normalized-return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_caller_answer_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    value_expr_node = arguments.get("value_expr")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        'normalized-answer-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_caller_route_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(field_specs_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'normalized-route-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_caller_finalize_workflow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(field_specs_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        'normalized-finalize-workflow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_answer_workflow_contract(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    contract = _compile_contract_items(arguments.get("contract"))
    role = _literal_string(_require_contract_entry(contract, "role"))

    if role == "caller":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "payload_file"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "delegate_target"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "missing_case"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "value_expr"))} ] '
            'caller-answer-workflow'
        )
        return expanded, [None] * len(expanded)

    if role == "delegate":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "kind"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "prompt_prefix"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "value_path"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "options"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "attrs", default=[]))} ] '
            f'{_serialize_compact(_require_contract_entry(contract, "match_mode"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "prepare_expr", default=[]))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "rules"))} ] '
            'delegate-answer-workflow'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM answer-workflow-contract role must be caller or delegate.")


def _expand_builtin_route_workflow_contract(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    contract = _compile_contract_items(arguments.get("contract"))
    role = _literal_string(_require_contract_entry(contract, "role"))

    if role == "caller":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "payload_file"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "delegate_target"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "missing_case"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "field_specs"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "value_expr"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "rules"))} ] '
            'caller-route-workflow'
        )
        return expanded, [None] * len(expanded)

    if role == "delegate":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "kind"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "prompt_prefix"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "value_path"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "options"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "attrs", default=[]))} ] '
            f'{_serialize_compact(_require_contract_entry(contract, "match_mode"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "prepare_expr", default=[]))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "base_expr"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "rules"))} ] '
            'delegate-structured-workflow'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM route-workflow-contract role must be caller or delegate.")


def _expand_builtin_finalize_workflow_contract(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    contract = _compile_contract_items(arguments.get("contract"))
    role = _literal_string(_require_contract_entry(contract, "role"))

    if role == "caller":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "payload_file"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "delegate_target"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "missing_case"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "field_specs"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "value_expr"))} ] '
            'caller-finalize-workflow'
        )
        return expanded, [None] * len(expanded)

    if role == "delegate":
        expanded = parse_stackvm_source(
            f'{_serialize_compact(_require_contract_entry(contract, "kind"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "prompt_prefix"))} '
            f'{_serialize_compact(_require_contract_entry(contract, "value_path"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "options"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "attrs", default=[]))} ] '
            f'{_serialize_compact(_require_contract_entry(contract, "match_mode"))} '
            f'[ {_serialize_compact(_require_contract_entry(contract, "prepare_expr", default=[]))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "base_expr"))} ] '
            f'[ {_serialize_compact(_require_contract_entry(contract, "rules"))} ] '
            'delegate-structured-workflow'
        )
        return expanded, [None] * len(expanded)

    raise ValueError("StackVM finalize-workflow-contract role must be caller or delegate.")


def _expand_builtin_return_answer_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    value_expr_node = arguments.get("value_expr")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'[ {_serialize_compact(load_body_node)} ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ [ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(value_expr_node)} ] '
        'returned-answer-policy ] '
        'return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_return_field_policy_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    mode_node = arguments.get("mode")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")
    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'[ {_serialize_compact(load_body_node)} ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ [ {_serialize_compact(missing_case_node)} ] '
        f'{_build_projection_quotation_from_field_specs(field_specs_node)} '
        f'{_serialize_compact(mode_node)} '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'returned-policy ] '
        'return-flow'
    )
    return expanded, [None] * len(expanded)
    

def _expand_builtin_return_field_route_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")
    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'[ {_serialize_compact(load_body_node)} ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ [ {_serialize_compact(missing_case_node)} ] '
        f'{_build_projection_quotation_from_field_specs(field_specs_node)} '
        '"handoff" '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'returned-policy ] '
        'return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_return_field_finalize_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    field_specs_node = arguments.get("field_specs")
    value_expr_node = arguments.get("value_expr")
    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'[ {_serialize_compact(load_body_node)} ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ [ {_serialize_compact(missing_case_node)} ] '
        f'{_build_projection_quotation_from_field_specs(field_specs_node)} '
        '"finalize" '
        f'[ {_serialize_compact(value_expr_node)} ] '
        '[ ] '
        'returned-policy ] '
        'return-flow'
    )
    return expanded, [None] * len(expanded)


def _expand_builtin_return_policy_flow(
    arguments: dict[str, StackVmAstNode],
    _argument_spans: dict[str, StackVmAstSpan],
    _gensym_state: dict[str, int],
) -> tuple[list[StackVmAstNode], list[StackVmAstSpan | None]]:
    payload_file_node = arguments.get("payload_file")
    load_body_node = arguments.get("load_body")
    delegate_target_node = arguments.get("delegate_target")
    missing_case_node = arguments.get("missing_case")
    projections_node = arguments.get("projections")
    mode_node = arguments.get("mode")
    value_expr_node = arguments.get("value_expr")
    rules_node = arguments.get("rules")

    expanded = parse_stackvm_source(
        f'{_serialize_compact(payload_file_node)} '
        f'[ {_serialize_compact(load_body_node)} ] '
        f'{_serialize_compact(delegate_target_node)} '
        f'[ [ {_serialize_compact(missing_case_node)} ] '
        f'[ {_serialize_compact(projections_node)} ] '
        f'{_serialize_compact(mode_node)} '
        f'[ {_serialize_compact(value_expr_node)} ] '
        f'[ {_serialize_compact(rules_node)} ] '
        'returned-policy ] '
        'return-flow'
    )
    return expanded, [None] * len(expanded)


def _builtin_macro_definitions() -> dict[str, MacroDefinition]:
    return {
        "when": MacroDefinition(
            name="when",
            parameters=("cond", "body"),
            template=parse_stackvm_source(
                '[ cond unquote ] [ [ body unquote ] call ] [ ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "unless": MacroDefinition(
            name="unless",
            parameters=("cond", "body"),
            template=parse_stackvm_source(
                '[ cond unquote ] not [ [ body unquote ] call ] [ ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "shared-or": MacroDefinition(
            name="shared-or",
            parameters=("path", "fallback"),
            template=parse_stackvm_source(
                '[ path unquote ] shared@ dup none? [ drop [ fallback unquote ] ] [ ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "shared-handoff": MacroDefinition(
            name="shared-handoff",
            parameters=("value", "path", "target_agent"),
            template=parse_stackvm_source(
                '[ value unquote ] [ path unquote ] shared! '
                '[ target_agent unquote ] handoff'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "tool-once": MacroDefinition(
            name="tool-once",
            parameters=("tool_name", "args_expr", "later_turn"),
            template=parse_stackvm_source(
                'last-tool-result none? '
                '[ [ tool_name unquote ] [ args_expr unquote ] call tool-request ] '
                '[ [ later_turn unquote ] call ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "delegate-return": MacroDefinition(
            name="delegate-return",
            parameters=("target_agent", "result_path"),
            template=parse_stackvm_source(
                '[ result_path unquote ] shared@ none? '
                '[ [ target_agent unquote ] handoff ] '
                '[ [ result_path unquote ] shared@ answer ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "return-handoff": MacroDefinition(
            name="return-handoff",
            parameters=("target_agent",),
            template=parse_stackvm_source(
                '"{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml> '
                '"pending_handoff_policy" store-set '
                '[ target_agent unquote ] handoff'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "return-delegate": MacroDefinition(
            name="return-delegate",
            parameters=("target_agent", "result_path"),
            template=parse_stackvm_source(
                '[ result_path unquote ] shared@ none? '
                '[ "{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml> '
                '"pending_handoff_policy" store-set '
                '[ target_agent unquote ] handoff ] '
                '[ [ result_path unquote ] shared@ answer ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "return-flow": MacroDefinition(
            name="return-flow",
            parameters=("payload_file", "load_body", "delegate_target", "resume_body"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_flow,
        ),
        "project-fields": MacroDefinition(
            name="project-fields",
            parameters=("field_specs", "body"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_project_fields,
        ),
        "return-answer-flow": MacroDefinition(
            name="return-answer-flow",
            parameters=("payload_file", "load_body", "delegate_target", "missing_case", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_answer_flow,
        ),
        "return-contract-flow": MacroDefinition(
            name="return-contract-flow",
            parameters=(
                "output_mode",
                "payload_file",
                "load_body",
                "delegate_target",
                "missing_case",
                "field_specs",
                "value_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_contract_flow,
        ),
        "normalized-return-flow": MacroDefinition(
            name="normalized-return-flow",
            parameters=(
                "output_mode",
                "payload_file",
                "delegate_target",
                "missing_case",
                "field_specs",
                "value_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_return_flow,
        ),
        "normalized-answer-workflow": MacroDefinition(
            name="normalized-answer-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_answer_workflow,
        ),
        "caller-answer-workflow": MacroDefinition(
            name="caller-answer-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_caller_answer_workflow,
        ),
        "normalized-route-workflow": MacroDefinition(
            name="normalized-route-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "field_specs", "value_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_route_workflow,
        ),
        "caller-route-workflow": MacroDefinition(
            name="caller-route-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "field_specs", "value_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_caller_route_workflow,
        ),
        "normalized-finalize-workflow": MacroDefinition(
            name="normalized-finalize-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "field_specs", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_finalize_workflow,
        ),
        "caller-finalize-workflow": MacroDefinition(
            name="caller-finalize-workflow",
            parameters=("payload_file", "delegate_target", "missing_case", "field_specs", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_caller_finalize_workflow,
        ),
        "answer-workflow-contract": MacroDefinition(
            name="answer-workflow-contract",
            parameters=("contract",),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_answer_workflow_contract,
        ),
        "route-workflow-contract": MacroDefinition(
            name="route-workflow-contract",
            parameters=("contract",),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_route_workflow_contract,
        ),
        "finalize-workflow-contract": MacroDefinition(
            name="finalize-workflow-contract",
            parameters=("contract",),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_finalize_workflow_contract,
        ),
        "return-field-policy-flow": MacroDefinition(
            name="return-field-policy-flow",
            parameters=(
                "payload_file",
                "load_body",
                "delegate_target",
                "missing_case",
                "field_specs",
                "mode",
                "value_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_field_policy_flow,
        ),
        "return-field-route-flow": MacroDefinition(
            name="return-field-route-flow",
            parameters=("payload_file", "load_body", "delegate_target", "missing_case", "field_specs", "value_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_field_route_flow,
        ),
        "return-field-finalize-flow": MacroDefinition(
            name="return-field-finalize-flow",
            parameters=("payload_file", "load_body", "delegate_target", "missing_case", "field_specs", "value_expr"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_field_finalize_flow,
        ),
        "return-policy-flow": MacroDefinition(
            name="return-policy-flow",
            parameters=(
                "payload_file",
                "load_body",
                "delegate_target",
                "missing_case",
                "projections",
                "mode",
                "value_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_return_policy_flow,
        ),
        "maybe-handoff": MacroDefinition(
            name="maybe-handoff",
            parameters=("value_expr", "missing_case"),
            template=parse_stackvm_source(
                '[ value_expr unquote ] call '
                'dup none? '
                '[ drop [ missing_case unquote ] call ] '
                '[ handoff ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "indexed-value": MacroDefinition(
            name="indexed-value",
            parameters=("list_expr", "index_expr", "missing_case", "body"),
            template=parse_stackvm_source(
                '[ list_expr unquote ] call '
                '[ index_expr unquote ] call '
                'list-get? '
                'dup none? '
                '[ drop [ missing_case unquote ] call ] '
                '[ [ body unquote ] call ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "indexed-handoff-route": MacroDefinition(
            name="indexed-handoff-route",
            parameters=("list_expr", "index_expr", "missing_reason", "fallback_agent", "body"),
            template=parse_stackvm_source(
                '[ list_expr unquote ] '
                '[ index_expr unquote ] '
                '[ [ missing_reason unquote ] "route_reason" [ fallback_agent unquote ] shared-handoff ] '
                '[ body unquote ] '
                'indexed-value'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "prompt-store-switch": MacroDefinition(
            name="prompt-store-switch",
            parameters=("request_expr", "value_path", "cases"),
            template=parse_stackvm_source(
                '[ request_expr unquote ] call '
                'prompt-interaction '
                'dup [ value_path unquote ] shared!? drop '
                '[ cases unquote ] switch'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "prompt-store-policy": MacroDefinition(
            name="prompt-store-policy",
            parameters=("request_expr", "value_path", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_store_policy,
        ),
        "choice-request": MacroDefinition(
            name="choice-request",
            parameters=("kind", "prompt_expr", "options", "attrs"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_request,
        ),
        "normalize-loaded-payload": MacroDefinition(
            name="normalize-loaded-payload",
            parameters=(),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalize_loaded_payload,
        ),
        "summary-choice-flow": MacroDefinition(
            name="summary-choice-flow",
            parameters=(
                "output_mode",
                "kind",
                "prompt_prefix",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_summary_choice_flow,
        ),
        "summary-answer-workflow": MacroDefinition(
            name="summary-answer-workflow",
            parameters=("kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_summary_answer_workflow,
        ),
        "delegate-answer-workflow": MacroDefinition(
            name="delegate-answer-workflow",
            parameters=("kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_delegate_answer_workflow,
        ),
        "summary-structured-workflow": MacroDefinition(
            name="summary-structured-workflow",
            parameters=("kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "base_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_summary_structured_workflow,
        ),
        "delegate-structured-workflow": MacroDefinition(
            name="delegate-structured-workflow",
            parameters=("kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "base_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_delegate_structured_workflow,
        ),
        "normalized-choice-router": MacroDefinition(
            name="normalized-choice-router",
            parameters=(
                "payload_file",
                "output_mode",
                "kind",
                "prompt_prefix",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_choice_router,
        ),
        "normalized-continue-workflow": MacroDefinition(
            name="normalized-continue-workflow",
            parameters=("payload_file", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_normalized_continue_workflow,
        ),
        "router-continue-workflow": MacroDefinition(
            name="router-continue-workflow",
            parameters=("payload_file", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_router_continue_workflow,
        ),
        "continue-workflow-contract": MacroDefinition(
            name="continue-workflow-contract",
            parameters=("contract",),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_continue_workflow_contract,
        ),
        "workflow-spec": MacroDefinition(
            name="workflow-spec",
            parameters=("spec", "role", "policy"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_workflow_spec,
        ),
        "define-workflow-spec": MacroDefinition(
            name="define-workflow-spec",
            parameters=("name", "spec"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_workflow_spec,
        ),
        "extend-workflow-spec": MacroDefinition(
            name="extend-workflow-spec",
            parameters=("base_name", "name", "overrides"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_extend_workflow_spec,
        ),
        "use-workflow-spec": MacroDefinition(
            name="use-workflow-spec",
            parameters=("name", "role", "policy"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_use_workflow_spec,
        ),
        "define-workflow-family": MacroDefinition(
            name="define-workflow-family",
            parameters=("name", "family"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_workflow_family,
        ),
        "extend-workflow-family": MacroDefinition(
            name="extend-workflow-family",
            parameters=("base_name", "name", "overrides"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_extend_workflow_family,
        ),
        "use-workflow-family": MacroDefinition(
            name="use-workflow-family",
            parameters=("name", "role", "policy"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_use_workflow_family,
        ),
        "define-choice-continue-spec": MacroDefinition(
            name="define-choice-continue-spec",
            parameters=("name", "payload_file", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_continue_spec,
        ),
        "define-choice-answer-spec": MacroDefinition(
            name="define-choice-answer-spec",
            parameters=("name", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "delegate_rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_answer_spec,
        ),
        "define-choice-answer-family": MacroDefinition(
            name="define-choice-answer-family",
            parameters=("name", "payload_file", "delegate_target", "missing_case", "caller_value_expr", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "delegate_rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_answer_family,
        ),
        "define-choice-continue-answer-family": MacroDefinition(
            name="define-choice-continue-answer-family",
            parameters=("name", "payload_file", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "continue_rules", "delegate_kind", "delegate_prompt_prefix", "delegate_value_path", "delegate_options", "delegate_attrs", "delegate_match_mode", "delegate_prepare_expr", "delegate_rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_continue_answer_family,
        ),
        "define-choice-route-family": MacroDefinition(
            name="define-choice-route-family",
            parameters=("name", "payload_file", "delegate_target", "missing_case", "caller_field_specs", "caller_value_expr", "caller_rules", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "delegate_base_expr", "delegate_rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_route_family,
        ),
        "define-choice-finalize-family": MacroDefinition(
            name="define-choice-finalize-family",
            parameters=("name", "payload_file", "delegate_target", "missing_case", "caller_field_specs", "caller_value_expr", "kind", "prompt_prefix", "value_path", "options", "attrs", "match_mode", "prepare_expr", "delegate_base_expr", "delegate_rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_define_choice_finalize_family,
        ),
        "choice-policy": MacroDefinition(
            name="choice-policy",
            parameters=("kind", "prompt_expr", "value_path", "options", "attrs", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_policy,
        ),
        "prompt-return-policy": MacroDefinition(
            name="prompt-return-policy",
            parameters=("request_expr", "value_path", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_return_policy,
        ),
        "prompt-return-yaml-policy": MacroDefinition(
            name="prompt-return-yaml-policy",
            parameters=("request_expr", "value_path", "match_mode", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_return_yaml_policy,
        ),
        "prompt-return-merge-policy": MacroDefinition(
            name="prompt-return-merge-policy",
            parameters=("request_expr", "value_path", "match_mode", "prepare_expr", "base_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_return_merge_policy,
        ),
        "prompt-decision": MacroDefinition(
            name="prompt-decision",
            parameters=("output_mode", "request_expr", "value_path", "match_mode", "prepare_expr", "base_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_decision,
        ),
        "choice-decision": MacroDefinition(
            name="choice-decision",
            parameters=(
                "output_mode",
                "kind",
                "prompt_expr",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_decision,
        ),
        "choice-contract": MacroDefinition(
            name="choice-contract",
            parameters=(
                "output_mode",
                "kind",
                "prompt_expr",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_contract,
        ),
        "choice-flow": MacroDefinition(
            name="choice-flow",
            parameters=(
                "output_mode",
                "kind",
                "prompt_expr",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_flow,
        ),
        "record-fields": MacroDefinition(
            name="record-fields",
            parameters=("base_expr", "field_specs"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_record_fields,
        ),
        "choice-structured-decision": MacroDefinition(
            name="choice-structured-decision",
            parameters=(
                "kind",
                "prompt_expr",
                "value_path",
                "options",
                "attrs",
                "match_mode",
                "prepare_expr",
                "base_expr",
                "rules",
            ),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_choice_structured_decision,
        ),
        "prompt-store-contains-switch": MacroDefinition(
            name="prompt-store-contains-switch",
            parameters=("request_expr", "value_path", "prepare_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_prompt_store_contains_switch,
        ),
        "finalize-from": MacroDefinition(
            name="finalize-from",
            parameters=("value_expr",),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_finalize_from,
        ),
        "validated-match": MacroDefinition(
            name="validated-match",
            parameters=("result_expr", "cases", "invalid_case"),
            template=parse_stackvm_source(
                '[ result_expr unquote ] call '
                'dup "success" dict-get? '
                '[ "value" dict-get? [ cases unquote ] match ] '
                '[ [ invalid_case unquote ] call ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "schema-route": MacroDefinition(
            name="schema-route",
            parameters=("errors_path", "value_store_path", "cases", "invalid_case"),
            template=parse_stackvm_source(
                'dup "errors" dict-get? [ errors_path unquote ] shared! '
                '[ [ value_store_path unquote ] none? [ ] [ dup "value" dict-get? dup [ value_store_path unquote ] store-set drop ] if ] '
                '[ cases unquote ] '
                '[ invalid_case unquote ] '
                'validated-match'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "handoff-rules": MacroDefinition(
            name="handoff-rules",
            parameters=("rules", "band_path"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_handoff_rules,
        ),
        "handoff-switch": MacroDefinition(
            name="handoff-switch",
            parameters=("value_expr", "cases"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_handoff_switch,
        ),
        "project-shared": MacroDefinition(
            name="project-shared",
            parameters=("projections", "body"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_project_shared,
        ),
        "returned-handoff-switch": MacroDefinition(
            name="returned-handoff-switch",
            parameters=("missing_case", "projections", "value_expr", "cases"),
            template=parse_stackvm_source(
                '[ missing_case unquote ] '
                '[ [ projections unquote ] [ [ value_expr unquote ] [ cases unquote ] handoff-switch ] project-shared ] '
                'returned-yaml'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "returned-policy": MacroDefinition(
            name="returned-policy",
            parameters=("missing_case", "projections", "mode", "value_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_returned_policy,
        ),
        "returned-field-policy": MacroDefinition(
            name="returned-field-policy",
            parameters=("missing_case", "field_specs", "mode", "value_expr", "rules"),
            template=[],
            builtin=True,
            custom_expand=_expand_builtin_returned_field_policy,
        ),
        "returned-finalize": MacroDefinition(
            name="returned-finalize",
            parameters=("missing_case", "projections", "value_expr"),
            template=parse_stackvm_source(
                '[ missing_case unquote ] '
                '[ [ projections unquote ] [ [ value_expr unquote ] finalize-from ] project-shared ] '
                'returned-yaml'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "returned-yaml": MacroDefinition(
            name="returned-yaml",
            parameters=("missing_case", "body"),
            template=parse_stackvm_source(
                '"last_delegated_result" shared@ "answer" dict-get dup none? '
                '[ drop [ missing_case unquote ] call ] '
                '[ yaml> [ body unquote ] call ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "returned-answer": MacroDefinition(
            name="returned-answer",
            parameters=("missing_case", "body"),
            template=parse_stackvm_source(
                '"last_delegated_result" shared@ "answer" dict-get dup none? '
                '[ drop [ missing_case unquote ] call ] '
                '[ [ body unquote ] call ] if'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "returned-answer-policy": MacroDefinition(
            name="returned-answer-policy",
            parameters=("missing_case", "value_expr"),
            template=parse_stackvm_source(
                '[ missing_case unquote ] '
                '[ [ value_expr unquote ] finalize-from ] '
                'returned-answer'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "prompt-store": MacroDefinition(
            name="prompt-store",
            parameters=("request_expr", "value_path", "body"),
            template=parse_stackvm_source(
                '[ request_expr unquote ] call '
                'prompt-interaction '
                'dup [ value_path unquote ] shared!? drop '
                '[ body unquote ] call'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "ask-from": MacroDefinition(
            name="ask-from",
            parameters=("question_expr",),
            template=parse_stackvm_source(
                '[ question_expr unquote ] call ask-user'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "prompt-store-text": MacroDefinition(
            name="prompt-store-text",
            parameters=("question_expr", "value_path", "body"),
            template=parse_stackvm_source(
                '[ question_expr unquote ] call '
                'prompt-user '
                'dup [ value_path unquote ] shared!? drop '
                '[ body unquote ] call'
            ),
            template_mode="syntax",
            builtin=True,
        ),
        "prompt-route": MacroDefinition(
            name="prompt-route",
            parameters=("request_expr", "cases"),
            template=parse_stackvm_source(
                '[ request_expr unquote ] call prompt-interaction [ cases unquote ] switch'
            ),
            template_mode="syntax",
            builtin=True,
        ),
    }
