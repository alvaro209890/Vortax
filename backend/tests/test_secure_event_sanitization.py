import unittest

from services.safe_diagnostics import sanitize_payload, redact_text


class SecureEventSanitizationTests(unittest.TestCase):
    def test_redacts_credential_keys(self) -> None:
        payload = sanitize_payload({"username": "alice", "password": "secret", "nested": {"otp": "123456"}})

        self.assertEqual(payload["username"], "[REDACTED]")
        self.assertEqual(payload["password"], "[REDACTED]")
        self.assertEqual(payload["nested"]["otp"], "[REDACTED]")

    def test_redacts_inline_password_patterns(self) -> None:
        text = redact_text("usuario alice senha: supersecret token=abc123")

        self.assertNotIn("supersecret", text)
        self.assertNotIn("abc123", text)
        self.assertIn("[REDACTED]", text)
    def test_redacts_browser_type_text_params_even_when_unlabeled(self) -> None:
        from tools.tool_executor import _safe_tool_params

        payload = _safe_tool_params("browser_type", {"selector": "input[type=password]", "text": "DO_NOT_STORE_123"})

        self.assertNotIn("DO_NOT_STORE_123", str(payload))
        self.assertIn("[REDACTED", payload["text"])


if __name__ == "__main__":
    unittest.main()
