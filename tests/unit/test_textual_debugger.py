from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from pocketcode.cli.textual_ui import PocketCodeTextualApp
from pocketcode.cli.textual_ui.selectors import select_run_preview_blocks
from pocketcode.cli.textual_ui.store import OutputBlock, make_initial_runtime_state


class _EngineStub:
    auto_confirm_tools = False
    active_agent_profile = None
    global_llm_override = None

    def __init__(self):
        self.session_debugger_breakpoints: list[str] = []
        self._saved_sessions = [
            {
                "session_id": "session-1",
                "title": "First session",
                "updated_at": "2026-03-07T10:00:00+00:00",
                "is_active": True,
                "is_resumable": True,
                "debugger_breakpoint_count": 1,
                "debugger_breakpoints": ["until node review"],
            },
            {
                "session_id": "session-2",
                "title": "Earlier work",
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
                "is_resumable": True,
                "debugger_breakpoint_count": 2,
                "debugger_breakpoints": [
                    "until tool core.write_file",
                    "until when pending_tool.name == \"core.write_file\"",
                ],
            },
        ]

    def status(self):
        return {
            "runtime_flow": "internal-router",
            "agent": "coder.safe",
            "active_agent_profile": "coder.safe",
            "global_llm_override": None,
            "session_tool_confirmation_overrides": {},
            "last_run_summary": {
                "runtime_event_count": 0,
                "step_count": 0,
                "steps": [],
                "agent_path": [],
                "llm_usage": {},
                "llm_cost_usd": 0.0,
                "vm_validation_warning_count": 0,
                "vm_validation_warnings": [],
                "context_stats": {},
            },
        }

    def get_current_agent(self):
        return "coder.coder"

    def get_active_skills(self):
        return []

    def get_system_settings(self):
        return {
            "theme_name": "ocean",
            "workspace_view": "balanced",
        }

    def list_agents(self):
        return []

    def list_agent_profiles(self, agent_name=None):
        return []

    def get_agent_prompt_sources(self, agent_name):
        return []

    def list_saved_sessions(self):
        return [dict(item) for item in self._saved_sessions]

    def get_active_session_info(self):
        return {
            "session_id": "session-1",
            "title": "First session",
            "updated_at": "2026-03-07T10:00:00+00:00",
            "debugger_breakpoint_count": 1,
            "debugger_breakpoints": ["until node review"],
        }

    def get_saved_session_details(self, session_id):
        for item in self._saved_sessions:
            if item["session_id"] == session_id:
                return dict(item)
        return {}

    def add_session_debugger_breakpoint(self, label):
        if label not in self.session_debugger_breakpoints:
            self.session_debugger_breakpoints.append(str(label))
        return str(label)

    def clear_session_debugger_breakpoint(self, label):
        text = str(label)
        if text not in self.session_debugger_breakpoints:
            return False
        self.session_debugger_breakpoints = [item for item in self.session_debugger_breakpoints if item != text]
        return True

    def clear_session_debugger_breakpoints(self):
        count = len(self.session_debugger_breakpoints)
        self.session_debugger_breakpoints = []
        return count

    def clear_saved_session_debugger_breakpoints(self, session_id):
        for item in self._saved_sessions:
            if item["session_id"] == session_id:
                cleared = len(item.get("debugger_breakpoints", []))
                item["debugger_breakpoint_count"] = 0
                item["debugger_breakpoints"] = []
                return {"session_id": session_id, "cleared": cleared}
        return {"session_id": session_id, "cleared": 0}


