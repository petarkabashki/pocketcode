from __future__ import annotations

from typing import Any

from pocketcode.core.stackvm_parser import StackVmSourceToken, tokenize_stackvm_source

STACKVM_COMPILE_ONLY_FORMS = {
    "defmacro",
    "syntax-quote",
    "unquote",
    "unquote-splice",
    "gensym",
    "module",
    "export",
    "import",
}


def validate_stackvm_ast(ast: list[Any]) -> None:
    for node in ast:
        _validate_stackvm_node(node)


def collect_stackvm_authoring_warnings(ast: list[Any], *, source: str | None = None) -> list[dict[str, Any]]:
    if source:
        return _collect_source_authoring_warnings(source)

    warnings: list[dict[str, Any]] = []
    _collect_authoring_warnings(ast, warnings)
    return warnings


def _collect_authoring_warnings(nodes: list[Any], warnings: list[dict[str, Any]]) -> None:
    for start_index in range(max(len(nodes) - 3, 0)):
        if _matches_manual_tool_loop(nodes, start_index):
            warnings.append(_make_warning("manual-tool-loop"))
        if _matches_manual_prompt_route(nodes, start_index):
            warnings.append(_make_warning("manual-prompt-route"))

    for node in nodes:
        if isinstance(node, list):
            _collect_authoring_warnings(node, warnings)


def _validate_stackvm_node(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _validate_stackvm_node(item)
        return

    if not isinstance(node, tuple) or len(node) != 2:
        raise TypeError(f"Unsupported StackVM AST node {node!r}")

    token_type, token_value = node
    if token_type == "sym" and str(token_value) in STACKVM_COMPILE_ONLY_FORMS:
        raise ValueError(f"StackVM compile-time form '{token_value}' cannot appear in executable AST.")


def _matches_manual_tool_loop(nodes: list[Any], start_index: int) -> bool:
    if start_index + 4 >= len(nodes):
        return False

    if not _is_symbol(nodes[start_index], "last-tool-result"):
        return False
    if not _is_symbol(nodes[start_index + 1], "none?"):
        return False

    request_branch = nodes[start_index + 2]
    later_branch = nodes[start_index + 3]
    if_node = nodes[start_index + 4]
    if not isinstance(request_branch, list) or not isinstance(later_branch, list):
        return False
    if not _is_symbol(if_node, "if"):
        return False
    return _contains_symbol(request_branch, "tool-request")


def _matches_manual_prompt_route(nodes: list[Any], start_index: int) -> bool:
    if start_index + 3 >= len(nodes):
        return False

    request_expr = nodes[start_index]
    interaction_word = nodes[start_index + 1]
    cases = nodes[start_index + 2]
    switch_word = nodes[start_index + 3]

    if _is_symbol(request_expr, "prompt-interaction"):
        return False
    if not _is_symbol(interaction_word, "prompt-interaction"):
        return False
    if not isinstance(cases, list):
        return False
    return _is_symbol(switch_word, "switch")


def _contains_symbol(node: Any, symbol_name: str) -> bool:
    if _is_symbol(node, symbol_name):
        return True
    if isinstance(node, list):
        return any(_contains_symbol(item, symbol_name) for item in node)
    return False


def _is_symbol(node: Any, symbol_name: str) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] == "sym" and str(node[1]) == symbol_name


def _collect_source_authoring_warnings(source: str) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    tokens = tokenize_stackvm_source(source)

    for start_index in range(len(tokens)):
        tool_loop_end = _match_manual_tool_loop_tokens(tokens, start_index)
        if tool_loop_end is not None:
            warnings.append(_make_warning("manual-tool-loop", start=tokens[start_index], end=tokens[tool_loop_end]))

        prompt_route_span = _match_manual_prompt_route_tokens(tokens, start_index)
        if prompt_route_span is not None:
            prompt_route_start, prompt_route_end = prompt_route_span
            warnings.append(
                _make_warning(
                    "manual-prompt-route",
                    start=tokens[prompt_route_start],
                    end=tokens[prompt_route_end],
                )
            )

    return warnings


