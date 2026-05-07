import asyncio
import json
import re
import shlex
from typing import Any
from pathlib import Path

from config import settings
from database import database
from services.context_manager import prepare_context_history
from services.deepseek_client import DeepSeekError, deepseek_configured, request_deepseek_action, request_direct_chat_response
from services.document_intent import (
    document_extensions_from_text,
    downloadable_document_files,
    markdown_documentation_files,
)
from services.event_bus import EventBus
from services.exact_solver import format_exact_answer, is_exact_prompt, should_answer_directly, solve_exact_problem
from services.mock_runner import run_mock_task
from services.research_policy import cross_check_status
from services.task_store import TaskStore
from tools.tool_executor import compact_tool_result, execute_tool
from services.web_validation import web_intent_from_command


LOCAL_PREVIEW_RE = re.compile(
    r"(?:LINK_LOCAL_DO_SITE:\s*)?https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)
LOCAL_PREVIEW_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:LINK_LOCAL_DO_SITE\s*:\s*)?https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}.*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def _message_history_from_events(events: list[dict[str, Any]], fallback_description: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for event in events:
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        content = str(payload.get("content") or "").strip()
        if not content:
            continue
        if event_type == "user_message":
            messages.append({"role": "user", "content": content})
        elif event_type == "assistant_message_done":
            messages.append({"role": "assistant", "content": content})

    if not messages:
        messages.append({"role": "user", "content": fallback_description})

    return messages[-12:]


def _progress_label(action_name: str, description: str) -> str:
    if action_name == "browser_google_search":
        return "Pesquisando no Google"
    if action_name == "browser_click_link_by_index":
        return "Abrindo resultado"
    if action_name in {"browser_extract_text", "browser_extract_links"}:
        return "Lendo conteudo da pagina"
    if action_name in {"browser_go_back", "browser_navigate"}:
        return "Navegando"
    if action_name.startswith("browser_"):
        return "Operando o navegador"
    return description or action_name


def _latest_user_prompt(history: list[dict[str, str]]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if (
                content
                and not content.startswith("Resultado da ferramenta:")
                and not content.startswith("Controle automatico de pesquisa:")
                and not content.startswith("Controle automatico de revisao")
                and not content.startswith("Controle automatico de validacao")
            ):
                return content
    return ""


def _is_vertex_shell_call(event: dict[str, Any]) -> bool:
    return _vertex_shell_command(event) is not None


def _vertex_shell_command(event: dict[str, Any]) -> str | None:
    if event.get("type") != "tool_call":
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload.get("name") != "shell_run":
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    command = str(params.get("command") or "").strip()
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if len(parts) >= 4 and parts[0] == "cd" and parts[2] == "&&":
        cd_path = Path(parts[1])
        if cd_path.is_absolute() or ".." in cd_path.parts:
            return None
        parts = parts[3:]
    return command if bool(parts) and parts[0] == "vertex" else None


def _looks_like_creation_vertex_command(command: str) -> bool:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        return False
    if len(parts) >= 4 and parts[0] == "cd" and parts[2] == "&&":
        parts = parts[3:]
    if not parts or parts[0] != "vertex":
        return False
    if any(part in {"--version", "-v", "--help", "help"} for part in parts[1:]):
        return False
    text = " ".join(parts[1:]).lower()
    return bool(
        text
        and any(
            keyword in text
            for keyword in (
                "api",
                "app",
                "automacao",
                "automação",
                "backend",
                "bug",
                "codigo",
                "código",
                "corrija",
                "crie",
                "criar",
                "dashboard",
                "desenvolva",
                "erro",
                "faça",
                "faca",
                "frontend",
                "html",
                "implemente",
                "interface",
                "node",
                "python",
                "react",
                "script",
                "site",
                "software",
                "sistema",
            )
        )
    )


def _latest_vertex_call(events: list[dict[str, Any]]) -> tuple[int, str] | None:
    latest: tuple[int, str] | None = None
    for event in events:
        command = _vertex_shell_command(event)
        if command is not None:
            latest = (int(event.get("event_id") or 0), command)
    return latest


def _latest_validation_payload(events: list[dict[str, Any]], latest_vertex_id: int, event_type: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in events:
        event_id = int(event.get("event_id") or 0)
        if event_id <= latest_vertex_id or event.get("type") != event_type:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        latest = payload
    return latest


def _latest_web_validation_gate(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_vertex_call(events)
    if latest_call is None:
        return {"required": False, "status": "not_required"}
    latest_vertex_id, command = latest_call
    latest_result = _latest_validation_payload(events, latest_vertex_id, "web_validation_result")

    if latest_result is None:
        if not _looks_like_creation_vertex_command(command):
            return {"required": False, "status": "not_required"}
        return {"required": True, "status": "pending", "reason": "Site criado pelo Vertex ainda nao passou pela revisao visual."}

    if not latest_result.get("requires_validation"):
        return {"required": False, "status": str(latest_result.get("status") or "skipped"), "result": latest_result}

    return {
        "required": True,
        "status": str(latest_result.get("status") or "pending"),
        "result": latest_result,
        "reason": latest_result.get("reason") or "",
        "bugs": latest_result.get("bugs") if isinstance(latest_result.get("bugs"), list) else [],
    }


def _latest_vertex_quality_gate(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_vertex_call(events)
    if latest_call is None:
        return {"required": False, "status": "not_required"}

    latest_vertex_id, command = latest_call
    web_result = _latest_validation_payload(events, latest_vertex_id, "web_validation_result")
    project_result = _latest_validation_payload(events, latest_vertex_id, "project_validation_result")
    creation_command = _looks_like_creation_vertex_command(command)

    pending_reasons: list[str] = []
    failed_bugs: list[str] = []
    blocked_reasons: list[str] = []
    passed_required = False

    for label, result in (("web_validation", web_result), ("project_validation", project_result)):
        if result is None:
            if label == "project_validation" and creation_command:
                pending_reasons.append("Projeto criado pelo Vertex ainda nao passou pela revisao automatica.")
            elif label == "web_validation" and creation_command:
                pending_reasons.append("Projeto criado pelo Vertex ainda nao passou pela revisao visual.")
            continue

        requires_validation = bool(result.get("requires_validation"))
        status = str(result.get("status") or "pending")
        if status == "blocked":
            blocked_reasons.append(str(result.get("reason") or "Revisao bloqueada."))
            continue
        if not requires_validation:
            continue
        if status == "passed":
            passed_required = True
            continue
        if status == "failed":
            bugs = result.get("bugs") if isinstance(result.get("bugs"), list) else []
            failed_bugs.extend(str(item) for item in bugs)
            if not bugs and result.get("reason"):
                failed_bugs.append(str(result["reason"]))
            continue
        pending_reasons.append(str(result.get("reason") or f"{label} ainda esta pendente."))

    if blocked_reasons:
        return {
            "required": True,
            "status": "blocked",
            "reason": " ".join(blocked_reasons),
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if failed_bugs:
        return {
            "required": True,
            "status": "failed",
            "reason": "Revisao automatica encontrou bugs.",
            "bugs": failed_bugs[:12],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if pending_reasons:
        return {
            "required": True,
            "status": "pending",
            "reason": " ".join(pending_reasons),
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if passed_required:
        return {
            "required": True,
            "status": "passed",
            "reason": "Revisao automatica aprovada.",
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    return {
        "required": False,
        "status": "not_required",
        "reason": "",
        "bugs": [],
        "web_validation": web_result,
        "project_validation": project_result,
    }


def _format_research_note(status: dict[str, Any]) -> str:
    required = int(status.get("required_sources") or 0)
    if required <= 1:
        return ""
    source_count = int(status.get("source_count") or 0)
    divergence = status.get("divergence") if isinstance(status.get("divergence"), dict) else {}
    if divergence.get("has_divergence"):
        categories = ", ".join(str(item.get("category")) for item in divergence.get("signals", []) if isinstance(item, dict))
        return f"\n\nVerificacao cruzada: {source_count} fontes relevantes consultadas. Possivel divergencia detectada em: {categories or 'dados extraidos'}."
    return f"\n\nVerificacao cruzada: {source_count} fontes relevantes consultadas; nenhuma divergencia automatica evidente foi detectada."


def _sanitize_chat_content(content: str) -> str:
    text = str(content or "")
    had_local_preview = bool(LOCAL_PREVIEW_RE.search(text) or "LINK_LOCAL_DO_SITE" in text)
    text = LOCAL_PREVIEW_LINE_RE.sub("", text)
    text = LOCAL_PREVIEW_RE.sub("preview interno do Vortax", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if had_local_preview:
        note = "O preview foi usado apenas para revisao interna e foi encerrado apos a entrega."
        if note not in text:
            text = f"{text}\n\n{note}".strip() if text else note
    return text or "Pronto. A entrega foi gerada e revisada pelo Vortax."


async def _cleanup_project_runtime(task_id: str, bus: EventBus, reason: str) -> None:
    try:
        from tools.shell import stop_dev_server

        stopped = await stop_dev_server(task_id)
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Falha ao encerrar preview interno: {type(exc).__name__}: {exc}"})
        return
    if stopped:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Preview interno encerrado",
                "detail": reason,
            },
        )
        await bus.publish(task_id, "dev_server_stopped", {"task_id": task_id, "reason": reason})


def _file_payload(file: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": file.get("path"),
        "name": Path(str(file.get("path") or "arquivo")).name,
        "extension": file.get("extension") or Path(str(file.get("path") or "")).suffix.lower(),
        "size_bytes": int(file.get("size_bytes") or file.get("size") or 0),
        "project_name": file.get("project_name"),
    }


def _generated_file_response_payload(task_id: str, result: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_vertex_call(events)
    if latest_call is None:
        return {"content": result}

    _, command = latest_call
    files = database.list_generated_files(task_id)
    requested_extensions = document_extensions_from_text(command)
    docs = markdown_documentation_files(files)
    requested_downloads = downloadable_document_files(files, requested_extensions)
    is_web_project = web_intent_from_command(command)

    downloads: list[dict[str, Any]] = []
    for file in [*requested_downloads, *(docs if is_web_project else [])]:
        payload = _file_payload(file)
        if payload["path"] and all(existing.get("path") != payload["path"] for existing in downloads):
            downloads.append(payload)

    if not downloads and not docs:
        return {"content": result}

    payload: dict[str, Any] = {"content": result, "downloads": downloads[:8]}
    if docs:
        payload["documentation"] = _file_payload(docs[0])

    if is_web_project and docs:
        payload["content"] = (
            "Pronto. Criei o site solicitado, revisei o projeto e gerei a documentacao em Markdown. "
            "Abra o card Documentacao para ler no Vortax ou use o botao abaixo para baixar."
        )
    elif requested_downloads:
        payload["content"] = "Pronto. Gerei o arquivo solicitado. Use o botao abaixo para baixar."

    return payload


def _history_with_research_context(task_id: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    sources = database.list_sources(task_id)[:8]
    if not sources:
        return history
    lines = []
    for source in sources:
        title = source.get("title") or source.get("url")
        score = source.get("quality_score", 0)
        source_type = source.get("source_type") or "web"
        snippet = str(source.get("snippet") or "").strip()
        excerpt = str(source.get("extracted_text") or "").strip()
        detail = snippet or excerpt
        lines.append(f"- [{source_type} {score}/100] {title}: {source.get('url')}" + (f" — {detail[:520]}" if detail else ""))
    source_context = (
        "Fontes ja abertas e salvas nesta conversa. IMPORTANTE: Se voce for criar software com Vertex, "
        "USE estas fontes para enriquecer o prompt. Extraia destas fontes: tendencias de design, exemplos "
        "de layout, paleta de cores, estrutura de navegacao, tecnologias recomendadas e boas praticas. "
        "Se houver resultado de vision_analyze no historico, ELE contem analise visual com cores exatas, "
        "estrutura de layout, estilo visual, tipografia e elementos de UI — incorpore TUDO no prompt do Vertex. "
        "Monte um prompt detalhado para o Vertex que inclua referencias concretas extraidas das fontes "
        "(ex: 'crie um site inspirado nas referencias de [URL], usando paleta de cores similar, layout com "
        "hero section, navegacao superior, secao de depoimentos e rodape com contato'). "
        "Reutilize antes de pesquisar de novo quando responder ao mesmo tema; "
        "se precisar de informacao atual, controversa ou insuficiente, busque fontes adicionais. "
        "Quando browser_google_search retornar from_conversation_cache=true, nao use browser_click_link_by_index; use as evidencias salvas ou navegue direto pela URL se precisar reler.\n"
        + "\n".join(lines)
    )
    return [{"role": "system", "content": source_context}, *history]


async def _finish_text_response(
    task_id: str,
    description: str,
    result: str,
    store: TaskStore,
    bus: EventBus,
) -> None:
    payload = _generated_file_response_payload(task_id, result, bus.history(task_id))
    final_content = _sanitize_chat_content(str(payload.get("content") or result))
    payload["content"] = final_content
    store.update_status(task_id, "done", result=final_content)
    await bus.publish(task_id, "assistant_message_done", payload)
    await _cleanup_project_runtime(task_id, bus, "Servidor temporario do projeto fechado apos a resposta no chat.")
    _, final_context, final_compacted = await prepare_context_history(task_id, bus.history(task_id), description)
    if final_compacted:
        await bus.publish(task_id, "context_compacted", final_context)
    await bus.publish(task_id, "context_status", final_context)
    await bus.publish(task_id, "agent_status", {"status": "done", "label": "Entrega pronta"})


async def _answer_exact_prompt(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    store: TaskStore,
    bus: EventBus,
) -> None:
    await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Calculando"})
    await bus.publish(task_id, "agent_progress", {"label": "Resolvendo com tool de exatas", "detail": description, "tool": "exact_solve"})
    await bus.publish(task_id, "tool_call", {"name": "exact_solve", "description": "Resolver pergunta de matematica/exatas", "params": {"problem": description}})
    exact_result = solve_exact_problem(description)
    await bus.publish(task_id, "tool_result", {"name": "exact_solve", "result": exact_result})

    if exact_result.get("status") == "solved":
        await _finish_text_response(task_id, description, format_exact_answer(exact_result), store, bus)
        return

    direct = await request_direct_chat_response(
        history,
        mode="exact",
        tool_context={"exact_solve": exact_result},
    )
    await _finish_text_response(task_id, description, direct["content"], store, bus)


async def _answer_simple_prompt(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    store: TaskStore,
    bus: EventBus,
) -> None:
    await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Respondendo"})
    await bus.publish(task_id, "agent_progress", {"label": "Resposta rapida", "detail": "Sem planner e sem Vertex para pergunta simples."})
    direct = await request_direct_chat_response(history, mode="direct")
    await _finish_text_response(task_id, description, direct["content"], store, bus)


async def _wait_if_paused_or_stopped(task_id: str, store: TaskStore, bus: EventBus) -> bool:
    while store.is_paused(task_id):
        if store.is_stopped(task_id):
            await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Tarefa parada"})
            return False
        await bus.publish(task_id, "agent_status", {"status": "paused", "label": "Pausado"})
        import asyncio

        await asyncio.sleep(0.5)
    if store.is_stopped(task_id):
        await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Tarefa parada"})
        return False
    return True


async def _inject_pre_research_if_needed(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    bus: EventBus,
) -> list[dict[str, str]]:
    """Analisa o pedido e, se for criacao de software viavel para pesquisa, executa
    pesquisa web automatica e alimenta o historico para o DeepSeek usar ao planejar."""
    from services.research_policy import relevant_sources_for_query, software_research_profile

    profile = software_research_profile(description)
    if not profile.get("is_software_request") or not profile.get("requires_pre_research"):
        return history

    # Verifica se o historico ja tem resultados de pesquisa (evita repetir)
    for msg in history:
        content = str(msg.get("content") or "")
        if "Resultado da ferramenta:" in content and "browser_google_search" in content:
            return history

    research_queries = profile.get("research_queries", [])
    if not research_queries:
        return history

    # Verifica se ja ha fontes relevantes salvas para esta task
    existing_sources = database.list_sources(task_id)
    if existing_sources:
        relevant = relevant_sources_for_query(description, existing_sources, limit=3)
        if len(relevant) >= 2:
            return _history_with_research_context(task_id, history)

    await bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Pesquisando referencias antes de criar"},
    )

    pesquisa_feita = False
    for query in research_queries[:2]:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisando referencias e tendencias",
                "detail": f"Buscando: {query}",
                "tool": "browser_google_search",
            },
        )
        try:
            from tools.tool_executor import execute_tool

            search_result = await execute_tool(
                "browser_google_search",
                {"query": query, "hl": "pt-BR"},
                task_id=task_id,
                bus=bus,
                description=f"Pesquisa automatica de referencias: {query}",
            )
            if search_result.get("success"):
                pesquisa_feita = True
                data = search_result.get("data", {})
                results = data.get("results", [])
                if results:
                    best = results[0]
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Abrindo referencia",
                            "detail": f"Abrindo: {best.get('title') or best.get('href', 'resultado')}",
                            "tool": "browser_navigate",
                        },
                    )
                    await execute_tool(
                        "browser_navigate",
                        {"url": best.get("href")},
                        task_id=task_id,
                        bus=bus,
                        description="Abrindo melhor resultado da pesquisa",
                    )
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Extraindo referencia",
                            "detail": "Extraindo conteudo da pagina de referencia",
                            "tool": "browser_extract_article",
                        },
                    )
                    await execute_tool(
                        "browser_extract_article",
                        {},
                        task_id=task_id,
                        bus=bus,
                        description="Extraindo conteudo da referencia",
                    )
                    # Analise visual da pagina de referencia
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Analisando design da referencia",
                            "detail": "Usando visao computacional para extrair cores, layout e estilo visual.",
                            "tool": "vision_analyze",
                        },
                    )
                    await execute_tool(
                        "vision_analyze",
                        {
                            "question": (
                                "Analise este design de referencia em detalhes. "
                                "Extraia: paleta de cores usada (cores principais, secundarias, de destaque), "
                                "estrutura de layout (hero, grid, sidebar, navegacao, footer), "
                                "tipografia aparente (serifada, sans-serif, mono), "
                                "estilo visual (flat, minimalista, material, neumorphism, moderno), "
                                "elementos de UI (botoes, cards, modais, formularios, icons), "
                                "e qualquer detalhe de design que possa servir de inspiracao. "
                                "Seja detalhado e especifico."
                            ),
                        },
                        task_id=task_id,
                        bus=bus,
                        description="Analise visual do design de referencia",
                    )
        except Exception:
            pass  # Falha na pesquisa nao deve bloquear o fluxo

    if pesquisa_feita:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisa de referencias concluida",
                "detail": "Dados coletados. O DeepSeek usara as referencias ao planejar a criacao com Vertex.",
            },
        )
    return _history_with_research_context(task_id, history)


