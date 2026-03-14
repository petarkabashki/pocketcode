from __future__ import annotations

from pocketcode.core.runtime_effects import (
    ask_user_effect,
    call_tool_effect,
    final_answer_effect,
    handoff_effect,
    serialize_runtime_effect,
    transition_effect,
    transition_from_runtime_effect,
)


def test_transition_from_runtime_effect_maps_canonical_effect_kinds():
    assert transition_from_runtime_effect(final_answer_effect("done")) == "final_answer"
    assert transition_from_runtime_effect(ask_user_effect("Proceed?")) == "ask_user"
    assert transition_from_runtime_effect(handoff_effect("delegate.agent")) == "handoff"
    assert (
        transition_from_runtime_effect(
            call_tool_effect(tool_name="core.echo", arguments={"text": "ping"}, requested_by="agent")
        )
        == "call_tool"
    )


def test_transition_from_runtime_effect_maps_transition_payload_name():
    assert transition_from_runtime_effect(transition_effect("retry")) == "retry"
    assert transition_from_runtime_effect(transition_effect("")) == "continue"


def test_serialize_runtime_effect_normalizes_dict_payloads():
    effect = serialize_runtime_effect({"kind": "handoff", "payload": {"target_agent": "delegate.agent"}})

    assert effect == {
        "kind": "handoff",
        "payload": {"target_agent": "delegate.agent"},
    }


def test_transition_from_runtime_effect_accepts_serialized_runtime_effect():
    effect = serialize_runtime_effect(final_answer_effect("done"))

    assert transition_from_runtime_effect(effect) == "final_answer"
