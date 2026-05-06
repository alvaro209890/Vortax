import asyncio
import json
import shlex
from typing import Any
from pathlib import Path

from config import settings
from database import database
from services.context_manager import prepare_context_history
from services.deepseek_client import DeepSeekError, deepseek_configured, request_deepseek_action
from services.event_bus import EventBus
from services.mock_runner import run_mock_task
from services.research_policy import cross_check_status
from services.task_store import TaskStore
from tools.tool_executor import compact_tool_result, execute_tool


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
            if content and not content.startswith("Resultado da ferramenta:") and not content.startswith("Controle automatico de pesquisa:"):
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
        return {"required": True, "status": "pending", "reason": "Site criado pelo Vertex ainda nao passou pela validacao visual local."}

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
                pending_reasons.append("Projeto criado pelo Vertex ainda nao passou pela validacao automatica local.")
            elif label == "web_validation" and creation_command:
                pending_reasons.append("Projeto criado pelo Vertex ainda nao passou pela checagem de preview/web.")
            continue

        requires_validation = bool(result.get("requires_validation"))
        status = str(result.get("status") or "pending")
        if status == "blocked":
            blocked_reasons.append(str(result.get("reason") or "Validacao bloqueada."))
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
            "reason": "Validacao local encontrou bugs.",
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
            "reason": "Validacao local aprovada.",
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
        "Fontes ja abertas e salvas nesta conversa. Reutilize antes de pesquisar de novo quando responder ao mesmo tema; "
        "se precisar de informacao atual, controversa ou insuficiente, busque fontes adicionais. "
        "Quando browser_google_search retornar from_conversation_cache=true, nao use browser_click_link_by_index; use as evidencias salvas ou navegue direto pela URL se precisar reler.\n"
        + "\n".join(lines)
    )
    return [{"role": "system", "content": source_context}, *history]


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

        for iteration in range(settings.MAX_ITERATIONS):
            if not await _wait_if_paused_or_stopped(task_id, store, bus):
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
                        reason = str(validation_gate.get("reason") or "Validacao local obrigatoria indisponivel.")
                        raise DeepSeekError(reason)

                    bugs = validation_gate.get("bugs") or []
                    bug_text = "; ".join(str(item) for item in bugs[:8]) or str(validation_gate.get("reason") or "Validacao local ainda nao foi aprovada.")
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Corrigindo bugs do projeto",
                            "detail": "A tarefa nao pode finalizar antes da validacao local passar.",
                        },
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "Controle automatico de validacao local: nao finalize ainda. "
                                f"Status da validacao do projeto: {status}. "
                                f"Problemas encontrados: {bug_text}. "
                                "Use shell_run com vertex para corrigir exatamente esses bugs no projeto atual. "
                                "Isso vale para sites, sistemas, APIs, scripts Python, apps Node e qualquer outro codigo criado. "
                                "Depois da correcao, o Vortax repetira a validacao automatica e so entao podera finalizar. "
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
                store.update_status(task_id, "done", result=result)
                await bus.publish(task_id, "assistant_message_done", {"content": result})
                _, final_context, final_compacted = await prepare_context_history(task_id, bus.history(task_id), description)
                if final_compacted:
                    await bus.publish(task_id, "context_compacted", final_context)
                await bus.publish(task_id, "context_status", final_context)
                await bus.publish(task_id, "agent_status", {"status": "done", "label": "Concluído"})
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
            await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
            return

        raise DeepSeekError(f"Limite de iteracoes atingido ({settings.MAX_ITERATIONS}).")
    except asyncio.CancelledError:
        store.update_status(task_id, "stopped", result="Tarefa interrompida pelo usuario.")
        await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida pelo usuario."})
        await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
        return
    except DeepSeekError as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro no DeepSeek"})
    except Exception as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro"})