def _make_warning(
    code: str,
    *,
    start: StackVmSourceToken | None = None,
    end: StackVmSourceToken | None = None,
) -> dict[str, Any]:
    warning: dict[str, Any] = {
        "code": code,
        "message": _warning_message(code),
    }
    if start is not None and end is not None:
        warning["location"] = _format_warning_location(start, end)
        warning["span"] = {
            "start_line": start.line,
            "start_column": start.column,
            "end_line": end.end_line,
            "end_column": end.end_column,
        }
    return warning


def _warning_message(code: str) -> str:
    if code == "manual-tool-loop":
        return (
            "StackVM source uses the manual 'last-tool-result none?' tool loop pattern. "
            "Prefer the built-in 'tool-once' macro for tool-first flows."
        )
    if code == "manual-prompt-route":
        return (
            "StackVM source uses the manual 'prompt-interaction' plus 'switch' routing pattern. "
            "Prefer the built-in 'prompt-route' macro for exact-match interaction routing."
        )
    raise ValueError(f"Unknown StackVM warning code {code!r}")


def _match_manual_tool_loop_tokens(tokens: list[StackVmSourceToken], start_index: int) -> int | None:
    if not _token_is(tokens, start_index, "last-tool-result"):
        return None
    if not _token_is(tokens, start_index + 1, "none?"):
        return None

    request_branch_end = _consume_expression(tokens, start_index + 2)
    if request_branch_end is None or not _token_is(tokens, start_index + 2, "["):
        return None

    later_branch_start = request_branch_end
    later_branch_end = _consume_expression(tokens, later_branch_start)
    if later_branch_end is None or not _token_is(tokens, later_branch_start, "["):
        return None

    if_index = later_branch_end
    if not _token_is(tokens, if_index, "if"):
        return None
    if not _contains_token(tokens, start_index + 2, request_branch_end, "tool-request"):
        return None
    return if_index


def _match_manual_prompt_route_tokens(tokens: list[StackVmSourceToken], start_index: int) -> tuple[int, int] | None:
    if not _token_is(tokens, start_index, "prompt-interaction"):
        return None

    request_expr_start = _find_previous_expression_start(tokens, start_index)
    if request_expr_start is None:
        return None
    if request_expr_start == start_index:
        return None
    if _token_is(tokens, request_expr_start, "prompt-interaction"):
        return None

    cases_end = _consume_expression(tokens, start_index + 1)
    if cases_end is None or not _token_is(tokens, start_index + 1, "["):
        return None
    switch_index = cases_end
    if not _token_is(tokens, switch_index, "switch"):
        return None
    return (request_expr_start, switch_index)


def _consume_expression(tokens: list[StackVmSourceToken], start_index: int) -> int | None:
    if start_index >= len(tokens):
        return None
    if tokens[start_index].raw != "[":
        return start_index + 1

    depth = 0
    for index in range(start_index, len(tokens)):
        token = tokens[index].raw
        if token == "[":
            depth += 1
        elif token == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _find_previous_expression_start(tokens: list[StackVmSourceToken], before_index: int) -> int | None:
    prev_index = before_index - 1
    if prev_index < 0:
        return None
    if tokens[prev_index].raw != "]":
        return prev_index
    return _find_matching_open_bracket(tokens, prev_index)


def _find_matching_open_bracket(tokens: list[StackVmSourceToken], close_index: int) -> int | None:
    depth = 0
    for index in range(close_index, -1, -1):
        token = tokens[index].raw
        if token == "]":
            depth += 1
        elif token == "[":
            depth -= 1
            if depth == 0:
                return index
    return None


def _contains_token(tokens: list[StackVmSourceToken], start_index: int, end_index: int, raw: str) -> bool:
    return any(token.raw == raw for token in tokens[start_index:end_index])


def _token_is(tokens: list[StackVmSourceToken], index: int, raw: str) -> bool:
    return 0 <= index < len(tokens) and tokens[index].raw == raw


def _format_warning_location(start: StackVmSourceToken, end: StackVmSourceToken) -> str:
    if start.line == end.end_line:
        if start.column == end.end_column:
            return f"line {start.line}, col {start.column}"
        return f"line {start.line}, cols {start.column}-{end.end_column}"
    return (
        f"line {start.line}, col {start.column} "
        f"to line {end.end_line}, col {end.end_column}"
    )
