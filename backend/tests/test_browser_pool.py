import tempfile
import unittest
from pathlib import Path

from tools.browser_pool import BrowserPool, BrowserPoolError


class FakeBrowserTool:
    def __init__(self, cdp_port: int, profile_dir: Path) -> None:
        self.cdp_port = cdp_port
        self.profile_dir = profile_dir
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class BrowserPoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_root = Path(self.tmp.name)
        self.pool = BrowserPool(
            max_instances=2,
            port_start=9300,
            port_end=9302,
            profile_root=self.profile_root,
            tool_factory=FakeBrowserTool,  # type: ignore[arg-type]
        )
        await self.pool.initialize()

    async def asyncTearDown(self) -> None:
        await self.pool.shutdown()
        self.tmp.cleanup()

    async def test_same_task_reuses_same_instance(self) -> None:
        first = await self.pool.acquire("task-a")
        second = await self.pool.acquire("task-a")

        self.assertIs(first, second)
        self.assertEqual(first.cdp_port, 9300)

    async def test_different_tasks_get_different_ports_and_profiles(self) -> None:
        first = await self.pool.acquire("task-a")
        second = await self.pool.acquire("task-b")

        self.assertNotEqual(first.cdp_port, second.cdp_port)
        self.assertNotEqual(first.profile_dir, second.profile_dir)
        self.assertTrue(first.profile_dir.exists())
        self.assertTrue(second.profile_dir.exists())

    async def test_release_closes_browser_removes_profile_and_reuses_port(self) -> None:
        first = await self.pool.acquire("task-a")
        marker = first.profile_dir / "marker"
        marker.write_text("cache", encoding="utf-8")

        released = await self.pool.release("task-a")
        second = await self.pool.acquire("task-b")

        self.assertTrue(released)
        self.assertTrue(first.closed)
        self.assertFalse(first.profile_dir.exists())
        self.assertEqual(second.cdp_port, first.cdp_port)

    async def test_release_without_instance_is_idempotent(self) -> None:
        self.assertFalse(await self.pool.release("missing-task"))

    async def test_max_instances_timeout(self) -> None:
        await self.pool.release("task-a")
        limited = BrowserPool(
            max_instances=1,
            port_start=9400,
            port_end=9401,
            profile_root=self.profile_root / "limited",
            tool_factory=FakeBrowserTool,  # type: ignore[arg-type]
        )
        await limited.initialize()
        try:
            await limited.acquire("task-a")
            with self.assertRaises(BrowserPoolError):
                await limited.acquire("task-b", timeout=0.01)
        finally:
            await limited.shutdown()


if __name__ == "__main__":
    unittest.main()
