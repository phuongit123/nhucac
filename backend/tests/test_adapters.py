"""Test nhận diện URL từng nền tảng + URL không hợp lệ + adapter chưa hỗ trợ."""
from __future__ import annotations

import pytest

from backend.adapters.registry import registry
from backend.models.schemas import SupportStatus
from backend.services.security import validate_url
from backend.errors import ForbiddenHostError, InvalidURLError


@pytest.mark.parametrize("url,key", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ("https://music.youtube.com/watch?v=abc123def45", "youtube"),
    ("https://www.facebook.com/user/videos/1234567/", "facebook"),
    ("https://fb.watch/abcdef/", "facebook"),
    ("https://www.tiktok.com/@user/video/71234567890", "tiktok"),
    ("https://vm.tiktok.com/ZMabcdef/", "tiktok"),
    ("https://www.douyin.com/video/7123456789", "douyin"),
    ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
    ("https://b23.tv/abCdEf", "bilibili"),
    ("https://www.instagram.com/reel/Cabcdefg/", "instagram"),
    ("https://x.com/user/status/1234567890", "twitter"),
    ("https://twitter.com/user/status/1234567890", "twitter"),
    ("https://www.reddit.com/r/sub/comments/abc/title/", "reddit"),
    ("https://vimeo.com/76979871", "vimeo"),
    ("https://www.dailymotion.com/video/x7tgad0", "dailymotion"),
    ("https://dai.ly/x7tgad0", "dailymotion"),
    ("https://pin.it/abcdefg", "pinterest"),
    ("https://www.threads.net/@user/post/Cabcdef", "threads"),
    ("https://shopee.vn/i/123.456", "shopee_video"),
])
def test_platform_detection(url: str, key: str) -> None:
    adapter, is_generic = registry.resolve(url)
    assert adapter is not None and not is_generic, url
    assert adapter.key == key


def test_generic_fallback_for_unknown_site() -> None:
    adapter, is_generic = registry.resolve("https://some-random-site.example/video/1")
    assert is_generic and adapter.key == "generic"


def test_dongbao_not_claimed_until_verified() -> None:
    """ĐôngBao: chưa xác minh tên miền → KHÔNG được nhận bừa."""
    adapter, is_generic = registry.resolve("https://dongbao.example/watch/1")
    assert is_generic  # rơi về generic, không phải adapter 'dongbao' supported
    dong = registry.get("dongbao")
    assert dong is not None and dong.status == SupportStatus.UNSUPPORTED


def test_netflix_official_only_and_blocked() -> None:
    nf = registry.get("netflix")
    assert nf and nf.status == SupportStatus.OFFICIAL_ONLY
    assert nf.download_allowed is False


def test_recognized_is_not_supported() -> None:
    """Instagram được NHẬN DIỆN nhưng trạng thái là needs-authentication, không phải supported."""
    ig = registry.get("instagram")
    assert ig and ig.can_handle("https://www.instagram.com/reel/abc/")
    assert ig.status == SupportStatus.NEEDS_AUTHENTICATION


@pytest.mark.parametrize("bad", [
    "", "not a url", "javascript:alert(1)", "ftp://example.com/file",
    "http://", "https://", "htp:/typo.example/x", "data:text/html,<script>",
])
def test_invalid_urls_rejected(bad: str) -> None:
    with pytest.raises(InvalidURLError):
        validate_url(bad)


@pytest.mark.parametrize("internal", [
    "http://localhost/video",
    "http://127.0.0.1:8000/x",
    "http://10.0.0.5/video",
    "http://192.168.1.1/admin",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/video",
])
def test_ssrf_protection(internal: str) -> None:
    with pytest.raises(ForbiddenHostError):
        validate_url(internal)
