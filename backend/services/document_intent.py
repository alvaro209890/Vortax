import re
from pathlib import Path
from typing import Any


DOCUMENT_EXTENSIONS = (".md", ".pdf", ".txt", ".docx", ".csv", ".xlsx", ".json", ".pptx")

_EXTENSION_ALIASES = {
    "markdown": ".md",
    "md": ".md",
    "pdf": ".pdf",
    "txt": ".txt",
    "texto": ".txt",
    "docx": ".docx",
    "word": ".docx",
    "csv": ".csv",
    "xlsx": ".xlsx",
    "excel": ".xlsx",
    "exel": ".xlsx",
    "planilha": ".xlsx",
    "json": ".json",
    "pptx": ".pptx",
    "powerpoint": ".pptx",
    "slides": ".pptx",
    "slide": ".pptx",
    "apresentacao": ".pptx",
    "apresentação": ".pptx",
}

_EXPLICIT_EXTENSION_RE = re.compile(
    r"(?<![\w/-])\.(md|markdown|pdf|txt|docx|csv|xlsx|json|pptx)\b",
    re.IGNORECASE,
)
_DOCUMENT_REQUEST_RE = re.compile(
    r"\b(arquivo|documento|documenta[cç][aã]o|relat[oó]rio|manual|guia|planilha|apresenta[cç][aã]o|"
    r"gere|gerar|crie|criar|fa[cç]a|exporte|baixar|download)\b",
    re.IGNORECASE,
)
_SOFTWARE_REPORT_RE = re.compile(
    r"\b(site|pagina|p[aá]gina|landing|frontend|backend|fullstack|api|app|aplicativo|"
    r"software|sistema|dashboard|script|codigo|c[oó]digo|repositorio|reposit[oó]rio|"
    r"projeto|arquitetura|componente|banco\s+de\s+dados|database)\b",
    re.IGNORECASE,
)
_TECHNICAL_REPORT_RE = re.compile(
    r"\b(analis(?:e|ar|ando)|auditor(?:ia|ar)|rev(?:ise|isar|isao|isão)|"
    r"diagn[oó]stico|relat[oó]rio|documenta[cç][aã]o|explica[cç][aã]o\s+t[eé]cnica|"
    r"map(?:ear|eamento)|arquitetura|fluxo|estrutura|depend[eê]ncias|vulnerabilidade|"
    r"performance|qualidade\s+do\s+c[oó]digo|code\s+review)\b",
    re.IGNORECASE,
)
_CREATE_SOFTWARE_RE = re.compile(
    r"\b(crie|criar|gere|gerar|desenvolva|implemente|construa|fa[cç]a|corrija|"
    r"bug|erro|falha)\b",
    re.IGNORECASE,
)


def _normalize_extension(value: str) -> str | None:
    lowered = value.lower().lstrip(".")
    extension = _EXTENSION_ALIASES.get(lowered)
    if extension == ".markdown":
        return ".md"
    return extension if extension in DOCUMENT_EXTENSIONS else None


def document_extensions_from_text(text: str) -> list[str]:
    """Return requested final-file extensions mentioned by the user/code-agent prompt."""
    value = str(text or "")
    found: list[str] = []

    for match in _EXPLICIT_EXTENSION_RE.finditer(value):
        extension = _normalize_extension(match.group(1))
        if extension and extension not in found:
            found.append(extension)

    lowered = value.lower()
    has_document_request = bool(_DOCUMENT_REQUEST_RE.search(lowered))
    for alias, extension in _EXTENSION_ALIASES.items():
        if extension in found:
            continue
        if not re.search(rf"\b{re.escape(alias)}\b", lowered, re.IGNORECASE):
            continue
        if extension in {".pdf", ".csv", ".xlsx", ".docx", ".pptx"} or has_document_request:
            found.append(extension)

    return found


def document_intent_from_text(text: str) -> bool:
    return bool(document_extensions_from_text(text))


def report_artifact_profile(text: str) -> dict[str, Any]:
    """Return whether a task should produce a previewable report artifact."""
    value = str(text or "")
    lowered = value.lower()
    requested_extensions = document_extensions_from_text(value)
    wants_markdown = ".md" in requested_extensions or bool(re.search(r"\b(markdown|documenta[cç][aã]o)\b", lowered))
    wants_pdf = ".pdf" in requested_extensions
    software_context = bool(_SOFTWARE_REPORT_RE.search(value))
    technical_context = bool(_TECHNICAL_REPORT_RE.search(value))
    creation_context = bool(_CREATE_SOFTWARE_RE.search(value)) and software_context
    analysis_context = technical_context and software_context
    should_generate_markdown = wants_markdown or wants_pdf or creation_context or analysis_context

    if wants_markdown:
        reason = "requested_markdown"
    elif analysis_context:
        reason = "technical_analysis"
    elif creation_context:
        reason = "software_documentation"
    elif wants_pdf:
        reason = "requested_pdf"
    else:
        reason = "none"

    if creation_context and not analysis_context:
        preferred_filename = "DOCUMENTACAO.md"
    elif wants_pdf:
        preferred_filename = "DOCUMENTO_FONTE.md"
    else:
        preferred_filename = "RELATORIO_TECNICO.md"
    return {
        "should_generate_markdown": should_generate_markdown,
        "requires_markdown": should_generate_markdown,
        "wants_pdf": wants_pdf,
        "wants_markdown": wants_markdown,
        "is_technical": technical_context or software_context,
        "is_software": software_context,
        "is_analysis": analysis_context,
        "reason": reason,
        "preferred_filename": preferred_filename,
        "requested_extensions": requested_extensions,
    }


def is_markdown_document(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in {".md", ".markdown"}


def is_previewable_document(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in {".md", ".markdown", ".pdf"}


def file_is_nonempty(file: dict[str, Any]) -> bool:
    size = file.get("size_bytes", file.get("size", 0))
    try:
        return int(size or 0) > 0
    except (TypeError, ValueError):
        return False


def markdown_documentation_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs = [
        file
        for file in files
        if is_markdown_document(str(file.get("path") or "")) and file_is_nonempty(file)
    ]
    preferred_names = ("documentacao", "documentação", "readme", "docs", "guia", "manual")

    def sort_key(file: dict[str, Any]) -> tuple[int, int, str]:
        path = str(file.get("path") or "")
        name = Path(path).stem.lower()
        preferred = 0 if any(token in name for token in preferred_names) else 1
        return (preferred, path.count("/"), path)

    return sorted(docs, key=sort_key)


def downloadable_document_files(
    files: list[dict[str, Any]],
    requested_extensions: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    requested = set(requested_extensions)
    candidates = []
    for file in files:
        path = str(file.get("path") or "")
        extension = Path(path).suffix.lower()
        if extension == ".markdown":
            extension = ".md"
        if extension not in DOCUMENT_EXTENSIONS or not file_is_nonempty(file):
            continue
        if requested and extension not in requested:
            continue
        candidates.append(file)

    def sort_key(file: dict[str, Any]) -> tuple[int, int, str]:
        path = str(file.get("path") or "")
        extension = Path(path).suffix.lower()
        requested_rank = 0 if extension in requested else 1
        doc_rank = 0 if is_markdown_document(path) and "documenta" in Path(path).stem.lower() else 1
        return (requested_rank, doc_rank, path.count("/"), path)

    return sorted(candidates, key=sort_key)
