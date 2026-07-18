"""Testes LIVE contra api.deepseek.com usando a chave do Hermes (ou env).

Pula automaticamente se não houver chave.
Nunca imprime a chave.
"""

from __future__ import annotations

import asyncio
import os
import unittest

from tests.live_helpers import apply_key_to_settings, live_enabled


@unittest.skipUnless(live_enabled(), "sem DEEPSEEK_API_KEY (hermes/.env ou env)")
class DeepSeekLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = apply_key_to_settings()
        assert key and len(key) > 10
        # garantir settings do módulo deepseek
        import services.deepseek_client as ds

        ds.settings.DEEPSEEK_API_KEY = key
        ds.settings.DEEPSEEK_STREAMING = False
        ds.settings.DEEPSEEK_MODEL_BRAIN = "deepseek-v4-pro"
        ds.settings.DEEPSEEK_MODEL_FAST = "deepseek-v4-flash"
        ds.settings.DEEPSEEK_MODEL = "deepseek-v4-pro"
        ds.settings.DEEPSEEK_MAX_OUTPUT_TOKENS = 1024
        cls.ds = ds

    def test_flash_simple_completion(self):
        async def _run():
            return await self.ds.request_agent_turn(
                [{"role": "user", "content": "Reply with exactly: pong"}],
                tools=None,
                stream=False,
                purpose="fast",
            )

        # force flash via purpose + pick_model
        out = asyncio.run(_run())
        # purpose fast uses flash; content may be short
        content = (out.get("content") or "").lower()
        self.assertTrue(content or out.get("tool_calls") is not None)
        self.assertIn("usage", out)
        self.assertGreater(int((out.get("usage") or {}).get("total_tokens") or 0), 0)

    def test_pro_function_calling_echo(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "echo",
                    "description": "Echo text back",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            }
        ]

        async def _run():
            return await self.ds.request_agent_turn(
                [
                    {
                        "role": "user",
                        "content": "Call the echo tool with text set to hello_vortax. Do not answer in plain text.",
                    }
                ],
                tools=tools,
                stream=False,
                purpose="brain",
            )

        out = asyncio.run(_run())
        calls = out.get("tool_calls") or []
        # Pro should prefer tool_calls when instructed
        self.assertTrue(
            calls or (out.get("content") and "hello" in (out.get("content") or "").lower()),
            msg=f"expected tool_calls or content, got finish={out.get('finish_reason')} content_len={len(out.get('content') or '')}",
        )
        if calls:
            self.assertEqual(calls[0]["name"], "echo")
            args = calls[0].get("arguments") or {}
            # text may be under different keys if model free-forms
            blob = str(args).lower()
            self.assertIn("hello", blob)

    def test_generate_task_title_live(self):
        async def _run():
            return await self.ds.generate_task_title(
                "Crie um site de portfolio com React e tres paginas"
            )

        title = asyncio.run(_run())
        self.assertIsInstance(title, str)
        self.assertGreater(len(title.strip()), 2)
        self.assertLess(len(title), 120)

    def test_pick_model_layers(self):
        self.assertEqual(self.ds.pick_model("brain"), "deepseek-v4-pro")
        self.assertEqual(self.ds.pick_model("title"), "deepseek-v4-flash")
        self.assertEqual(self.ds.pick_model("fast"), "deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()
