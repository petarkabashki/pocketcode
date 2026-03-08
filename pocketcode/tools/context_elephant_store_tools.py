from __future__ import annotations

from pocketcode.core.workspace_module_loader import load_workspace_plugin_module

# Backward-compatibility shim.
# Canonical implementation: .pocketcode/plugins/workspace_context/tools/context_elephant_store_tools.py

module = load_workspace_plugin_module(
    ".pocketcode",
    "plugins",
    "workspace_context",
    "tools",
    "context_elephant_store_tools.py",
)

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
