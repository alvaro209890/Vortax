from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from config import settings
from services.registry import task_store

router = APIRouter()


def safe_task_workspace_path(task_id: str, relative_path: str = "") -> Path:
    base = (settings.WORKSPACE_PATH / task_id).resolve()
    workspace = settings.WORKSPACE_PATH.resolve()
    if base != workspace and workspace not in base.parents:
        raise HTTPException(status_code=400, detail="Conversa fora da workspace")
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=400, detail="Caminho fora da conversa")
    return target


def list_task_workspace_files(task_id: str) -> list[dict]:
    base = safe_task_workspace_path(task_id)
    if not base.exists() or not base.is_dir():
        return []

    files = []
    for path in base.rglob("*"):
        if path.is_file() and path.name != ".gitkeep":
            files.append(
                {
                    "path": str(path.relative_to(base)),
                    "size_bytes": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )
    return sorted(files, key=lambda item: item["path"])


@router.get("/task/{task_id}")
async def list_task_files(task_id: str) -> dict:
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    return {"files": list_task_workspace_files(task_id)}


@router.get("/task/{task_id}/{file_path:path}")
async def download_task_file(task_id: str, file_path: str) -> FileResponse:
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    target = safe_task_workspace_path(task_id, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(target)


@router.get("/")
async def list_files() -> dict:
    raise HTTPException(status_code=400, detail="Informe uma conversa: /api/files/task/{task_id}")


@router.get("/{file_path:path}")
async def download_file(file_path: str) -> FileResponse:
    raise HTTPException(status_code=400, detail="Use /api/files/task/{task_id}/{file_path}")


# ── Preview de projetos web gerados ────────────────────────────────────────

@router.get("/preview/{task_id}/{file_path:path}")
async def preview_task_file(task_id: str, file_path: str):
    """Serve arquivos estaticos da workspace para preview em iframe."""
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    target = safe_task_workspace_path(task_id, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(target)


@router.get("/preview/{task_id}/")
async def preview_task_index(task_id: str):
    """Serve o index.html padrao para preview do projeto web."""
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    base = safe_task_workspace_path(task_id)
    index_path = base / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Nenhum index.html encontrado para preview")
    return FileResponse(index_path)


@router.get("/preview-dev/{task_id}")
async def check_dev_server(task_id: str) -> dict:
    """Verifica se ha um dev server rodando para esta conversa."""
    from tools.shell import get_dev_server

    server = get_dev_server(task_id)
    if not server:
        return {"running": False}
    return {"running": True, "url": server["url"], "port": server["port"]}


@router.delete("/preview-dev/{task_id}")
async def stop_dev_server_endpoint(task_id: str) -> dict:
    """Para o dev server de uma conversa."""
    from tools.shell import stop_dev_server

    stopped = await stop_dev_server(task_id)
    return {"ok": stopped}
