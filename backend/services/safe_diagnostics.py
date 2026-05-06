import re
from typing import Any


_SECRET_KEY_NAMES = ("api_key", "apikey", "token", "secret", "authorization", "password")
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gsk_[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"((?:DEEPSEEK|GROQ)_API_KEY=)[^\s]+", re.IGNORECASE),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]", redacted)
    return redacted


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if any(secret_name in key.lower() for secret_name in _SECRET_KEY_NAMES):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def format_exception_for_user(exc: BaseException, *, include_message: bool = True) -> str:
    if not include_message:
        return type(exc).__name__
    message = redact_text(str(exc))
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def text_len_hint(text: str | None) -> int:
    return len(text) if text else 0
