import json
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status
from starlette.websockets import WebSocket

from config import settings


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
    return AuthUser(uid=settings.DEV_USER_ID, email="dev@local", name="Desenvolvimento", is_dev=True)


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthUser:
    token = _bearer_token(authorization) or str(request.query_params.get("token") or "").strip()
    if token:
        return _verify_token(token)
    if settings.ALLOW_NO_AUTH:
        return dev_user()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria.")


async def authenticate_websocket(websocket: WebSocket) -> AuthUser | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if not token:
        token = _bearer_token(websocket.headers.get("authorization"))
    if token:
        try:
            return _verify_token(token)
        except HTTPException:
            await websocket.close(code=1008)
            return None
    if settings.ALLOW_NO_AUTH:
        return dev_user()
    await websocket.close(code=1008)
    return None


def ensure_task_owner(task: dict | None, user: AuthUser) -> dict:
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task nao encontrada")
    if task.get("user_id") != user.uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task nao encontrada")
    return task
