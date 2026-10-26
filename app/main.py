"""Точка входа FastAPI."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .config import settings
from .db import init_db
from .services.pipeline import MANAGER

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("vector")

STATIC_DIR = settings.base_dir / "app" / "static"
INDEX_FILE = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.ensure_dirs()
    MANAGER.recover()
    port = os.getenv("PORT") or os.getenv("VECTOR_PORT", "8000")
    port = str(port).strip() or "8000"
    log.info("«Вектор» запущен на порту %s", port)
    yield
    MANAGER.shutdown()


app = FastAPI(
    title="Вектор — семантический поиск по видеолекциям",
    version=settings.version,
    description="Загрузка лекций, транскрибация, конспект, структура и поиск по смыслу.",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=800)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    if request.url.path in {"/", "/index.html"} or request.url.path.startswith("/lecture/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Необработанная ошибка на %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера. Подробности в логах."},
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store"})


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Метод API не найден."})
    # защита от path traversal
    if ".." in Path(full_path).parts:
        return JSONResponse(status_code=404, content={"detail": "Не найдено."})
    return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store"})


def run() -> None:
    import uvicorn

    port = int(os.getenv("PORT") or os.getenv("VECTOR_PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
