from __future__ import annotations

import asyncio
import io
import logging
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Input,
    OptionList,
    Select,
    SelectionList,
    Static,
    Switch,
    TextArea,
)
from textual.widgets.option_list import Option

from pocketcode.cli.command_handler import _skill_group_name, handle_command, list_command_suggestions
from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import (
    describe_interaction_request,
    interaction_placeholder,
    parse_interaction_response,
)
from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.run_handle import RunHandle

logger = logging.getLogger(__name__)

NO_LLM = "__none__"
NO_MODE = "__none_mode__"
UNSET_OPTION = "__unset__"
INHERIT_POLICY = "__inherit__"
LOADING_OPTION = "__loading__"
MAX_OUTPUT_LINES = 400
SKILL_GROUP_PREFIX = "__skill_group__:"
VIEW_TITLES = {
    "control": "Control Center",
    "run": "Run Inspector",
}
THEME_OPTIONS = {
    "ocean": "Ocean",
    "forest": "Forest",
    "ember": "Ember",
}
WORKSPACE_MODES = {
    "balanced": {"label": "Balanced", "view": "chat", "right": True},
    "chat_focus": {"label": "Chat Focus", "view": "chat", "right": True},
    "control_desk": {"label": "Control Desk", "view": "control", "right": True},
    "minimal": {"label": "Minimal", "view": "chat", "right": False},
    "review": {"label": "Review", "view": "run", "right": True},
}


def _tool_group_name(tool_name: str) -> str:
    cleaned = str(tool_name).strip()
    if not cleaned:
        return "other"
    if "::" in cleaned:
        return cleaned.split("::", 1)[0]
    if "." in cleaned:
        return cleaned.split(".", 1)[0]
    return "other"


def _build_stats_text(status: Dict[str, Any]) -> str:
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
    llm_usage = run_summary.get("llm_usage", {}) if isinstance(run_summary, dict) else {}
    cost = run_summary.get("llm_cost_usd", 0.0) if isinstance(run_summary, dict) else 0.0
    session_confirm = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or "inherit"
    return (
        f"Tokens in={llm_usage.get('prompt_tokens', 0)} "
        f"out={llm_usage.get('completion_tokens', 0)} total={llm_usage.get('total_tokens', 0)} | "
        f"Cost=${float(cost):.6f} | Session confirm={session_confirm}"
    )


def _resolve_status_display_parts(status: Dict[str, Any]) -> tuple[str, str, str, str]:
    runtime_flow = status.get("runtime_flow") or "internal-flow"
    run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}

    current_llm_profile = str(
        status.get("selected_llm_profile")
        or status.get("global_llm_override")
        or status.get("default_llm_profile")
        or "none"
    )
    last_llm_profile = run_summary.get("current_llm_profile") if isinstance(run_summary, dict) else None
    current_llm_model = (
        run_summary.get("current_llm_model")
        if isinstance(run_summary, dict) and last_llm_profile == current_llm_profile
        else "-"
    )
    active_agent = (
        status.get("selected_agent")
        or status.get("agent")
        or status.get("active_agent")
        or status.get("active_agent_profile")
        or "none"
    )
    return runtime_flow, active_agent, current_llm_profile, current_llm_model


def _build_status_text(status: Dict[str, Any], current_view: str) -> str:
    runtime_flow, active_agent, current_llm_profile, current_llm_model = _resolve_status_display_parts(status)
    return f"Runtime flow: {runtime_flow} | Agent: {active_agent} | LLM: {current_llm_profile} ({current_llm_model})"


def _build_header_summary_text(status: Dict[str, Any]) -> str:
    runtime_flow, _, _, _ = _resolve_status_display_parts(status)
    return f"Runtime flow: {runtime_flow}"


def _build_header_agent_text(status: Dict[str, Any]) -> str:
    _, active_agent, _, _ = _resolve_status_display_parts(status)
    return f"Agent: {active_agent}"


def _build_header_llm_text(status: Dict[str, Any]) -> str:
    _, _, current_llm_profile, current_llm_model = _resolve_status_display_parts(status)
    return f"LLM: {current_llm_profile} ({current_llm_model})"


def _build_view_title_text(view_name: str) -> str:
    return VIEW_TITLES.get(view_name, "")


def _build_profile_editor_hint(active_profile: Any) -> str:
    if active_profile is None:
        return "Select an agent to edit agent settings."
    if active_profile.source == "workspace":
        return f"Editing workspace agent '{active_profile.name}'. Save persists tools, prompts, and LLM."
    return f"Agent '{active_profile.name}' is plugin/synthesised. Clone it to a workspace agent to edit."


def _dump_yaml_text(payload: Dict[str, Any]) -> str:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()
    return text or "{}"


