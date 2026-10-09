import asyncio
import tempfile
import unittest
from pathlib import Path

from api import files as files_api
from api import tasks as tasks_api
from auth import AuthUser


class FakeTaskStore:
    def get(self, task_id: str) -> dict | None:
        return {"id": task_id, "user_id": "test-user", "description": "test", "status": "done"}


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
        self.user = AuthUser(uid="test-user")

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

    def test_preview_index_endpoint_targets_generated_index_html(self) -> None:
        response = asyncio.run(files_api.preview_task_index(self.task_id, current_user=self.user))

        self.assertEqual(Path(response.path).name, "index.html")

    def test_preview_index_sets_cookie_when_token_provided(self) -> None:
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": f"/api/files/preview/{self.task_id}/",
            "headers": [],
            "query_string": b"token=test-token-123",
            "scheme": "http",
            "server": ("127.0.0.1", 8010),
        }
        req = Request(scope)
        response = asyncio.run(files_api.preview_task_index(self.task_id, request=req, current_user=self.user))

        self.assertEqual(Path(response.path).name, "index.html")
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"vx_preview_{self.task_id}=test-token-123", set_cookie)
        self.assertIn(f"Path=/api/files/preview/{self.task_id}/", set_cookie)

    def test_require_auth_extracts_preview_cookie_for_subresources(self) -> None:
        import auth
        from starlette.requests import Request
        cookie_header = f"vx_preview_{self.task_id}=preview-user-tok".encode("latin-1")
        scope = {
            "type": "http",
            "method": "GET",
            "path": f"/api/files/preview/{self.task_id}/style.css",
            "headers": [(b"cookie", cookie_header)],
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 8010),
            "client": ("127.0.0.1", 54321),
        }
        req = Request(scope)
        # Mock _verify_token to accept preview-user-tok
        original_verify = auth._verify_token
        try:
            auth._verify_token = lambda tok: AuthUser(uid="preview-user", name="Preview User")
            user = asyncio.run(auth.require_auth(req))
            self.assertEqual(user.uid, "preview-user")
        finally:
            auth._verify_token = original_verify

    def test_task_files_are_listed_inside_only_that_task_directory(self) -> None:
        (self.workspace / "other-task").mkdir()
        (self.workspace / "other-task" / "leak.txt").write_text("nope", encoding="utf-8")

        files = files_api.list_task_workspace_files(self.task_id)

        self.assertEqual([item["path"] for item in files], ["index.html"])
        self.assertEqual(files[0]["project_name"], "Projeto principal")
        self.assertEqual(files[0]["project_type"], "static_web")

    def test_task_files_are_grouped_by_nested_project(self) -> None:
        root = self.workspace / self.task_id
        (root / "app").mkdir()
        (root / "app" / "index.html").write_text("<!doctype html><title>App</title>", encoding="utf-8")
        (root / "app" / "style.css").write_text("body{}", encoding="utf-8")

        files = files_api.list_task_workspace_files(self.task_id)
        nested = [item for item in files if item["path"].startswith("app/")]

        self.assertEqual({item["project_root"] for item in nested}, {"app"})
        self.assertEqual({item["project_name"] for item in nested}, {"App"})

    def test_task_zip_download_endpoint_builds_zip_response(self) -> None:
        response = asyncio.run(tasks_api.download_task_zip(self.task_id, current_user=self.user))

        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("vortax-task-pre.zip", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
