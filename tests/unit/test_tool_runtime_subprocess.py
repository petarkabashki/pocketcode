from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import Any

from pocketcode.core.interfaces import BaseTool
from pocketcode.core.tool_runtime import ToolRuntime


class _ManagedSleepTool(BaseTool):
    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "managed_sleep"

    @property
    def description(self) -> str:
        return "Sleep in a managed subprocess for testing."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sleep_seconds": {"type": "number"},
            },
            "required": ["sleep_seconds"],
        }

    @property
    def execution_mode(self) -> str:
        return "managed_subprocess"

    @property
    def timeout_seconds(self) -> float | None:
        return self._timeout_seconds

    def spawn_subprocess(self, **kwargs) -> Any:
        sleep_seconds = float(kwargs["sleep_seconds"])
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import sys,time; "
                    "time.sleep(float(sys.argv[1])); "
                    "print('done')"
                ),
                str(sleep_seconds),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

    def handle_subprocess_result(self, *, returncode: int, stdout: str, stderr: str, **kwargs) -> Any:
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    def execute(self, **kwargs) -> Any:
        raise AssertionError("managed_subprocess tools should not run via execute()")


def _make_runtime(tool: BaseTool) -> ToolRuntime:
    return ToolRuntime(
        tools={tool.name: tool},
        require_confirmation=False,
    )


class TestManagedSubprocessToolRuntime:
    def test_managed_subprocess_tool_succeeds(self):
        runtime = _make_runtime(_ManagedSleepTool())
        store: dict[str, Any] = {}

        result = runtime.execute_tool("managed_sleep", {"sleep_seconds": 0.01}, store)

        assert result["success"] is True
        assert result["returncode"] == 0
        assert result["stdout"].strip() == "done"
        assert "active_tool_execution" not in store

    def test_managed_subprocess_tool_can_be_cancelled(self):
        runtime = _make_runtime(_ManagedSleepTool())
        cancel_state = {"value": False}
        store: dict[str, Any] = {
            "run_cancel_requested": lambda: cancel_state["value"],
            "runtime_event_handler": lambda *_args, **_kwargs: None,
        }

        def trigger_cancel() -> None:
            time.sleep(0.1)
            cancel_state["value"] = True

        thread = threading.Thread(target=trigger_cancel, daemon=True)
        thread.start()
        started_at = time.monotonic()

        result = runtime.execute_tool("managed_sleep", {"sleep_seconds": 5}, store)
        elapsed = time.monotonic() - started_at

        assert result["success"] is False
        assert result["cancelled"] is True
        assert elapsed < 2.0
        assert "active_tool_execution" not in store

    def test_managed_subprocess_tool_timeout_is_reported(self):
        runtime = _make_runtime(_ManagedSleepTool(timeout_seconds=0.1))
        store: dict[str, Any] = {}

        result = runtime.execute_tool("managed_sleep", {"sleep_seconds": 5}, store)

        assert result["success"] is False
        assert result["timed_out"] is True
        assert "timeout" in result["error"].lower()
        assert "active_tool_execution" not in store