async def _inject_people_research_if_needed(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    bus: EventBus,
) -> list[dict[str, str]]:
    """Analisa se o pedido e sobre uma pessoa e, em caso positivo, executa
    pesquisa web automatica com multiplas consultas em diversas plataformas."""
    from services.research_policy import people_research_profile

    profile = people_research_profile(description)
    if not profile.get("is_people_search"):
        return history

    person_name = profile.get("person_name")
    search_queries = profile.get("search_queries", [])
    if not person_name or not search_queries:
        return history

    # Verifica se ja tem fontes sobre este nome
    from services.research_policy import relevant_sources_for_query
    existing_sources = database.list_sources(task_id)
    if existing_sources:
        relevant = relevant_sources_for_query(person_name, existing_sources, limit=3, min_quality=40)
        if len(relevant) >= profile.get("required_sources", 3):
            return _history_with_research_context(task_id, history)

    await bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Pesquisando informacoes da pessoa"},
    )
    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Pesquisando pessoa em multiplas plataformas",
            "detail": f"Buscando informacoes sobre: {person_name}",
        },
    )

    pesquisa_feita = False
    categories = profile.get("categories", [])

    for query in search_queries[:5]:  # Max 5 consultas
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Buscando em plataforma",
                "detail": f"Consulta: {query[:120]}",
                "tool": "browser_google_search",
            },
        )
        try:
            from tools.tool_executor import execute_tool

            search_result = await execute_tool(
                "browser_google_search",
                {"query": query, "hl": "pt-BR"},
                task_id=task_id,
                bus=bus,
                description=f"Pesquisa sobre pessoa: {query[:100]}",
            )
            if search_result.get("success"):
                pesquisa_feita = True
                data = search_result.get("data", {})
                results = data.get("results", [])
                if results:
                    # Tenta abrir o melhor resultado que nao seja login/agregador fraco
                    for result in results[:3]:
                        href = str(result.get("href") or "")
                        title = str(result.get("title") or "")
                        # Pula paginas de login, anúncios e agregadores
                        if any(skip in href.lower() for skip in
                               ["accounts.google", "servicelogin", "login", "signin", "ads.",
                                "googleadservices", "facebook.com/settings"]):
                            continue
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Abrindo perfil encontrado",
                                "detail": f"Abrindo: {title[:80]}",
                                "tool": "browser_navigate",
                            },
                        )
                        await execute_tool(
                            "browser_navigate",
                            {"url": href},
                            task_id=task_id,
                            bus=bus,
                            description="Abrindo resultado de busca sobre pessoa",
                        )
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Extraindo informacoes",
                                "detail": f"Extraindo dados de: {title[:80]}",
                                "tool": "browser_extract_article",
                            },
                        )
                        await execute_tool(
                            "browser_extract_article",
                            {},
                            task_id=task_id,
                            bus=bus,
                            description="Extraindo informacoes sobre a pessoa",
                        )
                        break  # Abre so um resultado por consulta
        except Exception:
            pass  # Falha nao bloqueia o fluxo

    # Se tiver LinkedIn, GitHub ou Instagram, tenta busca direta
    linkedin_queries = [q for q in search_queries if "linkedin" in q.lower()]
    github_queries = [q for q in search_queries if "github" in q.lower()]

    for extra_query in (linkedin_queries + github_queries)[:2]:
        try:
            from tools.tool_executor import execute_tool as et

            result = await et(
                "browser_google_search",
                {"query": extra_query, "hl": "pt-BR"},
                task_id=task_id,
                bus=bus,
                description=f"Busca adicional em rede profissional: {extra_query[:80]}",
            )
            if result.get("success"):
                data = result.get("data", {})
                results = data.get("results", [])
                if results:
                    href = str(results[0].get("href") or "")
                    if not any(skip in href.lower() for skip in
                               ["accounts.google", "servicelogin", "login", "signin"]):
                        await et(
                            "browser_navigate",
                            {"url": href},
                            task_id=task_id,
                            bus=bus,
                            description="Abrindo perfil profissional",
                        )
                        await et(
                            "browser_extract_article",
                            {},
                            task_id=task_id,
                            bus=bus,
                            description="Extraindo perfil profissional",
                        )
        except Exception:
            pass

    if pesquisa_feita:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisa sobre pessoa concluida",
                "detail": f"Dados coletados sobre {person_name} em multiplas plataformas.",
            },
        )

    # Usa o contexto enriquecido com fontes, mas com aviso de pessoa
    research_history = _history_with_research_context(task_id, history)
    # Adiciona instrucao especifica de pessoa no inicio
    people_instruction = (
        "ATENCAO: Este pedido envolve pesquisa sobre uma PESSOA. "
        "Voce DEVE utilizar as fontes acima para montar um perfil completo. "
        "Para CADA informacao relevante, indique de qual URL/fonte veio. "
        "Se informacoes importantes nao foram encontradas (LinkedIn, GitHub, formacao, experiencia), "
        "declare explicitamente o que NAO foi encontrado. "
        "NAO resuma informacoes vagas — extraia dados concretos das fontes abertas. "
        f"Pessoa pesquisada: {person_name}. "
        f"Plataformas sugeridas: {', '.join(categories)}."
    )
    # Preserva o history original mas com people_instruction como primeiro system msg
    return [{"role": "system", "content": people_instruction}, *research_history]


