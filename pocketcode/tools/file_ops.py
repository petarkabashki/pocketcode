# Backward-compatibility re-export shim.
# The canonical implementation lives in pocketcode/plugins/core/tools/file_ops.py.
from pocketcode.plugins.core.tools.file_ops import (  # noqa: F401
    ApplyStagedEditTool,
    CancelStagedEditTool,
    ExtractTextTool,
    SelectFilesystemEntryTool,
    StageTextReplaceTool,
    apply_staged_edit,
    cancel_staged_edit,
    extract_text,
    select_filesystem_entry,
    stage_text_replace,
)

__all__ = [
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
]
