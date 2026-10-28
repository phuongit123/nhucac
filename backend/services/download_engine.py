"""Download engine dựa trên yt-dlp (thư viện, KHÔNG sinh shell command từ URL).

- Chạy blocking code của yt-dlp trong thread pool → không chặn event loop.
- Callback tiến độ cập nhật task + publish sự kiện SSE.
- Hủy tác vụ qua CancelFlag (yt_dlp.utils.DownloadCancelled).
- Chỉ báo COMPLETED khi file đầu ra TỒN TẠI và có kích thước > 0 sau khi
  yt-dlp kết thúc (kể cả post-process FFmpeg).
- Phân loại lỗi yt-dlp thành AppError có thông báo tiếng Việt + cách khắc phục.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled

from backend.adapters.base import BaseAdapter
from backend.config import ffmpeg_available, settings
from backend.errors import (
    AuthenticationRequiredError,
    DependencyMissingError,
    ExtractionOutdatedError,
    FormatNotAvailableError,
    InsufficientDiskSpaceError,
    NetworkError,
    VideoUnavailableError,
)
from backend.models.schemas import FormatInfo, MediaMetadata
from backend.services.security import sanitize_filename, unique_destination, validate_url

log = logging.getLogger("umd.engine")


class CancelFlag:
    """Cờ hủy an toàn giữa threads."""

    def __init__(self) -> None:
        self.cancelled = False

    def raise_if(self) -> None:
        if self.cancelled:
            raise DownloadCancelled("Người dùng đã hủy tác vụ.")


def classify_ydl_error(exc: Exception) -> Exception:
    """Chuyển lỗi yt-dlp thô thành AppError có hướng dẫn (không lộ chi tiết nhạy cảm).

    Thứ tự kiểm tra quan trọng: các tín hiệu đặc thù (ffmpeg, unsupported url,
    private/removed, login) phải được xét TRƯỚC nhóm từ khóa chung như "format".
    """
    msg = str(exc)
    low = msg.lower()
    if isinstance(exc, DownloadCancelled):
        return exc
    # FFmpeg / post-processing — xét sớm vì chuỗi thường chứa cả từ "format"
    if any(k in low for k in ("ffmpeg", "ffprobe", "postprocessing", "post-process")):
        return DependencyMissingError(msg[:300])
    if "unsupported url" in low or "no suitable extractor" in low:
        return ExtractionOutdatedError(msg[:300])
    if any(k in low for k in ("login", "sign in", "sign in to confirm", "cookies",
                              "authentication", "auth required", "members-only",
                              "age-restricted", "private video", "this video is private",
                              "account needed")):
        return AuthenticationRequiredError(msg[:300])
    if any(k in low for k in ("removed", "unavailable", "does not exist",
                              "video unavailable", "not available", "deleted")):
        return VideoUnavailableError(msg[:300])
    if any(k in low for k in ("requested format is not available", "no formats",
                              "format is not available")):
        return FormatNotAvailableError(msg[:300])
    if any(k in low for k in ("timed out", "timeout", "temporary failure", "connection reset",
                              "network", "getaddrinfo", "ssl", "urlopen error")):
        return NetworkError(msg[:300])
    return NetworkError(f"Lỗi không phân loại được từ nguồn: {msg[:200]}")


def _quality_label(f: dict) -> str:
    h = f.get("height")
    if h:
        return f"{h}p"
    if f.get("vcodec") == "none" or not f.get("height"):
        return "Audio only"
    return f.get("format_note") or f.get("ext", "")


def extract_formats(info: dict) -> list[FormatInfo]:
    """Sinh DANH SÁCH ĐỊNH DẠNG THỰC TẾ từ metadata yt-dlp. Không tạo tùy chọn ảo."""
    out: list[FormatInfo] = []
    seen: set[str] = set()
    for f in info.get("formats") or []:
        fid = str(f.get("format_id", ""))
        ext = f.get("ext") or ""
        if not fid or not ext:
            continue
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        has_video = vcodec != "none"
        has_audio = acodec != "none"
        # Bỏ định dạng không tải được (m3u8 manifest không có filesize vẫn giữ nếu cần)
        height = f.get("height")
        fi = FormatInfo(
            format_id=fid,
            ext=ext,
            resolution=f.get("resolution") or (f"{f.get('width', '')}x{height}" if height else ""),
            quality_label=_quality_label(f),
            height=height,
            vcodec=vcodec,
            acodec=acodec,
            filesize=f.get("filesize") or f.get("filesize_approx"),
            tbr=f.get("tbr"),
            has_video=has_video,
            has_audio=has_audio,
            note=f.get("format_note") or "",
        )
        key = f"{fid}|{ext}|{height}"
        if key in seen:
            continue
        seen.add(key)
        out.append(fi)
    return out


def build_progress_hook(task_cb: Callable[[dict], None], flag: CancelFlag):
    last = {"t": 0.0}

    def hook(d: dict) -> None:
        flag.raise_if()
        now = time.monotonic()
        if d.get("status") == "downloading":
            if now - last["t"] < 0.25:  # throttle UI updates
                return
            last["t"] = now
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            speed = d.get("speed")
            payload = {
                "event": "progress",
                "percent": round(downloaded / total * 100, 1) if total else 0.0,
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "speed_bps": speed,
                "eta_seconds": d.get("eta"),
                "status_text": "Đang tải...",
            }
            task_cb(payload)
        elif d.get("status") == "finished":
            task_cb({"event": "progress", "percent": 100.0, "status_text": "Tải xong, xử lý hậu kỳ..."})
        elif d.get("status") == "error":
            task_cb({"event": "progress", "status_text": "Lỗi khi tải fragment"})
    return hook


def _postprocessor_hooks(task_cb: Callable[[dict], None]):
    def pp_hook(d: dict) -> None:
        stage = d.get("status")
        if stage == "started_processing":
            task_cb({"event": "progress", "status_text": "FFmpeg đang ghép/chuyển đổi..."})
    return [pp_hook]


async def analyze(url: str, adapter: BaseAdapter) -> MediaMetadata:
    """Phân tích metadata trong thread pool với timeout."""
    validate_url(url)

    def _run() -> dict:
        opts = _base_opts(adapter, quiet=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(_run), timeout=settings.analyze_timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise NetworkError("Hết thời gian phân tích URL (timeout).") from exc
    except DownloadCancelled:
        raise
    except Exception as exc:
        raise classify_ydl_error(exc) from exc

    if not info:
        raise VideoUnavailableError("Nguồn trả về dữ liệu rỗng.")
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise VideoUnavailableError("Playlist trống hoặc không khả dụng.")
        info = entries[0]  # giai đoạn này hỗ trợ từng video một

    return MediaMetadata(
        url=url,
        platform_key=adapter.key,
        title=sanitize_filename(info.get("title") or "", fallback="video"),
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel") or "",
        webpage_url=info.get("webpage_url") or url,
        formats=extract_formats(info),
        requires_auth=bool(info.get("requires_login")),
        is_live=bool(info.get("is_live")),
        raw_id=str(info.get("id") or ""),
    )


def _base_opts(adapter: BaseAdapter, *, quiet: bool = True) -> dict:
    opts: dict = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "overwrites": False,
        "windowsfilenames": True,   # an toàn tên file trên Windows
        "restrictfilenames": False,  # giữ Unicode — tự sanitize ở tầng app
        "ignoreerrors": False,
        "nocheckcertificate": False,
    }
    if settings.cookie_file and settings.cookie_file.exists():
        opts["cookiefile"] = str(settings.cookie_file)
    opts.update(adapter.ydl_extra_opts())
    return opts


def _build_format_fmt(options: dict, adapter: BaseAdapter) -> tuple[str, str | None]:
    """Trả (format_selector, target_ext) từ lựa chọn người dùng — chỉ dựa trên format THỰC."""
    fmt_id = options.get("format_id")
    audio_only = options.get("audio_only", False)
    audio_fmt = (options.get("audio_format") or "").lower() or None

    if audio_only:
        if not adapter.supports_audio_only:
            raise FormatNotAvailableError("Nền tảng này không cung cấp tùy chọn âm thanh riêng.")
        if audio_fmt in {"mp3"} :
            if not ffmpeg_available():
                raise DependencyMissingError("Chuyển đổi MP3 cần FFmpeg nhưng chưa được cài.")
            return ("bestaudio/best", "mp3")
        if audio_fmt in {"m4a", "opus", "webm"}:
            return (f"bestaudio[ext={audio_fmt}]/bestaudio/best", audio_fmt)
        return ("bestaudio/best", None)

    if fmt_id:
        # Cho phép id cụ thể; nếu nguồn không còn id đó yt-dlp sẽ báo
        # Requested format is not available → classify sang FormatNotAvailableError.
        return (fmt_id, None)
    # Mặc định: video+audio tốt nhất cùng container, tránh merge nếu không cần
    return ("bestvideo*+bestaudio/best", None)


async def download_file(
    url: str,
    adapter: BaseAdapter,
    options: dict,
    progress_cb: Callable[[dict], None],
    cancel: CancelFlag,
) -> Path:
    """Tải và xác minh file thật. Trả về đường dẫn cuối cùng đã lưu."""
    validate_url(url)
    if settings.free_disk_bytes() < settings.min_free_disk_bytes:
        raise InsufficientDiskSpaceError(
            f"Còn {settings.free_disk_bytes() // (1024*1024)} MB dung lượng trống.")

    out_dir: Path = options["output_dir"]
    fmt_sel, target_ext = _build_format_fmt(options, adapter)

    def _run() -> Path:
        opts = _base_opts(adapter)
        opts["paths"] = {"temp": str(out_dir / ".tmp")}
        opts["progress_hooks"] = [build_progress_hook(progress_cb, cancel)]
        opts["postprocessor_hooks"] = _postprocessor_hooks(progress_cb)
        opts["format"] = fmt_sel

        need_merge = "+" in fmt_sel and not options.get("audio_only")
        want_convert = bool(target_ext) and target_ext not in {"m4a", "opus", "webm"}
        if (need_merge or want_convert) and not ffmpeg_available():
            # Trung thực: không hứa ghép audio/video nếu thiếu FFmpeg
            if need_merge:
                raise DependencyMissingError(
                    "Video này cần FFmpeg để ghép audio+video nhưng FFmpeg chưa được cài.")
        if need_merge:
            opts["merge_output_format"] = "mp4"
        if options.get("audio_only"):
            opts["format"] = fmt_sel
            if target_ext == "mp3":
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                ]
            elif target_ext in {"m4a", "opus", "webm"}:
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": target_ext},
                ]
            else:
                opts["noplaylist"] = True

        stem = sanitize_filename(options.get("filename_stem") or "video")
        ext_guess = target_ext or "mp4"
        dest = unique_destination(out_dir, stem, ext_guess)
        opts["outtmpl"] = {
            "default": str(dest.with_name(dest.stem + ".%(ext)s")),
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info and info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
                if entries:
                    info = entries[0]
            final_path = None
            with contextlib.suppress(Exception):
                req = ydl.prepare_filename(info or {})
                final_path = Path(req)
        # Tìm file thật sự được tạo (extension có thể khác dự đoán)
        candidates: list[Path] = []
        if final_path and final_path.exists():
            candidates.append(final_path)
        for p in sorted(out_dir.glob(dest.stem + ".*")):
            if p.suffix.lower() not in (".part", ".ytdl", ".tmp") and p not in candidates:
                candidates.append(p)
        real = next((p for p in candidates if p.is_file() and p.stat().st_size > 0), None)
        if real is None:
            raise RuntimeError("yt-dlp kết thúc nhưng không tìm thấy file kết quả hợp lệ.")
        # Dọn phần tạm
        with contextlib.suppress(OSError):
            tmpdir = out_dir / ".tmp"
            if tmpdir.exists():
                shutil.rmtree(tmpdir, ignore_errors=True)
        return real

    try:
        return await asyncio.to_thread(_run)
    except DownloadCancelled:
        raise
    except (InsufficientDiskSpaceError, DependencyMissingError):
        raise
    except Exception as exc:
        mapped = classify_ydl_error(exc)
        if mapped is exc:
            raise
        raise mapped from exc
