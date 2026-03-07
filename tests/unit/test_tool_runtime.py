from pocketcode.core.tool_runtime import ToolRuntime
from pocketcode.plugins.core.tools.filesystem import ReadFileTool
from pocketcode.plugins.core.tools.user_input import AskUserInputTool


class TestToolDescriptions:
    def test_describe_tool_uses_tools_file_for_nested_group_path(self):
        runtime = ToolRuntime(
            {
                "core.read_file": ReadFileTool,
                "core.ask_user_input": AskUserInputTool,
            }
        )

        filesystem_tool = runtime.describe_tool("core.read_file")
        user_input_tool = runtime.describe_tool("core.ask_user_input")

        assert filesystem_tool["group_path"] == ["core", "filesystem"]
        assert user_input_tool["group_path"] == ["core", "user_input"]
        assert filesystem_tool["source_path"].endswith("tools/filesystem.py")
        assert user_input_tool["source_path"].endswith("tools/user_input.py")
