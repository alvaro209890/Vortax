"""Replanejamento real mid-run do Plano Vivo.

Detecta mudança relevante de objetivo durante o loop ReAct e emite
`task_plan_replanned`, preservando etapas já concluídas (passed/failed/skipped)
como histórico em evidence e gerando novas etapas para o restante do trabalho.
"""

from __future__ import annotations

import re
from typing import Any

from services.deepseek_client import (
    DeepSeekError,
    request_task_plan,
    task_planner_configured,
)
from services.event_bus import EventBus
from services.task_plan_store import fallback_steps, task_plan_store


_STOPWORDS = {
    "para", "com", "uma", "por", "que", "dos", "das", "the", "and", "for",
    "com", "sem", "mais", "menos", "como", "este", "esta", "isso", "aquele",
    "fazer", "crie", "criar", "gere", "gerar", "preciso", "quero", "pode",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9_]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def objective_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def should_replan(
    *,
    original_objective: str,
    latest_user_prompt: str,
    last_tool: str | None,
    last_tool_ok: bool,
    iteration: int,
    already_replanned: bool,
    force: bool = False,
) -> tuple[bool, str]:
    """Retorna (deve_replanejar, motivo)."""
    if force:
        return True, "force"
    if already_replanned and iteration > 2:
        # evita replan em loop; permite 1 replan natural por run + force
        pass

    latest = (latest_user_prompt or "").strip()
    original = (original_objective or "").strip()
    if not latest or not original:
        return False, ""

    # Usuário mudou o pedido de forma clara (baixo overlap lexical)
    sim = objective_similarity(original, latest)
    if sim < 0.28 and len(_tokens(latest)) >= 3 and latest.lower() != original.lower():
        return True, f"objetivo divergiu (similaridade={sim:.2f})"

    # Pivô pesquisa → desenvolvimento
    research_tools = {"browser_google_search", "browser_extract_article", "browser_extract_text", "browser_navigate"}
    dev_signals = ("crie", "criar", "implemente", "código", "codigo", "site", "app", "projeto", "corrija", "refatore")
    if last_tool in research_tools and any(s in latest.lower() for s in dev_signals) and sim < 0.55:
        return True, "pivot pesquisa→desenvolvimento"

    # Tool crítica falhou e o pedido pede caminho alternativo
    if last_tool and not last_tool_ok and any(
        phrase in latest.lower() for phrase in ("em vez", "ao inves", "ao invés", "outra forma", "diferente", "ignore")
    ):
        return True, f"falha em {last_tool} + pedido de caminho alternativo"

    return False, ""


async def replan_task(
    task_id: str,
    new_objective: str,
    bus: EventBus,
    *,
    reason: str,
) -> list[dict[str, Any]]:
    """Gera novo plano, preserva steps done como evidência histórica, publica evento."""
    previous = task_plan_store.list_steps(task_id)
    done = [s for s in previous if s.get("status") in {"passed", "failed", "skipped"}]
    running = [s for s in previous if s.get("status") == "running"]

    # Marca running como skipped com evidência de replan
    for step in running:
        task_plan_store.complete_step_by_id(
            step["id"],
            status="skipped",
            evidence={"status": "skipped", "summary": f"Replanejado: {reason}"},
        )

    raw_steps: list[dict[str, Any]] = []
    plan_result: dict[str, Any] = {}
    warning = ""
    if task_planner_configured():
        try:
            plan_result = await request_task_plan(new_objective)
            raw_steps = plan_result.get("plan", []) or []
        except DeepSeekError as exc:
            warning = str(exc)

    # Prefixar histórico resumido do que já foi feito
    history_note = ""
    if done:
        labels = ", ".join(str(s.get("label") or "") for s in done[:6])
        history_note = f"Já concluído antes do replan: {labels}. "

    steps = task_plan_store.replace_plan(
        task_id,
        raw_steps or fallback_steps(new_objective),
        f"{history_note}{new_objective}",
    )

    # Anexa evidência do replan na primeira etapa nova
    if steps and done:
        from database import database
        from services.task_plan_store import utc_now

        first_id = steps[0]["id"]
        step = database.get_task_step(first_id)
        if step:
            evidences = list(step.get("evidence") or [])
            evidences.append(
                {
                    "status": "info",
                    "summary": f"Replan mid-run ({reason}). Etapas anteriores preservadas: {len(done)}.",
                    "previous_steps": [
                        {"label": s.get("label"), "status": s.get("status")} for s in done
                    ],
                }
            )
            database.update_task_step(first_id, {"evidence": evidences[-12:], "updated_at": utc_now()})
            steps = task_plan_store.list_steps(task_id)

    payload: dict[str, Any] = {
        "steps": steps,
        "reason": reason,
        "objective": new_objective,
        "preserved_completed": len(done),
        "fallback": not bool(raw_steps),
    }
    if plan_result.get("planner_provider"):
        payload["planner"] = {
            "provider": plan_result.get("planner_provider"),
            "model": plan_result.get("planner_model"),
        }
    if warning:
        payload["warning"] = warning

    await bus.publish(task_id, "task_plan_replanned", payload)
    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Plano atualizado",
            "detail": f"Replanejado: {reason}. {len(steps)} novas etapas.",
        },
    )
    return steps
