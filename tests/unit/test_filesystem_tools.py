from __future__ import annotations

from pocketcode.plugins.core.tools import filesystem as core_filesystem
from pocketcode.plugins.core.tools import file_ops as core_file_ops
from pocketcode.core.workspace_module_loader import load_workspace_plugin_module


architect_filesystem = load_workspace_plugin_module(
    ".pocketcode", "plugins", "architect", "tools", "filesystem.py"
)
coder_filesystem = load_workspace_plugin_module(
    ".pocketcode", "plugins", "coder", "tools", "filesystem.py"
)
workspace_file_ops = load_workspace_plugin_module(
    ".pocketcode", "tools", "file_ops.py"
)


class TestFilesystemHelpers:
    def test_write_and_read_file_round_trip(self, tmp_path):
        target = tmp_path / "notes" / "todo.txt"

        assert core_filesystem.write_file(str(target), "hello") is True
        assert core_filesystem.read_file(str(target)) == "hello"

    def test_list_directory_recursive_returns_relative_paths(self, tmp_path):
        (tmp_path / "b_dir").mkdir()
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b_dir" / "nested.txt").write_text("b", encoding="utf-8")

        assert core_filesystem.list_directory(str(tmp_path)) == ["a.txt", "b_dir"]
        assert core_filesystem.list_directory(str(tmp_path), recursive=True) == [
            "a.txt",
            "b_dir",
            "b_dir/nested.txt",
        ]

    def test_glob_files_returns_matches_relative_to_base_path(self, tmp_path):
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "app.log").write_text("log", encoding="utf-8")
        (tmp_path / "logs" / "app.txt").write_text("txt", encoding="utf-8")

        assert core_filesystem.glob_files("**/*.log", str(tmp_path)) == ["logs/app.log"]


class TestFilesystemToolCompatibility:
    def test_write_file_tool_alias_matches_write_to_file_tool(self):
        assert issubclass(core_filesystem.WriteFileTool, core_filesystem.WriteToFileTool)

    def test_architect_filesystem_module_reexports_core_symbols(self):
        assert architect_filesystem.ReadFileTool is core_filesystem.ReadFileTool
        assert architect_filesystem.WriteToFileTool is core_filesystem.WriteToFileTool
        assert architect_filesystem.WriteFileTool is core_filesystem.WriteFileTool
        assert architect_filesystem.glob_files is core_filesystem.glob_files

    def test_coder_filesystem_module_reexports_core_symbols(self):
        assert coder_filesystem.ReadFileTool is core_filesystem.ReadFileTool
        assert coder_filesystem.WriteToFileTool is core_filesystem.WriteToFileTool
        assert coder_filesystem.WriteFileTool is core_filesystem.WriteFileTool
        assert coder_filesystem.create_directory is core_filesystem.create_directory

    def test_workspace_file_ops_module_reexports_core_symbols(self):
        assert workspace_file_ops.extract_text(text="x\ny\n", start_line=2)["content"] == "y"
        assert workspace_file_ops.stage_text_replace(
            text="hello",
            match_text="hello",
            replacement="bye",
        )["updated_text"] == "bye"
        assert set(workspace_file_ops.TOOLS) == {
            "select_filesystem_entry",
            "extract_text",
            "stage_text_replace",
            "apply_staged_edit",
            "cancel_staged_edit",
        }


class TestFileOpsHelpers:
    def test_extract_text_by_line_range(self, tmp_path):
        target = tmp_path / "sample.txt"
        target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

        result = core_file_ops.extract_text(
            path=str(target),
            start_line=2,
            end_line=3,
        )

        assert result == {
            "success": True,
            "content": "two\nthree",
            "path": str(target),
            "start_line": 2,
            "end_line": 3,
        }

    def test_extract_text_by_boundary_patterns(self):
        result = core_file_ops.extract_text(
            text="alpha\nBEGIN\nkeep\nEND\nomega\n",
            start_pattern="BEGIN",
            end_pattern="END",
            include_boundaries=False,
        )

        assert result["success"] is True
        assert result["content"] == "keep"
        assert result["start_line"] == 3
        assert result["end_line"] == 3

    def test_stage_replace_by_match_and_apply(self, tmp_path):
        target = tmp_path / "edit.txt"
        target.write_text("hello world\nhello again\n", encoding="utf-8")
        store: dict[str, object] = {}

        staged = core_file_ops.stage_text_replace(
            path=str(target),
            match_text="hello",
            replacement="goodbye",
            count=1,
            shared_store=store,
        )

        assert staged["success"] is True
        assert staged["changes"] == 1
        assert staged["edit_id"]
        assert "goodbye world" in staged["updated_text"]
        assert target.read_text(encoding="utf-8") == "hello world\nhello again\n"

        applied = core_file_ops.apply_staged_edit(
            edit_id=staged["edit_id"],
            shared_store=store,
        )

        assert applied["success"] is True
        assert target.read_text(encoding="utf-8") == "goodbye world\nhello again\n"
        assert store["pending_file_edits"] == {}

    def test_stage_replace_by_line_range_can_be_cancelled(self, tmp_path):
        target = tmp_path / "edit_range.txt"
        target.write_text("a\nb\nc\nd\n", encoding="utf-8")
        store: dict[str, object] = {}

        staged = core_file_ops.stage_text_replace(
            path=str(target),
            start_line=2,
            end_line=3,
            replacement="beta\ngamma\n",
            shared_store=store,
        )

        assert staged["success"] is True
        assert staged["start_line"] == 2
        assert staged["end_line"] == 3

        cancelled = core_file_ops.cancel_staged_edit(
            edit_id=staged["edit_id"],
            shared_store=store,
        )

        assert cancelled["success"] is True
        assert target.read_text(encoding="utf-8") == "a\nb\nc\nd\n"
        assert store["pending_file_edits"] == {}
