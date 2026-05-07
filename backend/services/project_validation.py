import asyncio
import json
from pathlib import Path
from typing import Any

from config import settings
from services.document_artifacts import valid_markdown_files, valid_pdf_files
from services.document_intent import document_extensions_from_text, report_artifact_profile
from services.project_files import missing_local_asset_refs, scan_task_workspace
from services.web_validation import web_intent_from_command


CODE_SUFFIXES = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".mjs",
    ".php",
    ".py",
    ".rs",
    ".sh",
    ".ts",
    ".tsx",
    ".vue",
}


def _project_suffixes(files: list[dict[str, Any]]) -> set[str]:
    return {str(file.get("extension") or "").lower() for file in files}


def detect_project_profile(project_dir: Path) -> dict[str, Any]:
    files = scan_task_workspace(project_dir)
    paths = {str(file.get("path") or "") for file in files}
    suffixes = _project_suffixes(files)

    kind = "generic"
    if any(path.endswith("package.json") for path in paths):
        kind = "node"
    if ".py" in suffixes and kind == "generic":
        kind = "python"
    if any(path.endswith("index.html") for path in paths) and kind == "generic":
        kind = "static_web"
    if not files:
        kind = "empty"

    return {
        "kind": kind,
        "file_count": len(files),
        "paths": sorted(paths),
        "suffixes": sorted(suffixes),
        "has_code": bool(suffixes & CODE_SUFFIXES),
        "has_tests_dir": (project_dir / "tests").is_dir(),
        "has_package_json": any(path.endswith("package.json") for path in paths),
        "has_index_html": any(path.endswith("index.html") for path in paths),
    }


def _trim_output(text: str, limit: int = 1600) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "... [truncated]"


async def _run_check(args: list[str], cwd: Path, *, timeout: float) -> dict[str, Any]:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return {
            "command": " ".join(args),
            "returncode": -1,
            "stdout": "",
            "stderr": f"Comando indisponivel: {exc.filename}",
            "passed": False,
            "blocked": True,
        }

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return {
            "command": " ".join(args),
            "returncode": -1,
            "stdout": _trim_output(stdout.decode("utf-8", errors="replace")),
            "stderr": f"Timeout depois de {timeout:.0f}s",
            "passed": False,
        }

    returncode = process.returncode if process.returncode is not None else -1
    return {
        "command": " ".join(args),
        "returncode": returncode,
        "stdout": _trim_output(stdout.decode("utf-8", errors="replace")),
        "stderr": _trim_output(stderr.decode("utf-8", errors="replace")),
        "passed": returncode == 0,
    }


async def _publish_step(task_id: str, bus: Any, label: str, detail: str = "", **extra: Any) -> None:
    await bus.publish(task_id, "project_validation_step", {"label": label, "detail": detail, **extra})
    await bus.publish(task_id, "agent_progress", {"label": label, "detail": detail, "tool": "project_validation"})


def _python_files(project_dir: Path) -> list[str]:
    ignored = {"__pycache__", ".git", "node_modules", "dist", "build"}
    files: list[str] = []
    for path in sorted(project_dir.rglob("*.py")):
        if any(part in ignored for part in path.parts):
            continue
        files.append(str(path.relative_to(project_dir)).replace("\\", "/"))
    return files


def _js_files(project_dir: Path) -> list[str]:
    ignored = {"node_modules", ".git", "dist", "build"}
    files: list[str] = []
    for suffix in ("*.js", "*.mjs", "*.cjs"):
        for path in sorted(project_dir.rglob(suffix)):
            if any(part in ignored for part in path.parts):
                continue
            files.append(str(path.relative_to(project_dir)).replace("\\", "/"))
    return sorted(set(files))


def _nonempty_files_with_suffix(project_dir: Path, suffix: str) -> list[str]:
    ignored = {"__pycache__", ".git", "node_modules", "dist", "build"}
    matches: list[str] = []
    normalized_suffix = suffix.lower()
    for path in sorted(project_dir.rglob(f"*{normalized_suffix}")):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file() and path.stat().st_size > 0:
            matches.append(str(path.relative_to(project_dir)).replace("\\", "/"))
    return matches


def _valid_files_for_requested_suffix(project_dir: Path, suffix: str) -> list[str]:
    if suffix.lower() in {".md", ".markdown"}:
        return valid_markdown_files(project_dir)
    if suffix.lower() == ".pdf":
        return valid_pdf_files(project_dir)
    return _nonempty_files_with_suffix(project_dir, suffix)


