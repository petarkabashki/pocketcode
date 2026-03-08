from types import SimpleNamespace

from pocketcode.core.tool_runtime import ToolRuntime
from pocketcode.plugins.core.tools.filesystem import ReadFileTool
from pocketcode.plugins.core.tools.user_input import AskUserInputTool


def _build_runtime(tools=None, **kwargs) -> ToolRuntime:
    return ToolRuntime(
        tools
        or {
            "core.read_file": ReadFileTool,
            "core.ask_user_input": AskUserInputTool,
        },
        **kwargs,
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

    def test_describe_tool_accepts_typed_reference(self):
        runtime = _build_runtime()

        filesystem_tool = runtime.describe_tool("tool:core.read_file")

        assert filesystem_tool["group_path"] == ["core", "filesystem"]
        assert filesystem_tool["source_path"].endswith("tools/filesystem.py")


class TestScopedToolConfirmation:
    def test_confirmation_config_normalizes_typed_tool_reference(self):
        runtime = _build_runtime(
            confirmation_config={
                "default_policy": "allow",
                "tool_policies": {
                    "tool:core.read_file": "deny",
                },
            }
        )

        policy = runtime._resolve_confirmation_policy(
            tool_name="core.read_file",
            shared_store={},
            agent_name=None,
            auto_confirm=False,
        )

        assert policy == "deny"

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


class TestFilesystemToolScoping:
    def test_execute_tool_accepts_typed_reference_against_canonical_allowlist(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        inside = workspace / "allowed.txt"
        inside.write_text("ok", encoding="utf-8")

        runtime = _build_runtime()

        result = runtime.execute_tool(
            "tool:core.read_file",
            {"path": str(inside)},
            {
                "filesystem_root": str(workspace),
                "active_allowed_tools": ["core.read_file"],
            },
            auto_confirm=True,
        )

        assert result["success"] is True
        assert result["content"] == "ok"

    def test_execute_tool_denies_reads_outside_runtime_root(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        inside = workspace / "allowed.txt"
        inside.write_text("ok", encoding="utf-8")
        outside = tmp_path / "blocked.txt"
        outside.write_text("no", encoding="utf-8")

        runtime = _build_runtime()

        allowed = runtime.execute_tool(
            "core.read_file",
            {"path": str(inside)},
            {"filesystem_root": str(workspace)},
            auto_confirm=True,
        )
        blocked = runtime.execute_tool(
            "core.read_file",
            {"path": str(outside)},
            {"filesystem_root": str(workspace)},
            auto_confirm=True,
        )

        assert allowed["success"] is True
        assert allowed["content"] == "ok"
        assert blocked["success"] is False
        assert "escapes the allowed root" in blocked["error"]
