import unittest

from fastapi import HTTPException

from api import tasks as tasks_module


class AuthorizedTasksApiTests(unittest.TestCase):
    def test_rejects_inline_credentials_before_event_creation(self) -> None:
        with self.assertRaises(HTTPException):
            tasks_module._reject_inline_credentials("senha: DO_NOT_STORE_123")

    def test_authorized_description_is_sanitized(self) -> None:
        safe = tasks_module._safe_authorized_description("analise bugs", "https://example.com")

        self.assertIn("https://example.com", safe)
        self.assertNotIn("DO_NOT_STORE_123", safe)
        self.assertNotIn("senha", safe.lower())


if __name__ == "__main__":
    unittest.main()
