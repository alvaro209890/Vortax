import asyncio
import unittest

from services.stream_contract import build_stream_event
from services.web_validation import _vision_found_bug
from tools.shell import (
    _clean_terminal_text,
    _display_terminal_line,
    _extract_command,
    _is_spinner_noise,
    _normalize_shell_command,
    _parse_vertex_progress,
    _publish_vertex_terminal_frame,
)
from tools.tool_executor import _augment_vertex_command_for_local_site, _augment_vertex_command_for_quality


class VertexStreamTests(unittest.TestCase):
    def test_ai_exchange_is_known_stream_event(self) -> None:
        event = build_stream_event(
            "task-1",
            "ai_exchange",
            {"actor": "deepseek", "target": "vertex", "message": "delegando"},
        )

        self.assertEqual(event["type"], "ai_exchange")
        self.assertEqual(event["payload"]["actor"], "deepseek")

    def test_web_validation_events_are_known_stream_events(self) -> None:
        for event_type in (
            "web_validation_started",
            "web_validation_step",
            "web_validation_result",
            "project_validation_started",
            "project_validation_step",
            "project_validation_result",
        ):
            with self.subTest(event_type=event_type):
                event = build_stream_event("task-1", event_type, {"status": "passed"})
                self.assertEqual(event["type"], event_type)

    def test_parses_vertex_file_progress(self) -> None:
        progress = _parse_vertex_progress("Criando arquivo src/App.jsx")

        self.assertEqual(progress["stage"], "writing_file")
        self.assertEqual(progress["file"], "src/App.jsx")

    def test_cleans_terminal_control_sequences(self) -> None:
        cleaned = _clean_terminal_text("\x1b[32mVertex\x1b[0m\r\n")

        self.assertEqual(cleaned, "Vertex\r\n")

    def test_cleans_vertex_osc_title_sequences(self) -> None:
        cleaned = _clean_terminal_text("\x1b]0;✳ Vertex\x07Conectado\r\n")

        self.assertEqual(cleaned, "Conectado\r\n")

    def test_filters_spinner_only_terminal_lines(self) -> None:
        self.assertTrue(_is_spinner_noise("●"))
        self.assertTrue(_is_spinner_noise("  ◔  "))
        self.assertFalse(_is_spinner_noise("◔ Aplicando…"))

    def test_removes_spinner_prefix_from_status_line(self) -> None:
        self.assertEqual(_display_terminal_line("◔ Aplicando…"), "Aplicando…")

    def test_augments_vertex_site_prompt_with_local_link_instruction(self) -> None:
        command = _augment_vertex_command_for_local_site("vertex 'crie um site react'")

        self.assertIn("LINK_LOCAL_DO_SITE", command)
        self.assertIn("vertex -p", command)
        self.assertIn("index.html", command)

    def test_augments_vertex_command_after_safe_cd(self) -> None:
        command = _augment_vertex_command_for_local_site("cd workspace/app && vertex 'crie uma landing page'")

        self.assertTrue(command.startswith("cd workspace/app && vertex -p"))
        self.assertIn("LINK_LOCAL_DO_SITE", command)

    def test_existing_local_link_instruction_still_uses_print_mode(self) -> None:
        command = _augment_vertex_command_for_local_site("vertex 'crie site e imprima LINK_LOCAL_DO_SITE'")

        self.assertIn("vertex -p", command)
        self.assertEqual(command.count("LINK_LOCAL_DO_SITE"), 1)

    def test_does_not_augment_non_site_vertex_prompt(self) -> None:
        command = _augment_vertex_command_for_local_site("vertex 'crie uma api python'")

        self.assertEqual(command, "vertex 'crie uma api python'")

    def test_augments_non_site_vertex_prompt_with_quality_gate(self) -> None:
        command = _augment_vertex_command_for_quality("vertex 'crie uma api python'")

        self.assertIn("VALIDACAO_AUTOMATICA_VORTAX", command)
        self.assertIn("python3 -m py_compile", command)
        self.assertIn("vertex -p", command)

    def test_does_not_augment_vertex_version_check_with_quality_gate(self) -> None:
        command = _augment_vertex_command_for_quality("vertex --version")

        self.assertEqual(command, "vertex --version")

    def test_normalizes_background_dev_server_wrappers(self) -> None:
        command = _normalize_shell_command("cd workspace/calc && nohup python3 -m http.server 8080 --bind 127.0.0.1 &")

        self.assertEqual(command, "cd workspace/calc && python3 -m http.server 8080 --bind 127.0.0.1")
        self.assertEqual(_extract_command(command), "python3")

    def test_vertex_terminal_status_uses_progress_event_not_screen_frame(self) -> None:
        class FakeBus:
            def __init__(self) -> None:
                self.events = []

            async def publish(self, *args, **kwargs) -> None:
                self.events.append((args, kwargs))

        async def run() -> None:
            bus = FakeBus()
            await _publish_vertex_terminal_frame(
                "task-1",
                bus,
                [{"stream": "stdout", "line": "Criando arquivo index.html"}],
                current_stage="writing_file",
            )
            self.assertEqual(bus.events[0][0][1], "vertex_progress")
            payload = bus.events[0][0][2]
            self.assertEqual(payload["current_stage"], "writing_file")
            self.assertEqual(payload["line_count"], 1)

        asyncio.run(run())

    def test_visual_validation_does_not_flag_negated_bug_summary(self) -> None:
        self.assertFalse(
            _vision_found_bug(
                {
                    "summary": (
                        "Não há bugs aparentes. A página carrega corretamente e o layout parece bem estruturado. "
                        "Nenhum erro visual ou funcional foi detectado."
                    )
                }
            )
        )

    def test_visual_validation_flags_affirmative_bug_summary(self) -> None:
        self.assertTrue(
            _vision_found_bug(
                {
                    "summary": "Há um bug visual: o botão está cortado e parte do texto não aparece."
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
