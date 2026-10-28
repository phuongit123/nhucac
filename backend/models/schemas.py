"""Pydantic models — hợp đồng API giữa frontend và backend."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    OFFICIAL_ONLY = "official-only"
    UNSUPPORTED = "unsupported"
    NEEDS_AUTHENTICATION = "needs-authentication"


class TaskState(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"   # ví dụ: ghép audio/video bằng FFmpeg
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}


class FormatInfo(BaseModel):
    """Một định dạng THỰC SỰ tồn tại trong metadata của nguồn.

    Không bao giờ sinh ra tùy chọn ảo.
    """
    format_id: str
    ext: str                       # mp4, webm, m4a, mp3...
    resolution: str = ""           # "1920x1080" hoặc "" với audio-only
    quality_label: str = ""        # "1080p", "720p", "Audio only"...
    height: int | None = None
    vcodec: str = "none"
    acodec: str = "none"
    filesize: int | None = None
    tbr: float | None = None
    has_video: bool = True
    has_audio: bool = True
    note: str = ""

    @field_validator("ext")
    @classmethod
    def _norm_ext(cls, v: str) -> str:
        return v.lower().lstrip(".")


class PlatformInfo(BaseModel):
    key: str
    display_name: str
    status: SupportStatus
    description_vi: str = ""
    conditions_vi: str = ""       # điều kiện sử dụng / giới hạn kỹ thuật
    needs_authentication: bool = False
    supports_audio_only: bool = False
    max_resolution: int | None = None


class DetectResponse(BaseModel):
    url: str
    platform_key: str | None
    platform_display_name: str | None
    recognized: bool
    status: SupportStatus | None = None
    message_vi: str = ""


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class MediaMetadata(BaseModel):
    url: str
    platform_key: str
    title: str = ""
    thumbnail: str | None = None
    duration: float | None = None
    uploader: str = ""
    webpage_url: str = ""
    formats: list[FormatInfo] = Field(default_factory=list)
    requested_formats_note: str = ""
    requires_auth: bool = False
    is_live: bool = False
    raw_id: str = ""


class DownloadOptions(BaseModel):
    url: str
    format_id: str | None = None          # nếu None => tốt nhất có thể
    audio_only: bool = False
    audio_format: str | None = None       # mp3/m4a khi audio_only và FFmpeg có sẵn
    output_dir: str | None = None         # đã được kiểm tra path traversal ở service
    filename_template: str | None = None
    skip_duplicate: bool = True


class TaskProgress(BaseModel):
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: float | None = None
    status_text: str = ""


class TaskOut(BaseModel):
    id: str
    url: str
    platform_key: str
    title: str = ""
    state: TaskState
    progress: TaskProgress = Field(default_factory=TaskProgress)
    options: DownloadOptions
    error: dict[str, Any] | None = None
    file_path: str | None = None
    file_size: int | None = None
    created_at: str
    updated_at: str
    attempts: int = 0


class HistoryEntry(BaseModel):
    id: str
    url: str
    platform_key: str
    title: str
    file_path: str
    file_size: int
    completed_at: str
    state: TaskState


class QueueStats(BaseModel):
    total: int
    active: int
    pending: int
    completed: int
    failed: int
    cancelled: int
    max_concurrent: int


class HealthResponse(BaseModel):
    status: str
    version: str
    ffmpeg_available: bool
    yt_dlp_version: str | None
    download_dir: str
    free_disk_bytes: int
    warnings: list[str] = Field(default_factory=list)
