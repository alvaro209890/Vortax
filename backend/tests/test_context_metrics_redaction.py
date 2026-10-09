import unittest
from services.safe_diagnostics import sanitize_payload


class TokenMetricTests(unittest.TestCase):
    def test_numeric_context_counts_are_not_credentials(self):
        value = sanitize_payload({"estimated_tokens": 470, "token_limit": 24000, "authorization": "Bearer private", "token": 123})
        self.assertEqual(value["estimated_tokens"], 470)
        self.assertEqual(value["token_limit"], 24000)
        self.assertEqual(value["authorization"], "[REDACTED]")
        self.assertEqual(value["token"], "[REDACTED]")

    def test_metric_named_strings_still_redacted(self):
        self.assertEqual(sanitize_payload({"token_limit": "private-secret"}), {"token_limit": "[REDACTED]"})
