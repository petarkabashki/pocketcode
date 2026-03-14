from __future__ import annotations

import time
from pathlib import Path

from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunCancelledError
from pocketcode.core.session_manager import SessionManager


class _ImmediateRuntime:
    def run(self, shared_store):
        shared_store["active_agent"] = "core.agent"
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
        shared_store["active_agent"] = "core.agent"
        shared_store["final_output"] = f"answer={answer.get('value')}"


class _EventfulRuntime:
    def run(self, shared_store):
        emit = shared_store["runtime_event_handler"]
        emit(
            "tool_started",
            agent="core.agent",
            tool="resource_root.pocketcode.write_file",
            arguments={"path": "notes.txt", "content": "hello"},
        )
        emit(
            "tool_finished",
            agent="core.agent",
            tool="resource_root.pocketcode.write_file",
            success=True,
            result={"success": True, "result": "ok"},
        )
        emit(
            "handoff_return",
            source_agent="core.agent",
            target_agent="planner.agent",
            return_transition="continue",
        )
        shared_store["active_agent"] = "core.agent"
        shared_store["final_output"] = "ready"


class _WarningRuntime:
    def run(self, shared_store):
        shared_store["active_agent"] = "core.agent"
        shared_store["last_vm_validation_warnings"] = [
            {
                "code": "manual-tool-loop",
                "message": "Prefer tool-once.",
                "location": "line 4, cols 1-12",
                "span": {
                    "start_line": 4,
                    "start_column": 1,
                    "end_line": 4,
                    "end_column": 12,
                },
            }
        ]
        shared_store["final_output"] = "ready"


class _EffectHistoryRuntime:
    def run(self, shared_store):
        shared_store["active_agent"] = "core.agent"
        shared_store["last_runtime_effect"] = {
            "kind": "final_answer",
            "payload": {"answer": "ready"},
        }
        shared_store["last_vm_effect"] = {
            "kind": "final_answer",
            "payload": {"answer": "ready"},
        }
        shared_store["last_vm_transition"] = "final_answer"
        shared_store["runtime_effect_history"] = [
            {
                "agent": "core.agent",
                "source": "agent",
                "transition": "final_answer",
                "effect": {"kind": "final_answer", "payload": {"answer": "ready"}},
            }
        ]
        shared_store["vm_effect_history"] = [
            {
                "agent": "core.agent",
                "transition": "final_answer",
                "effect": {"kind": "final_answer", "payload": {"answer": "ready"}},
            }
        ]
        shared_store["final_output"] = "ready"


class _CancellableRuntime:
    def run(self, shared_store):
        for _ in range(100):
            if shared_store["run_cancel_requested"]():
                raise RunCancelledError(shared_store["run_cancel_reason"]())
            time.sleep(0.01)
        shared_store["active_agent"] = "core.agent"
        shared_store["final_output"] = "late"


class _DebuggableRuntime:
    def run(self, shared_store):
        emit = shared_store["runtime_event_handler"]
        shared_store["active_agent"] = "core.agent"
        time.sleep(0.01)
        emit(
            "tool_started",
            agent="core.agent",
            tool="resource_root.pocketcode.write_file",
            arguments={"path": "notes.txt"},
        )
        time.sleep(0.01)
        emit(
            "tool_finished",
            agent="core.agent",
            tool="resource_root.pocketcode.write_file",
            success=True,
            result={"success": True, "result": "ok"},
        )
        shared_store["final_output"] = "ready"


class _NodeDebugRuntime:
    def run(self, shared_store):
        emit = shared_store["runtime_event_handler"]
        shared_store["active_agent"] = "graph.agent"
        shared_store["active_node_id"] = "start"
        shared_store["active_node_kind"] = "noop"
        emit("node_started", agent="graph.agent", node_id="start", node_kind="noop")
        emit("node_completed", agent="graph.agent", node_id="start", node_kind="noop", transition="default")
        shared_store["active_node_id"] = "review"
        shared_store["active_node_kind"] = "tool"
        emit("node_started", agent="graph.agent", node_id="review", node_kind="tool")
        emit("node_completed", agent="graph.agent", node_id="review", node_kind="tool", transition="final_answer")
        shared_store["final_output"] = "done"