def _load_package_json(project_dir: Path) -> tuple[dict[str, Any] | None, Path, str | None]:
    package_paths = sorted(project_dir.rglob("package.json"), key=lambda path: len(path.parts))
    if not package_paths:
        return None, project_dir, None
    try:
        data = json.loads(package_paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, package_paths[0].parent, f"package.json invalido: {type(exc).__name__}: {exc}"
    return data if isinstance(data, dict) else None, package_paths[0].parent, None


def _package_has_dependencies(package: dict[str, Any] | None) -> bool:
    if not isinstance(package, dict):
        return False
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = package.get(key)
        if isinstance(value, dict) and value:
            return True
    return False


def _script_is_real_test(script: str) -> bool:
    lowered = str(script or "").lower()
    return bool(script.strip()) and "no test specified" not in lowered


async def validate_project_after_vertex(
    task_id: str,
    command: str,
    bus: Any,
    *,
    vertex_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_dir = settings.WORKSPACE_PATH / task_id
    profile = detect_project_profile(project_dir)
    await bus.publish(task_id, "project_validation_started", {"project": profile})

    result_success = True
    if isinstance(vertex_result, dict):
        result_success = bool(vertex_result.get("success", True))

    checks: list[dict[str, Any]] = []
    bugs: list[str] = []
    warnings: list[str] = []

    if not result_success:
        bugs.append("Vertex terminou com erro antes de entregar um projeto valido.")

    if profile["kind"] == "empty":
        bugs.append("Vertex nao gerou arquivos no diretorio da conversa.")

    if not profile.get("has_code") and profile["kind"] != "empty":
        warnings.append("Arquivos gerados nao parecem conter codigo executavel.")

    missing_assets = missing_local_asset_refs(project_dir)
    if missing_assets:
        bugs.append("Referencias locais ausentes no HTML: " + ", ".join(missing_assets))

    report_profile = report_artifact_profile(command)
    if (web_intent_from_command(command) or report_profile.get("requires_markdown")) and not valid_markdown_files(project_dir):
        bugs.append(
            "Entrega tecnica criada pelo Vertex precisa incluir DOCUMENTACAO.md ou RELATORIO_TECNICO.md em Markdown claro, bem formatado, com H1 e conteudo suficiente."
        )

    for extension in document_extensions_from_text(command):
        matches = _valid_files_for_requested_suffix(project_dir, extension)
        if not matches:
            if extension == ".pdf":
                bugs.append("Pedido de PDF exige um arquivo .pdf valido, nao vazio e iniciado por %PDF no diretorio da conversa.")
            elif extension == ".md":
                bugs.append("Pedido de Markdown exige um arquivo .md valido, com titulo H1 e conteudo suficiente no diretorio da conversa.")
            else:
                bugs.append(
                    f"Pedido de documento/arquivo exige um arquivo {extension} nao vazio no diretorio da conversa."
                )

    timeout = float(getattr(settings, "PROJECT_VALIDATION_TIMEOUT_SECONDS", 60) or 60)

    if ".py" in set(profile.get("suffixes") or []):
        py_files = _python_files(project_dir)
        if py_files:
            await _publish_step(task_id, bus, "Validando Python", f"Compilando {len(py_files)} arquivo(s) .py.")
            check = await _run_check(["python3", "-m", "py_compile", *py_files], project_dir, timeout=timeout)
            checks.append(check)
            if not check["passed"]:
                bugs.append("Python falhou no py_compile: " + (check.get("stderr") or check.get("stdout") or "erro sem saida"))

        if (project_dir / "tests").is_dir():
            await _publish_step(task_id, bus, "Rodando testes Python", "Executando unittest discover.")
            check = await _run_check(["python3", "-m", "unittest", "discover", "-s", "tests"], project_dir, timeout=timeout)
            checks.append(check)
            if not check["passed"]:
                bugs.append("Testes Python falharam: " + (check.get("stderr") or check.get("stdout") or "erro sem saida"))

    package, package_dir, package_error = _load_package_json(project_dir)
    if package_error:
        bugs.append(package_error)
    if package:
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        has_node_modules = (package_dir / "node_modules").exists()
        deps_present = _package_has_dependencies(package)

        js_files = _js_files(project_dir)
        if js_files:
            await _publish_step(task_id, bus, "Validando JavaScript", f"Checando sintaxe de {len(js_files)} arquivo(s).")
            for rel in js_files[:20]:
                check = await _run_check(["node", "--check", rel], project_dir, timeout=min(timeout, 20))
                checks.append(check)
                if not check["passed"]:
                    bugs.append(f"JavaScript invalido em {rel}: " + (check.get("stderr") or check.get("stdout") or "erro sem saida"))
                    break

        can_run_npm_scripts = has_node_modules or not deps_present
        if scripts.get("build"):
            if can_run_npm_scripts:
                await _publish_step(task_id, bus, "Rodando build", "Executando npm run build.")
                check = await _run_check(["npm", "run", "build", "--if-present", "--silent"], package_dir, timeout=timeout)
                checks.append(check)
                if not check["passed"]:
                    bugs.append("Build Node falhou: " + (check.get("stderr") or check.get("stdout") or "erro sem saida"))
            else:
                warnings.append("Build Node nao rodou porque as dependencias ainda nao estao instaladas.")

        test_script = scripts.get("test")
        if _script_is_real_test(str(test_script or "")):
            if can_run_npm_scripts:
                await _publish_step(task_id, bus, "Rodando testes Node", "Executando npm test.")
                check = await _run_check(["npm", "test", "--if-present", "--silent"], package_dir, timeout=timeout)
                checks.append(check)
                if not check["passed"]:
                    bugs.append("Testes Node falharam: " + (check.get("stderr") or check.get("stdout") or "erro sem saida"))
            else:
                warnings.append("Testes Node nao rodaram porque as dependencias ainda nao estao instaladas.")

    status = "failed" if bugs else "passed"
    if not checks and not bugs:
        checks.append(
            {
                "command": "workspace scan",
                "returncode": 0,
                "stdout": f"{profile['file_count']} arquivo(s) encontrados.",
                "stderr": "",
                "passed": True,
            }
        )

    result = {
        "status": status,
        "requires_validation": True,
        "project": profile,
        "checks": checks[-12:],
        "bugs": bugs[:12],
        "warnings": warnings[:8],
        "reason": "A revisao automatica encontrou pontos para corrigir." if bugs else "Projeto revisado e pronto para usar.",
    }
    await bus.publish(task_id, "project_validation_result", result)
    return result
