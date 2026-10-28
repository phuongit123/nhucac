"""Ứng dụng FastAPI — điểm khởi chạy backend.

Chạy:  uvicorn backend.main:app --host 127.0.0.1 --port 8756
(Host mặc định 127.0.0.1 để không mở rộng mạng; app là công cụ desktop cá nhân.)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.api.routes import router as api_router
from backend.config import settings
from backend.errors import AppError
from backend.services.queue_manager import bus, db, queue

from pathlib import Path as _P
WEB_DIR = _P(__file__).resolve().parent.parent / "web"

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


def _ui_available() -> bool:
    return (WEB_DIR / "index.html").is_file()


@app.get("/")
async def root():
    """Mở / là thấy giao diện ngay (nếu có web/); không thì trả JSON info."""
    if _ui_available():
        return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}


# ------------------------- UI tĩnh (thư mục web/) ---------------------------
# Phục vụ giao diện người dùng từ cùng origin với API => không cần CORS,
# không cần Node.js/Vite trên máy người dùng. Chạy uvicorn xong mở là dùng được.
if WEB_DIR.is_dir():

    @app.get("/ui")
    async def ui_index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")

    @app.get("/{path:path}", include_in_schema=False)
    async def ui_static(path: str):
        # Chỉ serve file trong web/ — chống path traversal.
        if path.startswith("api/") or path in ("docs", "openapi.json", "redoc"):
            raise HTTPException_404()
        target = (WEB_DIR / path).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            raise HTTPException_404() from None
        if not target.is_file():
            raise HTTPException_404()
        return FileResponse(target)

    def HTTPException_404():  # noqa: N802
        from fastapi import HTTPException
        return HTTPException(404, detail={"error_code": "not_found",
                                          "message": "Không tìm thấy trang."})
