"""Test engine: extract_formats, classify lỗi, build format selector — offline."""
from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadCancelled

from backend.adapters.registry import registry
from backend.errors import (
    AuthenticationRequiredError,
    DependencyMissingError,
    ExtractionOutdatedError,
    FormatNotAvailableError,
    NetworkError,
    VideoUnavailableError,
)
from backend.services.download_engine import (
    CancelFlag,
    _build_format_fmt,
    classify_ydl_error,
    extract_formats,
)


def test_extract_formats_only_real_ones(sample_info_dict) -> None:
    fmts = extract_formats(sample_info_dict)
    ids = {f.format_id for f in fmts}
    assert ids == {"140", "160", "137", "18", "251"}
    audio = [f for f in fmts if not f.has_video]
    assert {f.ext for f in audio} == {"m4a", "webm"}
    f137 = next(f for f in fmts if f.format_id == "137")
    assert f137.height == 1080 and f137.quality_label == "1080p"
    # Không được sinh chất lượng ảo như 4K khi fixture không có
    assert all((f.height or 0) <= 1080 for f in fmts if f.height)


def test_classify_errors() -> None:
    cases = [
        (Exception("Video is private"), VideoUnavailableError),
        (Exception("Login required, use cookies"), AuthenticationRequiredError),
        (Exception("Requested format is not available"), FormatNotAvailableError),
        (Exception("<urlopen error timed out>"), NetworkError),
        (Exception("ERROR: Unsupported URL: https://x.example"), ExtractionOutdatedError),
        (Exception("ffmpeg not found. Please install ffmpeg"), DependencyMissingError),
    ]
    for exc, expected in cases:
        mapped = classify_ydl_error(exc)
        assert isinstance(mapped, expected), f"{exc} -> {type(mapped)}"


def test_cancelled_passthrough() -> None:
    exc = DownloadCancelled("user cancelled")
    assert classify_ydl_error(exc) is exc


def test_cancel_flag() -> None:
    flag = CancelFlag()
    flag.raise_if()  # ok when not cancelled
    flag.cancelled = True
    with pytest.raises(DownloadCancelled):
        flag.raise_if()


def test_build_format_default(yt=None) -> None:
    yt_adapter = registry.get("youtube")
    sel, ext = _build_format_fmt({}, yt_adapter)
    assert "+" in sel and ext is None


def test_build_format_specific_id() -> None:
    yt_adapter = registry.get("youtube")
    sel, ext = _build_format_fmt({"format_id": "137"}, yt_adapter)
    assert sel == "137"


def test_build_format_audio_mp3_requires_ffmpeg(monkeypatch) -> None:
    yt_adapter = registry.get("youtube")
    monkeypatch.setattr("backend.services.download_engine.ffmpeg_available", lambda: False)
    from backend.errors import DependencyMissingError
    with pytest.raises(DependencyMissingError):
        _build_format_fmt({"audio_only": True, "audio_format": "mp3"}, yt_adapter)
    monkeypatch.setattr("backend.services.download_engine.ffmpeg_available", lambda: True)
    sel, ext = _build_format_fmt({"audio_only": True, "audio_format": "mp3"}, yt_adapter)
    assert ext == "mp3"


def test_netflix_audio_not_offered() -> None:
    nf = registry.get("netflix")
    with pytest.raises(FormatNotAvailableError):
        _build_format_fmt({"audio_only": True}, nf)
