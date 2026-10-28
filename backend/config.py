"""Cấu hình ứng dụng Universal Media Downloader (backend).

Mọi giá trị có thể ghi đè bằng biến môi trường, xem .env.example.
Không chứa thông tin bí mật.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    app_name: str = "Universal Media Downloader"
    version: str = "0.1.0"

    # Thư mục làm việc
    data_dir: Path = field(default_factory=lambda: Path(
        os.getenv("UMD_DATA_DIR", Path.home() / ".universal-media-downloader")))
    download_dir: Path = field(default_factory=lambda: Path(
        os.getenv("UMD_DOWNLOAD_DIR", str(Path.home() / "Downloads" / "UniversalMediaDownloader"))))

    # Database
    db_path: Path = field(default_factory=lambda: Path(
        os.getenv("UMD_DB_PATH", "")) or None)  # type: ignore[assignment]

    # Hàng đợi
    max_concurrent_tasks: int = field(default_factory=lambda: _env_int("UMD_MAX_CONCURRENT", 2))
    max_queue_size: int = field(default_factory=lambda: _env_int("UMD_MAX_QUEUE_SIZE", 200))
    task_timeout_seconds: int = field(default_factory=lambda: _env_int("UMD_TASK_TIMEOUT", 3600))
    analyze_timeout_seconds: int = field(default_factory=lambda: _env_int("UMD_ANALYZE_TIMEOUT", 60))
    max_retries: int = field(default_factory=lambda: _env_int("UMD_MAX_RETRIES", 2))

    # Giới hạn an toàn
    max_file_size_bytes: int = field(default_factory=lambda: _env_int("UMD_MAX_FILE_SIZE", 4 * 1024**3))
    min_free_disk_bytes: int = field(default_factory=lambda: _env_int("UMD_MIN_FREE_DISK", 500 * 1024**2))

    # Bảo mật mạng
    allow_private_networks: bool = field(default_factory=lambda: _env_bool("UMD_ALLOW_PRIVATE_NETWORKS", False))
    http_scheme_allowlist: tuple = ("http", "https")

    # CORS
    cors_origins: list = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "UMD_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        ).split(",") if o.strip()
    ])

    # Cookie cục bộ (chỉ khi người dùng tự cung cấp, cho nội dung họ có quyền)
    cookie_file: Path | None = None

    def __post_init__(self) -> None:
        if self.db_path is None:
            object.__setattr__(self, "db_path", self.data_dir / "umd.sqlite3")
        else:
            object.__setattr__(self, "db_path", Path(str(self.db_path)))
        self.data_dir = Path(self.data_dir)
        self.download_dir = Path(self.download_dir)
        cf = os.getenv("UMD_COOKIE_FILE")
        self.cookie_file = Path(cf) if cf else None

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def free_disk_bytes(self) -> int:
        probe = self.download_dir if self.download_dir.exists() else Path("/")
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            return 0


settings = Settings()
settings.ensure_dirs()


def ffmpeg_available() -> bool:
    """Kiểm tra FFmpeg có thực sự tồn tại trên hệ thống (không giả định)."""
    path = shutil.which("ffmpeg")
    if not path:
        return False
    try:
        res = shutil.which("ffprobe")
        return bool(res)
    except Exception:
        return False
