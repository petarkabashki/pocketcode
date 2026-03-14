from pocketcode.core.stackvm_expander import expand_stackvm_source
from tests.integration.stackvm_test_utils import (
    EXAMPLES_ROOT,
    load_example_asset_vm_source,
    make_example_engine,
    request_context,
    wait_for_new_interaction_request,
    write_fixture,
)


def test_real_engine_start_request_can_finalize_after_structured_delegate_return_concise(tmp_path):
    write_fixture(
        tmp_path,
        "structured_finalize_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_structured_return_finalize_example.normalize")

    handle = engine.start_request(
        "finalize from structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert prompt_event["kind"] == "radio"
    assert prompt_event["prompt"] == "Choose finalization mode for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["concise", "detailed", "blocked"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "concise",
            "values": ["concise"],
            "selected_options": [{"id": "concise", "label": "Concise", "value": "concise"}],
            "raw_input": "concise",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "finalized: Alpha, Beta, untitled from fixture | mode=concise | note=concise summary requested"
    assert engine.last_run_summary["current_agent"] == "stackvm_structured_return_finalize_example.normalize"
    router_source = load_example_asset_vm_source("stackvm_structured_return_finalize_example", "normalize.md")
    delegate_source = load_example_asset_vm_source(
        "stackvm_structured_return_finalize_example",
        "confirm_delegate.md",
    )
    assert expand_stackvm_source(router_source).expansion_trace == [
        "tool-once",
        "stdlib.io.read-file-once",
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
        "stdlib.io.read-yaml-file-once",
    ]
    assert expand_stackvm_source(delegate_source).expansion_trace == [
        "define-choice-finalize-family",
        "use-workflow-family",
        "workflow-spec",
        "finalize-workflow-contract",
        "delegate-structured-workflow",
        "summary-structured-workflow",
        "summary-choice-flow",
        "choice-flow",
        "choice-contract",
        "choice-structured-decision",
        "record-fields",
        "record-fields",
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")
    assert event_types[-1] == "run_completed"


def test_real_engine_start_request_can_finalize_after_structured_delegate_return_blocked(tmp_path):
    write_fixture(
        tmp_path,
        "structured_finalize_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_structured_return_finalize_example.normalize")

    handle = engine.start_request(
        "finalize from structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "blocked",
            "values": ["blocked"],
            "selected_options": [{"id": "blocked", "label": "Blocked", "value": "blocked"}],
            "raw_input": "blocked",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "finalized: Alpha, Beta, untitled from fixture | mode=blocked | note=blocked by delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_structured_return_finalize_example.normalize"


def test_real_engine_start_request_can_route_after_structured_delegate_return_approve(tmp_path):
    write_fixture(
        tmp_path,
        "structured_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_structured_return_routing_example.normalize")

    handle = engine.start_request(
        "route from structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert prompt_event["kind"] == "radio"
    assert prompt_event["prompt"] == "Choose final route for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["approve", "escalate", "review"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "approve",
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "approved route handled: Alpha, Beta, untitled from fixture (approved by delegate)"
    assert engine.last_run_summary["current_agent"] == "stackvm_structured_return_routing_example.approve_route"
    router_source = load_example_asset_vm_source("stackvm_structured_return_routing_example", "normalize.md")
    delegate_source = load_example_asset_vm_source(
        "stackvm_structured_return_routing_example",
        "confirm_delegate.md",
    )
    assert expand_stackvm_source(router_source).expansion_trace == [
        "tool-once",
        "stdlib.io.read-file-once",
        "define-choice-route-family",
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
        "stdlib.io.read-yaml-file-once",
    ]
    assert expand_stackvm_source(delegate_source).expansion_trace == [
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
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")


def test_real_engine_start_request_can_route_after_structured_delegate_return_escalate(tmp_path):
    write_fixture(
        tmp_path,
        "structured_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_structured_return_routing_example.normalize")

    handle = engine.start_request(
        "route from structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "escalate",
            "values": ["escalate"],
            "selected_options": [{"id": "escalate", "label": "Escalate", "value": "escalate"}],
            "raw_input": "escalate",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "escalated route handled: Alpha, Beta, untitled from fixture (escalated by delegate)"
    assert engine.last_run_summary["current_agent"] == "stackvm_structured_return_routing_example.escalate_route"


def test_real_engine_start_request_can_finalize_after_nested_structured_delegate_return_concise(tmp_path):
    write_fixture(
        tmp_path,
        "nested_structured_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_structured_return_example.normalize")

    handle = engine.start_request(
        "finalize from nested structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert prompt_event["kind"] == "radio"
    assert prompt_event["prompt"] == "Choose nested mode for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["concise", "blocked"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "concise",
            "values": ["concise"],
            "selected_options": [{"id": "concise", "label": "Concise", "value": "concise"}],
            "raw_input": "concise",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "nested finalized: Alpha, Beta, untitled from fixture | mode=concise | note=concise summary requested | delegate_source=delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_structured_return_example.normalize"
    router_source = load_example_asset_vm_source("stackvm_nested_structured_return_example", "normalize.md")
    delegate_source = load_example_asset_vm_source(
        "stackvm_nested_structured_return_example",
        "confirm_delegate.md",
    )
    assert expand_stackvm_source(router_source).expansion_trace == [
        "tool-once",
        "stdlib.io.read-file-once",
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
        "stdlib.io.read-yaml-file-once",
    ]
    assert expand_stackvm_source(delegate_source).expansion_trace == [
        "define-choice-finalize-family",
        "use-workflow-family",
        "workflow-spec",
        "finalize-workflow-contract",
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


def test_real_engine_start_request_can_finalize_after_nested_structured_delegate_return_with_default_note(tmp_path):
    write_fixture(
        tmp_path,
        "nested_structured_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_structured_return_example.normalize")

    handle = engine.start_request(
        "finalize from nested structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "blocked",
            "values": ["blocked"],
            "selected_options": [{"id": "blocked", "label": "Blocked", "value": "blocked"}],
            "raw_input": "blocked",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "nested finalized: Alpha, Beta, untitled from fixture | mode=blocked | note=no note | delegate_source=delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_structured_return_example.normalize"


def test_real_engine_start_request_can_route_after_nested_structured_delegate_return_approve(tmp_path):
    write_fixture(
        tmp_path,
        "nested_structured_return_routing_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_structured_return_routing_example.normalize")

    handle = engine.start_request(
        "route from nested structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert prompt_event["kind"] == "radio"
    assert prompt_event["prompt"] == "Choose nested route for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["approve", "escalate", "review"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "approve",
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "approved nested route handled: Alpha, Beta, untitled from fixture | note=approved by delegate | delegate_source=delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_structured_return_routing_example.approve_route"
    router_source = load_example_asset_vm_source(
        "stackvm_nested_structured_return_routing_example",
        "normalize.md",
    )
    delegate_source = load_example_asset_vm_source(
        "stackvm_nested_structured_return_routing_example",
        "confirm_delegate.md",
    )
    assert expand_stackvm_source(router_source).expansion_trace == [
        "tool-once",
        "stdlib.io.read-file-once",
        "define-choice-route-family",
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
        "stdlib.io.read-yaml-file-once",
    ]
    assert expand_stackvm_source(delegate_source).expansion_trace == [
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
        "record-fields",
        "choice-decision",
        "choice-request",
        "prompt-decision",
        "prompt-return-yaml-policy",
    ]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")


def test_real_engine_start_request_can_route_after_nested_structured_delegate_return_with_default_note(tmp_path):
    write_fixture(
        tmp_path,
        "nested_structured_return_routing_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_nested_structured_return_routing_example.normalize")

    handle = engine.start_request(
        "route from nested structured delegate return",
        request_context(),
        bridge_user_input=True,
    )

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert prompt_event is not None
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "review",
            "values": ["review"],
            "selected_options": [{"id": "review", "label": "Review", "value": "review"}],
            "raw_input": "review",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "review nested route handled: Alpha, Beta, untitled from fixture | note=no note | delegate_source=delegate"
    assert engine.last_run_summary["current_agent"] == "stackvm_nested_structured_return_routing_example.review_route"
