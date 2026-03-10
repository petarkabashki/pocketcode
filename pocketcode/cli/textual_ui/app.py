from __future__ import annotations

from typing import Any, Dict

from pocketcode.core.engine import PocketCodeEngine

from .asset_management_mixin import TextualAppAssetManagementMixin
from .base import TextualAppBase
from .config_effects_mixin import TextualAppConfigEffectsMixin
from .config_editing_mixin import TextualAppConfigEditingMixin
from .control_center_mixin import TextualAppControlCenterMixin
from .debugger_mixin import TextualAppDebuggerMixin
from .effects_mixin import TextualAppEffectsMixin
from .input_history_mixin import TextualAppInputHistoryMixin
from .interaction_mixin import TextualAppInteractionMixin
from .modal_coordinator_mixin import TextualAppModalCoordinatorMixin
from .picker_model_mixin import TextualAppPickerModelMixin
from .rendering_mixin import TextualAppRenderingMixin
from .selection_effects_mixin import TextualAppSelectionEffectsMixin
from .selection_mixin import TextualAppSelectionMixin
from .ui_state_mixin import TextualAppUiStateMixin
from .widget_sync_mixin import TextualAppWidgetSyncMixin


class PocketCodeTextualApp(
    TextualAppModalCoordinatorMixin,
    TextualAppConfigEffectsMixin,
    TextualAppPickerModelMixin,
    TextualAppUiStateMixin,
    TextualAppWidgetSyncMixin,
    TextualAppSelectionEffectsMixin,
    TextualAppDebuggerMixin,
    TextualAppEffectsMixin,
    TextualAppInputHistoryMixin,
    TextualAppInteractionMixin,
    TextualAppAssetManagementMixin,
    TextualAppConfigEditingMixin,
    TextualAppControlCenterMixin,
    TextualAppSelectionMixin,
    TextualAppRenderingMixin,
    TextualAppBase,
):
    pass


def run_textual_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    app = PocketCodeTextualApp(engine=engine, cli_context=cli_context)
    app.run()
