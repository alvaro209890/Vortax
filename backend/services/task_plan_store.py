from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from database import database


VALID_STEP_STATUSES = {"pending", "running", "passed", "failed", "skipped"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_tool_hint(label: str, detail: str = "") -> str:
    text = f"{label} {detail}".lower()
    if any(word in text for word in ("pesquis", "fonte", "referencia", "referência")):
        return "research"
    if any(word in text for word in ("valid", "revis", "test", "bug", "corrig")):
        return "validate"
    if any(word in text for word in ("entreg", "final", "resposta", "download")):
        return "deliver"
    if any(word in text for word in ("vertex", "openclaude", "criar", "gerar", "execut", "implementar", "codigo", "código", "site")):
        return "execute"
    return "understand"


def fallback_steps(description: str) -> list[dict[str, Any]]:
    detail = description.strip()[:180]
    return [
        {
            "label": "Entender pedido",
            "detail": detail or "Analisar objetivo e contexto da conversa.",
            "tool_hint": "understand",
            "acceptance_criteria": ["Objetivo principal identificado."],
        },
        {
            "label": "Executar trabalho",
            "detail": "Usar as ferramentas certas para pesquisar, criar ou resolver a tarefa.",
            "tool_hint": "execute",
            "acceptance_criteria": ["Acoes principais executadas sem bloquear a conversa."],
        },
        {
            "label": "Validar entrega",
            "detail": "Conferir resultados, arquivos, fontes ou projeto antes de finalizar.",
            "tool_hint": "validate",
            "acceptance_criteria": ["Resultado revisado e problemas importantes registrados."],
        },
        {
            "label": "Entregar resposta",
            "detail": "Responder com o resumo final e disponibilizar artefatos quando existirem.",
            "tool_hint": "deliver",
            "acceptance_criteria": ["Usuario recebe uma conclusao clara da tarefa."],
        },
    ]


def direct_response_steps(description: str) -> list[dict[str, Any]]:
    detail = description.strip()[:180]
    return [
        {
            "label": "Responder mensagem",
            "detail": detail or "Responder de forma direta.",
            "tool_hint": "deliver",
            "acceptance_criteria": ["Resposta direta enviada."],
        }
    ]


class TaskPlanStore:
    def normalize_steps(self, raw_steps: list[dict[str, Any]], description: str) -> list[dict[str, Any]]:
        source_steps = raw_steps if raw_steps else fallback_steps(description)
        now = utc_now()
        normalized: list[dict[str, Any]] = []
        for index, step in enumerate(source_steps[:8], start=1):
            label = str(step.get("label") or f"Etapa {index}").strip()[:80]
            detail = str(step.get("detail") or "").strip()[:500]
            criteria = step.get("acceptance_criteria")
            if not isinstance(criteria, list) or not criteria:
                criteria = [detail or f"{label} concluida."]
            tool_hint = str(step.get("tool_hint") or _infer_tool_hint(label, detail)).strip() or "understand"
            normalized.append(
                {
                    "id": str(uuid4()),
                    "position": index,
                    "label": label,
                    "detail": detail,
                    "status": "pending",
                    "tool_hint": tool_hint,
                    "acceptance_criteria": [str(item).strip()[:220] for item in criteria[:5] if str(item).strip()],
                    "evidence": [],
                    "started_at": None,
                    "finished_at": None,
                    "updated_at": now,
                }
            )
        return normalized or self.normalize_steps(fallback_steps(description), description)

    def replace_plan(self, task_id: str, steps: list[dict[str, Any]], description: str) -> list[dict[str, Any]]:
        return database.replace_task_steps(task_id, self.normalize_steps(steps, description))

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        return database.list_task_steps(task_id)

    def current_step(self, task_id: str) -> dict[str, Any] | None:
        steps = self.list_steps(task_id)
        for step in steps:
            if step.get("status") == "running":
                return step
        for step in steps:
            if step.get("status") == "pending":
                return step
        return steps[-1] if steps else None

    def first_pending(self, task_id: str) -> dict[str, Any] | None:
        for step in self.list_steps(task_id):
            if step.get("status") == "pending":
                return step
        return None

    def find_for_hint(self, task_id: str, hint: str) -> dict[str, Any] | None:
        steps = self.list_steps(task_id)
        for step in steps:
            if step.get("status") == "running" and step.get("tool_hint") == hint:
                return step
        for step in steps:
            if step.get("status") == "pending" and step.get("tool_hint") == hint:
                return step
        if hint == "validate":
            for step in steps:
                if step.get("status") in {"pending", "running"} and step.get("tool_hint") in {"execute", "validate"}:
                    return step
        return None

    def start_step(self, task_id: str, *, hint: str | None = None) -> dict[str, Any] | None:
        step = self.find_for_hint(task_id, hint) if hint else self.first_pending(task_id)
        if not step:
            return None
        now = utc_now()
        updates = {"status": "running", "started_at": step.get("started_at") or now, "updated_at": now}
        return database.update_task_step(step["id"], updates)

    def complete_step(
        self,
        task_id: str,
        *,
        hint: str | None = None,
        status: str = "passed",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        final_status = status if status in VALID_STEP_STATUSES else "passed"
        step = self.find_for_hint(task_id, hint) if hint else self.current_step(task_id)
        if not step:
            return None
        evidences = list(step.get("evidence") or [])
        if evidence:
            evidences.append(evidence)
        now = utc_now()
        return database.update_task_step(
            step["id"],
            {
                "status": final_status,
                "evidence": evidences[-12:],
                "finished_at": now if final_status in {"passed", "failed", "skipped"} else step.get("finished_at"),
                "updated_at": now,
            },
        )

    def complete_step_by_id(
        self,
        step_id: str,
        *,
        status: str = "passed",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        final_status = status if status in VALID_STEP_STATUSES else "passed"
        step = database.get_task_step(step_id)
        if not step:
            return None
        evidences = list(step.get("evidence") or [])
        if evidence:
            evidences.append(evidence)
        now = utc_now()
        return database.update_task_step(
            step_id,
            {
                "status": final_status,
                "evidence": evidences[-12:],
                "started_at": step.get("started_at") or now,
                "finished_at": now if final_status in {"passed", "failed", "skipped"} else step.get("finished_at"),
                "updated_at": now,
            },
        )

    def append_evidence(self, task_id: str, evidence: dict[str, Any], *, hint: str | None = None) -> dict[str, Any] | None:
        step = self.find_for_hint(task_id, hint) if hint else self.current_step(task_id)
        if not step:
            return None
        evidences = list(step.get("evidence") or [])
        evidences.append(evidence)
        return database.update_task_step(step["id"], {"evidence": evidences[-12:], "updated_at": utc_now()})


task_plan_store = TaskPlanStore()
