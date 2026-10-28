"""Các adapter nền tảng cụ thể.

Trạng thái hỗ trợ được khai báo THÀNH PHẦN và trung thực dựa trên khả năng
thực tế của yt-dlp tại thời điểm phát triển (yt-dlp 2026.10.x). Không đánh dấu
Supported chỉ vì URL được nhận diện — cần test thực tế mới nâng cấp trạng thái.
"""
from __future__ import annotations

import re

from backend.adapters.base import BaseAdapter
from backend.models.schemas import SupportStatus


class YouTubeAdapter(BaseAdapter):
    key = "youtube"
    display_name = "YouTube"
    status = SupportStatus.SUPPORTED
    domains = ("youtube.com", "youtu.be", "music.youtube.com", "www.youtube.com")
    url_patterns = (
        re.compile(r"https?://(www\.|m\.)?(youtube\.com/watch\?v=[\w-]{11}|youtu\.be/[\w-]{11})"),
        re.compile(r"https?://music\.youtube\.com/watch\?v="),
    )
    description_vi = "Video, Shorts và playlist YouTube."
    conditions_vi = ("Hỗ trợ video công khai và video bạn có quyền. Video riêng tư/giới hạn tuổi "
                     "cần cookie cục bộ hợp lệ. Không vượt DRM YouTube Premium/Originals.")
    max_resolution = None  # tùy nguồn (tới 4K/8K nếu nguồn cung cấp)


class FacebookAdapter(BaseAdapter):
    key = "facebook"
    display_name = "Facebook"
    status = SupportStatus.LIMITED
    domains = ("facebook.com", "fb.watch", "m.facebook.com", "web.facebook.com")
    description_vi = "Video công khai trên Facebook (watch, reel, fb.watch)."
    conditions_vi = ("Chỉ hoạt động ổn định với video CÔNG KHAI. Video trong nhóm kín/trang cá nhân "
                     "yêu cầu đăng nhập → trạng thái needs-authentication khi dùng cookie. "
                     "Hay thay đổi theo phía Facebook.")


class TikTokAdapter(BaseAdapter):
    key = "tiktok"
    display_name = "TikTok"
    status = SupportStatus.SUPPORTED
    domains = ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com")
    description_vi = "Video TikTok công khai."
    conditions_vi = "Một số region/URL rút gọn có thể cần thử lại hoặc cập nhật yt-dlp."


class DouyinAdapter(BaseAdapter):
    key = "douyin"
    display_name = "Douyin (抖音)"
    status = SupportStatus.LIMITED
    domains = ("douyin.com", "iesdouyin.com")
    description_vi = "Video Douyin công khai (nền tảng nội địa Trung Quốc của TikTok)."
    conditions_vi = ("Thường cần yt-dlp phiên bản mới; một số nội dung giới hạn khu vực "
                     "hoặc yêu cầu xác minh thiết bị.")


class BilibiliAdapter(BaseAdapter):
    key = "bilibili"
    display_name = "Bilibili (哔哩哔哩)"
    status = SupportStatus.LIMITED
    domains = ("bilibili.com", "b23.tv", "m.bilibili.com")
    description_vi = "Video Bilibili công khai."
    conditions_vi = ("Chất lượng cao (>1080p) và nội dung premium cần tài khoản đăng nhập hợp lệ "
                     "(cookie cục bộ). Giới hạn khu vực có thể áp dụng.")


class InstagramAdapter(BaseAdapter):
    key = "instagram"
    display_name = "Instagram"
    status = SupportStatus.NEEDS_AUTHENTICATION
    domains = ("instagram.com", "instagr.am")
    description_vi = "Reels/video Instagram."
    conditions_vi = ("Instagram thường yêu cầu đăng nhập để xem và tải. Ứng dụng chỉ cho phép "
                     "dùng cookie CỤC BỘ do chính người dùng cung cấp cho nội dung họ có quyền.")
    needs_authentication = True


class TwitterAdapter(BaseAdapter):
    key = "twitter"
    display_name = "X (Twitter)"
    status = SupportStatus.LIMITED
    domains = ("twitter.com", "x.com")
    description_vi = "Video công khai trên X/Twitter."
    conditions_vi = ("Tweet riêng tư hoặc tài khoản khóa cần đăng nhập (cookie cục bộ). "
                     "API thay đổi thường xuyên, cần yt-dlp mới.")


class RedditAdapter(BaseAdapter):
    key = "reddit"
    display_name = "Reddit"
    status = SupportStatus.SUPPORTED
    domains = ("reddit.com", "redd.it", "old.reddit.com")
    description_vi = "Video nhúng/link trực tiếp trong bài viết Reddit."
    conditions_vi = "Nội dung bị xóa hoặc subreddit riêng tư sẽ không tải được."


