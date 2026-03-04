"""
Pocketcode Native Tools Package.

This package provides a collection of utility functions designed to be used as tools
by the Pocketcode AI assistant, managed via the PocketFlow framework.
"""

# Expose the core tool functions for easier import
from .system import execute_shell_command
from .filesystem import (
    read_file,
    write_file,
    create_directory,
    list_directory,
    glob_files
)
from .git import (
    GitStatusTool, # Corrected import
    GitDiffTool,   # Corrected import
    GitAddTool,    # Corrected import
    GitCommitTool, # Corrected import
    GitPullTool,   # Corrected import
    GitPushTool    # Corrected import
)
from .search import search_code_func, is_ripgrep_installed
from .user_input import ask_user_input, ask_user_confirmation, AskUserInputTool, ConfirmUserInputTool

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
    'ask_user_confirmation',
    'AskUserInputTool',
    'ConfirmUserInputTool',
]
