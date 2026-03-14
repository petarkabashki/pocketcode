from __future__ import annotations

from typing import Any

from pocketcode.core.stackvm_analysis import analyze_stackvm_ast
from pocketcode.core.stackvm_parser import StackVmSourceToken, tokenize_stackvm_source, parse_stackvm_token

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
        # Source-based checks still use token-level scanning for now
        return _collect_source_authoring_warnings(source)

    # Legacy manual traversal warnings
    warnings: list[dict[str, Any]] = []
    _collect_authoring_warnings(ast, warnings)
    
    # New full-analysis based diagnostics
    analysis = analyze_stackvm_ast(ast)
    analysis_diagnostics = analysis.get("diagnostics", [])
    
    # Merge, avoiding duplicates if any overlap exists
    existing_codes = {w["code"] for w in warnings}
    for diag in analysis_diagnostics:
        if diag["code"] not in existing_codes:
            warnings.append(diag)
            
    return warnings


def _collect_authoring_warnings(nodes: list[Any], warnings: list[dict[str, Any]], depth: int = 0) -> None:
    found_codes = set()
    for start_index in range(len(nodes)):
        if _is_symbol(nodes[start_index], "define") or _is_symbol(nodes[start_index], "defmacro"):
            _check_definition_signature(nodes, start_index, warnings)

        if _matches_manual_tool_loop(nodes, start_index):
            if "manual-tool-loop" not in found_codes:
                warnings.append(_make_warning("manual-tool-loop"))
                found_codes.add("manual-tool-loop")
        if _matches_manual_prompt_route(nodes, start_index):
            if "manual-prompt-route" not in found_codes:
                warnings.append(_make_warning("manual-prompt-route"))
                found_codes.add("manual-prompt-route")
        if _matches_manual_dict_chain(nodes, start_index):
            # Trigger the smell warning if the manual pattern is found repeatedly in this specific block
            if sum(1 for i in range(len(nodes)) if _matches_manual_dict_chain(nodes, i)) >= 2:
                if "manual-dict-get-chain" not in found_codes:
                    warnings.append(_make_warning("manual-dict-get-chain"))
                    found_codes.add("manual-dict-get-chain")
        
        if _is_complex_expression(nodes):
            if "complex-expression-smell" not in found_codes:
                warnings.append(_make_warning("complex-expression-smell"))
                found_codes.add("complex-expression-smell")

    # Check for missing module declaration if imports/exports are present
    if any(_is_symbol(node, "import") or _is_symbol(node, "export") for node in nodes):
        if not any(_is_symbol(node, "module") for node in nodes):
            if "missing-module-declaration" not in found_codes:
                warnings.append(_make_warning("missing-module-declaration"))
                found_codes.add("missing-module-declaration")

    # Style checks for nested-if-smell
    if depth >= 2 and any(_is_symbol(node, "if") for node in nodes):
        warnings.append(_make_warning("nested-if-smell"))

    for node in nodes:
        if isinstance(node, list):
            new_depth = depth + 1 if any(_is_symbol(n, "if") for n in nodes) else depth
            _collect_authoring_warnings(node, warnings, new_depth)


def _check_definition_signature(nodes: list[Any], index: int, warnings: list[dict[str, Any]]) -> None:
    """Validates that a define/defmacro body matches its preceding ( in -- out ) signature."""
    # Pattern: [body] (sig) "name" define
    if index < 3:
        return

    name_node = nodes[index - 1]
    sig_node = nodes[index - 2]
    body_node = nodes[index - 3]

    if not (isinstance(sig_node, tuple) and sig_node[0] == "sig" and isinstance(body_node, list)):
        return

    in_types, out_types = _parse_signature(sig_node[1])
    
    # Perform static analysis on the body quotation
    analysis = analyze_stackvm_ast(body_node)
    
    # The analyzer reports how many items the block expects to pop (min_stack_depth)
    # and what it leaves behind (final_stack_shape)
    actual_pops = analysis.get("final_min_stack_depth", 0)
    actual_pushes = len(analysis.get("final_stack_shape", []))

    if actual_pops != len(in_types) or actual_pushes != len(out_types):
        warnings.append(_make_warning("signature-mismatch"))


def _parse_signature(sig_tokens: list[Any]) -> tuple[list[str], list[str]]:
    """
    Parses signature tokens into (inputs, outputs).
    Example: ( int int -- str ) -> (['int', 'int'], ['str'])
    """
    in_types: list[str] = []
    out_types: list[str] = []
    target = in_types
    
    for token in sig_tokens:
        # Handle symbol-wrapped types or raw strings
        val = str(token[1]) if isinstance(token, tuple) else str(token)
        if val == "--":
            target = out_types
            continue
        # Filter out parentheses if they leaked into the token list
        if val not in ("(", ")"):
            target.append(val)
            
    return in_types, out_types


def _matches_manual_dict_chain(nodes: list[Any], start_index: int) -> bool:
    """Detects repetitive manual dict-get patterns that should use project-fields."""
    if start_index + 2 >= len(nodes):
        return False
    
    # Pattern: dup "key" dict-get?
    return (
        _is_symbol(nodes[start_index], "dup") and
        isinstance(nodes[start_index + 1], tuple) and nodes[start_index + 1][0] == "str" and
        (_is_symbol(nodes[start_index + 2], "dict-get") or _is_symbol(nodes[start_index + 2], "dict-get?"))
    )


def _validate_stackvm_node(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _validate_stackvm_node(item)
        return

    if not isinstance(node, tuple) or len(node) != 2:
        raise TypeError(f"Unsupported StackVM AST node {node!r}")

    token_type, token_value = node
    if token_type == "sig":
        if isinstance(token_value, list):
            for item in token_value:
                _validate_stackvm_node(item)
        return

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


def _is_complex_expression(nodes: list[Any]) -> bool:
    """Detects blocks with too many tokens and few structures."""
    if len(nodes) < 15:
        return False
    
    # Count structural nodes vs flat words
    structure_count = sum(1 for node in nodes if isinstance(node, list) or (isinstance(node, tuple) and node[0] == "sig"))
    if structure_count < 2:
        return True
    return False


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
    if code == "nested-if-smell":
        return (
            "StackVM source uses deeply nested 'if' structures (> 2 levels). "
            "Consider using 'cond', 'switch', or 'match' for better readability."
        )
    if code == "manual-dict-get-chain":
        return (
            "StackVM source uses repetitive manual 'dict-get' calls. "
            "Consider using the 'project-fields' or 'project-shared' macros to normalize state."
        )
    if code == "signature-mismatch":
        return (
            "StackVM helper body stack effect does not match its explicit ( in -- out ) signature."
        )
    if code == "complex-expression-smell":
        return (
            "StackVM block contains a long sequence of tokens (> 15) without enough structure. "
            "Consider breaking it into smaller helpers or using comments."
        )
    if code == "missing-module-declaration":
        return (
            "StackVM source uses 'import' or 'export' but does not declare a 'module'. "
            "Add 'module {name}' at the top of the file."
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
