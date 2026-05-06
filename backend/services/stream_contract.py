from datetime import datetime, timezone
from typing import Any

from services.safe_diagnostics import sanitize_payload


KNOWN_EVENT_TYPES = frozenset(
    {
        "assistant_message_delta",
        "assistant_message_done",
        "agent_status",
        "agent_progress",
        "task_created",
        "user_message",
        "image_saved",
        "tool_call",
        "tool_result",
        "screen_frame",
        "source_saved",
        "confirmation_request",
        "confirmation_result",
        "context_status",
        "context_compacted",
        "shell_stdout",
        "shell_stderr",
        "files_created",
        "vertex_progress",
        "shell_interactive_prompt",
        "error",
        "pong",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_stream_event(task_id: str, event_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    safe_payload = sanitize_payload(payload or {})
    safe_type = event_type if event_type in KNOWN_EVENT_TYPES else "error"
    if safe_type != event_type:
        safe_payload = {
            "message": "Evento desconhecido publicado no stream.",
            "original_type": event_type,
            "payload": safe_payload,
        }
    return {
        "type": safe_type,
        "task_id": task_id,
        "created_at": utc_now(),
        "payload": safe_payload,
    }
