from __future__ import annotations

import time

from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunCancelledError


class _ImmediateRuntime:
    def run(self, shared_store):
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = "ready"


class _PromptRuntime:
    def run(self, shared_store):
        answer = shared_store["interaction_handler"](
            {
                "kind": "buttons",
                "prompt": "Approve tool execution?",
                "options": [
                    {"id": "yes", "label": "Yes", "value": "yes"},
                    {"id": "no", "label": "No", "value": "no"},
                ],
                "default": "no",
            }
        )
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = f"answer={answer.get('value')}"


class _EventfulRuntime:
    def run(self, shared_store):
        emit = shared_store["runtime_event_handler"]
        emit(
            "tool_started",
            agent="core::agent",
            tool="workspace::write_file",
            arguments={"path": "notes.txt", "content": "hello"},
        )
        emit(
            "handoff_return",
            source_agent="core::agent",
            target_agent="planner::agent",
            return_transition="continue",
        )
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = "ready"


class _CancellableRuntime:
    def run(self, shared_store):
        for _ in range(100):
            if shared_store["run_cancel_requested"]():
                raise RunCancelledError(shared_store["run_cancel_reason"]())
            time.sleep(0.01)
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = "late"


def _build_engine(runtime) -> PocketCodeEngine:
    engine = PocketCodeEngine.__new__(PocketCodeEngine)
    engine._runtime_config = {}
    engine.default_llm_profile = "default"
    engine.current_agent = None
    engine.global_llm_override = None
    engine.agent_llm_overrides = {}
    engine.handoff_llm_overrides = {}
    engine.config_llm_overrides = {"agents": {}, "handoffs": {}}
    engine.auto_confirm_tools = False
    engine.session_confirmation_overrides = {
        "default_policy": None,
        "tool_policies": {},
        "agent_policies": {},
    }
    engine.active_agent_profile = None
    engine.last_run_summary = {}
    engine._agent_runtime = runtime
    engine.list_agents = lambda: ["core::agent"]
    return engine


class TestEngineRunHandle:
    def test_start_request_emits_lifecycle_events_and_returns_result(self):
        engine = _build_engine(_ImmediateRuntime())

        handle = engine.start_request("hello", {"files": set(), "folders": set(), "urls": set(), "snippets": {}})
        result = handle.wait(timeout=1.0)
        events = handle.drain_events()

        assert result == "ready"
        assert [event["type"] for event in events] == ["run_started", "run_completed"]
        assert events[-1]["output"] == "ready"
        assert engine.last_run_summary["current_agent"] == "core::agent"

    def test_start_request_can_bridge_user_input_through_run_handle(self):
        engine = _build_engine(_PromptRuntime())

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            bridge_user_input=True,
        )

        prompt_event = None
        events = []
        for _ in range(20):
            batch = handle.drain_events()
            events.extend(batch)
            prompt_event = next((event for event in events if event["type"] == "interaction_requested"), None)
            if prompt_event is not None:
                break
            time.sleep(0.01)

        assert prompt_event is not None
        assert "Approve tool execution?" in prompt_event["prompt"]

        assert handle.resolve_interaction(
            str(prompt_event["request_id"]),
            {"value": "yes", "raw_input": "1"},
        ) is True
        result = handle.wait(timeout=1.0)
        events.extend(handle.drain_events())

        assert result == "answer=yes"
        assert [event["type"] for event in events] == [
            "run_started",
            "interaction_requested",
            "interaction_received",
            "run_completed",
        ]

    def test_start_request_captures_custom_runtime_events(self):
        engine = _build_engine(_EventfulRuntime())

        handle = engine.start_request("hello", {"files": set(), "folders": set(), "urls": set(), "snippets": {}})
        result = handle.wait(timeout=1.0)
        events = handle.drain_events()

        assert result == "ready"
        assert [event["type"] for event in events] == [
            "run_started",
            "tool_started",
            "handoff_return",
            "run_completed",
        ]

    def test_start_request_can_be_cancelled(self):
        engine = _build_engine(_CancellableRuntime())

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        time.sleep(0.02)

        assert handle.cancel("Stop requested from test.") is True
        assert handle.wait(timeout=1.0) == ""

        events = handle.drain_events()
        assert [event["type"] for event in events] == [
            "run_started",
            "run_cancel_requested",
            "run_cancelled",
        ]
        assert events[-1]["reason"] == "Stop requested from test."

    def test_format_runtime_event_includes_tool_arguments_and_handoff_return(self):
        tool_message = format_runtime_event(
            {
                "type": "tool_started",
                "tool": "workspace::write_file",
                "arguments": {"path": "notes.txt", "content": "hello"},
            }
        )
        handoff_message = format_runtime_event(
            {
                "type": "handoff_return",
                "source_agent": "core::agent",
                "target_agent": "planner::agent",
                "return_transition": "continue",
            }
        )

        assert "workspace::write_file" in tool_message
        assert "notes.txt" in tool_message
        assert handoff_message == "Handoff return: core::agent <- planner::agent (transition=continue)."

    def test_format_runtime_event_includes_cancellation_messages(self):
        assert format_runtime_event({"type": "run_cancel_requested", "reason": "Please stop"}) == (
            "Run cancellation requested: Please stop."
        )
        assert format_runtime_event({"type": "run_cancelled", "reason": "Please stop"}) == (
            "Run cancelled: Please stop."
        )
