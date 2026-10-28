"""Test hàng đợi, trạng thái tác vụ, hủy, retry — chạy offline với engine mock."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from backend.models.schemas import DownloadOptions, TaskState
from backend.services.queue_manager import Database, EventBus, QueueManager


@pytest.fixture()
async def qm(tmp_path: Path):
    db = Database(tmp_path / "q.sqlite3")
    await db.connect()
    bus = EventBus()
    manager = QueueManager(db, bus)
    manager._sem = asyncio.Semaphore(2)
    yield manager, db, bus
    await manager.shutdown()
    await db.close()


def _opts(url: str, out_dir: Path) -> DownloadOptions:
    return DownloadOptions(url=url, output_dir=str(out_dir))


async def test_add_task_states(qm, tmp_path, monkeypatch) -> None:
    manager, db, bus = qm
    events = bus.subscribe()
    fake_file = tmp_path / "fake.mp4"

    async def fake_download(url, adapter, options, progress_cb, cancel):
        # giả lập tiến trình thật: ghi file tăng dần rồi hoàn tất
        fake_file.write_bytes(b"123")
        progress_cb({"event": "progress", "percent": 50.0, "downloaded_bytes": 500,
                     "total_bytes": 1000, "status_text": "Đang tải..."})
        await asyncio.sleep(0.05)
        fake_file.write_bytes(b"1234567890")
        return fake_file

    monkeypatch.setattr("backend.services.queue_manager.download_file", fake_download)
    task = await manager.add(_opts("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path))
    assert task.state == TaskState.QUEUED

    for _ in range(100):
        cur = await db.get_task(task.id)
        if cur and cur.state == TaskState.COMPLETED:
            break
        await asyncio.sleep(0.05)
    cur = await db.get_task(task.id)
    assert cur is not None and cur.state == TaskState.COMPLETED
    assert cur.file_path and Path(cur.file_path).exists()
    assert cur.file_size == len(b"1234567890")
    hist = await db.list_history()
    assert len(hist) == 1 and hist[0]["id"] == task.id
    # sự kiện SSE đã được publish
    got = []
    while not events.empty():
        got.append(events.get_nowait())
    assert any(e["event"] == "task_completed" for e in got)


async def test_cancel_pending_task(qm, tmp_path) -> None:
    manager, db, _ = qm
    # chặn semaphore để task không chạy
    manager._sem = asyncio.Semaphore(0)
    task = await manager.add(_opts("https://youtu.be/dQw4w9WgXcQ", tmp_path))
    done = await manager.cancel(task.id)
    assert done.state == TaskState.CANCELLED


async def test_pause_resume(qm, tmp_path, monkeypatch) -> None:
    manager, db, _ = qm
    started = asyncio.Event()
    release = asyncio.Event()
    fake_file = tmp_path / "p.mp4"

    async def slow_download(url, adapter, options, progress_cb, cancel):
        started.set()
        await release.wait()
        fake_file.write_bytes(b"data")
        return fake_file

    monkeypatch.setattr("backend.services.queue_manager.download_file", slow_download)
    task = await manager.add(_opts("https://youtu.be/dQw4w9WgXcQ", tmp_path))
    await asyncio.wait_for(started.wait(), 2)
    paused = await manager.pause(task.id)
    assert paused.state == TaskState.PAUSED
    resumed = await manager.resume(task.id)
    assert resumed.state in (TaskState.QUEUED, TaskState.DOWNLOADING)
    release.set()
    for _ in range(60):
        cur = await db.get_task(task.id)
        if cur and cur.state == TaskState.COMPLETED:
            break
        await asyncio.sleep(0.05)
    cur = await db.get_task(task.id)
    assert cur.state == TaskState.COMPLETED


async def test_retry_on_network_error_then_fail(qm, tmp_path, monkeypatch) -> None:
    manager, db, _ = qm
    calls = {"n": 0}

    async def failing(url, adapter, options, progress_cb, cancel):
        calls["n"] += 1
        from backend.errors import NetworkError
        raise NetworkError("mock timeout")

    monkeypatch.setattr("backend.services.queue_manager.download_file", failing)
    monkeypatch.setattr("backend.services.queue_manager.asyncio.sleep", lambda s: asyncio.sleep(0))
    task = await manager.add(_opts("https://youtu.be/dQw4w9WgXcQ", tmp_path))
    for _ in range(120):
        cur = await db.get_task(task.id)
        if cur and cur.state == TaskState.FAILED:
            break
        await asyncio.sleep(0.05)
    cur = await db.get_task(task.id)
    assert cur.state == TaskState.FAILED
    assert cur.error and cur.error["error_code"] == "network_error"
    # attempts > 1 vì có retry tự động
    assert cur.attempts >= 2
    # manual retry đưa về queued
    retried = await manager.retry(task.id)
    assert retried.state in (TaskState.QUEUED, TaskState.ANALYZING, TaskState.DOWNLOADING)


async def test_unsupported_platform_rejected(qm, tmp_path) -> None:
    manager, _, _ = qm
    from backend.errors import UnsupportedPlatformError
    with pytest.raises(UnsupportedPlatformError):
        await manager.add(_opts("https://www.netflix.com/watch/12345", tmp_path))


async def test_shopee_unsupported_rejected(qm, tmp_path) -> None:
    manager, _, _ = qm
    from backend.errors import UnsupportedPlatformError
    with pytest.raises(UnsupportedPlatformError):
        await manager.add(_opts("https://shopee.vn/i/123.456", tmp_path))


async def test_stats(qm, tmp_path, monkeypatch) -> None:
    manager, db, _ = qm
    manager._sem = asyncio.Semaphore(0)
    await manager.add(_opts("https://youtu.be/dQw4w9WgXcQ", tmp_path))
    stats = await manager.stats()
    assert stats["total"] == 1 and stats["pending"] == 1
    assert stats["max_concurrent"] >= 1


async def test_remove_task(qm, tmp_path) -> None:
    manager, db, _ = qm
    manager._sem = asyncio.Semaphore(0)
    task = await manager.add(_opts("https://youtu.be/dQw4w9WgXcQ", tmp_path))
    await manager.remove(task.id)
    assert await db.get_task(task.id) is None


async def test_duplicate_detection(qm, tmp_path, monkeypatch) -> None:
    manager, db, _ = qm
    f = tmp_path / "dup.mp4"

    async def ok(url, adapter, options, progress_cb, cancel):
        f.write_bytes(b"x")
        return f

    monkeypatch.setattr("backend.services.queue_manager.download_file", ok)
    url = "https://youtu.be/dQw4w9WgXcQ"
    t = await manager.add(_opts(url, tmp_path))
    for _ in range(60):
        cur = await db.get_task(t.id)
        if cur and cur.state == TaskState.COMPLETED:
            break
        await asyncio.sleep(0.05)
    dup = await db.find_duplicate(url)
    assert dup is not None and dup["file_path"] == str(f)
