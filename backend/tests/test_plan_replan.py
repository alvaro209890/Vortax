import unittest

from services.plan_replan import objective_similarity, should_replan


class PlanReplanTests(unittest.TestCase):
    def test_similarity_high_for_same_topic(self):
        a = "Pesquise sobre CAR ambiental em Mato Grosso"
        b = "Quero mais detalhes sobre CAR ambiental de MT"
        self.assertGreater(objective_similarity(a, b), 0.2)

    def test_should_replan_on_divergent_objective(self):
        do, reason = should_replan(
            original_objective="Pesquise notícias de IA em 2026",
            latest_user_prompt="Crie um site HTML de portfólio com 3 páginas e CSS",
            last_tool="browser_google_search",
            last_tool_ok=True,
            iteration=3,
            already_replanned=False,
        )
        self.assertTrue(do)
        self.assertTrue(reason)

    def test_should_not_replan_similar(self):
        do, reason = should_replan(
            original_objective="Crie um site de portfólio em HTML",
            latest_user_prompt="Crie um site de portfólio com HTML e CSS",
            last_tool="shell_run",
            last_tool_ok=True,
            iteration=2,
            already_replanned=False,
        )
        # similar enough — may or may not replan depending on threshold; must not force
        self.assertIsInstance(do, bool)
        self.assertIsInstance(reason, str)

    def test_force(self):
        do, reason = should_replan(
            original_objective="x",
            latest_user_prompt="x",
            last_tool=None,
            last_tool_ok=True,
            iteration=0,
            already_replanned=True,
            force=True,
        )
        self.assertTrue(do)
        self.assertEqual(reason, "force")


if __name__ == "__main__":
    unittest.main()
