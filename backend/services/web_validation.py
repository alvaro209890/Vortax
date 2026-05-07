import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from config import settings
from services.project_files import missing_local_asset_refs
from tools.browser import browser_tool
from tools.vision import vision_configured, vision_tool


WEB_INTENT_RE = re.compile(
    r"\b(site|frontend|front-end|pagina|p[aá]gina|landing|html|css|react|vite|vue|next|nuxt|dashboard|interface)\b",
    re.IGNORECASE,
)
BUG_RE = re.compile(
    r"\b(bug|erro|falha|quebrad[ao]|sobrepost[ao]s?|cortad[ao]|ileg[ií]vel|vazio|blank|desalinhad[ao]|"
    r"overflow|fora da tela|n[aã]o aparece|n[aã]o carrega|corrigir|problema)\b",
    re.IGNORECASE,
)
NO_BUG_RE = re.compile(
    r"\b(sem bugs?|sem erros?|sem falhas?|sem problemas?|nenhum bug|nenhum erro|nenhuma falha|nenhum problema|"
    r"n[aã]o h[aá] bugs?|n[aã]o h[aá] erros?|n[aã]o identifiquei|n[aã]o detectei|nada quebrado|"
    r"tudo parece|layout consistente)\b",
    re.IGNORECASE,
)
LOCAL_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}(?:/[^\s\"'<>)]*)?", re.IGNORECASE)


def _iter_project_files(project_dir: Path) -> list[Path]:
    if not project_dir.exists():
        return []
    ignored = {"node_modules", ".git", "dist", "build", "__pycache__"}
    files: list[Path] = []
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored for part in path.parts):
            continue
        files.append(path)
    return files


def _safe_rel(path: Path, project_dir: Path) -> str:
    return str(path.relative_to(project_dir)).replace("\\", "/")


def web_intent_from_command(command: str) -> bool:
    return bool(WEB_INTENT_RE.search(str(command or "")))


def local_url_from_text(text: str) -> str | None:
    match = LOCAL_URL_RE.search(str(text or ""))
    if not match:
        return None
    url = match.group(0).rstrip(".,;")
    return url.replace("://0.0.0.0:", "://127.0.0.1:")


def local_url_from_shell_result(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    urls = result.get("local_urls")
    if isinstance(urls, list):
        for item in urls:
            found = local_url_from_text(str(item))
            if found:
                return found
    for key in ("stdout", "stderr"):
        found = local_url_from_text(str(result.get(key) or ""))
        if found:
            return found
    return None


def detect_web_project(project_dir: Path, *, force: bool = False) -> dict[str, Any]:
    files = _iter_project_files(project_dir)
    package_files = [path for path in files if path.name == "package.json"]
    index_files = [path for path in files if path.name == "index.html"]

    for package_path in package_files:
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else {}
        if isinstance(scripts, dict) and scripts.get("dev"):
            return {
                "type": "node_dev_server",
                "package_dir": _safe_rel(package_path.parent, project_dir),
                "package_json": _safe_rel(package_path, project_dir),
                "command": "npm run dev" if package_path.parent == project_dir else f"cd {_safe_rel(package_path.parent, project_dir)} && npm run dev",
                "install_command": (
                    "npm install --no-audit --no-fund"
                    if package_path.parent == project_dir
                    else f"cd {_safe_rel(package_path.parent, project_dir)} && npm install --no-audit --no-fund"
                ),
            }

    if index_files:
        index_path = sorted(index_files, key=lambda path: len(path.parts))[0]
        rel = _safe_rel(index_path, project_dir)
        preview_path = "" if rel == "index.html" else rel
        preview_url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{{task_id}}/"
        if preview_path:
            preview_url += quote(preview_path)
        return {
            "type": "static_html",
            "index_html": rel,
            "url_template": preview_url,
        }

    return {
        "type": "missing" if force else "none",
        "reason": "Nenhum index.html ou package.json com script dev foi encontrado.",
    }


def _vision_result_text(result: dict[str, Any]) -> str:
    parts = [
        result.get("summary"),
        result.get("visible_text"),
        result.get("suggested_action"),
        " ".join(str(item) for item in result.get("ui_elements") or []),
        " ".join(str(item) for item in result.get("objects") or []),
    ]
    return " ".join(str(part or "") for part in parts)


def _vision_found_bug(result: dict[str, Any]) -> bool:
    text = _vision_result_text(result)
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|[\n\r]+|,?\s+(?:mas|por[eé]m|contudo|entretanto)\s+", text, flags=re.IGNORECASE)
        if part.strip()
    ]
    if sentences:
        bug_sentences = [sentence for sentence in sentences if BUG_RE.search(sentence)]
        if bug_sentences:
            return any(not NO_BUG_RE.search(sentence) for sentence in bug_sentences)
    if NO_BUG_RE.search(text):
        return False
    return bool(BUG_RE.search(text))


