from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional


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
        self._prompt_condition = threading.Condition()
        self._prompt_counter = 0
        self._prompt_responses: Dict[str, Optional[str]] = {}
        self._thread: threading.Thread | None = None
        self._result: str | None = None
        self._error: Exception | None = None

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
        with self._prompt_condition:
            self._prompt_counter += 1
            prompt_id = f"prompt-{self._prompt_counter}"
            self._prompt_responses[prompt_id] = None
        self.emit("user_input_requested", prompt_id=prompt_id, prompt=prompt)
        with self._prompt_condition:
            while self._prompt_responses.get(prompt_id) is None and not self._done.is_set():
                self._prompt_condition.wait()
            response = self._prompt_responses.pop(prompt_id, None)
        return "" if response is None else response

    def resolve_user_input(self, prompt_id: str, value: str) -> bool:
        with self._prompt_condition:
            if prompt_id not in self._prompt_responses:
                return False
            self._prompt_responses[prompt_id] = value
            self._prompt_condition.notify_all()
        self.emit("user_input_received", prompt_id=prompt_id)
        return True

    def complete(self, *, result: str, summary: Dict[str, Any] | None = None) -> None:
        self._result = result
        self.emit("run_completed", output=result, summary=dict(summary or {}))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()

    def fail(self, error: Exception) -> None:
        self._error = error
        self.emit("run_failed", error=str(error))
        self._done.set()
        with self._prompt_condition:
            self._prompt_condition.notify_all()

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
