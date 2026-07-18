"""Live web_fetch (sem chave; rede pública)."""

from __future__ import annotations

import asyncio
import unittest

from tools.web_fetch import web_fetch


class WebFetchLiveTests(unittest.TestCase):
    def test_fetch_example_com(self):
        async def _run():
            return await web_fetch("https://example.com", task_id=None, save_source=False, max_chars=3000)

        out = asyncio.run(_run())
        self.assertTrue(out.get("success"), msg=str(out.get("error")))
        self.assertIn("example", (out.get("text") or "").lower() + (out.get("title") or "").lower())
        self.assertEqual(out.get("status_code"), 200)

    def test_ssrf_localhost_blocked(self):
        async def _run():
            return await web_fetch("http://127.0.0.1:8010/health", save_source=False)

        out = asyncio.run(_run())
        self.assertFalse(out.get("success"))


if __name__ == "__main__":
    unittest.main()
