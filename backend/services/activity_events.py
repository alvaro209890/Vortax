from typing import Any

from services.event_bus import EventBus


ACTIVITY_KINDS = {
    "analysis",
    "search",
    "source",
    "browser",
    "code",
    "validation",
    "file",
    "finalizing",
}

ACTIVITY_STATUSES = {"running", "done", "blocked", "failed"}


async def publish_agent_activity(
    bus: EventBus,
    task_id: str,
    *,
    kind: str,
    title: str,
    detail: str = "",
    status: str = "running",
    tool: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    safe_kind = kind if kind in ACTIVITY_KINDS else "analysis"
    safe_status = status if status in ACTIVITY_STATUSES else "running"
    payload: dict[str, Any] = {
        "kind": safe_kind,
        "title": str(title or "").strip()[:180] or "Vortax trabalhando",
        "detail": str(detail or "").strip()[:500],
        "status": safe_status,
        "metadata": metadata or {},
    }
    if tool:
        payload["tool"] = str(tool)[:80]
    await bus.publish(task_id, "agent_activity", payload)
