import ipaddress
import logging

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket

from config import settings

logger = logging.getLogger("vortax.access")


def is_private_client(host: str | None) -> bool:
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in {"localhost"}
    return ip.is_private or ip.is_loopback


def install_lan_guard(app: FastAPI) -> None:
    if settings.ALLOW_NO_AUTH:
        logger.warning("Vortax sem autenticacao; use apenas em rede local confiavel.")

    @app.middleware("http")
    async def lan_only_middleware(request: Request, call_next):
        client_host = request.client.host if request.client else None
        if settings.LAN_ONLY and not is_private_client(client_host):
            return JSONResponse(
                {"detail": "Vortax MVP aceita apenas clientes de rede local."},
                status_code=403,
            )
        return await call_next(request)


async def reject_non_lan_websocket(websocket: WebSocket) -> bool:
    client_host = websocket.client.host if websocket.client else None
    if settings.LAN_ONLY and not is_private_client(client_host):
        await websocket.close(code=1008)
        return True
    return False
