from fastapi import APIRouter, HTTPException

from services.registry import event_bus, task_store

router = APIRouter()


@router.post("/{task_id}/confirm")
async def confirm_task(task_id: str, approved: bool = True) -> dict:
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "confirmation_result", {"approved": approved})
    return {"ok": True, "approved": approved}
