import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import files as file_tools


class FileToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.task_id = "task-files-1"
        (self.workspace / self.task_id).mkdir()
        self.patcher = mock.patch.object(file_tools.settings, "WORKSPACE_PATH", self.workspace)
        self.patcher.start()
        # avoid real DB
        self.db_patch = mock.patch.object(file_tools, "sync_task_workspace_files", return_value={"files": [], "projects": []})
        self.db_patch.start()
        self.ann_patch = mock.patch.object(file_tools, "annotate_workspace_files", return_value=0)
        self.ann_patch.start()

    def tearDown(self):
        self.ann_patch.stop()
        self.db_patch.stop()
        self.patcher.stop()
        self.tmp.cleanup()

    def test_write_read_edit_grep_glob(self):
        w = file_tools.file_write(self.task_id, "app.py", "def hello():\n    return 1\n")
        self.assertTrue(w["success"])
        r = file_tools.file_read(self.task_id, "app.py")
        self.assertTrue(r["success"])
        self.assertIn("def hello", r["content"])
        e = file_tools.file_edit(self.task_id, "app.py", "return 1", "return 2")
        self.assertTrue(e["success"])
        r2 = file_tools.file_read(self.task_id, "app.py")
        self.assertIn("return 2", r2["content"])
        g = file_tools.glob_files(self.task_id, "*.py")
        self.assertIn("app.py", g["matches"])
        hits = file_tools.grep_files(self.task_id, r"def hello", output_mode="content")
        self.assertTrue(hits["success"])
        self.assertGreaterEqual(len(hits["matches"]), 1)

    def test_path_traversal_blocked(self):
        with self.assertRaises(ValueError):
            file_tools.resolve_task_path(self.task_id, "../secret.txt")


if __name__ == "__main__":
    unittest.main()
