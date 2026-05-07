import unittest

from services.document_intent import document_extensions_from_text


class DocumentIntentTests(unittest.TestCase):
    def test_detects_explicit_document_extensions(self) -> None:
        self.assertEqual(document_extensions_from_text("gere um relatorio .md e um .pdf"), [".md", ".pdf"])

    def test_detects_common_document_words(self) -> None:
        self.assertEqual(document_extensions_from_text("crie uma planilha xlsx"), [".xlsx"])
        self.assertEqual(document_extensions_from_text("faca um PDF do contrato"), [".pdf"])

    def test_json_requires_file_context_without_dot(self) -> None:
        self.assertEqual(document_extensions_from_text("uma api que retorna json"), [])
        self.assertEqual(document_extensions_from_text("crie um arquivo json"), [".json"])


if __name__ == "__main__":
    unittest.main()