async def _publish_step(task_id: str, bus: Any, label: str, detail: str = "", **extra: Any) -> None:
    await bus.publish(task_id, "web_validation_step", {"label": label, "detail": detail, **extra})
    await bus.publish(task_id, "agent_progress", {"label": label, "detail": detail, "tool": "web_validation"})


async def _capture_and_analyze(task_id: str, bus: Any, viewport_index: int) -> dict[str, Any]:
    frame = await browser_tool.screenshot(task_id=task_id)
    await bus.publish(
        task_id,
        "screen_frame",
        {
            "caption": f"Revisao visual - viewport {viewport_index}",
            "title": frame.get("title"),
            "url": frame.get("url"),
            "image_base64": frame.get("image_base64"),
        },
    )
    question = (
        "Analise esta captura do site criado pelo Vertex como revisor de frontend. "
        "Procure bugs visuais ou funcionais aparentes: pagina em branco, erros visiveis, elementos sobrepostos, "
        "texto cortado, layout quebrado, conteudo fora da tela, contraste ruim, botoes ilegíveis ou estado incompleto. "
        "Responda no JSON esperado pelo sistema; se houver bug, descreva exatamente o que corrigir em suggested_action. "
        "Se nao houver bug aparente nesta viewport, diga claramente que nao ha bugs aparentes."
    )
    vision = await vision_tool.analyze(
        image_base64=frame.get("image_base64"),
        question=question,
        task_id=task_id,
    )
    return {
        "viewport": viewport_index,
        "url": frame.get("url"),
        "title": frame.get("title"),
        "vision": vision,
        "has_bug": _vision_found_bug(vision),
    }


async def _scroll_state() -> dict[str, Any]:
    return await browser_tool.get_scroll_state()


