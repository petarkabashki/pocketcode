from __future__ import annotations

import pytest

from pocketcode.core.stackvm_expander import expand_stackvm_source
from pocketcode.core.stackvm_parser import parse_stackvm_source, serialize_stackvm_ast
from pocketcode.core.stackvm_validator import analyze_stackvm_ast, collect_stackvm_authoring_warnings, validate_stackvm_ast


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


def test_collect_stackvm_authoring_warnings_flags_manual_tool_loop_pattern():
    source = (
        "! manual tool loop\n"
        'last-tool-result none? [ "resource_root.pocketcode.echo" "{text: ping}" yaml> tool-request ] '
        '[ "last_tool_result.text" shared@ answer ] if'
    )
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(source),
        source=source,
    )

    assert warnings == [
        {
            "code": "manual-tool-loop",
            "message": (
                "StackVM source uses the manual 'last-tool-result none?' tool loop pattern. "
                "Prefer the built-in 'tool-once' macro for tool-first flows."
            ),
            "location": "line 2, cols 1-138",
            "span": {
                "start_line": 2,
                "start_column": 1,
                "end_line": 2,
                "end_column": 138,
            },
        }
    ]


def test_collect_stackvm_authoring_warnings_does_not_flag_tool_once_macro_usage():
    warnings = collect_stackvm_authoring_warnings(
        parse_stackvm_source(
            '"resource_root.pocketcode.echo" [ "{text: ping}" yaml> ] [ "last_tool_result.text" shared@ answer ] tool-once'
        )
    )

    assert warnings == []


def test_collect_stackvm_authoring_warnings_flags_manual_prompt_route_pattern():
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
            "code": "manual-prompt-route",
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


def test_analyze_stackvm_ast_flags_stack_underflow():
    analysis = analyze_stackvm_ast(parse_stackvm_source('"hello" concat'), source='"hello" concat')

    assert analysis["diagnostic_count"] == 1
    assert analysis["diagnostics"][0]["code"] == "stack-underflow"
    assert analysis["diagnostics"][0]["location"] == "line 1, cols 9-14"


def test_analyze_stackvm_ast_tracks_effects_and_user_word_contracts():
    source = '[ "done" answer ] "decide" define decide'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["effect_kinds"] == ["final"]
    assert analysis["host_surfaces_used"] == ["portable_host"]
    assert analysis["standalone_script_compatible"] is True
    assert analysis["word_metadata_summary"]["decide"]["pops"] == 0
    assert analysis["word_metadata_summary"]["decide"]["pushes"] == 0
    assert analysis["word_metadata_summary"]["decide"]["host_surface"] == "core"
    assert analysis["word_metadata_summary"]["decide"]["definition_location"] == "line 1, cols 1-17"
    assert analysis["word_metadata_summary"]["decide"]["output_shape"] == []


def test_analyze_stackvm_ast_reports_pocketcoder_host_dependencies():
    source = 'request "resource_root.pocketcode.echo" "{text: ping}" yaml> tool-request'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["host_surfaces_used"] == ["pocketcoder_host", "portable_host"]
    assert analysis["pocketcoder_host_words_used"] == ["tool-request"]
    assert analysis["standalone_script_compatible"] is False


