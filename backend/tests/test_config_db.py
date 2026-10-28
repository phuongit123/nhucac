"""Test cấu hình đường dẫn database (UMD_DB_PATH) và khả năng mở SQLite.

Tái hiện lỗi gốc: Path("") == Path(".") -> db trỏ tới thư mục hiện tại
-> sqlite3.OperationalError: unable to open database file khi lifespan gọi
await db.connect().
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.config import Settings, _resolve_db_path
from backend.services.database import Database


@pytest.fixture()
def clean_env(monkeypatch):
    """Xóa mọi biến UMD_* để test hành vi mặc định."""
    for k in list(__import__("os").environ):
        if k.startswith("UMD_"):
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ---------- 1. Không có UMD_DB_PATH ----------
def test_default_db_path_without_env(clean_env, tmp_path):
    clean_env.setenv("UMD_DATA_DIR", str(tmp_path / "data"))
    s = Settings()
    assert s.db_path == tmp_path / "data" / "umd.sqlite3"
    assert s.db_path.name.endswith(".sqlite3")
    # KHÔNG bao giờ là '.' hay thư mục
    assert str(s.db_path) != "."
    assert not s.db_path.is_dir()


def test_empty_umd_db_path_falls_back_to_data_dir(clean_env, tmp_path):
    """UMD_DB_PATH='' (rỗng) phải xử lý như không đặt."""
    clean_env.setenv("UMD_DATA_DIR", str(tmp_path / "data"))
    clean_env.setenv("UMD_DB_PATH", "")
    s = Settings()
    assert s.db_path == tmp_path / "data" / "umd.sqlite3"


def test_whitespace_umd_db_path_falls_back(clean_env, tmp_path):
    clean_env.setenv("UMD_DATA_DIR", str(tmp_path / "data"))
    clean_env.setenv("UMD_DB_PATH", "   ")
    s = Settings()
    assert s.db_path == tmp_path / "data" / "umd.sqlite3"


# ---------- 2. Có UMD_DB_PATH ----------
def test_custom_umd_db_path_is_used(clean_env, tmp_path):
    target = tmp_path / "custom" / "mydb.sqlite3"
    clean_env.setenv("UMD_DB_PATH", str(target))
    p = _resolve_db_path()
    assert p == target
    s = Settings()
    assert s.db_path == target
    # ensure_dirs phải tạo thư mục cha chưa tồn tại
    s.ensure_dirs()
    assert target.parent.is_dir()


def test_umd_db_path_pointing_to_directory(clean_env, tmp_path):
    """Nếu người dùng cấu hình nhầm thành THƯ MỤC -> bổ sung file con,
    tránh 'unable to open database file'."""
    d = tmp_path / "dbdir"
    d.mkdir()
    clean_env.setenv("UMD_DB_PATH", str(d))
    s = Settings()
    assert s.db_path == d / "umd.sqlite3"
    assert not s.db_path.is_dir()


# ---------- 3. Database.__init__ không nhận thư mục/rỗng ----------
def test_database_init_rejects_directory(clean_env, tmp_path):
    data = tmp_path / "data"
    db = Database(tmp_path)  # truyền thư mục hiện tại
    assert Path(db.path).is_file() or not Path(db.path).exists()
    assert not Path(db.path).is_dir()
    assert db.path.endswith("umd.sqlite3")


def test_database_init_empty_string(clean_env, tmp_path):
    clean_env.setenv("UMD_DATA_DIR", str(tmp_path / "data"))
    s = Settings()
    db = Database("")
    assert not Path(db.path).is_dir()
    assert str(db.path) not in {"", "."}


# ---------- 4. Mở DB thật trong thư mục tạm (async) ----------
async def test_connect_creates_parent_dirs_and_file(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "test.sqlite3"
    assert not nested.parent.exists()
    db = Database(nested)
    await db.connect()          # không được ném OperationalError
    try:
        assert nested.exists()
        # xác minh file SQLite thật
        con = sqlite3.connect(str(nested))
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"tasks", "history"} <= tables
    finally:
        await db.close()


async def test_connect_does_not_overwrite_existing_db(tmp_path):
    """Không ghi đè database hiện có (yêu cầu giữ dữ liệu người dùng)."""
    p = tmp_path / "keep.sqlite3"
    db1 = Database(p)
    await db1.connect()
    await db1.add_history(url="https://example.com/v1", platform_key="youtube",
                          title="Old Record", file_path=str(p), file_size=1,
                          task_id="abc123")
    await db1.close()

    db2 = Database(p)
    await db2.connect()
    rows = await db2.list_history()
    await db2.close()
    assert len(rows) == 1
    assert rows[0]["title"] == "Old Record"


def test_settings_post_init_fixes_dot_path(clean_env, tmp_path):
    """Chặn trực tiếp regression: db_path='.' phải bị thay bằng file mặc định."""
    clean_env.setenv("UMD_DATA_DIR", str(tmp_path / "data"))
    s = Settings(db_path=Path("."))
    assert s.db_path == tmp_path / "data" / "umd.sqlite3"
