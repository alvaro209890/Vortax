"""Contratos opcionais usados pela interface para acompanhar cada ferramenta."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import services.event_bus as event_bus_module
import tools.tool_executor as tool_executor
from services.event_bus import EventBus
from services.stream_contract import KNOWN_EVENT_TYPES
from services.tool_context import DERIVED_EVENT_TYPES, current_call_id
from tools import files as file_tools


class FakeDatabase:
    def __init__(self) -> None:
        self.next_id = 0

    def insert_event(self, *_args) -> int:
        self.next_id += 1
        return self.next_id

    def get_task(self, _task_id):
        return {"user_id": "local-dev-user"}

    def list_sources(self, _task_id):
        return []


class RecordingBus(EventBus):
    """EventBus real (com a injeção de call_id), sem SQLite nem sockets."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

    async def publish(self, task_id, event_type, payload=None):
        event = await super().publish(task_id, event_type, payload)
        self.events.append(event)
        return event


class EventBusCorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_patch = mock.patch.object(event_bus_module, "database", FakeDatabase())
        self.db_patch.start()
        self.bus = RecordingBus()

    async def asyncTearDown(self) -> None:
        self.db_patch.stop()

    async def test_derived_events_inherit_call_id_without_overwriting(self) -> None:
        token = current_call_id.set("tc_a")
        try:
            await self.bus.publish("t", "shell_stdout", {"line": "ok"})
            await self.bus.publish("t", "screen_frame", {"call_id": "tc_explicit"})
            await self.bus.publish("t", "assistant_message_delta", {"delta": "x"})
        finally:
            current_call_id.reset(token)
        await self.bus.publish("t", "shell_stdout", {"line": "fora de ferramenta"})
        stdout, frame, delta, outside = self.bus.events
        self.assertEqual(stdout["payload"]["call_id"], "tc_a")
        self.assertEqual(frame["payload"]["call_id"], "tc_explicit")
        self.assertNotIn("call_id", delta["payload"])
        self.assertNotIn("call_id", outside["payload"])

    async def test_parallel_calls_do_not_mix_ids(self) -> None:
        async def tool(call_id: str, lines: int) -> None:
            token = current_call_id.set(call_id)
            try:
                for index in range(lines):
                    await self.bus.publish("t", "shell_stdout", {"line": f"{call_id}-{index}"})
                    await asyncio.sleep(0)
            finally:
                current_call_id.reset(token)

        await asyncio.gather(tool("tc_1", 4), tool("tc_2", 4))
        for event in self.bus.events:
            self.assertTrue(event["payload"]["line"].startswith(event["payload"]["call_id"]))

    def test_derived_types_are_known_stream_types(self) -> None:
        self.assertTrue(DERIVED_EVENT_TYPES <= KNOWN_EVENT_TYPES)


class ExecuteToolCorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        workspace = Path(self.tmp.name)
        (workspace / "task-1").mkdir()
        fake_db = FakeDatabase()
        self.patches = [
            mock.patch.object(event_bus_module, "database", fake_db),
            mock.patch.object(tool_executor, "database", fake_db),
            mock.patch.object(file_tools.settings, "WORKSPACE_PATH", workspace),
            mock.patch.object(file_tools, "sync_task_workspace_files", return_value={"files": [], "projects": []}),
            mock.patch.object(file_tools, "annotate_workspace_files", return_value=0),
            mock.patch.object(tool_executor, "_project_dir", return_value=workspace / "task-1"),
            mock.patch.object(tool_executor, "sync_task_workspace_files", return_value={"files": [{"path": "a.txt"}], "projects": []}),
        ]
        for patch in self.patches:
            patch.start()
        self.bus = RecordingBus()

    async def asyncTearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    async def test_call_result_and_files_share_one_id(self) -> None:
        await tool_executor.execute_tool("file_write", {"path": "a.txt", "content": "um\ndois\n"}, task_id="task-1", bus=self.bus)
        by_type = {event["type"]: event for event in self.bus.events}
        call_id = by_type["tool_call"]["payload"]["call_id"]
        self.assertTrue(call_id.startswith("tc_"))
        self.assertEqual(by_type["tool_result"]["payload"]["call_id"], call_id)
        self.assertEqual(by_type["files_created"]["payload"]["call_id"], call_id)
        result = by_type["tool_result"]["payload"]["result"]
        self.assertTrue(result["created"])
        self.assertEqual(result["line_count"], 2)
        self.assertIsNone(current_call_id.get())

    async def test_exception_still_closes_the_call(self) -> None:
        async def broken(**_kwargs):
            raise RuntimeError("falhou de verdade")

        with mock.patch.dict(tool_executor.TOOLS, {"exact_solve": broken}):
            outcome = await tool_executor.execute_tool("exact_solve", {"problem": "1+1"}, task_id="task-1", bus=self.bus, call_id="tc_fixed")
        self.assertFalse(outcome["success"])
        results = [event for event in self.bus.events if event["type"] == "tool_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["payload"]["call_id"], "tc_fixed")
        self.assertFalse(results[0]["payload"]["result"]["success"])
        errors = [event for event in self.bus.events if event["type"] == "error"]
        self.assertEqual(errors[0]["payload"]["call_id"], "tc_fixed")

    async def test_unknown_tool_closes_the_call(self) -> None:
        await tool_executor.execute_tool("nao_existe", {}, task_id="task-1", bus=self.bus)
        types = [event["type"] for event in self.bus.events]
        self.assertEqual(types, ["tool_call", "error", "tool_result"])


class BrowserFrameDedupeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_patch = mock.patch.object(event_bus_module, "database", FakeDatabase())
        self.db_patch.start()
        self.bus = RecordingBus()
        tool_executor._LAST_FRAME_SIGNATURE.clear()

    async def asyncTearDown(self) -> None:
        self.db_patch.stop()

    async def test_identical_frame_is_not_resent(self) -> None:
        frame = {"image_base64": "AAAA", "url": "https://a.test", "title": "A", "cursor": None, "viewport": {"width": 10, "height": 10}}
        self.assertTrue(await tool_executor._publish_browser_frame("t", frame, self.bus, trigger="browser_navigate"))
        self.assertFalse(await tool_executor._publish_browser_frame("t", dict(frame), self.bus, trigger="browser_navigate"))
        moved = {**frame, "cursor": {"x": 1, "y": 2, "action": "click"}}
        self.assertTrue(await tool_executor._publish_browser_frame("t", moved, self.bus, trigger="browser_click_text"))
        published = [event for event in self.bus.events if event["type"] == "screen_frame"]
        self.assertEqual(len(published), 2)
        self.assertEqual(published[1]["payload"]["trigger"], "browser_click_text")
        self.assertIn("captured_at", published[1]["payload"])

    async def test_frame_after_block_is_always_sent(self) -> None:
        frame = {"image_base64": "BBBB", "url": "https://a.test", "cursor": None}
        await tool_executor._publish_browser_frame("t", frame, self.bus, trigger="browser_navigate")
        blocked = {"blocked": True, "blocked_reason": "sensitive_input", "url": "https://a.test/login", "image_base64": "SECRET"}
        await tool_executor._publish_browser_frame("t", blocked, self.bus, trigger="browser_click_text")
        self.assertTrue(await tool_executor._publish_browser_frame("t", dict(frame), self.bus, trigger="browser_go_back"))
        types = [event["type"] for event in self.bus.events]
        self.assertEqual(types, ["screen_frame", "screen_frame_blocked", "screen_frame"])
        self.assertNotIn("image_base64", self.bus.events[1]["payload"])


class FileToolLineMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        workspace = Path(self.tmp.name)
        (workspace / "t").mkdir()
        self.patches = [
            mock.patch.object(file_tools.settings, "WORKSPACE_PATH", workspace),
            mock.patch.object(file_tools, "sync_task_workspace_files", return_value={"files": [], "projects": []}),
            mock.patch.object(file_tools, "annotate_workspace_files", return_value=0),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def test_write_reports_creation_then_overwrite(self) -> None:
        first = file_tools.file_write("t", "a.py", "a = 1\nb = 2\nc = 3")
        second = file_tools.file_write("t", "a.py", "a = 1\n")
        self.assertTrue(first["created"])
        self.assertEqual(first["line_count"], 3)
        self.assertFalse(second["created"])
        self.assertEqual(second["line_count"], 1)

    def test_edit_reports_real_lines(self) -> None:
        file_tools.file_write("t", "a.py", "um\ndois\ntres\nquatro\n")
        file_tools.file_read("t", "a.py")
        result = file_tools.file_edit("t", "a.py", "tres\n", "TRES\nTRES-B\n")
        self.assertEqual((result["start_line"], result["end_line"]), (3, 4))
        self.assertEqual(result["line_count"], 5)


if __name__ == "__main__":
    unittest.main()
