from __future__ import annotations

from typing import Any, Dict, Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, SelectionList, Static
from textual.widgets.option_list import Option

from .shared import LOADING_OPTION, PickerOption


class AssetPickerScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("escape", "cancel", "Close", show=False),
        Binding("enter", "submit", "Choose", show=False),
    ]

    DEFAULT_CSS = """
    AssetPickerScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #asset-picker-modal {
        width: 76;
        max-width: 90vw;
        height: 24;
        max-height: 85vh;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #asset-picker-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #asset-picker-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #asset-picker-filter {
        margin-bottom: 1;
    }

    #asset-picker-options {
        height: 1fr;
        border: round #334155;
        background: #0b1220;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None = None,
        help_text: str = "Use arrows to move, Enter to select, Esc to close.",
        empty_message: str = "No matching options.",
    ) -> None:
        super().__init__()
        self._title = title
        self._options = tuple(options)
        self._current_value = current_value
        self._help_text = help_text
        self._empty_message = empty_message
        self._visible_values: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="asset-picker-modal"):
            yield Static(self._title, id="asset-picker-title")
            yield Static(self._help_text, id="asset-picker-help")
            yield Input(placeholder="Filter options...", id="asset-picker-filter")
            yield OptionList(id="asset-picker-options")

    def on_mount(self) -> None:
        self._refresh_options()
        self.query_one("#asset-picker-filter", Input).focus()

    def _matching_options(self, term: str) -> list[PickerOption]:
        lowered = term.strip().lower()
        if not lowered:
            return list(self._options)
        matches: list[PickerOption] = []
        for option in self._options:
            haystack = " ".join(
                part
                for part in [option.label, option.value, option.description, option.search_text]
                if part
            ).lower()
            if lowered in haystack:
                matches.append(option)
        return matches

    def _refresh_options(self) -> None:
        filter_value = self.query_one("#asset-picker-filter", Input).value
        option_list = self.query_one("#asset-picker-options", OptionList)
        matching_options = self._matching_options(filter_value)
        self._visible_values = [option.value for option in matching_options]
        option_list.clear_options()
        if not matching_options:
            option_list.add_option(Option(self._empty_message, disabled=True))
            option_list.highlighted = 0
            return

        option_list.add_options(
            [
                Option(
                    f"{'* ' if option.value == self._current_value else '  '}{option.label}"
                    + (f" [{option.description}]" if option.description else ""),
                )
                for option in matching_options
            ]
        )
        try:
            highlight_index = self._visible_values.index(self._current_value) if self._current_value is not None else 0
        except ValueError:
            highlight_index = 0
        option_list.highlighted = highlight_index

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        option_list = self.query_one("#asset-picker-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted >= len(self._visible_values):
            return
        self.dismiss(self._visible_values[highlighted])

    def action_cursor_up(self) -> None:
        option_list = self.query_one("#asset-picker-options", OptionList)
        if self._visible_values:
            option_list.action_cursor_up()

    def action_cursor_down(self) -> None:
        option_list = self.query_one("#asset-picker-options", OptionList)
        if self._visible_values:
            option_list.action_cursor_down()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "asset-picker-filter":
            self._refresh_options()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "asset-picker-filter":
            self.action_submit()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "asset-picker-options":
            return
        option_index = getattr(event, "option_index", None)
        if option_index is not None and option_index < len(self._visible_values):
            self.dismiss(str(self._visible_values[option_index]))


class ToolSelectionScreen(ModalScreen[dict[str, Any] | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("ctrl+s", "apply", "Apply", show=False),
        Binding("ctrl+up", "focus_filter", "Focus Search", show=False),
        Binding("ctrl+down", "focus_list", "Focus List", show=False),
    ]

    DEFAULT_CSS = """
    ToolSelectionScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #tool-picker-modal {
        width: 88;
        max-width: 95vw;
        height: 30;
        max-height: 90vh;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #tool-picker-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #tool-picker-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #tool-picker-filter {
        margin-bottom: 1;
    }

    #tool-picker-list {
        height: 1fr;
        border: round #334155;
        background: #0b1220;
        margin-bottom: 1;
    }

    #tool-picker-actions {
        height: auto;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        tools: Iterable[PickerOption],
        selected_values: Iterable[str],
        help_text: str = "Filter tools, toggle with Space, then choose Apply.",
        empty_message: str = "No matching tools.",
        filter_placeholder: str = "Filter tools...",
        grouped_values: Dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._tools = tuple(tools)
        self._selected_values = set(str(value) for value in selected_values)
        self._help_text = help_text
        self._empty_message = empty_message
        self._filter_placeholder = filter_placeholder
        self._grouped_values = {
            str(group_value): tuple(str(item) for item in grouped_items)
            for group_value, grouped_items in (grouped_values or {}).items()
        }

    def compose(self) -> ComposeResult:
        with Vertical(id="tool-picker-modal"):
            yield Static(self._title, id="tool-picker-title")
            yield Static(self._help_text, id="tool-picker-help")
            yield Input(placeholder=self._filter_placeholder, id="tool-picker-filter")
            yield SelectionList(id="tool-picker-list")
            with Horizontal(id="tool-picker-actions", classes="button-row"):
                yield Button("Apply", id="tool-picker-apply", variant="primary")
                yield Button("Reset", id="tool-picker-reset")
                yield Button("Save as Default", id="tool-picker-save-default")
                yield Button("Cancel", id="tool-picker-cancel")

    def on_mount(self) -> None:
        self._refresh_tools()
        self.query_one("#tool-picker-filter", Input).focus()

    def _matching_tools(self, term: str) -> list[PickerOption]:
        lowered = term.strip().lower()
        if not lowered:
            return list(self._tools)
        matches: list[PickerOption] = []
        for option in self._tools:
            haystack = " ".join(
                part
                for part in (option.label, option.value, option.description, option.search_text)
                if part
            ).lower()
            if lowered in haystack:
                matches.append(option)
        return matches

    def _refresh_tools(
        self,
        *,
        preferred_highlighted_value: str | None = None,
        preferred_highlighted_index: int | None = None,
    ) -> None:
        filter_value = self.query_one("#tool-picker-filter", Input).value
        selection_list = self.query_one("#tool-picker-list", SelectionList)
        matching_tools = self._matching_tools(filter_value)
        highlighted_index = selection_list.highlighted
        highlighted_value: str | None = preferred_highlighted_value
        if highlighted_value is None and highlighted_index is not None and selection_list.option_count:
            try:
                highlighted_value = str(selection_list.get_option_at_index(highlighted_index).value)
            except Exception:
                highlighted_value = None
        if preferred_highlighted_index is None:
            preferred_highlighted_index = highlighted_index
        preserve_list_focus = self.focused is selection_list
        selection_list.clear_options()
        if not matching_tools:
            selection_list.add_options([(self._empty_message, LOADING_OPTION, False)])
            selection_list.disabled = True
            selection_list.highlighted = 0
            if preserve_list_focus:
                selection_list.focus()
            return
        selection_list.disabled = False
        selection_list.add_options(
            [
                (tool.label, tool.value, tool.value in self._selected_values)
                for tool in matching_tools
            ]
        )
        next_highlighted = None
        if highlighted_value is not None:
            next_highlighted = next(
                (index for index, tool in enumerate(matching_tools) if tool.value == highlighted_value),
                None,
            )
        if next_highlighted is None and preferred_highlighted_index is not None:
            next_highlighted = min(preferred_highlighted_index, len(matching_tools) - 1)
        selection_list.highlighted = 0 if next_highlighted is None else next_highlighted
        if preserve_list_focus:
            selection_list.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        self.dismiss({"action": "apply", "values": sorted(self._selected_values)})

    def action_reset(self) -> None:
        self.dismiss({"action": "reset"})

    def action_save_default(self) -> None:
        self.dismiss({"action": "save_default", "values": sorted(self._selected_values)})

    def action_focus_filter(self) -> None:
        self.query_one("#tool-picker-filter", Input).focus()

    def action_focus_list(self) -> None:
        selection_list = self.query_one("#tool-picker-list", SelectionList)
        if selection_list.option_count and selection_list.highlighted is None:
            selection_list.highlighted = 0
        selection_list.focus()

    def _toggle_highlighted_selection(self) -> None:
        selection_list = self.query_one("#tool-picker-list", SelectionList)
        if selection_list.disabled or not selection_list.option_count:
            return
        if selection_list.highlighted is None:
            selection_list.highlighted = 0
        selection_list.action_select()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tool-picker-filter":
            self._refresh_tools()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "tool-picker-apply":
            self.action_apply()
        elif button_id == "tool-picker-reset":
            self.action_reset()
        elif button_id == "tool-picker-save-default":
            self.action_save_default()
        elif button_id == "tool-picker-cancel":
            self.action_cancel()

    def on_key(self, event) -> None:
        if event.key == "space" and self.focused is self.query_one("#tool-picker-list", SelectionList):
            event.prevent_default()
            event.stop()
            self._toggle_highlighted_selection()

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        if event.selection_list.id != "tool-picker-list" or event.selection_list.disabled:
            return
        option_index = getattr(event, "selection_index", getattr(event, "index", None))
        if option_index is None:
            return
        option = event.selection_list.get_option_at_index(option_index)
        value = str(option.value)
        if value == LOADING_OPTION:
            return
        if value in self._grouped_values:
            if value in event.selection_list.selected:
                self._selected_values.add(value)
                self._selected_values.update(self._grouped_values[value])
            else:
                self._selected_values.discard(value)
                for member_value in self._grouped_values[value]:
                    self._selected_values.discard(member_value)
        else:
            if value in event.selection_list.selected:
                self._selected_values.add(value)
            else:
                self._selected_values.discard(value)
        self._sync_group_selection_values()
        if self.is_mounted:
            self._refresh_tools(
                preferred_highlighted_value=value,
                preferred_highlighted_index=option_index,
            )

    def _sync_group_selection_values(self) -> None:
        for group_value, member_values in self._grouped_values.items():
            if member_values and all(member_value in self._selected_values for member_value in member_values):
                self._selected_values.add(group_value)
            else:
                self._selected_values.discard(group_value)