class _DebugHandleStub:
    def __init__(self):
        self.step_calls: list[int] = []
        self.continue_calls = 0
        self.cancel_calls: list[str] = []
        self.added_breakpoints: list[str] = []
        self.cleared_all = 0
        self.cleared_ids: list[int] = []
        self._pause_event = {
            "type": "node_completed",
            "node_id": "review",
            "node_kind": "tool",
            "transition": "final_answer",
        }

    @property
    def is_debug_paused(self):
        return True

    @property
    def debug_pause_event(self):
        return dict(self._pause_event)

    @property
    def debug_until_label(self):
        return "until node review"

    def get_debug_snapshot(self):
        return {
            "active_agent": "review.safe",
            "active_node_id": "review",
            "active_node_kind": "tool",
            "runtime_event_count": 4,
            "step_count": 2,
            "steps": [
                {"index": 1, "kind": "node", "status": "completed", "summary": "start"},
                {"index": 2, "kind": "node", "status": "completed", "summary": "review"},
            ],
        }

    def list_debug_breakpoints(self):
        return [{"id": 1, "label": "until tool core.write_file"}]

    def step_debugger(self, count=1):
        self.step_calls.append(int(count))
        return True

    def add_debug_breakpoint(self, predicate, *, label):
        self.added_breakpoints.append(str(label))
        return len(self.added_breakpoints)

    def clear_all_debug_breakpoints(self):
        self.cleared_all += 1
        return 1

    def clear_debug_breakpoint(self, breakpoint_id):
        self.cleared_ids.append(int(breakpoint_id))
        return True

    def continue_debugger(self):
        self.continue_calls += 1
        return True

    def cancel(self, reason):
        self.cancel_calls.append(str(reason))
        return True


def test_select_run_preview_blocks_includes_debugger_block():
    blocks = select_run_preview_blocks(
        make_initial_runtime_state(),
        _EngineStub().status(),
        debugger_state={
            "attached": True,
            "paused": True,
            "pause_event": {
                "type": "node_completed",
                "node_id": "review",
                "node_kind": "tool",
                "transition": "final_answer",
            },
            "snapshot": {
                "active_agent": "review.safe",
                "active_node_id": "review",
                "active_node_kind": "tool",
                "runtime_event_count": 4,
                "step_count": 2,
            },
            "until_label": "until node review",
            "breakpoints": ({"id": 1, "label": "until tool core.write_file"},),
        },
    )

    debugger_block = next(block for block in blocks if block.title == "Debugger")
    breakpoint_block = next(block for block in blocks if block.title == "Breakpoint #1")
    assert "paused: yes" in debugger_block.text
    assert "active_node: review (tool)" in debugger_block.text
    assert "stop_condition: until node review" in debugger_block.text
    assert breakpoint_block.text == "until tool core.write_file"


def test_textual_debug_request_runner_queues_debug_run():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    app.call_from_thread = lambda func, *args: func(*args)

    message = cli_context["debug_request_runner"]("inspect the active agent")

    assert message == "Debugger starting in the Run view."
    assert app._queued_textual_actions == [("start_debug_request", "inspect the active agent")]


def test_textual_debugger_input_supports_counted_step_commands():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    app._refresh_ui = lambda: None
    app._set_main_input_placeholder = lambda prompt=None: None

    handled = app._handle_textual_debugger_input("next 3")

    assert handled is True
    assert app._active_run.step_calls == [3]
    assert app._runtime_state.run_status == "debug_running"


def test_textual_debugger_actions_drive_run_handle_controls():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    app._refresh_ui = lambda: None
    app._set_main_input_placeholder = lambda prompt=None: None
    app._write_info = lambda text: None

    app.action_debug_next()
    app.action_debug_continue()
    app.action_debug_quit()

    assert app._active_run.step_calls == [1]
    assert app._active_run.continue_calls == 2
    assert app._active_run.cancel_calls == ["Run cancelled from Textual debugger."]


def test_textual_debugger_shortcut_reports_missing_debug_run():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    messages: list[str] = []
    app._write_info = lambda text: messages.append(str(text))

    app.action_debug_status()

    assert messages == ["No active debug run."]


def test_textual_debugger_can_add_breakpoint_inline_by_default():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    engine = _EngineStub()
    app = PocketCodeTextualApp(engine, cli_context)
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))
    app._refresh_ui = lambda: None

    app.action_debug_add_breakpoint()
    app._set_inline_debugger_breakpoint_type("tool")
    app._debugger_inline_breakpoint_value = "core.write_file"
    app._submit_inline_debugger_breakpoint()

    assert app._active_run.added_breakpoints == ["until tool core.write_file"]
    assert engine.session_debugger_breakpoints == ["until tool core.write_file"]
    assert info_messages[-1] == "Breakpoint 1 added: until tool core.write_file"


