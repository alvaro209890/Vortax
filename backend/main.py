from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from access import install_lan_guard
from api import control, files, providers, tasks, ws
from config import settings
from database import database
from services.process_registry import kill_all_best_effort
from tools.browser_pool import browser_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await browser_pool.initialize()
    try:
        yield
    finally:
        await browser_pool.shutdown()
        database.close()
        kill_all_best_effort()


app = FastAPI(title="Vortax", version="0.1.2-local", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
install_lan_guard(app)

app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(control.router, prefix="/api/control", tags=["control"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(ws.router, tags=["websocket"])


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": "vortax",
        "version": app.version,
        "mode": settings.APP_ENV,
        "auth": "disabled" if settings.ALLOW_NO_AUTH else "lan_optional" if settings.ALLOW_LAN_NO_AUTH else "enabled",
        "lan_only": settings.LAN_ONLY,
        "model": settings.DEEPSEEK_MODEL,
        "deepseek_configured": bool(settings.DEEPSEEK_API_KEY.strip()),
        "vision_provider": settings.VISION_PROVIDER,
        "vision_model": settings.GROQ_VISION_MODEL,
        "vision_configured": settings.ENABLE_VISION_TESTS and bool(settings.GROQ_API_KEY.strip()),
    }
