from pocketcode.core.stackvm_expander import expand_stackvm_source
from tests.integration.stackvm_test_utils import (
    EXAMPLES_ROOT,
    make_example_engine,
    write_fixture,
    write_temp_stackvm_plugin,
)


def test_real_engine_runs_checked_in_stackvm_handoff_example(tmp_path):
    engine = make_example_engine(tmp_path, "stackvm_handoff_example.router")

    result = engine.process_request("route this", {})

    assert result == "delegate handled: route this"
    assert engine.last_run_summary["current_agent"] == "stackvm_handoff_example.delegate"


def test_real_engine_runs_checked_in_stackvm_review_example(tmp_path):
    (tmp_path / "readme.md").write_text("review content from workspace\n", encoding="utf-8")
    engine = make_example_engine(tmp_path, "stackvm_example.review")

    result = engine.process_request("review this", {})

    assert result == "review content from workspace\n"
    assert engine.last_run_summary["current_agent"] == "stackvm_example.review"


def test_real_engine_runs_checked_in_stackvm_resilient_example(tmp_path):
    engine = make_example_engine(tmp_path, "stackvm_resilient_example.router")

    result = engine.process_request("recover this", {})

    assert result == "fallback handled tool failure: Failed to read file 'definitely_missing.md'."
    assert engine.last_run_summary["current_agent"] == "stackvm_resilient_example.fallback"


