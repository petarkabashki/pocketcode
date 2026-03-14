from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from pocketcode.core.user_interaction import normalize_interaction_request


class RunCancelledError(Exception):
    def __init__(self, message: str = "Run cancelled.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {"type": self.event_type, **self.payload}


class RunHandle:
    def __init__(self) -> None:
        self._events: queue.Queue[RuntimeEvent] = queue.Queue()
        self._done = threading.Event()
        self._cancel_requested = threading.Event()
        self._prompt_condition = threading.Condition()
        self._debug_condition = threading.Condition()
        self._prompt_counter = 0
        self._prompt_responses: Dict[str, Optional[str]] = {}
        self._interaction_requests: Dict[str, Dict[str, Any]] = {}
        self._interaction_responses: Dict[str, Optional[Dict[str, Any]]] = {}
        self._thread: threading.Thread | None = None
        self._result: str | None = None
        self._error: Exception | None = None
        self._cancel_reason = "Run cancelled."
        self._debug_enabled = False
        self._debug_mode = "continue"
        self._debug_paused_event: Dict[str, Any] | None = None
        self._debug_snapshot_provider: Any = None
        self._debug_step_budget: int | None = None
        self._debug_until_predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool] | None = None
        self._debug_until_label: str | None = None
        self._debug_breakpoints: list[dict[str, Any]] = []
        self._debug_breakpoint_counter = 0
        self._active_vm: Any | None = None

    def start(self, target: Any) -> None:
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def emit(self, event_type: str, **payload: Any) -> None:
        event_payload = dict(payload)
        self._events.put(RuntimeEvent(event_type=event_type, payload=event_payload))
        self._pause_for_debugger(event_type=event_type, payload=event_payload)

    def drain_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        drained: list[dict[str, Any]] = []
        for _ in range(max(limit, 0)):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            drained.append(event.as_dict())
        return drained

    def request_user_input(self, prompt: str) -> str:
        response = self.request_interaction(
            {
                "kind": "text",
                "prompt": prompt,
                "allow_empty": True,
            }
        )
        return str(response.get("value") or "")

    def resolve_user_input(self, prompt_id: str, value: str) -> bool:
        return self.resolve_interaction(
            prompt_id,
            {
                "value": value,
                "raw_input": value,
            },
        )

    def request_interaction(self, request: Dict[str, Any] | Any) -> Dict[str, Any]:
        interaction = normalize_interaction_request(request)
        with self._prompt_condition:
            self._prompt_counter += 1
            request_id = f"interaction-{self._prompt_counter}"
            payload = interaction.as_dict(request_id=request_id)
            self._interaction_requests[request_id] = dict(payload)
            self._interaction_responses[request_id] = None

        self.emit("interaction_requested", **payload)

        with self._prompt_condition:
            while (
                self._interaction_responses.get(request_id) is None
                and not self._done.is_set()
                and not self._cancel_requested.is_set()
            ):
                self._prompt_condition.wait()
            response = self._interaction_responses.pop(request_id, None)
            self._interaction_requests.pop(request_id, None)

        if response is None and self._cancel_requested.is_set():
            raise RunCancelledError(self._cancel_reason)
        return {} if response is None else dict(response)

    def resolve_interaction(self, request_id: str, response: Dict[str, Any] | Any) -> bool:
        with self._prompt_condition:
            if request_id not in self._interaction_responses:
                return False

            request = dict(self._interaction_requests.get(request_id, {}))
            if isinstance(response, dict):
                payload = dict(response)
            else:
                payload = {"value": response, "raw_input": str(response)}

            payload.setdefault("kind", request.get("kind", "text"))
            payload["request_id"] = request_id
            self._interaction_responses[request_id] = payload
            self._prompt_condition.notify_all()

        self.emit("interaction_received", **payload)
        return True

    def complete(self, *, result: str, summary: Dict[str, Any] | None = None) -> None:
        self._result = result
        self.emit("run_completed", output=result, summary=dict(summary or {}))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()
        with self._debug_condition:
            self._debug_condition.notify_all()

    def cancelled(self, *, reason: str, summary: Dict[str, Any] | None = None) -> None:
        self._result = ""
        self.emit("run_cancelled", reason=reason, summary=dict(summary or {}))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()
        with self._debug_condition:
            self._debug_condition.notify_all()

    def fail(self, error: Exception) -> None:
        self._error = error
        self.emit("run_failed", error=str(error))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()
        with self._debug_condition:
            self._debug_condition.notify_all()

    def cancel(self, reason: str = "Run cancelled by user.") -> bool:
        if self._done.is_set() or self._cancel_requested.is_set():
            return False
        self._cancel_reason = str(reason or "Run cancelled.")
        self._cancel_requested.set()
        self.emit("run_cancel_requested", reason=self._cancel_reason)
        with self._prompt_condition:
            self._prompt_condition.notify_all()
        with self._debug_condition:
            self._debug_condition.notify_all()
        return True

    def wait(self, timeout: float | None = None) -> str:
        finished = self._done.wait(timeout)
        if not finished:
            raise TimeoutError("Run did not complete before timeout.")
        if self._thread is not None:
            self._thread.join(timeout=0)
        if self._error is not None:
            raise self._error
        return str(self._result or "")

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    @property
    def is_cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    @property
    def cancel_reason(self) -> str:
        return self._cancel_reason

    def enable_debugger(self, *, start_mode: str = "step") -> None:
        with self._debug_condition:
            self._debug_enabled = True
            self._debug_mode = "continue" if str(start_mode).strip().lower() == "continue" else "step"
            self._debug_paused_event = None
            self._debug_step_budget = None
            self._debug_until_predicate = None
            self._debug_until_label = None
            self._debug_condition.notify_all()

    def disable_debugger(self) -> None:
        with self._debug_condition:
            self._debug_enabled = False
            self._debug_mode = "continue"
            self._debug_paused_event = None
            self._debug_step_budget = None
            self._debug_until_predicate = None
            self._debug_until_label = None
            self._debug_breakpoints = []
            self._debug_breakpoint_counter = 0
            self._debug_condition.notify_all()

    def set_debug_snapshot_provider(self, provider: Any) -> None:
        self._debug_snapshot_provider = provider

    def get_debug_snapshot(self) -> Dict[str, Any]:
        provider = self._debug_snapshot_provider
        if not callable(provider):
            return {}
        snapshot = provider()
        return dict(snapshot) if isinstance(snapshot, dict) else {"value": snapshot}

    def set_active_vm(self, vm: Any) -> None:
        with self._debug_condition:
            self._active_vm = vm

    def get_active_vm(self) -> Any | None:
        with self._debug_condition:
            return self._active_vm

    def step_debugger(self, count: int = 1) -> bool:
        budget = max(int(count or 1), 1)
        return self._resume_debugger(mode="step", step_budget=budget)

    def continue_debugger(self) -> bool:
        return self._resume_debugger(mode="continue", step_budget=None)

    def continue_until_debugger(
        self,
        predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool],
        *,
        label: str,
    ) -> bool:
        return self._resume_debugger(
            mode="continue",
            step_budget=None,
            until_predicate=predicate,
            until_label=label,
        )

    def add_debug_breakpoint(
        self,
        predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool],
        *,
        label: str,
    ) -> int:
        with self._debug_condition:
            self._debug_breakpoint_counter += 1
            breakpoint_id = int(self._debug_breakpoint_counter)
            self._debug_breakpoints.append(
                {
                    "id": breakpoint_id,
                    "label": str(label),
                    "predicate": predicate,
                }
            )
            return breakpoint_id

    def list_debug_breakpoints(self) -> list[dict[str, Any]]:
        with self._debug_condition:
            return [
                {
                    "id": int(item.get("id", 0)),
                    "label": str(item.get("label") or ""),
                }
                for item in self._debug_breakpoints
                if isinstance(item, dict)
            ]

    def clear_debug_breakpoint(self, breakpoint_id: int) -> bool:
        with self._debug_condition:
            original_count = len(self._debug_breakpoints)
            self._debug_breakpoints = [
                item
                for item in self._debug_breakpoints
                if not (isinstance(item, dict) and int(item.get("id", -1)) == int(breakpoint_id))
            ]
            return len(self._debug_breakpoints) != original_count

    def clear_all_debug_breakpoints(self) -> int:
        with self._debug_condition:
            count = len(self._debug_breakpoints)
            self._debug_breakpoints = []
            return count

    @property
    def is_debug_paused(self) -> bool:
        with self._debug_condition:
            return self._debug_paused_event is not None

    @property
    def debug_pause_event(self) -> Dict[str, Any] | None:
        with self._debug_condition:
            if not isinstance(self._debug_paused_event, dict):
                return None
            return dict(self._debug_paused_event)

    @property
    def debug_until_label(self) -> str | None:
        with self._debug_condition:
            return self._debug_until_label

    def _resume_debugger(
        self,
        *,
        mode: str,
        step_budget: int | None,
        until_predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool] | None = None,
        until_label: str | None = None,
    ) -> bool:
        with self._debug_condition:
            if not self._debug_enabled:
                return False
            self._debug_mode = "continue" if str(mode).strip().lower() == "continue" else "step"
            self._debug_step_budget = step_budget
            self._debug_until_predicate = until_predicate
            self._debug_until_label = until_label
            self._debug_paused_event = None
            self._debug_condition.notify_all()
            return True

    def _pause_for_debugger(self, *, event_type: str, payload: Dict[str, Any]) -> None:
        if not self._should_pause_for_debugger(event_type=event_type):
            return

        with self._debug_condition:
            if (
                not self._debug_enabled
                or self._done.is_set()
                or self._cancel_requested.is_set()
            ):
                return
            snapshot = self.get_debug_snapshot()
            if not self._should_pause_on_debug_event(event_type=event_type, payload=payload, snapshot=snapshot):
                return
            self._debug_paused_event = {"type": event_type, **payload}
            self._debug_condition.notify_all()
            while (
                self._debug_paused_event is not None
                and not self._done.is_set()
                and not self._cancel_requested.is_set()
            ):
                self._debug_condition.wait()

    def _should_pause_for_debugger(self, *, event_type: str) -> bool:
        return self._debug_enabled and event_type in {
            "node_completed",
            "agent_turn_completed",
            "llm_call_completed",
            "tool_finished",
            "handoff",
            "handoff_return",
            "final_answer",
            "ask_user",
            "runtime_error",
        }

    def _should_pause_on_debug_event(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> bool:
        if self._debug_until_predicate is not None:
            try:
                if self._debug_until_predicate({"type": event_type, **payload}, snapshot):
                    self._debug_mode = "step"
                    self._debug_step_budget = None
                    self._debug_until_predicate = None
                    self._debug_until_label = None
                    return True
            except Exception:
                self._debug_until_predicate = None
                self._debug_until_label = None

        matched_breakpoint = self._matching_debug_breakpoint(event_type=event_type, payload=payload, snapshot=snapshot)
        if matched_breakpoint is not None:
            payload.setdefault("debug_breakpoint_id", matched_breakpoint["id"])
            payload.setdefault("debug_breakpoint_label", matched_breakpoint["label"])
            return True

        if self._debug_step_budget is not None:
            self._debug_step_budget = max(int(self._debug_step_budget) - 1, 0)
            if self._debug_step_budget == 0:
                self._debug_mode = "step"
                self._debug_step_budget = None
                return True
            return False

        return self._debug_mode != "continue"

    def _matching_debug_breakpoint(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> dict[str, Any] | None:
        event = {"type": event_type, **payload}
        for item in self._debug_breakpoints:
            if not isinstance(item, dict):
                continue
            predicate = item.get("predicate")
            if not callable(predicate):
                continue
            try:
                if predicate(event, snapshot):
                    return item
            except Exception:
                continue
        return None
