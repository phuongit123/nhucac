"""Các lớp lỗi nghiệp vụ dùng chung.

Mỗi lỗi mang theo mã lỗi ổn định (error_code) để frontend hiển thị
thông báo tiếng Việt có hướng khắc phục, và HTTP status phù hợp.
"""
from __future__ import annotations


class AppError(Exception):
    error_code = "internal_error"
    http_status = 500
    # Hướng khắc phục mặc định (tiếng Việt) — frontend có thể dịch.
    hint_vi = "Lỗi không xác định. Hãy thử lại hoặc kiểm tra log backend."

    def __init__(self, message: str = "", *, details: dict | None = None) -> None:
        super().__init__(message or self.__doc__)
        self.message = message or self.__doc__ or self.error_code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "hint_vi": self.hint_vi,
            "details": self.details,
        }


class InvalidURLError(AppError):
    error_code = "invalid_url"
    http_status = 400
    hint_vi = "URL không hợp lệ. Hãy sao chép liên kết đầy đủ từ trình duyệt và thử lại."


class UnsupportedPlatformError(AppError):
    error_code = "unsupported_platform"
    http_status = 400
    hint_vi = ("Nền tảng này chưa được hỗ trợ tải xuống trực tiếp. "
               "Xem danh sách nền tảng được hỗ trợ trong mục About/Settings.")


class ForbiddenHostError(AppError):
    error_code = "forbidden_host"
    http_status = 400
    hint_vi = "URL trỏ tới địa chỉ nội bộ hoặc bị chặn vì lý do bảo mật (chống SSRF)."


class VideoUnavailableError(AppError):
    error_code = "video_unavailable"
    http_status = 404
    hint_vi = "Video đã bị xóa, đặt riêng tư hoặc không tồn tại. Hãy kiểm tra lại liên kết."


class AuthenticationRequiredError(AppError):
    error_code = "authentication_required"
    http_status = 401
    hint_vi = ("Nội dung yêu cầu đăng nhập. Ứng dụng này không tự động vượt qua "
               "cơ chế xác thực. Bạn có thể cung cấp cookie cục bộ hợp lệ cho "
               "nội dung mà bạn có quyền truy cập (Settings).")


class FormatNotAvailableError(AppError):
    error_code = "format_not_available"
    http_status = 422
    hint_vi = "Nguồn không cung cấp chất lượng/định dạng đã chọn. Hãy chọn định dạng khác trong danh sách khả dụng."


class NetworkError(AppError):
    error_code = "network_error"
    http_status = 502
    hint_vi = "Lỗi mạng hoặc timeout khi truy cập nguồn. Kiểm tra kết nối Internet rồi thử lại."


class ExtractionOutdatedError(AppError):
    error_code = "extractor_outdated"
    http_status = 502
    hint_vi = ("Trình trích xuất (yt-dlp) có thể đã cũ so với thay đổi của nền tảng. "
               "Nâng cấp: pip install -U yt-dlp")


class DependencyMissingError(AppError):
    error_code = "dependency_missing"
    http_status = 500
    hint_vi = "Thiếu FFmpeg hoặc dependency cần thiết. Xem docs/FFMPEG_INSTALL.md để cài đặt."


class InsufficientDiskSpaceError(AppError):
    error_code = "insufficient_disk_space"
    http_status = 507
    hint_vi = "Không đủ dung lượng ổ đĩa cho tác vụ tải. Xóa bớt file hoặc đổi thư mục lưu."


class TaskNotFoundError(AppError):
    error_code = "task_not_found"
    http_status = 404
    hint_vi = "Không tìm thấy tác vụ. Nó có thể đã bị xóa khỏi hàng đợi."


class TaskCancelledError(AppError):
    error_code = "task_cancelled"
    http_status = 200
    hint_vi = "Tác vụ đã được người dùng hủy."


class QueueFullError(AppError):
    error_code = "queue_full"
    http_status = 429
    hint_vi = "Hàng đợi đã đầy. Hãy chờ một số tác vụ hoàn tất rồi thêm lại."


class DuplicateFileWarning(AppError):
    error_code = "duplicate_file"
    http_status = 200
    hint_vi = "File trùng lặp đã tồn tại (tùy chọn bỏ qua hoặc tải tiếp)."
