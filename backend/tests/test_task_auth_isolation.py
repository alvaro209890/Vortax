import tempfile
import unittest
from pathlib import Path

import database as database_module
from auth import AuthUser, ensure_task_owner
from database import Database
from services.task_store import utc_now


class TaskAuthIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_base = database_module.settings.DATABASE_BASE_PATH
        database_module.settings.DATABASE_BASE_PATH = Path(self.tmp.name)
        self.db = Database()

    def tearDown(self) -> None:
        self.db.close()
        database_module.settings.DATABASE_BASE_PATH = self.original_base
        self.tmp.cleanup()

    def _task(self, task_id: str, user_id: str | None) -> dict:
        now = utc_now()
        return {
            "id": task_id,
            "user_id": user_id,
            "description": task_id,
            "status": "done",
            "created_at": now,
            "updated_at": now,
            "result": None,
        }

    def test_lists_only_tasks_owned_by_user(self) -> None:
        self.db.create_task(self._task("task-a", "user-a"))
        self.db.create_task(self._task("task-b", "user-b"))
        self.db.create_task(self._task("legacy", None))

        tasks = self.db.list_tasks("user-a")

        self.assertEqual([task["id"] for task in tasks], ["task-a"])

    def test_owner_guard_hides_other_users_and_legacy_tasks(self) -> None:
        owned = self._task("task-a", "user-a")
        other = self._task("task-b", "user-b")
        legacy = self._task("legacy", None)

        self.assertEqual(ensure_task_owner(owned, AuthUser(uid="user-a"))["id"], "task-a")
        with self.assertRaises(Exception):
            ensure_task_owner(other, AuthUser(uid="user-a"))
        with self.assertRaises(Exception):
            ensure_task_owner(legacy, AuthUser(uid="user-a"))


if __name__ == "__main__":
    unittest.main()
