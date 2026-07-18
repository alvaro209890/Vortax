import unittest
from unittest import mock

from agent.gates import ResearchSourcesGate, CycleGuardGate, evaluate_delivery_gates, first_blocking_gate
from agent.tools.registry import build_tool_specs, openai_tools_payload, tool_is_read_only, legacy_tools_schema_from_registry


class RegistryTests(unittest.TestCase):
    def test_openai_payload_shape(self):
        tools = openai_tools_payload()
        self.assertGreater(len(tools), 10)
        names = {t["function"]["name"] for t in tools}
        self.assertIn("browser_google_search", names)
        self.assertIn("file_read", names)
        self.assertIn("todo_write", names)
        self.assertIn("message_ask_user", names)
        for t in tools:
            self.assertEqual(t["type"], "function")
            self.assertIn("parameters", t["function"])
            self.assertEqual(t["function"]["parameters"]["type"], "object")

    def test_read_only_flags(self):
        self.assertTrue(tool_is_read_only("file_read"))
        self.assertTrue(tool_is_read_only("browser_google_search"))
        self.assertFalse(tool_is_read_only("shell_run"))
        self.assertFalse(tool_is_read_only("file_write"))

    def test_legacy_schema(self):
        legacy = legacy_tools_schema_from_registry()
        self.assertTrue(any(x["action"] == "shell_run" for x in legacy))


class GatesTests(unittest.TestCase):
    def test_cycle_gate_stagnant(self):
        g = CycleGuardGate()
        ok = g.check({"stagnant_iterations": 1})
        self.assertTrue(ok.ok)
        bad = g.check({"stagnant_iterations": 8})
        self.assertFalse(bad.ok)
        self.assertIn("GATE", bad.as_system_message()[:20] + "x")
        self.assertTrue(bad.as_system_message().startswith("[GATE:"))

    def test_research_gate_satisfied_when_no_requirement(self):
        with mock.patch("agent.gates.database") as db:
            db.list_sources.return_value = []
            with mock.patch("agent.gates.cross_check_status", return_value={"satisfied": True, "required_sources": 0}):
                r = ResearchSourcesGate().check({"task_id": "t1", "user_prompt": "oi"})
                self.assertTrue(r.ok)

    def test_first_blocking(self):
        results = evaluate_delivery_gates({"stagnant_iterations": 0, "task_id": "", "user_prompt": "x"})
        # may or may not block research depending on policy; ensure list
        self.assertIsInstance(results, list)
        # force a fail
        from agent.gates import GateResult

        self.assertIsNotNone(first_blocking_gate([GateResult(ok=False, code="x", instruction="no")]))
        self.assertIsNone(first_blocking_gate([GateResult(ok=True, code="y")]))


if __name__ == "__main__":
    unittest.main()