def test_real_engine_runs_checked_in_stackvm_config_router_example(tmp_path):
    write_fixture(
        tmp_path,
        "route_config.yaml",
        [
            'enabled: "yes"',
            'target_index: "0"',
            'routes:',
            '  - stackvm_config_router_example.delegate',
            '  - stackvm_config_router_example.fallback',
            'message: "config-selected delegate"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_config_router_example.router")

    result = engine.process_request("route from config", {})

    assert result == "config delegate handled: config-selected delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_config_router_example.delegate"


def test_real_engine_runs_checked_in_stackvm_config_router_example_disabled_branch(tmp_path):
    write_fixture(
        tmp_path,
        "route_config.yaml",
        [
            'enabled: "no"',
            'target_index: "0"',
            'routes:',
            '  - stackvm_config_router_example.delegate',
            '  - stackvm_config_router_example.fallback',
            'message: "config-selected delegate"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_config_router_example.router")

    result = engine.process_request("route from disabled config", {})

    assert result == "config fallback handled: disabled"
    assert engine.last_run_summary["current_agent"] == "stackvm_config_router_example.fallback"


def test_real_engine_runs_checked_in_stackvm_config_router_example_missing_config(tmp_path):
    engine = make_example_engine(tmp_path, "stackvm_config_router_example.router")

    result = engine.process_request("route with missing config", {})

    assert result == "config fallback handled: tool_failure"
    assert engine.last_run_summary["current_agent"] == "stackvm_config_router_example.fallback"


def test_real_engine_runs_checked_in_stackvm_config_router_example_missing_route_target(tmp_path):
    write_fixture(
        tmp_path,
        "route_config.yaml",
        [
            'enabled: "yes"',
            'target_index: "5"',
            'routes:',
            '  - stackvm_config_router_example.delegate',
            'message: "config-selected delegate"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_config_router_example.router")

    result = engine.process_request("route with missing target", {})

    assert result == "config fallback handled: missing_route"
    assert engine.last_run_summary["current_agent"] == "stackvm_config_router_example.fallback"


def test_real_engine_runs_checked_in_stackvm_nested_router_example(tmp_path):
    write_fixture(
        tmp_path,
        "nested_route_config.yaml",
        [
            'routing:',
            '  enabled: "yes"',
            '  selected:',
            '    index: "0"',
            '  targets:',
            '    - agent: stackvm_nested_router_example.delegate',
            '      message: "nested delegate selected"',
            '    - agent: stackvm_nested_router_example.fallback',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_router_example.router")

    result = engine.process_request("route through nested config", {})

    assert result == "nested delegate handled: nested delegate selected"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_router_example.delegate"


def test_real_engine_runs_checked_in_stackvm_nested_router_example_missing_target(tmp_path):
    write_fixture(
        tmp_path,
        "nested_route_config.yaml",
        [
            'routing:',
            '  enabled: "yes"',
            '  selected:',
            '    index: "4"',
            '  targets:',
            '    - agent: stackvm_nested_router_example.delegate',
            '      message: "nested delegate selected"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_router_example.router")

    result = engine.process_request("route through nested config", {})

    assert result == "nested fallback handled: missing_target"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_router_example.fallback"


def test_real_engine_runs_checked_in_stackvm_tool_normalize_example(tmp_path):
    write_fixture(
        tmp_path,
        "tool_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '    enabled: "yes"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_tool_normalize_example.normalize")

    result = engine.process_request("normalize tool payload", {})

    assert result == "Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_tool_normalize_example.normalize"
    router_source = (EXAMPLES_ROOT / "stackvm_tool_normalize_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["tool-once"]


def test_real_engine_runs_checked_in_stackvm_tool_normalize_example_disabled_payload(tmp_path):
    write_fixture(
        tmp_path,
        "tool_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '    enabled: "no"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_tool_normalize_example.normalize")

    result = engine.process_request("normalize disabled tool payload", {})

    assert result == "disabled: Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_tool_normalize_example.normalize"


def test_real_engine_runs_checked_in_stackvm_macro_authoring_example(tmp_path):
    write_fixture(
        tmp_path,
        "macro_payload.yaml",
        [
            'message: "from macro example"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_macro_authoring_example.normalize")

    result = engine.process_request("run macro authoring example", {})

    assert result == "Macro says: from macro example"
    assert engine.last_run_summary["current_agent"] == "stackvm_macro_authoring_example.normalize"
    router_source = (EXAMPLES_ROOT / "stackvm_macro_authoring_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["tool-once", "answer-from", "read-file-once"]


def test_real_engine_runs_checked_in_stackvm_parallel_map_example(tmp_path):
    engine = make_example_engine(tmp_path, "stackvm_parallel_map_example.map")

    result = engine.process_request("map these items", {})

    assert result == "parallel results: item=alpha, item=beta, item=gamma"
    assert engine.last_run_summary["current_agent"] == "stackvm_parallel_map_example.map"


def test_real_engine_runs_checked_in_stackvm_parallel_tool_map_example(tmp_path):
    write_fixture(
        tmp_path,
        "parallel_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_parallel_tool_map_example.map")

    result = engine.process_request("map payload items", {})

    assert result == "parallel map from tool: item=Alpha, item=Beta, item=untitled"
    assert engine.last_run_summary["current_agent"] == "stackvm_parallel_tool_map_example.map"


def test_real_engine_runs_checked_in_stackvm_reduce_example(tmp_path):
    engine = make_example_engine(tmp_path, "stackvm_reduce_example.summarize")

    result = engine.process_request("summarize mapped items", {})

    assert result == "reduced summary: item=alpha; item=beta; item=gamma"
    assert engine.last_run_summary["current_agent"] == "stackvm_reduce_example.summarize"


def test_real_engine_runs_checked_in_stackvm_reduce_tool_example(tmp_path):
    write_fixture(
        tmp_path,
        "reduce_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - {}',
            '  - title: "Gamma"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_reduce_tool_example.summarize")

    result = engine.process_request("summarize payload items", {})

    assert result == "reduced tool summary: item=Alpha; item=untitled; item=Gamma"
    assert engine.last_run_summary["current_agent"] == "stackvm_reduce_tool_example.summarize"


def test_real_engine_runs_checked_in_stackvm_reduce_numeric_example(tmp_path):
    write_fixture(
        tmp_path,
        "reduce_numeric_payload.yaml",
        [
            "items:",
            '  - score: "3"',
            '  - score: "7"',
            '  - {}',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_reduce_numeric_example.summarize")

    result = engine.process_request("aggregate numeric values", {})

    assert result == "numeric total: 10"
    assert engine.last_run_summary["current_agent"] == "stackvm_reduce_numeric_example.summarize"


def test_real_engine_runs_checked_in_stackvm_threshold_router_example_low(tmp_path):
    write_fixture(
        tmp_path,
        "threshold_payload.yaml",
        [
            "items:",
            '  - score: "1"',
            '  - score: "2"',
            '  - {}',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_threshold_router_example.router")

    result = engine.process_request("route low aggregate", {})

    assert result == "low route handled total: 3"
    assert engine.last_run_summary["current_agent"] == "stackvm_threshold_router_example.low_route"


def test_real_engine_runs_checked_in_stackvm_threshold_router_example_review(tmp_path):
    write_fixture(
        tmp_path,
        "threshold_payload.yaml",
        [
            "items:",
            '  - score: "2"',
            '  - score: "3"',
            '  - {}',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_threshold_router_example.router")

    result = engine.process_request("route review aggregate", {})

    assert result == "review route handled total: 5"
    assert engine.last_run_summary["current_agent"] == "stackvm_threshold_router_example.review_route"


def test_real_engine_runs_checked_in_stackvm_threshold_router_example_high(tmp_path):
    write_fixture(
        tmp_path,
        "threshold_payload.yaml",
        [
            "items:",
            '  - score: "4"',
            '  - score: "6"',
            '  - score: "1"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_threshold_router_example.router")

    result = engine.process_request("route high aggregate", {})

    assert result == "high route handled total: 11"
    assert engine.last_run_summary["current_agent"] == "stackvm_threshold_router_example.high_route"


def test_real_engine_rejects_transition_words_inside_parallel_map(tmp_path):
    plugin_root, flow_ref = write_temp_stackvm_plugin(
        tmp_path,
        plugin_dir_name="stackvm_parallel_map_invalid_plugin",
        plugin_name="stackvm_parallel_map_invalid_example",
        plugin_description="Invalid parallel-map runtime transition example",
        flow_name="bad",
        flow_description="Invalid parallel-map flow that tries to finalize inside a child quotation",
        flow_body_lines=[
            "Attempt an illegal runtime transition from inside a parallel-map child quotation.",
        ],
        vm_lines=[
            "[",
            '  "[alpha]" yaml>',
            '  [ "illegal child answer" answer ]',
            "  parallel-map",
            '] "decide" define',
        ],
    )
    engine = make_example_engine(
        tmp_path,
        flow_ref,
        workspace_paths=[plugin_root.parent],
    )

    result = engine.process_request("run invalid map", {})

    assert result == (
        "Error: VM execution failed: parallel-map child quotations cannot finalize answers."
    )
    assert engine.last_run_summary["current_agent"] == flow_ref


def test_real_engine_rejects_transition_words_inside_reduce(tmp_path):
    plugin_root, flow_ref = write_temp_stackvm_plugin(
        tmp_path,
        plugin_dir_name="stackvm_reduce_invalid_plugin",
        plugin_name="stackvm_reduce_invalid_example",
        plugin_description="Invalid reduce runtime transition example",
        flow_name="bad",
        flow_description="Invalid reduce flow that tries to finalize inside a child quotation",
        flow_body_lines=[
            "Attempt an illegal runtime transition from inside a reduce child quotation.",
        ],
        vm_lines=[
            "[",
            '  "[alpha]" yaml>',
            '  "seed"',
            '  [ "illegal child answer" answer ]',
            "  reduce",
            '] "decide" define',
        ],
    )
    engine = make_example_engine(
        tmp_path,
        flow_ref,
        workspace_paths=[plugin_root.parent],
    )

    result = engine.process_request("run invalid reduce", {})

    assert result == (
        "Error: VM execution failed: reduce child quotations cannot finalize answers."
    )
    assert engine.last_run_summary["current_agent"] == flow_ref


def test_real_engine_runs_checked_in_stackvm_normalize_handoff_example_enabled(tmp_path):
    write_fixture(
        tmp_path,
        "handoff_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '    enabled: "yes"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_normalize_handoff_example.normalize")

    result = engine.process_request("normalize and handoff", {})

    assert result == "enabled delegate handled: Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_normalize_handoff_example.enabled_delegate"


def test_real_engine_runs_checked_in_stackvm_normalize_handoff_example_disabled(tmp_path):
    write_fixture(
        tmp_path,
        "handoff_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '    enabled: "no"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_normalize_handoff_example.normalize")

    result = engine.process_request("normalize and handoff", {})

    assert result == "disabled delegate handled: Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_normalize_handoff_example.disabled_delegate"


def test_real_engine_runs_checked_in_stackvm_normalize_ask_example(tmp_path):
    write_fixture(
        tmp_path,
        "ask_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '    enabled: "yes"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_normalize_ask_example.normalize")

    result = engine.process_request("normalize and ask", {})

    assert result == "Question: Proceed with Alpha, Beta, untitled from fixture?"
    assert engine.last_run_summary["current_agent"] == "stackvm_normalize_ask_example.normalize"
