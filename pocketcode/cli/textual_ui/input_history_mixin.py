from __future__ import annotations

from textual.widgets import Input

from .shared import PickerOption

MAX_ENTRY_HISTORY = 100


def _history_label(text: str, *, index: int) -> tuple[str, str]:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    first_line = lines[0] if lines else str(text).strip()
    if len(first_line) > 72:
        first_line = first_line[:69] + "..."
    description = f"Entry {index}"
    if len(lines) > 1:
        description = f"{description}, {len(lines)} lines"
    return first_line or f"Entry {index}", description


class TextualAppInputHistoryMixin:
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "debugger-inline-value-input":
            self._debugger_inline_breakpoint_value = event.value
        elif event.input.id in {"inline-prompt-input-chat", "inline-prompt-input-run"}:
            self._inline_prompt_text_value = event.value

    def action_pick_history(self) -> None:
        if getattr(self, "_runtime_state", None) and self._runtime_state.active_modal_kind is not None:
            return
        if not self._entry_history:
            self._write_info("No previous entries are available yet.")
            return
        input_widget = self.query_one("#main-input", Input)
        options = []
        reversed_history = list(reversed(self._entry_history))
        for offset, text in enumerate(reversed_history, start=1):
            label, description = _history_label(text, index=len(self._entry_history) - offset + 1)
            options.append(
                PickerOption(
                    value=text,
                    label=label,
                    description=description,
                    search_text=text,
                )
            )
        self._show_picker(
            title="Entry History",
            options=tuple(options),
            current_value=input_widget.value if input_widget.value in self._entry_history else None,
            on_select=self._apply_history_selection,
            help_text="Choose a previous entry to load it back into the main input.",
            empty_message="No previous entries.",
        )

    def action_history_previous(self) -> None:
        if self._runtime_state.active_modal_kind is not None:
            return
        input_widget = self.query_one("#main-input", Input)
        if not self._entry_history:
            return
        if self._entry_history_cursor is None:
            self._entry_history_draft = input_widget.value
            self._entry_history_cursor = len(self._entry_history) - 1
        elif self._entry_history_cursor > 0:
            self._entry_history_cursor -= 1
        self._set_main_input_value(self._entry_history[self._entry_history_cursor], preserve_history_cursor=True)

    def action_history_next(self) -> None:
        if self._runtime_state.active_modal_kind is not None:
            return
        if self._entry_history_cursor is None:
            return
        if self._entry_history_cursor < len(self._entry_history) - 1:
            self._entry_history_cursor += 1
            next_value = self._entry_history[self._entry_history_cursor]
        else:
            self._entry_history_cursor = None
            next_value = self._entry_history_draft
            self._entry_history_draft = ""
        self._set_main_input_value(next_value, preserve_history_cursor=self._entry_history_cursor is not None)

    def _apply_history_selection(self, value: str) -> None:
        self._entry_history_cursor = None
        self._entry_history_draft = ""
        self._set_main_input_value(value, preserve_history_cursor=False)

    def _set_main_input_value(self, value: str, *, preserve_history_cursor: bool) -> None:
        input_widget = self.query_one("#main-input", Input)
        self._suppress_history_input_reset = True
        input_widget.value = str(value)
        input_widget.cursor_position = len(input_widget.value)
        self.call_after_refresh(self._clear_history_input_reset)
        if not preserve_history_cursor:
            self._entry_history_cursor = None
            self._entry_history_draft = ""
        input_widget.focus()

    def _clear_history_input_reset(self) -> None:
        self._suppress_history_input_reset = False

    def _remember_entry_history(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        if self._entry_history and self._entry_history[-1] == normalized:
            self._entry_history_cursor = None
            self._entry_history_draft = ""
            return
        self._entry_history.append(normalized)
        self._entry_history = self._entry_history[-MAX_ENTRY_HISTORY:]
        self._entry_history_cursor = None
        self._entry_history_draft = ""
        if hasattr(self._engine, "set_last_used_entry_history"):
            self._engine.set_last_used_entry_history(list(self._entry_history))
