import asyncio
import contextlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import database
from services.agent_runner import run_agent_task
from services.registry import event_bus, runner_tasks, task_store

router = APIRouter()


class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


@router.post("/")
async def create_task(payload: TaskCreate) -> dict:
    task = task_store.create(payload.description)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    await event_bus.publish(task["id"], "user_message", {"content": task["description"]})
    runner_tasks[task["id"]] = asyncio.create_task(
        run_agent_task(task["id"], task["description"], task_store, event_bus)
    )
    return {"task_id": task["id"], "task": task}


@router.post("/{task_id}/messages")
async def create_task_message(task_id: str, payload: TaskMessageCreate) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    content = payload.content.strip()
    await event_bus.publish(task_id, "user_message", {"content": content})
    task_store.update_status(task_id, "queued")
    runner_tasks[task_id] = asyncio.create_task(run_agent_task(task_id, content, task_store, event_bus))
    return {"ok": True, "task_id": task_id}


@router.get("/")
async def list_tasks() -> dict:
    return {"tasks": task_store.list()}


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    return {"task": task, "events": event_bus.history(task_id), "sources": database.list_sources(task_id)}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    runner = runner_tasks.pop(task_id, None)
    if runner and not runner.done():
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner

    await event_bus.close_task_connections(task_id)
    deleted = task_store.delete(task_id)
    return {"ok": deleted}
