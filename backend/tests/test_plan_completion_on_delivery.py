import asyncio
import unittest
from unittest import mock

from services.event_bus import EventBus
import services.agent_runner as agent_runner
from services.task_plan_store import task_plan_store
import database


class PlanCompletionOnDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.task_id = "test-plan-delivery-task"
        database.create_task(self.task_id, "Tarefa com plano e entrega de software")
        self.bus = EventBus()
        self.store = mock.Mock()

    def tearDown(self):
        try:
            database.delete_task(self.task_id)
        except Exception:
            pass

    def test_running_steps_are_completed_on_finish_response(self):
        # Cria plano com 2 etapas: uma 'passed' e uma 'running' (sem tool_hint deliver)
        steps = [
            {"position": 1, "label": "Pesquisar referencias", "tool_hint": "research", "status": "passed"},
            {"position": 2, "label": "Construir solucao", "tool_hint": "execute", "status": "running"},
        ]
        task_plan_store.replace_plan(self.task_id, steps, "Criar app")

        asyncio.run(
            agent_runner._finish_text_response(
                self.task_id,
                "Criar app",
                "Aqui esta a solucao completa entregue.",
                self.store,
                self.bus,
                refresh_context=False,
            )
        )

        all_steps = task_plan_store.list_steps(self.task_id)
        # Nenhuma etapa deve permanecer 'running'
        running_steps = [s for s in all_steps if s.get("status") == "running"]
        self.assertEqual(running_steps, [])

        # Todas as etapas devem estar 'passed'
        passed_steps = [s for s in all_steps if s.get("status") == "passed"]
        self.assertEqual(len(passed_steps), 2)

    def test_find_for_hint_fallback_to_last_active_step_for_deliver(self):
        steps = [
            {"position": 1, "label": "Etapa 1", "tool_hint": "research", "status": "passed"},
            {"position": 2, "label": "Etapa final de conclusao", "tool_hint": "conclude", "status": "pending"},
        ]
        task_plan_store.replace_plan(self.task_id, steps, "Etapa sem deliver")

        found = task_plan_store.find_for_hint(self.task_id, "deliver")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("label"), "Etapa final de conclusao")


if __name__ == "__main__":
    unittest.main()
