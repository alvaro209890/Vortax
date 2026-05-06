import unittest

from services.research_policy import cached_search_result, cross_check_status, detect_source_divergence, research_profile


SOURCES = [
    {
        "id": 1,
        "url": "https://www.hyundai.com/br/pt/creta",
        "title": "Hyundai Creta 2026 oficial",
        "snippet": "Especificacoes do Creta 2026",
        "extracted_text": "Creta 2026 tem motor e equipamentos divulgados pela Hyundai.",
        "source_type": "official",
        "quality_score": 88,
    },
    {
        "id": 2,
        "url": "https://motor1.com/news/creta-2026",
        "title": "Creta 2026 noticias",
        "snippet": "Detalhes do Creta 2026 no mercado brasileiro",
        "extracted_text": "Materia sobre Creta 2026 com preco R$ 160.000.",
        "source_type": "news",
        "quality_score": 74,
    },
]


class ResearchPolicyTests(unittest.TestCase):
    def test_reuses_cached_sources_for_same_non_fresh_query(self) -> None:
        result = cached_search_result("Creta 2026 especificacoes", SOURCES)

        self.assertIsNotNone(result)
        self.assertTrue(result["from_conversation_cache"])
        self.assertEqual(result["results"][0]["href"], "https://www.hyundai.com/br/pt/creta")

    def test_does_not_reuse_cache_when_user_requests_fresh_information(self) -> None:
        result = cached_search_result("preco atual Creta 2026 hoje", SOURCES)

        self.assertIsNone(result)

    def test_sensitive_queries_require_two_relevant_sources(self) -> None:
        status = cross_check_status("preco Creta 2026", SOURCES[:1])

        self.assertFalse(status["satisfied"])
        self.assertEqual(status["required_sources"], 2)

    def test_accented_sensitive_terms_are_detected(self) -> None:
        status = cross_check_status("notícia atual sobre segurança", SOURCES[:1])

        self.assertFalse(status["satisfied"])
        self.assertEqual(status["required_sources"], 2)

    def test_software_creation_does_not_require_research_sources(self) -> None:
        profile = research_profile("gere um site simples de calculadora para mim")

        self.assertTrue(profile["development_intent"])
        self.assertFalse(profile["search_intent"])
        self.assertEqual(profile["required_sources"], 0)

    def test_marks_possible_price_divergence(self) -> None:
        sources = [
            {**SOURCES[0], "extracted_text": "Preco divulgado R$ 150.000."},
            {**SOURCES[1], "extracted_text": "Preco divulgado R$ 160.000."},
        ]

        divergence = detect_source_divergence("preco Creta 2026", sources)

        self.assertTrue(divergence["has_divergence"])


if __name__ == "__main__":
    unittest.main()
