import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import files as file_tools
from tools.web_fetch import _html_to_text, _safe_url


class FileEditRequiresReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.task_id = "t-edit-1"
        (self.workspace / self.task_id).mkdir()
        self.p_ws = mock.patch.object(file_tools.settings, "WORKSPACE_PATH", self.workspace)
        self.p_ws.start()
        self.p_sync = mock.patch.object(
            file_tools, "sync_task_workspace_files", return_value={"files": [], "projects": []}
        )
        self.p_sync.start()
        self.p_ann = mock.patch.object(file_tools, "annotate_workspace_files", return_value=0)
        self.p_ann.start()
        file_tools.clear_task_reads(self.task_id)

    def tearDown(self):
        self.p_ann.stop()
        self.p_sync.stop()
        self.p_ws.stop()
        self.tmp.cleanup()

    def test_edit_without_read_fails(self):
        file_tools.file_write(self.task_id, "a.py", "x = 1\n")
        file_tools.clear_task_reads(self.task_id)
        r = file_tools.file_edit(self.task_id, "a.py", "x = 1", "x = 2")
        self.assertFalse(r["success"])
        self.assertIn("file_read", r["error"])

    def test_edit_after_read_ok(self):
        file_tools.file_write(self.task_id, "a.py", "x = 1\n")
        file_tools.clear_task_reads(self.task_id)
        self.assertTrue(file_tools.file_read(self.task_id, "a.py")["success"])
        r = file_tools.file_edit(self.task_id, "a.py", "x = 1", "x = 2")
        self.assertTrue(r["success"])


class WebFetchHelpersTests(unittest.TestCase):
    def test_ssrf_block(self):
        self.assertIsNone(_safe_url("http://127.0.0.1/x"))
        self.assertIsNone(_safe_url("http://localhost/x"))
        self.assertIsNone(_safe_url("ftp://example.com"))
        self.assertTrue(_safe_url("https://example.com/docs").startswith("https://"))

    def test_html_to_text(self):
        html = "<html><head><style>x{}</style></head><body><h1>Hi</h1><p>Ok</p></body></html>"
        text = _html_to_text(html)
        self.assertIn("Hi", text)
        self.assertIn("Ok", text)
        self.assertNotIn("style", text.lower())


class ShellSessionTests(unittest.TestCase):
    def test_shell_exec_oneshot(self):
        from tools.shell_sessions import shell_exec

        async def _run():
            with mock.patch("tools.shell_sessions.run_shell", new=mock.AsyncMock(return_value={"success": True, "stdout": "ok"})):
                return await shell_exec("echo hi", "task-1", background=False)

        r = asyncio.run(_run())
        self.assertTrue(r["success"])
        self.assertEqual(r.get("mode"), "oneshot")

    def test_shell_view_unknown(self):
        from tools.shell_sessions import shell_view

        r = asyncio.run(shell_view("missing"))
        self.assertFalse(r["success"])


class RegistryExtendedTests(unittest.TestCase):
    def test_new_tools_registered(self):
        from agent.tools.registry import openai_tools_payload

        names = {t["function"]["name"] for t in openai_tools_payload()}
        for n in (
            "shell_exec",
            "shell_view",
            "shell_write",
            "shell_kill",
            "web_fetch",
            "web_search",
            "validate_project",
            "document_render",
            "file_read",
            "todo_write",
        ):
            self.assertIn(n, names)


if __name__ == "__main__":
    unittest.main()
