import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status
from starlette.websockets import WebSocket

from access import is_private_client
from config import settings

logger = logging.getLogger("vortax.auth")


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str = ""
    name: str = ""
    is_dev: bool = False


def _bearer_token(value: str | None) -> str:
    header = str(value or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


@lru_cache(maxsize=1)
def _firebase_auth():
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
        from firebase_admin import credentials
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="firebase-admin nao instalado no backend.",
        ) from exc

    if not firebase_admin._apps:
        options = {"projectId": settings.FIREBASE_PROJECT_ID}
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip():
            info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            credential = credentials.Certificate(info)
            firebase_admin.initialize_app(credential, options)
        elif settings.FIREBASE_CREDENTIALS_PATH.strip():
            credential = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(credential, options)
        else:
            firebase_admin.initialize_app(options=options)
    return firebase_auth


def _user_from_claims(claims: dict) -> AuthUser:
    uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Firebase sem uid.")
    return AuthUser(
        uid=uid,
        email=str(claims.get("email") or ""),
        name=str(claims.get("name") or ""),
    )


def _verify_token(token: str) -> AuthUser:
    try:
        claims = _firebase_auth().verify_id_token(token, check_revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Firebase invalido.") from exc
    return _user_from_claims(claims)


def dev_user() -> AuthUser:
    """Usuário de desenvolvimento único (ALLOW_NO_AUTH=true). Todos compartilham o mesmo uid."""
    return AuthUser(uid=settings.DEV_USER_ID, email="dev@local", name="Desenvolvimento", is_dev=True)


def _lan_user(client_host: str | None) -> AuthUser:
    """Usuário LAN sem Firebase token.

    Usa o IP como uid para isolar dados entre diferentes dispositivos na rede.
    Quando ALLOW_NO_AUTH=True (modo single-user), usa o uid compartilhado.
    """
    if settings.ALLOW_NO_AUTH:
        return dev_user()
    host = str(client_host or "localhost")
    safe = host.replace(":", "_").replace(".", "_")
    uid = f"lan_{safe}"
    return AuthUser(uid=uid, email=f"{safe}@local.lan", name=f"LAN ({host})", is_dev=True)


def _allow_lan_no_auth(request_or_websocket: Request | WebSocket) -> bool:
    client_host = request_or_websocket.client.host if request_or_websocket.client else None
    return settings.ALLOW_LAN_NO_AUTH and is_private_client(client_host)


def _client_host(request_or_websocket: Request | WebSocket) -> str | None:
    return request_or_websocket.client.host if request_or_websocket.client else None


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthUser:
    token = _bearer_token(authorization) or str(request.query_params.get("token") or "").strip()
    if token:
        try:
            return _verify_token(token)
        except HTTPException:
            if _allow_lan_no_auth(request):
                logger.debug("Token invalido na LAN — usando usuario LAN isolado por IP.")
                return _lan_user(_client_host(request))
            raise
    if settings.ALLOW_NO_AUTH:
        return dev_user()
    if _allow_lan_no_auth(request):
        return _lan_user(_client_host(request))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticacao obrigatoria. Configure ALLOW_NO_AUTH=true apenas para desenvolvimento local.",
    )


async def authenticate_websocket(websocket: WebSocket) -> AuthUser | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if not token:
        token = _bearer_token(websocket.headers.get("authorization"))
    if token:
        try:
            return _verify_token(token)
        except HTTPException:
            if _allow_lan_no_auth(websocket):
                return _lan_user(_client_host(websocket))
            await websocket.close(code=1008)
            return None
    if settings.ALLOW_NO_AUTH:
        return dev_user()
    if _allow_lan_no_auth(websocket):
        return _lan_user(_client_host(websocket))
    await websocket.close(code=1008)
    return None


def ensure_task_owner(task: dict | None, user: AuthUser) -> dict:
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task nao encontrada")
    if task.get("user_id") != user.uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task nao encontrada")
    return task
