from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import choice, token_hex, token_urlsafe
from string import ascii_letters, digits
from threading import RLock
from typing import Any
from urllib.parse import urlparse


class CredentialStoreError(ValueError):
    pass


@dataclass
class CredentialAuthorization:
    handle: str
    task_id: str
    user_id: str
    origin: str
    login_url: str
    allowed_origins: set[str]
    username: str | None
    password: str | None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=10))
    used_at: datetime | None = None
    status: str = "pending"
    generated_for_signup: bool = False
    signup_username: str | None = None
    signup_email: str | None = None
    signup_password: str | None = None
    signup_used_at: datetime | None = None
    signup_status: str = "not_requested"

    def metadata(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "origin": self.origin,
            "login_url": self.login_url,
            "allowed_origins": sorted(self.allowed_origins),
            "username_present": bool(self.username),
            "password_present": bool(self.password),
            "username_selector": self.username_selector,
            "password_selector": self.password_selector,
            "submit_selector": self.submit_selector,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "status": self.status,
            "generated_signup_present": bool(self.generated_for_signup),
            "signup_status": self.signup_status,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_origin(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CredentialStoreError("URL de login precisa ser http(s) valida")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    port_part = "" if port is None or default_port else f":{port}"
    return f"{scheme}://{host}{port_part}"


def normalize_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    origin = normalize_origin(url)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{origin}{path}{query}"

def generate_secure_signup_credentials(task_id: str, origin: str) -> dict[str, str]:
    suffix = token_hex(4)
    parsed = urlparse(origin)
    host = (parsed.hostname or "site").replace(".", "-")[:32]
    username = f"vortax_{suffix}"
    email = f"vortax+{suffix}@example.com"
    alphabet = ascii_letters + digits + "!@#$%"
    password = "Vx!" + "".join(choice(alphabet) for _ in range(13))
    return {"username": username, "email": email, "password": password, "label": f"{host}-{suffix}"}


class CredentialStore:
    def __init__(self) -> None:
        self._items: dict[str, CredentialAuthorization] = {}
        self._by_task: dict[str, str] = {}
        self._lock = RLock()

    def create_authorization(
        self,
        *,
        task_id: str,
        user_id: str,
        login_url: str,
        username: str,
        password: str,
        allowed_origins: list[str] | None = None,
        username_selector: str | None = None,
        password_selector: str | None = None,
        submit_selector: str | None = None,
        ttl_seconds: int = 600,
    ) -> dict[str, Any]:
        task_key = str(task_id or "").strip()
        user_key = str(user_id or "").strip()
        if not task_key or not user_key:
            raise CredentialStoreError("task_id e user_id sao obrigatorios")
        clean_login_url = normalize_url(login_url)
        origin = normalize_origin(clean_login_url)
        origins = {origin}
        for item in allowed_origins or []:
            origins.add(normalize_origin(item))
        now = utc_now()
        auth = CredentialAuthorization(
            handle=token_urlsafe(24),
            task_id=task_key,
            user_id=user_key,
            origin=origin,
            login_url=clean_login_url,
            allowed_origins=origins,
            username=str(username or ""),
            password=str(password or ""),
            username_selector=(username_selector or None),
            password_selector=(password_selector or None),
            submit_selector=(submit_selector or None),
            created_at=now,
            expires_at=now + timedelta(seconds=max(30, int(ttl_seconds))),
        )
        with self._lock:
            old = self._by_task.get(task_key)
            if old:
                self._items.pop(old, None)
            self._items[auth.handle] = auth
            self._by_task[task_key] = auth.handle
        return auth.metadata()

    def _get(self, task_id: str, user_id: str | None = None) -> CredentialAuthorization | None:
        self.cleanup_expired()
        with self._lock:
            handle = self._by_task.get(str(task_id or ""))
            auth = self._items.get(handle or "")
            if not auth:
                return None
            if user_id is not None and auth.user_id != str(user_id):
                return None
            return auth

    def get_metadata(self, task_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        auth = self._get(task_id, user_id)
        return auth.metadata() if auth else None

    def has_authorization(self, task_id: str) -> bool:
        return self._get(task_id) is not None

    def consume_for_login(self, task_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        auth = self._get(task_id, user_id)
        if not auth or auth.status == "expired":
            return None
        with self._lock:
            auth.used_at = utc_now()
            auth.status = "login_attempted"
            return {
                **auth.metadata(),
                "username": auth.username,
                "password": auth.password,
            }

    def create_signup_credentials(self, task_id: str, *, signup_url: str | None = None) -> dict[str, str] | None:
        auth = self._get(task_id)
        if not auth:
            return None
        with self._lock:
            if not auth.generated_for_signup:
                creds = generate_secure_signup_credentials(task_id, auth.origin)
                auth.generated_for_signup = True
                auth.signup_username = creds["username"]
                auth.signup_email = creds["email"]
                auth.signup_password = creds["password"]
                auth.signup_status = "generated"
            return {
                "username": auth.signup_username or "",
                "email": auth.signup_email or "",
                "password": auth.signup_password or "",
                "signup_url": signup_url or auth.login_url,
                "origin": auth.origin,
            }

    def mark_signup_used(self, task_id: str, *, status: str = "signup_submitted") -> None:
        auth = self._get(task_id)
        if not auth:
            return
        with self._lock:
            auth.signup_status = status
            auth.signup_used_at = utc_now()

    def signup_summary(self, task_id: str) -> dict[str, str] | None:
        auth = self._get(task_id)
        if not auth or not auth.generated_for_signup:
            return None
        return {
            "origin": auth.origin,
            "username": auth.signup_username or "",
            "email": auth.signup_email or "",
            "password": auth.signup_password or "",
            "status": auth.signup_status,
        }

    def revoke_raw_credentials(self, task_id: str, *, status: str = "revoked") -> None:
        auth = self._get(task_id)
        if not auth:
            return
        with self._lock:
            auth.username = None
            auth.password = None
            auth.status = status
            auth.used_at = auth.used_at or utc_now()

    def revoke_task(self,task_id: str) -> None:
        key = str(task_id or "")
        with self._lock:
            handle = self._by_task.pop(key, None)
            if handle:
                self._items.pop(handle, None)

    def is_url_allowed(self, task_id: str, url: str) -> bool:
        auth = self._get(task_id)
        if not auth:
            return False
        try:
            return normalize_origin(url) in auth.allowed_origins
        except CredentialStoreError:
            return False

    def cleanup_expired(self) -> None:
        now = utc_now()
        with self._lock:
            for handle, auth in list(self._items.items()):
                if auth.expires_at < now:
                    auth.username = None
                    auth.password = None
                    auth.status = "expired"
                    if auth.used_at is None:
                        auth.used_at = now


credential_store = CredentialStore()
