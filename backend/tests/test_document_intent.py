import unittest

from services.document_intent import document_extensions_from_text, report_artifact_profile


class DocumentIntentTests(unittest.TestCase):
    def test_detects_explicit_document_extensions(self) -> None:
        self.assertEqual(document_extensions_from_text("gere um relatorio .md e um .pdf"), [".md", ".pdf"])

    def test_detects_common_document_words(self) -> None:
        self.assertEqual(document_extensions_from_text("crie uma planilha xlsx"), [".xlsx"])
        self.assertEqual(document_extensions_from_text("faca um PDF do contrato"), [".pdf"])

    def test_json_requires_file_context_without_dot(self) -> None:
        self.assertEqual(document_extensions_from_text("uma api que retorna json"), [])
        self.assertEqual(document_extensions_from_text("crie um arquivo json"), [".json"])

    def test_software_creation_requires_markdown_report(self) -> None:
        profile = report_artifact_profile("crie uma api python para estoque")

        self.assertTrue(profile["requires_markdown"])
        self.assertEqual(profile["preferred_filename"], "DOCUMENTACAO.md")

    def test_code_analysis_requires_markdown_report(self) -> None:
        profile = report_artifact_profile("analise o frontend deste repositorio")

        self.assertTrue(profile["requires_markdown"])
        self.assertEqual(profile["preferred_filename"], "RELATORIO_TECNICO.md")

    def test_common_question_does_not_require_markdown_report(self) -> None:
        profile = report_artifact_profile("explique cache em uma frase")

        self.assertFalse(profile["requires_markdown"])


if __name__ == "__main__":
    unittest.main()
