"""Compatibility shim for the workspace-owned context elephant store tools."""

from pocketcode.tools._workspace_plugin_loader import load_workspace_plugin_module

_workspace_context = load_workspace_plugin_module(
    ".pocketcode", "plugins", "workspace_context", "tools", "context_elephant_store_tools.py"
)

ReadContextElephantStoreFileTool = _workspace_context.ReadContextElephantStoreFileTool
WriteContextElephantStoreFileTool = _workspace_context.WriteContextElephantStoreFileTool
AppendToContextElephantStoreFileTool = _workspace_context.AppendToContextElephantStoreFileTool
GetContextElephantStoreSummaryTool = _workspace_context.GetContextElephantStoreSummaryTool
CheckContextElephantStoreStatusTool = _workspace_context.CheckContextElephantStoreStatusTool
ContextElephantStoreToolError = _workspace_context.ContextElephantStoreToolError
ProjectNotFoundError = _workspace_context.ProjectNotFoundError
InvalidContextElephantStoreFileNameError = _workspace_context.InvalidContextElephantStoreFileNameError
ContextElephantStoreFileNotFoundError = _workspace_context.ContextElephantStoreFileNotFoundError
WriteError = _workspace_context.WriteError
ReadError = _workspace_context.ReadError
SummarizationError = _workspace_context.SummarizationError
read_context_elephant_store_file = _workspace_context.read_context_elephant_store_file
write_context_elephant_store_file = _workspace_context.write_context_elephant_store_file
append_to_context_elephant_store_file = _workspace_context.append_to_context_elephant_store_file
get_context_elephant_store_summary = _workspace_context.get_context_elephant_store_summary
check_context_elephant_store_status = _workspace_context.check_context_elephant_store_status

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
    "read_context_elephant_store_file",
    "write_context_elephant_store_file",
    "append_to_context_elephant_store_file",
    "get_context_elephant_store_summary",
    "check_context_elephant_store_status",
]
