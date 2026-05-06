import asyncio

from services.event_bus import EventBus
from services.task_store import TaskStore


event_bus = EventBus()
task_store = TaskStore()
runner_tasks: dict[str, asyncio.Task] = {}
