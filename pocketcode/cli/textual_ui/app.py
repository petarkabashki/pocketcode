from __future__ import annotations

from typing import Any, Dict

from pocketcode.core.engine import PocketCodeEngine

from .base import TextualAppBase
from .debugger_mixin import TextualAppDebuggerMixin
from .effects_mixin import TextualAppEffectsMixin
from .input_history_mixin import TextualAppInputHistoryMixin
from .interaction_mixin import TextualAppInteractionMixin
from .modal_coordinator_mixin import TextualAppModalCoordinatorMixin
from .rendering_mixin import TextualAppRenderingMixin
from .selection_mixin import TextualAppSelectionMixin
from .ui_state_mixin import TextualAppUiStateMixin
from .widget_sync_mixin import TextualAppWidgetSyncMixin


class PocketCodeTextualApp(
    TextualAppModalCoordinatorMixin,
    TextualAppUiStateMixin,
    TextualAppWidgetSyncMixin,
    TextualAppDebuggerMixin,
    TextualAppEffectsMixin,
    TextualAppInputHistoryMixin,
    TextualAppInteractionMixin,
    TextualAppSelectionMixin,
    TextualAppRenderingMixin,
    TextualAppBase,
):
    pass


def run_textual_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    app = PocketCodeTextualApp(engine=engine, cli_context=cli_context)
    app.run()
