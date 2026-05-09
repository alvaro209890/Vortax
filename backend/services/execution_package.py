import logging
import re
import shlex
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_SKIP_DIRS = frozenset({"node_modules", ".git", "venv", ".venv", "__pycache__", ".next", "dist", "build", ".cache"})
_CODE_EXTS = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
    ".yaml", ".yml", ".toml", ".md", ".sh", ".go", ".rs", ".vue", ".svelte",
})
_PRUNE_THRESHOLD = 150


def _prune_python(lines: list[str]) -> str:
    out: list[str] = []
    in_def = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("import ", "from ")):
            out.append(line.rstrip())
            in_def = False
            continue
        if stripped.startswith(("class ", "def ", "async def ")):
            out.append(line.rstrip())
            in_def = True
            continue
        if in_def:
            if stripped.startswith(('"""', "'''", "#")):
                out.append("    " + stripped[:120].rstrip())
            in_def = False
    return "\n".join(out)


def _prune_js(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if (
            stripped.startswith(("import ", "from "))
            or stripped.startswith("export ")
            or re.match(r"(?:const|let|var)\s+\w+\s*=\s*(?:memo\(|React\.memo\(|function|async\s+function|\()", stripped)
            or re.match(r"(?:async\s+)?function\s+\w+", stripped)
            or stripped.startswith(("module.exports", "export default"))
        ):
            out.append(line.rstrip())
    return "\n".join(out)


def _prune_file_context(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if len(lines) <= _PRUNE_THRESHOLD:
        return text.rstrip()
    suffix = path.suffix.lower()
    if suffix == ".py":
        pruned = _prune_python(lines)
        omitted = len(lines) - pruned.count("\n") - 1
        return pruned + f"\n# [{omitted} linhas omitidas — arquivo completo no disco]"
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
        pruned = _prune_js(lines)
        omitted = len(lines) - pruned.count("\n") - 1
        return pruned + f"\n// [{omitted} linhas omitidas — arquivo completo no disco]"
    first80 = "\n".join(lines[:80])
    return first80 + f"\n# [{len(lines) - 80} linhas omitidas]"


def _select_relevant_files(workspace: Path, objective: str, max_files: int = 8) -> list[Path]:
    if not workspace.exists():
        return []
    keywords = [w.lower() for w in re.split(r"\W+", objective) if len(w) >= 4]
    candidates: list[tuple[int, Path]] = []
    for path in workspace.rglob("*"):
        if path.is_dir():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _CODE_EXTS:
            continue
        try:
            if path.stat().st_size > 500_000:
                continue
        except OSError:
            continue
        name = path.stem.lower()
        score = sum(1 for kw in keywords if kw in name)
        candidates.append((score, path))
    candidates.sort(key=lambda x: (-x[0], x[1].name))
    return [p for _, p in candidates[:max_files]]


def build_execution_package(
    objective: str,
    task_id: str,
    *,
    constraints: list[str] | None = None,
    success_criteria: list[str] | None = None,
    snippets_block: str = "",
) -> str:
    """Monta ExecutionPackage estruturado em Markdown para o OpenClaude."""
    workspace = settings.WORKSPACE_PATH / task_id
    relevant = _select_relevant_files(workspace, objective)

    sections: list[str] = [f"## Objetivo\n{objective.strip()}"]

    if relevant:
        file_parts: list[str] = []
        for path in relevant:
            try:
                rel = path.relative_to(workspace)
            except ValueError:
                rel = path
            content = _prune_file_context(path)
            if content.strip():
                suffix = path.suffix.lower().lstrip(".")
                fence = suffix or "text"
                file_parts.append(f"### {rel}\n```{fence}\n{content}\n```")
        if file_parts:
            sections.append("## Arquivos Relevantes\n" + "\n\n".join(file_parts))

    if constraints:
        sections.append("## Restrições\n" + "\n".join(f"- {c}" for c in constraints))

    if success_criteria:
        sections.append("## Critérios de Sucesso\n" + "\n".join(f"- [ ] {s}" for s in success_criteria))

    if snippets_block:
        sections.append(snippets_block)

    return "\n\n".join(sections)


def extract_openclaude_prompt(command: str) -> str | None:
    """Extrai o argumento prompt de `openclaude '...'` ou `cd X && openclaude '...'`."""
    try:
        parts = shlex.split(command or "")
    except ValueError:
        return None
    if len(parts) >= 4 and parts[0] == "cd" and parts[2] == "&&":
        parts = parts[3:]
    if not parts:
        return None
    if Path(parts[0]).name != "openclaude":
        return None
    return " ".join(parts[1:]) if len(parts) > 1 else None


def enrich_code_agent_command(
    command: str,
    task_id: str,
    *,
    constraints: list[str] | None = None,
    success_criteria: list[str] | None = None,
    snippets_block: str = "",
) -> str:
    """Substitui o prompt plano do OpenClaude por um ExecutionPackage estruturado.

    Se não conseguir parsear o comando original, retorna o comando inalterado.
    """
    original_prompt = extract_openclaude_prompt(command)
    if not original_prompt:
        return command

    package = build_execution_package(
        original_prompt,
        task_id,
        constraints=constraints,
        success_criteria=success_criteria,
        snippets_block=snippets_block,
    )
    workspace = settings.WORKSPACE_PATH / task_id
    enriched = f"cd {shlex.quote(str(workspace))} && openclaude {shlex.quote(package)}"
    logger.debug(
        "[execution_package] prompt: %d chars → package: %d chars",
        len(original_prompt),
        len(package),
    )
    return enriched
