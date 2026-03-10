from __future__ import annotations

from typing import Any, Dict

from pocketcode.cli.debugger_commands import (
    build_debugger_until_predicate,
    parse_debug_step_count,
    split_debugger_command,
)
from pocketcode.cli.runtime_events import format_runtime_event

from .shared import PickerOption
from .shared import DEFAULT_MAIN_INPUT_PLACEHOLDER
from .store import OutputBlock


_TEXTUAL_DEBUGGER_PLACEHOLDER = (
    "Debugger paused. Enter next, continue, until ..., break ..., breaks, clear, status, steps, quit"
)

_BREAKPOINT_PICKER_OPTIONS = (
    PickerOption(value="node", label="Node", description="Stop when a node id completes"),
    PickerOption(value="agent", label="Agent", description="Stop when a pause event matches an agent"),
    PickerOption(value="tool", label="Tool", description="Stop when a pause event matches a tool"),
    PickerOption(value="event", label="Event", description="Stop when a runtime event type matches"),
    PickerOption(value="handoff", label="Handoff", description="Stop at the next handoff"),
    PickerOption(value="error", label="Error", description="Stop at the next runtime error"),
    PickerOption(value="answer", label="Answer", description="Stop at the next final answer"),
    PickerOption(value="ask", label="Ask", description="Stop at the next ask-user event"),
    PickerOption(value="when", label="Condition", description="Stop when a snapshot or event condition matches"),
)


