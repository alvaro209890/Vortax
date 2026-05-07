import tempfile
import unittest
from pathlib import Path

from config import settings
from services.document_artifacts import (
    archive_edit_targets,
    artifact_profile,
    markdown_file_valid,
    markdown_to_html,
    pdf_file_valid,
    resolve_document_target,
)


class DocumentArtifactsTests(unittest.TestCase):
    def test_pdf_request_prefers_markdown_source_and_pdf_names(self) -> None:
        profile = artifact_profile("Gere um PDF com a historia do Corinthians")

        self.assertTrue(profile["wants_pdf"])
        self.assertTrue(profile["requires_artifact"])
        self.assertTrue(profile["preferred_markdown"].endswith(".md"))
        self.assertTrue(profile["preferred_pdf"].endswith(".pdf"))
        self.assertIn("corinthians", profile["preferred_pdf"])

    def test_detects_contextual_document_edit(self) -> None:
        profile = artifact_profile("melhore esse PDF e deixe mais completo")

        self.assertTrue(profile["edit_requested"])
        self.assertTrue(profile["wants_pdf"])

    def test_resolves_latest_previewable_document_target(self) -> None:
        files = [
            {"path": "old.pdf", "extension": ".pdf", "modified_at": 1, "size_bytes": 300},
            {"path": "versions/old.pdf", "extension": ".pdf", "modified_at": 3, "size_bytes": 300},
            {"path": "novo.pdf", "extension": ".pdf", "modified_at": 2, "size_bytes": 300},
        ]

        target = resolve_document_target("task", "melhore o pdf", files)

        self.assertEqual(target["path"], "novo.pdf")

    def test_archives_existing_document_for_edit(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                task_dir = settings.WORKSPACE_PATH / "task-doc"
                task_dir.mkdir()
                (task_dir / "relatorio.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 300)
                archived = archive_edit_targets(
                    "task-doc",
                    "melhore o pdf",
                    [{"path": "relatorio.pdf", "extension": ".pdf", "modified_at": 1, "size_bytes": 309}],
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0].startswith("versions/relatorio_"))

    def test_validates_markdown_and_pdf_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md = root / "doc.md"
            pdf = root / "doc.pdf"
            md.write_text("# Titulo\n\n" + "conteudo " * 20, encoding="utf-8")
            pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 300)

            self.assertTrue(markdown_file_valid(md))
            self.assertTrue(pdf_file_valid(pdf))

    def test_markdown_to_html_preserves_headings(self) -> None:
        html = markdown_to_html("# Titulo\n\n## Secao\n\nTexto")

        self.assertIn("<h1>Titulo</h1>", html)
        self.assertIn("<h2>Secao</h2>", html)


if __name__ == "__main__":
    unittest.main()