async def run_agent_task(task_id: str, description: str, store: TaskStore, bus: EventBus) -> None:
    if not deepseek_configured():
        history, context_payload, compacted = await prepare_context_history(task_id, bus.history(task_id), description)
        _ = history
        if compacted:
            await bus.publish(task_id, "context_compacted", context_payload)
        await bus.publish(task_id, "context_status", context_payload)
        await bus.publish(
            task_id,
            "tool_result",
            {"name": "deepseek_config", "result": "Sem DEEPSEEK_API_KEY; usando runner mockado."},
        )
        await run_mock_task(task_id, description, store, bus)
        return

    try:
        store.update_status(task_id, "running")
        history, context_payload, compacted = await prepare_context_history(task_id, bus.history(task_id), description)
        if compacted:
            await bus.publish(task_id, "context_compacted", context_payload)
        await bus.publish(task_id, "context_status", context_payload)
        await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Trabalhando"})
        await bus.publish(task_id, "agent_progress", {"label": "Analisando pedido", "detail": description})

        latest_prompt = _latest_user_prompt(history) or description
        if is_exact_prompt(latest_prompt):
            await _answer_exact_prompt(task_id, latest_prompt, history, store, bus)
            return
        if should_answer_directly(latest_prompt):
            await _answer_simple_prompt(task_id, latest_prompt, history, store, bus)
            return

        # Pesquisa previa automatica antes do loop ReAct
        history = await _inject_pre_research_if_needed(task_id, latest_prompt, history, bus)

        # Pesquisa automatica de pessoas antes do loop ReAct
        history = await _inject_people_research_if_needed(task_id, latest_prompt, history, bus)

        for iteration in range(settings.MAX_ITERATIONS):
            if not await _wait_if_paused_or_stopped(task_id, store, bus):
                await _cleanup_project_runtime(task_id, bus, "Tarefa parada; preview interno fechado.")
                return

            await bus.publish(task_id, "agent_progress", {"label": "Planejando proximo passo", "step": iteration + 1})
            action = await request_deepseek_action(_history_with_research_context(task_id, history))
            history.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})

            action_name = str(action.get("action", "")).strip()
            if action_name == "finish":
                validation_gate = _latest_vertex_quality_gate(bus.history(task_id))
                if validation_gate.get("required") and validation_gate.get("status") != "passed":
                    status = str(validation_gate.get("status") or "pending")
                    if status == "blocked":
                        reason = str(validation_gate.get("reason") or "Revisao automatica obrigatoria indisponivel.")
                        raise DeepSeekError(reason)

                    bugs = validation_gate.get("bugs") or []
                    bug_text = "; ".join(str(item) for item in bugs[:8]) or str(validation_gate.get("reason") or "Revisao automatica ainda nao foi aprovada.")
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Corrigindo bugs do projeto",
                            "detail": "A tarefa nao pode finalizar antes da revisao automatica passar.",
                        },
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "Controle automatico de revisao da entrega: nao finalize ainda. "
                                f"Status da revisao do projeto: {status}. "
                                f"Problemas encontrados: {bug_text}. "
                                "Use shell_run com vertex para corrigir exatamente esses bugs no projeto atual. "
                                "Isso vale para sites, sistemas, APIs, scripts Python, apps Node e qualquer outro codigo criado. "
                                "Depois da correcao, o Vortax repetira a revisao automatica e so entao podera finalizar. "
                                "Para HTML/CSS/JS estatico, nao suba servidor manual; o Vortax abrira o preview interno."
                            ),
                        }
                    )
                    continue

                result = str(action.get("result") or action.get("params", {}).get("result") or "Tarefa concluida.")
                research_prompt = _latest_user_prompt(history) or description
                research_status = cross_check_status(research_prompt, database.list_sources(task_id))
                if not research_status.get("satisfied"):
                    required = int(research_status.get("required_sources") or 0)
                    found = int(research_status.get("source_count") or 0)
                    if required > 0:
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Verificando fontes",
                                "detail": f"Resposta ainda precisa de {required} fonte(s) relevante(s); ha {found}.",
                            },
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    "Controle automatico de pesquisa: nao finalize ainda. "
                                    f"A pergunta exige pelo menos {required} fonte(s) relevante(s) e ha {found}. "
                                    "Use fontes ja salvas se forem suficientes para o mesmo assunto; caso contrario, pesquise/abra/extrai outra fonte. "
                                    "Para preco, versao, documentacao, noticia, dado sensivel ou comparacao, faca verificacao cruzada e marque divergencias na resposta final."
                                ),
                            }
                        )
                        continue
                result = result + _format_research_note(research_status)
                await _finish_text_response(task_id, description, result, store, bus)
                return

            if action.get("requires_confirmation"):
                message = action.get("confirmation_message") or action.get("description") or "Confirmar acao?"
                await bus.publish(
                    task_id,
                    "confirmation_request",
                    {"message": message, "action": action_name, "params": action.get("params", {})},
                )
                raise DeepSeekError("Planner pediu confirmacao; fluxo de confirmacao sera ligado no proximo bloco.")

            progress_label = _progress_label(action_name, str(action.get("description") or ""))
            await bus.publish(
                task_id,
                "agent_progress",
                {"label": progress_label, "detail": action.get("description") or action_name, "tool": action_name},
            )
            await bus.publish(task_id, "agent_status", {"status": "executing", "label": "Executando"})

            # Checa se foi interrompido antes de executar a ferramenta
            if store.is_stopped(task_id):
                break

            tool_result = await execute_tool(
                action_name,
                action.get("params") if isinstance(action.get("params"), dict) else {},
                task_id=task_id,
                bus=bus,
                description=str(action.get("description") or action_name),
            )

            # Checa se foi interrompido apos a ferramenta (o usuario pode ter clicado stop durante)
            if store.is_stopped(task_id):
                break

            result_for_model = compact_tool_result(tool_result.get("data", tool_result) if isinstance(tool_result, dict) else {"result": tool_result})
            history.append(
                {
                    "role": "user",
                    "content": "Resultado da ferramenta: " + json.dumps(result_for_model, ensure_ascii=False),
                }
            )

        if store.is_stopped(task_id):
            store.update_status(task_id, "stopped", result="Tarefa interrompida pelo usuario.")
            await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida pelo usuario."})
            await _cleanup_project_runtime(task_id, bus, "Tarefa interrompida; preview interno fechado.")
            await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
            return

        raise DeepSeekError(f"Limite de iteracoes atingido ({settings.MAX_ITERATIONS}).")
    except asyncio.CancelledError:
        store.update_status(task_id, "stopped", result="Tarefa interrompida pelo usuario.")
        await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida pelo usuario."})
        await _cleanup_project_runtime(task_id, bus, "Tarefa cancelada; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
        return
    except DeepSeekError as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await _cleanup_project_runtime(task_id, bus, "Tarefa finalizada com erro; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro no DeepSeek"})
    except Exception as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await _cleanup_project_runtime(task_id, bus, "Tarefa finalizada com erro; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro"})
