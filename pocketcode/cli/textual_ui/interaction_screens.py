from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, SelectionList, Static
from textual.widgets.option_list import Option

from pocketcode.core.user_interaction import normalize_interaction_request


def _default_tokens(default: Any) -> list[str]:
    if default is None:
        return []
    if isinstance(default, (list, tuple, set)):
        return [str(item).strip() for item in default if str(item).strip()]
    text = str(default).strip()
    return [text] if text else []


class PromptInputScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("enter", "submit", "Submit", show=False),
    ]

    DEFAULT_CSS = """
    PromptInputScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #prompt-input-modal {
        width: 76;
        max-width: 92vw;
        height: auto;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #prompt-input-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #prompt-input-prompt {
        color: #f8fafc;
        margin-bottom: 1;
    }

    #prompt-input-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #prompt-input-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        prompt: str,
        help_text: str,
        placeholder: str,
        initial_text: str = "",
        submit_label: str = "Submit",
    ) -> None:
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._help_text = help_text
        self._placeholder = placeholder
        self._initial_text = initial_text
        self._submit_label = submit_label

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-input-modal"):
            yield Static(self._title, id="prompt-input-title")
            yield Static(self._prompt, id="prompt-input-prompt")
            yield Static(self._help_text, id="prompt-input-help")
            yield Input(value=self._initial_text, placeholder=self._placeholder, id="prompt-input-field")
            with Horizontal(id="prompt-input-actions", classes="button-row"):
                yield Button(self._submit_label, id="prompt-input-submit", variant="primary")
                yield Button("Cancel", id="prompt-input-cancel")

    def on_mount(self) -> None:
        field = self.query_one("#prompt-input-field", Input)
        field.focus()
        field.cursor_position = len(field.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self.dismiss(self.query_one("#prompt-input-field", Input).value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt-input-field":
            self.action_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "prompt-input-submit":
            self.action_submit()
        elif button_id == "prompt-input-cancel":
            self.action_cancel()


class InteractionControlsScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("enter", "submit", "Submit", show=False),
    ]

    DEFAULT_CSS = """
    InteractionControlsScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #interaction-controls-modal {
        width: 84;
        max-width: 94vw;
        height: 28;
        max-height: 88vh;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #interaction-controls-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #interaction-controls-prompt {
        color: #f8fafc;
        margin-bottom: 1;
    }

    #interaction-controls-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #interaction-controls-options,
    #interaction-controls-checklist {
        height: 1fr;
        border: round #334155;
        background: #0b1220;
        margin-bottom: 1;
    }

    #interaction-controls-actions {
        height: auto;
    }
    """

    def __init__(self, *, request: dict[str, Any]) -> None:
        super().__init__()
        self._request = normalize_interaction_request(request)
        self._selected_values = {
            token
            for token in _default_tokens(self._request.default)
        }

    def compose(self) -> ComposeResult:
        help_text = self._request.description or self._default_help_text()
        with Vertical(id="interaction-controls-modal"):
            yield Static("Input Required", id="interaction-controls-title")
            yield Static(self._request.prompt, id="interaction-controls-prompt")
            yield Static(help_text, id="interaction-controls-help")
            if self._request.kind == "checklist":
                yield SelectionList(id="interaction-controls-checklist")
            else:
                yield OptionList(id="interaction-controls-options")
            with Horizontal(id="interaction-controls-actions", classes="button-row"):
                yield Button(self._submit_label(), id="interaction-controls-submit", variant="primary")
                yield Button("Cancel", id="interaction-controls-cancel")

    def on_mount(self) -> None:
        if self._request.kind == "checklist":
            checklist = self.query_one("#interaction-controls-checklist", SelectionList)
            checklist.add_options(
                [
                    (option.label, option.id, option.id in self._selected_values or str(option.value) in self._selected_values)
                    for option in self._request.options
                ]
            )
            if checklist.option_count and checklist.highlighted is None:
                checklist.highlighted = 0
            checklist.focus()
            return

        option_list = self.query_one("#interaction-controls-options", OptionList)
        option_list.add_options(
            [
                Option(
                    option.label + (f" [{option.description}]" if option.description else ""),
                    id=option.id,
                )
                for option in self._request.options
            ]
        )
        preferred_id = next(iter(self._selected_values), None)
        if preferred_id is not None:
            highlighted = next(
                (index for index, option in enumerate(self._request.options) if option.id == preferred_id or str(option.value) == preferred_id),
                0,
            )
            option_list.highlighted = highlighted
        elif option_list.option_count:
            option_list.highlighted = 0
        option_list.focus()

    def _default_help_text(self) -> str:
        if self._request.kind == "checklist":
            return "Use arrows and Space to toggle options, then apply."
        return "Use arrows to choose an option, then press Enter."

    def _submit_label(self) -> str:
        return self._request.submit_label or ("Apply" if self._request.kind == "checklist" else "Choose")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        if self._request.kind == "checklist":
            self.dismiss(",".join(sorted(self._selected_values)))
            return

        option_list = self.query_one("#interaction-controls-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted >= len(self._request.options):
            return
        self.dismiss(self._request.options[highlighted].id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "interaction-controls-submit":
            self.action_submit()
        elif button_id == "interaction-controls-cancel":
            self.action_cancel()

    def on_key(self, event) -> None:
        if self._request.kind != "checklist":
            return
        checklist = self.query_one("#interaction-controls-checklist", SelectionList)
        if event.key == "space" and self.focused is checklist:
            event.prevent_default()
            event.stop()
            if checklist.highlighted is None:
                checklist.highlighted = 0
            checklist.action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "interaction-controls-options" and event.option_id is not None:
            self.dismiss(str(event.option_id))

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        if event.selection_list.id != "interaction-controls-checklist" or event.selection_list.disabled:
            return
        option_index = getattr(event, "selection_index", getattr(event, "index", None))
        if option_index is None:
            return
        option = event.selection_list.get_option_at_index(option_index)
        value = str(option.value)
        if value in event.selection_list.selected:
            self._selected_values.add(value)
        else:
            self._selected_values.discard(value)
