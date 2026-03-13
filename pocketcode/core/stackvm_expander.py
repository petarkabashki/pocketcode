from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pocketcode.core.stackvm_parser import parse_stackvm_source


StackVmAstNode = Any


@dataclass(frozen=True)
class MacroDefinition:
    name: str
    parameters: tuple[str, ...]
    template: list[StackVmAstNode]
    template_mode: str = "plain"
    builtin: bool = False


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
    macros: dict[str, MacroDefinition] = field(default_factory=dict)
    expansion_count: int = 0
    gensym_count: int = 0
    expansion_trace: list[str] = field(default_factory=list)


def expand_stackvm_source(code: str, *, max_expansion_depth: int = 32) -> StackVmExpansionResult:
    ast = parse_stackvm_source(code)
    return expand_stackvm_ast(ast, max_expansion_depth=max_expansion_depth)


def expand_stackvm_ast(
    ast: list[StackVmAstNode],
    *,
    max_expansion_depth: int = 32,
    macros: dict[str, MacroDefinition] | None = None,
    _depth: int = 0,
) -> StackVmExpansionResult:
    if _depth > max_expansion_depth:
        raise RecursionError(f"StackVM macro expansion exceeded max depth ({max_expansion_depth}).")

    registry = _builtin_macro_definitions()
    if macros:
        registry.update(macros)
    gensym_state = {"count": 0}
    expansion_trace: list[str] = []
    expanded, expansion_count = _expand_sequence(
        ast,
        macros=registry,
        max_expansion_depth=max_expansion_depth,
        depth=_depth,
        gensym_state=gensym_state,
        expansion_trace=expansion_trace,
        macro_stack=(),
    )
    return StackVmExpansionResult(
        ast=expanded,
        macros=registry,
        expansion_count=expansion_count,
        gensym_count=int(gensym_state["count"]),
        expansion_trace=expansion_trace,
    )


def _expand_sequence(
    items: list[StackVmAstNode],
    *,
    macros: dict[str, MacroDefinition],
    max_expansion_depth: int,
    depth: int,
    gensym_state: dict[str, int],
    expansion_trace: list[str],
    macro_stack: tuple[str, ...],
) -> tuple[list[StackVmAstNode], int]:
    output: list[StackVmAstNode] = []
    expansion_count = 0

    for item in items:
        if isinstance(item, list):
            nested, nested_expansion_count = _expand_sequence(
                item,
                macros=macros,
                max_expansion_depth=max_expansion_depth,
                depth=depth,
                gensym_state=gensym_state,
                expansion_trace=expansion_trace,
                macro_stack=macro_stack,
            )
            output.append(nested)
            expansion_count += nested_expansion_count
            continue

        if _is_symbol(item, "defmacro"):
            try:
                macro = _consume_macro_definition(output)
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
                args.reverse()
                arguments = dict(zip(macro.parameters, args, strict=False))
                substituted = _substitute_template(macro.template, arguments)
                if macro.template_mode == "syntax":
                    substituted = _expand_syntax_template(
                        macro.template,
                        arguments=arguments,
                        gensym_state=gensym_state,
                    )
                expansion_trace.append(macro.name)
                nested, nested_expansion_count = _expand_sequence(
                    substituted,
                    macros=macros,
                    max_expansion_depth=max_expansion_depth,
                    depth=depth + 1,
                    gensym_state=gensym_state,
                    expansion_trace=expansion_trace,
                    macro_stack=(*macro_stack, macro.name),
                )
            except StackVmMacroExpansionError:
                raise
            except Exception as exc:
                raise _wrap_macro_error(exc, (*macro_stack, macro.name)) from exc
            output.extend(nested)
            expansion_count += 1 + nested_expansion_count
            continue

        output.append(item)

    return output, expansion_count