class TextualAppDebuggerMixin:
    def _can_sync_debugger_ui(self) -> bool:
        return bool(getattr(self, "_screen_stack", []))

    def _debugger_uses_modal_controls(self) -> bool:
        return getattr(self, "_control_presentation", "inline") == "modal"

    def _breakpoint_prompt_spec(self, choice: str) -> tuple[str, str, str]:
        prompt_map = {
            "node": (
                "Add Node Breakpoint",
                "review_route",
                "Enter the node id to stop on when `node_completed` is observed.",
            ),
            "agent": (
                "Add Agent Breakpoint",
                "review.safe",
                "Enter the active agent name to stop on.",
            ),
            "tool": (
                "Add Tool Breakpoint",
                "core.write_file",
                "Enter the tool name to stop on.",
            ),
            "event": (
                "Add Event Breakpoint",
                "tool_finished",
                "Enter the runtime event type to stop on.",
            ),
            "when": (
                "Add Conditional Breakpoint",
                'pending_tool.name == "core.write_file"',
                "Enter a condition such as event.node_id == review_route or pending_tool.name == \"core.write_file\".",
            ),
        }
        return prompt_map.get(
            choice,
            ("Add Breakpoint", "", "Enter a breakpoint target."),
        )

    def _breakpoint_target_required(self, choice: str) -> bool:
        return choice in {"node", "agent", "tool", "event", "when"}

    def _set_inline_debugger_breakpoint_type(self, choice: str) -> None:
        normalized = str(choice or "node").strip().lower()
        if normalized not in {"node", "agent", "tool", "event", "handoff", "error", "answer", "ask", "when"}:
            normalized = "node"
        _, placeholder, help_text = self._breakpoint_prompt_spec(normalized)
        if not self._breakpoint_target_required(normalized):
            help_text = f"Add a breakpoint for the next {normalized} event."
            placeholder = ""
        self._debugger_inline_breakpoint_type = normalized
        self._debugger_inline_breakpoint_help = help_text
        self._debugger_inline_breakpoint_placeholder = placeholder
        if not self._breakpoint_target_required(normalized):
            self._debugger_inline_breakpoint_value = ""

    def _show_inline_debugger_breakpoint_editor(self, choice: str = "node") -> None:
        self._debugger_inline_breakpoint_visible = True
        self._set_inline_debugger_breakpoint_type(choice)
        if self._can_sync_debugger_ui():
            self._commit_engine_ui_update()
            self.call_after_refresh(self._focus_inline_debugger_breakpoint_input)

    def _focus_inline_debugger_breakpoint_input(self) -> None:
        from textual.widgets import Input, Select

        if self._breakpoint_target_required(getattr(self, "_debugger_inline_breakpoint_type", "node")):
            target = self.query_one("#debugger-inline-value-input", Input)
            target.focus()
            return
        self.query_one("#debugger-inline-type-select", Select).focus()

    def _hide_inline_debugger_breakpoint_editor(self) -> None:
        self._debugger_inline_breakpoint_visible = False
        self._debugger_inline_breakpoint_value = ""
        if self._can_sync_debugger_ui():
            self._commit_engine_ui_update()

    def _submit_inline_debugger_breakpoint(self) -> None:
        choice = str(getattr(self, "_debugger_inline_breakpoint_type", "node") or "node")
        if self._breakpoint_target_required(choice):
            if self._can_sync_debugger_ui():
                from textual.widgets import Input

                raw_value = self.query_one("#debugger-inline-value-input", Input).value
            else:
                raw_value = getattr(self, "_debugger_inline_breakpoint_value", "")
            clean_value = str(raw_value or "").strip()
            self._debugger_inline_breakpoint_value = clean_value
            if not clean_value:
                self._write_error("Enter a breakpoint target first.")
                if self._can_sync_debugger_ui():
                    self._commit_engine_ui_update()
                return
            self._submit_textual_breakpoint(choice, clean_value)
        else:
            self._add_textual_breakpoint(choice)
        self._hide_inline_debugger_breakpoint_editor()

    def _breakpoint_id_from_run_preview_block(self, block: Any) -> int | None:
        title = str(getattr(block, "title", "") or "").strip()
        if not title.startswith("Breakpoint #"):
            return None
        raw_id = title[len("Breakpoint #") :].strip()
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None

    def _selected_textual_breakpoint_id(self, *, run_preview_blocks: tuple[Any, ...] | None = None) -> int | None:
        blocks = tuple(run_preview_blocks or (self._ui_state.run_preview_blocks if self._ui_state is not None else ()))
        if not blocks:
            return None
        selected_index = dict(self._cli_state.selected_surface_block_indices).get("run-preview")
        if isinstance(selected_index, int) and 0 <= selected_index < len(blocks):
            return self._breakpoint_id_from_run_preview_block(blocks[selected_index])
        return None

    def _ensure_textual_debugger_session(self) -> bool:
        if not self._textual_debugger_active or self._active_run is None:
            self._write_info("No active debug run.")
            return False
        return True

    def _execute_textual_debugger_shortcut(self, command: str) -> bool:
        if not self._ensure_textual_debugger_session():
            return False
        if not self._active_run.is_debug_paused:
            if str(command).strip().lower() in {"status", "where", "breaks", "bp"}:
                self._write_info(self._build_textual_debugger_status_text())
                return False
            self._write_info("Debugger is running. Wait for the next pause.")
            return False
        return self._handle_textual_debugger_input(command)

    def _enqueue_textual_debug_request(self, request: str) -> str:
        text = str(request or "").strip()
        if not text:
            return ""
        try:
            self.call_from_thread(self._queue_start_debug_request, text)
        except RuntimeError:
            self._queue_start_debug_request(text)
        return "Debugger starting in the Run view."

    def _queue_start_debug_request(self, request: str) -> None:
        self._queued_textual_actions.append(("start_debug_request", str(request)))

    def _start_debug_request_from_queue(self, request: str) -> None:
        with self._batch_ui_update(commit=False):
            self._textual_debugger_active = True
            self._textual_debugger_last_pause_key = None
            self._set_runtime_busy(True)
            self._set_runtime_status("debug_running")
            self._set_current_view("run", refresh=False)
            self._start_request_effect(str(request), debug=True)
        self._write_info("Debugger attached. Run view will update when execution pauses.")
        self._refresh_ui()

    def _current_textual_debugger_state(self) -> Dict[str, Any] | None:
        if not self._textual_debugger_active or self._active_run is None:
            return None
        return {
            "attached": True,
            "paused": bool(self._active_run.is_debug_paused),
            "pause_event": self._active_run.debug_pause_event,
            "snapshot": self._active_run.get_debug_snapshot(),
            "until_label": self._active_run.debug_until_label,
            "breakpoints": tuple(self._active_run.list_debug_breakpoints()),
        }

    def _sync_textual_debugger_state(self) -> bool:
        if not self._textual_debugger_active or self._active_run is None:
            self._textual_debugger_last_pause_key = None
            self._debugger_inline_breakpoint_visible = False
            return False

        if self._active_run.is_debug_paused:
            pause_event = self._active_run.debug_pause_event or {}
            pause_key = (
                str(pause_event.get("type") or ""),
                pause_event.get("step_index"),
                str(pause_event.get("node_id") or ""),
                str(pause_event.get("tool") or ""),
                pause_event.get("debug_breakpoint_id"),
            )
            changed = False
            if self._runtime_state.run_status != "debug_paused":
                self._set_runtime_status("debug_paused")
                changed = True
            if self._runtime_state.pending_input_request is None:
                self._set_main_input_placeholder(_TEXTUAL_DEBUGGER_PLACEHOLDER)
                changed = True
            if pause_key != self._textual_debugger_last_pause_key:
                self._set_current_view("run", refresh=False)
                changed = True
            self._textual_debugger_last_pause_key = pause_key
            return changed

        changed = False
        if self._runtime_state.run_status == "debug_paused":
            self._set_runtime_status("debug_running")
            changed = True
        if (
            self._runtime_state.pending_input_request is None
            and self._runtime_state.main_input_placeholder != DEFAULT_MAIN_INPUT_PLACEHOLDER
        ):
            self._set_main_input_placeholder()
            changed = True
        self._textual_debugger_last_pause_key = None
        return changed

    def _handle_textual_debugger_input(self, raw_text: str) -> bool:
        if self._active_run is None or not self._active_run.is_debug_paused:
            return False

        command_text = str(raw_text or "").strip()
        if command_text.startswith("/"):
            command_text = command_text[1:].strip()

        parts = split_debugger_command(command_text)
        if not parts:
            if self._active_run.step_debugger():
                self._set_runtime_status("debug_running")
                self._set_main_input_placeholder()
                self._refresh_ui()
            return True

        normalized = parts[0].lower()
        if normalized in {"n", "next", "s", "step"}:
            count = parse_debug_step_count(parts[1:] if len(parts) > 1 else [])
            if count is None:
                self._write_error("Debugger usage: next [count]")
                return True
            if self._active_run.step_debugger(count=count):
                self._set_runtime_status("debug_running")
                self._set_main_input_placeholder()
                self._refresh_ui()
            return True
        if normalized in {"c", "cont", "continue"}:
            if self._active_run.continue_debugger():
                self._set_runtime_status("debug_running")
                self._set_main_input_placeholder()
                self._refresh_ui()
            return True
        if normalized in {"p", "pause", "status", "where"}:
            self._write_info(self._build_textual_debugger_status_text())
            return True
        if normalized in {"steps", "timeline"}:
            self._write_textual_debugger_steps()
            return True
        if normalized in {"break", "b"}:
            breakpoint_config = build_debugger_until_predicate(parts[1:])
            if breakpoint_config is None:
                self._write_error("Debugger usage: break <node|agent|tool|event|when> ...")
                return True
            predicate, label = breakpoint_config
            breakpoint_id = self._active_run.add_debug_breakpoint(predicate, label=label)
            if hasattr(self._engine, "add_session_debugger_breakpoint"):
                self._engine.add_session_debugger_breakpoint(label)
            self._write_info(f"Breakpoint {breakpoint_id} added: {label}")
            self._refresh_ui()
            return True
        if normalized in {"breaks", "bp"}:
            breakpoints = self._active_run.list_debug_breakpoints()
            if not breakpoints:
                self._write_info("No breakpoints set.")
                return True
            self._write_info(
                "Breakpoints:\n" + "\n".join(
                    f"- {item.get('id')}. {item.get('label')}" for item in breakpoints
                )
            )
            return True
        if normalized == "clear":
            if len(parts) == 1 or parts[1].lower() == "all":
                cleared = self._active_run.clear_all_debug_breakpoints()
                if hasattr(self._engine, "clear_session_debugger_breakpoints"):
                    self._engine.clear_session_debugger_breakpoints()
                self._write_info(f"Cleared {cleared} breakpoint(s).")
                self._refresh_ui()
                return True
            try:
                breakpoint_id = int(parts[1])
            except (TypeError, ValueError):
                self._write_error("Debugger usage: clear <breakpoint_id|all>")
                return True
            label = None
            for item in self._active_run.list_debug_breakpoints():
                if int(item.get("id", -1)) == breakpoint_id:
                    label = str(item.get("label") or "")
                    break
            if self._active_run.clear_debug_breakpoint(breakpoint_id):
                if label and hasattr(self._engine, "clear_session_debugger_breakpoint"):
                    self._engine.clear_session_debugger_breakpoint(label)
                self._write_info(f"Cleared breakpoint {breakpoint_id}.")
                self._refresh_ui()
            else:
                self._write_error(f"Breakpoint {breakpoint_id} not found.")
            return True
        if normalized == "until":
            predicate_config = build_debugger_until_predicate(parts[1:])
            if predicate_config is None:
                self._write_error("Debugger usage: until <node|agent|tool|event|when> ...")
                return True
            predicate, label = predicate_config
            if self._active_run.continue_until_debugger(predicate, label=label):
                self._set_runtime_status("debug_running")
                self._set_main_input_placeholder()
                self._refresh_ui()
            return True
        if normalized in {"q", "quit", "cancel"}:
            if self._active_run.cancel("Run cancelled from Textual debugger."):
                self._write_info("Cancellation requested.")
            self._active_run.continue_debugger()
            self._set_runtime_status("stopping")
            self._set_main_input_placeholder()
            self._refresh_ui()
            return True
        if normalized in {"h", "help", "?"}:
            self._write_info(
                "Debugger commands: next [count], continue, until node <id>, until agent <name>, "
                "until tool <name>, until event <type>, until when <path> == <value>, "
                "break <...>, breaks, clear <id|all>, status, steps, quit, help"
            )
            return True

        self._write_error(
            "Unknown debugger command. Use: next [count], continue, until ..., break <...>, "
            "breaks, clear <id|all>, status, steps, quit, help"
        )
        return True

    def _build_textual_debugger_status_text(self) -> str:
        debug_state = self._current_textual_debugger_state() or {}
        snapshot = debug_state.get("snapshot") if isinstance(debug_state, dict) else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        pause_event = debug_state.get("pause_event") if isinstance(debug_state, dict) else {}
        if not isinstance(pause_event, dict):
            pause_event = {}
        breakpoints = debug_state.get("breakpoints") if isinstance(debug_state, dict) else ()
        until_label = debug_state.get("until_label") if isinstance(debug_state, dict) else None

        lines = [
            f"paused: {'yes' if debug_state.get('paused') else 'no'}",
            f"active_agent: {snapshot.get('active_agent') or 'unknown'}",
        ]
        if snapshot.get("active_node_id"):
            lines.append(
                f"active_node: {snapshot.get('active_node_id')} ({snapshot.get('active_node_kind') or 'node'})"
            )
        if pause_event:
            lines.append(f"pause_event: {format_runtime_event(pause_event)}")
        if until_label:
            lines.append(f"stop_condition: {until_label}")
        lines.append(f"breakpoints: {len(tuple(breakpoints))}")
        lines.append(f"runtime_events: {snapshot.get('runtime_event_count', 0)}")
        lines.append(f"runtime_steps: {snapshot.get('step_count', 0)}")
        return "\n".join(lines)

    def _write_textual_debugger_steps(self) -> None:
        debug_state = self._current_textual_debugger_state() or {}
        snapshot = debug_state.get("snapshot") if isinstance(debug_state, dict) else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        steps = snapshot.get("steps", [])
        if not isinstance(steps, list) or not steps:
            self._write_info("No recorded steps yet.")
            return

        lines: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            duration = step.get("duration_ms")
            duration_suffix = f" [{float(duration):.1f}ms]" if isinstance(duration, (int, float)) else ""
            lines.append(
                f"{step.get('index')}. {step.get('kind')} ({step.get('status')}){duration_suffix} "
                f"{step.get('summary')}"
            )
        self._append_output_block(
            OutputBlock(kind="code", title="Debugger Steps", text="\n".join(lines), language="text"),
            include_in_transcript=False,
        )
        self._sync_output_widget()

    def _add_textual_breakpoint(self, *args: str) -> bool:
        if not self._ensure_textual_debugger_session():
            return False
        predicate_config = build_debugger_until_predicate(list(args))
        if predicate_config is None:
            self._write_error("Invalid breakpoint configuration.")
            return False
        predicate, label = predicate_config
        breakpoint_id = self._active_run.add_debug_breakpoint(predicate, label=label)
        if hasattr(self._engine, "add_session_debugger_breakpoint"):
            self._engine.add_session_debugger_breakpoint(label)
        self._write_info(f"Breakpoint {breakpoint_id} added: {label}")
        self._refresh_ui()
        return True

    def _present_textual_breakpoint_picker(self) -> None:
        if not self._ensure_textual_debugger_session():
            return
        if not self._debugger_uses_modal_controls():
            self._show_inline_debugger_breakpoint_editor()
            return
        self._present_asset_picker_modal(
            title="Add Breakpoint",
            options=_BREAKPOINT_PICKER_OPTIONS,
            current_value=None,
            help_text="Choose a breakpoint type, then provide its target if needed.",
            empty_message="No breakpoint types available.",
            on_select=self._handle_textual_breakpoint_picker_selection,
        )

    def _handle_textual_breakpoint_picker_selection(self, selection: str) -> None:
        choice = str(selection or "").strip().lower()
        if not choice:
            return
        if choice in {"handoff", "error", "answer", "ask"}:
            self._add_textual_breakpoint(choice)
            return
        title, placeholder, help_text = self._breakpoint_prompt_spec(choice)
        self._present_name_input_modal(
            title=title,
            placeholder=placeholder,
            help_text=help_text,
            on_submit=lambda value, choice=choice: self._submit_textual_breakpoint(choice, value),
        )

    def _submit_textual_breakpoint(self, choice: str, value: str) -> None:
        clean_value = str(value or "").strip()
        if not clean_value:
            return
        if choice == "when":
            self._add_textual_breakpoint("when", *split_debugger_command(clean_value))
            return
        self._add_textual_breakpoint(choice, clean_value)

    def action_debug_next(self) -> None:
        self._execute_textual_debugger_shortcut("next")

    def action_debug_continue(self) -> None:
        self._execute_textual_debugger_shortcut("continue")

    def action_debug_status(self) -> None:
        self._execute_textual_debugger_shortcut("status")

    def action_debug_breakpoints(self) -> None:
        self._execute_textual_debugger_shortcut("breaks")

    def action_debug_add_breakpoint(self) -> None:
        self._present_textual_breakpoint_picker()

    def action_debug_inline_add_breakpoint(self) -> None:
        if not self._ensure_textual_debugger_session():
            return
        self._submit_inline_debugger_breakpoint()

    def action_debug_clear_breakpoints(self) -> None:
        if not self._ensure_textual_debugger_session():
            return
        cleared = self._active_run.clear_all_debug_breakpoints()
        if hasattr(self._engine, "clear_session_debugger_breakpoints"):
            self._engine.clear_session_debugger_breakpoints()
        self._write_info(f"Cleared {cleared} breakpoint(s).")
        self._refresh_ui()

    def action_debug_clear_selected_breakpoint(self) -> None:
        if not self._ensure_textual_debugger_session():
            return
        breakpoint_id = self._selected_textual_breakpoint_id()
        if breakpoint_id is None:
            self._write_info("Select a breakpoint block in the Run view first.")
            return
        label = None
        for item in self._active_run.list_debug_breakpoints():
            if int(item.get("id", -1)) == int(breakpoint_id):
                label = str(item.get("label") or "")
                break
        if self._active_run.clear_debug_breakpoint(breakpoint_id):
            if label and hasattr(self._engine, "clear_session_debugger_breakpoint"):
                self._engine.clear_session_debugger_breakpoint(label)
            self._write_info(f"Cleared breakpoint {breakpoint_id}.")
            self._refresh_ui()
            return
        self._write_error(f"Breakpoint {breakpoint_id} not found.")

    def action_debug_quit(self) -> None:
        self._execute_textual_debugger_shortcut("quit")
