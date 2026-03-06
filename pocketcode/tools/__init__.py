"""
Pocketcode Native Tools Package.

This package provides a collection of utility functions designed to be used as tools
by the Pocketcode AI assistant, managed via the PocketFlow framework.
"""

from ._workspace_plugin_loader import load_workspace_plugin_module

# Expose the core tool functions for easier import
from .system import execute_shell_command
from .filesystem import (
    read_file,
    write_file,
    create_directory,
    list_directory,
    glob_files
)
from .search import search_code_func, is_ripgrep_installed
from .user_input import (
    ask_user_buttons,
    ask_user_checklist,
    ask_user_confirmation,
    ask_user_input,
    ask_user_radio_group,
    AskUserButtonsTool,
    AskUserChecklistTool,
    AskUserInputTool,
    AskUserRadioGroupTool,
    ConfirmUserInputTool,
)

_workspace_git = load_workspace_plugin_module(".pocketcode", "plugins", "workspace_git", "tools", "git.py")
GitStatusTool = _workspace_git.GitStatusTool
GitDiffTool = _workspace_git.GitDiffTool
GitAddTool = _workspace_git.GitAddTool
GitCommitTool = _workspace_git.GitCommitTool
GitPullTool = _workspace_git.GitPullTool
GitPushTool = _workspace_git.GitPushTool

__all__ = [
    'execute_shell_command',
    'read_file',
    'write_file',
    'create_directory',
    'list_directory',
    'glob_files',
    'GitStatusTool',
    'GitDiffTool',
    'GitAddTool',
    'GitCommitTool',
    'GitPullTool',
    'GitPushTool',
    'search_code_func',
    'is_ripgrep_installed',
    'ask_user_input',
    'ask_user_buttons',
    'ask_user_radio_group',
    'ask_user_checklist',
    'ask_user_confirmation',
    'AskUserInputTool',
    'AskUserButtonsTool',
    'AskUserRadioGroupTool',
    'AskUserChecklistTool',
    'ConfirmUserInputTool',
]
