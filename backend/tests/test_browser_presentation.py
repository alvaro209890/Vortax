import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from services.browser_presentation import browser_reading_view
from tools import tool_executor


class PresentationTests(unittest.TestCase):
    def test_http_and_cache_search_have_real_results(self):
        result = {"query": "IA", "engine": "brave_http", "url": "https://search.brave.com", "results": [{"title": "Fonte", "href": "https://example.com", "snippet": "Conteúdo"}]}
        view = browser_reading_view("browser_google_search", result)
        self.assertEqual(view["results"][0]["title"], "Fonte")
        self.assertEqual(view["url"], result["url"])
        result["from_conversation_cache"] = True
        self.assertEqual(browser_reading_view("browser_google_search", result)["via"], "cache")

    def test_blocked_page_never_becomes_reading_view(self):
        self.assertIsNone(browser_reading_view("web_fetch", {"blocked": True, "text": "secret"}))
        self.assertIsNone(browser_reading_view("web_fetch", {"success": False}))

    def test_browser_search_uses_capture_instead(self):
        self.assertIsNone(browser_reading_view("browser_google_search", {"engine": "duckduckgo_browser"}))


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_shell_does_not_capture_or_start_chrome(self):
        bus = AsyncMock()
        with patch.object(tool_executor.browser_pool, "get_existing", new=AsyncMock()) as existing:
            await tool_executor._publish_screenshot_if_browser_action("t", "shell_run", bus)
            existing.assert_not_awaited()
            bus.publish.assert_not_awaited()

    async def test_blank_capture_not_published(self):
        browser = AsyncMock()
        browser.screenshot.return_value = {"url": "about:blank", "empty": True}
        bus = AsyncMock()
        with patch.object(tool_executor.browser_pool, "get_existing", new=AsyncMock(return_value=browser)):
            await tool_executor._publish_screenshot_if_browser_action("t", "browser_navigate", bus)
        bus.publish.assert_not_awaited()

    async def test_sensitive_capture_publishes_block_not_image(self):
        browser = AsyncMock()
        browser.screenshot.return_value = {"blocked": True, "blocked_reason": "sensitive_input"}
        bus = AsyncMock()
        with patch.object(tool_executor.browser_pool, "get_existing", new=AsyncMock(return_value=browser)):
            await tool_executor._publish_screenshot_if_browser_action("t", "browser_type", bus)
        self.assertEqual(bus.publish.call_args.args[1], "screen_frame_blocked")
        self.assertNotIn("image_base64", bus.publish.call_args.args[2])

    async def test_capture_timeout_is_bounded(self):
        browser = AsyncMock()
        async def stalled(**kwargs):
            await asyncio.sleep(60)
        browser.screenshot.side_effect = stalled
        bus = AsyncMock()
        with patch.object(tool_executor.browser_pool, "get_existing", new=AsyncMock(return_value=browser)):
            await asyncio.wait_for(tool_executor._publish_screenshot_if_browser_action("t", "browser_navigate", bus), timeout=5)
        self.assertEqual(bus.publish.call_args.args[1], "error")

    async def test_web_fetch_publishes_reading_without_chrome(self):
        bus = AsyncMock()
        result = {"success": True, "url": "https://example.com", "title": "Example", "text": "Fetched text"}
        with patch("tools.web_fetch.web_fetch", new=AsyncMock(return_value=result)):
            response = await tool_executor.execute_tool("web_fetch", {"url": result["url"]}, task_id="test-reading", bus=bus)
        self.assertTrue(response["success"])
        views = [c.args[2] for c in bus.publish.call_args_list if c.args[1] == "browser_view"]
        self.assertEqual(views[0]["text"], "Fetched text")
