from __future__ import annotations

import html
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from services.document_intent import (
    document_extensions_from_text,
    is_markdown_document,
    is_previewable_document,
)


EDIT_REQUEST_RE = re.compile(
    r"\b(melhore|melhorar|altere|alterar|atualize|atualizar|corrija|corrigir|"
    r"revise|revisar|adicione|adicionar|remova|remover|mude|mudar|edite|editar|"
    r"reescreva|reescrever|complete|completar|formate|formatar)\b",
    re.IGNORECASE,
)
DOCUMENT_TARGET_RE = re.compile(
    r"\b(pdf|markdown|\.md|md|arquivo|documento|relat[oó]rio|manual|guia|texto|"
    r"esse|este|essa|esta|anterior|ultimo|último)\b",
    re.IGNORECASE,
)
PROVIDED_CONTENT_RE = re.compile(
    r"\b(texto abaixo|conte[uú]do abaixo|com este texto|com o texto|a seguir|segue o texto|"
    r"use este conte[uú]do|baseado neste conte[uú]do)\b",
    re.IGNORECASE,
)


def _workspace(task_id: str) -> Path:
    return settings.WORKSPACE_PATH / task_id


def safe_document_path(task_id: str, relative_path: str) -> Path:
    base = _workspace(task_id).resolve()
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        raise ValueError("Caminho fora da conversa")
    return target


def _normalize_extension(path: str) -> str:
    extension = Path(str(path or "")).suffix.lower()
    return ".md" if extension == ".markdown" else extension


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _subject_from_text(text: str) -> str:
    value = str(text or "")
    lowered = value.lower()
    match = re.search(
        r"(?:hist[oó]ria|biografia|perfil|relat[oó]rio|guia|manual|sobre|do|da|de)\s+(?:o\s+|a\s+|os\s+|as\s+)?([^.,;:!?]{3,80})",
        value,
        flags=re.IGNORECASE,
    )
    subject = match.group(1) if match else value
    subject = re.sub(r"\.(?:md|pdf|markdown)\b", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(
        r"\b(gere|gerar|crie|criar|fa[cç]a|um|uma|arquivo|documento|pdf|markdown|md|com|em|para|sobre|hist[oó]ria)\b",
        " ",
        subject,
        flags=re.IGNORECASE,
    )
    subject = _strip_accents(subject).lower()
    words = [word for word in re.findall(r"[a-z0-9]+", subject) if len(word) >= 3]
    if not words and "corinthians" in lowered:
        words = ["historia", "corinthians"]
    return "_".join(words[:7]) or "documento"


def artifact_profile(text: str) -> dict[str, Any]:
    requested_extensions = document_extensions_from_text(text)
    wants_markdown = ".md" in requested_extensions
    wants_pdf = ".pdf" in requested_extensions
    explicit = wants_markdown or wants_pdf
    edit_requested = bool(EDIT_REQUEST_RE.search(str(text or "")) and DOCUMENT_TARGET_RE.search(str(text or "")))
    slug = _subject_from_text(text)
    return {
        "requested_extensions": requested_extensions,
        "wants_markdown": wants_markdown,
        "wants_pdf": wants_pdf,
        "explicit_document": explicit,
        "edit_requested": edit_requested,
        "requires_artifact": explicit,
        "preferred_markdown": f"{slug}.md",
        "preferred_pdf": f"{slug}.pdf",
        "subject": slug.replace("_", " "),
    }


def document_has_provided_content(text: str) -> bool:
    value = str(text or "")
    return bool(PROVIDED_CONTENT_RE.search(value)) or len(value) >= 1200


def is_document_edit_request(text: str) -> bool:
    return bool(artifact_profile(text).get("edit_requested"))


def resolve_document_target(task_id: str, text: str, files: list[dict[str, Any]]) -> dict[str, Any] | None:
    profile = artifact_profile(text)
    requested = set(profile.get("requested_extensions") or [])
    candidates = [
        file
        for file in files
        if is_previewable_document(str(file.get("path") or "")) and not str(file.get("path") or "").startswith("versions/")
    ]
    if requested:
        candidates = [
            file
            for file in candidates
            if _normalize_extension(str(file.get("path") or "")) in requested
        ] or candidates
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda file: (float(file.get("modified_at") or 0), str(file.get("updated_at") or ""), str(file.get("path") or "")),
        reverse=True,
    )[0]


def archive_existing_document(task_id: str, relative_path: str) -> str | None:
    target = safe_document_path(task_id, relative_path)
    if not target.is_file():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = safe_document_path(task_id, "versions")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{target.stem}_{timestamp}{target.suffix}"
    backup = backup_dir / backup_name
    shutil.copy2(target, backup)
    return str(backup.relative_to(_workspace(task_id))).replace("\\", "/")


def archive_edit_targets(task_id: str, text: str, files: list[dict[str, Any]]) -> list[str]:
    if not is_document_edit_request(text):
        return []
    target = resolve_document_target(task_id, text, files)
    if not target:
        return []
    archived = archive_existing_document(task_id, str(target.get("path") or ""))
    return [archived] if archived else []


def markdown_file_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 80:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r"^\s{0,3}#\s+\S+", text, flags=re.MULTILINE)) and len(text.strip()) >= 80


def pdf_file_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 128:
        return False
    try:
        return path.read_bytes()[:4] == b"%PDF"
    except OSError:
        return False


