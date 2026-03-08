"""Backward-compatible import surface for core and workspace-owned tools.

Canonical built-in tool implementations live in ``pocketcode.plugins.core.tools``.
This package remains as a compatibility layer for older imports and for exposing
workspace-owned shim tools that do not belong to the built-in core plugin.
"""

from pocketcode.plugins.core.tools import (
    ApplyStagedEditTool,
    AskUserButtonsTool,
    AskUserChecklistTool,
    AskUserInputTool,
    AskUserRadioGroupTool,
    CancelStagedEditTool,
    ConfirmUserInputTool,
    CreateDirectoryTool,
    ExecuteCommandTool,
    ExtractTextTool,
    GlobFilesTool,
    ListFilesTool,
    ReadFileTool,
    SearchCodeTool,
    SelectFilesystemEntryTool,
    StageTextReplaceTool,
    WriteFileTool,
    WriteToFileTool,
    apply_staged_edit,
    ask_user_buttons,
    ask_user_checklist,
    ask_user_confirmation,
    ask_user_input,
    ask_user_radio_group,
    cancel_staged_edit,
    create_directory,
    execute_shell_command,
    extract_text,
    glob_files,
    is_ripgrep_installed,
    list_directory,
    read_file,
    search_code_func,
    select_filesystem_entry,
    stage_text_replace,
    write_file,
)

from pocketcode.core.workspace_module_loader import load_workspace_plugin_module

_workspace_git = load_workspace_plugin_module(".pocketcode", "plugins", "workspace_git", "tools", "git.py")
GitStatusTool = _workspace_git.GitStatusTool
GitDiffTool = _workspace_git.GitDiffTool
GitAddTool = _workspace_git.GitAddTool
GitCommitTool = _workspace_git.GitCommitTool
GitPullTool = _workspace_git.GitPullTool
GitPushTool = _workspace_git.GitPushTool

__all__ = [
    "execute_shell_command",
    "ExecuteCommandTool",
    "read_file",
    "write_file",
    "create_directory",
    "list_directory",
    "glob_files",
    "ReadFileTool",
    "WriteFileTool",
    "WriteToFileTool",
    "ListFilesTool",
    "CreateDirectoryTool",
    "GlobFilesTool",
    "SelectFilesystemEntryTool",
    "ExtractTextTool",
    "StageTextReplaceTool",
    "ApplyStagedEditTool",
    "CancelStagedEditTool",
    "select_filesystem_entry",
    "extract_text",
    "stage_text_replace",
    "apply_staged_edit",
    "cancel_staged_edit",
    "GitStatusTool",
    "GitDiffTool",
    "GitAddTool",
    "GitCommitTool",
    "GitPullTool",
    "GitPushTool",
    "search_code_func",
    "is_ripgrep_installed",
    "SearchCodeTool",
    "ask_user_input",
    "ask_user_buttons",
    "ask_user_radio_group",
    "ask_user_checklist",
    "ask_user_confirmation",
    "AskUserInputTool",
    "AskUserButtonsTool",
    "AskUserRadioGroupTool",
    "AskUserChecklistTool",
    "ConfirmUserInputTool",
]
