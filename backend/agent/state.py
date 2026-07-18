"""Estado de execução da task no loop nativo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskAgentState:
    task_id: str
    description: str
    phase: str = "INTAKE"  # INTAKE|PLAN|EXECUTE|VERIFY|DELIVER
    iteration: int = 0
    tool_calls: int = 0
    stagnant_iterations: int = 0
    last_fingerprint: str = ""
    same_fingerprint_count: int = 0
    files_seen: int = 0
    sources_seen: int = 0
    research_mode: str = "fast"
    user_profile: dict[str, Any] | None = None
    native: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self, tool_name: str, params: dict[str, Any] | None) -> str:
        import json

        return f"{tool_name}:{json.dumps(params or {}, sort_keys=True, ensure_ascii=False)[:400]}"

    def note_tool(self, tool_name: str, params: dict[str, Any] | None, *, progressed: bool) -> None:
        fp = self.fingerprint(tool_name, params)
        if fp == self.last_fingerprint:
            self.same_fingerprint_count += 1
        else:
            self.same_fingerprint_count = 1
            self.last_fingerprint = fp
        self.tool_calls += 1
        if progressed:
            self.stagnant_iterations = 0
        else:
            self.stagnant_iterations += 1
