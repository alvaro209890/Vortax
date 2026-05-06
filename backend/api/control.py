from fastapi import APIRouter, HTTPException

from services.registry import event_bus, task_store

router = APIRouter()


@router.post("/{task_id}/pause")
async def pause_task(task_id: str) -> dict:
    if not task_store.pause(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "agent_status", {"status": "paused", "label": "Pausado"})
    return {"ok": True, "status": "paused"}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str) -> dict:
    if not task_store.resume(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "agent_status", {"status": "running", "label": "Continuando"})
    return {"ok": True, "status": "running"}


@router.post("/{task_id}/stop")
async def stop_task(task_id: str) -> dict:
    if not task_store.stop(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Parado"})
    return {"ok": True, "status": "stopped"}


@router.post("/{task_id}/confirm")
async def confirm_task(task_id: str, approved: bool = True) -> dict:
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "confirmation_result", {"approved": approved})
    return {"ok": True, "approved": approved}
