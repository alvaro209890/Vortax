from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from access import reject_non_lan_websocket
from services.registry import event_bus

router = APIRouter()


@router.websocket("/ws/{task_id}")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    if await reject_non_lan_websocket(websocket):
        return

    await event_bus.connect(task_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "task_id": task_id, "payload": {}})
    except WebSocketDisconnect:
        await event_bus.disconnect(task_id, websocket)
