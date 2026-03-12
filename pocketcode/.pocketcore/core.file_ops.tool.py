from pocketcode.core_tools.file_ops import (
    ApplyStagedEditTool,
    CancelStagedEditTool,
    ExtractTextTool,
    SelectFilesystemEntryTool,
    StageTextReplaceTool,
)


TOOLS = {
    "select_filesystem_entry": SelectFilesystemEntryTool,
    "extract_text": ExtractTextTool,
    "stage_text_replace": StageTextReplaceTool,
    "apply_staged_edit": ApplyStagedEditTool,
    "cancel_staged_edit": CancelStagedEditTool,
}
