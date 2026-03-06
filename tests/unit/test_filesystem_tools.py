from __future__ import annotations

from pocketcode.plugins.core.tools import filesystem as core_filesystem
from pocketcode.tools._workspace_plugin_loader import load_workspace_plugin_module


architect_filesystem = load_workspace_plugin_module(
    ".pocketcode", "plugins", "architect", "tools", "filesystem.py"
)
coder_filesystem = load_workspace_plugin_module(
    ".pocketcode", "plugins", "coder", "tools", "filesystem.py"
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