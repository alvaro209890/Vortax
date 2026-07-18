"""Subtasks paralelas controladas (asyncio + semáforo).

Uso: pesquisas largas (análise de N textos), comparações e varredura de arquivos.
Não usa browser compartilhado em paralelo (CDP single-session por task) —
para I/O de disco e CPU-bound leve.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from services.event_bus import EventBus

T = TypeVar("T")


async def run_parallel(
    items: Iterable[T],
    worker: Callable[[T], Awaitable[Any]],
    *,
    max_concurrency: int = 4,
    return_exceptions: bool = True,
) -> list[Any]:
    """Executa worker(item) em paralelo com limite de concorrência."""
    sem = asyncio.Semaphore(max(1, int(max_concurrency)))
    items_list = list(items)

    async def _run(item: T) -> Any:
        async with sem:
            return await worker(item)

    if not items_list:
        return []
    return await asyncio.gather(*[_run(item) for item in items_list], return_exceptions=return_exceptions)


async def scan_files_parallel(
    paths: list[str],
    reader: Callable[[str], Awaitable[dict[str, Any]]],
    *,
    max_concurrency: int = 6,
) -> list[dict[str, Any]]:
    results = await run_parallel(paths, reader, max_concurrency=max_concurrency, return_exceptions=True)
    out: list[dict[str, Any]] = []
    for path, result in zip(paths, results):
        if isinstance(result, Exception):
            out.append({"path": path, "ok": False, "error": str(result)[:300]})
        else:
            out.append(result if isinstance(result, dict) else {"path": path, "ok": True, "data": result})
    return out


async def publish_subtask_fanout(
    bus: EventBus,
    task_id: str,
    *,
    title: str,
    subtasks: list[str],
) -> None:
    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": title,
            "detail": f"{len(subtasks)} subtasks em paralelo: " + "; ".join(subtasks[:6]),
            "parallel": True,
            "subtasks": subtasks,
        },
    )
