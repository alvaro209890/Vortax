"""Tools de arquivo confinadas ao workspace da task (plano-melhoria-ia §03)."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from config import settings
from services.project_files import annotate_workspace_files, sync_task_workspace_files
from services.stream_contract import utc_now

MAX_READ_LINES = 2000
MAX_READ_BYTES = 50 * 1024
MAX_WRITE_BYTES = 2 * 1024 * 1024

# Claude Code: Edit exige Read prévio na mesma task (anti-edição cega).
_READ_TRACKER: dict[str, set[str]] = {}


def mark_file_read(task_id: str, path: str) -> None:
    _READ_TRACKER.setdefault(task_id, set()).add(str(path).replace("\\", "/"))


def was_file_read(task_id: str, path: str) -> bool:
    return str(path).replace("\\", "/") in _READ_TRACKER.get(task_id, set())


def clear_task_reads(task_id: str) -> None:
    _READ_TRACKER.pop(task_id, None)


def _workspace(task_id: str) -> Path:
    base = (settings.WORKSPACE_PATH / task_id).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_task_path(task_id: str, relative: str) -> Path:
    base = _workspace(task_id)
    rel = str(relative or "").strip().lstrip("/")
    if not rel or rel in {".", ".."} or ".." in Path(rel).parts:
        raise ValueError("Caminho invalido")
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise ValueError("Path traversal bloqueado")
    if target.is_symlink():
        real = target.resolve()
        if real != base and base not in real.parents:
            raise ValueError("Symlink fora do workspace bloqueado")
    return target


def file_read(task_id: str, path: str, offset: int = 1, limit: int | None = None) -> dict[str, Any]:
    target = resolve_task_path(task_id, path)
    if not target.exists() or not target.is_file():
        return {"success": False, "error": f"Arquivo nao encontrado: {path}"}
    size = target.stat().st_size
    if size > MAX_READ_BYTES * 4:
        return {
            "success": True,
            "path": path,
            "binary_or_large": True,
            "size_bytes": size,
            "note": "Arquivo grande; leia com offset/limit ou use shell.",
        }
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"success": False, "error": str(exc)}
    lines = text.splitlines()
    start = max(1, int(offset or 1))
    max_lines = min(MAX_READ_LINES, int(limit) if limit else MAX_READ_LINES)
    chunk = lines[start - 1 : start - 1 + max_lines]
    numbered = "\n".join(f"{i + start:>6}|{line}" for i, line in enumerate(chunk))
    rel = str(path).replace("\\", "/")
    mark_file_read(task_id, rel)
    return {
        "success": True,
        "path": path,
        "offset": start,
        "lines_returned": len(chunk),
        "total_lines": len(lines),
        "content": numbered[:MAX_READ_BYTES],
    }


def file_write(task_id: str, path: str, content: str) -> dict[str, Any]:
    target = resolve_task_path(task_id, path)
    data = str(content or "")
    if len(data.encode("utf-8")) > MAX_WRITE_BYTES:
        return {"success": False, "error": f"Conteudo excede {MAX_WRITE_BYTES} bytes"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    sync_task_workspace_files(task_id, _workspace(task_id))
    annotate_workspace_files(task_id, tool_origin="file_write", paths=[path], validation_status="pending")
    return {"success": True, "path": path, "size_bytes": target.stat().st_size, "created_at": utc_now()}


def file_edit(
    task_id: str,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> dict[str, Any]:
    rel = str(path).replace("\\", "/")
    if not was_file_read(task_id, rel):
        return {
            "success": False,
            "error": (
                f"file_edit recusado: leia '{rel}' com file_read nesta task antes de editar "
                "(padrao Claude Code / Manus file_str_replace)."
            ),
        }
    target = resolve_task_path(task_id, path)
    if not target.exists():
        return {"success": False, "error": f"Arquivo nao encontrado: {path}. Use file_read antes."}
    text = target.read_text(encoding="utf-8", errors="replace")
    old = str(old_string or "")
    new = str(new_string or "")
    if not old:
        return {"success": False, "error": "old_string vazio"}
    count = text.count(old)
    if count == 0:
        return {
            "success": False,
            "error": "old_string nao encontrado. Reler o arquivo com file_read e tentar de novo.",
        }
    if count > 1 and not replace_all:
        return {
            "success": False,
            "error": f"old_string aparece {count} vezes; use replace_all=true ou trecho unico.",
        }
    updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    target.write_text(updated, encoding="utf-8")
    sync_task_workspace_files(task_id, _workspace(task_id))
    annotate_workspace_files(task_id, tool_origin="file_edit", paths=[path], validation_status="pending")
    mark_file_read(task_id, rel)  # ainda "lido" após edit
    return {"success": True, "path": path, "replacements": count if replace_all else 1}


def file_append(task_id: str, path: str, content: str) -> dict[str, Any]:
    target = resolve_task_path(task_id, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(str(content or ""))
    sync_task_workspace_files(task_id, _workspace(task_id))
    return {"success": True, "path": path}


def glob_files(task_id: str, pattern: str, path: str = "") -> dict[str, Any]:
    base = resolve_task_path(task_id, path) if path else _workspace(task_id)
    if not base.exists():
        return {"success": True, "matches": []}
    matches: list[str] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "__pycache__", "dist", "build"}]
        for name in files:
            full = Path(root) / name
            rel = full.relative_to(_workspace(task_id)).as_posix()
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
                matches.append(rel)
    matches.sort(key=lambda p: (_workspace(task_id) / p).stat().st_mtime if (_workspace(task_id) / p).exists() else 0, reverse=True)
    return {"success": True, "matches": matches[:200], "count": len(matches)}


def grep_files(
    task_id: str,
    pattern: str,
    path: str = "",
    glob_pat: str = "",
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    context: int = 0,
) -> dict[str, Any]:
    base = resolve_task_path(task_id, path) if path else _workspace(task_id)
    # Preferir ripgrep (Claude Code) quando disponível
    rg = _grep_with_ripgrep(
        base,
        pattern,
        glob_pat=glob_pat,
        output_mode=output_mode,
        case_insensitive=case_insensitive,
        context=context,
        workspace=_workspace(task_id),
    )
    if rg is not None:
        return rg

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return {"success": False, "error": f"Regex invalida: {exc}"}

    files_hit: list[str] = []
    content_hits: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "__pycache__", "dist", "build"}]
        for name in files:
            if glob_pat and not fnmatch.fnmatch(name, glob_pat):
                continue
            full = Path(root) / name
            if full.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip"}:
                continue
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = full.relative_to(_workspace(task_id)).as_posix()
            lines = text.splitlines()
            local_hits = 0
            for i, line in enumerate(lines, start=1):
                if not rx.search(line):
                    continue
                local_hits += 1
                if output_mode == "content":
                    ctx_before = lines[max(0, i - 1 - context) : i - 1]
                    ctx_after = lines[i : i + context]
                    content_hits.append(
                        {
                            "path": rel,
                            "line": i,
                            "text": line[:400],
                            "before": ctx_before[-context:] if context else [],
                            "after": ctx_after,
                        }
                    )
            if local_hits:
                files_hit.append(rel)
                counts[rel] = local_hits

    if output_mode == "count":
        return {"success": True, "engine": "python", "counts": counts, "files": len(counts)}
    if output_mode == "content":
        return {"success": True, "engine": "python", "matches": content_hits[:200], "files": len(files_hit)}
    return {"success": True, "engine": "python", "files": files_hit[:200], "count": len(files_hit)}


def _grep_with_ripgrep(
    base: Path,
    pattern: str,
    *,
    glob_pat: str,
    output_mode: str,
    case_insensitive: bool,
    context: int,
    workspace: Path,
) -> dict[str, Any] | None:
    import shutil
    import subprocess

    rg_bin = shutil.which("rg")
    if not rg_bin or not base.exists():
        return None
    cmd = [rg_bin, "--no-heading", "--line-number", "--color", "never"]
    if case_insensitive:
        cmd.append("-i")
    if glob_pat:
        cmd.extend(["--glob", glob_pat])
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    elif context:
        cmd.extend(["-C", str(int(context))])
    cmd.extend(["--", pattern, str(base)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in {0, 1}:  # 1 = no matches
        return None
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if output_mode == "files_with_matches":
        files = []
        for ln in lines[:200]:
            p = Path(ln)
            try:
                files.append(p.relative_to(workspace).as_posix())
            except ValueError:
                files.append(ln)
        return {"success": True, "engine": "ripgrep", "files": files, "count": len(files)}
    if output_mode == "count":
        counts: dict[str, int] = {}
        for ln in lines[:200]:
            if ":" not in ln:
                continue
            path_s, _, num = ln.rpartition(":")
            try:
                rel = Path(path_s).relative_to(workspace).as_posix()
            except ValueError:
                rel = path_s
            try:
                counts[rel] = int(num)
            except ValueError:
                continue
        return {"success": True, "engine": "ripgrep", "counts": counts, "files": len(counts)}
    matches = []
    for ln in lines[:200]:
        # path:line:text
        parts = ln.split(":", 2)
        if len(parts) < 3:
            continue
        path_s, line_s, text = parts
        try:
            rel = Path(path_s).relative_to(workspace).as_posix()
        except ValueError:
            rel = path_s
        try:
            line_no = int(line_s)
        except ValueError:
            continue
        matches.append({"path": rel, "line": line_no, "text": text[:400]})
    return {"success": True, "engine": "ripgrep", "matches": matches, "files": len({m["path"] for m in matches})}
