import unittest

from auth import AuthUser
from services.metrics import MetricsRegistry
from services.permissions import (
    CAP_DESTRUCTIVE,
    CAP_EXPORT,
    CAP_SHELL,
    capabilities_for,
    tool_allowed,
)


class PermissionsTests(unittest.TestCase):
    def test_default_user_has_shell(self):
        user = AuthUser(uid="u1", email="a@b.c", name="A")
        self.assertTrue(tool_allowed(user, "shell_run"))
        self.assertTrue(tool_allowed(user, "browser_navigate"))
        caps = capabilities_for(user)
        self.assertIn(CAP_EXPORT, caps.granted)
        self.assertIn(CAP_DESTRUCTIVE, caps.granted)


class MetricsTests(unittest.TestCase):
    def test_record_usage_and_snapshot(self):
        m = MetricsRegistry()
        m.record_usage("deepseek", {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        m.observe_ms("deepseek_request", 120.0)
        m.incr("agent_runs")
        snap = m.snapshot()
        self.assertEqual(snap["token_usage"]["deepseek"]["total"], 150)
        self.assertIn("deepseek_request", snap["timings"])
        self.assertEqual(snap["counters"]["agent_runs"], 1)
        self.assertIn("deepseek", snap["estimated_cost_usd"])


if __name__ == "__main__":
    unittest.main()
