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


def _resolve_db_path() -> Path:
    """Trả về đường dẫn file SQLite hợp lệ.

    - UMD_DB_PATH không đặt hoặc rỗng → data_dir mặc định / umd.sqlite3.
    - UMD_DB_PATH trỏ tới thư mục tồn tại → bên trong thư mục đó / umd.sqlite3
      (tránh 'unable to open database file' khi người dùng cấu hình nhầm thư mục).
    - Ngược lại: dùng đúng đường dẫn người dùng cấu hình.
    """
    raw = os.getenv("UMD_DB_PATH", "").strip()
    if not raw:
        data_dir = Path(os.getenv(
            "UMD_DATA_DIR", Path.home() / ".universal-media-downloader"))
        return data_dir / "umd.sqlite3"
    p = Path(raw)
    if p.is_dir():
        return p / "umd.sqlite3"
    return p


@dataclass
class Settings:
    app_name: str = "Universal Media Downloader"
    version: str = "0.1.0"

    # Thư mục làm việc
    data_dir: Path = field(default_factory=lambda: Path(
        os.getenv("UMD_DATA_DIR", Path.home() / ".universal-media-downloader")))
    download_dir: Path = field(default_factory=lambda: Path(
        os.getenv("UMD_DOWNLOAD_DIR", str(Path.home() / "Downloads" / "UniversalMediaDownloader"))))

    # Database — nếu UMD_DB_PATH không tồn tại hoặc rỗng, mặc định data_dir/umd.sqlite3.
    # (Path("") == Path(".") là thư mục hiện tại, KHÔNG phải None — lỗi cũ ở đây.)
    db_path: Path = field(default_factory=lambda: _resolve_db_path())

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
        # db_path luôn là file (không bao giờ là '.' hay thư mục rỗng).
        raw = str(self.db_path).strip() if self.db_path is not None else ""
        if not raw or raw in {".", "\\"} or Path(raw).is_dir():
            object.__setattr__(self, "db_path", self.data_dir / "umd.sqlite3")
        else:
            object.__setattr__(self, "db_path", Path(raw))
        self.data_dir = Path(self.data_dir)
        self.download_dir = Path(self.download_dir)
        cf = os.getenv("UMD_COOKIE_FILE")
        self.cookie_file = Path(cf) if cf else None

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        # Thư mục cha của file DB (có thể khác data_dir nếu cấu hình UMD_DB_PATH)
        parent = self.db_path.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)

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
