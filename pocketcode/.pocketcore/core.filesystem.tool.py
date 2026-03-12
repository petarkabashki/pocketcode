from pocketcode.core_tools.filesystem import (
    CreateDirectoryTool,
    GlobFilesTool,
    ListFilesTool,
    ReadFileTool,
    WriteToFileTool,
)


TOOLS = {
    "read_file": ReadFileTool,
    "write_to_file": WriteToFileTool,
    "list_files": ListFilesTool,
    "create_directory": CreateDirectoryTool,
    "glob_files": GlobFilesTool,
}
