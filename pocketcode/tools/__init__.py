#%%
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
    git_status,
    git_diff,
    git_add,
    git_commit,
    git_pull,
    git_push
)
from .search import search_code, is_ripgrep_installed

# You might also define an 'all' list if needed for wildcard imports,
# though explicit imports are generally preferred.
__all__ = [
    # system.py
    'execute_shell_command',
    # filesystem.py
    'read_file',
    'write_file',
    'create_directory',
    'list_directory',
    'glob_files',
    # git.py
    'git_status',
    'git_diff',
    'git_add',
    'git_commit',
    'git_pull',
    'git_push',
    # search.py
    'search_code',
    'is_ripgrep_installed', # Expose the check function as well
]

# Potential future addition: A function or class here to gather all tool definitions
# from tool_definitions.py for registration with PocketFlow.