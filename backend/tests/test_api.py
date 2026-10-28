"""Test API backend bằng httpx ASGI transport — không mở port thật.

Engine yt-dlp được mock: test xác minh HỢP ĐỒNG API và xử lý lỗi,
không phụ thuộc mạng/video thật.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.services.queue_manager import db as app_db


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "download_dir", tmp_path)
    await app_db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await app_db.close()


async def test_health(client) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["ffmpeg_available"], bool)
    assert body["yt_dlp_version"]  # đã cài trong môi trường test


async def test_platforms_list(client) -> None:
    r = await client.get("/api/platforms")
    assert r.status_code == 200
    platforms = {p["key"]: p for p in r.json()["platforms"]}
    assert platforms["youtube"]["status"] == "supported"
    assert platforms["netflix"]["status"] == "official-only"
    assert platforms["shopee_video"]["status"] == "unsupported"
    assert platforms["instagram"]["status"] == "needs-authentication"


async def test_detect_youtube(client) -> None:
    r = await client.post("/api/detect",
                          json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert r.status_code == 200
    body = r.json()
    assert body["recognized"] is True and body["platform_key"] == "youtube"


async def test_detect_invalid_url_400(client) -> None:
    r = await client.post("/api/detect", json={"url": "not-a-url"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "invalid_url"


async def test_detect_ssrf_blocked(client) -> None:
    r = await client.post("/api/detect", json={"url": "http://169.254.169.254/meta"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "forbidden_host"


async def test_analyze_netflix_rejected(client) -> None:
    r = await client.post("/api/analyze", json={"url": "https://www.netflix.com/watch/80000001"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "official_only"


async def test_analyze_mocked_success(client, monkeypatch, sample_info_dict) -> None:
    async def fake_analyze(url, adapter):
        from backend.services.download_engine import MediaMetadata, extract_formats
        return MediaMetadata(
            url=url, platform_key=adapter.key,
            title="Rick Astley - Never Gonna Give You Up (Official Music Video)",
            thumbnail=sample_info_dict["thumbnail"], duration=212,
            uploader="Rick Astley", webpage_url=url,
            formats=extract_formats(sample_info_dict))

    monkeypatch.setattr("backend.api.routes.download_engine.analyze", fake_analyze)
    r = await client.post("/api/analyze",
                          json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert r.status_code == 200
    body = r.json()
    assert body["duration"] == 212
    fmt_ids = [f["format_id"] for f in body["formats"]]
    assert "137" in fmt_ids and "140" in fmt_ids
    heights = sorted({f["height"] for f in body["formats"] if f["height"]})
    assert heights == [144, 360, 1080]  # chỉ định dạng THẬT có trong fixture


async def test_create_task_and_cancel_flow(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("backend.services.queue_manager.QueueManager._schedule",
                        lambda self, tid: None)  # không chạy worker
    r = await client.post("/api/tasks", json={
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "audio_only": False})
    assert r.status_code == 201
    task = r.json()
    assert task["state"] == "queued"

    r2 = await client.get(f"/api/tasks/{task['id']}")
    assert r2.status_code == 200 and r2.json()["id"] == task["id"]

    r3 = await client.post(f"/api/tasks/{task['id']}/cancel")
    assert r3.status_code == 200 and r3.json()["state"] == "cancelled"

    r4 = await client.get("/api/tasks")
    assert r4.status_code == 200
    assert any(t["id"] == task["id"] for t in r4.json()["tasks"])

    r5 = await client.delete(f"/api/tasks/{task['id']}")
    assert r5.status_code == 200

    r6 = await client.get("/api/tasks/nonexistent")
    assert r6.status_code == 404


async def test_create_task_unsupported(client) -> None:
    r = await client.post("/api/tasks", json={"url": "https://www.netflix.com/watch/1"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "unsupported_platform"


async def test_history_endpoints(client) -> None:
    r = await client.get("/api/history")
    assert r.status_code == 200 and isinstance(r.json()["history"], list)
    r2 = await client.delete("/api/history/does-not-exist")
    assert r2.status_code == 404


async def test_download_dir_settings(client, tmp_path) -> None:
    new_dir = str(tmp_path / "vids")
    r = await client.put("/api/settings/download-dir", json={"path": new_dir})
    assert r.status_code == 200 and r.json()["download_dir"].endswith("vids")
    r2 = await client.get("/api/settings/download-dir")
    assert r2.json()["download_dir"] == str(Path(new_dir).resolve())
    # chặn vùng hệ thống
    r3 = await client.put("/api/settings/download-dir", json={"path": "/etc"})
    assert r3.status_code == 400


async def test_sse_connect(client) -> None:
    async with client.stream("GET", "/api/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        line = b""
        async for chunk in resp.aiter_bytes():
            line += chunk
            break
        assert b"connected" in line
