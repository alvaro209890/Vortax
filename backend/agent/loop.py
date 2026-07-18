"""Loop nativo do agente com function calling (plano-melhoria-ia Fase 1)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agent.gates import evaluate_delivery_gates, first_blocking_gate
from agent.state import TaskAgentState
from agent.tools.registry import openai_tools_payload, tool_is_read_only
from config import settings
from database import database
from services.activity_events import publish_agent_activity
from services.deepseek_client import (
    DeepSeekError,
    deepseek_configured,
    request_agent_turn,
)
from services.event_bus import EventBus
from services.task_plan_store import task_plan_store
from services.task_store import TaskStore
from tools.tool_executor import execute_tool

logger = logging.getLogger("vortax.agent.loop")


def _native_system_prompt(user_id: str | None = None) -> str:
    from services.code_agent import CODE_AGENT_COMMAND, CODE_AGENT_LABEL

    prompt = (
        "Você é o Vortax, agente autônomo neste PC Linux. "
        "Use function calling (tools) para agir. Não invente JSON de ação no content. "
        "Quando terminar de verdade, responda em markdown no content SEM tool_calls. "
        "Pesquise proativamente (browser_google_search + extract_article) para dados atuais. "
        "Para software grande use shell_run com "
        f"{CODE_AGENT_COMMAND} \"descrição\"; para ajustes pequenos use file_read/file_edit. "
        f"Agente de código configurado: {CODE_AGENT_LABEL} ({CODE_AGENT_COMMAND}). "
        "Nunca coloque senhas/tokens em parâmetros. "
        "Não exponha localhost na resposta final para usuários remotos. "
        "Use message_notify_user para progresso útil; message_ask_user para confirmações. "
        "Use todo_write para manter o plano vivo (1 item in_progress por vez). "
        "Tools estilo Claude Code/Manus: file_read→file_edit (sempre leia antes de editar); "
        "web_fetch para páginas estáticas (sem Chrome); shell_exec background=true + shell_view para builds longos; "
        "validate_project antes de finalizar código; document_render para MD→PDF. "
        "Responda em português do Brasil salvo pedido contrário."
    )
    if user_id:
        try:
            from services.user_memory import format_for_system_prompt

            memory_block = format_for_system_prompt(user_id)
            if memory_block:
                prompt = prompt + "\n\n" + memory_block
        except Exception:
            pass
    return prompt


async def _wait_paused(task_id: str, store: TaskStore, bus: EventBus) -> bool:
    while store.is_paused(task_id):
        if store.is_stopped(task_id):
            return False
        await bus.publish(task_id, "agent_status", {"status": "paused", "label": "Pausado"})
        await asyncio.sleep(0.4)
    return not store.is_stopped(task_id)


async def _handle_special_tool(
    name: str,
    args: dict[str, Any],
    *,
    task_id: str,
    store: TaskStore,
    bus: EventBus,
) -> dict[str, Any] | None:
    """Tools de agente tratadas no loop (não no tool_executor)."""
    if name == "message_notify_user":
        text = str(args.get("text") or "").strip()
        if text:
            await bus.publish(task_id, "assistant_message_done", {"content": text, "notice": True})
            await publish_agent_activity(
                bus, task_id, kind="analysis", title="Aviso ao usuário", detail=text[:200], status="done"
            )
        return {"success": True, "delivered": True}

    if name == "message_ask_user":
        question = str(args.get("question") or "").strip() or "Confirmar?"
        kind = str(args.get("kind") or "confirmation")
        await bus.publish(
            task_id,
            "confirmation_request",
            {
                "message": question,
                "kind": kind,
                "suggested_replies": args.get("suggested_replies") or [],
            },
        )
        store.request_confirmation(task_id)
        await bus.publish(task_id, "agent_status", {"status": "paused", "label": "Aguardando usuário"})
        if not await _wait_paused(task_id, store, bus):
            return {"success": False, "error": "tarefa interrompida"}
        approved = store.pop_confirmation(task_id)
        return {
            "success": True,
            "approved": approved,
            "answer": "sim" if approved else "não" if approved is False else "",
        }

    if name == "todo_write":
        todos = args.get("todos") or []
        if not isinstance(todos, list) or not todos:
            return {"success": False, "error": "todos vazio"}
        steps = []
        for i, item in enumerate(todos[:12], start=1):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "pending").lower()
            mapped = {
                "pending": "pending",
                "in_progress": "running",
                "completed": "passed",
                "done": "passed",
                "skipped": "skipped",
                "failed": "failed",
            }.get(status, "pending")
            steps.append(
                {
                    "label": str(item.get("label") or f"Etapa {i}")[:80],
                    "detail": str(item.get("detail") or "")[:500],
                    "tool_hint": "execute",
                    "acceptance_criteria": [str(item.get("label") or "ok")],
                    "_status": mapped,
                }
            )
        description = str(args.get("objective") or "")
        created = task_plan_store.replace_plan(task_id, steps, description or "Plano do modelo")
        from database import database as db
        from services.task_plan_store import utc_now

        now = utc_now()
        for step, raw in zip(created, steps):
            wanted = raw.get("_status") or "pending"
            if wanted == "running":
                db.update_task_step(
                    step["id"],
                    {"status": "running", "started_at": now, "updated_at": now},
                )
            elif wanted in {"passed", "failed", "skipped"}:
                task_plan_store.complete_step_by_id(step["id"], status=wanted)
        final = task_plan_store.list_steps(task_id)
        await bus.publish(task_id, "task_plan_replanned", {"steps": final, "origin": "model"})
        return {"success": True, "steps": len(final)}

    return None


async def run_native_agent_loop(
    task_id: str,
    description: str,
    store: TaskStore,
    bus: EventBus,
    *,
    user_profile: dict | None = None,
    research_mode: str = "fast",
) -> None:
    if not deepseek_configured():
        raise DeepSeekError("DeepSeek nao configurado para loop nativo")

    task = store.get(task_id) or {}
    user_id = str(task.get("user_id") or "") or None
    state = TaskAgentState(
        task_id=task_id,
        description=description,
        research_mode=research_mode,
        user_profile=user_profile,
    )

    store.update_status(task_id, "running")
    await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Trabalhando (nativo)"})
    await bus.publish(task_id, "agent_progress", {"label": "Loop nativo DeepSeek", "detail": description[:200]})

    # Plano inicial se vazio
    if not task_plan_store.list_steps(task_id):
        from services.task_plan_store import fallback_steps

        steps = task_plan_store.replace_plan(task_id, fallback_steps(description), description)
        await bus.publish(task_id, "task_plan_created", {"steps": steps, "origin": "native_fallback"})

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _native_system_prompt(user_id)},
        {"role": "user", "content": description},
    ]
    if user_profile:
        messages.append(
            {
                "role": "system",
                "content": "[PROFILE] " + json.dumps(user_profile, ensure_ascii=False)[:800],
            }
        )

    tools = openai_tools_payload()
    max_iter = int(settings.MAX_ITERATIONS or 30)

    for iteration in range(max_iter):
        state.iteration = iteration + 1
        if not await _wait_paused(task_id, store, bus):
            store.update_status(task_id, "stopped", result="Interrompido")
            await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida."})
            return

        await bus.publish(
            task_id,
            "agent_progress",
            {"label": "Planejando", "step": state.iteration},
        )

        turn = await request_agent_turn(
            messages,
            tools=tools,
            stream=bool(getattr(settings, "DEEPSEEK_STREAMING", False)),
            bus=bus,
            task_id=task_id,
            purpose="brain",
        )

        tool_calls = turn.get("tool_calls") or []
        content = (turn.get("content") or "").strip() if turn.get("content") else ""

        if tool_calls:
            # assistant message with tool_calls for API history
            raw = turn.get("raw_message")
            if raw:
                messages.append(raw)
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {
                                    "name": c["name"],
                                    "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                                },
                            }
                            for c in tool_calls
                        ],
                    }
                )

            # execute tools (parallel if all read-only and flag on)
            parallel_ok = bool(getattr(settings, "PARALLEL_TOOL_CALLS", True)) and all(
                tool_is_read_only(c["name"]) and c["name"] not in {"message_ask_user"} for c in tool_calls
            )

            async def _run_one(call: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
                name = call["name"]
                args = call.get("arguments") or {}
                special = await _handle_special_tool(name, args, task_id=task_id, store=store, bus=bus)
                if special is not None:
                    return call, special
                result = await execute_tool(
                    name,
                    args,
                    task_id=task_id,
                    bus=bus,
                    description=name,
                )
                data = result.get("data", result) if isinstance(result, dict) else {"result": result}
                return call, data if isinstance(data, dict) else {"result": data}

            if parallel_ok and len(tool_calls) > 1:
                pairs = await asyncio.gather(*[_run_one(c) for c in tool_calls])
            else:
                pairs = [await _run_one(c) for c in tool_calls]

            sources_before = len(database.list_sources(task_id))
            files_before = len(database.list_generated_files(task_id))

            for call, data in pairs:
                progressed = bool(data.get("success", True))
                state.note_tool(call["name"], call.get("arguments"), progressed=progressed)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(data, ensure_ascii=False, default=str)[:12000],
                    }
                )

            sources_after = len(database.list_sources(task_id))
            files_after = len(database.list_generated_files(task_id))
            if sources_after > sources_before or files_after > files_before:
                state.stagnant_iterations = 0

            if state.same_fingerprint_count >= 3:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "[GATE:cycle] Você repetiu a mesma tool/params 3x. "
                            "Mude de estratégia ou finalize com o melhor resultado parcial."
                        ),
                    }
                )
            continue

        # Sem tool_calls → tentativa de entrega final
        if not content:
            messages.append(
                {
                    "role": "system",
                    "content": "[GATE:empty] Resposta vazia. Continue com uma tool ou escreva a entrega final.",
                }
            )
            continue

        gate_ctx = {
            "task_id": task_id,
            "description": description,
            "user_prompt": description,
            "stagnant_iterations": state.stagnant_iterations,
        }
        results = evaluate_delivery_gates(gate_ctx)
        blocked = first_blocking_gate(results)
        if blocked is not None:
            messages.append({"role": "system", "content": blocked.as_system_message()})
            # se streaming já publicou deltas, ainda assim pedimos mais trabalho
            continue

        # Entrega
        if not (getattr(settings, "DEEPSEEK_STREAMING", False) and content):
            # se não streamou, publicar de uma vez
            # (com stream, deltas já saíram; ainda assim done fecha)
            chunk_size = 40
            for i in range(0, len(content), chunk_size):
                piece = content[i : i + chunk_size]
                await bus.publish(task_id, "assistant_message_delta", {"delta": piece, "content": piece})
                await asyncio.sleep(0)  # yield

        await bus.publish(task_id, "assistant_message_done", {"content": content})
        store.update_status(task_id, "done", result=content[:2000])
        # concluir plano
        for step in task_plan_store.list_steps(task_id):
            if step.get("status") in {"pending", "running"}:
                task_plan_store.complete_step_by_id(step["id"], status="passed")
        await bus.publish(task_id, "agent_status", {"status": "done", "label": "Concluído"})
        await publish_agent_activity(
            bus, task_id, kind="finalizing", title="Entrega final", detail="Loop nativo concluiu.", status="done"
        )
        return

    store.update_status(task_id, "error", result="Limite de iterações")
    await bus.publish(
        task_id,
        "assistant_message_done",
        {"content": f"Limite de iterações ({max_iter}) atingido sem entrega final."},
    )
    await bus.publish(task_id, "agent_status", {"status": "error", "label": "Limite de iterações"})
