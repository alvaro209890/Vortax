from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from database import database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    id: str
    user_id: str
    description: str
    status: str
    created_at: str
    updated_at: str
    result: str | None = None


class TaskStore:
    def __init__(self) -> None:
        self._paused: set[str] = set()
        self._stopped: set[str] = set()

    def create(self, description: str, user_id: str) -> dict:
        task_id = str(uuid4())
        now = utc_now()
        record = TaskRecord(
            id=task_id,
            user_id=user_id,
            description=description.strip(),
            status="queued",
            created_at=now,
            updated_at=now,
        )
        payload = asdict(record)
        database.create_task(payload)
        return payload

    def get(self, task_id: str) -> dict | None:
        return database.get_task(task_id)

    def list(self, user_id: str) -> list[dict]:
        return database.list_tasks(user_id)

    def update_status(self, task_id: str, status: str, result: str | None = None) -> dict | None:
        return database.update_task(task_id, status, result, utc_now())

    def pause(self, task_id: str) -> bool:
        if not self.get(task_id):
            return False
        self._paused.add(task_id)
        self.update_status(task_id, "paused")
        return True

    def resume(self, task_id: str) -> bool:
        if not self.get(task_id):
            return False
        self._paused.discard(task_id)
        self._stopped.discard(task_id)
        self.update_status(task_id, "running")
        return True

    def stop(self, task_id: str) -> bool:
        if not self.get(task_id):
            return False
        self._stopped.add(task_id)
        self.update_status(task_id, "stopped")
        return True

    def delete(self, task_id: str) -> bool:
        self._paused.discard(task_id)
        self._stopped.discard(task_id)
        return database.delete_task(task_id)

    def is_paused(self, task_id: str) -> bool:
        return task_id in self._paused

    def is_stopped(self, task_id: str) -> bool:
        return task_id in self._stopped