class VimeoAdapter(BaseAdapter):
    key = "vimeo"
    display_name = "Vimeo"
    status = SupportStatus.LIMITED
    domains = ("vimeo.com", "player.vimeo.com")
    description_vi = "Video Vimeo công khai."
    conditions_vi = "Video private/password cần quyền truy cập hợp lệ."


class DailymotionAdapter(BaseAdapter):
    key = "dailymotion"
    display_name = "Dailymotion"
    status = SupportStatus.SUPPORTED
    domains = ("dailymotion.com", "dai.ly")
    description_vi = "Video Dailymotion công khai."


class PinterestAdapter(BaseAdapter):
    key = "pinterest"
    display_name = "Pinterest"
    status = SupportStatus.LIMITED
    domains = ("pinterest.com", "pin.it", "it.pinterest.com")
    description_vi = "Video Pin công khai."
    conditions_vi = "Chỉ pin dạng video; ảnh/idea pin không áp dụng."


class ThreadsAdapter(BaseAdapter):
    key = "threads"
    display_name = "Threads"
    status = SupportStatus.LIMITED
    domains = ("threads.net", "www.threads.net", "threads.com")
    description_vi = "Video công khai trên Threads."
    conditions_vi = "Hỗ trợ còn hạn chế, phụ thuộc phiên bản yt-dlp gần nhất."


class ShopeeVideoAdapter(BaseAdapter):
    key = "shopee_video"
    display_name = "Shopee Video"
    status = SupportStatus.UNSUPPORTED
    domains = ("shopee.vn", "shopee.com", "s.shopee.vn", "video.shopee.vn")
    description_vi = "Shopee Video."
    conditions_vi = ("Chưa có extractor tương thích ổn định trong yt-dlp. Trang chủ Shopee là "
                     "sàn thương mại điện tử, nội dung video nằm sau API riêng và điều khoản sử dụng. "
                     "Để trống chức năng thay vì giả mạo kết quả.")


class DongBaoAdapter(BaseAdapter):
    key = "dongbao"
    display_name = "Đông Báo / ĐôngBao"
    status = SupportStatus.UNSUPPORTED
    domains = ()  # Chưa xác minh được tên miền chính thức.
    description_vi = "Nền tảng 'ĐôngBao/Đông Báo' theo yêu cầu người dùng."
    conditions_vi = ("CẦN XÁC MINH: chưa xác định chắc chắn tên miền và bản chất nền tảng "
                     "(có thể nhầm với dongphim/báo điện tử). Không bật adapter khi chưa xác minh; "
                     "người dùng cung cấp URL mẫu thì hệ thống generic extractor sẽ thử phân tích "
                     "và báo cáo trung thực kết quả.")

    def can_handle(self, url: str) -> bool:
        return False  # an toàn: không nhận bừa


class NetflixAdapter(BaseAdapter):
    key = "netflix"
    display_name = "Netflix"
    status = SupportStatus.OFFICIAL_ONLY
    domains = ("netflix.com",)
    description_vi = "Netflix (dịch vụ DRM)."
    conditions_vi = ("CHỈ hỗ trợ tính năng tải ngoại tuyến CHÍNH THỨC của ứng dụng Netflix. "
                     "Không phá DRM, không trích xuất khóa giải mã, không vượt xác thực. "
                     "Ứng dụng này từ chối mọi URL Netflix.")
    supports_audio_only = False

    @property
    def download_allowed(self) -> bool:
        return False


class GenericWebsiteAdapter(BaseAdapter):
    """Fallback cho các website video công khai khác (HTML5 video, HLS công khai...)."""
    key = "generic"
    display_name = "Website công khai khác"
    status = SupportStatus.LIMITED
    relies_on_generic = True
    description_vi = "Những trang web chứa video công khai mà yt-dlp generic extractor xử lý được."
    conditions_vi = ("Kết quả phụ thuộc cấu trúc trang. Trang dùng DRM/paywall/login bắt buộc "
                     "sẽ KHÔNG hoạt động — đây là giới hạn kỹ thuật thật, không phải lỗi app.")

    def can_handle(self, url: str) -> bool:
        return True  # fallback cuối cùng


ADAPTERS: list[BaseAdapter] = [
    YouTubeAdapter(),
    FacebookAdapter(),
    TikTokAdapter(),
    DouyinAdapter(),
    BilibiliAdapter(),
    InstagramAdapter(),
    TwitterAdapter(),
    RedditAdapter(),
    VimeoAdapter(),
    DailymotionAdapter(),
    PinterestAdapter(),
    ThreadsAdapter(),
    ShopeeVideoAdapter(),
    DongBaoAdapter(),
    NetflixAdapter(),
    GenericWebsiteAdapter(),
]
