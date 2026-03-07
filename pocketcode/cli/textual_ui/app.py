from __future__ import annotations

from typing import Any, Dict

from pocketcode.core.engine import PocketCodeEngine

from .asset_management_mixin import TextualAppAssetManagementMixin
from .base import TextualAppBase
from .config_editing_mixin import TextualAppConfigEditingMixin
from .control_center_mixin import TextualAppControlCenterMixin
from .interaction_mixin import TextualAppInteractionMixin
from .rendering_mixin import TextualAppRenderingMixin
from .selection_mixin import TextualAppSelectionMixin


class PocketCodeTextualApp(
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