async def validate_web_project_after_vertex(
    task_id: str,
    command: str,
    bus: Any,
    *,
    vertex_result: dict[str, Any] | None = None,
    max_viewports: int = 8,
) -> dict[str, Any]:
    project_dir = settings.WORKSPACE_PATH / task_id
    force = web_intent_from_command(command)
    detected = detect_web_project(project_dir, force=force)

    if detected["type"] == "none":
        return {"status": "skipped", "requires_validation": False, "reason": detected["reason"], "project": detected}

    await bus.publish(task_id, "web_validation_started", {"project": detected, "forced": force})

    if detected["type"] == "missing":
        result = {
            "status": "failed",
            "requires_validation": True,
            "reason": detected["reason"],
            "bugs": [detected["reason"]],
            "project": detected,
        }
        await bus.publish(task_id, "web_validation_result", result)
        return result

    missing_assets = missing_local_asset_refs(project_dir)
    if missing_assets:
        detail = "Arquivos locais referenciados pelo index.html nao foram encontrados: " + ", ".join(missing_assets)
        result = {
            "status": "failed",
            "requires_validation": True,
            "reason": detail,
            "bugs": [
                detail,
                "Crie os arquivos ausentes ou remova as referencias quebradas antes de revisar o preview.",
            ],
            "project": detected,
            "missing_assets": missing_assets,
        }
        await bus.publish(task_id, "web_validation_result", result)
        return result

    if not vision_configured():
        result = {
            "status": "blocked",
            "requires_validation": False,
            "reason": "Revisao visual obrigatoria indisponivel. Defina ENABLE_VISION_TESTS=true e GROQ_API_KEY.",
            "project": detected,
        }
        await bus.publish(task_id, "web_validation_result", result)
        return result

    internal_server_started = False
    try:
        if detected["type"] == "static_html":
            url = str(detected["url_template"]).format(task_id=quote(task_id))
            await _publish_step(task_id, bus, "Abrindo preview estatico", "Preview interno do Vortax para revisao visual.")
        elif detected["type"] == "node_dev_server":
            from tools.shell import run_shell

            await _publish_step(
                task_id,
                bus,
                "Subindo preview interno",
                "Servidor temporario usado apenas para revisar o projeto; ele sera fechado antes da entrega.",
            )
            server_result = await run_shell(str(detected.get("command") or "npm run dev"), task_id=task_id, bus=bus)
            server_data = server_result.get("data", server_result) if isinstance(server_result, dict) else {}
            url = local_url_from_shell_result(server_data)
            internal_server_started = bool(server_data.get("success") and server_data.get("is_dev_server"))
            if not url or not server_data.get("success"):
                detail = str(server_data.get("stderr") or server_data.get("stdout") or "Nao foi possivel iniciar o preview interno.")
                result = {
                    "status": "failed",
                    "requires_validation": True,
                    "reason": "Nao foi possivel iniciar o preview interno para revisar o site.",
                    "bugs": [detail[:500]],
                    "project": detected,
                }
                await bus.publish(task_id, "web_validation_result", result)
                return result
        else:
            result = {
                "status": "failed",
                "requires_validation": True,
                "reason": "Nao foi possivel abrir um preview interno para o Vortax testar.",
                "bugs": [
                    "Crie um index.html estatico funcional ou configure um script dev que o Vortax consiga iniciar temporariamente para revisao interna."
                ],
                "project": detected,
            }
            await bus.publish(task_id, "web_validation_result", result)
            return result

        await _publish_step(task_id, bus, "Abrindo site no Chrome", "Preview interno para revisao visual.")
        await browser_tool.navigate(url, task_id=task_id)
        await browser_tool.scroll_to_top(task_id=task_id)

        analyses: list[dict[str, Any]] = []
        bugs: list[str] = []
        await _publish_step(task_id, bus, "Testando funcionalidades do frontend", "Clicando controles, preenchendo campos e observando erros.")
        smoke = await browser_tool.frontend_smoke_test(task_id=task_id)
        if not smoke.get("success"):
            bugs.append(
                "Smoke test do frontend encontrou erro: "
                + "; ".join(str(item) for item in smoke.get("errors", [])[:5])
                + ("; texto de erro visivel na pagina" if smoke.get("visible_error") else "")
            )
        await browser_tool.scroll_to_top(task_id=task_id)
        seen_positions: set[int] = set()

        for viewport_index in range(1, max_viewports + 1):
            state = await _scroll_state()
            y = int(state.get("scroll_y") or 0)
            if y in seen_positions and viewport_index > 1:
                break
            seen_positions.add(y)

            await _publish_step(task_id, bus, f"Analisando viewport {viewport_index}", "Revisando a tela renderizada.")
            analysis = await _capture_and_analyze(task_id, bus, viewport_index)
            analyses.append(analysis)
            if analysis["has_bug"]:
                vision = analysis["vision"]
                bugs.append(str(vision.get("suggested_action") or vision.get("summary") or "Bug visual detectado."))

            state = await _scroll_state()
            if bool(state.get("at_bottom")):
                break
            await _publish_step(task_id, bus, "Rolando pagina", "Testando a proxima parte da pagina.")
            await browser_tool.scroll(direction="down", amount=int(state.get("viewport_height") or 700), task_id=task_id)

        await browser_tool.scroll_to_top(task_id=task_id)

        status = "failed" if bugs else "passed"
        result = {
            "status": status,
            "requires_validation": True,
            "url": url,
            "project": detected,
            "viewports_checked": len(analyses),
            "bugs": bugs,
            "frontend_smoke_test": smoke,
            "analyses": [
                {
                    "viewport": item["viewport"],
                    "has_bug": item["has_bug"],
                    "summary": item["vision"].get("summary"),
                    "suggested_action": item["vision"].get("suggested_action"),
                    "confidence": item["vision"].get("confidence"),
                }
                for item in analyses
            ],
        }
        await bus.publish(task_id, "web_validation_result", result)
        return result
    except Exception as exc:
        result = {
            "status": "failed",
            "requires_validation": True,
            "reason": f"{type(exc).__name__}: {exc}",
            "bugs": [f"Falha ao executar revisao visual: {type(exc).__name__}: {exc}"],
            "project": detected,
        }
        await bus.publish(task_id, "web_validation_result", result)
        return result
    finally:
        if internal_server_started:
            from tools.shell import stop_dev_server

            stopped = await stop_dev_server(task_id)
            if stopped:
                await _publish_step(
                    task_id,
                    bus,
                    "Preview interno encerrado",
                    "Servidor temporario do projeto fechado apos a revisao.",
                )
