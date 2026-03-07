from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Backward-compatibility shim.
# Canonical implementation: .pocketcode/plugins/workspace_context/tools/context_elephant_store_tools.py

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".pocketcode"
    / "plugins"
    / "workspace_context"
    / "tools"
    / "context_elephant_store_tools.py"
)
_MODULE_NAME = "pocketcode.compat.workspace_context_elephant_store_tools"

if not _MODULE_PATH.is_file():
    raise ModuleNotFoundError(
        "Workspace context elephant store tools module is missing at "
        f"{_MODULE_PATH}."
    )

spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load module spec for '{_MODULE_PATH}'.")
module = importlib.util.module_from_spec(spec)
sys.modules[_MODULE_NAME] = module
spec.loader.exec_module(module)

ReadContextElephantStoreFileTool = module.ReadContextElephantStoreFileTool
WriteContextElephantStoreFileTool = module.WriteContextElephantStoreFileTool
AppendToContextElephantStoreFileTool = module.AppendToContextElephantStoreFileTool
GetContextElephantStoreSummaryTool = module.GetContextElephantStoreSummaryTool
CheckContextElephantStoreStatusTool = module.CheckContextElephantStoreStatusTool
ContextElephantStoreToolError = module.ContextElephantStoreToolError
ProjectNotFoundError = module.ProjectNotFoundError
InvalidContextElephantStoreFileNameError = module.InvalidContextElephantStoreFileNameError
ContextElephantStoreFileNotFoundError = module.ContextElephantStoreFileNotFoundError
WriteError = module.WriteError
ReadError = module.ReadError
SummarizationError = module.SummarizationError

__all__ = [
    "ReadContextElephantStoreFileTool",
    "WriteContextElephantStoreFileTool",
    "AppendToContextElephantStoreFileTool",
    "GetContextElephantStoreSummaryTool",
    "CheckContextElephantStoreStatusTool",
    "ContextElephantStoreToolError",
    "ProjectNotFoundError",
    "InvalidContextElephantStoreFileNameError",
    "ContextElephantStoreFileNotFoundError",
    "WriteError",
    "ReadError",
    "SummarizationError",
]
