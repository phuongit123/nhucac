"""Bảo mật: kiểm tra URL chống SSRF, tên file an toàn, chống path traversal.

- Không cho phép scheme khác http/https.
- Chặn hostname localhost / IP riêng tư / loopback / link-local (trừ khi
  UMD_ALLOW_PRIVATE_NETWORKS=true cho môi trường phát triển nội bộ).
- Tên file: giữ Unicode (tiếng Việt, tiếng Trung), loại ký tự cấm theo OS,
  chặn tên device Windows, giới hạn độ dài, tránh ghi đè bằng hậu tố (1), (2)...
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from backend.config import settings
from backend.errors import ForbiddenHostError, InvalidURLError

# Host blacklist theo tên (dù có phân giải hay không)
_BLOCKED_HOSTNAMES = {
    "localhost", "localdomain", "metadata.google.internal",
    "ip6-loopback", "ip6-localhost",
}

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

# Ký tự cấm trên Windows + kiểm soát chung
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*\u202e]')
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

MAX_FILENAME_LEN = 150


def validate_url(url: str) -> str:
    """Trả về URL đã chuẩn hóa. Ném InvalidURLError/ForbiddenHostError nếu không an toàn."""
    url = (url or "").strip()
    if not url or len(url) > 2048 or not _URL_RE.match(url):
        raise InvalidURLError(f"URL không hợp lệ: {url!r}")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in settings.http_scheme_allowlist:
        raise InvalidURLError("Chỉ hỗ trợ http/https.")
    host = parsed.hostname
    if not host:
        raise InvalidURLError("URL thiếu hostname.")
    return check_host(host, url)


def check_host(host: str, url: str) -> str:
    """Kiểm tra SSRF: chặn loopback/private/link-local/reserved."""
    h = host.lower().rstrip(".")
    if h in _BLOCKED_HOSTNAMES:
        raise ForbiddenHostError(f"Địa chỉ bị chặn: {host}")
    try:
        # Nếu host là literal IP
        ip = ipaddress.ip_address(h.strip("[]"))
        if not settings.allow_private_networks and (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            raise ForbiddenHostError("URL trỏ tới địa chỉ nội bộ, bị chặn để chống SSRF.")
    except ValueError:
        pass  # hostname thường, sẽ phân giải khi tải — yt-dlp xử lý tiếp
    return url


def sanitize_filename(name: str, fallback: str = "video") -> str:
    """Tên file an toàn, giữ Unicode có thể in được.

    - Normalization NFC để tiếng Việt/tiếng Trung ổn định.
    - Loại control chars và ký tự cấm của Windows.
    - Thay sequence khoảng trắng bằng một dấu cách, cắt bỏ phần thừa đầu/cuối.
    - Chặn tên dành riêng Windows, chặn bắt đầu/kết thúc bằng dấu chấm.
    """
    if not name:
        return fallback
    name = unicodedata.normalize("NFC", str(name))
    name = _ILLEGAL_FILENAME_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(". ")  # không bắt đầu/kết thúc bằng dấu chấm
    if not name:
        return fallback
    if name.lower().split(".")[0] in _WINDOWS_RESERVED:
        name = "_" + name
    # Giới hạn độ dài theo byte UTF-8 để an toàn trên mọi filesystem
    encoded = name.encode("utf-8")
    if len(encoded) > MAX_FILENAME_LEN * 3:
        # Cắt an toàn theo ký tự
        out = ""
        used = 0
        for ch in name:
            b = len(ch.encode("utf-8"))
            if used + b > MAX_FILENAME_LEN * 2:
                break
            out += ch
            used += b
        name = out.strip(". ") or fallback
    return name


def resolve_safe_output_dir(raw: str | None) -> Path:
    """Chuyển thư mục người dùng nhập thành Path nằm trong phạm vi cho phép.

    Mặc định: download_dir gốc. Người dùng có thể chọn thư mục con tương đối
    hoặc đường dẫn tuyệt đối — nhưng phải resolve được và KHÔNG escape symlink
    độc hại; đồng thời phải là thư mục (tạo nếu cần) và ghi được.
    """
    base = settings.download_dir.resolve()
    if not raw:
        return base
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise InvalidURLError(f"Không phân giải được thư mục lưu: {exc}") from exc
    # Cho phép mọi thư mục tuyệt đối mà process có quyền ghi (ứng dụng desktop
    # của riêng người dùng) — nhưng chặn rõ các vị trí hệ thống nhạy cảm.
    forbidden_prefixes = [Path("/etc"), Path("/bin"), Path("/sbin"), Path("/usr"),
                          Path("/boot"), Path("/dev"), Path("/proc"), Path("/sys")]
    for fp in forbidden_prefixes:
        if resolved == fp or resolved.is_relative_to(fp):
            raise InvalidURLError("Thư mục lưu nằm trong vùng hệ thống, bị chặn.")
    if any(part.startswith("..") for part in candidate.parts):
        raise InvalidURLError("Đường dẫn chứa '..', bị chặn (path traversal).")
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir() or not (resolved.exists() and _is_writable(resolved)):
        raise InvalidURLError("Thư mục lưu không tồn tại hoặc không có quyền ghi.")
    return resolved


def _is_writable(p: Path) -> bool:
    try:
        probe = p / ".umd_write_test"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def unique_destination(directory: Path, stem: str, ext: str) -> Path:
    """Tránh ghi đè ngoài ý muốn: video.mp4 -> video (1).mp4 -> video (2).mp4..."""
    stem = sanitize_filename(stem)
    ext = (ext or "").lower().lstrip(".")
    candidate = directory / f"{stem}.{ext}" if ext else directory / stem
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}).{ext}" if ext else directory / f"{stem} ({counter})"
        counter += 1
        if counter > 999:
            raise InvalidURLError("Quá nhiều file trùng tên trong thư mục đích.")
    return candidate
