"""Queue manager: điều phối tác vụ tải xuống.

- asyncio.Semaphore giới hạn số tác vụ đồng thời.
- Mỗi task chạy trong asyncio.Task riêng; lỗi của một task KHÔNG crash backend.
- Publish sự kiện tiến độ qua EventBus (SSE).
- Pause/Resume ở mức ứng dụng: pause = cancel an toàn & giữ .part để yt-dlp
  resume (.part được yt-dlp tự tiếp tục khi chạy lại cùng outtmpl).
- Retry tối đa settings.max_retries cho lỗi tạm thời (network/timeout).
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from backend.adapters.registry import registry
from backend.config import settings
from backend.errors import AppError, TaskCancelledError, TaskNotFoundError
from backend.models.schemas import (
    DownloadOptions,
    TaskOut,
    TaskProgress,
    TaskState,
    TERMINAL_STATES,
)
from backend.services.database import Database, new_task_id
from backend.services.download_engine import CancelFlag, analyze, download_file
from backend.services.security import resolve_safe_output_dir, validate_url

log = logging.getLogger("umd.queue")

RETRYABLE = {"network_error", "extractor_outdated"}


class EventBus:
    """Pub/sub sự kiện theo task và toàn cục cho SSE."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, task_id: str | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        key = task_id or "*"
        self._subs.setdefault(key, set()).add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue, task_id: str | None = None) -> None:
        key = task_id or "*"
        self._subs.get(key, set()).discard(q)

    def publish(self, event: dict, task_id: str | None = None) -> None:
        event = {**event, "ts": time.time()}
        for q in list(self._subs.get("*", set())) + list(self._subs.get(task_id or "", set())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # client quá chậm — bỏ sự kiện cũ nhất để không chặn worker
                with_suppress = getattr(q, "get_nowait", None)
                try:
                    if with_suppress:
                        q.get_nowait()
                        q.put_nowait(event)
                except Exception:
                    pass


class QueueManager:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus
        self._running: dict[str, tuple[asyncio.Task, CancelFlag]] = {}
        self._sem = asyncio.Semaphore(settings.max_concurrent_tasks)
        self._paused_ids: set[str] = set()

    # ---------------- public API ----------------
    async def add(self, options: DownloadOptions) -> TaskOut:
        url = validate_url(options.url)
        adapter, is_generic = registry.resolve(url)
        if adapter is None:
            from backend.errors import UnsupportedPlatformError
            raise UnsupportedPlatformError(url)
        if not adapter.download_allowed:
            from backend.errors import UnsupportedPlatformError
            raise UnsupportedPlatformError(
                f"{adapter.display_name}: {adapter.conditions_vi}")
        # kiểm tra thư mục sớm để fail-fast trước khi vào hàng đợi
        out_dir = resolve_safe_output_dir(options.output_dir)
        options.output_dir = str(out_dir)
        options.url = url

        counts = await self.db.count_by_state()
        total = sum(counts.values())
        if total >= settings.max_queue_size:
            from backend.errors import QueueFullError
            raise QueueFullError()

        now = str(time.time())
        task = TaskOut(
            id=new_task_id(), url=url, platform_key=adapter.key,
            state=TaskState.QUEUED, options=options,
            created_at=now, updated_at=now,
        )
        await self.db.insert_task(task)
        self.bus.publish({"event": "task_added", "task": task.model_dump(mode="json")})
        self._schedule(task.id)
        return task

    async def cancel(self, task_id: str) -> TaskOut:
        task = await self._require(task_id)
        if task.state in TERMINAL_STATES:
            return task
        entry = self._running.get(task_id)
        if entry:
            _async_task, flag = entry
            flag.cancelled = True
            _async_task.cancel()
        else:
            self._paused_ids.discard(task_id)
            await self._set_state(task, TaskState.CANCELLED,
                                  error={"error_code": "task_cancelled",
                                         "message": "Người dùng đã hủy tác vụ."})
        return await self._require(task_id)

    async def pause(self, task_id: str) -> TaskOut:
        """Pause = dừng an toàn, giữ file .part để resume sau."""
        task = await self._require(task_id)
        if task.state not in {TaskState.DOWNLOADING, TaskState.QUEUED}:
            return task
        self._paused_ids.add(task_id)
        entry = self._running.get(task_id)
        if entry:
            _async_task, flag = entry
            flag.cancelled = True
            _async_task.cancel()
            await self._set_state(task, TaskState.PAUSED)
        else:
            await self._set_state(task, TaskState.PAUSED)
        return await self._require(task_id)

    async def resume(self, task_id: str) -> TaskOut:
        task = await self._require(task_id)
        if task.state != TaskState.PAUSED:
            return task
        self._paused_ids.discard(task_id)
        await self._set_state(task, TaskState.QUEUED)
        self._schedule(task_id)
        return await self._require(task_id)

    async def retry(self, task_id: str) -> TaskOut:
        task = await self._require(task_id)
        if task.state not in {TaskState.FAILED, TaskState.CANCELLED}:
            return task
        task.error = None
        await self._set_state(task, TaskState.QUEUED, extra_reset=True)
        self._schedule(task_id)
        return await self._require(task_id)

    async def remove(self, task_id: str) -> None:
        """Xóa task khỏi hàng đợi (không xóa file đã tải)."""
        entry = self._running.get(task_id)
        if entry:
            _async_task, flag = entry
            flag.cancelled = True
            _async_task.cancel()
        await self.db.delete_task(task_id)
        self.bus.publish({"event": "task_removed", "task_id": task_id})

    async def stats(self) -> dict:
        counts = await self.db.count_by_state()
        total = sum(counts.values())
        active = sum(1 for at, _ in self._running.values() if not at.done())
        pending = counts.get(TaskState.QUEUED.value, 0) + counts.get(TaskState.ANALYZING.value, 0)
        return {
            "total": total,
            "active": active,
            "pending": pending,
            "completed": counts.get(TaskState.COMPLETED.value, 0),
            "failed": counts.get(TaskState.FAILED.value, 0),
            "cancelled": counts.get(TaskState.CANCELLED.value, 0),
            "max_concurrent": settings.max_concurrent_tasks,
        }

    async def shutdown(self) -> None:
        for tid, (at, flag) in list(self._running.items()):
            flag.cancelled = True
            at.cancel()
        if self._running:
            await asyncio.gather(*(a for a, _ in self._running.values()),
                                 return_exceptions=True)

    # ---------------- internal ----------------
    def _schedule(self, task_id: str) -> None:
        if task_id in self._running:
            return
        flag = CancelFlag()
        at = asyncio.create_task(self._worker(task_id, flag), name=f"dl-{task_id}")
        self._running[task_id] = (at, flag)
        at.add_done_callback(lambda _t: self._running.pop(task_id, None))

    async def _require(self, task_id: str) -> TaskOut:
        task = await self.db.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    async def _set_state(self, task: TaskOut, state: TaskState, *,
                         error: dict | None = None, extra_reset: bool = False) -> None:
        task.state = state
        if error is not None:
            task.error = error
        if extra_reset:
            task.progress = TaskProgress()
            task.error = None
        await self.db.update_task(task)
        self.bus.publish({"event": "task_updated", "task": task.model_dump(mode="json")},
                         task_id=task.id)

    async def _worker(self, task_id: str, flag: CancelFlag) -> None:
        async with self._sem:
            try:
                task = await self._require(task_id)
            except TaskNotFoundError:
                return
            if task.state == TaskState.CANCELLED or task_id in self._paused_ids:
                return
            adapter = registry.get(task.platform_key)
            assert adapter is not None
            started = False
            try:
                # 1) metadata nếu chưa có title
                if not task.title:
                    await self._set_state(task, TaskState.ANALYZING)
                    meta = await asyncio.wait_for(
                        analyze(task.url, adapter), settings.task_timeout_seconds)
                    task.title = meta.title
                    await self.db.update_task(task)
                    self.bus.publish({"event": "task_updated",
                                      "task": task.model_dump(mode="json")}, task_id=task_id)

                await self._set_state(task, TaskState.DOWNLOADING)
                started = True
                opts_dict = task.options.model_dump()
                stem = task.title or "video"

                def progress_cb(payload: dict) -> None:
                    p = payload or {}
                    task.progress = TaskProgress(
                        percent=p.get("percent", task.progress.percent),
                        downloaded_bytes=p.get("downloaded_bytes", task.progress.downloaded_bytes),
                        total_bytes=p.get("total_bytes", task.progress.total_bytes),
                        speed_bps=p.get("speed_bps", task.progress.speed_bps),
                        eta_seconds=p.get("eta_seconds", task.progress.eta_seconds),
                        status_text=p.get("status_text", task.progress.status_text),
                    )
                    self.bus.publish({**p, "task_id": task_id}, task_id=task_id)

                final_path = await download_file(
                    task.url, adapter,
                    {**opts_dict, "output_dir": Path(opts_dict["output_dir"]),
                     "filename_stem": stem},
                    progress_cb, flag)

                # 2) XÁC MINH file thật trước khi báo completed
                if not final_path.exists() or final_path.stat().st_size <= 0:
                    raise RuntimeError("File kết quả không hợp lệ sau tải.")
                task.file_path = str(final_path)
                task.file_size = final_path.stat().st_size
                await self._set_state(task, TaskState.COMPLETED)
                await self.db.add_history(
                    task_id=task.id, url=task.url, platform_key=task.platform_key,
                    title=task.title, file_path=task.file_path, file_size=task.file_size)
                self.bus.publish({"event": "task_completed", "task_id": task_id,
                                  "file_path": task.file_path})

            except asyncio.CancelledError:
                task = await self.db.get_task(task_id)
                if task and task_id in self._paused_ids:
                    await self._set_state(task, TaskState.PAUSED)
                elif task:
                    await self._set_state(task, TaskState.CANCELLED,
                                          error={"error_code": "task_cancelled",
                                                 "message": "Tác vụ đã bị hủy."})
            except AppError as exc:
                task = await self.db.get_task(task_id)
                if not task:
                    return
                task.attempts += 1
                retriable = exc.error_code in RETRYABLE and task.attempts <= settings.max_retries
                if retriable and task_id not in self._paused_ids:
                    await self._set_state(task, TaskState.QUEUED, error=exc.to_dict())
                    await asyncio.sleep(min(2 ** task.attempts, 8))
                    self._schedule(task_id)
                else:
                    await self._set_state(task, TaskState.FAILED, error=exc.to_dict())
                    self.bus.publish({"event": "task_failed", "task_id": task_id,
                                      "error": exc.to_dict()})
            except Exception as exc:  # KHÔNG để crash cả backend
                log.exception("Lỗi không mong muốn ở task %s", task_id)
                task = await self.db.get_task(task_id)
                if task:
                    err = {"error_code": "internal_error",
                           "message": str(exc)[:200],
                           "hint_vi": "Lỗi nội bộ. Xem log backend."}
                    await self._set_state(task, TaskState.FAILED, error=err)
                    self.bus.publish({"event": "task_failed", "task_id": task_id, "error": err})


# Singleton helpers -----------------------------------------------------------
db = Database()
bus = EventBus()
queue = QueueManager(db, bus)
