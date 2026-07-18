"""web_fetch — HTTP fetch sem Chrome (padrão Manus web / Claude WebFetch).

Rápido e barato para docs, APIs JSON e páginas estáticas. Para JS/login use browser_*.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now

MAX_BYTES = 1_500_000
MAX_TEXT = 40_000
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; VortaxBot/1.0; +https://vortax-api.cursar.space) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def _html_to_text(html: str) -> str:
    cleaned = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", cleaned)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = _WS_RE.sub("\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _safe_url(url: str) -> str | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    # block obvious SSRF locals
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        return None
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return None
    return raw


async def web_fetch(
    url: str,
    *,
    task_id: str | None = None,
    max_chars: int = 12000,
    save_source: bool = True,
) -> dict[str, Any]:
    safe = _safe_url(url)
    if not safe:
        return {"success": False, "error": "URL invalida ou bloqueada (SSRF/local)."}

    try:
        timeout = httpx.Timeout(25.0, connect=8.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_UA, "Accept": "text/html,application/json,text/plain,*/*"},
        ) as client:
            response = await client.get(safe)
            content_type = (response.headers.get("content-type") or "").lower()
            raw = response.content[:MAX_BYTES]
            status = response.status_code
            final_url = str(response.url)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Falha HTTP: {type(exc).__name__}: {exc}"}

    if status >= 400:
        return {
            "success": False,
            "error": f"HTTP {status}",
            "url": final_url,
            "status_code": status,
        }

    text: str
    title = final_url
    if "application/json" in content_type or final_url.endswith(".json"):
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        title = "JSON"
        kind = "json"
    elif "text/html" in content_type or b"<html" in raw[:500].lower():
        html = raw.decode("utf-8", errors="replace")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
        text = _html_to_text(html)
        kind = "html"
    else:
        text = raw.decode("utf-8", errors="replace")
        kind = "text"

    text = text[: max(1000, min(max_chars, MAX_TEXT))]
    snippet = text[:300]

    result: dict[str, Any] = {
        "success": True,
        "url": final_url,
        "title": title,
        "content_type": content_type,
        "kind": kind,
        "status_code": status,
        "text": text,
        "snippet": snippet,
        "chars": len(text),
        "quality_score": source_quality_score(final_url, title, snippet),
        "source_type": source_type_for_url(final_url),
    }

    if save_source and task_id:
        try:
            from database import database

            database.upsert_source(
                task_id,
                {
                    "url": final_url,
                    "title": title,
                    "snippet": snippet,
                    "extracted_text": text[:8000],
                    "source_type": result["source_type"],
                    "quality_score": result["quality_score"],
                    "used": True,
                    "created_at": utc_now(),
                },
            )
            result["source_saved"] = True
        except Exception:
            result["source_saved"] = False

    return result
