from typing import Any, Awaitable, Callable
from urllib.parse import quote

from database import database
from services.event_bus import EventBus
from services.research_policy import cached_search_result
from services.safe_diagnostics import sanitize_payload
from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now
from pathlib import Path

from config import settings
from tools.browser import browser_tool
from tools.shell import _project_dir, run_shell
from tools.vision import vision_tool


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
    "shell_run": run_shell,
    "vision_analyze": vision_tool.analyze,
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

    # Se o resultado tem file_summary, preserva e adiciona nota de truncamento
    if compact.get("file_summary"):
        # Ja esta no formato certo, so garantir que nao e muito grande
        summary = compact["file_summary"]
        if isinstance(summary, dict) and summary.get("file_count", 0) > 100:
            summary["root_files"] = summary.get("root_files", [])[:30]
            summary["top_dirs"] = summary.get("top_dirs", [])[:15]
            summary["by_extension"] = dict(sorted(
                summary.get("by_extension", {}).items(),
                key=lambda x: -x[1]
            )[:10])
    if compact.get("stdout_truncated"):
        compact["_note"] = "A saida stdout foi truncada. Use o file_summary para ver a lista completa de arquivos gerados."

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
    if (not tool_name.startswith("browser_") and tool_name != "shell_run") or tool_name == "browser_screenshot":
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


def _is_vertex_command(command: str) -> bool:
    cmd = str(command or "").strip()
    for prefix in ("cd workspace && ", "cd ./workspace && ", "cd /workspace && "):
        if cmd.startswith(prefix):
            cmd = cmd[len(prefix):].lstrip()
    return bool(cmd.split()) and cmd.split()[0] == "vertex"


async def _open_static_preview_if_available(task_id: str, files: list[dict[str, Any]], bus: EventBus) -> None:
    has_index = any(str(file.get("path") or "") == "index.html" for file in files)
    if not has_index:
        return

    preview_url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{quote(task_id)}/"
    try:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Abrindo preview do site",
                "detail": "Carregando o index.html gerado no Chrome para validar visualmente.",
                "tool": "browser_navigate",
            },
        )
        await browser_tool.navigate(preview_url, task_id=task_id)
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Preview automatico falhou: {type(exc).__name__}: {exc}"})


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
        if tool_name == "browser_google_search":
            query = str((params or {}).get("query") or "").strip()
            cached = cached_search_result(query, database.list_sources(task_id)) if query else None
            if cached:
                await bus.publish(
                    task_id,
                    "agent_progress",
                    {
                        "label": "Reutilizando fontes da conversa",
                        "detail": "Busca ignorada porque ja ha fontes boas salvas para esta consulta.",
                        "tool": tool_name,
                    },
                )
                compact = compact_tool_result(cached)
                await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})
                return {"success": True, "data": cached}

        # shell_run recebe o bus para streaming de stdout
        if tool_name == "shell_run":
            command = str((params or {}).get("command", ""))
            if _is_vertex_command(command):
                await bus.publish(
                    task_id,
                    "ai_exchange",
                    {
                        "actor": "deepseek",
                        "target": "vertex",
                        "message": "DeepSeek delegou a criacao de codigo ao Vertex.",
                        "kind": "delegation",
                    },
                )
            result = await tool(**(params or {}), task_id=task_id, bus=bus)
        else:
            result = await tool(**(params or {}), task_id=task_id)
        await _save_source_if_extracted(task_id, tool_name, result, bus)
        compact = compact_tool_result(result)
        await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})

        # Após shell_run, lista arquivos criados e publica files_created
        if tool_name == "shell_run":
            from tools.shell import _list_files

            project_dir = _project_dir(task_id)
            files = await _list_files(project_dir)
            if files:
                await bus.publish(
                    task_id,
                    "files_created",
                    {"files": files, "directory": str(project_dir)},
                )
                await _open_static_preview_if_available(task_id, files, bus)

            # Se foi dev server, publica evento
            shell_data = result.get("data", result) if isinstance(result, dict) else {}
            if shell_data.get("is_dev_server") and shell_data.get("dev_server_url"):
                await bus.publish(
                    task_id,
                    "dev_server_started",
                    {
                        "url": shell_data["dev_server_url"],
                        "port": shell_data.get("dev_server_port"),
                        "task_id": task_id,
                    },
                )

            # Se foi vertex, publica progresso final
            command = str((params or {}).get("command", ""))
            if _is_vertex_command(command) and result.get("success"):
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "done",
                        "message": "Vertex concluiu o projeto.",
                        "interactive_rounds": shell_data.get("interactive_rounds", 0),
                    },
                )
                await bus.publish(
                    task_id,
                    "ai_exchange",
                    {
                        "actor": "vertex",
                        "target": "deepseek",
                        "message": "Vertex terminou a criacao do projeto e devolveu o resultado.",
                        "kind": "completion",
                    },
                )

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
