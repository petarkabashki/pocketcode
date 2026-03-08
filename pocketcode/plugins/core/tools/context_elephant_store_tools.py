"""Compatibility aliases for workspace-owned context elephant store tools.

These tools are implemented by the workspace plugin at
``.pocketcode/plugins/workspace_context`` and are re-exported here only for
older imports that still expect a package-owned path.
"""

from pocketcode.core.workspace_module_loader import load_workspace_plugin_module

_workspace_context = load_workspace_plugin_module(
    ".pocketcode",
    "plugins",
    "workspace_context",
    "tools",
    "context_elephant_store_tools.py",
)

AppendToContextElephantStoreFileTool = _workspace_context.AppendToContextElephantStoreFileTool
CheckContextElephantStoreStatusTool = _workspace_context.CheckContextElephantStoreStatusTool
ContextElephantStoreFileNotFoundError = _workspace_context.ContextElephantStoreFileNotFoundError
ContextElephantStoreToolError = _workspace_context.ContextElephantStoreToolError
GetContextElephantStoreSummaryTool = _workspace_context.GetContextElephantStoreSummaryTool
InvalidContextElephantStoreFileNameError = _workspace_context.InvalidContextElephantStoreFileNameError
ProjectNotFoundError = _workspace_context.ProjectNotFoundError
ReadContextElephantStoreFileTool = _workspace_context.ReadContextElephantStoreFileTool
ReadError = _workspace_context.ReadError
SummarizationError = _workspace_context.SummarizationError
WriteContextElephantStoreFileTool = _workspace_context.WriteContextElephantStoreFileTool
WriteError = _workspace_context.WriteError

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
