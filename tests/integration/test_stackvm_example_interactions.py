import time

from pocketcode.core.stackvm_expander import expand_stackvm_source
from tests.integration.stackvm_test_utils import (
    EXAMPLES_ROOT,
    make_example_engine,
    request_context,
    wait_for_new_interaction_request,
    write_fixture,
)


def test_real_engine_start_request_can_bridge_stackvm_normalize_ask_example(tmp_path):
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

    handle = engine.start_request("normalize and ask", request_context(), bridge_user_input=True)

    prompt_event = None
    events = []
    for _ in range(40):
        batch = handle.drain_events()
        events.extend(batch)
        prompt_event = next((event for event in events if event["type"] == "interaction_requested"), None)
        if prompt_event is not None:
            break
        time.sleep(0.01)

    assert prompt_event is None
    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "Question: Proceed with Alpha, Beta, untitled from fixture?"
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"


def test_real_engine_start_request_can_continue_after_stackvm_prompt_user(tmp_path):
    write_fixture(
        tmp_path,
        "confirm_payload.yaml",
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
    engine = make_example_engine(tmp_path, "stackvm_normalize_confirm_example.normalize")

    handle = engine.start_request("normalize and confirm", request_context(), bridge_user_input=True)

    prompt_event = None
    events = []
    for _ in range(40):
        batch = handle.drain_events()
        events.extend(batch)
        prompt_event = next((event for event in events if event["type"] == "interaction_requested"), None)
        if prompt_event is not None:
            break
        time.sleep(0.01)

    assert prompt_event is not None
    assert prompt_event["prompt"] == "Proceed with Alpha, Beta, untitled from fixture?"
    assert handle.resolve_interaction(str(prompt_event["request_id"]), {"value": "yes", "raw_input": "yes"}) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "Confirmed Alpha, Beta, untitled from fixture"
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_started"
    assert event_types[-1] == "run_completed"
    assert event_types.count("interaction_requested") == 1
    assert event_types.count("interaction_received") == 1
    assert event_types.count("agent_turn_started") == 2
    assert event_types.count("agent_turn_completed") == 2
    assert event_types.index("tool_started") < event_types.index("tool_finished")
    assert event_types.index("tool_finished") < event_types.index("interaction_requested")
    assert event_types.index("interaction_requested") < event_types.index("interaction_received")


def test_real_engine_start_request_can_continue_after_stackvm_prompt_user_decline(tmp_path):
    write_fixture(
        tmp_path,
        "confirm_payload.yaml",
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
    engine = make_example_engine(tmp_path, "stackvm_normalize_confirm_example.normalize")

    handle = engine.start_request("normalize and confirm", request_context(), bridge_user_input=True)

    prompt_event = None
    events = []
    for _ in range(40):
        batch = handle.drain_events()
        events.extend(batch)
        prompt_event = next((event for event in events if event["type"] == "interaction_requested"), None)
        if prompt_event is not None:
            break
        time.sleep(0.01)

    assert prompt_event is not None
    assert handle.resolve_interaction(str(prompt_event["request_id"]), {"value": "no", "raw_input": "no"}) is True

    result = handle.wait(timeout=1.0)

    assert result == "Declined Alpha, Beta, untitled from fixture"


def test_real_engine_start_request_can_continue_after_stackvm_button_interaction(tmp_path):
    write_fixture(
        tmp_path,
        "buttons_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            "meta:",
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_buttons_example.normalize")

    handle = engine.start_request("normalize and choose", request_context(), bridge_user_input=True)

    prompt_event = None
    events = []
    for _ in range(40):
        batch = handle.drain_events()
        events.extend(batch)
        prompt_event = next((event for event in events if event["type"] == "interaction_requested"), None)
        if prompt_event is not None:
            break
        time.sleep(0.01)

    assert prompt_event is not None
    assert prompt_event["kind"] == "buttons"
    assert prompt_event["prompt"] == "Choose next step for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["approve", "delegate", "deny"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "buttons",
            "value": "delegate",
            "values": ["delegate"],
            "selected_options": [{"id": "delegate", "label": "Delegate", "value": "delegate"}],
            "raw_input": "delegate",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    assert result == "Delegating Alpha, Beta, untitled from fixture"
    router_source = (EXAMPLES_ROOT / "stackvm_buttons_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["prompt-route", "tool-once"]


def test_real_engine_start_request_can_return_from_prompted_stackvm_delegate(tmp_path):
    write_fixture(
        tmp_path,
        "prompt_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_prompt_return_example.normalize")

    handle = engine.start_request("normalize and delegate", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert prompt_event["kind"] == "buttons"
    assert prompt_event["prompt"] == "Choose delegate action for Alpha, Beta, untitled from fixture"
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "buttons",
            "value": "approve",
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "Caller received delegate decision: delegate approved Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_prompt_return_example.normalize"
    router_source = (EXAMPLES_ROOT / "stackvm_prompt_return_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["tool-once", "finalize-from"]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")


def test_real_engine_start_request_can_pass_through_stackvm_delegate_return(tmp_path):
    write_fixture(
        tmp_path,
        "delegate_return_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_delegate_return_example.normalize")

    handle = engine.start_request("normalize and pass through delegate answer", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert prompt_event["kind"] == "buttons"
    assert prompt_event["prompt"] == "Choose delegate action for Alpha, Beta, untitled from fixture"
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "buttons",
            "value": "approve",
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "delegate approved Alpha, Beta, untitled from fixture"
    assert engine.last_run_summary["current_agent"] == "stackvm_delegate_return_example.normalize"
    router_source = (EXAMPLES_ROOT / "stackvm_delegate_return_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["delegate-return", "tool-once"]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")


def test_real_engine_start_request_can_return_from_checklist_stackvm_delegate(tmp_path):
    write_fixture(
        tmp_path,
        "checklist_return_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            "meta:",
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_checklist_return_example.normalize")

    handle = engine.start_request("normalize and choose tools", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert prompt_event["kind"] == "checklist"
    assert prompt_event["prompt"] == "Pick tools for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["git", "search", "context"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "checklist",
            "value": ["git", "search"],
            "values": ["git", "search"],
            "selected_options": [
                {"id": "git", "label": "Git", "value": "git"},
                {"id": "search", "label": "Search", "value": "search"},
            ],
            "raw_input": "git,search",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "Caller received delegate tools: delegate picked git, search for Alpha, Beta, untitled from fixture"
    router_source = (EXAMPLES_ROOT / "stackvm_checklist_return_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["tool-once", "finalize-from"]
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    assert event_types.index("handoff") < event_types.index("interaction_requested")
    assert event_types.index("interaction_received") < event_types.index("handoff_return")


def test_real_engine_start_request_can_continue_after_stackvm_radio_interaction(tmp_path):
    write_fixture(
        tmp_path,
        "radio_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            "meta:",
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_radio_example.normalize")

    handle = engine.start_request("normalize and choose mode", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert prompt_event["kind"] == "radio"
    assert prompt_event["prompt"] == "Choose mode for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["delegate", "approve", "deny"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "radio",
            "value": "delegate",
            "values": ["delegate"],
            "selected_options": [{"id": "delegate", "label": "Delegate", "value": "delegate"}],
            "raw_input": "delegate",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    assert result == "Selected mode delegate for Alpha, Beta, untitled from fixture"
    router_source = (EXAMPLES_ROOT / "stackvm_radio_example" / "vm" / "router.vm").read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["tool-once"]


def test_real_engine_start_request_can_route_after_stackvm_checklist_interaction_delegate(tmp_path):
    write_fixture(
        tmp_path,
        "checklist_handoff_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            "meta:",
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_checklist_handoff_example.normalize")

    handle = engine.start_request("normalize and route", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert prompt_event["kind"] == "checklist"
    assert prompt_event["prompt"] == "Choose actions for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in prompt_event["options"]] == ["approve", "delegate", "review"]
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "checklist",
            "value": ["delegate", "review"],
            "values": ["delegate", "review"],
            "selected_options": [
                {"id": "delegate", "label": "Delegate", "value": "delegate"},
                {"id": "review", "label": "Review", "value": "review"},
            ],
            "raw_input": "delegate,review",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "delegate route handled: Alpha, Beta, untitled from fixture with actions delegate, review"
    assert engine.last_run_summary["current_agent"] == "stackvm_checklist_handoff_example.delegate_route"
    event_types = [event["type"] for event in events]
    assert "handoff" in event_types
    assert event_types.index("interaction_received") < event_types.index("handoff")


def test_real_engine_start_request_can_route_after_stackvm_checklist_interaction_approve(tmp_path):
    write_fixture(
        tmp_path,
        "checklist_handoff_payload.yaml",
        [
            "items:",
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            "meta:",
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_checklist_handoff_example.normalize")

    handle = engine.start_request("normalize and route", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    prompt_event = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=40)

    assert prompt_event is not None
    assert handle.resolve_interaction(
        str(prompt_event["request_id"]),
        {
            "kind": "checklist",
            "value": ["approve"],
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    result = handle.wait(timeout=1.0)

    assert result == "approve route handled: Alpha, Beta, untitled from fixture with actions approve"
    assert engine.last_run_summary["current_agent"] == "stackvm_checklist_handoff_example.approve_route"


def test_real_engine_start_request_can_run_stackvm_multistage_pipeline(tmp_path):
    write_fixture(
        tmp_path,
        "multistage_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_multistage_pipeline_example.normalize")

    handle = engine.start_request("run multistage pipeline", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    first_prompt = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)
    assert first_prompt is not None
    assert first_prompt["kind"] == "checklist"
    assert first_prompt["prompt"] == "Choose actions for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in first_prompt["options"]] == ["delegate", "review", "approve"]
    assert handle.resolve_interaction(
        str(first_prompt["request_id"]),
        {
            "kind": "checklist",
            "value": ["delegate", "review"],
            "values": ["delegate", "review"],
            "selected_options": [
                {"id": "delegate", "label": "Delegate", "value": "delegate"},
                {"id": "review", "label": "Review", "value": "review"},
            ],
            "raw_input": "delegate,review",
        },
    ) is True

    second_prompt = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)
    assert second_prompt is not None
    assert second_prompt["kind"] == "radio"
    assert second_prompt["prompt"] == "Choose delegate plan for Alpha, Beta, untitled from fixture"
    assert [option["id"] for option in second_prompt["options"]] == ["review-first", "delegate-now"]
    assert handle.resolve_interaction(
        str(second_prompt["request_id"]),
        {
            "kind": "radio",
            "value": "review-first",
            "values": ["review-first"],
            "selected_options": [{"id": "review-first", "label": "Review First", "value": "review-first"}],
            "raw_input": "review-first",
        },
    ) is True

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "pipeline complete: Alpha, Beta, untitled from fixture | actions=delegate, review | delegate=delegate plan review-first"
    assert engine.last_run_summary["current_agent"] == "stackvm_multistage_pipeline_example.normalize"
    router_source = (
        EXAMPLES_ROOT / "stackvm_multistage_pipeline_example" / "vm" / "router.vm"
    ).read_text(encoding="utf-8")
    assert expand_stackvm_source(router_source).expansion_trace == ["finalize-from", "tool-once", "finalize-from"]
    event_types = [event["type"] for event in events]
    assert event_types.count("interaction_requested") == 2
    assert event_types.count("interaction_received") == 2
    assert "handoff" in event_types
    assert "handoff_return" in event_types
    first_request_index = event_types.index("interaction_requested")
    first_received_index = event_types.index("interaction_received")
    second_request_index = event_types.index("interaction_requested", first_request_index + 1)
    second_received_index = event_types.index("interaction_received", first_received_index + 1)
    assert first_request_index < first_received_index < second_request_index < second_received_index
    assert event_types.index("handoff") < second_request_index
    assert second_received_index < event_types.index("handoff_return")


def test_real_engine_start_request_can_skip_delegate_in_stackvm_multistage_pipeline(tmp_path):
    write_fixture(
        tmp_path,
        "multistage_payload.yaml",
        [
            'items:',
            '  - title: "Alpha"',
            '  - title: "Beta"',
            '  - {}',
            'meta:',
            '  source: "fixture"',
        ],
    )
    engine = make_example_engine(tmp_path, "stackvm_multistage_pipeline_example.normalize")

    handle = engine.start_request("run multistage pipeline", request_context(), bridge_user_input=True)

    events = []
    seen_request_ids = set()
    first_prompt = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=80)

    assert first_prompt is not None
    assert first_prompt["kind"] == "checklist"
    assert handle.resolve_interaction(
        str(first_prompt["request_id"]),
        {
            "kind": "checklist",
            "value": ["approve"],
            "values": ["approve"],
            "selected_options": [{"id": "approve", "label": "Approve", "value": "approve"}],
            "raw_input": "approve",
        },
    ) is True

    second_prompt = wait_for_new_interaction_request(handle, events, seen_request_ids, attempts=20)
    assert second_prompt is None

    result = handle.wait(timeout=1.0)
    events.extend(handle.drain_events())

    assert result == "pipeline complete: Alpha, Beta, untitled from fixture | actions=approve | delegate=skipped"
    assert engine.last_run_summary["current_agent"] == "stackvm_multistage_pipeline_example.normalize"
    event_types = [event["type"] for event in events]
    assert event_types.count("interaction_requested") == 1
    assert event_types.count("interaction_received") == 1
    assert "handoff" not in event_types
    assert "handoff_return" not in event_types
