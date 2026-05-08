import unittest

import services.agent_runner as agent_runner_module


class AgentTaskPlanContextTests(unittest.TestCase):
    def test_deepseek_history_receives_current_task_plan(self) -> None:
        class FakePlanStore:
            def list_steps(self, task_id):
                self.seen_task_id = task_id
                return [
                    {
                        "position": 1,
                        "label": "Pesquisar agenda",
                        "detail": "Buscar a agenda atual em fontes confiaveis.",
                        "status": "running",
                        "tool_hint": "research",
                        "acceptance_criteria": ["Fonte atual encontrada"],
                    },
                    {
                        "position": 2,
                        "label": "Entregar resumo",
                        "detail": "Responder com dados e URLs.",
                        "status": "pending",
                        "tool_hint": "deliver",
                        "acceptance_criteria": ["Resposta enviada"],
                    },
                ]

        original_store = agent_runner_module.task_plan_store
        fake_store = FakePlanStore()
        agent_runner_module.task_plan_store = fake_store
        try:
            history = agent_runner_module._history_with_task_plan(
                "task-1",
                [{"role": "user", "content": "pesquise os jogos de hoje"}],
            )
        finally:
            agent_runner_module.task_plan_store = original_store

        self.assertEqual(fake_store.seen_task_id, "task-1")
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("PLANO DE TASKS DO VORTAX", history[0]["content"])
        self.assertIn("Pesquisar agenda", history[0]["content"])
        self.assertIn("hint=research", history[0]["content"])
        self.assertEqual(history[1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
