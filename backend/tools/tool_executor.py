import re
import shlex
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from database import database
from services.event_bus import EventBus
from services.project_validation import validate_project_after_vertex
from services.research_policy import cached_search_result
from services.safe_diagnostics import sanitize_payload
from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now
from services.web_validation import validate_web_project_after_vertex, web_intent_from_command
from pathlib import Path
from services.project_files import sync_task_workspace_files

from config import settings
from tools.browser import browser_tool
from tools.exact import exact_tool
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
    "exact_solve": exact_tool.solve,
}


def compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    compact = dict(result)
    if compact.get("tty"):
        if compact.get("missing_assets"):
            compact["stdout"] = "Vertex retornou projeto incompleto; ha referencias locais ausentes."
        else:
            compact["stdout"] = "Vertex executou a tarefa. O andamento esta disponivel em vertex_progress e a validacao em web_validation_result."
        compact["stderr"] = str(compact.get("stderr") or "")[:500]
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

    for validation_key in ("web_validation", "project_validation"):
        validation = compact.get(validation_key)
        if isinstance(validation, dict):
            compact[validation_key] = {
                "status": validation.get("status"),
                "requires_validation": validation.get("requires_validation"),
                "reason": validation.get("reason"),
                "bugs": validation.get("bugs", [])[:8] if isinstance(validation.get("bugs"), list) else [],
                "warnings": validation.get("warnings", [])[:5] if isinstance(validation.get("warnings"), list) else [],
                "project": validation.get("project"),
            }

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
    return _split_vertex_command(command) is not None


def _vertex_creation_intent(command: str) -> bool:
    split = _split_vertex_command(command)
    if split is None:
        return False
    _, parts = split
    if any(part in {"--version", "-v", "--help", "help"} for part in parts[1:]):
        return False
    text = " ".join(parts[1:]).lower()
    return bool(
        web_intent_from_command(command)
        or re.search(
            r"\b(crie|criar|faca|faça|desenvolva|implemente|gere|corrija|bug|erro|falha|"
            r"software|sistema|script|api|backend|python|node|cli|automacao|automação|app)\b",
            text,
            re.IGNORECASE,
        )
    )


def _looks_like_manual_static_server(command: str) -> bool:
    text = str(command or "").lower()
    return "http.server" in text and ("python -m" in text or "python3 -m" in text)


def _preview_url_for_files(task_id: str, files: list[dict[str, Any]]) -> str | None:
    index_paths = sorted(
        str(file.get("path") or "")
        for file in files
        if str(file.get("path") or "").endswith("index.html")
    )
    if not index_paths:
        return None
    index_path = index_paths[0]
    url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{quote(task_id)}/"
    if index_path != "index.html":
        url += quote(index_path)
    return url


def _split_vertex_command(command: str) -> tuple[str, list[str]] | None:
    cmd = str(command or "").strip()
    cd_prefix = ""
    cd_match = None
    try:
        cd_match = shlex.split(cmd)
    except ValueError:
        return None

    if len(cd_match) >= 4 and cd_match[0] == "cd" and cd_match[2] == "&&":
        cd_path = Path(cd_match[1])
        if cd_path.is_absolute() or ".." in cd_path.parts:
            return None
        cd_prefix = f"cd {shlex.quote(cd_match[1])} && "
        args = cd_match[3:]
    else:
        args = cd_match

    if not args or args[0] != "vertex":
        return None
    return cd_prefix, args


def _augment_vertex_command_for_local_site(command: str) -> str:
    split = _split_vertex_command(command)
    if split is None or not web_intent_from_command(command):
        return command

    cd_prefix, parts = split

    pass_through_flags = {"-p", "--print", "--permission-mode", "--dangerously-skip-permissions", "--no-session-persistence"}
    prompt_parts: list[str] = []
    skip_next = False
    for part in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if part == "--permission-mode":
            skip_next = True
            continue
        if part.startswith("--permission-mode=") or part in pass_through_flags:
            continue
        prompt_parts.append(part)

    prompt = " ".join(prompt_parts).strip()
    instruction = "" if "LINK_LOCAL_DO_SITE" in prompt else (
        "\n\nObrigatorio para o Vortax: crie os arquivos do site dentro do diretorio atual. "
        "Para HTML/CSS/JavaScript estatico, NAO inicie servidor local e NAO rode modulo de servidor HTTP do Python; "
        "quando o pedido mencionar HTML, CSS e JavaScript/JS, crie obrigatoriamente arquivos separados index.html, style.css e script.js. "
        "Nao deixe href/src apontando para arquivos locais inexistentes. "
        "Garanta que exista um index.html funcional, pois o Vortax abrira o preview local automaticamente. "
        "Revise responsividade, estados de botoes, erros no console, textos cortados e arquivos vazios antes de finalizar. "
        "Somente se o projeto realmente exigir dev server, imprima uma linha exatamente no formato "
        "LINK_LOCAL_DO_SITE: http://127.0.0.1:PORTA ou LINK_LOCAL_DO_SITE: http://localhost:PORTA e finalize."
    )
    return (
        cd_prefix
        + "vertex -p --permission-mode bypassPermissions --dangerously-skip-permissions --no-session-persistence "
        + shlex.quote((prompt + instruction).strip())
    )


