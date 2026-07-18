"""Export/replay auditável de uma sessão Vortax.

Pacote ZIP:
  manifest.json
  task.json
  plan.json
  events.jsonl
  sources.json
  context.json
  metrics.json
  files/…          (workspace)
  screenshots/…    (metadados + opcional base64 truncado)
  chat_images/…    (metadados)
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from config import settings
from database import database
from services.metrics import metrics
from services.stream_contract import utc_now
from services.task_plan_store import task_plan_store


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)[:120]


def build_session_export_zip(
    task_id: str,
    *,
    include_screenshot_images: bool = True,
    max_screenshots: int = 40,
) -> bytes:
    task = database.get_task(task_id)
    if not task:
        raise FileNotFoundError("task not found")

    events = database.list_events(task_id)
    sources = database.list_sources(task_id)
    plan_steps = task_plan_store.list_steps(task_id)
    files_meta = database.list_generated_files(task_id)
    projects = database.list_generated_projects(task_id)
    images = database.list_chat_images(task_id)
    context = database.get_context(task_id) or {}
    screenshots = database.list_screenshots(task_id, limit=max_screenshots)

    manifest = {
        "format": "vortax-session-export",
        "version": 1,
        "exported_at": utc_now(),
        "task_id": task_id,
        "counts": {
            "events": len(events),
            "sources": len(sources),
            "plan_steps": len(plan_steps),
            "files": len(files_meta),
            "projects": len(projects),
            "screenshots": len(screenshots),
            "chat_images": len(images),
        },
        "include_screenshot_images": include_screenshot_images,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("task.json", _json_bytes(task))
        zf.writestr("plan.json", _json_bytes({"steps": plan_steps}))
        zf.writestr("sources.json", _json_bytes(sources))
        zf.writestr("context.json", _json_bytes(context))
        zf.writestr("projects.json", _json_bytes(projects))
        zf.writestr("files_index.json", _json_bytes(files_meta))
        zf.writestr("metrics.json", _json_bytes(metrics.snapshot(task_id=task_id)))

        # events as jsonl for streaming replay tools
        lines = []
        for ev in events:
            lines.append(json.dumps(ev, ensure_ascii=False, default=str))
        zf.writestr("events.jsonl", ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"))

        # screenshots metadata (+ optional images)
        shot_meta = []
        for idx, shot in enumerate(screenshots):
            meta = {
                "id": shot.get("id"),
                "event_id": shot.get("event_id"),
                "created_at": shot.get("created_at"),
                "caption": shot.get("caption"),
                "title": shot.get("title"),
                "url": shot.get("url"),
            }
            b64 = shot.get("image_base64") or ""
            if include_screenshot_images and b64:
                # strip data-url prefix if present
                if "," in b64[:80]:
                    b64 = b64.split(",", 1)[1]
                try:
                    raw = base64.b64decode(b64)
                    fname = f"screenshots/{idx:03d}_{_safe_name(str(shot.get('id') or idx))}.png"
                    zf.writestr(fname, raw)
                    meta["file"] = fname
                except Exception:
                    meta["file"] = None
            shot_meta.append(meta)
        zf.writestr("screenshots/index.json", _json_bytes(shot_meta))

        # chat images metadata only (base64 can be huge; include small ones)
        chat_meta = []
        for idx, img in enumerate(images):
            entry = {
                "id": img.get("id"),
                "filename": img.get("filename"),
                "content_type": img.get("content_type"),
                "question": img.get("question"),
                "analysis": (img.get("analysis") or "")[:2000],
                "created_at": img.get("created_at"),
            }
            b64 = img.get("image_base64") or ""
            if b64 and len(b64) < 2_000_000:
                if "," in b64[:80]:
                    b64 = b64.split(",", 1)[1]
                try:
                    raw = base64.b64decode(b64)
                    ext = "png"
                    ctype = str(img.get("content_type") or "")
                    if "jpeg" in ctype or "jpg" in ctype:
                        ext = "jpg"
                    fname = f"chat_images/{idx:03d}.{ext}"
                    zf.writestr(fname, raw)
                    entry["file"] = fname
                except Exception:
                    entry["file"] = None
            chat_meta.append(entry)
        zf.writestr("chat_images/index.json", _json_bytes(chat_meta))

        # workspace files
        project_dir = (settings.WORKSPACE_PATH / task_id).resolve()
        if project_dir.is_dir():
            for path in sorted(project_dir.rglob("*")):
                if not path.is_file() or path.name == ".gitkeep":
                    continue
                if any(part in {"node_modules", ".git", "__pycache__", "dist", "build"} for part in path.parts):
                    continue
                rel = path.relative_to(project_dir).as_posix()
                try:
                    zf.write(path, f"files/{rel}")
                except OSError:
                    continue

    return buf.getvalue()
