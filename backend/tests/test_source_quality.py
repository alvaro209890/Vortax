import unittest

from services.source_quality import source_quality_score, source_type_for_url


class SourceQualityTests(unittest.TestCase):
    def test_scores_official_sources_above_social_sources(self) -> None:
        official = source_quality_score("https://www.hyundai.com/br/pt", "Creta", "x" * 2000)
        social = source_quality_score("https://www.instagram.com/example", "Post", "x" * 200)

        self.assertGreater(official, social)

    def test_classifies_common_source_types(self) -> None:
        self.assertEqual(source_type_for_url("https://www.hyundai.com/br/pt"), "official")
        self.assertEqual(source_type_for_url("https://motor1.com/news/example"), "news")
        self.assertEqual(source_type_for_url("https://www.youtube.com/watch?v=abc"), "video")
        self.assertEqual(source_type_for_url("https://www.reddit.com/r/test"), "forum")