def test_analyze_stackvm_ast_treats_portable_prompt_llm_and_tool_words_as_standalone_compatible():
    source = (
        'tool-definitions drop '
        '"Proceed?" prompt-user drop '
        '"{kind: buttons, prompt: Pick, options: [{id: ok, label: OK, value: ok}]}" prompt-interaction drop '
        '"Say hi" llm-call drop '
        '"demo.echo" "{text: ping}" yaml> tool-call drop '
        '"Need confirmation?" ask-user'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["host_surfaces_used"] == ["portable_host"]
    assert analysis["pocketcoder_host_words_used"] == []
    assert analysis["standalone_script_compatible"] is True


def test_analyze_stackvm_ast_preserves_authored_location_through_macro_expansion():
    source = '"resource_root.pocketcode.echo" [ "{text: ping}" yaml> ] [ "done" answer ] tool-once'
    expanded = expand_stackvm_source(source)
    analysis = analyze_stackvm_ast(
        expanded.ast,
        source=serialize_stackvm_ast(expanded.ast),
        authored_spans=expanded.ast_spans,
    )

    if_step = next(
        step for step in analysis["shape_flow"] if isinstance(step, dict) and step.get("label") == "if"
    )
    assert if_step["authored_location"] == expanded.expansion_frames[0].call_site


def test_analyze_stackvm_ast_uses_argument_location_for_substituted_macro_nodes():
    source = '[ op ] [ op ] "emit" defmacro answer emit'
    expanded = expand_stackvm_source(source)
    analysis = analyze_stackvm_ast(
        expanded.ast,
        source=serialize_stackvm_ast(expanded.ast),
        authored_spans=expanded.ast_spans,
    )

    answer_step = next(
        step for step in analysis["shape_flow"] if isinstance(step, dict) and step.get("label") == "answer"
    )
    assert answer_step["authored_location"] == "line 1, cols 31-36"


def test_analyze_stackvm_ast_carries_helper_definition_location_into_scope_summary():
    source = '[ 1 + ] "inc" define 0 inc'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    word_scope = next(
        summary for summary in analysis["scope_summaries"]
        if isinstance(summary, dict) and summary.get("scope") == "main > word:inc" and summary.get("kind") == "region"
    )
    assert word_scope["definition_location"] == "line 1, cols 1-7"


def test_analyze_stackvm_ast_carries_authored_locations_into_replayed_helper_steps():
    source = '[ dup 1 + swap drop ] "inc-copy" define 0 inc-copy'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    helper_steps = [
        step
        for step in analysis["shape_flow"]
        if isinstance(step, dict) and step.get("scope") == "main > word:inc-copy"
    ]

    assert [step["label"] for step in helper_steps] == ["dup", "1", "+", "swap", "drop"]
    assert [step["authored_location"] for step in helper_steps] == [
        "line 1, cols 3-5",
        "line 1, col 7",
        "line 1, col 9",
        "line 1, cols 11-14",
        "line 1, cols 16-19",
    ]


def test_analyze_stackvm_ast_preserves_user_word_output_shape():
    source = '[ 1 + ] "inc" define 0 inc'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_min_stack_depth"] == 1
    assert analysis["word_metadata_summary"]["inc"]["pops"] == 1
    assert analysis["word_metadata_summary"]["inc"]["pushes"] == 1
    assert analysis["word_metadata_summary"]["inc"]["output_shape"] == ["unknown"]


def test_analyze_stackvm_ast_infers_more_specific_builtin_output_shapes():
    source = '[ len ] "measure" define "[a, b]" yaml> measure'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_min_stack_depth"] == 1
    assert analysis["word_metadata_summary"]["measure"]["output_shape"] == ["int"]


def test_analyze_stackvm_ast_infers_boolean_helper_output_shape():
    source = '[ empty? ] "is-empty" define "[]" yaml> is-empty'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["word_metadata_summary"]["is-empty"]["output_shape"] == ["bool"]


def test_analyze_stackvm_ast_tracks_shape_through_yaml_and_dict_get():
    source = '"{count: 2, title: hello}" yaml> "count" dict-get?'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["int"]


def test_analyze_stackvm_ast_tracks_shape_through_yaml_and_list_get():
    source = '"[alpha, beta]" yaml> 1 list-get?'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["str"]


def test_analyze_stackvm_ast_tracks_collection_word_output_shapes():
    source = (
        '"[1, 2, 3]" yaml> [ 10 * ] map '
        '"[[1], [2, 3]]" yaml> [ ] flat-map '
        '"[1, 2, 3]" yaml> [ 2 > ] filter '
        '"[1, 2, 3]" yaml> [ 2 > ] find '
        '"[1, 2, 3]" yaml> [ 2 > ] any? '
        '"[1, 2, 3]" yaml> [ 0 > ] all? '
        '"[{score: 2}, {score: 1}]" yaml> [ "score" dict-get ] sort-by '
        '"[{kind: a}, {kind: b}]" yaml> [ "kind" dict-get ] group-by'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["list", "list", "list", "unknown", "bool", "bool", "list", "dict"]


def test_analyze_stackvm_ast_tracks_schema_word_output_shapes():
    source = (
        '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-check '
        "\"{count: '7'}\" yaml> " '"{type: object, properties: {count: {type: integer}}}" yaml> schema-apply'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["dict", "dict"]


def test_analyze_stackvm_ast_flags_illegal_child_effects_for_data_collection_words():
    source = '"[1]" yaml> [ "bad" answer ] map'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert any(
        diagnostic["code"] == "illegal-child-effect" and diagnostic.get("word") == "map"
        for diagnostic in analysis["diagnostics"]
    )

    source = '"[1]" yaml> [ "bad" answer ] flat-map'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(
        diagnostic["code"] == "illegal-child-effect" and diagnostic.get("word") == "flat-map"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_tracks_shape_through_yaml_and_get_in():
    source = '"{meta: {enabled: true}}" yaml> "meta.enabled" get-in?'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["bool"]
    assert analysis["shape_flow"]
    assert analysis["shape_flow"][-1]["label"] == "get-in?"
    assert analysis["shape_flow"][-1]["scope"] == "main"
    assert analysis["shape_flow"][-1]["stack_shape"] == ["bool"]


def test_analyze_stackvm_ast_tracks_yaml_dump_output_shape():
    source = '"{route: approve}" yaml> "approved by delegate" "note" dict-set yaml<'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_stack_shape"] == ["str"]


def test_analyze_stackvm_ast_records_scoped_shape_flow_for_nested_regions():
    source = '[ 1 + ] "inc" define 0 [ dup 3 < ] [ inc ] while'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    scopes = [step.get("scope") for step in analysis["shape_flow"] if isinstance(step, dict)]

    assert "main" in scopes
    assert "main > while:condition" in scopes
    assert "main > while:body" in scopes
    assert "main > while:body > word:inc" in scopes
    scope_summaries = [summary for summary in analysis["scope_summaries"] if isinstance(summary, dict)]
    assert any(summary.get("scope") == "main > while:condition" and summary.get("kind") == "region" for summary in scope_summaries)
    while_merge = next(summary for summary in scope_summaries if summary.get("scope") == "main > while:merge")
    assert while_merge["kind"] == "merge"
    assert while_merge["reason"] == "shape-preserving-loop"
    assert while_merge["precision"] == "precise"
    assert while_merge["location"] == "line 1, cols 44-48"
    decisions = [decision for decision in analysis["analysis_decisions"] if isinstance(decision, dict)]
    assert any(
        decision.get("scope") == "main > while:merge"
        and decision.get("reason") == "shape-preserving-loop"
        and decision.get("location") == "line 1, cols 44-48"
        for decision in decisions
    )


def test_analyze_stackvm_ast_marks_optional_no_match_merges_explicitly():
    source = '"x" [ "y" [ "matched" ] ] switch'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    merge_summary = next(
        summary
        for summary in analysis["scope_summaries"]
        if isinstance(summary, dict) and summary.get("scope") == "main > switch:merge"
    )

    assert merge_summary["reason"] == "optional-no-match-path"
    assert merge_summary["precision"] == "optional-path"
    assert merge_summary["location"] == "line 1, cols 27-32"
    assert any(
        decision.get("scope") == "main > switch:merge"
        and decision.get("reason") == "optional-no-match-path"
        and decision.get("location") == "line 1, cols 27-32"
        for decision in analysis["analysis_decisions"]
        if isinstance(decision, dict)
    )


def test_analyze_stackvm_ast_preserves_shape_through_dup_helper():
    source = '[ dup ] "copy" define True copy'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_min_stack_depth"] == 2
    assert analysis["word_metadata_summary"]["copy"]["output_shape"] == ["unknown", "unknown"]


def test_analyze_stackvm_ast_preserves_shape_through_over_helper():
    source = '[ over ] "copy-second" define 1 False copy-second'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["diagnostic_count"] == 0
    assert analysis["final_min_stack_depth"] == 3
    assert analysis["word_metadata_summary"]["copy-second"]["output_shape"] == ["unknown", "unknown", "unknown"]


def test_analyze_stackvm_ast_flags_illegal_parallel_map_child_effects():
    source = '"[alpha]" yaml> [ "bad" answer ] parallel-map'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert any(diagnostic["code"] == "illegal-child-effect" for diagnostic in analysis["diagnostics"])
    assert any(diagnostic.get("location") == "line 1, cols 34-45" for diagnostic in analysis["diagnostics"])


def test_analyze_stackvm_ast_flags_reduce_child_that_may_not_leave_accumulator():
    analysis = analyze_stackvm_ast(parse_stackvm_source('"[1, 2]" yaml> 0 [ drop drop ] reduce'))

    assert any(
        diagnostic["code"] == "dynamic-stack-shape" and diagnostic.get("word") == "reduce"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_flags_reduce_child_that_leaves_extra_values():
    source = '"[1, 2]" yaml> 0 [ over + ] reduce'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert any(
        diagnostic["code"] == "reduce-child-arity" and diagnostic.get("word") == "reduce"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_models_switch_without_default_as_optional_branch():
    source = '"x" [ "y" [ "matched" ] ] switch'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["final_min_stack_depth"] == 0


def test_analyze_stackvm_ast_models_cond_without_default_as_optional_branch():
    source = '[ [ False ] [ "matched" ] ] cond'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["final_min_stack_depth"] == 0


def test_analyze_stackvm_ast_models_match_without_wildcard_as_optional_branch():
    source = '"x" [ "y" [ "matched" ] ] match'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["final_min_stack_depth"] == 0
    merge_summary = next(
        summary
        for summary in analysis["scope_summaries"]
        if isinstance(summary, dict) and summary.get("scope") == "main > match:merge"
    )
    assert merge_summary["reason"] == "optional-no-match-path"


def test_analyze_stackvm_ast_models_match_with_wildcard_as_exhaustive():
    source = '"x" [ _ [ "matched" ] ] match'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    merge_summary = next(
        summary
        for summary in analysis["scope_summaries"]
        if isinstance(summary, dict) and summary.get("scope") == "main > match:merge"
    )
    assert merge_summary["reason"] == "exhaustive-match-merge"
    assert merge_summary["precision"] == "merged"


def test_analyze_stackvm_ast_treats_shape_preserving_while_more_precisely():
    source = '0 [ dup 3 < ] [ dup 1 + swap drop ] while'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["final_min_stack_depth"] == 1
    assert not any(
        diagnostic["code"] == "dynamic-stack-shape" and diagnostic.get("word") == "while"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_treats_shape_preserving_while_with_helper_more_precisely():
    source = '[ 1 + ] "inc" define 0 [ dup 3 < ] [ inc ] while'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert analysis["final_min_stack_depth"] == 1
    assert not any(
        diagnostic["code"] == "dynamic-stack-shape" and diagnostic.get("word") == "while"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_keeps_conservative_warning_for_shape_changing_while():
    source = '0 [ dup 3 < ] [ dup ] while'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)

    assert any(
        diagnostic["code"] == "dynamic-stack-shape" and diagnostic.get("word") == "while"
        for diagnostic in analysis["diagnostics"]
    )


def test_analyze_stackvm_ast_respects_explicit_output_shape():
    source = '[ 10 > ] ( int -- bool ) "is-big" define 5 is-big'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert analysis["word_metadata_summary"]["is-big"]["output_shape"] == ["bool"]

def test_analyze_stackvm_ast_catches_signature_mismatch():
    source = '[ 1 + ] ( int -- str ) "bad-sig" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 1
    assert analysis["diagnostics"][0]["code"] == "signature-mismatch"

def test_analyze_stackvm_ast_catches_signature_input_deficit():
    # Body consumes 2 items (+) but signature only declares 1 input.
    source = '[ + ] ( int -- int ) "bad-inputs" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(d["code"] == "signature-mismatch" and "inputs" in d["message"] for d in analysis["diagnostics"])

def test_analyze_stackvm_ast_catches_signature_output_mismatch():
    # Body leaves 1 item but signature declares 2 outputs.
    source = '[ 1 ] ( -- int int ) "bad-outputs" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(d["code"] == "signature-mismatch" and "outputs" in d["message"] for d in analysis["diagnostics"])

def test_collect_stackvm_authoring_warnings_flags_signature_mismatch():
    source = '[ 1 + ] ( int -- str ) "bad-sig" define'
    warnings = collect_stackvm_authoring_warnings(parse_stackvm_source(source))
    assert any(w["code"] == "signature-mismatch" for w in warnings)

def test_analyze_stackvm_ast_catches_unknown_dict_key():
    source = '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-apply "success" dict-get? drop "value" dict-get? "scroe" dict-get?'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-dict-key" for diag in analysis["diagnostics"])

def test_collect_stackvm_authoring_warnings_flags_nested_if_smell():
    # 3 levels of nested if (0 -> 1 -> 2)
    source = 'True [ True [ True [ "smell" ] [ "ok" ] if ] [ ] if ] [ ] if'
    warnings = collect_stackvm_authoring_warnings(parse_stackvm_source(source))
    assert any(w["code"] == "nested-if-smell" for w in warnings)

def test_collect_stackvm_authoring_warnings_flags_manual_dict_get_chain():
    source = 'dup "key1" dict-get? drop dup "key2" dict-get? drop'
    warnings = collect_stackvm_authoring_warnings(parse_stackvm_source(source))
    assert any(w["code"] == "manual-dict-get-chain" for w in warnings)


def test_analyze_stackvm_ast_recursive_signature_validation():
    # Recursive fact example using signature for recursive case analysis.
    # Inside 'fact', the recursive call 'fact' uses the signature (1 pop, 1 push).
    source = '[ dup 0 > [ 1 - fact * ] [ drop 1 ] if ] ( int -- int ) "fact" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert analysis["word_metadata_summary"]["fact"]["pops"] == 1
    assert analysis["word_metadata_summary"]["fact"]["pushes"] == 1


def test_analyze_stackvm_ast_nested_word_signatures():
    # Defining and using a typed word inside another typed word.
    source = '[ [ 1 + ] ( int -- int ) "inc" define inc inc ] ( int -- int ) "add-two" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert analysis["word_metadata_summary"]["inc"]["pops"] == 1
    assert analysis["word_metadata_summary"]["add-two"]["pops"] == 1


def test_analyze_stackvm_ast_catches_signature_mismatch_in_nested_word():
    # Outer is fine, but inner has a mismatch (returns 2 items but declares 1).
    source = '[ [ 1 2 ] ( -- int ) "broken-inner" define broken-inner ] ( -- int ) "outer" define'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(d["code"] == "signature-mismatch" and "broken-inner" in d["message"] for d in analysis["diagnostics"])


def test_analyze_stackvm_ast_exhaustive_switch_via_enum():
    # Define a schema with an enum, apply it, and verify switch handles it exhaustively.
    source = (
        '"{status: open}" yaml> '
        '"{type: object, properties: {status: {type: string, enum: [open, closed]}}}" yaml> '
        'schema-apply "value.status" get-in? '
        '[ "open" [ 1 ] "closed" [ 2 ] ] switch'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    # If exhaustive, min depth should be 1 (both branches push 1)
    assert analysis["final_min_stack_depth"] == 1
    
    merge_summary = next(s for s in analysis["scope_summaries"] if s.get("scope") == "main > switch:merge")
    assert merge_summary["reason"] == "exhaustive-switch-merge"
    assert merge_summary["precision"] == "merged"


def test_analyze_stackvm_ast_non_exhaustive_switch_via_enum():
    # Only 'open' is handled, but domain includes 'closed'.
    source = (
        '"{status: open}" yaml> '
        '"{type: object, properties: {status: {type: string, enum: [open, closed]}}}" yaml> '
        'schema-apply "value.status" get-in? '
        '[ "open" [ 1 ] ] switch'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    # Non-exhaustive means min depth is 0 (the no-match path pushes nothing)
    assert analysis["final_min_stack_depth"] == 0
    
    merge_summary = next(s for s in analysis["scope_summaries"] if s.get("scope") == "main > switch:merge")
    assert merge_summary["reason"] == "optional-no-match-path"


def test_analyze_stackvm_ast_exhaustive_match_via_enum():
    source = (
        '"{status: open}" yaml> '
        '"{type: object, properties: {status: {type: string, enum: [open, closed]}}}" yaml> '
        'schema-apply "value.status" get-in? '
        '[ "open" [ 1 ] "closed" [ 2 ] ] match'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["final_min_stack_depth"] == 1
    
    merge_summary = next(s for s in analysis["scope_summaries"] if s.get("scope") == "main > match:merge")
    assert merge_summary["reason"] == "exhaustive-match-merge"


def test_analyze_stackvm_ast_catches_unknown_dict_key_via_path():
    source = '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-apply "value.scroe" get-in?'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-dict-key" and "scroe" in diag["message"] for diag in analysis["diagnostics"])


def test_analyze_stackvm_ast_reports_enum_metadata_in_stack_shape():
    source = (
        '"{status: open}" yaml> '
        '"{type: object, properties: {status: {type: string, enum: [open, closed]}}}" yaml> '
        'schema-apply "value.status" get-in?'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    # Variants are sorted alphabetically for stability: closed|open
    assert analysis["final_stack_shape"] == ["str{closed|open}"]


def test_analyze_stackvm_ast_reports_dict_keys_in_stack_shape():
    source = (
        '"{count: 7}" yaml> '
        '"{type: object, properties: {count: {type: integer}}}" yaml> '
        'schema-apply'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    # Keys are sorted alphabetically: errors, success, value
    assert analysis["final_stack_shape"] == ["dict{errors:list,success:bool,value:dict}"]


def test_analyze_stackvm_ast_validates_project_fields_paths():
    # Verifies that project-fields macro usage flags typos in the source paths.
    source = (
        '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-apply '
        '[ "value.scroe" "shared.count" 0 ] [ ] project-fields'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-dict-key" and "scroe" in diag["message"] for diag in analysis["diagnostics"])


def test_analyze_stackvm_ast_tracks_handoff_rules_effects():
    source = (
        '[ [ "total" shared@ 10 >= ] "high" "router.high" [ True ] "low" "router.low" ] '
        '"normalized.band" '
        'handoff-rules'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "handoff" in analysis["effect_kinds"]
    assert "state" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_handoff_switch_effects():
    source = (
        '[ "route" shared@ ] '
        '[ "approve" "router.approve" "default" "router.review" ] '
        'handoff-switch'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "handoff" in analysis["effect_kinds"]
    # Exhaustive switch should leave min depth 0 if branches don't push anything
    # value_expr pushes 1, switch pops 1.
    assert analysis["final_min_stack_depth"] == 0


def test_analyze_stackvm_ast_validates_validated_match_keys():
    # Correct key 'count' should pass
    source_ok = (
        '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-apply '
        '[ ] [ [ "{count: $c}" yaml> ] [ ] ] [ ] validated-match'
    )
    analysis_ok = analyze_stackvm_ast(parse_stackvm_source(source_ok), source=source_ok)
    assert not any(diag["code"] == "unknown-dict-key" for diag in analysis_ok["diagnostics"])

    # Incorrect key 'scroe' should trigger diagnostic
    source_bad = (
        '"{count: 7}" yaml> "{type: object, properties: {count: {type: integer}}}" yaml> schema-apply '
        '[ ] [ [ "{scroe: $c}" yaml> ] [ ] ] [ ] validated-match'
    )
    analysis_bad = analyze_stackvm_ast(parse_stackvm_source(source_bad), source=source_bad)
    assert any(diag["code"] == "unknown-dict-key" and "scroe" in diag["message"] for diag in analysis_bad["diagnostics"])


def test_analyze_stackvm_ast_validates_schema_route_keys():
    # Incorrect key 'ststus' should trigger diagnostic
    source_bad = (
        '"{status: open}" yaml> "{type: object, properties: {status: {type: string}}}" yaml> schema-apply '
        '"errors" None [ [ "{ststus: open}" yaml> ] [ ] ] [ ] schema-route'
    )
    analysis_bad = analyze_stackvm_ast(parse_stackvm_source(source_bad), source=source_bad)
    assert any(diag["code"] == "unknown-dict-key" and "ststus" in diag["message"] for diag in analysis_bad["diagnostics"])


def test_analyze_stackvm_ast_tracks_prompt_route_effects():
    source = (
        '[ "{kind: buttons, prompt: Choose, options: [{id: ok, label: OK, value: ok}]}" yaml> ] '
        '[ "ok" [ "approved" answer ] "default" [ "rejected" answer ] ] '
        'prompt-route'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "prompt" in analysis["effect_kinds"]
    assert "final" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_prompt_store_effects():
    source = (
        '[ "Proceed?" ] '
        '"normalized.reply" '
        '[ "Reply: " swap concat answer ] '
        'prompt-store'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "prompt" in analysis["effect_kinds"]
    assert "state" in analysis["effect_kinds"]
    assert "final" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_stdlib_io_read_yaml_effects():
    source = (
        '"config.yaml" '
        '[ last-tool-result failure? [ "bad" answer ] [ "ok" answer ] if ] '
        'stdlib.io.read-yaml-file-once'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "tool" in analysis["effect_kinds"]
    assert "final" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_workflow_builder_and_usage_effects():
    # define-choice-answer-family takes 13 args
    source = (
        '"f" "p.yaml" "target" [ "missing" answer ] [ "val" ] '
        '"buttons" "Ask " "choice" [ "ok" "OK" "ok" ] [ ] "exact" [ ] [ "ok" [ "done" ] ] '
        'define-choice-answer-family '
        '"f" "caller" "answer" use-workflow-family'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "prompt" in analysis["effect_kinds"]
    assert "handoff" in analysis["effect_kinds"]
    assert "final" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_record_fields_output():
    source = (
        '[ "{}" yaml> ] [ "key" "value" ] record-fields'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    # record-fields leaves a dict on stack
    assert analysis["final_stack_shape"] == ["dict"]


def test_analyze_stackvm_ast_validates_nested_match_keys():
    # Schema with nested properties
    source = (
        '"{meta: {status: open}}" yaml> '
        '"{type: object, properties: {meta: {type: object, properties: {status: {type: string}}}}}" yaml> '
        'schema-apply [ ] '
        '[ [ "{meta: {ststus: $s}}" yaml> ] [ ] ] [ ] validated-match'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-dict-key" and "ststus" in diag["message"] for diag in analysis["diagnostics"])


def test_analyze_stackvm_ast_catches_unknown_nested_dict_key_via_path():
    source = (
        '"{meta: {status: open}}" yaml> '
        '"{type: object, properties: {meta: {type: object, properties: {status: {type: string}}}}}" yaml> '
        'schema-apply "value.meta.ststus" get-in?'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-dict-key" and "ststus" in diag["message"] for diag in analysis["diagnostics"])


def test_analyze_stackvm_ast_tracks_return_answer_flow_effects():
    source = (
        '"p.yaml" [ "payload" store-set ] "target" [ "missing" answer ] [ "done" ] '
        'return-answer-flow'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "tool" in analysis["effect_kinds"]
    assert "handoff" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_validates_workflow_spec_keys():
    source = '"my-spec" [ "unknown_key" 1 ] define-workflow-spec'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-workflow-key" and "unknown_key" in diag["message"] for diag in analysis["diagnostics"])


def test_analyze_stackvm_ast_validates_workflow_family_sections():
    source = '"my-family" [ "bad.section" [ ] ] define-workflow-family'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert any(diag["code"] == "unknown-workflow-key" and "bad.section" in diag["message"] for diag in analysis["diagnostics"])
    assert "final" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_return_field_route_flow_effects():
    source = (
        '"p.yaml" [ "p" store-set ] "target" [ "m" answer ] '
        '[ "r" "nr" None ] [ "nr" shared@ ] [ "ok" "r.ok" ] '
        'return-field-route-flow'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "tool" in analysis["effect_kinds"]
    assert "handoff" in analysis["effect_kinds"]
    assert "state" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_return_flow_effects():
    source = '"p.yaml" [ "load" ] "target" [ "resume" ] return-flow'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "tool" in analysis["effect_kinds"]
    assert "handoff" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_ask_from_effects():
    source = '[ "Proceed?" ] ask-from'
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "prompt" in analysis["effect_kinds"]


def test_analyze_stackvm_ast_tracks_prompt_store_text_effects():
    source = (
        '[ "Review summary?" ] "reply" [ "User said: " swap concat answer ] '
        'prompt-store-text'
    )
    analysis = analyze_stackvm_ast(parse_stackvm_source(source), source=source)
    assert analysis["diagnostic_count"] == 0
    assert "prompt" in analysis["effect_kinds"]
    assert "state" in analysis["effect_kinds"]
    assert "final" in analysis["effect_kinds"]
