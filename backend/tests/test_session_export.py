import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from services.session_export import build_session_export_zip


class SessionExportTests(unittest.TestCase):
    def test_build_zip_structure(self):
        task_id = "export-test-task"

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "projetos" / task_id
            workspace.mkdir(parents=True)
            (workspace / "hello.txt").write_text("ola vortax", encoding="utf-8")

            task = {
                "id": task_id,
                "description": "teste export",
                "status": "done",
                "user_id": "local-dev-user",
            }

            with mock.patch("services.session_export.database") as db, mock.patch(
                "services.session_export.settings"
            ) as settings, mock.patch(
                "services.session_export.task_plan_store"
            ) as plan_store, mock.patch(
                "services.session_export.metrics"
            ) as metrics:
                settings.WORKSPACE_PATH = Path(tmp) / "projetos"
                db.get_task.return_value = task
                db.list_events.return_value = [
                    {"id": 1, "type": "user_message", "payload": {"content": "oi"}}
                ]
                db.list_sources.return_value = []
                db.list_generated_files.return_value = [
                    {"path": "hello.txt", "content_hash": "abc", "tool_origin": "shell_run"}
                ]
                db.list_generated_projects.return_value = []
                db.list_chat_images.return_value = []
                db.get_context.return_value = {"summary": "ok"}
                db.list_screenshots.return_value = []
                plan_store.list_steps.return_value = [
                    {"id": "s1", "label": "Entender", "status": "passed"}
                ]
                metrics.snapshot.return_value = {"counters": {"agent_runs": 1}}

                payload = build_session_export_zip(task_id, include_screenshot_images=False)

        self.assertGreater(len(payload), 50)
        with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("task.json", names)
            self.assertIn("plan.json", names)
            self.assertIn("events.jsonl", names)
            self.assertIn("files/hello.txt", names)
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["format"], "vortax-session-export")
            self.assertEqual(manifest["task_id"], task_id)


if __name__ == "__main__":
    unittest.main()
