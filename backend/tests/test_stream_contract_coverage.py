"""Todo tipo de evento publicado no código precisa estar no KNOWN_EVENT_TYPES.

Tipo fora da lista vira "error" no stream (build_stream_event). Foi assim que o
task_title_updated se perdeu: o título da conversa nunca atualizava no front.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from services.stream_contract import KNOWN_EVENT_TYPES

BACKEND = Path(__file__).resolve().parent.parent
PUBLISH_RE = re.compile(r'publish\(\s*[\w.\[\]"]+\s*,\s*"([a-z_]+)"')


def published_event_types() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in BACKEND.rglob("*.py"):
        if {"venv", ".venv", "tests"} & set(path.parts):
            continue
        for match in PUBLISH_RE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            found.setdefault(match.group(1), set()).add(str(path.relative_to(BACKEND)))
    return found


class StreamContractCoverageTests(unittest.TestCase):
    def test_every_published_type_is_known(self):
        published = published_event_types()
        self.assertIn("assistant_message_done", published, "a varredura não achou os publish()")
        missing = {name: sorted(files) for name, files in published.items() if name not in KNOWN_EVENT_TYPES}
        self.assertEqual(missing, {}, "adicione estes tipos em services/stream_contract.py")


if __name__ == "__main__":
    unittest.main()
