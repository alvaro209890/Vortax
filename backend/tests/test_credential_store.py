import time
import unittest

from services.credential_store import CredentialStore, CredentialStoreError, normalize_origin


class CredentialStoreTests(unittest.TestCase):
    def test_normalizes_origins_and_allows_only_declared_scope(self) -> None:
        store = CredentialStore()
        store.create_authorization(
            task_id="task-1",
            user_id="user-1",
            login_url="https://Example.com/login",
            username="alice",
            password="secret",
            allowed_origins=["https://auth.example.com/callback"],
        )

        self.assertEqual(normalize_origin("https://Example.com/path"), "https://example.com")
        self.assertTrue(store.is_url_allowed("task-1", "https://example.com/dashboard"))
        self.assertTrue(store.is_url_allowed("task-1", "https://auth.example.com/oauth"))
        self.assertFalse(store.is_url_allowed("task-1", "https://evil.example.net"))

    def test_credentials_are_revoked_after_raw_revoke(self) -> None:
        store = CredentialStore()
        store.create_authorization(task_id="task-1", user_id="user-1", login_url="https://example.com", username="alice", password="secret")

        self.assertEqual(store.consume_for_login("task-1", "user-1")["password"], "secret")
        store.revoke_raw_credentials("task-1", status="login_succeeded")
        metadata = store.get_metadata("task-1", "user-1")

        self.assertFalse(metadata["password_present"])
        self.assertEqual(metadata["status"], "login_succeeded")

    def test_task_and_user_isolation(self) -> None:
        store = CredentialStore()
        store.create_authorization(task_id="task-1", user_id="user-1", login_url="https://example.com", username="alice", password="secret")

        self.assertIsNone(store.consume_for_login("task-1", "user-2"))
        self.assertIsNone(store.consume_for_login("missing", "user-1"))

    def test_ttl_expiry_removes_raw_credentials(self) -> None:
        store = CredentialStore()
        store.create_authorization(task_id="task-1", user_id="user-1", login_url="https://example.com", username="alice", password="secret", ttl_seconds=1)
        auth = store._get("task-1", "user-1")
        auth.expires_at = auth.created_at
        time.sleep(0.01)

        metadata = store.get_metadata("task-1", "user-1")

        self.assertEqual(metadata["status"], "expired")
        self.assertFalse(metadata["password_present"])

    def test_generates_strong_signup_credentials(self) -> None:
        store = CredentialStore()
        store.create_authorization(task_id="task-1", user_id="user-1", login_url="https://example.com/signup", username="unused", password="unused")

        creds = store.create_signup_credentials("task-1")
        summary = store.signup_summary("task-1")

        self.assertRegex(creds["username"], r"^vortax_[a-f0-9]{8}$")
        self.assertRegex(creds["email"], r"^vortax\+[a-f0-9]{8}@example\.com$")
        self.assertGreaterEqual(len(creds["password"]), 16)
        self.assertNotEqual(creds["password"], "12345678")
        self.assertEqual(summary["password"], creds["password"])

    def test_rejects_invalid_urls(self) -> None:
        store = CredentialStore()
        with self.assertRaises(CredentialStoreError):
            store.create_authorization(task_id="task-1", user_id="user-1", login_url="ftp://example.com", username="alice", password="secret")


if __name__ == "__main__":
    unittest.main()
