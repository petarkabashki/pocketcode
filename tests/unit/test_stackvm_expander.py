from __future__ import annotations

import pytest

from pocketcode.core.stackvm_expander import StackVmMacroExpansionError, expand_stackvm_source


def test_expand_stackvm_source_registers_and_expands_simple_macro():
    result = expand_stackvm_source('[ value ] [ value "Result: " swap concat answer ] "finalize-with-prefix" defmacro "ok" finalize-with-prefix')

    assert result.expansion_count == 1
    assert "finalize-with-prefix" in result.macros
    assert result.ast == [
        ("str", "ok"),
        ("str", "Result: "),
        ("sym", "swap"),
        ("sym", "concat"),
        ("sym", "answer"),
    ]


def test_expand_stackvm_source_supports_quotation_arguments():
    result = expand_stackvm_source(
        '[ cond body ] [ cond [ body call ] [ ] if ] "when" defmacro True [ "yes" "status" store-set ] when'
    )

    assert result.ast == [
        ("bool", True),
        [[("str", "yes"), ("str", "status"), ("sym", "store-set")], ("sym", "call")],
        [],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_syntax_quote_and_unquote():
    result = expand_stackvm_source(
        '[ value ] [ [ value unquote ] "SQ: " swap concat answer ] syntax-quote "emit-answer" defmacro "hello" emit-answer'
    )

    assert result.ast == [
        ("str", "hello"),
        ("str", "SQ: "),
        ("sym", "swap"),
        ("sym", "concat"),
        ("sym", "answer"),
    ]


def test_expand_stackvm_source_supports_unquote_splice():
    result = expand_stackvm_source(
        '[ body ] [ [ body unquote-splice ] ] syntax-quote "inline-body" defmacro [ "done" "status" store-set ] inline-body'
    )

    assert result.ast == [
        ("str", "done"),
        ("str", "status"),
        ("sym", "store-set"),
    ]


def test_expand_stackvm_source_supports_gensym_in_syntax_quote():
    result = expand_stackvm_source(
        '[ ] [ [ "tmp" gensym ] ] syntax-quote "fresh-name" defmacro fresh-name fresh-name'
    )

    assert result.gensym_count == 2
    assert result.ast[0][0] == "sym"
    assert result.ast[1][0] == "sym"
    assert result.ast[0][1].startswith("__tmp_")
    assert result.ast[1][1].startswith("__tmp_")
    assert result.ast[0][1] != result.ast[1][1]


def test_expand_stackvm_source_supports_builtin_when_macro():
    result = expand_stackvm_source('True [ "yes" "status" store-set ] when')

    assert result.expansion_trace == ["when"]
    assert result.ast == [
        ("bool", True),
        [[("str", "yes"), ("str", "status"), ("sym", "store-set")], ("sym", "call")],
        [],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_shared_or_macro():
    result = expand_stackvm_source('"normalized.missing" "fallback" shared-or')

    assert result.expansion_trace == ["shared-or"]
    assert result.ast == [
        ("str", "normalized.missing"),
        ("sym", "shared@"),
        ("sym", "dup"),
        ("sym", "none?"),
        [("sym", "drop"), ("str", "fallback")],
        [],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_tool_once_macro():
    result = expand_stackvm_source(
        '"workspace.echo" [ "{text: ping}" yaml> ] [ "last_tool_result.text" shared@ answer ] tool-once'
    )

    assert result.expansion_trace == ["tool-once"]
    assert result.ast == [
        ("sym", "last-tool-result"),
        ("sym", "none?"),
        [
            ("str", "workspace.echo"),
            [("str", "{text: ping}"), ("sym", "yaml>")],
            ("sym", "call"),
            ("sym", "tool-request"),
        ],
        [
            [("str", "last_tool_result.text"), ("sym", "shared@"), ("sym", "answer")],
            ("sym", "call"),
        ],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_delegate_return_macro():
    result = expand_stackvm_source('"delegate.agent" "last_delegated_result.answer" delegate-return')

    assert result.expansion_trace == ["delegate-return"]
    assert result.ast == [
        ("str", "last_delegated_result.answer"),
        ("sym", "shared@"),
        ("sym", "none?"),
        [("str", "delegate.agent"), ("sym", "handoff")],
        [("str", "last_delegated_result.answer"), ("sym", "shared@"), ("sym", "answer")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_finalize_from_macro():
    result = expand_stackvm_source('[ "done" ] finalize-from')

    assert result.expansion_trace == ["finalize-from"]
    assert result.ast == [
        [("str", "done")],
        ("sym", "call"),
        ("sym", "answer"),
    ]


def test_expand_stackvm_source_supports_builtin_prompt_route_macro():
    result = expand_stackvm_source(
        '[ "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '[ "approve" [ "Approved" answer ] "default" [ "Fallback" answer ] ] prompt-route'
    )

    assert result.expansion_trace == ["prompt-route"]
    assert result.ast == [
        [
            (
                "str",
                "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}",
            ),
            ("sym", "yaml>"),
        ],
        ("sym", "call"),
        ("sym", "prompt-interaction"),
        [
            ("str", "approve"),
            [("str", "Approved"), ("sym", "answer")],
            ("str", "default"),
            [("str", "Fallback"), ("sym", "answer")],
        ],
        ("sym", "switch"),
    ]


def test_expand_stackvm_source_rejects_malformed_macro_definition():
    with pytest.raises(TypeError, match="parameters must be symbols"):
        expand_stackvm_source('[ "not-symbol" ] [ answer ] "broken" defmacro')


def test_expand_stackvm_source_rejects_missing_macro_arguments():
    with pytest.raises(StackVmMacroExpansionError, match=r"expects 1 syntax arguments.*macro trace: needs-one"):
        expand_stackvm_source('[ value ] [ value answer ] "needs-one" defmacro needs-one')


def test_expand_stackvm_source_rejects_splicing_non_list_values():
    with pytest.raises(StackVmMacroExpansionError, match=r"unquote-splice expects a quotation/list syntax value.*macro trace: bad-splice"):
        expand_stackvm_source(
            '[ value ] [ [ value unquote-splice ] ] syntax-quote "bad-splice" defmacro "oops" bad-splice'
        )


def test_expand_stackvm_source_reports_macro_trace_for_nested_failures():
    with pytest.raises(StackVmMacroExpansionError, match=r"macro trace: outer -> inner"):
        expand_stackvm_source(
            '[ ] [ inner ] "outer" defmacro '
            '[ ] [ "oops" [ value unquote-splice ] ] syntax-quote "inner" defmacro '
            'outer'
        )