def _load_yaml_mapping(text: str, *, label: str) -> Dict[str, Any]:
    loaded = yaml.safe_load(text) if text.strip() else {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be a YAML mapping.")
    return loaded


def _trim_output_lines(lines: list[str], max_lines: int) -> tuple[list[str], int]:
    if max_lines <= 0:
        return [], len(lines)
    overflow = max(0, len(lines) - max_lines)
    if overflow == 0:
        return list(lines), 0
    return list(lines[overflow:]), overflow


def _build_output_text(lines: list[str], trimmed_line_count: int) -> str:
    if trimmed_line_count <= 0:
        return "\n".join(lines)
    notice = f"info> [output history trimmed: showing last {len(lines)} lines]"
    return "\n".join([notice, *lines]) if lines else notice


@dataclass(frozen=True)
class SelectViewState:
    options: tuple[tuple[str, str], ...]
    value: str


@dataclass(frozen=True)
class TextualUIState:
    theme_name: str
    current_view: str
    right_panel_visible: bool
    status_text: str
    header_agent_text: str
    header_llm_text: str
    view_title_text: str
    workspace_mode_select: SelectViewState
    theme_select: SelectViewState
    profile_select: SelectViewState
    llm_select: SelectViewState
    session_confirm_select: SelectViewState
    auto_confirm_tools: bool
    inspector_summary_text: str
    inspector_context_text: str
    skill_list_options: tuple[tuple[str, str, bool], ...]
    inspector_tools_text: str
    inspector_prompts_text: str
    profile_list_names: tuple[str, ...]
    profile_list_labels: tuple[str, ...]
    run_preview_text: str


@dataclass(frozen=True)
class PickerOption:
    value: str
    label: str
    description: str = ""
    search_text: str = ""


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
                    id=option.value,
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
        if event.option_list.id != "asset-picker-options" or event.option_id is None:
            return
        self.dismiss(str(event.option_id))


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


class ToolPolicyEditorScreen(ModalScreen[dict[str, str] | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("ctrl+s", "apply", "Apply", show=False),
    ]

    DEFAULT_CSS = """
    ToolPolicyEditorScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #text-editor-modal {
        width: 96;
        max-width: 95vw;
        height: 32;
        max-height: 90vh;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #text-editor-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #text-editor-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #text-editor-body {
        height: 1fr;
        margin-bottom: 1;
    }

    #text-editor-actions {
        height: auto;
    }
    """

    def __init__(self, *, title: str, help_text: str, initial_text: str) -> None:
        super().__init__()
        self._title = title
        self._help_text = help_text
        self._initial_text = initial_text

    def compose(self) -> ComposeResult:
        with Vertical(id="text-editor-modal"):
            yield Static(self._title, id="text-editor-title")
            yield Static(self._help_text, id="text-editor-help")
            yield TextArea(self._initial_text, id="text-editor-body")
            with Horizontal(id="text-editor-actions", classes="button-row"):
                yield Button("Apply", id="tool-policy-apply", variant="primary")
                yield Button("Reset", id="tool-policy-reset")
                yield Button("Save as Default", id="tool-policy-save-default")
                yield Button("Cancel", id="tool-policy-cancel")

    def on_mount(self) -> None:
        self.query_one("#text-editor-body", TextArea).focus()

    def _dismiss_with_action(self, action: str) -> None:
        self.dismiss({"action": action, "text": self.query_one("#text-editor-body", TextArea).text})

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        self._dismiss_with_action("apply")

    def action_reset(self) -> None:
        self._dismiss_with_action("reset")

    def action_save_default(self) -> None:
        self._dismiss_with_action("save_default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "tool-policy-apply":
            self.action_apply()
        elif button_id == "tool-policy-reset":
            self.action_reset()
        elif button_id == "tool-policy-save-default":
            self.action_save_default()
        elif button_id == "tool-policy-cancel":
            self.action_cancel()

class NameInputScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("enter", "submit", "Submit", show=False),
    ]

    DEFAULT_CSS = """
    NameInputScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #name-input-modal {
        width: 62;
        max-width: 90vw;
        height: auto;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #name-input-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #name-input-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #name-input-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, *, title: str, placeholder: str, help_text: str) -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._help_text = help_text

    def compose(self) -> ComposeResult:
        with Vertical(id="name-input-modal"):
            yield Static(self._title, id="name-input-title")
            yield Static(self._help_text, id="name-input-help")
            yield Input(placeholder=self._placeholder, id="name-input-field")
            with Horizontal(id="name-input-actions", classes="button-row"):
                yield Button("Submit", id="name-input-submit", variant="primary")
                yield Button("Cancel", id="name-input-cancel")

    def on_mount(self) -> None:
        self.query_one("#name-input-field", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        value = self.query_one("#name-input-field", Input).value.strip()
        if not value:
            return
        self.dismiss(value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "name-input-field":
            self.action_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "name-input-submit":
            self.action_submit()
        elif button_id == "name-input-cancel":
            self.action_cancel()


class TextEditorScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("ctrl+s", "submit", "Save", show=False),
    ]

    DEFAULT_CSS = """
    TextEditorScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #text-editor-modal {
        width: 96;
        max-width: 95vw;
        height: 32;
        max-height: 90vh;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #text-editor-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #text-editor-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #text-editor-body {
        height: 1fr;
        margin-bottom: 1;
    }

    #text-editor-actions {
        height: auto;
    }
    """

    def __init__(self, *, title: str, help_text: str, initial_text: str) -> None:
        super().__init__()
        self._title = title
        self._help_text = help_text
        self._initial_text = initial_text

    def compose(self) -> ComposeResult:
        with Vertical(id="text-editor-modal"):
            yield Static(self._title, id="text-editor-title")
            yield Static(self._help_text, id="text-editor-help")
            yield TextArea(self._initial_text, id="text-editor-body")
            with Horizontal(id="text-editor-actions", classes="button-row"):
                yield Button("Save", id="text-editor-save", variant="primary")
                yield Button("Cancel", id="text-editor-cancel")

    def on_mount(self) -> None:
        self.query_one("#text-editor-body", TextArea).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self.dismiss(self.query_one("#text-editor-body", TextArea).text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "text-editor-save":
            self.action_submit()
        elif button_id == "text-editor-cancel":
            self.action_cancel()


class SystemSettingsScreen(ModalScreen[dict[str, str | None] | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("ctrl+s", "apply", "Apply", show=False),
    ]

    DEFAULT_CSS = """
    SystemSettingsScreen {
        align: center middle;
        background: rgba(2, 6, 23, 0.72);
    }

    #system-settings-modal {
        width: 84;
        max-width: 95vw;
        height: auto;
        border: round #0ea5e9;
        background: #020617;
        padding: 1;
    }

    #system-settings-title {
        color: #e0f2fe;
        text-style: bold;
        margin-bottom: 1;
    }

    #system-settings-help {
        color: #cbd5e1;
        margin-bottom: 1;
    }

    #system-settings-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        theme_name: str,
        workspace_mode: str,
        default_agent: str | None,
        default_llm_profile: str | None,
        available_agents: Iterable[str],
        available_llm_profiles: Iterable[str],
    ) -> None:
        super().__init__()
        self._theme_name = str(theme_name)
        self._workspace_mode = str(workspace_mode)
        self._default_agent = str(default_agent) if default_agent else UNSET_OPTION
        self._default_llm_profile = str(default_llm_profile) if default_llm_profile else UNSET_OPTION
        self._available_agents = tuple(str(name) for name in available_agents)
        self._available_llm_profiles = tuple(str(name) for name in available_llm_profiles)

    def compose(self) -> ComposeResult:
        with Vertical(id="system-settings-modal"):
            yield Static("System Settings", id="system-settings-title")
            yield Static(
                "Apply saves these defaults to pocketcode.yml and updates the running UI/runtime.",
                id="system-settings-help",
            )
            yield Static("Theme Preset", classes="field-label")
            yield Select(
                [(label, key) for key, label in THEME_OPTIONS.items()],
                id="system-theme-select",
                allow_blank=False,
                value=self._theme_name,
            )
            yield Static("Workspace Mode", classes="field-label")
            yield Select(
                [(item["label"], key) for key, item in WORKSPACE_MODES.items()],
                id="system-workspace-mode-select",
                allow_blank=False,
                value=self._workspace_mode,
            )
            yield Static("Default Agent", classes="field-label")
            yield Select(
                [("(unset)", UNSET_OPTION), *((name, name) for name in self._available_agents)],
                id="system-default-agent-select",
                allow_blank=False,
                value=self._default_agent,
            )
            yield Static("Default LLM Profile", classes="field-label")
            yield Select(
                [("(unset)", UNSET_OPTION), *((name, name) for name in self._available_llm_profiles)],
                id="system-default-llm-select",
                allow_blank=False,
                value=self._default_llm_profile,
            )
            with Horizontal(id="system-settings-actions", classes="button-row"):
                yield Button("Apply", id="system-settings-apply", variant="primary")
                yield Button("Cancel", id="system-settings-cancel")

    def on_mount(self) -> None:
        self.query_one("#system-theme-select", Select).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        default_agent = self.query_one("#system-default-agent-select", Select).value
        default_llm_profile = self.query_one("#system-default-llm-select", Select).value
        self.dismiss(
            {
                "theme_name": str(self.query_one("#system-theme-select", Select).value),
                "workspace_mode": str(self.query_one("#system-workspace-mode-select", Select).value),
                "default_agent": None if str(default_agent) == UNSET_OPTION else str(default_agent),
                "default_llm_profile": None if str(default_llm_profile) == UNSET_OPTION else str(default_llm_profile),
            }
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "system-settings-apply":
            self.action_apply()
        elif button_id == "system-settings-cancel":
            self.action_cancel()

class PocketCodeTextualApp(App[None]):
    BINDINGS = [
        Binding("tab", "complete_input", "Complete Input", priority=True),
        Binding("f1", "view_chat", "Chat", priority=True),
        Binding("f3", "edit_asset", "Edit", priority=True),
        Binding("f4", "clone_asset", "Clone", priority=True),
        Binding("f5", "view_run", "Run", priority=True),
        Binding("f6", "pick_asset", "Control", priority=True),
        Binding("f10", "toggle_right_panel", "Toggle Inspector"),
        Binding("alt+1", "view_chat", "Chat", show=False),
        Binding("alt+2", "view_control", "Control", show=False),
        Binding("alt+5", "view_run", "Run", show=False),
        Binding("ctrl+shift+a", "copy_output", "Copy Output"),
        Binding("ctrl+y", "copy_last_response", "Copy Last"),
        Binding("ctrl+r", "reload_runtime", "Reload"),
        Binding("ctrl+l", "clear_output", "Clear Output"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: #0f172a;
        color: #e2e8f0;
    }

    Screen.theme-ocean {
        background: #0f172a;
        color: #e2e8f0;
    }

    Screen.theme-ocean #topbar {
        background: #082f49;
        border-bottom: solid #0ea5e9;
    }

    Screen.theme-ocean Footer {
        background: #111827;
        color: #dbeafe;
    }

    Screen.theme-ocean #header-agent,
    Screen.theme-ocean #header-llm {
        background: #0b4f6c;
        color: #f8fafc;
        border: round #0ea5e9;
    }

    Screen.theme-ocean .view {
        background: #111827;
        border: round #334155;
    }

    Screen.theme-ocean #view-title {
        background: #082f49;
        color: #e0f2fe;
        border: round #0ea5e9;
    }

    Screen.theme-ocean .card,
    Screen.theme-ocean #output,
    Screen.theme-ocean #profile-list,
    Screen.theme-ocean #profile-tools-summary,
    Screen.theme-ocean #profile-prompts,
    Screen.theme-ocean #context-preview,
    Screen.theme-ocean #run-preview,
    Screen.theme-ocean #inspector-tools,
    Screen.theme-ocean #inspector-prompts {
        background: #020617;
        border: round #334155;
        color: #e2e8f0;
    }

    Screen.theme-ocean #main-input {
        border: round #f59e0b;
    }

    Screen.theme-forest {
        background: #0b1510;
        color: #ecfccb;
    }

    Screen.theme-forest #topbar {
        background: #16351f;
        border-bottom: solid #65a30d;
    }

    Screen.theme-forest Footer {
        background: #14532d;
        color: #dcfce7;
    }

    Screen.theme-forest #header-agent,
    Screen.theme-forest #header-llm {
        background: #14532d;
        color: #f0fdf4;
        border: round #65a30d;
    }

    Screen.theme-forest .view {
        background: #102018;
        border: round #365314;
    }

    Screen.theme-forest #view-title {
        background: #16351f;
        color: #dcfce7;
        border: round #65a30d;
    }

    Screen.theme-forest .card,
    Screen.theme-forest #output,
    Screen.theme-forest #profile-list,
    Screen.theme-forest #profile-tools-summary,
    Screen.theme-forest #profile-prompts,
    Screen.theme-forest #context-preview,
    Screen.theme-forest #run-preview,
    Screen.theme-forest #inspector-tools,
    Screen.theme-forest #inspector-prompts {
        background: #09110d;
        border: round #365314;
        color: #ecfccb;
    }

    Screen.theme-forest #main-input {
        border: round #84cc16;
    }

    Screen.theme-ember {
        background: #1a120c;
        color: #ffedd5;
    }

    Screen.theme-ember #topbar {
        background: #3b1d10;
        border-bottom: solid #fb923c;
    }

    Screen.theme-ember Footer {
        background: #7c2d12;
        color: #ffedd5;
    }

    Screen.theme-ember #header-agent,
    Screen.theme-ember #header-llm {
        background: #9a3412;
        color: #fff7ed;
        border: round #fb923c;
    }

    Screen.theme-ember .view {
        background: #22140d;
        border: round #9a3412;
    }

    Screen.theme-ember #view-title {
        background: #3b1d10;
        color: #ffedd5;
        border: round #fb923c;
    }

    Screen.theme-ember .card,
    Screen.theme-ember #output,
    Screen.theme-ember #profile-list,
    Screen.theme-ember #profile-tools-summary,
    Screen.theme-ember #profile-prompts,
    Screen.theme-ember #context-preview,
    Screen.theme-ember #run-preview,
    Screen.theme-ember #inspector-tools,
    Screen.theme-ember #inspector-prompts {
        background: #120b07;
        border: round #9a3412;
        color: #ffedd5;
    }

    Screen.theme-ember #main-input {
        border: round #fb923c;
    }

    Footer {
        height: 1;
        padding: 0 1;
        background: #111827;
        color: #dbeafe;
    }

    #topbar {
        height: auto;
        padding: 0 1;
        background: #082f49;
        border-bottom: solid #0ea5e9;
    }

    #topbar-main {
        height: 1;
        padding: 0;
        content-align: right middle;
    }

    #header-agent,
    #header-llm {
        width: auto;
        min-width: 20;
        height: 1;
        margin: 0 0 0 1;
        padding: 0 1;
        content-align: left middle;
        text-style: bold;
    }

    #workspace {
        height: 1fr;
        padding: 0;
    }

    #main-column {
        width: 1fr;
        min-width: 60;
        margin: 0;
    }

    #right-panel {
        width: 34;
        min-width: 30;
        max-width: 38;
    }

    #view-tabs {
        height: auto;
        margin-bottom: 1;
    }

    #view-title {
        height: 3;
        padding: 0 1;
        margin-bottom: 1;
        border: round #0ea5e9;
        background: #082f49;
        color: #e0f2fe;
        content-align: left middle;
        text-style: bold;
    }

    #view-switcher {
        height: 1fr;
    }

    .view {
        height: 1fr;
        border: round #334155;
        background: #111827;
        padding: 0 1;
    }

    .view-scroll {
        height: 1fr;
    }

    #output {
        height: 1fr;
        border: round #0ea5e9;
        background: #020617;
        color: #e2e8f0;
    }

    #main-input {
        margin-top: 0;
        border: round #f59e0b;
    }

    .panel-title {
        height: auto;
        margin-bottom: 0;
        color: #f8fafc;
        text-style: bold;
    }

    .section-title {
        margin: 0 0 0 0;
        color: #93c5fd;
        text-style: bold;
    }

    .field-label {
        margin-top: 0;
        color: #cbd5e1;
    }

    .hint {
        color: #fcd34d;
        margin-bottom: 0;
    }

    .card {
        border: round #475569;
        background: #0b1220;
        padding: 0;
        margin-bottom: 0;
    }

    .button-row {
        height: auto;
        margin-top: 0;
    }

    Button {
        width: auto;
        min-width: 12;
        margin-bottom: 0;
    }

    #profile-list,
    #skill-list {
        height: 10;
        margin-bottom: 0;
        border: round #334155;
        background: #020617;
    }

    #profile-tools-summary {
        height: 12;
        border: round #334155;
        background: #020617;
    }

    #profile-policy-summary {
        height: 6;
        border: round #334155;
        background: #020617;
        color: #e2e8f0;
    }

    #run-preview,
    #inspector-context,
    #inspector-tools,
    #inspector-prompts {
        height: 10;
        border: round #334155;
        background: #020617;
        color: #e2e8f0;
    }

    #run-preview,
    #inspector-context,
    #inspector-tools,
    #inspector-prompts {
        height: 10;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(self, engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
        super().__init__()
        self._engine = engine
        self._cli_context = cli_context
        system_settings = (
            engine.get_system_settings()
            if hasattr(engine, "get_system_settings")
            else {
                "theme_name": "ocean",
                "workspace_mode": "balanced",
                "default_agent": None,
                "default_llm_profile": None,
            }
        )
        self._busy = False
        self._active_run: RunHandle | None = None
        self._pending_input_request: dict[str, Any] | None = None
        self._live_run_status = "idle"
        self._live_run_events: list[str] = []
        self._show_right_panel = True
        self._current_view = "chat"
        self._theme_name = str(system_settings.get("theme_name") or "ocean")
        self._workspace_mode = str(system_settings.get("workspace_mode") or "balanced")
        self._output_lines: list[str] = []
        self._trimmed_output_line_count = 0
        self._last_assistant_response: str = ""
        self._suggestions: list[str] = []
        self._profile_list_names: list[str] = []
        self._syncing_controls = False
        self._select_state_cache: dict[str, tuple[tuple[tuple[str, str], ...], str]] = {}
        self._text_state_cache: dict[str, str] = {}
        self._option_list_state_cache: dict[str, tuple[str, ...]] = {}
        self._selection_list_state_cache: dict[str, tuple[tuple[str, str, bool], ...]] = {}
        self._ui_state: TextualUIState | None = None
        self._apply_workspace_mode(self._workspace_mode, announce=False)

    def compose(self) -> ComposeResult:
        with Vertical(id="topbar"):
            with Horizontal(id="topbar-main"):
                yield Static(id="header-agent")
                yield Static(id="header-llm")
        with Horizontal(id="workspace"):
            with Vertical(id="main-column"):
                yield Static(id="view-title")
                with ContentSwitcher(initial="view-chat", id="view-switcher"):
                    with Vertical(id="view-chat", classes="view"):
                        yield TextArea("", id="output", read_only=True)
                    with VerticalScroll(id="view-control", classes="view view-scroll"):
                        yield Static("Runtime controls apply immediately.", classes="hint")
                        yield Static("Workspace Mode", classes="field-label")
                        yield Select(
                            [(item["label"], key) for key, item in WORKSPACE_MODES.items()],
                            id="workspace-mode-select",
                            allow_blank=False,
                            value=self._workspace_mode,
                        )
                        yield Static("Theme Preset", classes="field-label")
                        yield Select(
                            [(label, key) for key, label in THEME_OPTIONS.items()],
                            id="theme-select",
                            allow_blank=False,
                            value=self._theme_name,
                        )
                        yield Static("Active Agent", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="profile-select", allow_blank=False)
                        yield Static("Global LLM Override", classes="field-label")
                        yield Select([("loading...", LOADING_OPTION)], id="llm-select", allow_blank=False)
                        yield Static("Session Confirmation Default", classes="field-label")
                        yield Select(
                            [
                                ("inherit", INHERIT_POLICY),
                                ("allow", "allow"),
                                ("confirm", "confirm"),
                                ("deny", "deny"),
                            ],
                            id="session-confirm-select",
                            allow_blank=False,
                        )
                        yield Static("Auto-Confirm Tools", classes="field-label")
                        yield Switch(value=False, id="auto-confirm-switch")
                        with Horizontal(classes="button-row"):
                            yield Button("Control Center", id="control-center-button", variant="primary")
                            yield Button("Reload Runtime", id="reload-button", variant="primary")
                            yield Button("Return to Chat", id="goto-chat-button")
                    with VerticalScroll(id="view-run", classes="view view-scroll"):
                        yield Static("Last run summary and effective runtime state.", classes="hint")
                        yield TextArea("", id="run-preview", read_only=True)
                yield Input(
                    id="main-input",
                    placeholder="Type a request or /command. F1 chat F3 edit F4 clone F5 run F6 control",
                )
            with VerticalScroll(id="right-panel", classes="view"):
                yield Static("Inspector", classes="panel-title")
                yield Static("", id="inspector-summary", classes="card")
                yield Static("Session Context", classes="section-title")
                yield TextArea("", id="inspector-context", read_only=True)
                yield Static("Available Agent Profiles", classes="section-title")
                yield OptionList(id="profile-list")
                yield Static("Skills", classes="section-title")
                yield SelectionList(id="skill-list")
                yield Static("Active Tools", classes="section-title")
                yield TextArea("", id="inspector-tools", read_only=True)
                yield Static("Prompt Sources", classes="section-title")
                yield TextArea("", id="inspector-prompts", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_suggestions()
        self._refresh_ui()
        self.set_interval(0.1, self._drain_run_events)
        self.query_one("#main-input", Input).focus()

    def _refresh_suggestions(self) -> None:
        words = list_command_suggestions(self._engine)
        self._suggestions = words
        self.query_one("#main-input", Input).suggester = SuggestFromList(words, case_sensitive=False)

    def _render_profile_policy_summary(self, overrides: dict[str, str]) -> str:
        if not overrides:
            return "No per-tool confirmation overrides. Tools inherit the agent default."
        lines = ["Per-tool confirmation overrides:"]
        for tool_name in sorted(overrides):
            lines.append(f"- {tool_name}: {overrides[tool_name]}")
        return "\n".join(lines)

    def _render_profile_tools_summary(
        self,
        available_tools: tuple[str, ...],
        *,
        allow_all: bool,
        selected_tools: set[str],
    ) -> str:
        if not available_tools:
            return "No tools available for this agent."
        if allow_all:
            return "All agent tools are allowed."
        visible_tools = [tool_name for tool_name in available_tools if tool_name in selected_tools]
        if not visible_tools:
            return "No tools selected."
        return "\n".join(f"- {tool_name}" for tool_name in visible_tools)

    def _current_llm_profile_name(self) -> str | None:
        status = self._engine.status()
        current = (
            status.get("selected_llm_profile")
            or status.get("global_llm_override")
            or status.get("default_llm_profile")
        )
        return str(current) if current else None

    def _build_ui_state(self) -> TextualUIState:
        status = self._engine.status()
        current_agent = self._engine.get_current_agent()
        active_profile = self._engine.active_agent_profile
        all_profile_names = tuple(dict.fromkeys(self._profile_cycle()))
        current_agent_tools = tuple(self._engine.list_tools_for_agent(current_agent)) if current_agent else ()
        prompt_sources = tuple(self._engine.get_agent_prompt_sources(current_agent)) if current_agent else ()
        active_profile_name = active_profile.name if active_profile else None
        active_skill_names = tuple(
            str(getattr(skill, "name", skill))
            for skill in (
                self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else []
            )
        )

        llm_profile_names = tuple(str(name) for name in status.get("available_llm_profiles", []))
        session_default = status.get("session_tool_confirmation_overrides", {}).get("default_policy") or INHERIT_POLICY
        summary_lines = [
            f"Agent: {active_profile_name or 'none'}",
            f"Internal flow: {status.get('runtime_flow') or 'internal-flow'}",
            f"Agent source: {active_profile.source if active_profile else '-'}",
            f"Global LLM: {self._engine.global_llm_override or 'inherit'}",
            f"Skills: {', '.join(active_skill_names) if active_skill_names else 'none'}",
            f"Auto-confirm: {'on' if self._engine.auto_confirm_tools else 'off'}",
            f"Session confirm: {session_default}",
            _build_stats_text(status),
        ]
        if active_profile and active_profile.description:
            summary_lines.append(f"Agent note: {active_profile.description}")

        profile_list_labels = tuple(
            f"{'* ' if active_profile_name == profile_name else '  '}{profile_name}"
            for profile_name in all_profile_names
        ) or ("No agent profiles available",)

        effective_llm_profile = (
            active_profile.llm_profile
            if active_profile is not None and active_profile.llm_profile
            else self._engine.global_llm_override or status.get("default_llm_profile") or "none"
        )
        status_for_display = dict(status)
        status_for_display.setdefault("selected_agent", active_profile_name or "none")
        status_for_display.setdefault("selected_llm_profile", effective_llm_profile)
        profile_select_options = (
            tuple((profile_name, profile_name) for profile_name in all_profile_names)
            if all_profile_names
            else (("No agent profiles available", LOADING_OPTION),)
        )

        return TextualUIState(
            theme_name=self._theme_name,
            current_view=self._current_view,
            right_panel_visible=self._show_right_panel,
            status_text="",
            header_agent_text=_build_header_agent_text(status_for_display),
            header_llm_text=_build_header_llm_text(status_for_display),
            view_title_text=_build_view_title_text(self._current_view),
            workspace_mode_select=SelectViewState(
                options=tuple((item["label"], key) for key, item in WORKSPACE_MODES.items()),
                value=self._workspace_mode,
            ),
            theme_select=SelectViewState(
                options=tuple((label, key) for key, label in THEME_OPTIONS.items()),
                value=self._theme_name,
            ),
            profile_select=SelectViewState(
                options=profile_select_options,
                value=active_profile_name or LOADING_OPTION,
            ),
            llm_select=SelectViewState(
                options=(("(inherit)", NO_LLM),) + tuple((name, name) for name in llm_profile_names),
                value=self._engine.global_llm_override or NO_LLM,
            ),
            session_confirm_select=SelectViewState(
                options=(
                    ("inherit", INHERIT_POLICY),
                    ("allow", "allow"),
                    ("confirm", "confirm"),
                    ("deny", "deny"),
                ),
                value=session_default,
            ),
            auto_confirm_tools=bool(self._engine.auto_confirm_tools),
            inspector_summary_text="\n".join(summary_lines),
            inspector_context_text=self._render_context_summary(status),
            skill_list_options=self._render_skill_options(status),
            inspector_tools_text=self._render_tool_summary(current_agent, active_profile, list(current_agent_tools)),
            inspector_prompts_text=self._render_prompt_summary({"prompt_sources": list(prompt_sources)}, active_profile),
            profile_list_names=all_profile_names,
            profile_list_labels=profile_list_labels,
            run_preview_text=self._render_run_preview(status),
        )

    def _apply_theme_name(self, theme_name: str) -> None:
        for class_name in [f"theme-{name}" for name in THEME_OPTIONS]:
            self.screen.remove_class(class_name)
        self.screen.add_class(f"theme-{theme_name}")

    def _apply_panel_visibility(self, *, right_visible: bool) -> None:
        self.query_one("#right-panel", VerticalScroll).display = right_visible

    def _apply_view_state(self, view_name: str, view_title_text: str) -> None:
        self.query_one("#view-switcher", ContentSwitcher).current = f"view-{view_name}"
        title_widget = self.query_one("#view-title", Static)
        title_widget.display = bool(view_title_text)
        self._set_static_text(title_widget, view_title_text)

    def _apply_ui_state(self, state: TextualUIState) -> None:
        previous = self._ui_state
        if previous is None or previous.theme_name != state.theme_name:
            self._apply_theme_name(state.theme_name)
        if previous is None or previous.right_panel_visible != state.right_panel_visible:
            self._apply_panel_visibility(right_visible=state.right_panel_visible)
        if (
            previous is None
            or previous.current_view != state.current_view
            or previous.view_title_text != state.view_title_text
        ):
            self._apply_view_state(state.current_view, state.view_title_text)

        self._set_static_text(self.query_one("#header-agent", Static), state.header_agent_text)
        self._set_static_text(self.query_one("#header-llm", Static), state.header_llm_text)

        self._syncing_controls = True
        try:
            self._set_select_options(
                self.query_one("#workspace-mode-select", Select),
                state.workspace_mode_select.options,
                state.workspace_mode_select.value,
            )
            self._set_select_options(
                self.query_one("#theme-select", Select),
                state.theme_select.options,
                state.theme_select.value,
            )
            self._set_select_options(
                self.query_one("#profile-select", Select),
                state.profile_select.options,
                state.profile_select.value,
            )
            self._set_select_options(
                self.query_one("#llm-select", Select),
                state.llm_select.options,
                state.llm_select.value,
            )
            self._set_select_options(
                self.query_one("#session-confirm-select", Select),
                state.session_confirm_select.options,
                state.session_confirm_select.value,
            )
            self.query_one("#auto-confirm-switch", Switch).value = state.auto_confirm_tools
        finally:
            self._syncing_controls = False

        self._profile_list_names = list(state.profile_list_names)
        self._set_option_list_labels(self.query_one("#profile-list", OptionList), state.profile_list_labels)
        self._set_selection_list_options(self.query_one("#skill-list", SelectionList), state.skill_list_options)
        self._set_static_text(self.query_one("#inspector-summary", Static), state.inspector_summary_text)
        self._set_text_area_text(self.query_one("#inspector-context", TextArea), state.inspector_context_text)
        self._set_text_area_text(self.query_one("#inspector-tools", TextArea), state.inspector_tools_text)
        self._set_text_area_text(self.query_one("#inspector-prompts", TextArea), state.inspector_prompts_text)
        self._set_text_area_text(self.query_one("#run-preview", TextArea), state.run_preview_text)

        self._ui_state = state

    def _refresh_ui(self) -> None:
        self._apply_ui_state(self._build_ui_state())

    def _write_info(self, text: str) -> None:
        self._append_output_line(f"info> {text}")

    def _write_error(self, text: str) -> None:
        self._append_output_line(f"error> {text}")

    def _write_user(self, text: str) -> None:
        self._append_output_line(f"you> {text}")

    def _write_assistant(self, text: str) -> None:
        self._append_output_line(f"assistant> {text}")
        self._last_assistant_response = text

    def _append_output_line(self, line: str) -> None:
        self._output_lines.append(line)
        output_widget = self.query_one("#output", TextArea)
        trimmed_lines, trimmed_now = _trim_output_lines(self._output_lines, MAX_OUTPUT_LINES)
        if trimmed_now:
            self._trimmed_output_line_count += trimmed_now
            self._output_lines = trimmed_lines
        text = _build_output_text(self._output_lines, self._trimmed_output_line_count)
        self._load_text_area_text(output_widget, text)
        output_widget.scroll_end(animate=False)

    def _apply_workspace_mode(self, mode_name: str, *, announce: bool) -> None:
        config = WORKSPACE_MODES.get(mode_name)
        if config is None:
            return
        self._workspace_mode = mode_name
        self._show_right_panel = bool(config["right"])
        self._current_view = str(config["view"])
        if announce:
            self._write_info(f"Workspace mode: {config['label']}.")

    def _render_context_preview(self) -> str:
        if not any(self._cli_context.values()):
            return "No context selected."

        lines: list[str] = []
        for label, key in (
            ("Files", "files"),
            ("Folders", "folders"),
            ("URLs", "urls"),
        ):
            values = sorted(self._cli_context.get(key, set()) or set())
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {value}" for value in values)
        snippets = self._cli_context.get("snippets", {})
        if isinstance(snippets, dict) and snippets:
            lines.append("Snippets:")
            for name, content in sorted(snippets.items()):
                lines.append(f"- {name}: {content}")
        return "\n".join(lines)

    def _render_run_preview(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {})
        if not isinstance(run_summary, dict):
            run_summary = {}

        lines = [
            f"live_run_status: {self._live_run_status}",
            f"internal_flow: {status.get('runtime_flow') or 'internal-flow'}",
            f"active_agent: {status.get('agent') or 'auto'}",
            f"active_profile: {status.get('active_agent_profile') or 'none'}",
            f"global_llm_override: {status.get('global_llm_override') or 'none'}",
            f"agent_path: {run_summary.get('agent_path', [])}",
            f"current_llm_profile: {run_summary.get('current_llm_profile') or 'none'}",
            f"current_llm_model: {run_summary.get('current_llm_model') or '-'}",
            f"llm_usage: {run_summary.get('llm_usage', {})}",
            f"llm_cost_usd: {run_summary.get('llm_cost_usd', 0.0)}",
            f"context_stats: {run_summary.get('context_stats', {})}",
            f"session_confirmation: {status.get('session_tool_confirmation_overrides', {})}",
        ]
        if self._live_run_events:
            lines.append("live_events:")
            lines.extend(f"- {item}" for item in self._live_run_events[-8:])
        return "\n".join(lines)

    def _render_context_summary(self, status: Dict[str, Any]) -> str:
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
        if not isinstance(context_stats, dict):
            context_stats = {}

        lines = [
            f"files: {context_stats.get('files', len(self._cli_context.get('files', set()) or set()))}",
            f"folders: {context_stats.get('folders', len(self._cli_context.get('folders', set()) or set()))}",
            f"urls: {context_stats.get('urls', len(self._cli_context.get('urls', set()) or set()))}",
            f"snippets: {context_stats.get('snippets', len(self._cli_context.get('snippets', {}) or {}))}",
            f"snippet_chars: {context_stats.get('snippet_chars', 0)}",
            "",
            self._render_context_preview(),
        ]
        return "\n".join(lines)

    def _render_tool_summary(
        self,
        agent_name: str | None,
        active_profile: Any,
        tool_names: list[str] | None = None,
    ) -> str:
        if not agent_name:
            return "No agent selected."
        if tool_names is None:
            tool_names = self._engine.list_tools_for_agent(agent_name)
        if not tool_names:
            return "No tools available."
        allowed = set(active_profile.tools) if active_profile and active_profile.tools is not None else None
        lines: list[str] = []
        if allowed is None:
            lines.append("Tool scope: unrestricted")
            visible_tools = tool_names
        else:
            lines.append("Tool scope: profile allowlist")
            visible_tools = [tool_name for tool_name in tool_names if tool_name in allowed]
        if not visible_tools:
            lines.append("(no tools selected)")
            return "\n".join(lines)
        for tool_name in visible_tools:
            lines.append(f"[x] {tool_name}")
        return "\n".join(lines)

    def _render_prompt_summary(self, agent_meta: Dict[str, Any], active_profile: Any) -> str:
        agent_prompts = agent_meta.get("prompt_sources", []) if isinstance(agent_meta, dict) else []
        extra_prompts = list(active_profile.extra_prompts) if active_profile else []
        lines: list[str] = []
        if agent_prompts:
            lines.append("Agent prompt sources:")
            lines.extend(f"- {path}" for path in agent_prompts)
        if extra_prompts:
            lines.append("Profile extra prompts:")
            lines.extend(f"- {path}" for path in extra_prompts)
        if not lines:
            return "No prompt sources registered."
        return "\n".join(lines)

    def _skill_group_value(self, group_name: str) -> str:
        return f"{SKILL_GROUP_PREFIX}{group_name}"

    def _is_skill_group_value(self, value: str) -> bool:
        return str(value).startswith(SKILL_GROUP_PREFIX)

    def _skill_group_members(self, skill_names: Iterable[str]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for skill_name in sorted({str(name) for name in skill_names}):
            grouped.setdefault(_skill_group_name(skill_name), []).append(skill_name)
        return {
            group_name: tuple(grouped[group_name])
            for group_name in sorted(grouped)
        }

    def _tool_group_members(self, tool_names: Iterable[str]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for tool_name in sorted({str(name) for name in tool_names}):
            grouped.setdefault(_tool_group_name(tool_name), []).append(tool_name)
        return {
            group_name: tuple(grouped[group_name])
            for group_name in sorted(grouped)
        }

    def _tool_group_path(
        self,
        tool_name: str,
        tool_detail: Dict[str, Any] | None = None,
    ) -> tuple[str, ...]:
        if isinstance(tool_detail, dict):
            raw_group_path = tool_detail.get("group_path")
            if isinstance(raw_group_path, (list, tuple)):
                normalized = tuple(str(part).strip() for part in raw_group_path if str(part).strip())
                if normalized:
                    return normalized
        return (_tool_group_name(tool_name),)

    def _build_nested_tool_picker_options(
        self,
        tool_names: Iterable[str],
        *,
        selected_tools: set[str],
        tool_details: dict[str, Dict[str, Any]] | None = None,
    ) -> tuple[list[PickerOption], dict[str, tuple[str, ...]], set[str]]:
        grouped_values_by_path: dict[tuple[str, ...], list[str]] = {}
        child_groups: dict[tuple[str, ...], set[str]] = {}
        leaf_tools: dict[tuple[str, ...], list[str]] = {}

        for tool_name in sorted({str(name) for name in tool_names}):
            group_path = self._tool_group_path(tool_name, (tool_details or {}).get(tool_name))
            leaf_tools.setdefault(group_path, []).append(tool_name)
            for depth in range(1, len(group_path) + 1):
                prefix = group_path[:depth]
                grouped_values_by_path.setdefault(prefix, []).append(tool_name)
                parent = group_path[: depth - 1]
                child_groups.setdefault(parent, set()).add(group_path[depth - 1])

        picker_options: list[PickerOption] = []
        grouped_values: dict[str, tuple[str, ...]] = {}
        initial_selected_values = set(selected_tools)

        def _append_group(path: tuple[str, ...], depth: int) -> None:
            member_values = tuple(sorted(dict.fromkeys(grouped_values_by_path.get(path, []))))
            if not member_values:
                return
            group_value = self._skill_group_value("/".join(path))
            grouped_values[group_value] = member_values
            if all(member_value in selected_tools for member_value in member_values):
                initial_selected_values.add(group_value)
            group_label = f"{'  ' * depth}Group: {path[-1]}"
            group_search = " ".join(path)
            picker_options.append(
                PickerOption(
                    group_value,
                    group_label,
                    description=f"Toggle all {len(member_values)} tools in {' / '.join(path)}",
                    search_text=f"{group_search} group {' '.join(member_values)}",
                )
            )
            for child_name in sorted(child_groups.get(path, set())):
                _append_group(path + (child_name,), depth + 1)
            for member_value in sorted(leaf_tools.get(path, [])):
                picker_options.append(
                    PickerOption(
                        member_value,
                        f"{'  ' * (depth + 1)}{member_value}",
                        description=f"Group: {' / '.join(path)}",
                        search_text=f"{member_value} {group_search}",
                    )
                )

        for group_name in sorted(child_groups.get((), set())):
            _append_group((group_name,), 0)

        return picker_options, grouped_values, initial_selected_values

    def _active_skill_name_set(self) -> set[str]:
        return {
            str(getattr(skill, "name", skill))
            for skill in (
                self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else []
            )
        }

    def _render_skill_options(self, status: Dict[str, Any]) -> tuple[tuple[str, str, bool], ...]:
        available_skills = tuple(str(name) for name in status.get("available_skills", []) or [])
        active_skill_names = self._active_skill_name_set()
        if not available_skills:
            return (("No skills available", LOADING_OPTION, False),)
        grouped_skills = self._skill_group_members(available_skills)
        options: list[tuple[str, str, bool]] = []
        for group_name, member_values in grouped_skills.items():
            options.append(
                (
                    f"Group: {group_name} ({len(member_values)})",
                    self._skill_group_value(group_name),
                    bool(member_values) and all(member_value in active_skill_names for member_value in member_values),
                )
            )
            options.extend(
                (f"  {skill_name}", skill_name, skill_name in active_skill_names)
                for skill_name in member_values
            )
        return tuple(options)

    def _set_select_options(
        self,
        widget: Select,
        options: Iterable[tuple[str, str]],
        value: str,
    ) -> None:
        option_list = [(str(label), str(option_value)) for label, option_value in options]
        cache_key = widget.id or ""
        option_tuple = tuple(option_list)
        if self._select_state_cache.get(cache_key) == (option_tuple, value):
            return
        widget.set_options(option_list)
        try:
            widget.value = value
        except Exception:
            if option_list:
                widget.value = option_list[0][1]
                value = option_list[0][1]
        self._select_state_cache[cache_key] = (option_tuple, value)

    def _set_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.text = text
        self._text_state_cache[cache_key] = text

    def _load_text_area_text(self, widget: TextArea, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.load_text(text)
        self._text_state_cache[cache_key] = text

    def _set_static_text(self, widget: Static, text: str) -> None:
        cache_key = widget.id or ""
        if self._text_state_cache.get(cache_key) == text:
            return
        widget.update(text)
        self._text_state_cache[cache_key] = text

    def _set_option_list_labels(self, widget: OptionList, labels: Iterable[str]) -> None:
        option_tuple = tuple(str(label) for label in labels)
        cache_key = widget.id or ""
        if self._option_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        self._option_list_state_cache[cache_key] = option_tuple

    def _set_selection_list_options(
        self,
        widget: SelectionList,
        options: Iterable[tuple[str, str, bool]],
    ) -> None:
        option_tuple = tuple((str(label), str(value), bool(selected)) for label, value, selected in options)
        cache_key = widget.id or ""
        if self._selection_list_state_cache.get(cache_key) == option_tuple:
            return
        widget.clear_options()
        if option_tuple:
            widget.add_options(option_tuple)
        widget.disabled = len(option_tuple) == 1 and option_tuple[0][1] == LOADING_OPTION
        self._selection_list_state_cache[cache_key] = option_tuple

    def _sync_ui_from_engine(self) -> None:
        self._refresh_ui()

    def _set_main_input_placeholder(self, prompt: str | None = None) -> None:
        input_widget = self.query_one("#main-input", Input)
        input_widget.placeholder = prompt or "Type a request or /command. F1 chat F3 edit F4 clone F5 run F6 control"

    def _profile_cycle(self) -> list[str]:
        profile_names: list[str] = []
        for agent_name in self._engine.list_agents():
            profile_names.extend(self._engine.list_agent_profiles(agent_name))
        return profile_names

    def _remember_run_event(self, text: str) -> None:
        self._live_run_events.append(text)
        if len(self._live_run_events) > 25:
            self._live_run_events = self._live_run_events[-25:]

    def _drain_run_events(self) -> None:
        if self._active_run is None:
            return
        events = self._active_run.drain_events()
        if not events:
            return
        should_refresh = False
        for event in events:
            should_refresh = self._consume_run_event(event) or should_refresh
        if should_refresh:
            self._refresh_ui()

    def _consume_run_event(self, event: Dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "")
        message = self._format_runtime_event(event)
        if message:
            self._remember_run_event(message)
            self._write_info(message)

        if event_type == "interaction_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(interaction_placeholder(event))
            if event.get("kind") != "text":
                self._write_info(describe_interaction_request(event))
            return True
        if event_type == "interaction_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "user_input_requested":
            self._pending_input_request = event
            self._live_run_status = "waiting_for_input"
            self._set_main_input_placeholder(str(event.get("prompt") or "Provide input"))
            return True
        if event_type == "user_input_received":
            self._live_run_status = "running"
            self._set_main_input_placeholder()
            return True
        if event_type == "run_completed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._write_assistant(str(event.get("output") or ""))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_failed":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "failed"
            self._set_main_input_placeholder()
            self._write_error(str(event.get("error") or "Request failed."))
            self._sync_ui_from_engine()
            return False
        if event_type == "run_cancelled":
            self._busy = False
            self._active_run = None
            self._pending_input_request = None
            self._live_run_status = "idle"
            self._set_main_input_placeholder()
            self._sync_ui_from_engine()
            return False
        if event_type in {"run_started", "agent_turn_started", "llm_call_started", "tool_started", "handoff"}:
            self._live_run_status = "running"
        if event_type == "run_cancel_requested":
            self._live_run_status = "stopping"
        return True

    def _format_runtime_event(self, event: Dict[str, Any]) -> str:
        return format_runtime_event(event)

    def _show_picker(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None,
        on_select: Callable[[str], None],
        help_text: str = "Use arrows to move, Enter to select, Esc to close.",
        empty_message: str = "No matching options.",
    ) -> None:
        option_list = tuple(options)
        if not option_list:
            self._write_error(f"No options available for {title.lower()}.")
            return

        def _handle_selection(selected_value: str | None) -> None:
            if selected_value is None:
                return
            try:
                on_select(selected_value)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            AssetPickerScreen(
                title=title,
                options=option_list,
                current_value=current_value,
                help_text=help_text,
                empty_message=empty_message,
            ),
            callback=_handle_selection,
        )

    def _open_profile_picker(self) -> None:
        profile_names = tuple(dict.fromkeys(self._profile_cycle()))
        active_profile = self._engine.active_agent_profile
        options: list[PickerOption] = []
        for profile_name in profile_names:
            profile = None
            try:
                if hasattr(self._engine, "get_agent"):
                    profile = self._engine.get_agent(profile_name)
                elif hasattr(self._engine, "get_agent_profile"):
                    profile = self._engine.get_agent_profile(profile_name)
            except Exception:
                profile = None
            description_parts = [
                str(getattr(profile, "agent", "") or ""),
                str(getattr(profile, "source", "") or ""),
            ]
            description = " | ".join(part for part in description_parts if part)
            options.append(
                PickerOption(
                    profile_name,
                    profile_name,
                    description=description,
                    search_text=getattr(profile, "agent", "") if profile is not None else "",
                )
            )
        self._show_picker(
            title="Select Active Agent Profile",
            options=options,
            current_value=active_profile.name if active_profile is not None else None,
            on_select=self._apply_profile_selection,
            help_text="Choose the active agent profile.",
            empty_message="No agent profiles are available.",
        )

    def _open_mode_picker(self) -> None:
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        options = [PickerOption(NO_MODE, "(clear)", "Disable the active mode")]
        options.extend(PickerOption(name, name) for name in self._engine.list_modes())
        self._show_picker(
            title="Select Active Mode",
            options=tuple(options),
            current_value=active_mode.name if active_mode is not None else NO_MODE,
            on_select=self._apply_mode_selection,
            help_text="Choose the active runtime mode. Clear falls back to the selected agent profile.",
            empty_message="No modes are available.",
        )

    def _open_llm_picker(self) -> None:
        self._show_picker(
            title="Select Global LLM Override",
            options=(PickerOption(NO_LLM, "Inherit", "Use the engine default"),)
            + tuple(PickerOption(name, name) for name in self._engine.list_llm_profiles()),
            current_value=self._engine.global_llm_override or NO_LLM,
            on_select=self._apply_llm_selection,
            help_text="Choose the active runtime LLM override. Inherit falls back to the default resolution chain.",
            empty_message="No LLM profiles are available.",
        )

    def _open_workspace_mode_picker(self) -> None:
        self._show_picker(
            title="Select Workspace Mode",
            options=tuple(
                PickerOption(mode_name, config["label"], f"View: {config['view']}")
                for mode_name, config in WORKSPACE_MODES.items()
            ),
            current_value=self._workspace_mode,
            on_select=self._apply_workspace_mode_selection,
            help_text="Choose a layout preset for the Textual workspace.",
        )

    def _open_theme_picker(self) -> None:
        self._show_picker(
            title="Select Theme",
            options=tuple(PickerOption(theme_name, theme_label) for theme_name, theme_label in THEME_OPTIONS.items()),
            current_value=self._theme_name,
            on_select=self._apply_theme_selection,
            help_text="Choose a theme preset for the Textual workspace.",
        )

    def _open_session_confirmation_picker(self) -> None:
        current_value = self._engine.session_confirmation_overrides.get("default_policy") or INHERIT_POLICY
        self._show_picker(
            title="Select Session Confirmation Default",
            options=(
                PickerOption(INHERIT_POLICY, "Inherit", "Use config or agent defaults"),
                PickerOption("allow", "Allow"),
                PickerOption("confirm", "Confirm"),
                PickerOption("deny", "Deny"),
            ),
            current_value=current_value,
            on_select=self._apply_session_confirmation_selection,
            help_text="Choose the default confirmation policy for tools in this session.",
        )

    def _asset_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        session_default = self._engine.session_confirmation_overrides.get("default_policy") or "inherit"
        active_skill_names = tuple(
            str(getattr(skill, "name", skill))
            for skill in (
                self._engine.get_active_skills() if hasattr(self._engine, "get_active_skills") else []
            )
        )
        available_skill_count = len(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else 0
        preset_count = len(self._engine.list_textual_selection_presets()) if hasattr(
            self._engine, "list_textual_selection_presets"
        ) else 0
        return (
            PickerOption(
                value="profile",
                label=f"Agent: {active_profile.name if active_profile else 'none'}",
                description="Switch, edit, clone, or delete the active agent profile",
                search_text="agent profile active edit clone delete",
            ),
            PickerOption(
                value="mode",
                label=f"Mode: {active_mode.name if active_mode else 'none'}",
                description="Switch, clear, edit, clone, or delete a mode",
                search_text="mode preset switch clear edit clone delete",
            ),
            PickerOption(
                value="llm",
                label=f"LLM: {self._engine.global_llm_override or 'inherit'}",
                description="Switch, edit, clone, or delete the active LLM profile",
                search_text="llm model profile override edit clone delete",
            ),
            PickerOption(
                value="skills",
                label=(
                    f"Skills: {', '.join(active_skill_names)}"
                    if active_skill_names
                    else f"Skills: none ({available_skill_count} available)"
                ),
                description="Enable or disable runtime skills",
                search_text="skills capability packs selection",
            ),
            PickerOption(
                value="tools",
                label=f"Tools: {active_profile.name if active_profile else 'none'}",
                description="Edit the active agent tool allowlist",
                search_text="tools allowlist selection groups",
            ),
            PickerOption(
                value="tool_policies",
                label=f"Tool Policies: {active_profile.name if active_profile else 'none'}",
                description="Edit per-tool confirmation overrides",
                search_text="tool policy confirmation overrides",
            ),
            PickerOption(
                value="presets",
                label=f"Selection Presets: {preset_count}",
                description="Save, load, or delete whole selection snapshots",
                search_text="selection preset snapshot save load delete",
            ),
            PickerOption(
                value="session_confirm",
                label=f"Session confirmation: {session_default}",
                description="Set the default session confirmation policy",
                search_text="session confirm tool policy",
            ),
            PickerOption(
                value="system_settings",
                label="System Settings",
                description="Theme, workspace mode, and default agent/LLM saved to pocketcode.yml",
                search_text="system settings theme workspace mode default agent llm config save",
            ),
        )

    def _open_asset_picker(self) -> None:
        self._show_picker(
            title="Control Center",
            options=self._asset_category_options(),
            current_value=None,
            on_select=self._handle_asset_picker_selection,
            help_text="Choose a category, then drill into the action you want.",
        )

    def _handle_asset_picker_selection(self, selected_value: str) -> None:
        options = self._asset_action_options(selected_value)
        if not options:
            self._write_error(f"Unsupported asset picker target: {selected_value}")
            return
        self.call_after_refresh(lambda: self._open_asset_action_picker(selected_value, options))

    def _asset_action_options(self, category: str) -> tuple[PickerOption, ...]:
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if category == "profile":
            return (
                PickerOption("select", "Switch Active Profile", search_text="select switch active profile"),
                PickerOption("edit", "Edit Current Profile", search_text="edit agent profile yaml"),
                PickerOption("clone", "Clone Current Profile", search_text="clone agent profile workspace"),
                PickerOption("delete", "Delete Current Profile", search_text="delete remove workspace agent"),
            )
        if category == "mode":
            options = [
                PickerOption("select", "Switch Active Mode", search_text="select switch mode"),
                PickerOption("edit", "Edit Current Mode", search_text="edit mode markdown"),
                PickerOption("clone", "Clone Current Mode", search_text="clone mode"),
                PickerOption("delete", "Delete Current Mode", search_text="delete remove mode"),
            ]
            if active_mode is not None:
                options.insert(1, PickerOption("clear", "Clear Active Mode", search_text="clear reset active mode"))
            return tuple(options)
        if category == "llm":
            return (
                PickerOption("select", "Switch Global LLM", search_text="select switch llm"),
                PickerOption("edit", "Edit Current LLM", search_text="edit llm profile yaml"),
                PickerOption("clone", "Clone Current LLM", search_text="clone llm profile"),
                PickerOption("delete", "Delete Current LLM", search_text="delete remove workspace llm profile"),
            )
        if category == "skills":
            return (PickerOption("select", "Select Skills", search_text="skills selection"),)
        if category == "tools":
            return (PickerOption("select", "Edit Allowed Tools", search_text="tool selection allowlist"),)
        if category == "tool_policies":
            return (PickerOption("edit", "Edit Tool Policies", search_text="tool policy overrides"),)
        if category == "presets":
            return (
                PickerOption("save", "Save Current as Preset", search_text="save current selection preset"),
                PickerOption("load", "Load Preset", search_text="load selection preset"),
                PickerOption("delete", "Delete Preset", search_text="delete selection preset"),
            )
        if category == "session_confirm":
            return (PickerOption("select", "Set Session Confirmation", search_text="session confirmation"),)
        if category == "system_settings":
            return (PickerOption("open", "Open System Settings", search_text="system settings"),)
        return ()

    def _open_asset_action_picker(self, category: str, options: tuple[PickerOption, ...]) -> None:
        self._show_picker(
            title=f"{category.replace('_', ' ').title()} Actions",
            options=options,
            current_value=None,
            on_select=lambda action: self._handle_asset_action_selection(category, action),
            help_text="Choose the action to run for this category.",
        )

    def _handle_asset_action_selection(self, category: str, action: str) -> None:
        if category == "profile":
            if action == "select":
                self._open_profile_picker()
                return
            if action == "edit":
                self._open_agent_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone Agent Profile",
                    placeholder="my-agent-safe",
                    help_text="Enter the new workspace name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("agent", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("agent")
                return
        if category == "mode":
            if action == "select":
                self._open_mode_picker()
                return
            if action == "clear":
                if hasattr(self._engine, "set_last_used_mode"):
                    self._engine.set_last_used_mode(None)
                else:
                    self._engine.set_mode(None)
                self._write_info("Mode cleared.")
                self._sync_ui_from_engine()
                return
            if action == "edit":
                self._open_mode_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone Mode",
                    placeholder="review-copy",
                    help_text="Enter the new mode name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("mode", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("mode")
                return
        if category == "llm":
            if action == "select":
                self._open_llm_picker()
                return
            if action == "edit":
                self._open_llm_profile_editor()
                return
            if action == "clone":
                self._open_name_prompt(
                    title="Clone LLM Profile",
                    placeholder="my-llm-profile",
                    help_text="Enter the new workspace name / filename.",
                    on_submit=lambda value: self._clone_selected_asset("llm", value),
                )
                return
            if action == "delete":
                self._confirm_delete_current_asset("llm")
                return
        if category == "skills" and action == "select":
            self._open_skill_selection_picker()
            return
        if category == "tools" and action == "select":
            self._open_tool_selection_picker()
            return
        if category == "tool_policies" and action == "edit":
            self._open_tool_policy_editor()
            return
        if category == "presets":
            if action == "save":
                self._open_name_prompt(
                    title="Save Selection Preset",
                    placeholder="review-session",
                    help_text="Enter the preset name.",
                    on_submit=self._save_selection_preset,
                )
                return
            if action == "load":
                self._open_selection_preset_picker("load")
                return
            if action == "delete":
                self._open_selection_preset_picker("delete")
                return
        if category == "session_confirm" and action == "select":
            self._open_session_confirmation_picker()
            return
        if category == "system_settings" and action == "open":
            self._open_system_settings_screen()
            return
        self._write_error(f"Unsupported {category} action: {action}")

    def _apply_profile_selection(self, selected_value: str) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is not None and active_profile.name == selected_value:
            return
        if hasattr(self._engine, "set_last_used_active_profile"):
            self._engine.set_last_used_active_profile(selected_value)
        else:
            self._engine.set_active_agent_profile(selected_value)
        self._write_info(f"Activated agent profile: {selected_value}")

    def _apply_mode_selection(self, selected_value: str) -> None:
        target_mode = None if selected_value == NO_MODE else selected_value
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if active_mode is not None and target_mode == active_mode.name:
            return
        if active_mode is None and target_mode is None:
            return
        if hasattr(self._engine, "set_last_used_mode"):
            self._engine.set_last_used_mode(target_mode)
        else:
            self._engine.set_mode(target_mode)
        self._write_info(f"Mode: {target_mode or 'none'}")

    def _apply_llm_selection(self, selected_value: str) -> None:
        target_llm = None if selected_value == NO_LLM else selected_value
        if target_llm == self._engine.global_llm_override:
            return
        if hasattr(self._engine, "set_last_used_global_llm_profile"):
            self._engine.set_last_used_global_llm_profile(target_llm)
        else:
            self._engine.set_global_llm_override(target_llm)
        self._write_info(f"Global LLM override: {self._engine.global_llm_override or 'inherit'}")

    def _apply_workspace_mode_selection(self, selected_value: str) -> None:
        if selected_value == self._workspace_mode:
            return
        self._apply_workspace_mode(selected_value, announce=True)

    def _apply_theme_selection(self, selected_value: str) -> None:
        if selected_value == self._theme_name:
            return
        self._theme_name = selected_value
        self._write_info(f"Theme preset: {THEME_OPTIONS.get(selected_value, selected_value)}.")

    def _apply_session_confirmation_selection(self, selected_value: str) -> None:
        target_default = None if selected_value == INHERIT_POLICY else selected_value
        current_default = self._engine.session_confirmation_overrides.get("default_policy")
        if target_default == current_default:
            return
        if hasattr(self._engine, "set_last_used_session_confirmation_default"):
            self._engine.set_last_used_session_confirmation_default(target_default)
        else:
            self._engine.set_session_confirmation_default(target_default)
        self._write_info(
            f"Session confirmation default: "
            f"{self._engine.session_confirmation_overrides.get('default_policy') or 'inherit'}"
        )

    def _open_system_settings_screen(self) -> None:
        settings = (
            self._engine.get_system_settings()
            if hasattr(self._engine, "get_system_settings")
            else {
                "theme_name": self._theme_name,
                "workspace_mode": self._workspace_mode,
                "default_agent": None,
                "default_llm_profile": None,
            }
        )

        def _handle_submit(payload: dict[str, str | None] | None) -> None:
            if payload is None:
                return
            try:
                self._apply_system_settings(payload)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            SystemSettingsScreen(
                theme_name=str(settings.get("theme_name") or self._theme_name),
                workspace_mode=str(settings.get("workspace_mode") or self._workspace_mode),
                default_agent=str(settings.get("default_agent")) if settings.get("default_agent") else None,
                default_llm_profile=(
                    str(settings.get("default_llm_profile")) if settings.get("default_llm_profile") else None
                ),
                available_agents=self._engine.list_agents(),
                available_llm_profiles=self._engine.list_llm_profiles(),
            ),
            callback=_handle_submit,
        )

    def _apply_system_settings(self, payload: dict[str, str | None]) -> None:
        theme_name = str(payload.get("theme_name") or self._theme_name)
        workspace_mode = str(payload.get("workspace_mode") or self._workspace_mode)
        default_agent = str(payload.get("default_agent")) if payload.get("default_agent") else None
        default_llm_profile = (
            str(payload.get("default_llm_profile"))
            if payload.get("default_llm_profile")
            else None
        )

        if not hasattr(self._engine, "save_system_settings"):
            raise ValueError("This runtime does not support saving system settings.")

        config_path = self._engine.save_system_settings(
            theme_name=theme_name,
            workspace_mode=workspace_mode,
            default_agent=default_agent,
            default_llm_profile=default_llm_profile,
        )
        self._theme_name = theme_name
        self._apply_workspace_mode(workspace_mode, announce=False)
        if default_agent:
            self._engine.set_agent(default_agent)
        self._refresh_suggestions()
        self._write_info(f"Applied system settings and saved to {config_path}.")

    def _active_profile_policy_overrides(self, active_profile: Any) -> dict[str, str]:
        if not active_profile or not isinstance(active_profile.tool_confirmation, dict):
            return {}
        raw_overrides = active_profile.tool_confirmation.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            return {}
        return {
            str(tool_name): str(policy)
            for tool_name, policy in raw_overrides.items()
            if policy is not None
        }

    def _active_profile_default_confirmation(self, active_profile: Any) -> str | None:
        if not active_profile or not isinstance(active_profile.tool_confirmation, dict):
            return None
        value = active_profile.tool_confirmation.get("default")
        return str(value) if value else None

    def _suggest_workspace_agent_name(self, source_name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(source_name)).strip("-._")
        return f"{slug or 'agent'}-workspace"

    def _suggest_workspace_llm_name(self, source_name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(source_name)).strip("-._")
        return f"{slug or 'llm'}-workspace"

    def _ensure_workspace_agent_profile(
        self,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        active_profile = self._engine.active_agent_profile
        if active_profile is None:
            self._write_error("No active agent selected.")
            return
        if active_profile.source == "workspace":
            on_ready(active_profile.name)
            return
        self._open_name_prompt(
            title=f"Clone Agent Before {action_label.title()}",
            placeholder=self._suggest_workspace_agent_name(active_profile.name),
            help_text="This agent has no workspace YAML yet. Enter the workspace name / filename to clone it first.",
            on_submit=lambda value: self._clone_agent_for_edit(
                active_profile.name,
                value,
                action_label=action_label,
                on_ready=on_ready,
            ),
        )

    def _ensure_workspace_llm_profile(
        self,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        profile_name = self._current_llm_profile_name()
        if not profile_name:
            self._write_error("No active LLM profile available to edit.")
            return
        profile = getattr(self._engine, "get_llm_profile", lambda name=None: None)(profile_name)
        if profile is None:
            self._write_error(f"Unknown LLM profile '{profile_name}'.")
            return
        if profile.get("source") == "workspace":
            on_ready(profile_name)
            return
        self._open_name_prompt(
            title=f"Clone LLM Before {action_label.title()}",
            placeholder=self._suggest_workspace_llm_name(profile_name),
            help_text="This LLM profile has no workspace YAML yet. Enter the workspace name / filename to clone it first.",
            on_submit=lambda value: self._clone_llm_for_edit(
                profile_name,
                value,
                action_label=action_label,
                on_ready=on_ready,
            ),
        )

    def _clone_agent_for_edit(
        self,
        source_name: str,
        new_name: str,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
        cloned = cloner(source_name, new_name)
        self._engine.set_active_agent_profile(new_name)
        self._refresh_suggestions()
        target_path = getattr(cloned, "source_path", None)
        if target_path:
            self._write_info(f"Cloned agent '{source_name}' to {target_path} for {action_label}.")
        else:
            self._write_info(f"Cloned agent '{source_name}' to workspace agent '{new_name}' for {action_label}.")
        self.call_after_refresh(lambda: on_ready(new_name))

    def _clone_llm_for_edit(
        self,
        source_name: str,
        new_name: str,
        *,
        action_label: str,
        on_ready: Callable[[str], None],
    ) -> None:
        if not hasattr(self._engine, "clone_llm_profile"):
            self._write_error("This runtime does not support cloning LLM profiles.")
            return
        cloned = self._engine.clone_llm_profile(source_name, new_name)
        self._engine.set_global_llm_override(new_name)
        self._refresh_suggestions()
        target_path = cloned.get("source_path") if isinstance(cloned, dict) else getattr(cloned, "source_path", None)
        if target_path:
            self._write_info(f"Cloned LLM profile '{source_name}' to {target_path} for {action_label}.")
        else:
            self._write_info(f"Cloned LLM profile '{source_name}' to workspace profile '{new_name}' for {action_label}.")
        self.call_after_refresh(lambda: on_ready(new_name))

    def _save_workspace_agent_profile(
        self,
        profile_name: str,
        *,
        llm_profile: str | None,
        tools: list[str] | None,
        extra_prompts: list[str],
        tool_confirmation_default: str | None,
        tool_confirmation_overrides: dict[str, str],
    ) -> None:
        updater = getattr(self._engine, "update_agent", None) or getattr(self._engine, "update_agent_profile")
        updater(
            profile_name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=tool_confirmation_overrides,
        )
        self._refresh_suggestions()
        self._sync_ui_from_engine()

    def _edit_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        llm_profile = self._current_llm_profile_name()
        return (
            PickerOption(
                "agent",
                f"Agent Config: {active_profile.name if active_profile else 'none'}",
                description="Edit active agent llm, prompts, and default confirmation",
                search_text="agent config llm prompts confirmation",
            ),
            PickerOption(
                "mode",
                f"Mode Config: {active_mode.name if active_mode else 'none'}",
                description="Edit the active mode markdown",
                search_text="mode config markdown",
            ),
            PickerOption(
                "llm",
                f"LLM Config: {llm_profile or 'none'}",
                description="Edit the current LLM profile config",
                search_text="llm config provider model parameters",
            ),
            PickerOption(
                "tools",
                f"Tool Selection: {active_profile.name if active_profile else 'none'}",
                description="Edit the active agent tool allowlist",
                search_text="tool selection allowlist",
            ),
            PickerOption(
                "tool_policies",
                f"Tool Policies: {active_profile.name if active_profile else 'none'}",
                description="Edit per-tool confirmation overrides",
                search_text="tool policies overrides confirmation",
            ),
        )

    def _clone_category_options(self) -> tuple[PickerOption, ...]:
        active_profile = self._engine.active_agent_profile
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        llm_profile = self._current_llm_profile_name()
        return (
            PickerOption(
                "agent",
                f"Agent Config: {active_profile.name if active_profile else 'none'}",
                description="Clone the active agent profile into the workspace",
                search_text="clone agent profile workspace",
            ),
            PickerOption(
                "mode",
                f"Mode Config: {active_mode.name if active_mode else 'none'}",
                description="Clone the active mode",
                search_text="clone mode markdown",
            ),
            PickerOption(
                "llm",
                f"LLM Config: {llm_profile or 'none'}",
                description="Clone the current LLM profile into the workspace",
                search_text="clone llm profile workspace",
            ),
        )

    def _open_edit_asset_picker(self) -> None:
        self._show_picker(
            title="Edit Asset",
            options=self._edit_category_options(),
            current_value=None,
            on_select=self._handle_edit_asset_selection,
            help_text="Choose which config asset to edit.",
        )

    def _open_clone_asset_picker(self) -> None:
        self._show_picker(
            title="Clone Asset",
            options=self._clone_category_options(),
            current_value=None,
            on_select=self._handle_clone_asset_selection,
            help_text="Choose which config asset to clone.",
        )

    def _open_name_prompt(
        self,
        *,
        title: str,
        placeholder: str,
        help_text: str,
        on_submit: Callable[[str], None],
    ) -> None:
        def _handle_submit(value: str | None) -> None:
            if value is None:
                return
            try:
                on_submit(value)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            NameInputScreen(title=title, placeholder=placeholder, help_text=help_text),
            callback=_handle_submit,
        )

    def _open_text_editor(
        self,
        *,
        title: str,
        help_text: str,
        initial_text: str,
        on_submit: Callable[[str], None],
    ) -> None:
        def _handle_submit(text: str | None) -> None:
            if text is None:
                return
            try:
                on_submit(text)
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            TextEditorScreen(title=title, help_text=help_text, initial_text=initial_text),
            callback=_handle_submit,
        )

    def _handle_edit_asset_selection(self, selected_value: str) -> None:
        openers = {
            "agent": self._open_agent_editor,
            "mode": self._open_mode_editor,
            "llm": self._open_llm_profile_editor,
            "tools": self._open_tool_selection_picker,
            "tool_policies": self._open_tool_policy_editor,
        }
        opener = openers.get(selected_value)
        if opener is None:
            self._write_error(f"Unsupported edit target: {selected_value}")
            return
        self.call_after_refresh(opener)

    def _handle_clone_asset_selection(self, selected_value: str) -> None:
        placeholder = "new-name"
        if selected_value == "agent":
            placeholder = "my-agent-safe"
        elif selected_value == "mode":
            placeholder = "review-copy"
        elif selected_value == "llm":
            placeholder = "my-llm-profile"
        self._open_name_prompt(
            title=f"Clone {selected_value.replace('_', ' ').title()}",
            placeholder=placeholder,
            help_text="Enter the new workspace name / filename.",
            on_submit=lambda value: self._clone_selected_asset(selected_value, value),
        )

    def _open_agent_editor(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            self._ensure_workspace_agent_profile(
                action_label="editing agent settings",
                on_ready=self._open_agent_editor,
            )
            return
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        payload = {
            "llm_profile": active_profile.llm_profile,
            "extra_prompts": list(active_profile.extra_prompts),
            "tool_confirmation_default": self._active_profile_default_confirmation(active_profile),
        }
        self._open_text_editor(
            title=f"Edit Agent Config: {profile_name}",
            help_text="Edit llm_profile, extra_prompts, and tool_confirmation_default as YAML. Ctrl+S saves.",
            initial_text=_dump_yaml_text(payload),
            on_submit=lambda text: self._apply_agent_yaml_edit(profile_name, text),
        )

    def _apply_agent_yaml_edit(self, profile_name: str, text: str) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")

        data = _load_yaml_mapping(text, label="Agent config")
        allowed_keys = {"llm_profile", "extra_prompts", "tool_confirmation_default"}
        unexpected = sorted(set(data) - allowed_keys)
        if unexpected:
            raise ValueError(f"Unsupported agent config keys: {', '.join(unexpected)}")

        llm_value = data.get("llm_profile", active_profile.llm_profile)
        llm_profile = str(llm_value).strip() if llm_value not in {None, ""} else None

        prompts_value = data.get("extra_prompts", list(active_profile.extra_prompts))
        if prompts_value is None:
            extra_prompts: list[str] = []
        elif isinstance(prompts_value, list):
            extra_prompts = [str(item).strip() for item in prompts_value if str(item).strip()]
        else:
            raise ValueError("Agent config 'extra_prompts' must be a list.")

        default_value = data.get(
            "tool_confirmation_default",
            self._active_profile_default_confirmation(active_profile),
        )
        if default_value in {None, "", "inherit", INHERIT_POLICY}:
            tool_confirmation_default = None
        else:
            tool_confirmation_default = str(default_value).strip()
            if tool_confirmation_default not in {"allow", "confirm", "deny"}:
                raise ValueError("tool_confirmation_default must be allow, confirm, deny, or null.")

        tools = list(active_profile.tools) if active_profile.tools is not None else None
        overrides = self._active_profile_policy_overrides(active_profile)
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=overrides,
        )
        self._write_info(f"Saved workspace agent '{profile_name}'.")

    def _open_mode_editor(self) -> None:
        active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
        if active_mode is None:
            self._write_error("No active mode selected.")
            return
        if not hasattr(self._engine, "get_mode_text"):
            self._write_error("This runtime does not support editing modes.")
            return
        initial_text = self._engine.get_mode_text(active_mode.name)
        self._open_text_editor(
            title=f"Edit Mode: {active_mode.name}",
            help_text="Edit the mode markdown with YAML front matter. Ctrl+S saves.",
            initial_text=initial_text,
            on_submit=lambda text: self._apply_mode_edit(active_mode.name, text),
        )

    def _apply_mode_edit(self, mode_name: str, text: str) -> None:
        if not hasattr(self._engine, "update_mode"):
            raise ValueError("This runtime does not support editing modes.")
        target_path = self._engine.update_mode(mode_name, markdown_text=text)
        self._refresh_suggestions()
        self._write_info(f"Saved mode '{mode_name}' to {target_path}.")

    def _open_llm_profile_editor(self) -> None:
        self._ensure_workspace_llm_profile(
            action_label="editing llm config",
            on_ready=self._open_workspace_llm_profile_editor,
        )

    def _open_workspace_llm_profile_editor(self, profile_name: str) -> None:
        profile = getattr(self._engine, "get_llm_profile", lambda name=None: None)(profile_name)
        if profile is None:
            self._write_error(f"Unknown LLM profile '{profile_name}'.")
            return
        self._open_text_editor(
            title=f"Edit LLM Config: {profile_name}",
            help_text="Edit provider, model, and parameters as YAML. Ctrl+S saves.",
            initial_text=_dump_yaml_text(profile.get("config", {})),
            on_submit=lambda text: self._apply_llm_yaml_edit(profile_name, text),
        )

    def _apply_llm_yaml_edit(self, profile_name: str, text: str) -> None:
        if not hasattr(self._engine, "update_llm_profile"):
            raise ValueError("This runtime does not support editing LLM profiles.")
        data = _load_yaml_mapping(text, label="LLM config")
        self._engine.update_llm_profile(profile_name, profile_config=data)
        self._refresh_suggestions()
        self._write_info(f"Saved workspace LLM profile '{profile_name}'.")

    def _open_tool_policy_editor(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            profile_name = active_profile.name
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        overrides = self._active_profile_policy_overrides(active_profile)
        initial_text = _dump_yaml_text(overrides) if overrides else "{}"

        def _handle_submit(payload: dict[str, str] | None) -> None:
            if payload is None:
                return
            action = payload.get("action")
            text = payload.get("text", "")
            try:
                if action == "apply":
                    overrides = self._parse_tool_policy_yaml(text)
                    self._engine.set_last_used_profile_tool_policies(profile_name, overrides)
                    self._write_info(f"Saved last-used tool confirmation overrides for '{profile_name}'.")
                elif action == "reset":
                    self._engine.reset_last_used_profile_tool_policies(profile_name)
                    self._write_info(f"Reset tool confirmation overrides for '{profile_name}' to defaults.")
                elif action == "save_default":
                    self._ensure_workspace_agent_profile(
                        action_label="saving tool policy defaults",
                        on_ready=lambda target_name: self._apply_tool_policy_yaml_edit(target_name, text),
                    )
            except Exception as exc:
                self._write_error(str(exc))
            finally:
                self._sync_ui_from_engine()

        self.push_screen(
            ToolPolicyEditorScreen(
                title=f"Edit Tool Policies: {profile_name}",
                help_text="Apply saves last-used overrides. Reset clears them. Save as Default writes the workspace agent YAML.",
                initial_text=initial_text,
            ),
            callback=_handle_submit,
        )

    def _parse_tool_policy_yaml(self, text: str) -> dict[str, str]:
        data = _load_yaml_mapping(text, label="Tool policy overrides")
        normalized: dict[str, str] = {}
        for tool_name, policy in data.items():
            if not str(tool_name).strip():
                raise ValueError("Tool policy keys must be non-empty strings.")
            policy_value = str(policy).strip()
            if policy_value not in {"allow", "confirm", "deny"}:
                raise ValueError("Tool policy values must be allow, confirm, or deny.")
            normalized[str(tool_name)] = policy_value
        return normalized

    def _apply_tool_policy_yaml_edit(self, profile_name: str, text: str) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized = self._parse_tool_policy_yaml(text)

        tools = list(active_profile.tools) if active_profile.tools is not None else None
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=active_profile.llm_profile,
            tools=tools,
            extra_prompts=list(active_profile.extra_prompts),
            tool_confirmation_default=self._active_profile_default_confirmation(active_profile),
            tool_confirmation_overrides=normalized,
        )
        if hasattr(self._engine, "reset_last_used_profile_tool_policies"):
            self._engine.reset_last_used_profile_tool_policies(profile_name)
        self._write_info(f"Saved tool confirmation overrides for '{profile_name}'.")

    def _save_tool_selection_default(self, profile_name: str, tools: list[str] | None) -> None:
        active_profile = self._engine.get_agent_profile(profile_name, effective=False)
        if active_profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        self._save_workspace_agent_profile(
            profile_name,
            llm_profile=active_profile.llm_profile,
            tools=tools,
            extra_prompts=list(active_profile.extra_prompts),
            tool_confirmation_default=self._active_profile_default_confirmation(active_profile),
            tool_confirmation_overrides=self._active_profile_policy_overrides(active_profile),
        )
        if hasattr(self._engine, "reset_last_used_profile_tools"):
            self._engine.reset_last_used_profile_tools(profile_name)
        self._write_info(
            f"Saved default tool allowlist for '{profile_name}': "
            f"{'all tools' if tools is None else f'{len(tools)} selected'}."
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        widget_id = event.input.id or ""
        if widget_id == "main-input":
            await self._handle_main_input(event.value)
            return

    async def _handle_main_input(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text:
            return

        input_widget = self.query_one("#main-input", Input)
        input_widget.value = ""
        if self._pending_input_request is not None and self._active_run is not None:
            self._write_user(text)
            request_id = str(
                self._pending_input_request.get("request_id")
                or self._pending_input_request.get("prompt_id")
                or ""
            )
            if self._pending_input_request.get("type") == "interaction_requested":
                try:
                    response_payload = parse_interaction_response(self._pending_input_request, text)
                except ValueError as exc:
                    self._write_error(str(exc))
                    self._set_main_input_placeholder(interaction_placeholder(self._pending_input_request))
                    return
                resolved = bool(request_id) and self._active_run.resolve_interaction(request_id, response_payload)
            else:
                resolved = bool(request_id) and self._active_run.resolve_user_input(request_id, text)
            if not resolved:
                self._write_error("The pending prompt is no longer active.")
            self._pending_input_request = None
            self._set_main_input_placeholder()
            return
        normalized_text = text.lower()
        if self._busy and normalized_text not in {"/stop", "/cancel"}:
            self._write_info("A run is already in progress.")
            return

        try:
            if text.startswith("/"):
                self._busy = True
                self._write_user(text)
                if text.lower() == "/copy":
                    self.action_copy_last_response()
                    return
                if text.lower() == "/copy-all":
                    self.action_copy_output()
                    return
                command_output, should_exit = await asyncio.to_thread(self._run_command_capture, text)
                if command_output:
                    self._write_info(command_output)
                if should_exit:
                    self.exit()
                    return
                self._sync_ui_from_engine()
            else:
                self._busy = True
                self._write_user(text)
                self._active_run = self._engine.start_request(
                    text,
                    self._cli_context,
                    bridge_user_input=True,
                )
                self._live_run_status = "running"
                self._refresh_ui()
        except Exception as exc:
            logger.error("Failed to process Textual input: %s", exc, exc_info=True)
            self._write_error(str(exc))
        finally:
            if self._active_run is None:
                self._busy = False
            input_widget.focus()
            if self._active_run is None:
                self._sync_ui_from_engine()

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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "view-control-button":
            self.action_view_control()
        elif button_id == "view-run-button":
            self.action_view_run()
        elif button_id == "control-center-button":
            self.action_pick_asset()
        elif button_id in {"edit-asset-button", "edit-asset-button-secondary"}:
            self.action_edit_asset()
        elif button_id in {"clone-asset-button", "clone-asset-button-secondary"}:
            self.action_clone_asset()
        elif button_id == "reload-button":
            self.action_reload_runtime()
        elif button_id == "goto-chat-button":
            self.action_view_chat()

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._syncing_controls:
            return

        if event.select.value != event.value:
            return

        widget_id = event.select.id or ""
        value = str(event.value)
        if value == LOADING_OPTION:
            return
        try:
            if widget_id == "workspace-mode-select":
                self._apply_workspace_mode_selection(value)
            elif widget_id == "theme-select":
                self._apply_theme_selection(value)
            elif widget_id == "profile-select":
                self._apply_profile_selection(value)
            elif widget_id == "llm-select":
                self._apply_llm_selection(value)
            elif widget_id == "session-confirm-select":
                self._apply_session_confirmation_selection(value)
            self._sync_ui_from_engine()
        except Exception as exc:
            self._write_error(str(exc))
            self._sync_ui_from_engine()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._syncing_controls:
            return

        switch_id = event.switch.id or ""
        if switch_id == "auto-confirm-switch":
            if hasattr(self._engine, "set_last_used_auto_confirm_tools"):
                self._engine.set_last_used_auto_confirm_tools(bool(event.value))
            else:
                self._engine.auto_confirm_tools = bool(event.value)
            state = "enabled" if event.value else "disabled"
            self._write_info(f"Auto-confirm tools {state}.")
            self._sync_ui_from_engine()

    def on_key(self, event) -> None:
        if event.key != "space" or not isinstance(self.focused, SelectionList):
            return
        if self.focused.disabled or not self.focused.option_count:
            return
        event.prevent_default()
        event.stop()
        if self.focused.highlighted is None:
            self.focused.highlighted = 0
        self.focused.action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "profile-list":
            return
        option_index = getattr(event, "option_index", getattr(event, "index", None))
        if option_index is None or option_index >= len(self._profile_list_names):
            return
        profile_name = self._profile_list_names[option_index]
        try:
            if hasattr(self._engine, "set_last_used_active_profile"):
                self._engine.set_last_used_active_profile(profile_name)
            else:
                self._engine.set_active_agent_profile(profile_name)
            self._write_info(f"Activated agent profile: {profile_name}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        if event.selection_list.id != "skill-list" or event.selection_list.disabled:
            return
        option_index = getattr(event, "selection_index", getattr(event, "index", None))
        if option_index is None:
            return
        option = event.selection_list.get_option_at_index(option_index)
        value = str(option.value)
        if value == LOADING_OPTION:
            return
        skill_groups = self._skill_group_members(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else {}
        try:
            if self._is_skill_group_value(value):
                group_name = value[len(SKILL_GROUP_PREFIX):]
                member_values = skill_groups.get(group_name, ())
                if value in event.selection_list.selected:
                    for member_value in member_values:
                        self._engine.enable_skill(member_value)
                    self._write_info(
                        f"Enabled skill group: {group_name} ({len(member_values)} skills)."
                    )
                else:
                    for member_value in member_values:
                        self._engine.disable_skill(member_value)
                    self._write_info(
                        f"Disabled skill group: {group_name} ({len(member_values)} skills)."
                    )
            elif value in event.selection_list.selected:
                self._engine.enable_skill(value)
                self._write_info(f"Enabled skill: {value}")
            else:
                self._engine.disable_skill(value)
                self._write_info(f"Disabled skill: {value}")
            if hasattr(self._engine, "set_last_used_skills"):
                self._engine.set_last_used_skills(sorted(self._active_skill_name_set()))
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._refresh_suggestions()
            self._sync_ui_from_engine()

    def _clone_selected_asset(self, asset_name: str, new_name: str) -> None:
        active_profile = self._engine.active_agent_profile
        if asset_name == "agent":
            if active_profile is None:
                self._write_error("No active agent to clone.")
                return
            cloner = getattr(self._engine, "clone_agent", None) or getattr(self._engine, "clone_agent_profile")
            cloned = cloner(active_profile.name, new_name)
            self._engine.set_active_agent_profile(new_name)
            target_path = getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active agent to {target_path}.")
            else:
                self._write_info(f"Cloned active agent to workspace agent '{new_name}'.")
        elif asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                self._write_error("No active LLM profile to clone.")
                return
            if not hasattr(self._engine, "clone_llm_profile"):
                self._write_error("This runtime does not support cloning LLM profiles.")
                return
            cloned = self._engine.clone_llm_profile(profile_name, new_name)
            self._engine.set_global_llm_override(new_name)
            target_path = cloned.get("source_path") if isinstance(cloned, dict) else getattr(cloned, "source_path", None)
            if target_path:
                self._write_info(f"Cloned active LLM profile to {target_path}.")
            else:
                self._write_info(f"Cloned active LLM profile to workspace profile '{new_name}'.")
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                self._write_error("No active mode to clone.")
                return
            if not hasattr(self._engine, "clone_mode"):
                self._write_error("This runtime does not support cloning modes.")
                return
            target_path = self._engine.clone_mode(active_mode.name, new_name)
            if hasattr(self._engine, "set_last_used_mode"):
                self._engine.set_last_used_mode(new_name)
            else:
                self._engine.set_mode(new_name)
            self._write_info(f"Cloned active mode to {target_path}.")
        else:
            self._write_error(f"Unsupported clone target: {asset_name}")
            return

        self._refresh_suggestions()
        self._sync_ui_from_engine()

    def _confirm_delete_current_asset(self, asset_name: str) -> None:
        current_name = None
        if asset_name == "agent":
            current_name = self._engine.active_agent_profile.name if self._engine.active_agent_profile else None
        elif asset_name == "llm":
            current_name = self._current_llm_profile_name()
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            current_name = active_mode.name if active_mode is not None else None
        if not current_name:
            self._write_error(f"No active {asset_name} selected.")
            return
        self._show_picker(
            title=f"Delete {asset_name.title()}",
            options=(
                PickerOption("delete", f"Delete {current_name}", search_text="confirm delete"),
                PickerOption("cancel", "Cancel"),
            ),
            current_value=None,
            on_select=lambda value: self._delete_current_asset(asset_name) if value == "delete" else None,
            help_text=f"Delete the current {asset_name} config if it is workspace-backed.",
        )

    def _delete_current_asset(self, asset_name: str) -> None:
        if asset_name == "agent":
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            if not hasattr(self._engine, "delete_agent_profile"):
                self._write_error("This runtime does not support deleting agent profiles.")
                return
            target_path = self._engine.delete_agent_profile(active_profile.name)
            self._write_info(f"Deleted workspace agent '{active_profile.name}' from {target_path}.")
        elif asset_name == "llm":
            profile_name = self._current_llm_profile_name()
            if not profile_name:
                self._write_error("No active LLM profile selected.")
                return
            if not hasattr(self._engine, "delete_llm_profile"):
                self._write_error("This runtime does not support deleting LLM profiles.")
                return
            target_path = self._engine.delete_llm_profile(profile_name)
            self._write_info(f"Deleted workspace LLM profile '{profile_name}' from {target_path}.")
        elif asset_name == "mode":
            active_mode = self._engine.get_mode() if hasattr(self._engine, "get_mode") else None
            if active_mode is None:
                self._write_error("No active mode selected.")
                return
            if not hasattr(self._engine, "delete_mode"):
                self._write_error("This runtime does not support deleting modes.")
                return
            target_path = self._engine.delete_mode(active_mode.name)
            self._write_info(f"Deleted mode '{active_mode.name}' from {target_path}.")
        else:
            self._write_error(f"Unsupported delete target: {asset_name}")
            return
        self._refresh_suggestions()
        self._sync_ui_from_engine()

    def _save_selection_preset(self, preset_name: str) -> None:
        if not hasattr(self._engine, "save_textual_selection_preset"):
            raise ValueError("This runtime does not support selection presets.")
        target_path = self._engine.save_textual_selection_preset(preset_name)
        self._write_info(f"Saved selection preset '{preset_name}' to {target_path}.")
        self._sync_ui_from_engine()

    def _selection_preset_options(self) -> tuple[PickerOption, ...]:
        if not hasattr(self._engine, "list_textual_selection_presets"):
            return ()
        preset_names = self._engine.list_textual_selection_presets()
        options: list[PickerOption] = []
        for preset_name in preset_names:
            snapshot = self._engine.get_textual_selection_preset(preset_name) if hasattr(
                self._engine, "get_textual_selection_preset"
            ) else {}
            description_parts = [
                f"mode={snapshot.get('active_mode')}" if isinstance(snapshot, dict) and snapshot.get("active_mode") else "",
                (
                    f"profile={snapshot.get('active_profile')}"
                    if isinstance(snapshot, dict) and snapshot.get("active_profile")
                    else ""
                ),
                (
                    f"llm={snapshot.get('global_llm_profile')}"
                    if isinstance(snapshot, dict) and snapshot.get("global_llm_profile")
                    else ""
                ),
            ]
            options.append(
                PickerOption(
                    preset_name,
                    preset_name,
                    description=" | ".join(part for part in description_parts if part),
                    search_text="selection preset snapshot",
                )
            )
        return tuple(options)

    def _open_selection_preset_picker(self, action: str) -> None:
        options = self._selection_preset_options()
        if not options:
            self._write_error("No selection presets are available.")
            return
        self._show_picker(
            title=f"{action.title()} Selection Preset",
            options=options,
            current_value=None,
            on_select=lambda preset_name: self._apply_selection_preset_action(action, preset_name),
            help_text=f"Choose a preset to {action}.",
            empty_message="No selection presets are available.",
        )

    def _apply_selection_preset_action(self, action: str, preset_name: str) -> None:
        if action == "load":
            if not hasattr(self._engine, "apply_textual_selection_preset"):
                self._write_error("This runtime does not support selection presets.")
                return
            self._engine.apply_textual_selection_preset(preset_name)
            self._write_info(f"Loaded selection preset '{preset_name}'.")
        elif action == "delete":
            if not hasattr(self._engine, "delete_textual_selection_preset"):
                self._write_error("This runtime does not support selection presets.")
                return
            self._engine.delete_textual_selection_preset(preset_name)
            self._write_info(f"Deleted selection preset '{preset_name}'.")
        else:
            self._write_error(f"Unsupported preset action: {action}")
            return
        self._sync_ui_from_engine()

    def _open_tool_selection_picker(self, profile_name: str | None = None) -> None:
        if profile_name is None:
            active_profile = self._engine.active_agent_profile
            if active_profile is None:
                self._write_error("No active agent selected.")
                return
            profile_name = active_profile.name
        active_profile = self._engine.get_agent_profile(profile_name)
        if active_profile is None:
            return
        current_agent = str(getattr(active_profile, "agent", "") or self._engine.get_current_agent() or "")
        available_tools = tuple(self._engine.list_tools_for_agent(current_agent)) if current_agent else ()
        if not available_tools:
            self._write_error("No tools are available for the active agent.")
            return
        selected_tools = set(available_tools if active_profile.tools is None else active_profile.tools)
        tool_details = (
            {
                tool_name: self._engine.describe_tool(tool_name)
                for tool_name in available_tools
            }
            if hasattr(self._engine, "describe_tool")
            else {}
        )
        picker_options, grouped_values, initial_selected_values = self._build_nested_tool_picker_options(
            available_tools,
            selected_tools=selected_tools,
            tool_details=tool_details,
        )

        def _handle_selection(payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            action = str(payload.get("action") or "")
            selected_values = payload.get("values", [])
            selected_set = {
                value
                for value in selected_values
                if not self._is_skill_group_value(value)
            }
            tools = None if len(selected_set) >= len(available_tools) else sorted(selected_set)
            if action == "apply":
                self._engine.set_last_used_profile_tools(profile_name, tools)
                self._write_info(
                    f"Saved last-used tool allowlist for '{profile_name}': "
                    f"{'all tools' if tools is None else f'{len(selected_set)} selected'}."
                )
            elif action == "reset":
                self._engine.reset_last_used_profile_tools(profile_name)
                self._write_info(f"Reset tool allowlist for '{profile_name}' to defaults.")
            elif action == "save_default":
                self._ensure_workspace_agent_profile(
                    action_label="saving tool defaults",
                    on_ready=lambda target_name: self._save_tool_selection_default(target_name, tools),
                )

        self.push_screen(
            ToolSelectionScreen(
                title="Edit Allowed Tools",
                tools=tuple(picker_options),
                selected_values=initial_selected_values,
                help_text=(
                    "Apply saves last-used tools. Reset clears last-used overrides. "
                    "Save as Default writes the workspace agent YAML."
                ),
                grouped_values=grouped_values,
            ),
            callback=_handle_selection,
        )

    def _open_skill_selection_picker(self) -> None:
        available_skills = tuple(self._engine.list_skills()) if hasattr(self._engine, "list_skills") else ()
        if not available_skills:
            self._write_error("No skills are available.")
            return
        active_skill_names = self._active_skill_name_set()
        skill_groups = self._skill_group_members(available_skills)
        grouped_values = {
            self._skill_group_value(group_name): member_values
            for group_name, member_values in skill_groups.items()
        }
        picker_options: list[PickerOption] = []
        selected_values = set(active_skill_names)
        for group_name, member_values in skill_groups.items():
            group_value = self._skill_group_value(group_name)
            if member_values and all(member_value in active_skill_names for member_value in member_values):
                selected_values.add(group_value)
            picker_options.append(
                PickerOption(
                    group_value,
                    f"Group: {group_name}",
                    description=f"Toggle all {len(member_values)} skills in this group",
                    search_text=f"{group_name} group {' '.join(member_values)}",
                )
            )
            picker_options.extend(
                PickerOption(
                    skill_name,
                    f"  {skill_name}",
                    description=f"Group: {group_name}",
                    search_text=f"{skill_name} {group_name}",
                )
                for skill_name in member_values
            )

        def _handle_selection(payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            action = str(payload.get("action") or "")
            selected_values = payload.get("values", [])
            selected_set = {
                value
                for value in selected_values
                if not self._is_skill_group_value(value)
            }
            selected_skill_names = sorted(selected_set)
            if action == "apply":
                self._engine.set_last_used_skills(selected_skill_names)
                self._write_info(
                    f"Saved last-used skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                )
            elif action == "reset":
                self._engine.reset_last_used_skills()
                active_skills = sorted(self._active_skill_name_set())
                self._write_info(f"Reset skills to defaults: {', '.join(active_skills) if active_skills else 'none'}.")
            elif action == "save_default":
                self._engine.set_last_used_skills(selected_skill_names)
                self._engine.save_default_skills(selected_skill_names)
                self._write_info(
                    f"Saved default skills: {', '.join(selected_skill_names) if selected_skill_names else 'none'}."
                )
            self._refresh_suggestions()
            self._sync_ui_from_engine()

        self.push_screen(
            ToolSelectionScreen(
                title="Select Skills",
                tools=tuple(picker_options),
                selected_values=selected_values,
                help_text=(
                    "Apply saves last-used skills. Reset restores default skills. "
                    "Save as Default writes the default skill set to pocketcode.yml."
                ),
                empty_message="No matching skills.",
                filter_placeholder="Filter skills...",
                grouped_values=grouped_values,
            ),
            callback=_handle_selection,
        )

    def action_view_chat(self) -> None:
        self._current_view = "chat"
        self._refresh_ui()

    def action_view_control(self) -> None:
        self._current_view = "control"
        self._refresh_ui()

    def action_view_run(self) -> None:
        self._current_view = "run"
        self._refresh_ui()

    def action_edit_asset(self) -> None:
        self._open_edit_asset_picker()

    def action_clone_asset(self) -> None:
        self._open_clone_asset_picker()

    def action_pick_asset(self) -> None:
        self._open_asset_picker()

    def action_toggle_right_panel(self) -> None:
        self._show_right_panel = not self._show_right_panel
        self._workspace_mode = "balanced"
        self._write_info(f"Inspector panel {'shown' if self._show_right_panel else 'hidden'}.")
        self._refresh_ui()

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._refresh_suggestions()
            self._write_info("Reloaded plugins, agents, tools, and LLM mappings.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._sync_ui_from_engine()

    def action_clear_output(self) -> None:
        self._output_lines = []
        self._trimmed_output_line_count = 0
        self._load_text_area_text(self.query_one("#output", TextArea), "")
        self._write_info("Cleared output.")

    def action_copy_output(self) -> None:
        if not self._output_lines:
            self._write_error("No output to copy.")
            return
        text = "\n".join(self._output_lines)
        try:
            self.copy_to_clipboard(text)
            self._write_info("Copied full console output to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_copy_last_response(self) -> None:
        if not self._last_assistant_response:
            self._write_error("No assistant response available to copy.")
            return
        try:
            self.copy_to_clipboard(self._last_assistant_response)
            self._write_info("Copied last assistant response to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_complete_input(self) -> None:
        input_widget = self.query_one("#main-input", Input)
        prefix = input_widget.value
        if not prefix:
            return

        lowered_prefix = prefix.lower()
        for suggestion in self._suggestions:
            if suggestion.lower().startswith(lowered_prefix):
                input_widget.value = suggestion
                input_widget.cursor_position = len(suggestion)
                return


def run_textual_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    app = PocketCodeTextualApp(engine=engine, cli_context=cli_context)
    app.run()
