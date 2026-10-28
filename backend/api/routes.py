"""API endpoints: /api/*

Hợp đồng API (frontend phải khớp chính xác các đường dẫn và schema này):

GET  /api/health                     -> HealthResponse
GET  /api/platforms                  -> {platforms: PlatformInfo[]}
POST /api/detect                     -> DetectResponse          {url}
POST /api/analyze                    -> MediaMetadata           {url}
POST /api/tasks                      -> TaskOut                 (DownloadOptions)
GET  /api/tasks                      -> {tasks: TaskOut[], stats: QueueStats}
GET  /api/tasks/{id}                 -> TaskOut
POST /api/tasks/{id}/cancel          -> TaskOut
POST /api/tasks/{id}/pause           -> TaskOut
POST /api/tasks/{id}/resume          -> TaskOut
POST /api/tasks/{id}/retry           -> TaskOut
DELETE /api/tasks/{id}               -> {ok: true}
GET  /api/history                    -> {history: HistoryEntry[]}
DELETE /api/history/{id}             -> {ok, file_kept: true}
GET  /api/events                     -> SSE stream toàn cục
GET  /api/events/{task_id}           -> SSE stream theo task
GET  /api/settings/download-dir      -> {download_dir}
PUT  /api/settings/download-dir      -> {download_dir}   {path}
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.adapters.registry import registry
from backend.config import ffmpeg_available, settings
from backend.errors import AppError, DependencyMissingError, InvalidURLError
from backend.models.schemas import (
    AnalyzeRequest,
    DownloadOptions,
    HealthResponse,
    PlatformInfo,
    QueueStats,
    SupportStatus,
    DetectResponse,
)
from backend.services import download_engine
from backend.services.queue_manager import queue as qm
from backend.services.security import resolve_safe_output_dir, validate_url

log = logging.getLogger("umd.api")
router = APIRouter(prefix="/api")


class UrlBody(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class DirBody(BaseModel):
    path: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    warnings: list[str] = []
    if not ffmpeg_available():
        warnings.append("FFmpeg chưa được cài — ghép audio/video và chuyển đổi MP3 sẽ không hoạt động.")
    try:
        import yt_dlp  # noqa: F401
        # Một số phiên bản yt-dlp không định nghĩa __version__;
        # dùng metadata của package 'yt-dlp' làm nguồn đáng tin cậy.
        from importlib.metadata import PackageNotFoundError, version as _pkg_version
        try:
            ydl_ver = getattr(yt_dlp, "__version__", None) or _pkg_version("yt-dlp")
        except PackageNotFoundError:
            ydl_ver = None
    except ImportError:
        ydl_ver = None
        warnings.append("yt-dlp chưa được cài — engine tải xuống không khả dụng.")
    free = settings.free_disk_bytes()
    if free < settings.min_free_disk_bytes:
        warnings.append("Dung lượng ổ đĩa thấp (<500MB).")
    return HealthResponse(
        status="ok" if ydl_ver else "degraded",
        version=settings.version,
        ffmpeg_available=ffmpeg_available(),
        yt_dlp_version=ydl_ver,
        download_dir=str(settings.download_dir),
        free_disk_bytes=free,
        warnings=warnings,
    )


@router.get("/platforms")
async def platforms() -> dict:
    return {"platforms": [p.model_dump(mode="json") for p in registry.platform_infos()]}


@router.post("/detect", response_model=DetectResponse)
async def detect(body: UrlBody) -> DetectResponse:
    try:
        url = validate_url(body.url)
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc
    adapter, is_generic = registry.resolve(url)
    if adapter is None or is_generic:
        return DetectResponse(
            url=url, platform_key=None, platform_display_name=None, recognized=False,
            status=SupportStatus.LIMITED if adapter else SupportStatus.UNSUPPORTED,
            message_vi=("Không nhận diện được nền tảng đặc thù. Hệ thống sẽ THỬ phân tích bằng "
                        "generic extractor khi bạn bấm Analyze — kết quả phụ thuộc cấu trúc trang."))
    info = adapter.get_capabilities()
    msg = f"Nhận diện: {adapter.display_name} ({info.status.value})."
    if not adapter.download_allowed:
        msg += " " + adapter.conditions_vi
    return DetectResponse(
        url=url, platform_key=adapter.key, platform_display_name=adapter.display_name,
        recognized=True, status=info.status, message_vi=msg)


@router.post("/analyze")
async def analyze_ep(body: UrlBody) -> dict:
    try:
        url = validate_url(body.url)
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc
    adapter, is_generic = registry.resolve(url)
    if adapter is None:
        raise HTTPException(400, detail={"error_code": "unsupported_platform",
                                         "message": "Nền tảng không xác định.",
                                         "hint_vi": "Kiểm tra lại URL."})
    if not (adapter.download_allowed or adapter.relies_on_generic):
        err = AppError(f"{adapter.display_name}: chỉ hỗ trợ phương thức tải chính thức của nền tảng.")
        err.error_code = "official_only"
        err.hint_vi = adapter.conditions_vi
        raise HTTPException(400, detail=err.to_dict())
    try:
        meta = await download_engine.analyze(url, adapter)
        return {
            **meta.model_dump(mode="json"),
            "platform_display_name": adapter.display_name,
            "is_generic_fallback": is_generic,
        }
    except AppError as exc:
        log.info("Analyze thất bại (%s) cho URL hợp lệ", exc.error_code)  # không log URL đầy đủ
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc
    except Exception as exc:
        log.exception("Lỗi analyze không mong muốn")
        raise HTTPException(500, detail={"error_code": "internal_error",
                                         "message": str(exc)[:200],
                                         "hint_vi": "Lỗi nội bộ khi phân tích."}) from exc


@router.post("/tasks", status_code=201)
async def create_task(options: DownloadOptions) -> dict:
    try:
        task = await qm.add(options)
        return task.model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.get("/tasks")
async def list_tasks() -> dict:
    tasks = await qm.db.list_tasks()
    stats = await qm.stats()
    return {"tasks": [t.model_dump(mode="json") for t in tasks], "stats": stats}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    try:
        task = await qm._require(task_id)
        return task.model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    try:
        return (await qm.cancel(task_id)).model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str) -> dict:
    try:
        return (await qm.pause(task_id)).model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict:
    try:
        return (await qm.resume(task_id)).model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str) -> dict:
    try:
        return (await qm.retry(task_id)).model_dump(mode="json")
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    try:
        await qm.remove(task_id)
        return {"ok": True}
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc


@router.get("/history")
async def history() -> dict:
    rows = await qm.db.list_history()
    out = []
    for r in rows:
        exists = Path(r["file_path"]).exists()
        out.append({**r, "file_exists": exists,
                    "file_size_on_disk": (Path(r["file_path"]).stat().st_size
                                          if exists else None)})
    return {"history": out}


@router.delete("/history/{history_id}")
async def delete_history(history_id: str) -> dict:
    ok = await qm.db.delete_history(history_id)
    if not ok:
        raise HTTPException(404, detail={"error_code": "task_not_found",
                                         "message": "Không có mục lịch sử này."})
    return {"ok": True, "file_kept": True,
            "message_vi": "Đã xóa mục lịch sử. File gốc KHÔNG bị xóa."}


@router.get("/settings/download-dir")
async def get_download_dir() -> dict:
    return {"download_dir": str(settings.download_dir)}


@router.put("/settings/download-dir")
async def set_download_dir(body: DirBody) -> dict:
    try:
        new_dir = resolve_safe_output_dir(body.path)
    except AppError as exc:
        raise HTTPException(exc.http_status, detail=exc.to_dict()) from exc
    settings.download_dir = new_dir
    return {"download_dir": str(new_dir)}


# ------------------------- mở thư mục chứa file (desktop) --------------------
@router.post("/files/reveal")
async def reveal_in_folder(body: dict) -> dict:
    """Mở thư mục chứa file đã tải. Chỉ accept đường dẫn nằm trong download tree
    đã lưu trong DB (chống mở tùy ý đường dẫn từ frontend)."""
    raw = str(body.get("file_path") or "")
    target = Path(raw)
    known = {Path(h["file_path"]) for h in await qm.db.list_history(limit=1000)}
    if target not in known and target.parent not in {p.parent for p in known}:
        raise HTTPException(400, detail={"error_code": "invalid_url",
                                         "message": "File không thuộc lịch sử tải."})
    folder = target.parent if target.exists() else target
    try:
        import sys
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(folder)])  # noqa: S603 fixed args, no shell
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603
        return {"ok": True}
    except FileNotFoundError:
        raise HTTPException(500, detail={"error_code": "dependency_missing",
                                         "message": "Không tìm thấy trình mở thư mục."}) from None


# ------------------------------- SSE ----------------------------------------
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/events")
async def events_global(request: Request) -> StreamingResponse:
    return await _sse_stream(request, task_id=None)


@router.get("/events/{task_id}")
async def events_task(request: Request, task_id: str) -> StreamingResponse:
    return await _sse_stream(request, task_id=task_id)


async def _sse_stream(request: Request, task_id: str | None) -> StreamingResponse:
    q = qm.bus.subscribe(task_id)

    async def gen():
        try:
            yield _sse({"event": "connected", "task_id": task_id})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    yield _sse(ev)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            qm.bus.unsubscribe(q, task_id)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
