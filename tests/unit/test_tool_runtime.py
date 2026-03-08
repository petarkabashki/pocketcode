from types import SimpleNamespace

from pocketcode.core.tool_runtime import ToolRuntime
from pocketcode.plugins.core.tools.filesystem import ReadFileTool
from pocketcode.plugins.core.tools.user_input import AskUserInputTool


def _build_runtime(tools=None) -> ToolRuntime:
    return ToolRuntime(
        tools
        or {
            "core.read_file": ReadFileTool,
            "core.ask_user_input": AskUserInputTool,
        }
    )


class TestToolDescriptions:
    def test_describe_tool_uses_tools_file_for_nested_group_path(self):
        runtime = _build_runtime()

        filesystem_tool = runtime.describe_tool("core.read_file")
        user_input_tool = runtime.describe_tool("core.ask_user_input")

        assert filesystem_tool["group_path"] == ["core", "filesystem"]
        assert user_input_tool["group_path"] == ["core", "user_input"]
        assert filesystem_tool["source_path"].endswith("tools/filesystem.py")
        assert user_input_tool["source_path"].endswith("tools/user_input.py")


class TestScopedToolConfirmation:
    def test_request_tool_confirmation_returns_scope_payload(self):
        runtime = _build_runtime()
        runtime._confirm_tool = SimpleNamespace(
            execute=lambda **kwargs: {
                "success": True,
                "approved": True,
                "approval_scope": "session",
                "response": "session",
            }
        )

        approved, scope = runtime._request_tool_confirmation(
            tool_name="core.read_file",
            arguments={"path": "notes.txt"},
            shared_store={},
            agent_name="core::agent",
        )

        assert approved is True
        assert scope == "session"

    def test_apply_confirmation_response_writes_session_scope(self):
        runtime = _build_runtime()
        shared_store = {
            "session_tool_confirmation": {"default_policy": None, "tool_policies": {}, "agent_policies": {}},
        }

        runtime._apply_confirmation_response(
            tool_name="core.read_file",
            shared_store=shared_store,
            approval_scope="session",
            agent_name="core::agent",
        )

        assert shared_store["session_tool_confirmation"]["tool_policies"] == {"core.read_file": "allow"}

    def test_apply_confirmation_response_does_not_persist_once_scope(self):
        runtime = _build_runtime()
        shared_store = {
            "session_tool_confirmation": {"default_policy": None, "tool_policies": {}, "agent_policies": {}},
        }

        runtime._apply_confirmation_response(
            tool_name="core.read_file",
            shared_store=shared_store,
            approval_scope="once",
            agent_name="core::agent",
        )

        assert shared_store["session_tool_confirmation"]["tool_policies"] == {}
