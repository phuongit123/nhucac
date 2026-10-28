"""Test đặt tên file an toàn, chống path traversal, tránh ghi đè."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.security import (
    resolve_safe_output_dir,
    sanitize_filename,
    unique_destination,
)


def test_unicode_vietnamese() -> None:
    name = sanitize_filename("Hướng dẫn tải video ♪ 2026<>:\"/\\|?*")
    assert "Hướng dẫn tải video" in name
    assert not any(c in name for c in '<>:"/\\|?*')


def test_unicode_chinese() -> None:
    assert sanitize_filename("哔哩哔哩 视频下载") == "哔哩哔哩 视频下载"


def test_windows_reserved_names() -> None:
    out = sanitize_filename("CON.mp4")
    assert not out.lower().startswith("con.")
    assert out.startswith("_")


def test_control_chars_removed() -> None:
    out = sanitize_filename("abc\x00def\x1fghi\u202e")
    assert "\x00" not in out and "\x1f" not in out and "\u202e" not in out


def test_empty_fallback() -> None:
    assert sanitize_filename("", fallback="video") == "video"
    assert sanitize_filename("...") == "video"


def test_long_name_truncated() -> None:
    long = "あ" * 500
    out = sanitize_filename(long)
    assert len(out.encode("utf-8")) <= 150 * 3


def test_unique_destination_no_overwrite(tmp_path: Path) -> None:
    (tmp_path / "video.mp4").write_bytes(b"x")
    p1 = unique_destination(tmp_path, "video", "mp4")
    assert p1.name == "video (1).mp4"
    p1.write_bytes(b"y")
    p2 = unique_destination(tmp_path, "video", "mp4")
    assert p2.name == "video (2).mp4"


def test_output_dir_default(tmp_path, monkeypatch) -> None:
    from backend.config import settings
    monkeypatch.setattr(settings, "download_dir", tmp_path)
    resolved = resolve_safe_output_dir(None)
    assert resolved == tmp_path.resolve()


def test_output_dir_blocks_system_paths(tmp_path, monkeypatch) -> None:
    from backend.config import settings
    monkeypatch.setattr(settings, "download_dir", tmp_path)
    with pytest.raises(Exception):
        resolve_safe_output_dir("/etc")


def test_output_dir_relative_inside_base(tmp_path, monkeypatch) -> None:
    from backend.config import settings
    monkeypatch.setattr(settings, "download_dir", tmp_path)
    resolved = resolve_safe_output_dir("subfolder/nested")
    assert str(resolved).endswith("subfolder/nested")
    assert resolved.is_dir()
