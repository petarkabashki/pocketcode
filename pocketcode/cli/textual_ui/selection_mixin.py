from __future__ import annotations

# pyright: reportAttributeAccessIssue=false

from .shared import PickerOption, TEXTUAL_VIEWS


class TextualAppSelectionMixin:
    def _open_view_picker(self) -> None:
        self._show_picker(
            title="Select View",
            options=tuple(
                PickerOption(view_name, config["label"], config["description"])
                for view_name, config in TEXTUAL_VIEWS.items()
            ),
            current_value=self._cli_state.current_view,
            on_select=self._apply_view_selection,
            help_text="Choose the active Textual view.",
        )

    def _apply_view_selection(self, selected_value: str) -> None:
        self._set_current_view(selected_value, announce=True)
