from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from database import database
from services.stream_contract import utc_now


IGNORED_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}
LOCAL_ASSET_REF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def _file_type_for(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if name == "package.json":
        return "package"
    if name == "index.html":
        return "entry"
    if suffix in {".html", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue"}:
        return "source"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico"}:
        return "asset"
    if suffix in {".md", ".txt", ".json"}:
        return "document"
    return "file"


def _project_type(files: list[dict[str, Any]]) -> str:
    paths = {str(file["path"]) for file in files}
    suffixes = {str(file.get("extension") or "") for file in files}
    if any(path.endswith("package.json") for path in paths):
        if {".jsx", ".tsx"} & suffixes:
            return "react_app"
        if {".vue"} & suffixes:
            return "vue_app"
        return "node_app"
    if any(path.endswith("index.html") for path in paths):
        return "static_web"
    if ".py" in suffixes:
        return "python"
    return "generic"


def _project_name(root_path: str, project_type: str) -> str:
    if not root_path:
        return "Projeto principal"
    name = Path(root_path).name.replace("_", " ").replace("-", " ").strip()
    if not name:
        return "Projeto principal"
    return name.title()


def _candidate_roots(files: list[dict[str, Any]]) -> list[str]:
    roots = set()
    for file in files:
        path = Path(str(file["path"]))
        if path.name in {"package.json", "index.html"}:
            parent = str(path.parent).replace("\\", "/")
            roots.add("" if parent == "." else parent)
    normalized = {root.strip("/") for root in roots}
    normalized.discard("")
    if not normalized:
        return [""]
    return sorted(normalized, key=lambda item: (item.count("/"), item))


def _root_for_file(path: str, roots: list[str]) -> str:
    matches = [root for root in roots if not root or path == root or path.startswith(f"{root}/")]
    if not matches:
        return roots[0] if roots else ""
    return sorted(matches, key=len, reverse=True)[0]


def scan_task_workspace(project_dir: Path) -> list[dict[str, Any]]:
    if not project_dir.exists() or not project_dir.is_dir():
        return []

    files: list[dict[str, Any]] = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.name == ".gitkeep":
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(project_dir)).replace("\\", "/")
        stat = path.stat()
        files.append(
            {
                "path": rel,
                "size": stat.st_size,
                "size_bytes": stat.st_size,
                "extension": path.suffix.lower(),
                "modified_at": stat.st_mtime,
                "file_type": _file_type_for(rel),
            }
        )
    return files


def _is_local_asset_ref(ref: str) -> bool:
    value = ref.strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith(("#", "http://", "https://", "//", "data:", "mailto:", "tel:", "javascript:")):
        return False
    parsed = urlparse(value)
    return not parsed.scheme and not parsed.netloc


def missing_local_asset_refs(project_dir: Path) -> list[str]:
    """Return local href/src references from index.html files that do not exist."""
    if not project_dir.exists() or not project_dir.is_dir():
        return []

    missing: set[str] = set()
    for index_path in sorted(project_dir.rglob("index.html")):
        if any(part in IGNORED_DIRS for part in index_path.parts):
            continue
        try:
            html = index_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in LOCAL_ASSET_REF_RE.finditer(html):
            raw_ref = match.group(1).strip()
            if not _is_local_asset_ref(raw_ref):
                continue
            ref_path = raw_ref.split("?", 1)[0].split("#", 1)[0].strip("/")
            if not ref_path:
                continue
            candidate = (index_path.parent / ref_path).resolve()
            try:
                candidate.relative_to(project_dir.resolve())
            except ValueError:
                continue
            if not candidate.exists():
                rel = str(candidate.relative_to(project_dir.resolve())).replace("\\", "/")
                missing.add(rel)
    return sorted(missing)


def build_project_index(task_id: str, raw_files: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    now = utc_now()
    roots = _candidate_roots(raw_files)
    files_by_root: dict[str, list[dict[str, Any]]] = {root: [] for root in roots}

    for file in raw_files:
        path = str(file["path"])
        root = _root_for_file(path, roots)
        files_by_root.setdefault(root, []).append(file)

    projects: list[dict[str, Any]] = []
    indexed_files: list[dict[str, Any]] = []
    for root, project_files in sorted(files_by_root.items(), key=lambda item: item[0]):
        if not project_files:
            continue
        project_id = f"{task_id}:{root or '__root__'}"
        project_type = _project_type(project_files)
        main_file = next((file["path"] for file in project_files if Path(str(file["path"])).name == "index.html"), None)
        if main_file is None:
            main_file = next((file["path"] for file in project_files if Path(str(file["path"])).name == "package.json"), None)
        project = {
            "id": project_id,
            "task_id": task_id,
            "root_path": root,
            "name": _project_name(root, project_type),
            "project_type": project_type,
            "main_file": main_file,
            "file_count": len(project_files),
            "total_size": sum(int(file.get("size_bytes", file.get("size", 0))) for file in project_files),
            "created_at": now,
            "updated_at": now,
        }
        projects.append(project)
        for file in project_files:
            indexed_files.append(
                {
                    **file,
                    "task_id": task_id,
                    "project_id": project_id,
                    "project_name": project["name"],
                    "project_root": root,
                    "project_type": project_type,
                    "created_at": now,
                    "updated_at": now,
                }
            )

    return {"projects": projects, "files": sorted(indexed_files, key=lambda item: item["path"])}


def sync_task_workspace_files(task_id: str, project_dir: Path) -> dict[str, list[dict[str, Any]]]:
    index = build_project_index(task_id, scan_task_workspace(project_dir))
    if database.get_task(task_id) is None:
        return index
    database.sync_generated_projects(task_id, index["projects"], index["files"])
    return {
        "projects": database.list_generated_projects(task_id),
        "files": database.list_generated_files(task_id),
    }
