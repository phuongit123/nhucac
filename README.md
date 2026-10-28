# Universal Media Downloader

Ứng dụng tải video đa nền tảng: FastAPI backend + yt-dlp engine + kiến trúc adapter, SQLite (aiosqlite) cho hàng đợi/lịch sử, SSE cho tiến độ thời gian thực.

## Yêu cầu
- Python **3.10 – 3.12** khuyến nghị (tránh bản quá mới nếu dependency chưa tương thích).
- FFmpeg (bắt buộc để ghép video+audio và chuyển đổi định dạng): `winget install Gyan.FFmpeg` hoặc tải từ ffmpeg.org rồi thêm vào PATH.
- Node.js 18+ (chỉ khi chạy frontend dev).

## Chạy trên Windows — cách ĐÃ ĐƯỢC KIỂM CHỨNG

> **Lưu ý quan trọng:** các lệnh bên dưới là **CMD (cmd.exe)**, không phải PowerShell.
> - Mỗi lệnh chạy **một dòng riêng**, nhấn Enter xong mới gõ lệnh tiếp. **Không** dùng dấu `;` nối lệnh trong CMD (`;` chỉ dùng được trong PowerShell).
> - Dòng bắt đầu bằng `rem`/`#` là chú thích — **không copy vào terminal**.
> - Phải giải nén `workspace.tar` vào thư mục có đường dẫn **không chứa dấu `;` và khoảng trắng lạ**, ví dụ `C:\projects\umd`. Nếu giải nén thành `...\workspace.tar(3)\`, venv sẽ bị từ chối tạo — hãy giải nén đúng bằng 7-Zip vào `C:\projects\umd`.

```bat
cd /d "C:\projectD-acl-out\workspace.tar(3)"
py -3.12 -m venv .venv
".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8756
```

> Đường dẫn của bạn chứa `(3)` — **phải bọc dấu ngoặc kép `"` quanh lệnh `cd`**, nếu không CMD sẽ hiểu sai đường dẫn. Nếu `py -3.12` báo không tìm thấy, hãy cài Python 3.12 từ python.org (bỏ chọn bản 3.15 — quá mới, yt-dlp/FastAPI chưa được kiểm chứng) và thay bằng `py -3.12` hoặc `python` sau khi đã bật đúng phiên bản.

Mở trình duyệt: `http://127.0.0.1:8756/api/health` (backend), `http://127.0.0.1:8756/docs` (Swagger API).

Hoặc chạy script tự động (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
scripts\start-backend.bat
```

### Lỗi thường gặp
| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| `Refusing to create a venv ... contains the PATH separator ;` | Nối 2 lệnh bằng `;` trong CMD, hoặc đường dẫn project chứa ký tự lạ | Chạy từng lệnh một; giải nén project vào `C:\projects\umd` |
| `Could not open requirements file` | Đang đứng sai thư mục (phải là thư mục gốc có `requirements.txt`) | `cd /d C:\projects\umd` rồi chạy lại |
| `No module named uvicorn` | Chưa cài dependency (hoặc pip cài user do chưa activate venv) | `.venv\Scripts\activate` trước, rồi `python -m pip install -r requirements.txt` |
| `'#' is not recognized...` | Copy cả dòng chú thích vào CMD | Không copy dòng bắt đầu bằng `#`/`rem` |
| `sqlite3.OperationalError: unable to open database file` | Bản cũ: DB path trỏ vào thư mục. Đã sửa: mặc định `<data_dir>\umd.sqlite3`, tự tạo thư mục cha | Cập nhật code mới nhất; tùy chọn đặt `UMD_DB_PATH=C:\path\to\umd.sqlite3` |

## Cấu hình (xem `.env.example`)
`UMD_DB_PATH`, `UMD_DATA_DIR`, `UMD_DOWNLOAD_DIR`, `UMD_FFMPEG_PATH`, `UMD_MAX_CONCURRENT`.

## Test
```bat
python -m pytest                                  # toàn bộ
python -m pytest backend/tests/test_config_db.py backend/tests/test_engine.py -v
```
Cần `pytest-asyncio` và `anyio` (đã nằm trong requirements.txt; pytest.ini dùng `asyncio_mode = auto`).

## macOS / Linux
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8756
```

## Frontend
Thư mục `frontend/` hiện **chưa hoàn thiện** (xem mục Trạng thái bên dưới). Backend độc lập và có Swagger tại `/docs`.

## Trạng thái tính năng
- ✅ Hoàn thành & có test: adapter registry + phân loại URL, analyze/format (mock), hàng đợi + retry + cancel, SQLite history, SSE progress, SSRF/path-traversal guard, tên file Unicode an toàn, kiểm tra FFmpeg/disk.
- ⚠️ Limited: TikTok/Douyin/Bilibili/Threads/Shopee phụ thuộc yt-dlp extractor hiện hành; Instagram/X cần cookie nếu nội dung đăng nhập.
- ❌ Unsupported theo chính sách: Netflix/DRM — chỉ hướng dẫn phương thức official của nhà cung cấp.
- ⛔ Chưa xong: UI React (frontend), E2E download với mạng thật.

## Thêm adapter mới
Xem `backend/adapters/base.py`: kế thừa `BaseAdapter`, triển khai `can_handle/get_metadata/get_available_formats/create_download_task/get_capabilities`, đăng ký vào `ADAPTERS` trong `backend/adapters/registry.py`, thêm test nhận diện URL vào `backend/tests/test_adapters.py`.
