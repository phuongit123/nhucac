"""Interface chung cho mọi adapter nền tảng (kiến trúc plugin/adapter).

Adapter KHÔNG tự thực hiện tải xuống; chúng khai báo khả năng và cung cấp
cú pháp yt-dlp an toàn. Engine dùng thông tin này để cấu hình yt-dlp.

Phân loại trạng thái hỗ trợ:
- supported            : đã triển khai và có kiểm thử
- limited              : chỉ hoạt động với một số loại nội dung/điều kiện
- official-only        : chỉ dùng phương thức tải chính thức (Netflix, Spotify...)
- unsupported          : chưa có phương thức tương thích
- needs-authentication : cần xác thực được nền tảng cho phép (cookie cục bộ)
"""
from __future__ import annotations

import abc
import re
from urllib.parse import urlparse

from backend.models.schemas import PlatformInfo, SupportStatus


class BaseAdapter(abc.ABC):
    key: str = ""
    display_name: str = ""
    status: SupportStatus = SupportStatus.UNSUPPORTED
    domains: tuple[str, ...] = ()
    url_patterns: tuple[re.Pattern, ...] = ()
    description_vi: str = ""
    conditions_vi: str = ""
    needs_authentication: bool = False
    supports_audio_only: bool = True
    max_resolution: int | None = None
    # Có thể dựa vào generic extractor của yt-dlp hay không
    relies_on_generic: bool = False

    # ---------- Nhận diện ----------
    def can_handle(self, url: str) -> bool:
        """URL có thuộc nền tảng này không (chỉ nhận diện host/pattern)."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        for d in self.domains:
            if host == d or host.endswith("." + d):
                return True
        return False

    def validate_url(self, url: str) -> bool:
        """Kiểm tra sâu hơn cú pháp URL của nền tảng. Mặc định theo can_handle."""
        if not self.can_handle(url):
            return False
        if self.url_patterns:
            return any(p.search(url) for p in self.url_patterns)
        return True

    # ---------- Khả năng ----------
    def get_capabilities(self) -> PlatformInfo:
        return PlatformInfo(
            key=self.key,
            display_name=self.display_name,
            status=self.status,
            description_vi=self.description_vi,
            conditions_vi=self.conditions_vi,
            needs_authentication=self.needs_authentication,
            supports_audio_only=self.supports_audio_only,
            max_resolution=self.max_resolution,
        )

    def get_supported_features(self) -> dict:
        return {
            "metadata": self.status in _METADATA_OK,
            "formats": self.status in _METADATA_OK,
            "download": self.download_allowed,
            "audio_only": self.supports_audio_only and self.download_allowed,
            "needs_authentication": self.needs_authentication,
        }

    @property
    def download_allowed(self) -> bool:
        return self.status in {SupportStatus.SUPPORTED, SupportStatus.LIMITED,
                               SupportStatus.NEEDS_AUTHENTICATION}

    # ---------- Cấu hình yt-dlp ----------
    def ydl_extra_opts(self) -> dict:
        """Tùy chọn yt-dlp riêng cho nền tảng (an toàn, không shell)."""
        return {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} key={self.key!r} status={self.status.value}>"


_METADATA_OK = {SupportStatus.SUPPORTED, SupportStatus.LIMITED, SupportStatus.NEEDS_AUTHENTICATION}
