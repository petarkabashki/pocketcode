from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_workspace_plugin_module(*relative_parts: str) -> ModuleType:
    workspace_root = Path(__file__).resolve().parents[2]
    module_path = workspace_root.joinpath(*relative_parts)
    cache_key = f"pocketcode.workspace_loader.{module_path.stem}.{abs(hash(module_path))}"

    cached = sys.modules.get(cache_key)
    if cached is not None:
        return cached

    spec = importlib.util.spec_from_file_location(cache_key, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load workspace plugin module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module