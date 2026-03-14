from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import json
import re
from typing import Any

import yaml

STACKVM_COMMENT_LINE_RE = re.compile(r"(?m)^\s*!.*$")
STACKVM_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\[|\]|\(|\)|[^\s\[\]\(\)]+')


@dataclass(frozen=True)
class StackVmSourceToken:
    raw: str
    start: int
    end: int
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class StackVmSourceSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    @property
    def location(self) -> str:
        if self.start_line == self.end_line:
            if self.start_column == self.end_column:
                return f"line {self.start_line}, col {self.start_column}"
            return f"line {self.start_line}, cols {self.start_column}-{self.end_column}"
        return (
            f"line {self.start_line}, col {self.start_column} "
            f"to line {self.end_line}, col {self.end_column}"
        )


@dataclass(frozen=True)
class StackVmAstSpan:
    span: StackVmSourceSpan
    children: tuple["StackVmAstSpan", ...] = field(default_factory=tuple)


def strip_stackvm_comments(code: str) -> str:
    return STACKVM_COMMENT_LINE_RE.sub("", code or "")


def parse_stackvm_source(code: str) -> list[Any]:
    ast, _ = parse_stackvm_source_with_spans(code)
    return ast


def parse_stackvm_source_with_spans(code: str) -> tuple[list[Any], list[StackVmAstSpan]]:
    tokens = tokenize_stackvm_source(code)
    ast: list[Any] = []
    parse_stack: list[list[Any]] = [ast]
    span_tree: list[StackVmAstSpan] = []
    span_stack: list[list[StackVmAstSpan]] = [span_tree]
    open_tokens: list[StackVmSourceToken] = []

    for token in tokens:
        if token.raw in {"[", "("}:
            nested: list[Any] = []
            parse_stack[-1].append(nested)
            parse_stack.append(nested)
            open_tokens.append(token)
            span_stack.append([])
            continue
        if token.raw in {"]", ")"}:
            if len(parse_stack) <= 1:
                raise SyntaxError(f"Unexpected closing bracket '{token.raw}'")
            opening = open_tokens.pop()

            if (opening.raw == "[" and token.raw != "]") or (opening.raw == "(" and token.raw != ")"):
                raise SyntaxError(f"Mismatched closing bracket '{token.raw}' for opening '{opening.raw}'")

            nested_children = span_stack.pop()
            popped_nested = parse_stack.pop()

            if opening.raw == "(":
                parse_stack[-1][-1] = ("sig", popped_nested)

            span_stack[-1].append(
                StackVmAstSpan(
                    span=StackVmSourceSpan(
                        start_line=opening.line,
                        start_column=opening.column,
                        end_line=token.end_line,
                        end_column=token.end_column,
                    ),
                    children=tuple(nested_children),
                )
            )
            continue
        parse_stack[-1].append(parse_stackvm_token(token.raw))
        span_stack[-1].append(
            StackVmAstSpan(
                span=StackVmSourceSpan(
                    start_line=token.line,
                    start_column=token.column,
                    end_line=token.end_line,
                    end_column=token.end_column,
                )
            )
        )

    if len(parse_stack) > 1:
        opening = open_tokens[-1]
        raise SyntaxError(f"Missing closing bracket for '{opening.raw}'")
    return ast, span_tree


def tokenize_stackvm_source(code: str) -> list[StackVmSourceToken]:
    source = code or ""
    comment_ranges = [(match.start(), match.end()) for match in STACKVM_COMMENT_LINE_RE.finditer(source)]
    line_starts = _build_line_starts(source)
    tokens: list[StackVmSourceToken] = []
    comment_index = 0

    for match in STACKVM_TOKEN_RE.finditer(source):
        start = match.start()
        while comment_index < len(comment_ranges) and comment_ranges[comment_index][1] <= start:
            comment_index += 1
        if comment_index < len(comment_ranges):
            comment_start, comment_end = comment_ranges[comment_index]
            if comment_start <= start < comment_end:
                continue

        end = match.end()
        line, column = _offset_to_line_column(line_starts, start)
        end_line, end_column = _offset_to_line_column(line_starts, end - 1)
        tokens.append(
            StackVmSourceToken(
                raw=match.group(0),
                start=start,
                end=end,
                line=line,
                column=column,
                end_line=end_line,
                end_column=end_column,
            )
        )

    return tokens


def parse_stackvm_token(token: str) -> tuple[str, Any]:
    if token.startswith('"') and token.endswith('"'):
        return ("str", yaml.safe_load(token))
    if token in {"True", "False"}:
        return ("bool", token == "True")
    if token in {"None", "null"}:
        return ("none", None)
    try:
        return ("int", int(token))
    except ValueError:
        pass
    try:
        if any(char in token for char in (".", "e", "E")):
            return ("float", float(token))
    except ValueError:
        pass
    return ("sym", token)


def serialize_stackvm_ast(ast: list[Any]) -> str:
    return " ".join(_serialize_stackvm_node(node) for node in ast)


def _serialize_stackvm_node(node: Any) -> str:
    if isinstance(node, list):
        return f"[ {' '.join(_serialize_stackvm_node(item) for item in node)} ]"
    if not isinstance(node, tuple) or len(node) != 2:
        raise TypeError(f"Unsupported StackVM AST node {node!r}")

    token_type, token_value = node
    if token_type == "sig":
        return f"( {' '.join(_serialize_stackvm_node(item) for item in token_value)} )"
    if token_type == "str":
        return json.dumps(str(token_value))
    if token_type == "bool":
        return "True" if token_value else "False"
    if token_type == "none":
        return "None"
    if token_type in {"int", "float", "sym"}:
        return str(token_value)
    raise TypeError(f"Unsupported StackVM token type {token_type!r}")


def _build_line_starts(source: str) -> list[int]:
    starts = [0]
    for offset, char in enumerate(source):
        if char == "\n":
            starts.append(offset + 1)
    return starts


def _offset_to_line_column(line_starts: list[int], offset: int) -> tuple[int, int]:
    line_index = bisect_right(line_starts, offset) - 1
    line_start = line_starts[max(line_index, 0)]
    return (line_index + 1, offset - line_start + 1)
