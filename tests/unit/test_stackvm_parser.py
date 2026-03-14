from __future__ import annotations

import pytest

from pocketcode.core.stackvm_parser import (
    parse_stackvm_source_with_spans,
    parse_stackvm_source,
    serialize_stackvm_ast,
    strip_stackvm_comments,
    tokenize_stackvm_source,
)


def test_parse_stackvm_source_handles_nested_quotations_and_scalars():
    ast = parse_stackvm_source('"hello" [ 1 True None [ "nested" ] ] define-word')

    assert ast == [
        ("str", "hello"),
        [
            ("int", 1),
            ("bool", True),
            ("none", None),
            [("str", "nested")],
        ],
        ("sym", "define-word"),
    ]


def test_parse_stackvm_source_handles_explicit_signatures():
    ast = parse_stackvm_source('( dict -- bool ) "is-high-score" define')

    assert ast == [
        ("sig", [("sym", "dict"), ("sym", "--"), ("sym", "bool")]),
        ("str", "is-high-score"),
        ("sym", "define"),
    ]


def test_parse_stackvm_source_rejects_mismatched_brackets():
    with pytest.raises(SyntaxError, match=r"Mismatched closing bracket '\)' for opening '\['"):
        parse_stackvm_source("[ 1 )")

    with pytest.raises(SyntaxError, match=r"Mismatched closing bracket '\]' for opening '\('"):
        parse_stackvm_source("( 1 ]")


def test_parse_stackvm_source_rejects_unclosed_brackets():
    with pytest.raises(SyntaxError, match=r"Missing closing bracket for '\('"):
        parse_stackvm_source("( int -- str")


def test_strip_stackvm_comments_removes_bang_comment_lines_only():
    stripped = strip_stackvm_comments('! heading comment\n"value"\n  ! nested comment\nanswer\n')

    assert stripped == '\n"value"\n\nanswer\n'


def test_serialize_stackvm_ast_renders_parseable_source():
    ast = [("str", "hello"), [("int", 1), ("sym", "dup")], ("sym", "answer")]

    assert serialize_stackvm_ast(ast) == '"hello" [ 1 dup ] answer'


def test_serialize_stackvm_ast_renders_explicit_signatures():
    ast = [("sig", [("sym", "int"), ("sym", "--"), ("sym", "str")])]
    assert serialize_stackvm_ast(ast) == "( int -- str )"


def test_tokenize_stackvm_source_tracks_original_positions_without_comment_tokens():
    tokens = tokenize_stackvm_source('! heading comment\n"value"\n  ! nested comment\nanswer\n')

    assert [token.raw for token in tokens] == ['"value"', "answer"]
    assert (tokens[0].line, tokens[0].column, tokens[0].end_line, tokens[0].end_column) == (2, 1, 2, 7)
    assert (tokens[1].line, tokens[1].column, tokens[1].end_line, tokens[1].end_column) == (4, 1, 4, 6)


def test_parse_stackvm_source_with_spans_tracks_nested_form_locations():
    ast, spans = parse_stackvm_source_with_spans('"hello"\n[ 1 [ "nested" ] ]\nanswer')

    assert ast == [
        ("str", "hello"),
        [("int", 1), [("str", "nested")]],
        ("sym", "answer"),
    ]
    assert spans[0].span.location == "line 1, cols 1-7"
    assert spans[1].span.location == "line 2, cols 1-18"
    assert spans[1].children[0].span.location == "line 2, col 3"
    assert spans[1].children[1].span.location == "line 2, cols 5-16"
    assert spans[2].span.location == "line 3, cols 1-6"
