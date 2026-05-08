import unittest

from services.agent_runner import _history_with_authorized_session
from services.credential_store import CredentialStore
import services.agent_runner as agent_runner_module


class ContextAuthIsolationTests(unittest.TestCase):
    def test_authorized_session_history_contains_only_safe_metadata(self) -> None:
        original_store = agent_runner_module.credential_store
        store = CredentialStore()
        try:
            agent_runner_module.credential_store = store
            store.create_authorization(
                task_id="task-1",
                user_id="user-1",
                login_url="https://example.com/login",
                username="alice@example.com",
                password="DO_NOT_STORE_123",
            )

            history = _history_with_authorized_session("task-1", [{"role": "user", "content": "analise bugs"}])
            text = "\n".join(item["content"] for item in history)

            self.assertIn("https://example.com", text)
            self.assertNotIn("alice@example.com", text)
            self.assertNotIn("DO_NOT_STORE_123", text)
        finally:
            agent_runner_module.credential_store = original_store

    def test_finish_response_appends_generated_signup_credentials(self) -> None:
        from services.agent_runner import _finish_text_response
        from services.credential_store import CredentialStore
        import services.agent_runner as agent_runner_module

        class Store:
            def __init__(self):
                self.result = None
            def update_status(self, task_id, status, result=None):
                self.result = result

        class Bus:
            def __init__(self):
                self.events = []
            def history(self, task_id):
                return []
            async def publish(self, task_id, event_type, payload):
                self.events.append((event_type, payload))

        async def noop(*args, **kwargs):
            return None

        async def fake_context(*args, **kwargs):
            return [], {}, False

        original_store = agent_runner_module.credential_store
        original_complete = agent_runner_module._complete_supported_steps_before_delivery
        original_start = agent_runner_module._start_plan_step
        original_complete_step = agent_runner_module._complete_plan_step
        original_cleanup = agent_runner_module._cleanup_project_runtime
        original_context = agent_runner_module.prepare_context_history
        try:
            store = CredentialStore()
            agent_runner_module.credential_store = store
            agent_runner_module._complete_supported_steps_before_delivery = noop
            agent_runner_module._start_plan_step = noop
            agent_runner_module._complete_plan_step = noop
            agent_runner_module._cleanup_project_runtime = noop
            agent_runner_module.prepare_context_history = fake_context
            store.create_authorization(task_id="task-signup", user_id="user-1", login_url="https://example.com/signup", username="unused", password="unused")
            creds = store.create_signup_credentials("task-signup")
            state = Store()
            bus = Bus()

            import asyncio
            asyncio.run(_finish_text_response("task-signup", "cadastre", "Cadastro concluido.", state, bus))

            self.assertIn(creds["username"], state.result)
            self.assertIn(creds["email"], state.result)
            self.assertIn(creds["password"], state.result)
        finally:
            agent_runner_module.credential_store = original_store
            agent_runner_module._complete_supported_steps_before_delivery = original_complete
            agent_runner_module._start_plan_step = original_start
            agent_runner_module._complete_plan_step = original_complete_step
            agent_runner_module._cleanup_project_runtime = original_cleanup
            agent_runner_module.prepare_context_history = original_context


if __name__ == "__main__":
    unittest.main()
