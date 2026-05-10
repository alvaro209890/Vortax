from __future__ import annotations

from typing import Any

from config import settings
from database import database
from services.deepseek_client import DeepSeekError, request_context_summary
from services.stream_contract import utc_now


CHAT_EVENT_TYPES = {"user_message", "assistant_message_done"}


def estimate_text_tokens(text: str) -> int:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return 0
    # Same practical fallback used in the code-agent stack when tokenizer data is not available.
    return max(1, len(cleaned) // 4)


def _message_tokens(message: dict[str, Any]) -> int:
    tokens = estimate_text_tokens(str(message.get("content") or "")) + 4
    images = message.get("images")
    if isinstance(images, list):
        tokens += len(images) * 250
    return tokens


def estimate_messages_tokens(messages: list[dict[str, Any]], summary: str = "") -> int:
    summary_tokens = estimate_text_tokens(summary)
    return max(1, summary_tokens + sum(_message_tokens(message) for message in messages))


def _thresholds() -> tuple[int, int, int]:
    limit = max(1000, int(settings.CONTEXT_TOKEN_LIMIT))
    warning = int(limit * float(settings.CONTEXT_WARNING_RATIO))
    compact = int(limit * float(settings.CONTEXT_COMPACT_RATIO))
    return limit, warning, compact


def context_status(estimated_tokens: int) -> str:
    limit, warning, compact = _thresholds()
    if estimated_tokens <= 1:
        return "empty"
    if estimated_tokens >= compact:
        return "full"
    if estimated_tokens >= warning:
        return "warning"
    return "ok"


def _payload_from_context(context: dict[str, Any]) -> dict[str, Any]:
    token_limit = int(context.get("token_limit") or settings.CONTEXT_TOKEN_LIMIT)
    estimated = int(context.get("estimated_tokens") or 0)
    ratio = min(1.0, estimated / token_limit) if token_limit else 0.0
    return {
        "estimated_tokens": estimated,
        "token_limit": token_limit,
        "warning_threshold": int(context.get("warning_threshold") or 0),
        "compact_threshold": int(context.get("compact_threshold") or 0),
        "status": context.get("status") or context_status(estimated),
        "ratio": ratio,
        "percent": round(ratio * 100),
        "compaction_count": int(context.get("compaction_count") or 0),
        "last_compacted_event_id": context.get("last_compacted_event_id"),
        "updated_at": context.get("updated_at"),
    }


def chat_messages_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") not in CHAT_EVENT_TYPES:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        content = str(payload.get("content") or "").strip()
        files = payload.get("files") if isinstance(payload.get("files"), list) else []
        if files:
            file_lines = []
            for file in files[:8]:
                path = str(file.get("path") or file.get("name") or "").strip()
                summary = str(file.get("summary") or "").strip()
                if path:
                    file_lines.append(f"- {path}" + (f": {summary}" if summary else ""))
            if file_lines:
                content = (content + "\n\nArquivos enviados:\n" + "\n".join(file_lines)).strip()
        if not content:
            continue
        messages.append(
            {
                "event_id": int(event.get("event_id") or 0),
                "role": "user" if event.get("type") == "user_message" else "assistant",
                "content": content,
                "images": payload.get("images") if isinstance(payload.get("images"), list) else [],
            }
        )
    return messages


def _fallback_summary(previous_summary: str, messages: list[dict[str, Any]]) -> str:
    lines = [previous_summary.strip()] if previous_summary.strip() else []
    for message in messages:
        role = "Usuario" if message["role"] == "user" else "Assistente"
        content = " ".join(str(message.get("content") or "").split())
        lines.append(f"{role}: {content[:900]}")
    summary = "\n".join(line for line in lines if line).strip()
    return summary[-settings.CONTEXT_SUMMARY_MAX_CHARS :]


async def _summarize(previous_summary: str, messages: list[dict[str, Any]]) -> str:
    plain_messages = [
        {"role": message["role"], "content": str(message.get("content") or "")}
        for message in messages
    ]
    try:
        return await request_context_summary(
            previous_summary,
            plain_messages,
            max_chars=settings.CONTEXT_SUMMARY_MAX_CHARS,
        )
    except DeepSeekError:
        return _fallback_summary(previous_summary, messages)


def save_context_snapshot(
    task_id: str,
    *,
    summary: str,
    active_messages: list[dict[str, Any]],
    compaction_count: int,
    last_compacted_event_id: int | None,
    forced_status: str | None = None,
) -> dict[str, Any]:
    limit, warning, compact = _thresholds()
    estimated = estimate_messages_tokens(active_messages, summary)
    status = forced_status or context_status(estimated)
    return database.upsert_context(
        task_id,
        {
            "summary": summary,
            "estimated_tokens": estimated,
            "token_limit": limit,
            "warning_threshold": warning,
            "compact_threshold": compact,
            "status": status,
            "compaction_count": compaction_count,
            "last_compacted_event_id": last_compacted_event_id,
            "updated_at": utc_now(),
        },
    )


async def prepare_context_history(task_id: str, events: list[dict[str, Any]], fallback_description: str) -> tuple[list[dict[str, str]], dict[str, Any], bool]:
    saved = database.get_context(task_id) or {}
    summary = str(saved.get("summary") or "")
    compaction_count = int(saved.get("compaction_count") or 0)
    last_compacted_event_id = saved.get("last_compacted_event_id")
    last_compacted_event_id = int(last_compacted_event_id) if last_compacted_event_id is not None else None

    all_messages = chat_messages_from_events(events)
    active_messages = [
        message
        for message in all_messages
        if last_compacted_event_id is None or int(message.get("event_id") or 0) > last_compacted_event_id
    ]
    if not all_messages and fallback_description.strip():
        active_messages = [{"event_id": 0, "role": "user", "content": fallback_description.strip(), "images": []}]

    context = save_context_snapshot(
        task_id,
        summary=summary,
        active_messages=active_messages,
        compaction_count=compaction_count,
        last_compacted_event_id=last_compacted_event_id,
    )
    compacted = False

    if int(context["estimated_tokens"]) >= int(context["compact_threshold"]):
        keep_count = max(2, int(settings.CONTEXT_RECENT_MESSAGES))
        if len(active_messages) > keep_count:
            to_compact = active_messages[:-keep_count]
            kept = active_messages[-keep_count:]
            summary = await _summarize(summary, to_compact)
            compacted = True
            compaction_count += 1
            last_compacted_event_id = max(int(message.get("event_id") or 0) for message in to_compact)
            context = save_context_snapshot(
                task_id,
                summary=summary,
                active_messages=kept,
                compaction_count=compaction_count,
                last_compacted_event_id=last_compacted_event_id,
            )
            active_messages = kept

    history: list[dict[str, str]] = []
    if summary.strip():
        history.append(
            {
                "role": "system",
                "content": "Contexto compactado da conversa ate aqui:\n" + summary.strip(),
            }
        )
    history.extend(
        {"role": message["role"], "content": str(message.get("content") or "")}
        for message in active_messages
        if str(message.get("content") or "").strip()
    )
    if not history:
        history.append({"role": "user", "content": fallback_description})
    return history, _payload_from_context(context), compacted


def get_context_payload(task_id: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    saved = database.get_context(task_id)
    if saved:
        return _payload_from_context(saved)
    messages = chat_messages_from_events(events or [])
    context = save_context_snapshot(
        task_id,
        summary="",
        active_messages=messages,
        compaction_count=0,
        last_compacted_event_id=None,
    )
    return _payload_from_context(context)
