"""Compatibility re-export for coder namespace filesystem tools.

The canonical implementation lives in pocketcode.core_tools.filesystem.
"""

from pocketcode.core_tools.filesystem import (  # noqa: F401
    CreateDirectoryTool,
    GlobFilesTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    WriteToFileTool,
    create_directory,
    glob_files,
    list_directory,
    read_file,
    write_file,
)

TOOLS = {
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "write_to_file": WriteToFileTool,
    "list_files": ListFilesTool,
    "create_directory": CreateDirectoryTool,
    "glob_files": GlobFilesTool,
}

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "WriteToFileTool",
    "ListFilesTool",
    "CreateDirectoryTool",
    "GlobFilesTool",
    "read_file",
    "write_file",
    "create_directory",
    "list_directory",
    "glob_files",
]
