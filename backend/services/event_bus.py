import asyncio
from typing import Any

from database import database
from starlette.websockets import WebSocket

from services.stream_contract import build_stream_event


class EventBus:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(task_id, []).append(websocket)
        history = database.list_events(task_id)
        for event in history:
            await websocket.send_json(event)

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(task_id, [])
            if websocket in sockets:
                sockets.remove(websocket)

    async def publish(self, task_id: str, event_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        event = build_stream_event(task_id, event_type, payload)
        event_id = database.insert_event(task_id, event["type"], event["created_at"], event["payload"])
        event["event_id"] = event_id
        async with self._lock:
            sockets = list(self._connections.get(task_id, []))

        disconnected: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(event)
            except Exception:
                disconnected.append(socket)

        if disconnected:
            async with self._lock:
                current = self._connections.get(task_id, [])
                for socket in disconnected:
                    if socket in current:
                        current.remove(socket)

        return event

    def history(self, task_id: str) -> list[dict[str, Any]]:
        return database.list_events(task_id)

    async def close_task_connections(self, task_id: str) -> None:
        async with self._lock:
            sockets = list(self._connections.pop(task_id, []))
        for socket in sockets:
            try:
                await socket.close(code=1000)
            except Exception:
                pass