def valid_markdown_files(project_dir: Path) -> list[str]:
    matches: list[str] = []
    for suffix in ("*.md", "*.markdown"):
        for path in sorted(project_dir.rglob(suffix)):
            if any(part in {"node_modules", ".git", "dist", "build", "__pycache__", "versions"} for part in path.parts):
                continue
            if markdown_file_valid(path):
                matches.append(str(path.relative_to(project_dir)).replace("\\", "/"))
    return sorted(set(matches))


def valid_pdf_files(project_dir: Path) -> list[str]:
    matches: list[str] = []
    for path in sorted(project_dir.rglob("*.pdf")):
        if any(part in {"node_modules", ".git", "dist", "build", "__pycache__", "versions"} for part in path.parts):
            continue
        if pdf_file_valid(path):
            matches.append(str(path.relative_to(project_dir)).replace("\\", "/"))
    return matches


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_to_html(markdown: str, *, title: str = "Documento") -> str:
    body: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    for raw_line in str(markdown or "").splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            close_list()
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            close_list()
            level = min(len(heading.group(1)), 4)
            body.append(f"<h{level}>{_inline_markdown(heading.group(2).strip())}</h{level}>")
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_markdown(bullet.group(1).strip())}</li>")
            continue
        close_list()
        body.append(f"<p>{_inline_markdown(line.strip())}</p>")
    close_list()
    if in_code:
        body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    @page {{ margin: 22mm 18mm; }}
    body {{ color: #16181d; font-family: Inter, Arial, sans-serif; font-size: 12.5px; line-height: 1.58; }}
    h1 {{ font-size: 30px; line-height: 1.12; margin: 0 0 20px; }}
    h2 {{ font-size: 20px; margin: 26px 0 10px; }}
    h3 {{ font-size: 15px; margin: 20px 0 8px; }}
    h4 {{ font-size: 13px; margin: 16px 0 6px; }}
    p {{ margin: 0 0 10px; }}
    ul {{ margin: 0 0 12px 18px; padding: 0; }}
    li {{ margin: 0 0 6px; }}
    code {{ background: #eef1f5; border-radius: 4px; padding: 1px 4px; }}
    pre {{ background: #111827; color: #f8fafc; border-radius: 8px; padding: 12px; white-space: pre-wrap; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
    th, td {{ border: 1px solid #d7dde5; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; }}
  </style>
</head>
<body>
  {''.join(body)}
</body>
</html>"""


async def render_markdown_to_pdf(task_id: str, markdown_path: str, pdf_path: str) -> dict[str, Any]:
    source = safe_document_path(task_id, markdown_path)
    target = safe_document_path(task_id, pdf_path)
    if not markdown_file_valid(source):
        return {"success": False, "error": "Markdown fonte ausente, vazio ou sem titulo H1."}
    target.parent.mkdir(parents=True, exist_ok=True)
    markdown = source.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"^\s{0,3}#\s+(.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(markdown_path).stem
    page_html = markdown_to_html(markdown, title=title)

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        chrome_binary = Path(settings.CHROME_BINARY)
        if chrome_binary.exists():
            launch_kwargs["executable_path"] = str(chrome_binary)
        browser = await chromium.launch(**launch_kwargs)
        try:
            page = await browser.new_page()
            await page.set_content(page_html, wait_until="load")
            await page.pdf(
                path=str(target),
                format="A4",
                print_background=True,
                margin={"top": "18mm", "right": "16mm", "bottom": "18mm", "left": "16mm"},
            )
        finally:
            await browser.close()

    if not pdf_file_valid(target):
        return {"success": False, "error": "PDF renderizado parece invalido."}
    return {"success": True, "path": str(target.relative_to(_workspace(task_id))).replace("\\", "/")}


def preferred_markdown_for_pdf(task_id: str, pdf_path: str | None = None) -> str | None:
    base = _workspace(task_id)
    candidates = valid_markdown_files(base)
    if not candidates:
        return None
    if pdf_path:
        stem = Path(pdf_path).stem.lower()
        same_stem = [path for path in candidates if Path(path).stem.lower() == stem]
        if same_stem:
            return same_stem[0]
    return candidates[0]


def document_context_for_code_agent(task_id: str, prompt: str, files: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    quality_sources = [s for s in sources if int(s.get("quality_score") or 0) >= 50]
    relevant_sources = []
    for source in quality_sources[:3]:
        title = str(source.get("title") or source.get("url") or "").strip()
        url = str(source.get("url") or "").strip()
        text = str(source.get("extracted_text") or source.get("snippet") or "").strip()
        if not title and not url:
            continue
        relevant_sources.append(
            f"- [{source.get('source_type') or 'web'} {int(source.get('quality_score') or 0)}/100] {title}: {url}"
            + (f"\n  Trecho: {text[:300]}" if text else "")
        )
    if relevant_sources:
        sections.append("FONTES_PESQUISADAS:\n" + "\n".join(relevant_sources))

    docs = [
        file
        for file in files
        if is_previewable_document(str(file.get("path") or "")) and not str(file.get("path") or "").startswith("versions/")
    ]
    if docs:
        lines = [f"- {file.get('path')} ({file.get('extension') or Path(str(file.get('path') or '')).suffix}, {int(file.get('size_bytes') or 0)} bytes)" for file in docs[:5]]
        target = resolve_document_target(task_id, prompt, docs) if is_document_edit_request(prompt) else None
        if target:
            lines.insert(0, f"ALVO_DA_EDICAO: {target.get('path')}")
        sections.append("ARQUIVOS_DA_CONVERSA:\n" + "\n".join(lines))

    return "\n\n".join(sections)
