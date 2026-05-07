import unittest

from services.source_quality import rank_search_results, source_quality_score, source_type_for_url


class SourceQualityTests(unittest.TestCase):
    def test_scores_official_sources_above_social_sources(self) -> None:
        official = source_quality_score("https://www.hyundai.com/br/pt", "Creta", "x" * 2000)
        social = source_quality_score("https://www.instagram.com/example", "Post", "x" * 200)

        self.assertGreater(official, social)

    def test_classifies_common_source_types(self) -> None:
        self.assertEqual(source_type_for_url("https://www.hyundai.com/br/pt"), "official")
        self.assertEqual(source_type_for_url("https://sidra.ibge.gov.br/tabela/5932"), "data")
        self.assertEqual(source_type_for_url("https://motor1.com/news/example"), "news")
        self.assertEqual(source_type_for_url("https://www.youtube.com/watch?v=abc"), "video")
        self.assertEqual(source_type_for_url("https://www.reddit.com/r/test"), "forum")

    def test_ranks_and_deduplicates_search_results(self) -> None:
        results = [
            {"title": "Post social", "href": "https://www.instagram.com/p/abc", "snippet": "Creta 2026"},
            {"title": "Hyundai Creta 2026 oficial", "href": "https://www.hyundai.com/br/pt/creta", "snippet": "Creta 2026 especificacoes"},
            {"title": "Hyundai Creta duplicado", "href": "https://www.hyundai.com/br/pt/creta/", "snippet": "mesma pagina"},
            {"title": "Noticia Creta", "href": "https://motor1.com/news/creta-2026", "snippet": "dados do Creta 2026"},
        ]

        ranked = rank_search_results("Creta 2026 especificacoes", results, limit=10)

        self.assertEqual(ranked[0]["source_type"], "official")
        self.assertEqual(len([item for item in ranked if "hyundai.com" in item["href"]]), 1)
        self.assertFalse(any("instagram.com" in item["href"] for item in ranked))

    def test_limits_repeated_hosts(self) -> None:
        results = [
            {"title": f"Materia {index}", "href": f"https://motor1.com/news/item-{index}", "snippet": "Creta 2026"}
            for index in range(5)
        ]

        ranked = rank_search_results("Creta 2026", results, limit=10)

        self.assertEqual(len(ranked), 2)
