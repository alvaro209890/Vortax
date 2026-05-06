from typing import Any, Awaitable, Callable

from database import database
from services.event_bus import EventBus
from services.safe_diagnostics import sanitize_payload
from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now
from tools.browser import browser_tool


ToolCallable = Callable[..., Awaitable[dict[str, Any]]]


TOOLS: dict[str, ToolCallable] = {
    "browser_navigate": browser_tool.navigate,
    "browser_get_state": browser_tool.get_state,
    "browser_click_text": browser_tool.click_text,
    "browser_click_selector": browser_tool.click_selector,
    "browser_click_link_by_index": browser_tool.click_link_by_index,
    "browser_type": browser_tool.type_text,
    "browser_press_key": browser_tool.press_key,
    "browser_wait_for_text": browser_tool.wait_for_text,
    "browser_go_back": browser_tool.go_back,
    "browser_google_search": browser_tool.google_search,
    "browser_extract_text": browser_tool.extract_text,
    "browser_extract_article": browser_tool.extract_article,
    "browser_extract_links": browser_tool.extract_links,
    "browser_screenshot": browser_tool.screenshot,
    "browser_scroll": browser_tool.scroll,
}


def compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    compact = dict(result)
    if "image_base64" in compact:
        compact["image_base64"] = "[base64-image]"
    text = compact.get("text")
    if isinstance(text, str) and len(text) > 1800:
        compact["text"] = f"{text[:1800]}... [truncated]"
    for key in ("links", "results"):
        items = compact.get(key)
        if isinstance(items, list):
            compact[key] = items[:10]
    return compact


async def _save_source_if_extracted(task_id: str, tool_name: str, result: dict[str, Any], bus: EventBus) -> None:
    if tool_name not in {"browser_extract_text", "browser_extract_article"}:
        return
    url = str(result.get("url") or "").strip()
    if not url or url.startswith("data:") or url == "about:blank":
        return
    text = str(result.get("text") or "").strip()
    title = str(result.get("title") or "").strip()
    source = database.upsert_source(
        task_id,
        {
            "url": url,
            "title": title,
            "snippet": result.get("description") or text[:280],
            "extracted_text": text[:10000],
            "source_type": source_type_for_url(url),
            "quality_score": source_quality_score(url, title, text),
            "used": True,
            "created_at": utc_now(),
        },
    )
    await bus.publish(
        task_id,
        "source_saved",
        {
            "id": source["id"],
            "url": source["url"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "quality_score": source.get("quality_score"),
        },
    )


async def _publish_screenshot_if_browser_action(task_id: str, tool_name: str, bus: EventBus) -> None:
    if not tool_name.startswith("browser_") or tool_name == "browser_screenshot":
        return
    try:
        frame = await browser_tool.screenshot(task_id=task_id)
        await bus.publish(
            task_id,
            "screen_frame",
            {
                "caption": frame.get("title") or frame.get("url") or "Tela do Chrome",
                "title": frame.get("title"),
                "url": frame.get("url"),
                "image_base64": frame.get("image_base64"),
            },
        )
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Screenshot apos tool falhou: {type(exc).__name__}"})


async def execute_tool(
    tool_name: str,
    params: dict[str, Any] | None,
    *,
    task_id: str,
    bus: EventBus,
    description: str = "",
) -> dict[str, Any]:
    safe_params = sanitize_payload(params or {})
    await bus.publish(
        task_id,
        "tool_call",
        {"name": tool_name, "description": description or tool_name, "params": safe_params},
    )

    tool = TOOLS.get(tool_name)
    if tool is None:
        error = {"success": False, "error": f"Ferramenta desconhecida: {tool_name}"}
        await bus.publish(task_id, "error", {"message": error["error"]})
        return error

    try:
        result = await tool(**(params or {}), task_id=task_id)
        await _save_source_if_extracted(task_id, tool_name, result, bus)
        compact = compact_tool_result(result)
        await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})
        if tool_name == "browser_screenshot":
            await bus.publish(
                task_id,
                "screen_frame",
                {
                    "caption": result.get("title") or result.get("url") or "Tela do Chrome",
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "image_base64": result.get("image_base64"),
                },
            )
        else:
            await _publish_screenshot_if_browser_action(task_id, tool_name, bus)
        return {"success": True, "data": result}
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        await bus.publish(task_id, "error", {"message": message, "tool": tool_name})
        return {"success": False, "error": message}
