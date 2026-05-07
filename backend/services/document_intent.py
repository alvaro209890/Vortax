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
    "planilha": ".xlsx",
    "json": ".json",
    "pptx": ".pptx",
    "powerpoint": ".pptx",
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


def _normalize_extension(value: str) -> str | None:
    lowered = value.lower().lstrip(".")
    extension = _EXTENSION_ALIASES.get(lowered)
    if extension == ".markdown":
        return ".md"
    return extension if extension in DOCUMENT_EXTENSIONS else None


def document_extensions_from_text(text: str) -> list[str]:
    """Return requested final-file extensions mentioned by the user/Vertex prompt."""
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


def is_markdown_document(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in {".md", ".markdown"}


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
