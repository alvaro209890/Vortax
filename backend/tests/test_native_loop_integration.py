"""Integração do loop nativo com tools mockadas (sem API) + smoke com DeepSeek se houver chave."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from tests.live_helpers import apply_key_to_settings, live_enabled


class NativeLoopMockTests(unittest.TestCase):
    def test_loop_delivers_when_model_returns_content(self):
        from agent import loop as loop_mod
        from services.event_bus import EventBus
        from services.task_store import TaskStore

        bus = EventBus()
        store = TaskStore()
        # create task in store/db may need mock
        task_id = "native-mock-1"

        async def fake_turn(messages, **kwargs):
            # first call: finish with content
            return {
                "content": "Entrega final de teste.",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"total_tokens": 10},
                "model": "deepseek-v4-pro",
                "raw_message": {"role": "assistant", "content": "Entrega final de teste."},
            }

        async def _run():
            with mock.patch.object(loop_mod, "deepseek_configured", return_value=True), mock.patch.object(
                loop_mod, "request_agent_turn", side_effect=fake_turn
            ), mock.patch.object(loop_mod, "task_plan_store") as plan, mock.patch.object(
                loop_mod, "database"
            ) as db, mock.patch.object(loop_mod, "evaluate_delivery_gates", return_value=[]), mock.patch.object(
                loop_mod, "first_blocking_gate", return_value=None
            ), mock.patch.object(loop_mod, "publish_agent_activity", new=mock.AsyncMock()):
                plan.list_steps.return_value = []
                plan.replace_plan.return_value = [{"id": "s1", "status": "pending"}]
                plan.complete_step_by_id.return_value = {}
                db.list_sources.return_value = []
                db.list_generated_files.return_value = []
                store.get = mock.Mock(return_value={"id": task_id, "user_id": "u1"})  # type: ignore
                store.update_status = mock.Mock(return_value=None)  # type: ignore
                store.is_paused = mock.Mock(return_value=False)  # type: ignore
                store.is_stopped = mock.Mock(return_value=False)  # type: ignore
                events = []

                async def capture(tid, etype, payload=None):
                    events.append((etype, payload))

                bus.publish = capture  # type: ignore
                await loop_mod.run_native_agent_loop(task_id, "diga oi", store, bus)
                return events

        events = asyncio.run(_run())
        types = [e[0] for e in events]
        self.assertIn("assistant_message_done", types)
        done = [p for t, p in events if t == "assistant_message_done"][0]
        self.assertIn("Entrega", done.get("content") or "")


@unittest.skipUnless(live_enabled(), "sem DEEPSEEK_API_KEY")
class NativeLoopLiveSmoke(unittest.TestCase):
    def test_agent_turn_with_real_registry_tools_schema(self):
        """Garante que o schema de 39 tools é aceito pela API (sem executar tools)."""
        key = apply_key_to_settings()
        self.assertTrue(key)
        import services.deepseek_client as ds
        from agent.tools.registry import openai_tools_payload

        ds.settings.DEEPSEEK_API_KEY = key
        ds.settings.DEEPSEEK_STREAMING = False
        ds.settings.DEEPSEEK_MODEL_BRAIN = "deepseek-v4-pro"
        ds.settings.DEEPSEEK_MAX_OUTPUT_TOKENS = 512

        tools = openai_tools_payload()
        self.assertGreaterEqual(len(tools), 30)

        async def _run():
            return await ds.request_agent_turn(
                [
                    {
                        "role": "system",
                        "content": "You are a test agent. Prefer calling web_fetch if useful.",
                    },
                    {
                        "role": "user",
                        "content": "Call web_fetch with url https://example.com . Only use that tool.",
                    },
                ],
                tools=tools,
                stream=False,
                purpose="brain",
            )

        out = asyncio.run(_run())
        calls = out.get("tool_calls") or []
        # Accept either tool call or textual refusal/answer — but API must succeed
        self.assertIn(out.get("finish_reason"), {"tool_calls", "stop", "length", ""})
        if calls:
            names = {c["name"] for c in calls}
            # model should pick something from registry
            self.assertTrue(names)


if __name__ == "__main__":
    unittest.main()
