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


def _request_host(value: str | None) -> str:
    return str(value or "").split(":", 1)[0].strip().lower()


def _is_cloudflare_request(headers) -> bool:
    return bool(headers.get("cf-ray") or headers.get("cf-connecting-ip"))


def is_allowed_public_host(host: str | None, headers) -> bool:
    request_host = _request_host(host or headers.get("x-forwarded-host"))
    return bool(request_host and request_host in settings.public_hosts_list and _is_cloudflare_request(headers))


def install_lan_guard(app: FastAPI) -> None:
    if settings.ALLOW_NO_AUTH:
        logger.warning("Vortax sem autenticacao; restrinja o acesso ao backend.")

    @app.middleware("http")
    async def lan_only_middleware(request: Request, call_next):
        client_host = request.client.host if request.client else None
        if settings.LAN_ONLY and not is_private_client(client_host) and not is_allowed_public_host(request.headers.get("host"), request.headers):
            return JSONResponse(
                {"detail": "Acesso publico nao autorizado para este backend."},
                status_code=403,
            )
        return await call_next(request)


async def reject_non_lan_websocket(websocket: WebSocket) -> bool:
    client_host = websocket.client.host if websocket.client else None
    if settings.LAN_ONLY and not is_private_client(client_host) and not is_allowed_public_host(websocket.headers.get("host"), websocket.headers):
        await websocket.close(code=1008)
        return True
    return False
