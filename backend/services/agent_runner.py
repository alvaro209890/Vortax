import asyncio
import json
from typing import Any

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
