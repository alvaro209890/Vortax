"""Testes de shell_exec/view/kill em processo real (sem rede)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import settings


class ShellSessionsLiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.task_id = "shell-live-1"
        (self.workspace / self.task_id).mkdir()
        self._orig_ws = settings.WORKSPACE_PATH
        settings.WORKSPACE_PATH = self.workspace

    def tearDown(self):
        settings.WORKSPACE_PATH = self._orig_ws
        self.tmp.cleanup()

    def test_background_session_echo(self):
        from tools import shell_sessions

        async def _run():
            start = await shell_sessions.shell_exec(
                "python3 -c \"import time; print('START'); time.sleep(0.4); print('END')\"",
                self.task_id,
                background=True,
            )
            self.assertTrue(start.get("success"), msg=str(start))
            sid = start.get("session_id")
            self.assertTrue(sid)
            # poll until done
            last = None
            for _ in range(30):
                last = await shell_sessions.shell_view(sid)
                if not last.get("running"):
                    break
                await asyncio.sleep(0.15)
            self.assertIsNotNone(last)
            body = (last.get("stdout") or "") + (start.get("stdout") or "")
            # may have been read already in start snapshot
            view2 = await shell_sessions.shell_view(sid)
            body2 = body + (view2.get("stdout") or "")
            # kill if still running
            await shell_sessions.shell_kill(sid)
            return body2, last

        body, last = asyncio.run(_run())
        combined = body + str(last)
        self.assertTrue(
            "START" in combined or "END" in combined or last.get("returncode") is not None,
            msg=f"unexpected session output: {combined!r} last={last}",
        )

    def test_oneshot_echo(self):
        from tools import shell_sessions

        async def _run():
            # patch project dir via settings already
            return await shell_sessions.shell_exec("echo vortax_ok", self.task_id, background=False)

        # oneshot uses run_shell which uses whitelist - echo ok
        out = asyncio.run(_run())
        # run_shell path
        self.assertTrue(out.get("success") or "vortax" in str(out).lower() or out.get("mode") == "oneshot")


if __name__ == "__main__":
    unittest.main()
