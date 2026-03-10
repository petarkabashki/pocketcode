from __future__ import annotations

from pocketcode.core.stackvm_parser import (
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


def test_strip_stackvm_comments_removes_bang_comment_lines_only():
    stripped = strip_stackvm_comments('! heading comment\n"value"\n  ! nested comment\nanswer\n')

    assert stripped == '\n"value"\n\nanswer\n'


def test_serialize_stackvm_ast_renders_parseable_source():
    ast = [("str", "hello"), [("int", 1), ("sym", "dup")], ("sym", "answer")]

    assert serialize_stackvm_ast(ast) == '"hello" [ 1 dup ] answer'


def test_tokenize_stackvm_source_tracks_original_positions_without_comment_tokens():
    tokens = tokenize_stackvm_source('! heading comment\n"value"\n  ! nested comment\nanswer\n')

    assert [token.raw for token in tokens] == ['"value"', "answer"]
    assert (tokens[0].line, tokens[0].column, tokens[0].end_line, tokens[0].end_column) == (2, 1, 2, 7)
    assert (tokens[1].line, tokens[1].column, tokens[1].end_line, tokens[1].end_column) == (4, 1, 4, 6)
