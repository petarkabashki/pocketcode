from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

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
        self._prompt_counter = 0
        self._prompt_responses: Dict[str, Optional[str]] = {}
        self._interaction_requests: Dict[str, Dict[str, Any]] = {}
        self._interaction_responses: Dict[str, Optional[Dict[str, Any]]] = {}
        self._thread: threading.Thread | None = None
        self._result: str | None = None
        self._error: Exception | None = None
        self._cancel_reason = "Run cancelled."

    def start(self, target: Any) -> None:
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def emit(self, event_type: str, **payload: Any) -> None:
        self._events.put(RuntimeEvent(event_type=event_type, payload=dict(payload)))

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

    def cancelled(self, *, reason: str, summary: Dict[str, Any] | None = None) -> None:
        self._result = ""
        self.emit("run_cancelled", reason=reason, summary=dict(summary or {}))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()

    def fail(self, error: Exception) -> None:
        self._error = error
        self.emit("run_failed", error=str(error))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()

    def cancel(self, reason: str = "Run cancelled by user.") -> bool:
        if self._done.is_set() or self._cancel_requested.is_set():
            return False
        self._cancel_reason = str(reason or "Run cancelled.")
        self._cancel_requested.set()
        self.emit("run_cancel_requested", reason=self._cancel_reason)
        with self._prompt_condition:
            self._prompt_condition.notify_all()
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
