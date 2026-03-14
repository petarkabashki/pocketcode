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
    assert len(result.expansion_frames) == 1
    frame = result.expansion_frames[0]
    assert frame.macro_name == "emit-answer"
    assert frame.builtin is False
    assert frame.depth == 0
    assert frame.call_site == "line 1, cols 103-113"
    assert frame.definition_site == "line 1, cols 86-93"
    assert frame.generated_by is None
    assert frame.syntax_args == ['"hello"']
    assert frame.expanded_form == '"hello" "SQ: " swap concat answer'


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
        '"resource_root.pocketcode.echo" [ "{text: ping}" yaml> ] [ "last_tool_result.text" shared@ answer ] tool-once'
    )

    assert result.expansion_trace == ["tool-once"]
    assert result.ast == [
        ("sym", "last-tool-result"),
        ("sym", "none?"),
        [
            ("str", "resource_root.pocketcode.echo"),
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


def test_expand_stackvm_source_supports_builtin_return_handoff_macro():
    result = expand_stackvm_source('"delegate.agent" return-handoff')

    assert result.expansion_trace == ["return-handoff"]
    assert result.ast == [
        ("str", "{return_to_caller: true, context_mode: whole, return_transition: continue}"),
        ("sym", "yaml>"),
        ("str", "pending_handoff_policy"),
        ("sym", "store-set"),
        ("str", "delegate.agent"),
        ("sym", "handoff"),
    ]


def test_expand_stackvm_source_supports_builtin_return_delegate_macro():
    result = expand_stackvm_source('"delegate.agent" "last_delegated_result.answer" return-delegate')

    assert result.expansion_trace == ["return-delegate"]
    assert result.ast == [
        ("str", "last_delegated_result.answer"),
        ("sym", "shared@"),
        ("sym", "none?"),
        [
            ("str", "{return_to_caller: true, context_mode: whole, return_transition: continue}"),
            ("sym", "yaml>"),
            ("str", "pending_handoff_policy"),
            ("sym", "store-set"),
            ("str", "delegate.agent"),
            ("sym", "handoff"),
        ],
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


def test_expand_stackvm_source_supports_builtin_maybe_handoff_macro():
    result = expand_stackvm_source(
        '[ "routes" store-get 0 list-get? ] '
        '[ "missing_route" "route_reason" shared! "router.fallback" handoff ] '
        'maybe-handoff'
    )

    assert result.expansion_trace == ["maybe-handoff"]
    assert result.ast == [
        [("str", "routes"), ("sym", "store-get"), ("int", 0), ("sym", "list-get?")],
        ("sym", "call"),
        ("sym", "dup"),
        ("sym", "none?"),
        [
            ("sym", "drop"),
            [
                ("str", "missing_route"),
                ("str", "route_reason"),
                ("sym", "shared!"),
                ("str", "router.fallback"),
                ("sym", "handoff"),
            ],
            ("sym", "call"),
        ],
        [("sym", "handoff")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_indexed_value_macro():
    result = expand_stackvm_source(
        '[ "routes" store-get ] [ "selected_index" store-get ] '
        '[ "missing_route" "route_reason" "router.fallback" shared-handoff ] '
        '[ handoff ] '
        'indexed-value'
    )

    assert result.expansion_trace == ["shared-handoff", "indexed-value"]
    assert result.ast == [
        [("str", "routes"), ("sym", "store-get")],
        ("sym", "call"),
        [("str", "selected_index"), ("sym", "store-get")],
        ("sym", "call"),
        ("sym", "list-get?"),
        ("sym", "dup"),
        ("sym", "none?"),
        [
            ("sym", "drop"),
            [
                ("str", "missing_route"),
                ("str", "route_reason"),
                ("sym", "shared!"),
                ("str", "router.fallback"),
                ("sym", "handoff"),
            ],
            ("sym", "call"),
        ],
        [[("sym", "handoff")], ("sym", "call")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_indexed_handoff_route_macro():
    result = expand_stackvm_source(
        '[ "routes" store-get ] '
        '[ "selected_index" store-get ] '
        '"missing_route" '
        '"router.fallback" '
        '[ handoff ] '
        'indexed-handoff-route'
    )

    assert result.expansion_trace == ["indexed-handoff-route", "shared-handoff", "indexed-value"]
    assert result.ast == [
        [("str", "routes"), ("sym", "store-get")],
        ("sym", "call"),
        [("str", "selected_index"), ("sym", "store-get")],
        ("sym", "call"),
        ("sym", "list-get?"),
        ("sym", "dup"),
        ("sym", "none?"),
        [
            ("sym", "drop"),
            [
                ("str", "missing_route"),
                ("str", "route_reason"),
                ("sym", "shared!"),
                ("str", "router.fallback"),
                ("sym", "handoff"),
            ],
            ("sym", "call"),
        ],
        [[("sym", "handoff")], ("sym", "call")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_shared_handoff_macro():
    result = expand_stackvm_source(
        '"missing_route" "route_reason" "router.fallback" shared-handoff'
    )

    assert result.expansion_trace == ["shared-handoff"]
    assert result.ast == [
        ("str", "missing_route"),
        ("str", "route_reason"),
        ("sym", "shared!"),
        ("str", "router.fallback"),
        ("sym", "handoff"),
    ]


def test_expand_stackvm_source_supports_builtin_returned_handoff_switch_macro():
    result = expand_stackvm_source(
        '[ "missing" answer ] '
        '[ [ "route" dict-get ] "normalized.final_route" ] '
        '[ "normalized.final_route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'returned-handoff-switch'
    )

    assert result.expansion_trace == [
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
    ]


def test_expand_stackvm_source_supports_builtin_returned_finalize_macro():
    result = expand_stackvm_source(
        '[ "missing" answer ] '
        '[ [ "mode" dict-get ] "normalized.mode" ] '
        '[ "final: " "normalized.mode" shared@ concat ] '
        'returned-finalize'
    )

    assert result.expansion_trace == [
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
    ]


def test_expand_stackvm_source_supports_builtin_returned_policy_macro_with_handoff_mode():
    result = expand_stackvm_source(
        '[ "missing" answer ] '
        '[ [ "route" dict-get ] "normalized.final_route" ] '
        '"handoff" '
        '[ "normalized.final_route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'returned-policy'
    )

    assert result.expansion_trace == [
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
    ]


def test_expand_stackvm_source_supports_builtin_returned_policy_macro_with_finalize_mode():
    result = expand_stackvm_source(
        '[ "missing" answer ] '
        '[ [ "mode" dict-get ] "normalized.mode" ] '
        '"finalize" '
        '[ "final: " "normalized.mode" shared@ concat ] '
        '[ ] '
        'returned-policy'
    )

    assert result.expansion_trace == [
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
    ]


def test_expand_stackvm_source_supports_builtin_project_fields_macro():
    result = expand_stackvm_source(
        '[ "decision.route" "normalized.route" "review" "meta.source" "normalized.source" "delegate" ] '
        '[ "normalized.route" shared@ answer ] '
        'project-fields'
    )

    assert result.expansion_trace == ["project-fields", "project-shared"]


def test_expand_stackvm_source_supports_builtin_returned_field_policy_macro():
    result = expand_stackvm_source(
        '[ "missing" answer ] '
        '[ "route" "normalized.final_route" None "note" "normalized.delegate_note" "fallback" ] '
        '"handoff" '
        '[ "normalized.final_route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'returned-field-policy'
    )

    assert result.expansion_trace == [
        "returned-field-policy",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
    ]


def test_expand_stackvm_source_supports_builtin_return_field_route_flow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ "missing" answer ] '
        '[ "route" "normalized.final_route" "review" ] '
        '[ "normalized.final_route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'return-field-route-flow'
    )

    assert result.expansion_trace == [
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_return_field_finalize_flow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ "missing" answer ] '
        '[ "mode" "normalized.mode" "unknown" ] '
        '[ "final: " "normalized.mode" shared@ concat ] '
        'return-field-finalize-flow'
    )

    assert result.expansion_trace == [
        "return-field-finalize-flow",
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_returned_answer_policy_macro():
    result = expand_stackvm_source(
        '[ drop "missing" answer ] '
        '[ "Caller received: " swap concat ] '
        'returned-answer-policy'
    )

    assert result.expansion_trace == [
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
    ]


def test_expand_stackvm_source_supports_builtin_return_flow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ [ drop "missing" answer ] [ "Caller received: " swap concat ] returned-answer-policy ] '
        'return-flow'
    )

    assert result.expansion_trace == [
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_return_answer_flow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ drop "missing" answer ] '
        '[ "Caller received: " swap concat ] '
        'return-answer-flow'
    )

    assert result.expansion_trace == [
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_return_contract_flow_macro_with_answer_mode():
    result = expand_stackvm_source(
        '"answer" '
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ drop "missing" answer ] '
        '[ ] '
        '[ "Caller received: " swap concat ] '
        '[ ] '
        'return-contract-flow'
    )

    assert result.expansion_trace == [
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_return_policy_flow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '[ "payload" store-set ] '
        '"router.delegate" '
        '[ "missing" answer ] '
        '[ [ "route" dict-get ] "normalized.route" ] '
        '"handoff" '
        '[ "normalized.route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'return-policy-flow'
    )

    assert result.expansion_trace == [
        "return-policy-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_prompt_store_switch_macro():
    result = expand_stackvm_source(
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '[ "approve" [ "router.approve" handoff ] "default" [ "router.review" handoff ] ] '
        'prompt-store-switch'
    )

    assert result.expansion_trace == ["prompt-store-switch"]


def test_expand_stackvm_source_supports_builtin_prompt_store_contains_switch_macro():
    result = expand_stackvm_source(
        '[ "{kind: checklist, prompt: Choose, options: [{id: delegate, label: Delegate, value: delegate}]}" yaml> ] '
        '"normalized.actions" '
        '[ common.format-selected-actions ] '
        '[ "delegate" [ drop drop "router.delegate" handoff ] "default" [ drop drop "router.review" handoff ] ] '
        'prompt-store-contains-switch'
    )

    assert result.expansion_trace == ["prompt-store-contains-switch"]


def test_expand_stackvm_source_supports_builtin_prompt_store_policy_macro_with_exact_mode():
    result = expand_stackvm_source(
        '[ "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ "approve" [ answer ] "default" [ drop ] ] '
        'prompt-store-policy'
    )

    assert result.expansion_trace == ["prompt-store-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_store_policy_macro_with_contains_mode():
    result = expand_stackvm_source(
        '[ "{kind: checklist, prompt: Choose, options: [{id: delegate, label: Delegate, value: delegate}]}" yaml> ] '
        '"normalized.actions" '
        '"contains" '
        '[ common.format-selected-actions ] '
        '[ "delegate" [ handoff ] "default" [ answer ] ] '
        'prompt-store-policy'
    )

    assert result.expansion_trace == ["prompt-store-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_return_policy_macro_with_exact_mode():
    result = expand_stackvm_source(
        '[ "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'prompt-return-policy'
    )

    assert result.expansion_trace == ["prompt-return-policy"]


def test_expand_stackvm_source_supports_builtin_choice_request_macro():
    result = expand_stackvm_source(
        '"buttons" '
        '[ "Choose for " "normalized.summary" shared@ concat ] '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        'choice-request'
    )

    assert result.expansion_trace == ["choice-request"]
    assert result.ast == [
        (
            "str",
            "{kind: buttons, prompt: placeholder, options: [{id: approve, label: Approve, value: approve}, {id: reject, label: Reject, value: reject}]}",
        ),
        ("sym", "yaml>"),
        ("str", "prompt"),
        [
            ("str", "Choose for "),
            ("str", "normalized.summary"),
            ("sym", "shared@"),
            ("sym", "concat"),
        ],
        ("sym", "call"),
        ("sym", "dict-set"),
    ]


def test_expand_stackvm_source_supports_builtin_choice_policy_macro():
    result = expand_stackvm_source(
        '"buttons" '
        '[ "Choose for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ drop "approved" answer ] "default" [ drop "rejected" answer ] ] '
        'choice-policy'
    )

    assert result.expansion_trace == ["choice-policy", "choice-request", "prompt-store-policy"]


def test_expand_stackvm_source_supports_builtin_choice_flow_macro_with_continue_mode():
    result = expand_stackvm_source(
        '"continue" '
        '"buttons" '
        '[ "Choose for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ drop "approved" answer ] "default" [ drop "rejected" answer ] ] '
        'choice-flow'
    )

    assert result.expansion_trace == ["choice-flow", "choice-policy", "choice-request", "prompt-store-policy"]


def test_expand_stackvm_source_supports_builtin_summary_choice_flow_macro_with_continue_mode():
    result = expand_stackvm_source(
        '"continue" '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ drop "approved" answer ] "default" [ drop "rejected" answer ] ] '
        'summary-choice-flow'
    )

    assert result.expansion_trace == [
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_summary_answer_workflow_macro():
    result = expand_stackvm_source(
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'summary-answer-workflow'
    )

    assert result.expansion_trace == [
        "summary-answer-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_delegate_answer_workflow_macro():
    result = expand_stackvm_source(
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'delegate-answer-workflow'
    )

    assert result.expansion_trace == [
        "delegate-answer-workflow",
        "summary-answer-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_answer_workflow_contract_for_delegate():
    result = expand_stackvm_source(
        '[ '
        '"role" "delegate" '
        '"kind" "buttons" '
        '"prompt_prefix" "Choose for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"rules" [ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        '] answer-workflow-contract'
    )

    assert result.expansion_trace == [
        "answer-workflow-contract",
        "delegate-answer-workflow",
        "summary-answer-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_workflow_spec_for_delegate_answer():
    result = expand_stackvm_source(
        '[ '
        '"kind" "buttons" '
        '"prompt_prefix" "Choose for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"delegate_rules" [ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        '] "delegate" "answer" workflow-spec'
    )

    assert result.expansion_trace == [
        "workflow-spec",
        "answer-workflow-contract",
        "delegate-answer-workflow",
        "summary-answer-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_summary_structured_workflow_macro():
    result = expand_stackvm_source(
        '"radio" '
        '"Choose route for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> ] '
        '[ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        'summary-structured-workflow'
    )

    assert result.expansion_trace == [
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_route_workflow_contract_for_delegate():
    result = expand_stackvm_source(
        '[ '
        '"role" "delegate" '
        '"kind" "radio" '
        '"prompt_prefix" "Choose route for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"base_expr" [ "{}" yaml> ] '
        '"rules" [ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        '] route-workflow-contract'
    )

    assert result.expansion_trace == [
        "route-workflow-contract",
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_delegate_structured_workflow_macro():
    result = expand_stackvm_source(
        '"radio" '
        '"Choose route for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> ] '
        '[ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        'delegate-structured-workflow'
    )

    assert result.expansion_trace == [
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_choice_decision_macro_with_answer_mode():
    result = expand_stackvm_source(
        '"answer" '
        '"buttons" '
        '[ "Choose for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'choice-decision'
    )

    assert result.expansion_trace == ["choice-decision", "choice-request", "prompt-decision", "prompt-return-policy"]


def test_expand_stackvm_source_supports_builtin_choice_decision_macro_with_yaml_merge_mode():
    result = expand_stackvm_source(
        '"yaml-merge" '
        '"radio" '
        '[ "Choose route for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "{}" yaml> "approve" "decision.route" set-in ] "default" [ "{}" yaml> "review" "decision.route" set-in ] ] '
        'choice-decision'
    )

    assert result.expansion_trace == ["choice-decision", "choice-request", "prompt-decision", "prompt-return-merge-policy"]


def test_expand_stackvm_source_supports_builtin_choice_contract_macro_with_answer_mode():
    result = expand_stackvm_source(
        '"answer" '
        '"buttons" '
        '[ "Choose for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'choice-contract'
    )

    assert result.expansion_trace == [
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_choice_flow_macro_with_structured_mode():
    result = expand_stackvm_source(
        '"structured" '
        '"radio" '
        '[ "Choose route for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ] '
        '"default" [ "decision.route" "review" ] ] '
        'choice-flow'
    )

    assert result.expansion_trace == [
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_normalize_loaded_payload_macro():
    result = expand_stackvm_source("normalize-loaded-payload")

    assert result.expansion_trace == ["normalize-loaded-payload"]


def test_expand_stackvm_source_supports_builtin_normalized_choice_router_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"continue" '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ drop "approved" answer ] "default" [ drop "rejected" answer ] ] '
        'normalized-choice-router'
    )

    assert result.expansion_trace == [
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_normalized_continue_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ answer ] "default" [ answer ] ] '
        'normalized-continue-workflow'
    )

    assert result.expansion_trace == [
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_router_continue_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ answer ] "default" [ answer ] ] '
        'router-continue-workflow'
    )

    assert result.expansion_trace == [
        "router-continue-workflow",
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_continue_workflow_contract_macro():
    result = expand_stackvm_source(
        '[ '
        '"payload_file" "payload.yaml" '
        '"kind" "buttons" '
        '"prompt_prefix" "Choose for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"rules" [ "approve" [ answer ] "default" [ answer ] ] '
        '] continue-workflow-contract'
    )

    assert result.expansion_trace == [
        "continue-workflow-contract",
        "router-continue-workflow",
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_workflow_spec_for_router_continue():
    result = expand_stackvm_source(
        '[ '
        '"payload_file" "payload.yaml" '
        '"kind" "buttons" '
        '"prompt_prefix" "Choose for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"continue_rules" [ "approve" [ answer ] "default" [ answer ] ] '
        '] "router" "continue" workflow-spec'
    )

    assert result.expansion_trace == [
        "workflow-spec",
        "continue-workflow-contract",
        "router-continue-workflow",
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_use_workflow_spec_for_router_continue():
    result = expand_stackvm_source(
        '"basic-router" '
        '[ '
        '"payload_file" "payload.yaml" '
        '"kind" "buttons" '
        '"prompt_prefix" "Choose for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"continue_rules" [ "approve" [ answer ] "default" [ answer ] ] '
        '] define-workflow-spec '
        '"basic-router" '
        '"router" '
        '"continue" '
        'use-workflow-spec'
    )

    assert result.expansion_trace == [
        "define-workflow-spec",
        "use-workflow-spec",
        "workflow-spec",
        "continue-workflow-contract",
        "router-continue-workflow",
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_normalized_return_flow_macro():
    result = expand_stackvm_source(
        '"answer" '
        '"payload.yaml" '
        '"router.delegate" '
        '[ drop "missing" answer ] '
        '[ ] '
        '[ "Caller received: " swap concat ] '
        '[ ] '
        'normalized-return-flow'
    )

    assert result.expansion_trace == [
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_normalized_answer_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "done: " swap concat ] '
        'normalized-answer-workflow'
    )

    assert result.expansion_trace == [
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_caller_answer_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "done: " swap concat ] '
        'caller-answer-workflow'
    )

    assert result.expansion_trace == [
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_answer_workflow_contract_for_caller():
    result = expand_stackvm_source(
        '[ '
        '"role" "caller" '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"value_expr" [ "done: " swap concat ] '
        '] answer-workflow-contract'
    )

    assert result.expansion_trace == [
        "answer-workflow-contract",
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_workflow_spec_for_caller_answer():
    result = expand_stackvm_source(
        '[ '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"caller_value_expr" [ "done: " swap concat ] '
        '] "caller" "answer" workflow-spec'
    )

    assert result.expansion_trace == [
        "workflow-spec",
        "answer-workflow-contract",
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_use_workflow_spec_for_caller_answer():
    result = expand_stackvm_source(
        '"basic-caller" '
        '[ '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"caller_value_expr" [ "done: " swap concat ] '
        '] define-workflow-spec '
        '"basic-caller" '
        '"caller" '
        '"answer" '
        'use-workflow-spec'
    )

    assert result.expansion_trace == [
        "define-workflow-spec",
        "use-workflow-spec",
        "workflow-spec",
        "answer-workflow-contract",
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_extend_workflow_spec():
    result = expand_stackvm_source(
        '"base-workflow" '
        '[ '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"caller_value_expr" [ "done: " swap concat ] '
        '] define-workflow-spec '
        '"base-workflow" '
        '"route-workflow" '
        '[ '
        '"caller_field_specs" [ "route" "normalized.route" None ] '
        '"caller_value_expr" [ "normalized.route" shared@ ] '
        '"caller_rules" [ "approve" "router.approve" "default" "router.review" ] '
        '] extend-workflow-spec '
        '"route-workflow" '
        '"caller" '
        '"route" '
        'use-workflow-spec'
    )

    assert result.expansion_trace == [
        "define-workflow-spec",
        "extend-workflow-spec",
        "use-workflow-spec",
        "workflow-spec",
        "route-workflow-contract",
        "caller-route-workflow",
        "normalized-route-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_use_workflow_family_for_caller_answer():
    result = expand_stackvm_source(
        '"answer-family" '
        '[ '
        '"shared" [ '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '] '
        '"caller.answer" [ '
        '"caller_value_expr" [ "done: " swap concat ] '
        '] '
        '] define-workflow-family '
        '"answer-family" '
        '"caller" '
        '"answer" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-workflow-family",
        "use-workflow-family",
        "workflow-spec",
        "answer-workflow-contract",
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_use_workflow_family_for_delegate_route():
    result = expand_stackvm_source(
        '"structured-family" '
        '[ '
        '"shared" [ '
        '"kind" "radio" '
        '"prompt_prefix" "Choose route for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '] '
        '"delegate.route" [ '
        '"delegate_base_expr" [ "{}" yaml> ] '
        '"delegate_rules" [ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        '] '
        '] define-workflow-family '
        '"structured-family" '
        '"delegate" '
        '"route" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-workflow-family",
        "use-workflow-family",
        "workflow-spec",
        "route-workflow-contract",
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_extend_workflow_family():
    result = expand_stackvm_source(
        '"base-family" '
        '[ '
        '"shared" [ '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '] '
        '"caller.answer" [ '
        '"caller_value_expr" [ "done: " swap concat ] '
        '] '
        '] define-workflow-family '
        '"base-family" '
        '"route-family" '
        '[ '
        '"caller.route" [ '
        '"caller_field_specs" [ "route" "normalized.route" None ] '
        '"caller_value_expr" [ "normalized.route" shared@ ] '
        '"caller_rules" [ "approve" "router.approve" "default" "router.review" ] '
        '] '
        '] extend-workflow-family '
        '"route-family" '
        '"caller" '
        '"route" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-workflow-family",
        "extend-workflow-family",
        "use-workflow-family",
        "workflow-spec",
        "route-workflow-contract",
        "caller-route-workflow",
        "normalized-route-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_define_choice_continue_spec():
    result = expand_stackvm_source(
        '"basic-router" '
        '"payload.yaml" '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ answer ] "default" [ answer ] ] '
        'define-choice-continue-spec '
        '"basic-router" '
        '"router" '
        '"continue" '
        'use-workflow-spec'
    )

    assert result.expansion_trace == [
        "define-choice-continue-spec",
        "use-workflow-spec",
        "workflow-spec",
        "continue-workflow-contract",
        "router-continue-workflow",
        "normalized-continue-workflow",
        "normalized-choice-router",
        "normalize-loaded-payload",
        "summary-choice-flow",
        "choice-flow",
        "choice-policy",
        "choice-request",
        "prompt-store-policy",
    ]


def test_expand_stackvm_source_supports_builtin_define_choice_answer_family():
    result = expand_stackvm_source(
        '"answer-family" '
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "done: " swap concat ] '
        '"buttons" '
        '"Choose for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "reject" "Reject" "reject" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'define-choice-answer-family '
        '"answer-family" '
        '"caller" '
        '"answer" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-choice-answer-family",
        "use-workflow-family",
        "workflow-spec",
        "answer-workflow-contract",
        "caller-answer-workflow",
        "normalized-answer-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-answer-flow",
        "returned-answer-policy",
        "finalize-from",
        "returned-answer",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_define_choice_continue_answer_family():
    result = expand_stackvm_source(
        '"pipeline-family" '
        '"payload.yaml" '
        '"checklist" '
        '"Choose actions for " '
        '"normalized.actions" '
        '[ "delegate" "Delegate" "delegate" "review" "Review" "review" ] '
        '[ "min_selected" 1 ] '
        '"contains" '
        '[ ] '
        '[ "delegate" [ answer ] "default" [ answer ] ] '
        '"radio" '
        '"Choose delegate plan for " '
        '"normalized.plan" '
        '[ "review-first" "Review First" "review-first" "delegate-now" "Delegate Now" "delegate-now" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "review-first" [ "review-first" ] "default" [ "delegate-now" ] ] '
        'define-choice-continue-answer-family '
        '"pipeline-family" '
        '"delegate" '
        '"answer" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-choice-continue-answer-family",
        "use-workflow-family",
        "workflow-spec",
        "answer-workflow-contract",
        "delegate-answer-workflow",
        "summary-answer-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-policy",
    ]


def test_expand_stackvm_source_supports_builtin_define_choice_route_family():
    result = expand_stackvm_source(
        '"route-family" '
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "route" "normalized.route" None ] '
        '[ "normalized.route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        '"radio" '
        '"Choose route for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> ] '
        '[ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        'define-choice-route-family '
        '"route-family" '
        '"delegate" '
        '"route" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-choice-route-family",
        "use-workflow-family",
        "workflow-spec",
        "route-workflow-contract",
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_define_choice_finalize_family():
    result = expand_stackvm_source(
        '"finalize-family" '
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "route" "normalized.route" None ] '
        '[ "normalized.route" shared@ ] '
        '"radio" '
        '"Choose route for " '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> ] '
        '[ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        'define-choice-finalize-family '
        '"finalize-family" '
        '"caller" '
        '"finalize" '
        'use-workflow-family'
    )

    assert result.expansion_trace == [
        "define-choice-finalize-family",
        "use-workflow-family",
        "workflow-spec",
        "finalize-workflow-contract",
        "caller-finalize-workflow",
        "normalized-finalize-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-finalize-flow",
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_normalized_route_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "route" "normalized.route" None ] '
        '[ "normalized.route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'normalized-route-workflow'
    )

    assert result.expansion_trace == [
        "normalized-route-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_caller_route_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "route" "normalized.route" None ] '
        '[ "normalized.route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'caller-route-workflow'
    )

    assert result.expansion_trace == [
        "caller-route-workflow",
        "normalized-route-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_route_workflow_contract_for_caller():
    result = expand_stackvm_source(
        '[ '
        '"role" "caller" '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"field_specs" [ "route" "normalized.route" None ] '
        '"value_expr" [ "normalized.route" shared@ ] '
        '"rules" [ "approve" "router.approve" "default" "router.review" ] '
        '] route-workflow-contract'
    )

    assert result.expansion_trace == [
        "route-workflow-contract",
        "caller-route-workflow",
        "normalized-route-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-route-flow",
        "returned-policy",
        "returned-handoff-switch",
        "handoff-switch",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_workflow_spec_for_delegate_route():
    result = expand_stackvm_source(
        '[ '
        '"kind" "radio" '
        '"prompt_prefix" "Choose route for " '
        '"value_path" "normalized.choice" '
        '"options" [ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '"attrs" [ ] '
        '"match_mode" "exact" '
        '"prepare_expr" [ ] '
        '"delegate_base_expr" [ "{}" yaml> ] '
        '"delegate_rules" [ "approve" [ "route" "approve" ] "default" [ "route" "review" ] ] '
        '] "delegate" "route" workflow-spec'
    )

    assert result.expansion_trace == [
        "workflow-spec",
        "route-workflow-contract",
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_normalized_finalize_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "mode" "normalized.mode" None ] '
        '[ "mode=" "normalized.mode" shared@ concat ] '
        'normalized-finalize-workflow'
    )

    assert result.expansion_trace == [
        "normalized-finalize-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-finalize-flow",
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_caller_finalize_workflow_macro():
    result = expand_stackvm_source(
        '"payload.yaml" '
        '"delegate.agent" '
        '[ "missing" answer ] '
        '[ "mode" "normalized.mode" None ] '
        '[ "mode=" "normalized.mode" shared@ concat ] '
        'caller-finalize-workflow'
    )

    assert result.expansion_trace == [
        "caller-finalize-workflow",
        "normalized-finalize-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-finalize-flow",
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_finalize_workflow_contract_for_caller():
    result = expand_stackvm_source(
        '[ '
        '"role" "caller" '
        '"payload_file" "payload.yaml" '
        '"delegate_target" "delegate.agent" '
        '"missing_case" [ "missing" answer ] '
        '"field_specs" [ "mode" "normalized.mode" None ] '
        '"value_expr" [ "mode=" "normalized.mode" shared@ concat ] '
        '] finalize-workflow-contract'
    )

    assert result.expansion_trace == [
        "finalize-workflow-contract",
        "caller-finalize-workflow",
        "normalized-finalize-workflow",
        "normalized-return-flow",
        "normalize-loaded-payload",
        "return-contract-flow",
        "return-field-finalize-flow",
        "returned-policy",
        "returned-finalize",
        "finalize-from",
        "project-shared",
        "returned-yaml",
        "return-flow",
        "return-handoff",
    ]


def test_expand_stackvm_source_supports_builtin_record_fields_macro():
    result = expand_stackvm_source(
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "decision.route" "approve" "decision.note" "approved by delegate" ] '
        'record-fields'
    )

    assert result.expansion_trace == ["record-fields"]


def test_expand_stackvm_source_supports_builtin_choice_structured_decision_macro():
    result = expand_stackvm_source(
        '"radio" '
        '[ "Choose route for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ] '
        '"default" [ "decision.route" "review" ] ] '
        'choice-structured-decision'
    )

    assert result.expansion_trace == [
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_choice_contract_macro_with_structured_mode():
    result = expand_stackvm_source(
        '"structured" '
        '"radio" '
        '[ "Choose route for " "normalized.summary" shared@ concat ] '
        '"normalized.choice" '
        '[ "approve" "Approve" "approve" "review" "Review" "review" ] '
        '[ ] '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ] '
        '"default" [ "decision.route" "review" ] ] '
        'choice-contract'
    )

    assert result.expansion_trace == [
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]


def test_expand_stackvm_source_supports_builtin_prompt_return_policy_macro_with_contains_mode():
    result = expand_stackvm_source(
        '[ "{kind: checklist, prompt: Choose, options: [{id: delegate, label: Delegate, value: delegate}]}" yaml> ] '
        '"normalized.actions" '
        '"contains" '
        '[ ] '
        '[ "default" [ ", " join ] ] '
        'prompt-return-policy'
    )

    assert result.expansion_trace == ["prompt-return-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_return_policy_macro_with_default_only_contains_mode():
    result = expand_stackvm_source(
        '[ "{kind: checklist, prompt: Choose, options: [{id: git, label: Git, value: git}]}" yaml> ] '
        '"normalized.selected_tools" '
        '"contains" '
        '[ ] '
        '[ "default" [ ", " join ] ] '
        'prompt-return-policy'
    )

    assert result.expansion_trace == ["prompt-return-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_return_yaml_policy_macro():
    result = expand_stackvm_source(
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ "approve" [ "{}" yaml> "approve" "route" dict-set ] "default" [ "{}" yaml> "review" "route" dict-set ] ] '
        'prompt-return-yaml-policy'
    )

    assert result.expansion_trace == ["prompt-return-yaml-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_return_merge_policy_macro():
    result = expand_stackvm_source(
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "{}" yaml> "approve" "decision.route" set-in ] "default" [ "{}" yaml> "review" "decision.route" set-in ] ] '
        'prompt-return-merge-policy'
    )

    assert result.expansion_trace == ["prompt-return-merge-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_decision_macro_with_answer_mode():
    result = expand_stackvm_source(
        '"answer" '
        '[ "{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ "approved" ] "default" [ "rejected" ] ] '
        'prompt-decision'
    )

    assert result.expansion_trace == ["prompt-decision", "prompt-return-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_decision_macro_with_yaml_mode():
    result = expand_stackvm_source(
        '"yaml" '
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ ] '
        '[ "approve" [ "{}" yaml> "route" "approve" dict-set ] "default" [ "{}" yaml> "route" "review" dict-set ] ] '
        'prompt-decision'
    )

    assert result.expansion_trace == ["prompt-decision", "prompt-return-yaml-policy"]


def test_expand_stackvm_source_supports_builtin_prompt_decision_macro_with_merge_mode():
    result = expand_stackvm_source(
        '"yaml-merge" '
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '"exact" '
        '[ ] '
        '[ "{}" yaml> "delegate" "meta.source" set-in ] '
        '[ "approve" [ "{}" yaml> "approve" "decision.route" set-in ] "default" [ "{}" yaml> "review" "decision.route" set-in ] ] '
        'prompt-decision'
    )

    assert result.expansion_trace == ["prompt-decision", "prompt-return-merge-policy"]


def test_expand_stackvm_source_supports_builtin_validated_match_macro():
    result = expand_stackvm_source(
        '[ normalized-config ] '
        '[ "{enabled: true}" yaml> [ "enabled" "route" store-set ] _ [ "default" "route" store-set ] ] '
        '[ drop "invalid" "route" store-set ] '
        'validated-match'
    )

    assert result.expansion_trace == ["validated-match"]
    assert result.ast == [
        [("sym", "normalized-config")],
        ("sym", "call"),
        ("sym", "dup"),
        ("str", "success"),
        ("sym", "dict-get?"),
        [
            ("str", "value"),
            ("sym", "dict-get?"),
            [
                ("str", "{enabled: true}"),
                ("sym", "yaml>"),
                [("str", "enabled"), ("str", "route"), ("sym", "store-set")],
                ("sym", "_"),
                [("str", "default"), ("str", "route"), ("sym", "store-set")],
            ],
            ("sym", "match"),
        ],
        [[("sym", "drop"), ("str", "invalid"), ("str", "route"), ("sym", "store-set")], ("sym", "call")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_schema_route_macro():
    result = expand_stackvm_source(
        '"config_errors" None '
        '[ "{enabled: true}" yaml> [ "enabled" "route" store-set ] _ [ "default" "route" store-set ] ] '
        '[ drop "invalid" "route" store-set ] '
        'schema-route'
    )

    assert result.expansion_trace == ["schema-route", "validated-match"]
    assert result.ast == [
        ("sym", "dup"),
        ("str", "errors"),
        ("sym", "dict-get?"),
        ("str", "config_errors"),
        ("sym", "shared!"),
        [
            ("none", None),
            ("sym", "none?"),
            [],
            [
                ("sym", "dup"),
                ("str", "value"),
                ("sym", "dict-get?"),
                ("sym", "dup"),
                ("none", None),
                ("sym", "store-set"),
                ("sym", "drop"),
            ],
            ("sym", "if"),
        ],
        ("sym", "call"),
        ("sym", "dup"),
        ("str", "success"),
        ("sym", "dict-get?"),
        [
            ("str", "value"),
            ("sym", "dict-get?"),
            [
                ("str", "{enabled: true}"),
                ("sym", "yaml>"),
                [("str", "enabled"), ("str", "route"), ("sym", "store-set")],
                ("sym", "_"),
                [("str", "default"), ("str", "route"), ("sym", "store-set")],
            ],
            ("sym", "match"),
        ],
        [[("sym", "drop"), ("str", "invalid"), ("str", "route"), ("sym", "store-set")], ("sym", "call")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_handoff_rules_macro():
    result = expand_stackvm_source(
        '[ [ "total" shared@ 10 >= ] "high" "router.high" [ True ] "low" "router.low" ] '
        '"normalized.band" '
        'handoff-rules'
    )

    assert result.expansion_trace == ["handoff-rules"]


def test_expand_stackvm_source_supports_builtin_handoff_switch_macro():
    result = expand_stackvm_source(
        '[ "normalized.final_route" shared@ ] '
        '[ "approve" "router.approve" "escalate" "router.escalate" "default" "router.review" ] '
        'handoff-switch'
    )

    assert result.expansion_trace == ["handoff-switch"]
    assert result.ast == [
        [("str", "normalized.final_route"), ("sym", "shared@")],
        ("sym", "call"),
        [
            ("str", "approve"),
            [("str", "router.approve"), ("sym", "handoff")],
            ("str", "escalate"),
            [("str", "router.escalate"), ("sym", "handoff")],
            ("str", "default"),
            [("str", "router.review"), ("sym", "handoff")],
        ],
        ("sym", "switch"),
    ]


def test_expand_stackvm_source_supports_builtin_project_shared_macro():
    result = expand_stackvm_source(
        '[ [ "route" dict-get ] "normalized.final_route" [ "note" dict-get ] "normalized.delegate_note" ] '
        '[ "normalized.final_route" shared@ answer ] '
        'project-shared'
    )

    assert result.expansion_trace == ["project-shared"]
    serialized = " ".join(
        f"{item[1]}" if isinstance(item, tuple) else str(item)
        for item in result.ast
    )
    assert "__project_shared_" in serialized
    assert ("str", "normalized.final_route") in result.ast
    assert ("str", "normalized.delegate_note") in result.ast
    assert ("sym", "shared!?") in result.ast
    assert [("str", "route"), ("sym", "dict-get")] in result.ast
    assert [("str", "note"), ("sym", "dict-get")] in result.ast
    assert result.ast[-3:] == [
        ("str", "normalized.final_route"),
        ("sym", "shared@"),
        ("sym", "answer"),
    ]
    assert result.ast[:3] == [
        ("sym", "dup"),
        ("str", "__project_shared_1"),
        ("sym", "store-set"),
    ]


def test_expand_stackvm_source_supports_builtin_returned_yaml_macro():
    result = expand_stackvm_source(
        '[ "missing" answer ] [ "route" dict-get "normalized.final_route" shared!? drop ] returned-yaml'
    )

    assert result.expansion_trace == ["returned-yaml"]
    assert result.ast == [
        ("str", "last_delegated_result"),
        ("sym", "shared@"),
        ("str", "answer"),
        ("sym", "dict-get"),
        ("sym", "dup"),
        ("sym", "none?"),
        [("sym", "drop"), [("str", "missing"), ("sym", "answer")], ("sym", "call")],
        [
            ("sym", "yaml>"),
            [("str", "route"), ("sym", "dict-get"), ("str", "normalized.final_route"), ("sym", "shared!?"), ("sym", "drop")],
            ("sym", "call"),
        ],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_returned_answer_macro():
    result = expand_stackvm_source(
        '[ "missing" answer ] [ "Caller received: " swap concat ] returned-answer'
    )

    assert result.expansion_trace == ["returned-answer"]
    assert result.ast == [
        ("str", "last_delegated_result"),
        ("sym", "shared@"),
        ("str", "answer"),
        ("sym", "dict-get"),
        ("sym", "dup"),
        ("sym", "none?"),
        [("sym", "drop"), [("str", "missing"), ("sym", "answer")], ("sym", "call")],
        [[("str", "Caller received: "), ("sym", "swap"), ("sym", "concat")], ("sym", "call")],
        ("sym", "if"),
    ]


def test_expand_stackvm_source_supports_builtin_prompt_store_macro():
    result = expand_stackvm_source(
        '[ "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> ] '
        '"normalized.choice" '
        '[ "Selected " swap concat answer ] '
        'prompt-store'
    )

    assert result.expansion_trace == ["prompt-store"]
    assert result.ast == [
        [
            (
                "str",
                "{kind: radio, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}",
            ),
            ("sym", "yaml>"),
        ],
        ("sym", "call"),
        ("sym", "prompt-interaction"),
        ("sym", "dup"),
        ("str", "normalized.choice"),
        ("sym", "shared!?"),
        ("sym", "drop"),
        [("str", "Selected "), ("sym", "swap"), ("sym", "concat"), ("sym", "answer")],
        ("sym", "call"),
    ]


def test_expand_stackvm_source_supports_builtin_ask_from_macro():
    result = expand_stackvm_source(
        '[ "Proceed with " "normalized.summary" shared@ concat "?" concat ] ask-from'
    )

    assert result.expansion_trace == ["ask-from"]
    assert result.ast == [
        [
            ("str", "Proceed with "),
            ("str", "normalized.summary"),
            ("sym", "shared@"),
            ("sym", "concat"),
            ("str", "?"),
            ("sym", "concat"),
        ],
        ("sym", "call"),
        ("sym", "ask-user"),
    ]


def test_expand_stackvm_source_supports_builtin_prompt_store_text_macro():
    result = expand_stackvm_source(
        '[ "Proceed with " "normalized.summary" shared@ concat "?" concat ] '
        '"normalized.reply" '
        '[ bool> ] '
        'prompt-store-text'
    )

    assert result.expansion_trace == ["prompt-store-text"]
    assert result.ast == [
        [
            ("str", "Proceed with "),
            ("str", "normalized.summary"),
            ("sym", "shared@"),
            ("sym", "concat"),
            ("str", "?"),
            ("sym", "concat"),
        ],
        ("sym", "call"),
        ("sym", "prompt-user"),
        ("sym", "dup"),
        ("str", "normalized.reply"),
        ("sym", "shared!?"),
        ("sym", "drop"),
        [("sym", "bool>")],
        ("sym", "call"),
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


def test_expand_stackvm_source_tracks_generated_nested_macro_frames():
    result = expand_stackvm_source(
        '[ ] [ inner ] "outer" defmacro '
        '[ ] [ "done" answer ] "inner" defmacro '
        'outer'
    )

    assert result.expansion_trace == ["outer", "inner"]
    assert len(result.expansion_frames) == 2
    assert result.expansion_frames[0].macro_name == "outer"
    assert result.expansion_frames[0].call_site == "line 1, cols 71-75"
    assert result.expansion_frames[1].macro_name == "inner"
    assert result.expansion_frames[1].generated_by == "outer"
    assert result.expansion_frames[1].call_site == "line 1, cols 71-75"
