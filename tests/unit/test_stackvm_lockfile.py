import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from pocketcode.core.stackvm_lockfile import _parse_remote_ref, is_remote_ref, StackVmLockfile, LockfileEntry

class TestStackVmLockfile(unittest.TestCase):
    def test_is_remote_ref(self):
        self.assertTrue(is_remote_ref("github:user/repo/file.vm"))
        self.assertTrue(is_remote_ref("git+https://github.com/user/repo.git/file.vm"))
        self.assertFalse(is_remote_ref("local/file.vm"))
        self.assertFalse(is_remote_ref("vm.core"))

    def test_parse_github_ref(self):
        url, subpath = _parse_remote_ref("github:user/repo/path/to/file.vm")
        self.assertEqual(url, "https://github.com/user/repo.git")
        self.assertEqual(subpath, "path/to/file.vm")

    def test_parse_github_ref_default(self):
        url, subpath = _parse_remote_ref("github:user/repo")
        self.assertEqual(url, "https://github.com/user/repo.git")
        self.assertEqual(subpath, "index.vm")

    def test_parse_git_plus_ref(self):
        url, subpath = _parse_remote_ref("git+https://example.com/repo.git/src/main.vm")
        self.assertEqual(url, "https://example.com/repo.git")
        self.assertEqual(subpath, "src/main.vm")

    @patch("pocketcode.core.stackvm_lockfile.Path.write_text")
    @patch("pocketcode.core.stackvm_lockfile.Path.is_file", return_value=False)
    def test_lockfile_add_entry(self, mock_is_file, mock_write_text):
        lockfile = StackVmLockfile(Path("/tmp/fake.lock.yaml"))
        entry = LockfileEntry("github:u/r/f", "url", "commit", "/cache/f")
        lockfile.add_entry(entry)
        
        self.assertEqual(len(lockfile.entries), 1)
        self.assertTrue(mock_write_text.called)

if __name__ == "__main__":
    unittest.main()
