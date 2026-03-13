from __future__ import annotations

from typing import Any, Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static, TextArea

from pocketcode.core.reference_syntax import normalize_registry_reference

from .shared import THEME_OPTIONS, UNSET_OPTION, WORKSPACE_VIEWS


def _normalize_agent_select_value(value: str | None, available_agents: Iterable[str]) -> str:
    option_values = {str(name) for name in available_agents}
    clean_value = str(value or "").strip()
    if not clean_value:
        return UNSET_OPTION
    if clean_value in option_values:
        return clean_value
    try:
        canonical_value = normalize_registry_reference(clean_value, allowed_kinds={"agent", "flow"})
    except ValueError:
        return UNSET_OPTION
    if canonical_value in option_values:
        return canonical_value
    return UNSET_OPTION


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
        workspace_view: str,
        default_agent: str | None,
        default_llm_profile: str | None,
        control_presentation: str,
        available_agents: Iterable[str],
        available_llm_profiles: Iterable[str],
    ) -> None:
        super().__init__()
        self._theme_name = str(theme_name)
        self._workspace_view = str(workspace_view)
        self._available_agents = tuple(str(name) for name in available_agents)
        self._available_llm_profiles = tuple(str(name) for name in available_llm_profiles)
        self._default_agent = _normalize_agent_select_value(default_agent, self._available_agents)
        self._default_llm_profile = str(default_llm_profile) if default_llm_profile else UNSET_OPTION
        self._control_presentation = "modal" if str(control_presentation).strip().lower() == "modal" else "inline"

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
            yield Static("Workspace View", classes="field-label")
            yield Select(
                [(item["label"], key) for key, item in WORKSPACE_VIEWS.items()],
                id="system-workspace-view-select",
                allow_blank=False,
                value=self._workspace_view,
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
            yield Static("Control Presentation", classes="field-label")
            yield Select(
                [("Inline", "inline"), ("Modal Popups", "modal")],
                id="system-control-presentation-select",
                allow_blank=False,
                value=self._control_presentation,
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
                "workspace_view": str(self.query_one("#system-workspace-view-select", Select).value),
                "default_agent": None if str(default_agent) == UNSET_OPTION else str(default_agent),
                "default_llm_profile": None if str(default_llm_profile) == UNSET_OPTION else str(default_llm_profile),
                "control_presentation": str(self.query_one("#system-control-presentation-select", Select).value),
            }
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "system-settings-apply":
            self.action_apply()
        elif button_id == "system-settings-cancel":
            self.action_cancel()
