import tempfile
import unittest
from pathlib import Path

from config import settings
from services.project_validation import detect_project_profile, validate_project_after_vertex


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, task_id, event_type, payload):
        self.events.append({"task_id": task_id, "type": event_type, "payload": payload})


class ProjectValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_python_project_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "main.py").write_text("print('ok')\n", encoding="utf-8")

            profile = detect_project_profile(project)

        self.assertEqual(profile["kind"], "python")
        self.assertTrue(profile["has_code"])

    async def test_python_project_passes_compile_validation(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-python-ok"
                task_dir.mkdir()
                (task_dir / "main.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-python-ok",
                    "vertex 'crie um script python'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "passed")
        self.assertTrue(any(event["type"] == "project_validation_result" for event in bus.events))

    async def test_python_project_fails_compile_validation(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-python-bug"
                task_dir.mkdir()
                (task_dir / "main.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-python-bug",
                    "vertex 'crie um script python'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("py_compile" in bug for bug in result["bugs"]))

    async def test_static_project_fails_missing_asset_validation(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-site-bug"
                task_dir.mkdir()
                (task_dir / "index.html").write_text('<script src="missing.js"></script>', encoding="utf-8")
                (task_dir / "DOCUMENTACAO.md").write_text("# Site\n\nDocumentacao.", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-site-bug",
                    "vertex 'crie um site html'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("missing.js" in bug for bug in result["bugs"]))

    async def test_site_project_requires_markdown_documentation(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-site-no-doc"
                task_dir.mkdir()
                (task_dir / "index.html").write_text("<!doctype html><title>Site</title>", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-site-no-doc",
                    "vertex 'crie um site html'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("DOCUMENTACAO.md" in bug for bug in result["bugs"]))

    async def test_site_project_passes_with_markdown_documentation(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-site-doc"
                task_dir.mkdir()
                (task_dir / "index.html").write_text("<!doctype html><title>Site</title>", encoding="utf-8")
                (task_dir / "DOCUMENTACAO.md").write_text("# Site\n\nDocumentacao do projeto.", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-site-doc",
                    "vertex 'crie um site html'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "passed")

    async def test_document_request_requires_requested_extension(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-pdf"
                task_dir.mkdir()
                (task_dir / "relatorio.md").write_text("# Relatorio", encoding="utf-8")
                bus = FakeBus()

                result = await validate_project_after_vertex(
                    "task-pdf",
                    "vertex 'gere um relatorio em PDF'",
                    bus,
                    vertex_result={"success": True},
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(".pdf" in bug for bug in result["bugs"]))


if __name__ == "__main__":
    unittest.main()
