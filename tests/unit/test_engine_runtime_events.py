from __future__ import annotations

import time

from pocketcode.core.engine import PocketCodeEngine


class _ImmediateRuntime:
    def run(self, shared_store):
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = "ready"


class _PromptRuntime:
    def run(self, shared_store):
        answer = shared_store["user_input_handler"]("Approve tool execution?")
        shared_store["active_agent"] = "core::agent"
        shared_store["final_output"] = f"answer={answer}"


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
            prompt_event = next((event for event in events if event["type"] == "user_input_requested"), None)
            if prompt_event is not None:
                break
            time.sleep(0.01)

        assert prompt_event is not None
        assert "Approve tool execution?" in prompt_event["prompt"]

        assert handle.resolve_user_input(str(prompt_event["prompt_id"]), "yes") is True
        result = handle.wait(timeout=1.0)
        events.extend(handle.drain_events())

        assert result == "answer=yes"
        assert [event["type"] for event in events] == [
            "run_started",
            "user_input_requested",
            "user_input_received",
            "run_completed",
        ]
