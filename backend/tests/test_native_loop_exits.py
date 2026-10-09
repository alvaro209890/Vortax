"""Saídas do loop nativo: resposta rápida, teto de recusas do portão e orçamento de tempo.

Regressões de 09/10/2026: com o Gemini, o portão de fontes recusava a entrega e o modelo
reescrevia a mesma resposta até o limite de iterações (mais de 4 min sem terminar), e até
"oi" passava pelo loop completo com plano, ferramentas e portões.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock


def _turn(content: str = "", tool_calls: list | None = None) -> dict:
    return {
        "content": content,
        "tool_calls": tool_calls or [],
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "usage": {"total_tokens": 10},
        "model": "test",
        "raw_message": None,
    }


def run_loop(
    prompt: str,
    turns,
    *,
    gate_blocks: bool = False,
    budget: float | None = None,
    streaming: bool = False,
):
    """Roda o loop com modelo, banco, plano e portões falsos. Devolve (eventos, chamadas)."""
    from agent import loop as loop_mod
    from agent.gates import GateResult
    from services.event_bus import EventBus
    from services.task_store import TaskStore

    task_id = "native-exit-test"
    calls: list[dict] = []
    turn_iter = iter(turns)

    async def fake_turn(messages, **kwargs):
        calls.append({"messages": list(messages), **kwargs})
        return next(turn_iter)

    async def fake_tool(name, args, **kwargs):
        return {"success": True, "data": {"success": True, "ok": name}}

    blocked = GateResult(ok=False, code="research_sources", instruction="faltam fontes")
    events: list[tuple[str, dict]] = []

    async def capture(tid, etype, payload=None):
        events.append((etype, payload or {}))

    async def _run():
        bus = EventBus()
        bus.publish = capture  # type: ignore[assignment]
        bus.history = mock.Mock(return_value=[])  # type: ignore[assignment]
        store = TaskStore()
        store.get = mock.Mock(return_value={"id": task_id, "user_id": "u1"})  # type: ignore[assignment]
        store.update_status = mock.Mock(return_value=None)  # type: ignore[assignment]
        store.is_paused = mock.Mock(return_value=False)  # type: ignore[assignment]
        store.is_stopped = mock.Mock(return_value=False)  # type: ignore[assignment]
        history = [{"role": "user", "content": prompt}]
        patches = [
            mock.patch.object(loop_mod, "deepseek_configured", return_value=True),
            mock.patch.object(loop_mod, "request_agent_turn", side_effect=fake_turn),
            mock.patch.object(loop_mod, "execute_tool", side_effect=fake_tool),
            mock.patch.object(loop_mod, "task_plan_store"),
            mock.patch.object(loop_mod, "database"),
            mock.patch.object(loop_mod, "publish_agent_activity", new=mock.AsyncMock()),
            mock.patch.object(
                loop_mod,
                "prepare_context_history",
                new=mock.AsyncMock(return_value=(history, {"status": "ok", "percent": 1}, False)),
            ),
            mock.patch.object(loop_mod, "evaluate_delivery_gates", return_value=[blocked] if gate_blocks else []),
            # Native software now shares the finalizer; keep this loop fixture isolated from persistence.
            mock.patch("services.agent_runner.prepare_context_history", new=mock.AsyncMock(return_value=(history, {}, False))),
            mock.patch("services.agent_runner._save_task_title", new=mock.AsyncMock()),
        ]
        patches.append(mock.patch.object(loop_mod.settings, "DEEPSEEK_STREAMING", streaming))
        if budget is not None:
            patches.append(mock.patch.object(loop_mod.settings, "AGENT_TIME_BUDGET_SECONDS", budget))
        for patcher in patches:
            started = patcher.start()
            if patcher.attribute == "task_plan_store":
                started.list_steps.return_value = []
                started.replace_plan.return_value = []
            if patcher.attribute == "database":
                started.list_sources.return_value = []
                started.list_generated_files.return_value = []
        try:
            await loop_mod.run_native_agent_loop(task_id, prompt, store, bus)
        finally:
            for patcher in reversed(patches):
                patcher.stop()

    asyncio.run(_run())
    return events, calls


def _done(events):
    return [payload for etype, payload in events if etype == "assistant_message_done"]


class FastPathTests(unittest.TestCase):
    def test_simple_message_skips_agent_loop(self):
        from agent import loop as loop_mod

        with mock.patch(
            "services.agent_runner._answer_simple_prompt", new=mock.AsyncMock()
        ) as simple, mock.patch("services.agent_runner._answer_exact_prompt", new=mock.AsyncMock()):
            events, calls = run_loop("oi", [])
        self.assertEqual(calls, [], "conversa simples não deve chamar o loop com ferramentas")
        simple.assert_awaited_once()
        self.assertIn("context_status", [etype for etype, _ in events])
        self.assertTrue(loop_mod.should_answer_directly("oi"))

    def test_research_prompt_goes_to_loop(self):
        events, calls = run_loop(
            "Pesquise a cotação do dólar hoje e cite a fonte",
            [_turn("Dólar a R$ 4,99 (fonte: exemplo).")],
        )
        self.assertEqual(len(calls), 1)
        self.assertIn("4,99", _done(events)[0]["content"])


class GateCapTests(unittest.TestCase):
    PROMPT = "Pesquise a cotação do dólar hoje e cite a fonte"

    def test_rewrite_without_tools_is_rejected_once(self):
        answer = _turn("Dólar a R$ 4,99.")
        events, calls = run_loop(self.PROMPT, [answer, answer, answer, answer], gate_blocks=True, streaming=True)
        self.assertEqual(len(calls), 2, "sem ferramenta entre as tentativas, a 2ª entrega passa")
        self.assertEqual(len(_done(events)), 1)
        # a 1ª resposta (recusada) já tinha saído em delta: o front precisa descartá-la
        discards = [p for t, p in events if t == "assistant_message_discard"]
        self.assertEqual([d["reason"] for d in discards], ["gate"])

    def test_rejections_capped_even_with_tool_use(self):
        answer = _turn("Dólar a R$ 4,99.")
        search = _turn("", [{"id": "c1", "name": "web_search", "arguments": {"query": "dolar"}}])
        search2 = _turn("", [{"id": "c2", "name": "web_search", "arguments": {"query": "dolar hoje"}}])
        turns = [answer, search, answer, search2, answer, answer]
        events, calls = run_loop(self.PROMPT, turns, gate_blocks=True)
        # recusa 1 -> pesquisa -> recusa 2 -> pesquisa -> 3ª entrega passa (teto = 2)
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(_done(events)), 1)


class TimeBudgetTests(unittest.TestCase):
    def test_parallel_batch_cannot_exceed_two_searches(self):
        searches = _turn("", [{"id": f"s{i}", "name": "web_search", "arguments": {"query": f"IA {i}"}} for i in range(3)])
        _, calls = run_loop("Pesquise notícias recentes de IA", [searches, _turn("Síntese.")])
        results = [m["content"] for m in calls[1]["messages"] if m["role"] == "tool"]
        self.assertEqual(sum('"ok": "web_search"' in r for r in results), 2)
        self.assertEqual(sum("não repita buscas" in r for r in results), 1)

    def test_exact_urls_do_not_bypass_research_tools(self):
        with mock.patch("services.agent_runner._answer_exact_prompt", new=mock.AsyncMock()) as exact:
            _, calls = run_loop("Pesquise 3 notícias recentes com URLs exatas", [_turn("Síntese.")])
        exact.assert_not_awaited()
        self.assertEqual(calls[0]["purpose"], "fast")
        self.assertIn("web_search", {t["function"]["name"] for t in calls[0]["tools"]})

    def test_exhausted_budget_forces_answer_without_tools(self):
        search = _turn("", [{"id": "c1", "name": "web_search", "arguments": {"query": "dolar"}}])
        events, calls = run_loop(
            "Pesquise a cotação do dólar hoje e cite a fonte",
            [search, _turn("Entrega parcial.")],
            budget=-1,
        )
        self.assertIsNone(calls[0]["tools"], "orçamento esgotado: rodada sem ferramentas")
        self.assertTrue(any("[GATE:finish]" in str(m.get("content")) for m in calls[0]["messages"]))
        self.assertIn("limite de tempo", _done(events)[0]["content"])
        self.assertEqual(len(calls), 1, "provider tool calls after budget must not execute")

    def test_research_uses_fast_model_and_restricted_tools(self):
        _, calls = run_loop("Pesquise notícias recentes de IA", [_turn("Síntese com fontes.")])
        self.assertEqual(calls[0]["purpose"], "fast")
        names = {t["function"]["name"] for t in calls[0]["tools"]}
        self.assertIn("web_fetch", names)
        self.assertNotIn("shell_run", names)

    def test_software_keeps_brain_and_shell(self):
        _, calls = run_loop("Pesquise referências e crie um site", [_turn("Entrega.")])
        self.assertEqual(calls[0]["purpose"], "brain")
        self.assertIn("shell_run", {t["function"]["name"] for t in calls[0]["tools"]})


if __name__ == "__main__":
    unittest.main()
