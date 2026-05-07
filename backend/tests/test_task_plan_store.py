import tempfile
import unittest
from pathlib import Path

import database as database_module
import services.task_plan_store as task_plan_store_module
from database import Database
from services.task_plan_store import TaskPlanStore
from services.task_store import utc_now


class TaskPlanStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_base = database_module.settings.DATABASE_BASE_PATH
        database_module.settings.DATABASE_BASE_PATH = Path(self.tmp.name)
        self.db = Database()
        self.original_database = database_module.database
        self.original_plan_database = task_plan_store_module.database
        database_module.database = self.db
        task_plan_store_module.database = self.db
        self.store = TaskPlanStore()
        self.task_id = "task-plan-1"
        self.db.create_task(
            {
                "id": self.task_id,
                "description": "Crie um site",
                "status": "queued",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )

    def tearDown(self) -> None:
        database_module.database = self.original_database
        task_plan_store_module.database = self.original_plan_database
        database_module.settings.DATABASE_BASE_PATH = self.original_base
        self.db.close()
        self.tmp.cleanup()

    def test_replaces_and_lists_task_steps(self) -> None:
        steps = self.store.replace_plan(
            self.task_id,
            [
                {
                    "label": "Criar site",
                    "detail": "Gerar arquivos principais.",
                    "tool_hint": "execute",
                    "acceptance_criteria": ["index.html criado"],
                }
            ],
            "Crie um site",
        )

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["status"], "pending")
        self.assertEqual(steps[0]["acceptance_criteria"], ["index.html criado"])

    def test_start_complete_and_evidence_updates_step(self) -> None:
        self.store.replace_plan(self.task_id, [], "Crie um site")

        running = self.store.start_step(self.task_id, hint="execute")
        self.assertIsNotNone(running)
        self.assertEqual(running["status"], "running")

        updated = self.store.append_evidence(
            self.task_id,
            {"status": "ok", "summary": "4 arquivos gerados."},
            hint="execute",
        )
        self.assertEqual(updated["evidence"][0]["summary"], "4 arquivos gerados.")

        done = self.store.complete_step(self.task_id, hint="execute", status="passed")
        self.assertEqual(done["status"], "passed")
        self.assertIsNotNone(done["finished_at"])

    def test_delete_task_cascades_steps(self) -> None:
        self.store.replace_plan(self.task_id, [], "Crie um site")

        self.assertGreater(len(self.store.list_steps(self.task_id)), 0)
        self.db.delete_task(self.task_id)

        self.assertEqual(self.store.list_steps(self.task_id), [])


if __name__ == "__main__":
    unittest.main()
