import re
from typing import Any


_SECRET_KEY_NAMES = (
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "credentials",
    "login",
    "mfa",
    "otp",
    "pass",
    "password",
    "passwd",
    "pwd",
    "secret",
    "senha",
    "token",
)
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gsk_[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"Authorization:\s*Basic\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"((?:DEEPSEEK|GROQ)_API_KEY=)[^\s]+", re.IGNORECASE),
    re.compile(r"\b(password|passwd|pwd|senha|token|secret|otp|mfa|2fa)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        def repl(match: re.Match) -> str:
            if match.lastindex and match.lastindex >= 2 and match.group(1).lower() in {"password", "passwd", "pwd", "senha", "token", "secret", "otp", "mfa", "2fa"}:
                separator = ":" if ":" in match.group(0).split(match.group(1), 1)[-1][:3] else "="
                return f"{match.group(1)}{separator}[REDACTED]"
            return f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]"
        redacted = pattern.sub(repl, redacted)
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
