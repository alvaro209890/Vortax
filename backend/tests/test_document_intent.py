import unittest

from services.document_intent import document_extensions_from_text, report_artifact_profile


class DocumentIntentTests(unittest.TestCase):
    def test_detects_explicit_document_extensions(self) -> None:
        self.assertEqual(document_extensions_from_text("gere um relatorio .md e um .pdf"), [".md", ".pdf"])

    def test_detects_common_document_words(self) -> None:
        self.assertEqual(document_extensions_from_text("crie uma planilha xlsx"), [".xlsx"])
        self.assertEqual(document_extensions_from_text("faca um PDF do contrato"), [".pdf"])
        self.assertEqual(document_extensions_from_text("crie slides pptx sobre vendas"), [".pptx"])
        self.assertEqual(document_extensions_from_text("gere um exel de custos"), [".xlsx"])
        self.assertEqual(document_extensions_from_text("corrija esse worl e me devolva"), [".docx"])
        self.assertEqual(document_extensions_from_text("gere um zip com os shapes finais"), [".zip"])

    def test_code_agent_prompt_content_does_not_invent_txt_or_xlsx_outputs(self) -> None:
        prompt = (
            "vertex '## Objetivo\n"
            "Crie um arquivo DOCX com o texto corrigido do documento de especies.\n"
            "O texto corrigido é:\n"
            "A espécie foi conferida em consulta à planilha da SEMA.'"
        )

        self.assertEqual(document_extensions_from_text(prompt), [".docx"])

    def test_plain_text_word_only_requires_txt_with_file_context(self) -> None:
        self.assertEqual(document_extensions_from_text("corrija o texto do documento"), [])
        self.assertEqual(document_extensions_from_text("gere um arquivo de texto com o resumo"), [".txt"])

    def test_shapefile_edit_requires_zip_but_excel_report_does_not(self) -> None:
        self.assertEqual(document_extensions_from_text("edite a tabela de atributos do shapefile"), [".zip"])
        self.assertEqual(document_extensions_from_text("crie um relatorio excel com base no shape"), [".xlsx"])

    def test_office_documents_require_artifact(self) -> None:
        from services.document_artifacts import artifact_profile

        profile = artifact_profile("gere um docx, um pptx, um xlsx e um csv sobre o projeto")

        self.assertTrue(profile["requires_artifact"])
        self.assertCountEqual(profile["requested_extensions"], [".docx", ".pptx", ".xlsx", ".csv"])
        self.assertIn(".docx", profile["preferred_files"])

    def test_json_requires_file_context_without_dot(self) -> None:
        self.assertEqual(document_extensions_from_text("uma api que retorna json"), [])
        self.assertEqual(document_extensions_from_text("crie um arquivo json"), [".json"])

    def test_uploaded_file_context_does_not_force_output_extension(self) -> None:
        prompt = (
            "analise o arquivo\n\n"
            "ARQUIVOS_ENVIADOS_PELO_USUARIO_VORTAX:\n"
            "- uploads/entrada.xlsx (.xlsx): Excel com dados.\n"
            "INSTRUCOES_DE_ARQUIVO_VORTAX:\n"
            "- Para XLSX, use openpyxl."
        )

        self.assertEqual(document_extensions_from_text(prompt), [])

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

    def test_pdf_request_requires_markdown_source(self) -> None:
        profile = report_artifact_profile("gere um PDF com a historia do Corinthians")

        self.assertTrue(profile["requires_markdown"])
        self.assertTrue(profile["wants_pdf"])
        self.assertEqual(profile["preferred_filename"], "DOCUMENTO_FONTE.md")


if __name__ == "__main__":
    unittest.main()
