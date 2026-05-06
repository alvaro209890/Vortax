from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import settings

router = APIRouter()


def safe_workspace_path(relative_path: str) -> Path:
    base = settings.WORKSPACE_PATH.resolve()
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=400, detail="Caminho fora da workspace")
    return target


@router.get("/")
async def list_files() -> dict:
    files = []
    base = settings.WORKSPACE_PATH.resolve()
    for path in base.rglob("*"):
        if path.is_file() and path.name != ".gitkeep":
            files.append(
                {
                    "path": str(path.relative_to(base)),
                    "size_bytes": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )
    return {"files": files}


@router.get("/{file_path:path}")
async def download_file(file_path: str) -> FileResponse:
    target = safe_workspace_path(file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(target)
