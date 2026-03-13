from __future__ import annotations

from typing import Any, Callable, Iterable

from .interaction_screens import InteractionControlsScreen, PromptInputScreen
from .picker_screens import AssetPickerScreen
from .shared import PickerOption


class TextualAppModalCoordinatorMixin:
    def _present_modal(
        self,
        screen: Any,
        *,
        modal_kind: str,
        modal_title: str | None = None,
        on_result: Callable[[Any], None] | None = None,
        sync_ui: bool = True,
    ) -> None:
        self._open_runtime_modal(modal_kind, modal_title=modal_title)

        def _handle_result(result: Any) -> None:
            with self._batch_ui_update(commit=sync_ui, hydrate_engine=sync_ui):
                self._close_runtime_modal()
                if on_result is not None:
                    try:
                        on_result(result)
                    except Exception as exc:
                        self._write_error(str(exc))

        self.push_screen(screen, callback=_handle_result)

    def _present_asset_picker_modal(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None,
        on_select: Callable[[str], None],
        help_text: str,
        empty_message: str,
    ) -> None:
        option_list = tuple(options)
        self._present_modal(
            AssetPickerScreen(
                title=title,
                options=option_list,
                current_value=current_value,
                help_text=help_text,
                empty_message=empty_message,
            ),
            modal_kind="asset_picker",
            modal_title=title,
            on_result=lambda selected_value: on_select(selected_value) if selected_value is not None else None,
        )

    def _present_prompt_input_modal(
        self,
        *,
        title: str,
        prompt: str,
        help_text: str,
        placeholder: str,
        initial_text: str,
        submit_label: str,
        on_submit: Callable[[str], None],
    ) -> None:
        self._present_modal(
            PromptInputScreen(
                title=title,
                prompt=prompt,
                help_text=help_text,
                placeholder=placeholder,
                initial_text=initial_text,
                submit_label=submit_label,
            ),
            modal_kind="prompt_input",
            modal_title=title,
            on_result=lambda value: on_submit(value) if value is not None else None,
        )

    def _present_interaction_controls_modal(
        self,
        *,
        title: str,
        request: dict[str, Any],
        on_submit: Callable[[str], None],
    ) -> None:
        self._present_modal(
            InteractionControlsScreen(request=request),
            modal_kind="interaction_controls",
            modal_title=title,
            on_result=lambda value: on_submit(value) if value is not None else None,
        )
