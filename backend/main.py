"""Ứng dụng FastAPI — điểm khởi chạy backend.

Chạy:  uvicorn backend.main:app --host 127.0.0.1 --port 8756
(Host mặc định 127.0.0.1 để không mở rộng mạng; app là công cụ desktop cá nhân.)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.config import settings
from backend.errors import AppError
from backend.services.queue_manager import bus, db, queue

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("umd.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    recovered = await db.recover_interrupted()
    if recovered:
        log.info("Khôi phục %d tác vụ dở dang về hàng đợi.", recovered)
    log.info("Backend sẵn sàng. Download dir: %s | DB: %s",
             settings.download_dir, db.path)
    yield
    await queue.shutdown()
    await db.close()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,   # không cần cookie cross-origin từ browser FE
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """AppError luôn trả cấu trúc {detail:{error_code,message,hint_vi}} cho FE."""
    return JSONResponse(status_code=exc.http_status, content={"detail": exc.to_dict()})


@app.get("/")
async def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