def _build_engine(runtime) -> PocketCodeEngine:
    engine = PocketCodeEngine.__new__(PocketCodeEngine)
    engine._runtime_config = {}
    engine._workspace_root = Path("/tmp/test-workspace")
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
    engine.session_debugger_breakpoints = []
    engine.active_agent_profile = None
    engine.last_run_summary = {}
    engine._agent_runtime = runtime
    engine._session_manager = None
    engine.active_session_id = None
    engine.active_session_title = None
    engine.active_session_loaded_from_history = False
    engine.list_agents = lambda: ["core.agent"]
    engine.get_active_skills = lambda: []
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
        assert engine.last_run_summary["current_agent"] == "core.agent"

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
            "tool_finished",
            "handoff_return",
            "run_completed",
        ]
        assert events[1]["step_index"] == 1
        assert events[2]["step_index"] == 1
        assert events[3]["step_index"] == 2
        assert engine.last_run_summary["runtime_event_count"] == 4
        assert engine.last_run_summary["step_count"] == 2
        assert engine.last_run_summary["steps"] == [
            {
                "index": 1,
                "kind": "tool_call",
                "label": "Tool call: resource_root.pocketcode.write_file",
                "status": "completed",
                "parent_step_index": None,
                "duration_ms": engine.last_run_summary["steps"][0]["duration_ms"],
                "summary": "Succeeded: 'ok'",
                "details": {
                    "agent": "core.agent",
                    "tool": "resource_root.pocketcode.write_file",
                    "arguments": {"path": "notes.txt", "content": "hello"},
                    "outcome": {
                        "tool": "resource_root.pocketcode.write_file",
                        "success": True,
                        "result": {"success": True, "result": "ok"},
                    },
                },
            },
            {
                "index": 2,
                "kind": "handoff_return",
                "label": "Handoff return: core.agent <- planner.agent",
                "status": "completed",
                "parent_step_index": None,
                "duration_ms": 0.0,
                "summary": "Transition: continue",
                "details": {
                    "source_agent": "core.agent",
                    "target_agent": "planner.agent",
                    "return_transition": "continue",
                },
            },
        ]

    def test_start_request_includes_vm_validation_warnings_in_run_summary(self):
        engine = _build_engine(_WarningRuntime())

        handle = engine.start_request("hello", {"files": set(), "folders": set(), "urls": set(), "snippets": {}})
        result = handle.wait(timeout=1.0)

        assert result == "ready"
        assert engine.last_run_summary["vm_validation_warning_count"] == 1
        assert engine.last_run_summary["vm_validation_warnings"] == [
            {
                "code": "manual-tool-loop",
                "message": "Prefer tool-once.",
                "location": "line 4, cols 1-12",
                "span": {
                    "start_line": 4,
                    "start_column": 1,
                    "end_line": 4,
                    "end_column": 12,
                },
            }
        ]

    def test_start_request_includes_runtime_effect_history_in_run_summary(self):
        engine = _build_engine(_EffectHistoryRuntime())

        handle = engine.start_request("hello", {"files": set(), "folders": set(), "urls": set(), "snippets": {}})
        result = handle.wait(timeout=1.0)

        assert result == "ready"
        assert engine.last_run_summary["last_runtime_effect"] == {
            "kind": "final_answer",
            "payload": {"answer": "ready"},
        }
        assert engine.last_run_summary["last_vm_effect"] == {
            "kind": "final_answer",
            "payload": {"answer": "ready"},
        }
        assert engine.last_run_summary["last_vm_transition"] == "final_answer"
        assert engine.last_run_summary["runtime_effect_count"] == 1
        assert engine.last_run_summary["vm_effect_count"] == 1
        assert engine.last_run_summary["runtime_effect_history"] == [
            {
                "agent": "core.agent",
                "source": "agent",
                "transition": "final_answer",
                "effect": {"kind": "final_answer", "payload": {"answer": "ready"}},
            }
        ]
        assert engine.last_run_summary["vm_effect_history"] == [
            {
                "agent": "core.agent",
                "transition": "final_answer",
                "effect": {"kind": "final_answer", "payload": {"answer": "ready"}},
            }
        ]

    def test_build_run_summary_includes_standalone_session_summary_when_present(self):
        engine = _build_engine(_EffectHistoryRuntime())

        summary = engine._build_run_summary(
            {
                "active_agent": "core.agent",
                "standalone_session_id": "sess-123",
                "standalone_session_title": "Demo Session",
                "standalone_transcript": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "ready"},
                ],
                "standalone_transcript_text": "User: hello\nAssistant: ready",
                "standalone_session_persistent_keys": ["count", "mode"],
            },
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )

        assert summary["standalone_session"] == {
            "active": True,
            "session_id": "sess-123",
            "title": "Demo Session",
            "transcript_entries": 2,
            "transcript_chars": len("User: hello\nAssistant: ready"),
            "persistent_key_count": 2,
        }
        assert summary["stackvm_runtime"] == {
            "path": "unknown",
            "source": "unknown",
            "standalone_session_active": True,
        }
        assert summary["stackvm_static_runtime_correlation"] == {
            "static_scope_count": 0,
            "runtime_scope_count": 0,
            "matched_scope_count": 0,
            "matched_scopes": [],
            "runtime_only_scopes": [],
            "static_only_scopes": [],
            "static_decision_scope_count": 0,
            "runtime_decision_scope_count": 0,
            "matched_decision_scope_count": 0,
            "matched_decision_scopes": [],
            "runtime_only_decision_scopes": [],
            "static_only_decision_scopes": [],
        }

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

    def test_start_request_debugger_pauses_on_completed_step_events(self):
        engine = _build_engine(_DebuggableRuntime())

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            debug=True,
        )

        for _ in range(100):
            if handle.is_debug_paused:
                break
            time.sleep(0.01)

        assert handle.is_debug_paused is True
        paused_event = handle.debug_pause_event
        assert paused_event is not None
        assert paused_event["type"] == "tool_finished"
        assert paused_event["step_index"] == 1

        snapshot = handle.get_debug_snapshot()
        assert snapshot["active_agent"] == "core.agent"
        assert snapshot["step_count"] == 1
        assert snapshot["runtime_event_count"] == 3

        assert handle.step_debugger() is True
        assert handle.wait(timeout=1.0) == "ready"

    def test_start_request_debugger_can_continue_until_matching_predicate(self):
        engine = _build_engine(_NodeDebugRuntime())

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            debug=True,
        )

        for _ in range(100):
            if handle.is_debug_paused:
                break
            time.sleep(0.01)

        first_pause = handle.debug_pause_event
        assert first_pause is not None
        assert first_pause["type"] == "node_completed"
        assert first_pause["node_id"] == "start"
        assert handle.get_debug_snapshot()["active_node_id"] == "start"
        assert handle.get_debug_snapshot()["active_node_kind"] == "noop"

        assert handle.continue_until_debugger(
            lambda event, _snapshot: str(event.get("node_id") or "") == "review",
            label="until node review",
        ) is True

        for _ in range(100):
            if handle.is_debug_paused:
                break
            time.sleep(0.01)

        second_pause = handle.debug_pause_event
        assert second_pause is not None
        assert second_pause["type"] == "node_completed"
        assert second_pause["node_id"] == "review"
        assert handle.debug_until_label is None
        assert handle.get_debug_snapshot()["active_node_id"] == "review"
        assert handle.get_debug_snapshot()["active_node_kind"] == "tool"

        assert handle.step_debugger() is True
        assert handle.wait(timeout=1.0) == "done"

    def test_start_request_debugger_can_resume_to_persistent_breakpoint(self):
        engine = _build_engine(_NodeDebugRuntime())

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            debug=True,
        )

        for _ in range(100):
            if handle.is_debug_paused:
                break
            time.sleep(0.01)

        first_pause = handle.debug_pause_event
        assert first_pause is not None
        assert first_pause["node_id"] == "start"

        breakpoint_id = handle.add_debug_breakpoint(
            lambda event, _snapshot: str(event.get("node_id") or "") == "review",
            label="until node review",
        )
        assert breakpoint_id == 1
        assert handle.list_debug_breakpoints() == [{"id": 1, "label": "until node review"}]

        assert handle.continue_debugger() is True
        for _ in range(100):
            if handle.is_debug_paused:
                break
            time.sleep(0.01)

        second_pause = handle.debug_pause_event
        assert second_pause is not None
        assert second_pause["node_id"] == "review"
        assert second_pause["debug_breakpoint_id"] == 1
        assert second_pause["debug_breakpoint_label"] == "until node review"

        assert handle.clear_debug_breakpoint(1) is True
        assert handle.list_debug_breakpoints() == []
        assert handle.step_debugger() is True
        assert handle.wait(timeout=1.0) == "done"

    def test_start_request_restores_session_debugger_breakpoints(self):
        engine = _build_engine(_NodeDebugRuntime())
        engine.session_debugger_breakpoints = ["until node review"]

        handle = engine.start_request(
            "hello",
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            debug=True,
        )

        assert handle.list_debug_breakpoints() == [{"id": 1, "label": "until node review"}]
        assert handle.cancel("stop test")

    def test_format_runtime_event_includes_tool_arguments_and_handoff_return(self):
        tool_message = format_runtime_event(
            {
                "type": "tool_started",
                "step_index": 3,
                "tool": "resource_root.pocketcode.write_file",
                "arguments": {"path": "notes.txt", "content": "hello"},
            }
        )
        handoff_message = format_runtime_event(
            {
                "type": "handoff_return",
                "source_agent": "core.agent",
                "target_agent": "planner.agent",
                "return_transition": "continue",
            }
        )

        assert tool_message.startswith("Step 3: Tool call:")
        assert "resource_root.pocketcode.write_file" in tool_message
        assert "notes.txt" in tool_message
        assert handoff_message == "Handoff return: core.agent <- planner.agent (transition=continue)."

    def test_format_runtime_event_includes_cancellation_messages(self):
        assert format_runtime_event({"type": "run_cancel_requested", "reason": "Please stop"}) == (
            "Run cancellation requested: Please stop."
        )
        assert format_runtime_event({"type": "run_cancelled", "reason": "Please stop"}) == (
            "Run cancelled: Please stop."
        )

    def test_start_request_persists_transcript_when_session_manager_is_available(self, tmp_path):
        engine = _build_engine(_ImmediateRuntime())
        engine._workspace_root = tmp_path
        engine._session_manager = SessionManager(tmp_path)

        handle = engine.start_request("hello", {"files": set(), "folders": set(), "urls": set(), "snippets": {}})
        assert handle.wait(timeout=1.0) == "ready"

        assert engine.active_session_id is not None
        saved = engine._session_manager.load_session(engine.active_session_id)
        assert [entry.role for entry in saved.transcript] == ["user", "assistant"]
        assert saved.transcript[0].content == "hello"
        assert saved.transcript[1].content == "ready"
        assert format_runtime_event(
            {"type": "session_saved", "session_id": saved.session_id, "title": saved.title, "transcript_entries": 2}
        ).startswith("Session saved:")

    def test_replace_session_confirmation_overrides_updates_engine_and_session(self, tmp_path):
        engine = _build_engine(_ImmediateRuntime())
        engine._workspace_root = tmp_path
        engine._session_manager = SessionManager(tmp_path)
        engine._ensure_active_session()

        engine.replace_session_confirmation_overrides(
            {"default_policy": None, "tool_policies": {"core.read_file": "allow"}, "agent_policies": {}}
        )

        saved = engine._session_manager.load_session(engine.active_session_id)
        assert engine.session_confirmation_overrides["tool_policies"] == {"core.read_file": "allow"}
        assert saved.session_confirmation_overrides["tool_policies"] == {"core.read_file": "allow"}
