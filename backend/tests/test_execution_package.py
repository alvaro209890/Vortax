import tempfile
import unittest
from pathlib import Path

from config import settings
from services.execution_package import enrich_code_agent_command


class ExecutionPackageTests(unittest.TestCase):
    def test_github_analysis_package_includes_read_only_clone_contract(self) -> None:
        previous_workspace = settings.WORKSPACE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                settings.WORKSPACE_PATH = Path(tmp)
                command = enrich_code_agent_command(
                    "openclaude 'analise https://github.com/psf/requests'",
                    "task-github",
                )
            finally:
                settings.WORKSPACE_PATH = previous_workspace

        self.assertIn("Repositorio GitHub Publico", command)
        self.assertIn("https://github.com/psf/requests.git", command)
        self.assertIn("read-only", command)
        self.assertIn("RELATORIO_TECNICO.md", command)
        self.assertTrue(command.startswith("vertex "))


if __name__ == "__main__":
    unittest.main()
