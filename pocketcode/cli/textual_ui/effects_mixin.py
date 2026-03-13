from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

from pocketcode.cli.command_handler import handle_command
from pocketcode.cli.user_interaction import parse_interaction_response


class TextualAppEffectsMixin:
    async def _execute_command_effect(self, command_input: str) -> tuple[str, bool]:
        return self._run_command_capture(command_input)

    def _run_command_capture(self, command_input: str) -> tuple[str, bool]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = handle_command(
                command_input=command_input,
                engine=self._engine,
                cli_context=self._cli_context,
                active_run=self._active_run,
            )

        text = output.getvalue().strip()
        should_exit = result == "__exit__"
        return text, should_exit

    def _start_request_effect(self, user_input: str, *, debug: bool = False) -> None:
        self._active_run = self._engine.start_request(
            user_input,
            self._cli_context,
            bridge_user_input=True,
            debug=bool(debug),
        )

    def _resolve_pending_input_effect(
        self,
        text: str,
        pending_input_request: dict[str, Any],
    ) -> tuple[bool, str]:
        if self._active_run is None:
            return False, ""
        request_id = str(
            pending_input_request.get("request_id")
            or pending_input_request.get("prompt_id")
            or ""
        )
        if pending_input_request.get("type") == "interaction_requested":
            response_payload = parse_interaction_response(pending_input_request, text)
            labels = response_payload.get("labels")
            if isinstance(labels, list) and labels:
                display_text = ", ".join(str(item) for item in labels)
            else:
                display_text = str(response_payload.get("label") or response_payload.get("value") or text)
            self._write_user(display_text)
            return bool(request_id) and self._active_run.resolve_interaction(request_id, response_payload), display_text

        self._write_user(text)
        return bool(request_id) and self._active_run.resolve_user_input(request_id, text), str(text)

    def _drain_active_run_effect(self) -> list[dict[str, Any]]:
        if self._active_run is None:
            return []
        return list(self._active_run.drain_events() or [])
