import unittest

from services.github_repos import is_github_repo_analysis_request, normalize_public_github_repo


class GitHubRepoIntentTests(unittest.TestCase):
    def test_detects_public_github_url(self) -> None:
        repo = normalize_public_github_repo("analise https://github.com/openai/openai-python")

        self.assertEqual(repo["full_name"], "openai/openai-python")
        self.assertEqual(repo["clone_url"], "https://github.com/openai/openai-python.git")

    def test_detects_public_github_host_without_scheme(self) -> None:
        repo = normalize_public_github_repo("github.com/vitejs/vite.git")

        self.assertEqual(repo["html_url"], "https://github.com/vitejs/vite")

    def test_detects_owner_repo_only_with_github_context(self) -> None:
        repo = normalize_public_github_repo("no GitHub, analise pallets/flask")

        self.assertEqual(repo["full_name"], "pallets/flask")

    def test_owner_repo_without_context_is_ignored(self) -> None:
        self.assertIsNone(normalize_public_github_repo("abra docs/api para revisar"))

    def test_analysis_request_requires_analysis_language(self) -> None:
        self.assertTrue(is_github_repo_analysis_request("analise https://github.com/psf/requests"))
        self.assertFalse(is_github_repo_analysis_request("baixe https://github.com/psf/requests"))


if __name__ == "__main__":
    unittest.main()
