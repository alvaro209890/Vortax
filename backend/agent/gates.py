"""Gates de entrega — padrão [GATE:*] (plano-melhoria-ia §02)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from database import database
from services.research_policy import cross_check_status


@dataclass
class GateResult:
    ok: bool
    code: str
    instruction: str = ""
    blocked: bool = False

    def as_system_message(self) -> str:
        prefix = f"[GATE:{self.code}]"
        if self.ok:
            return f"{prefix} ok"
        if self.blocked:
            return f"{prefix} BLOQUEADO: {self.instruction}"
        return f"{prefix} {self.instruction}"


class DeliveryGate(Protocol):
    def check(self, ctx: dict[str, Any]) -> GateResult: ...


class ResearchSourcesGate:
    """Exige fontes mínimas para perguntas sensíveis/atualizadas."""

    def check(self, ctx: dict[str, Any]) -> GateResult:
        prompt = str(ctx.get("user_prompt") or ctx.get("description") or "")
        task_id = str(ctx.get("task_id") or "")
        sources = database.list_sources(task_id) if task_id else []
        status = cross_check_status(prompt, sources)
        if status.get("satisfied"):
            return GateResult(ok=True, code="research_sources")
        required = int(status.get("required_sources") or 0)
        found = int(status.get("source_count") or 0)
        if required <= 0:
            return GateResult(ok=True, code="research_sources")
        return GateResult(
            ok=False,
            code="research_sources",
            instruction=(
                f"Ainda precisa de {required} fonte(s) relevante(s); há {found}. "
                "Pesquise e extraia artigos antes de finalizar."
            ),
        )


class CycleGuardGate:
    """Bloqueia se o modelo tentou finalizar sem progresso após muitos loops."""

    def check(self, ctx: dict[str, Any]) -> GateResult:
        if ctx.get("force_finish"):
            return GateResult(ok=True, code="cycle")
        stagnant = int(ctx.get("stagnant_iterations") or 0)
        if stagnant >= 8:
            return GateResult(
                ok=False,
                code="cycle",
                instruction=(
                    "8 iterações sem progresso observável (arquivo/fonte/todo). "
                    "Mude de estratégia ou entregue o melhor resultado parcial com limitações."
                ),
                blocked=False,
            )
        return GateResult(ok=True, code="cycle")


DEFAULT_GATES: list[DeliveryGate] = [
    ResearchSourcesGate(),
    CycleGuardGate(),
]


def evaluate_delivery_gates(ctx: dict[str, Any], gates: list[DeliveryGate] | None = None) -> list[GateResult]:
    results: list[GateResult] = []
    for gate in gates or DEFAULT_GATES:
        try:
            results.append(gate.check(ctx))
        except Exception as exc:  # noqa: BLE001
            results.append(
                GateResult(
                    ok=False,
                    code="gate_error",
                    instruction=f"Falha ao avaliar gate: {exc}",
                    blocked=True,
                )
            )
    return results


def first_blocking_gate(results: list[GateResult]) -> GateResult | None:
    for item in results:
        if not item.ok:
            return item
    return None