def _consume_macro_definition(output: list[StackVmAstNode]) -> MacroDefinition:
    if len(output) < 3:
        raise ValueError("StackVM defmacro expects parameter list, template quotation, and macro name.")

    name_node = output.pop()
    template_node = output.pop()
    template_mode = "plain"
    if _is_symbol(template_node, "syntax-quote"):
        template_mode = "syntax"
        if not output:
            raise ValueError("StackVM defmacro syntax-quote form is missing its template quotation.")
        template_node = output.pop()

    if not output:
        raise ValueError("StackVM defmacro is missing its parameter quotation.")
    params_node = output.pop()

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
    )


def _substitute_template(
    template: list[StackVmAstNode],
    arguments: dict[str, StackVmAstNode],
) -> list[StackVmAstNode]:
    return [_substitute_node(node, arguments) for node in template]


def _expand_syntax_template(
    template: list[StackVmAstNode],
    *,
    arguments: dict[str, StackVmAstNode],
    gensym_state: dict[str, int],
) -> list[StackVmAstNode]:
    return _expand_syntax_list(template, arguments=arguments, gensym_state=gensym_state)


def _expand_syntax_list(
    items: list[StackVmAstNode],
    *,
    arguments: dict[str, StackVmAstNode],
    gensym_state: dict[str, int],
) -> list[StackVmAstNode]:
    output: list[StackVmAstNode] = []
    for item in items:
        if _is_compile_form(item, "unquote"):
            output.append(_evaluate_compile_expr(item[0], arguments=arguments, gensym_state=gensym_state))
            continue
        if _is_compile_form(item, "unquote-splice"):
            splice_value = _evaluate_compile_expr(item[0], arguments=arguments, gensym_state=gensym_state)
            if not isinstance(splice_value, list):
                raise TypeError("StackVM unquote-splice expects a quotation/list syntax value.")
            output.extend(_clone_nodes(splice_value))
            continue
        if _is_compile_form(item, "gensym"):
            output.append(_evaluate_compile_expr(item, arguments=arguments, gensym_state=gensym_state))
            continue
        if isinstance(item, list):
            output.append(_expand_syntax_list(item, arguments=arguments, gensym_state=gensym_state))
            continue
        output.append(_clone_node(item))
    return output


def _evaluate_compile_expr(
    node: StackVmAstNode,
    *,
    arguments: dict[str, StackVmAstNode],
    gensym_state: dict[str, int],
) -> StackVmAstNode:
    symbol_name = _symbol_name(node)
    if symbol_name and symbol_name in arguments:
        return _clone_node(arguments[symbol_name])

    if _is_compile_form(node, "gensym"):
        prefix = _literal_string(node[0]) or "gensym"
        gensym_state["count"] = int(gensym_state.get("count", 0)) + 1
        return ("sym", f"__{prefix}_{gensym_state['count']}")

    if isinstance(node, list):
        return _expand_syntax_list(node, arguments=arguments, gensym_state=gensym_state)

    return _clone_node(node)


def _substitute_node(node: StackVmAstNode, arguments: dict[str, StackVmAstNode]) -> StackVmAstNode:
    if isinstance(node, list):
        return [_substitute_node(item, arguments) for item in node]

    symbol_name = _symbol_name(node)
    if symbol_name and symbol_name in arguments:
        return _clone_node(arguments[symbol_name])
    return _clone_node(node)


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


def _wrap_macro_error(exc: Exception, macro_trace: tuple[str, ...]) -> StackVmMacroExpansionError:
    if not macro_trace:
        raise exc
    if isinstance(exc, StackVmMacroExpansionError):
        if macro_trace:
            return StackVmMacroExpansionError(exc.message, (*macro_trace, *exc.macro_trace))
        return exc
    return StackVmMacroExpansionError(str(exc), macro_trace)


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
        "finalize-from": MacroDefinition(
            name="finalize-from",
            parameters=("value_expr",),
            template=parse_stackvm_source(
                '[ value_expr unquote ] call answer'
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
