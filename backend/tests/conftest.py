"""Fixtures dùng chung cho test backend.

Mọi test tự động chạy offline: KHÔNG phụ thuộc mạng thật, video riêng tư,
tài khoản hay nội dung có bản quyền. Engine yt-dlp được mock bằng fixture
metadata giống hệt cấu trúc thật.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Cách ly data dir trước khi import config
_tmp = ROOT / ".pytest-tmp"
os.environ["UMD_DATA_DIR"] = str(_tmp / "data")
os.environ["UMD_DOWNLOAD_DIR"] = str(_tmp / "downloads")
os.environ["UMD_DB_PATH"] = str(_tmp / "data" / "test.sqlite3")


@pytest.fixture()
def sample_info_dict() -> dict:
    """Metadata mô phỏng yt-dlp extract_info(download=False) — video công khai mẫu."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "duration": 212,
        "uploader": "Rick Astley",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "requires_login": False,
        "is_live": False,
        "formats": [
            {"format_id": "140", "ext": "m4a", "acodec": "aac", "vcodec": "none",
             "height": None, "abr": 128, "tbr": 129.0, "filesize": 3_500_000},
            {"format_id": "160", "ext": "mp4", "acodec": "none", "vcodec": "avc1",
             "height": 144, "width": 256, "tbr": 110, "filesize": 1_200_000},
            {"format_id": "137", "ext": "mp4", "acodec": "none", "vcodec": "avc1",
             "height": 1080, "width": 1920, "tbr": 2500, "filesize": 45_000_000},
            {"format_id": "18", "ext": "mp4", "acodec": "mp4a", "vcodec": "avc1",
             "height": 360, "width": 640, "tbr": 500, "filesize": 12_000_000},
            {"format_id": "251", "ext": "webm", "acodec": "opus", "vcodec": "none",
             "height": None, "tbr": 160, "filesize": 4_200_000},
        ],
    }