def test_textual_debugger_can_add_breakpoint_via_picker_flow_when_control_presentation_is_modal():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    engine = _EngineStub()
    app = PocketCodeTextualApp(engine, cli_context)
    app._control_presentation = "modal"
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))
    app._refresh_ui = lambda: None
    app._present_asset_picker_modal = lambda **kwargs: kwargs["on_select"]("tool")
    app._present_name_input_modal = lambda **kwargs: kwargs["on_submit"]("core.write_file")

    app.action_debug_add_breakpoint()

    assert app._active_run.added_breakpoints == ["until tool core.write_file"]
    assert engine.session_debugger_breakpoints == ["until tool core.write_file"]
    assert info_messages[-1] == "Breakpoint 1 added: until tool core.write_file"


def test_textual_debugger_can_clear_breakpoints_from_action():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    engine = _EngineStub()
    engine.session_debugger_breakpoints = ["until tool core.write_file"]
    app = PocketCodeTextualApp(engine, cli_context)
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))
    app._refresh_ui = lambda: None

    app.action_debug_clear_breakpoints()

    assert app._active_run.cleared_all == 1
    assert engine.session_debugger_breakpoints == []
    assert info_messages[-1] == "Cleared 1 breakpoint(s)."


def test_textual_debugger_can_clear_selected_breakpoint_block():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    engine = _EngineStub()
    engine.session_debugger_breakpoints = ["until tool core.write_file"]
    app = PocketCodeTextualApp(engine, cli_context)
    app._active_run = _DebugHandleStub()
    app._textual_debugger_active = True
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))
    app._refresh_ui = lambda: None
    app._ui_state = SimpleNamespace(
        run_preview_blocks=(
            OutputBlock(kind="code", title="Debugger", text="paused: yes", language="text"),
            OutputBlock(kind="code", title="Breakpoint #1", text="until tool core.write_file", language="text"),
        )
    )
    app._cli_state = replace(
        app._cli_state,
        selected_surface_block_indices=(("run-preview", 1),),
    )

    app.action_debug_clear_selected_breakpoint()

    assert app._active_run.cleared_ids == [1]
    assert engine.session_debugger_breakpoints == []
    assert info_messages[-1] == "Cleared breakpoint 1."


def test_textual_control_center_session_actions_include_breakpoint_management():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)

    values = [option.value for option in app._asset_action_options("sessions")]

    assert "inspect_breakpoints" in values
    assert "clear_breakpoints" in values


def test_textual_saved_session_picker_for_breakpoints_lists_saved_sessions():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    picker_calls: list[dict[str, object]] = []
    app._show_picker = lambda **kwargs: picker_calls.append(kwargs)

    app._open_saved_session_picker(action="inspect_breakpoints")

    assert len(picker_calls) == 1
    picker_call = picker_calls[0]
    assert picker_call["title"] == "Inspect Session Breakpoints"
    options = picker_call["options"]
    assert [option.value for option in options] == ["session-1", "session-2"]
    assert "breaks=1" in options[0].description
    assert "breaks=2" in options[1].description


def test_textual_can_inspect_saved_session_breakpoints():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    app = PocketCodeTextualApp(_EngineStub(), cli_context)
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))

    app._inspect_saved_session_breakpoints("session-2")

    message = info_messages[-1]
    assert "Session: Earlier work" in message
    assert "Debugger breakpoints: 2" in message
    assert "until tool core.write_file" in message


def test_textual_can_clear_saved_session_breakpoints():
    cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
    engine = _EngineStub()
    app = PocketCodeTextualApp(engine, cli_context)
    info_messages: list[str] = []
    app._write_info = lambda text: info_messages.append(str(text))

    app._clear_saved_session_breakpoints("session-2")

    assert info_messages[-1] == "Cleared 2 debugger breakpoint(s) from session: session-2"
    session = next(item for item in engine.list_saved_sessions() if item["session_id"] == "session-2")
    assert session["debugger_breakpoint_count"] == 0
    assert session["debugger_breakpoints"] == []
