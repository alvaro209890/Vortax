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

    def test_economic_comparison_rejects_biography_sources_without_indicators(self) -> None:
        sources = [
            {
                "url": "https://pt.wikipedia.org/wiki/Luiz_Inacio_Lula_da_Silva",
                "title": "Lula biografia",
                "snippet": "Presidente do Brasil de 2003 a 2010.",
                "extracted_text": "Biografia de Lula, presidente do Brasil de 2003 a 2010.",
                "source_type": "web",
                "quality_score": 82,
            },
            {
                "url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia/ex-presidentes/jair-bolsonaro",
                "title": "Jair Bolsonaro",
                "snippet": "Presidente do Brasil de 2019 a 2022.",
                "extracted_text": "Biografia institucional de Jair Bolsonaro.",
                "source_type": "official",
                "quality_score": 86,
            },
        ]

        query = "comparacao economica Lula Bolsonaro PIB inflacao desemprego 2003 2010 2019 2022"
        status = cross_check_status(query, sources)

        self.assertFalse(status["satisfied"])
        self.assertEqual(status["required_sources"], 3)
        self.assertEqual(status["source_count"], 0)
        self.assertIn("PIB", status["missing_topics"])
        self.assertIn("inflacao/IPCA", status["missing_topics"])
        self.assertIn("desemprego", status["missing_topics"])
        self.assertIsNone(cached_search_result(query, sources))

    def test_economic_comparison_accepts_data_sources_covering_indicators(self) -> None:
        sources = [
            {
                "url": "https://www.ibge.gov.br/explica/pib.php",
                "title": "IBGE PIB Brasil",
                "snippet": "PIB do Brasil e crescimento economico em series historicas.",
                "extracted_text": "PIB Produto Interno Bruto Brasil 2003 2010 2019 2022 crescimento economico.",
                "source_type": "data",
                "quality_score": 94,
            },
            {
                "url": "https://www.ibge.gov.br/explica/inflacao.php",
                "title": "IBGE IPCA",
                "snippet": "IPCA serie historica do Brasil.",
                "extracted_text": "IPCA Brasil 2003 2010 2019 2022 serie historica.",
                "source_type": "data",
                "quality_score": 94,
            },
            {
                "url": "https://www.ipea.gov.br/cartadeconjuntura/index.php/tag/desemprego/",
                "title": "Ipea desemprego Brasil",
                "snippet": "Taxa de desemprego e mercado de trabalho no Brasil.",
                "extracted_text": "Desemprego taxa de desocupacao PNAD Brasil 2003 2010 2019 2022.",
                "source_type": "data",
                "quality_score": 90,
            },
        ]

        status = cross_check_status(
            "comparacao economica Lula Bolsonaro PIB inflacao desemprego 2003 2010 2019 2022",
            sources,
        )

        self.assertTrue(status["satisfied"])
        self.assertEqual(status["source_count"], 3)
        self.assertEqual(status["data_source_count"], 3)
        self.assertFalse(status["missing_topics"])


if __name__ == "__main__":
    unittest.main()
