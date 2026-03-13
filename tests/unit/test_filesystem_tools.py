from __future__ import annotations

from pathlib import Path

from pocketcode.core_tools import filesystem as core_filesystem
from pocketcode.core_tools import file_ops as core_file_ops
from pocketcode.core.workspace_migration import _is_workspace_compat_shim
from pocketcode.core.workspace_module_loader import load_workspace_module


workspace_file_ops = load_workspace_module(
    ".pocketcode", "file_ops.tool.py"
)


class TestFilesystemHelpers:
    def test_write_and_read_file_round_trip(self, tmp_path):
        target = tmp_path / "notes" / "todo.txt"

        assert core_filesystem.write_file(str(target), "hello", root_path=tmp_path) is True
        assert core_filesystem.read_file(str(target), root_path=tmp_path) == "hello"

    def test_write_file_rejects_paths_outside_root(self, tmp_path):
        root = tmp_path / "workspace"
        root.mkdir()
        outside = tmp_path / "outside.txt"

        assert core_filesystem.write_file(str(outside), "blocked", root_path=root) is False
        assert outside.exists() is False

    def test_list_directory_recursive_returns_relative_paths(self, tmp_path):
        (tmp_path / "b_dir").mkdir()
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b_dir" / "nested.txt").write_text("b", encoding="utf-8")

        assert core_filesystem.list_directory(str(tmp_path), root_path=tmp_path) == ["a.txt", "b_dir"]
        assert core_filesystem.list_directory(str(tmp_path), recursive=True, root_path=tmp_path) == [
            "a.txt",
            "b_dir",
            "b_dir/nested.txt",
        ]

    def test_glob_files_returns_matches_relative_to_base_path(self, tmp_path):
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "app.log").write_text("log", encoding="utf-8")
        (tmp_path / "logs" / "app.txt").write_text("txt", encoding="utf-8")

        assert core_filesystem.glob_files("**/*.log", str(tmp_path), root_path=tmp_path) == ["logs/app.log"]


class TestFilesystemToolCompatibility:
    def test_workspace_shims_are_removed(self):
        assert not (_workspace_root() / "architect.filesystem.tool.py").exists()
        assert not (_workspace_root() / "coder.filesystem.tool.py").exists()

    def test_shim_marker_detection_matches_removed_shims(self, tmp_path):
        shim_path = tmp_path / "shim.tool.py"
        shim_path.write_text('"""Compatibility re-export."""\n', encoding="utf-8")
        assert _is_workspace_compat_shim(shim_path) is True

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


def _workspace_root():
    return Path(__file__).resolve().parents[2] / ".pocketcode"


class TestFileOpsHelpers:
    def test_extract_text_by_line_range(self, tmp_path):
        target = tmp_path / "sample.txt"
        target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

        result = core_file_ops.extract_text(
            path=str(target),
            start_line=2,
            end_line=3,
            root_path=tmp_path,
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
        store: dict[str, object] = {"filesystem_root": str(tmp_path)}

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
        store: dict[str, object] = {"filesystem_root": str(tmp_path)}

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

    def test_stage_replace_rejects_paths_outside_root(self, tmp_path):
        root = tmp_path / "workspace"
        root.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("hello\n", encoding="utf-8")

        result = core_file_ops.stage_text_replace(
            path=str(outside),
            match_text="hello",
            replacement="goodbye",
            shared_store={"filesystem_root": str(root)},
        )

        assert result["success"] is False
        assert "escapes the allowed root" in result["error"]
