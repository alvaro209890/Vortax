import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import database as database_module
from database import Database
from services.task_store import utc_now
from services.event_bus import EventBus
import services.agent_runner as agent_runner
from services.task_plan_store import TaskPlanStore
import services.task_plan_store as task_plan_store_module


class PlanCompletionOnDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_base = database_module.settings.DATABASE_BASE_PATH
        database_module.settings.DATABASE_BASE_PATH = Path(self.tmp.name)
        self.db = Database()
        self.original_database = database_module.database
        self.original_plan_database = task_plan_store_module.database
        database_module.database = self.db
        task_plan_store_module.database = self.db
        agent_runner.database = self.db
        self.plan_store = TaskPlanStore()
        agent_runner.task_plan_store = self.plan_store

        self.task_id = "test-plan-delivery-task"
        self.db.create_task(
            {
                "id": self.task_id,
                "description": "Tarefa com plano e entrega de software",
                "status": "running",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self.bus = EventBus()
        self.store = mock.Mock()

    def tearDown(self):
        database_module.database = self.original_database
        task_plan_store_module.database = self.original_plan_database
        database_module.settings.DATABASE_BASE_PATH = self.original_base
        self.db.close()
        self.tmp.cleanup()

    def test_running_steps_are_completed_on_finish_response(self):
        # Cria plano com 2 etapas: uma 'passed' e uma 'running' (sem tool_hint deliver)
        steps = [
            {"position": 1, "label": "Pesquisar referencias", "tool_hint": "research", "status": "passed"},
            {"position": 2, "label": "Construir solucao", "tool_hint": "execute", "status": "running"},
        ]
        self.plan_store.replace_plan(self.task_id, steps, "Criar app")

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

        all_steps = self.plan_store.list_steps(self.task_id)
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
        self.plan_store.replace_plan(self.task_id, steps, "Etapa sem deliver")

        found = self.plan_store.find_for_hint(self.task_id, "deliver")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("label"), "Etapa final de conclusao")


if __name__ == "__main__":
    unittest.main()
