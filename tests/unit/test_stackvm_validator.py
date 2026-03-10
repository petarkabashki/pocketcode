from __future__ import annotations

import pytest

from pocketcode.core.stackvm_parser import parse_stackvm_source
from pocketcode.core.stackvm_validator import collect_stackvm_authoring_warnings, validate_stackvm_ast


def test_validate_stackvm_ast_accepts_ordinary_runtime_forms():
    validate_stackvm_ast(
        [
            ("str", "hello"),
            [("str", "nested"), ("sym", "answer")],
            ("sym", "concat"),
        ]
    )


def test_validate_stackvm_ast_rejects_compile_only_forms():
    with pytest.raises(ValueError, match="compile-time form 'syntax-quote'"):
        validate_stackvm_ast([("sym", "syntax-quote")])


def test_collect_stackvm_authoring_warnings_flags_legacy_manual_tool_loop():
    source = (
        "! legacy tool loop\n"
        'last-tool-result none? [ "workspace.echo" "{text: ping}" yaml> tool-request ] '
        '[ "last_tool_result.text" shared@ answer ] if'
    )
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(source),
        source=source,
    )

    assert warnings == [
        {
            "code": "legacy-tool-loop",
            "message": (
                "StackVM source uses the manual 'last-tool-result none?' tool loop pattern. "
                "Prefer the built-in 'tool-once' macro for tool-first flows."
            ),
            "location": "line 2, cols 1-123",
            "span": {
                "start_line": 2,
                "start_column": 1,
                "end_line": 2,
                "end_column": 123,
            },
        }
    ]


def test_collect_stackvm_authoring_warnings_does_not_flag_tool_once_macro_usage():
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(
            '"workspace.echo" [ "{text: ping}" yaml> ] [ "last_tool_result.text" shared@ answer ] tool-once'
        )
    )

    assert warnings == []


def test_collect_stackvm_authoring_warnings_flags_legacy_prompt_route_pattern():
    source = (
        '"{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}"\n'
        'prompt-interaction [ "approve" [ "Approved" answer ] "default" [ "Fallback" answer ] ] switch'
    )
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(source),
        source=source,
    )

    assert warnings == [
        {
            "code": "legacy-prompt-route",
            "message": (
                "StackVM source uses the manual 'prompt-interaction' plus 'switch' routing pattern. "
                "Prefer the built-in 'prompt-route' macro for exact-match interaction routing."
            ),
            "location": "line 1, col 1 to line 2, col 93",
            "span": {
                "start_line": 1,
                "start_column": 1,
                "end_line": 2,
                "end_column": 93,
            },
        }
    ]


def test_collect_stackvm_authoring_warnings_does_not_flag_prompt_route_macro_usage():
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(
            '[ "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" ] '
            '[ "approve" [ "Approved" answer ] "default" [ "Fallback" answer ] ] prompt-route'
        )
    )

    assert warnings == []
