from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from access import reject_non_lan_websocket
from auth import authenticate_websocket, ensure_task_owner
from services.registry import event_bus, task_store

router = APIRouter()


@router.websocket("/ws/{task_id}")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    if await reject_non_lan_websocket(websocket):
        return
    current_user = await authenticate_websocket(websocket)
    if current_user is None:
        return
    try:
        ensure_task_owner(task_store.get(task_id), current_user)
    except Exception:
        await websocket.close(code=1008)
        return

    await event_bus.connect(task_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "task_id": task_id, "payload": {}})
    except WebSocketDisconnect:
        await event_bus.disconnect(task_id, websocket)
