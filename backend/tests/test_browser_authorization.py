import asyncio
import unittest

from tools.browser import BrowserTool


class FakeLocator:
    def __init__(self, count_value=0):
        self.count_value = count_value
        self.filled = []

    def first(self):
        return self

    async def count(self):
        return self.count_value

    async def evaluate(self, script):
        return True

    async def fill(self, value, timeout=0):
        self.filled.append(value)


class FakePage:
    url = "https://example.com/login"

    async def title(self):
        return "Login"

    def locator(self, selector):
        return FakeLocator(1 if "password" in selector else 0)

    async def evaluate(self, script):
        return True


class BrowserAuthorizationTests(unittest.TestCase):
    def test_blocks_generic_password_typing_without_authorization(self) -> None:
        tool = BrowserTool(9999, __import__("pathlib").Path("/tmp/vortax-test-profile"))
        page = FakePage()

        result = asyncio.run(tool._guard_password_typing(page, "input[type='password']", None))

        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "password_field_without_authorization")

    def test_sensitive_pages_are_not_safe_to_capture(self) -> None:
        tool = BrowserTool(9999, __import__("pathlib").Path("/tmp/vortax-test-profile"))
        page = FakePage()
        tool._ensure_page = lambda: asyncio.sleep(0, result=page)

        result = asyncio.run(tool.safe_to_capture())

        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "sensitive_input")
    def test_auth_signup_returns_generated_credentials(self) -> None:
        from services.credential_store import CredentialStore
        import tools.browser as browser_module

        class SignupLocator:
            def __init__(self, count_value=1):
                self.count_value = count_value
                self.values = []
            def first(self):
                return self
            def nth(self, index):
                return self
            async def count(self):
                return self.count_value
            async def fill(self, value, timeout=0):
                self.values.append(value)
            async def click(self, timeout=0):
                return None
            async def inner_text(self, timeout=0):
                return "signup page"

        class Keyboard:
            async def press(self, key):
                return None

        class SignupPage:
            url = "https://example.com/signup"
            keyboard = Keyboard()
            async def title(self):
                return "Signup"
            async def goto(self, url, wait_until=None, timeout=0):
                self.url = url
            async def wait_for_load_state(self, *args, **kwargs):
                return None
            async def wait_for_timeout(self, timeout):
                return None
            def locator(self, selector):
                return SignupLocator(2 if "password" in selector else 1)

        original_store = browser_module.credential_store
        try:
            store = CredentialStore()
            browser_module.credential_store = store
            store.create_authorization(task_id="task-signup", user_id="user-1", login_url="https://example.com/signup", username="unused", password="unused")
            tool = BrowserTool(9999, __import__("pathlib").Path("/tmp/vortax-test-profile"))
            tool._ensure_page = lambda: asyncio.sleep(0, result=SignupPage())

            result = asyncio.run(tool.auth_signup(task_id="task-signup"))

            self.assertTrue(result["success"])
            self.assertRegex(result["created_credentials"]["username"], r"^vortax_[a-f0-9]{8}$")
            self.assertNotEqual(result["created_credentials"]["password"], "12345678")
        finally:
            browser_module.credential_store = original_store


if __name__ == "__main__":
    unittest.main()