def _augment_vertex_command_for_quality(command: str) -> str:
    if web_intent_from_command(command):
        return _augment_vertex_command_for_local_site(command)

    split = _split_vertex_command(command)
    if split is None or not _vertex_creation_intent(command):
        return command

    cd_prefix, parts = split
    pass_through_flags = {"-p", "--print", "--permission-mode", "--dangerously-skip-permissions", "--no-session-persistence"}
    prompt_parts: list[str] = []
    skip_next = False
    for part in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if part == "--permission-mode":
            skip_next = True
            continue
        if part.startswith("--permission-mode=") or part in pass_through_flags:
            continue
        prompt_parts.append(part)

    prompt = " ".join(prompt_parts).strip()
    if "VALIDACAO_AUTOMATICA_VORTAX" in prompt:
        instruction = ""
    else:
        instruction = (
            "\n\nVALIDACAO_AUTOMATICA_VORTAX: entregue um projeto executavel e revisado dentro do diretorio atual. "
            "Se for Python, garanta que todos os arquivos .py passam em python3 -m py_compile e crie testes unittest quando fizer sentido. "
            "Se for Node/JavaScript, garanta package.json valido, sintaxe JS valida e scripts build/test quando o projeto precisar. "
            "Se estiver corrigindo uma falha anterior, preserve o projeto existente e corrija exatamente os bugs descritos. "
            "Nao finalize deixando TODO, arquivo vazio, dependencia quebrada, caminho inexistente ou instrucao que impeca a validacao local."
        )

    return (
        cd_prefix
        + "vertex -p --permission-mode bypassPermissions --dangerously-skip-permissions --no-session-persistence "
        + shlex.quote((prompt + instruction).strip())
    )


async def _open_static_preview_if_available(task_id: str, files: list[dict[str, Any]], bus: EventBus) -> None:
    index_paths = sorted(
        str(file.get("path") or "")
        for file in files
        if str(file.get("path") or "").endswith("index.html")
    )
    if not index_paths:
        return

    index_path = index_paths[0]
    preview_url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{quote(task_id)}/"
    if index_path != "index.html":
        preview_url += quote(index_path)
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
            if _looks_like_manual_static_server(command):
                project_dir = _project_dir(task_id)
                project_index = sync_task_workspace_files(task_id, project_dir)
                files = project_index["files"]
                preview_url = _preview_url_for_files(task_id, files)
                if preview_url:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Usando preview interno",
                            "detail": "Servidor manual ignorado para evitar conflito de porta; abrindo o site pelo preview do Vortax.",
                            "tool": "browser_navigate",
                        },
                    )
                    await bus.publish(
                        task_id,
                        "files_created",
                        {"files": files, "projects": project_index["projects"], "directory": str(project_dir)},
                    )
                    await _open_static_preview_if_available(task_id, files, bus)
                    result = {
                        "success": True,
                        "stdout": f"Preview interno do Vortax: {preview_url}",
                        "stderr": "",
                        "returncode": 0,
                        "local_urls": [preview_url],
                        "skipped_manual_server": True,
                    }
                    compact = compact_tool_result(result)
                    await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})
                    await _publish_screenshot_if_browser_action(task_id, tool_name, bus)
                    return {"success": True, "data": result}
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
            tool_params = dict(params or {})
            if _is_vertex_command(command):
                command = _augment_vertex_command_for_quality(command)
                tool_params["command"] = command
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "starting",
                        "message": "Vertex iniciou a criacao do projeto.",
                        "status": "running",
                    },
                )
            result = await tool(**tool_params, task_id=task_id, bus=bus)
        else:
            result = await tool(**(params or {}), task_id=task_id)
        # Após shell_run, lista arquivos criados e publica files_created
        if tool_name == "shell_run":
            project_dir = _project_dir(task_id)
            project_index = sync_task_workspace_files(task_id, project_dir)
            files = project_index["files"]
            command = str((params or {}).get("command", ""))
            validation = None
            project_validation = None
            if files:
                await bus.publish(
                    task_id,
                    "files_created",
                    {"files": files, "projects": project_index["projects"], "directory": str(project_dir)},
                )
                if _is_vertex_command(command):
                    await bus.publish(
                        task_id,
                        "vertex_progress",
                        {
                            "stage": "creating",
                            "message": f"Vertex gerou {len(files)} arquivo(s) no projeto.",
                            "status": "running",
                        },
                    )

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

            is_creation_vertex = _is_vertex_command(command) and _vertex_creation_intent(command)
            if _is_vertex_command(command) and result.get("success"):
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "validating",
                        "message": "Vortax esta validando o projeto criado pelo Vertex.",
                        "status": "running",
                    },
                )
                validation = await validate_web_project_after_vertex(task_id, command, bus, vertex_result=result)
                if is_creation_vertex:
                    project_validation = await validate_project_after_vertex(task_id, command, bus, vertex_result=result)
                if isinstance(result, dict):
                    result["web_validation"] = validation
                    if project_validation is not None:
                        result["project_validation"] = project_validation

            elif files:
                await _open_static_preview_if_available(task_id, files, bus)

            # Se foi vertex, publica progresso final
            if _is_vertex_command(command) and result.get("success"):
                validation_status = validation.get("status") if isinstance(validation, dict) else "skipped"
                project_validation_status = project_validation.get("status") if isinstance(project_validation, dict) else "skipped"
                if validation_status == "failed" or project_validation_status == "failed":
                    vertex_done_message = "Vertex concluiu o projeto, mas a validacao local encontrou bugs."
                elif validation_status == "blocked" or project_validation_status == "blocked":
                    vertex_done_message = "Vertex concluiu o projeto, mas a validacao visual esta bloqueada."
                elif validation_status == "passed" or project_validation_status == "passed":
                    vertex_done_message = "Vertex concluiu o projeto e a validacao local foi aprovada."
                else:
                    vertex_done_message = "Vertex concluiu o projeto."
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "done",
                        "message": vertex_done_message,
                        "status": "done",
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
