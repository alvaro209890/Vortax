import asyncio
import tempfile
import unittest
from pathlib import Path

from api import files as files_api
from api import tasks as tasks_api


class FakeTaskStore:
    def get(self, task_id: str) -> dict | None:
        return {"id": task_id, "description": "test", "status": "done"}


class FilesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.task_id = "task-preview-1"
        project = self.workspace / self.task_id
        project.mkdir()
        (project / "index.html").write_text("<!doctype html><title>Calculadora</title>", encoding="utf-8")

        self.original_files_workspace = files_api.settings.WORKSPACE_PATH
        self.original_tasks_workspace = tasks_api.settings.WORKSPACE_PATH
        self.original_files_store = files_api.task_store
        self.original_tasks_store = tasks_api.task_store
        files_api.settings.WORKSPACE_PATH = self.workspace
        tasks_api.settings.WORKSPACE_PATH = self.workspace
        files_api.task_store = FakeTaskStore()
        tasks_api.task_store = FakeTaskStore()

    def tearDown(self) -> None:
        files_api.settings.WORKSPACE_PATH = self.original_files_workspace
        tasks_api.settings.WORKSPACE_PATH = self.original_tasks_workspace
        files_api.task_store = self.original_files_store
        tasks_api.task_store = self.original_tasks_store
        self.tmp.cleanup()

    def test_preview_routes_are_registered_before_legacy_catchall(self) -> None:
        route_paths = [route.path for route in files_api.router.routes]
        preview_index = route_paths.index("/preview/{task_id}/")
        catchall_index = route_paths.index("/{file_path:path}")

        self.assertLess(preview_index, catchall_index)

    def test_task_files_are_listed_inside_only_that_task_directory(self) -> None:
        (self.workspace / "other-task").mkdir()
        (self.workspace / "other-task" / "leak.txt").write_text("nope", encoding="utf-8")

        files = files_api.list_task_workspace_files(self.task_id)

        self.assertEqual([item["path"] for item in files], ["index.html"])

    def test_task_zip_download_endpoint_builds_zip_response(self) -> None:
        response = asyncio.run(tasks_api.download_task_zip(self.task_id))

        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("vortax-task-pre.zip", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
