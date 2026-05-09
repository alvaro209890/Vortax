import json
import tempfile
import unittest
from pathlib import Path

from services.project_files import missing_local_asset_refs
from services.web_validation import _vision_found_bug, detect_web_project, local_url_from_shell_result, web_intent_from_command


class WebValidationTests(unittest.TestCase):
    def test_detects_static_index_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")

            detected = detect_web_project(project)

        self.assertEqual(detected["type"], "static_html")
        self.assertEqual(detected["index_html"], "index.html")

    def test_detects_nested_static_index_html_preview_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "workspace" / "calc").mkdir(parents=True)
            (project / "workspace" / "calc" / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")

            detected = detect_web_project(project)

        self.assertEqual(detected["type"], "static_html")
        self.assertEqual(detected["index_html"], "workspace/calc/index.html")
        self.assertIn("workspace/calc/index.html", detected["url_template"])

    def test_detects_node_dev_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                json.dumps({"scripts": {"dev": "vite --host 0.0.0.0"}}),
                encoding="utf-8",
            )

            detected = detect_web_project(project)

        self.assertEqual(detected["type"], "node_dev_server")
        self.assertEqual(detected["command"], "npm run dev")

    def test_force_marks_missing_web_project_as_failed_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            detected = detect_web_project(Path(tmp), force=True)

        self.assertEqual(detected["type"], "missing")

    def test_web_intent_matches_site_commands(self) -> None:
        self.assertTrue(web_intent_from_command("vertex 'crie um site em react'"))
        self.assertTrue(web_intent_from_command("openclaude 'crie um site em react'"))
        self.assertFalse(web_intent_from_command("vertex 'crie uma api em python'"))

    def test_vision_bug_heuristic(self) -> None:
        self.assertTrue(_vision_found_bug({"summary": "Ha texto cortado e elementos sobrepostos."}))
        self.assertFalse(_vision_found_bug({"summary": "Nao ha bugs aparentes nesta viewport."}))

    def test_extracts_openclaude_local_site_link(self) -> None:
        url = local_url_from_shell_result({"stdout": "LINK_LOCAL_DO_SITE: http://0.0.0.0:5173/"})

        self.assertEqual(url, "http://127.0.0.1:5173/")

    def test_prefers_preserved_local_urls_from_shell_result(self) -> None:
        url = local_url_from_shell_result({"stdout": "sem link", "local_urls": ["http://localhost:4173/app"]})

        self.assertEqual(url, "http://localhost:4173/app")

    def test_detects_missing_local_assets_referenced_by_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "index.html").write_text(
                '<link rel="stylesheet" href="style.css"><script src="script.js"></script>',
                encoding="utf-8",
            )

            missing = missing_local_asset_refs(project)

        self.assertEqual(missing, ["script.js", "style.css"])

    def test_missing_asset_detector_ignores_external_and_existing_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "style.css").write_text("body {}", encoding="utf-8")
            (project / "index.html").write_text(
                '<link rel="stylesheet" href="style.css">'
                '<script src="https://cdn.example/app.js"></script>'
                '<a href="#top">top</a>',
                encoding="utf-8",
            )

            missing = missing_local_asset_refs(project)

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
