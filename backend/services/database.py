"""SQLite lưu hàng đợi và lịch sử (aiosqlite).

- Task được persist để không mất khi restart; task đang chạy khi shutdown
  sẽ chuyển về 'queued'/'failed' tùy trạng thái đĩa thật.
- History: chỉ ghi COMPLETED với file đã xác minh tồn tại.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import aiosqlite

from backend.config import settings
from backend.models.schemas import DownloadOptions, TaskOut, TaskProgress, TaskState

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    platform_key TEXT NOT NULL,
    title TEXT DEFAULT '',
    state TEXT NOT NULL,
    options_json TEXT NOT NULL,
    progress_json TEXT DEFAULT '{}',
    error_json TEXT,
    file_path TEXT,
    file_size INTEGER,
    attempts INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    platform_key TEXT NOT NULL,
    title TEXT,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    completed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
CREATE INDEX IF NOT EXISTS idx_history_completed ON history(completed_at DESC);
"""


def _now() -> float:
    return time.time()


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = str(path or settings.db_path)

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self) -> None:
        if getattr(self, "db", None):
            await self.db.close()

    # ---------------- tasks ----------------
    async def insert_task(self, task: TaskOut) -> None:
        await self.db.execute(
            "INSERT INTO tasks (id,url,platform_key,title,state,options_json,progress_json,"
            "error_json,file_path,file_size,attempts,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task.id, task.url, task.platform_key, task.title, task.state.value,
             task.options.model_dump_json(), task.progress.model_dump_json(),
             json.dumps(task.error) if task.error else None,
             task.file_path, task.file_size, task.attempts,
             _ts_to_f(task.created_at), _ts_to_f(task.updated_at)),
        )
        await self.db.commit()

    async def update_task(self, task: TaskOut) -> None:
        await self.db.execute(
            "UPDATE tasks SET title=?, state=?, progress_json=?, error_json=?, "
            "file_path=?, file_size=?, attempts=?, updated_at=? WHERE id=?",
            (task.title, task.state.value, task.progress.model_dump_json(),
             json.dumps(task.error) if task.error else None,
             task.file_path, task.file_size, task.attempts, _now(), task.id),
        )
        await self.db.commit()

    async def get_task(self, task_id: str) -> TaskOut | None:
        cur = await self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
        return _row_to_task(row) if row else None

    async def list_tasks(self) -> list[TaskOut]:
        cur = await self.db.execute("SELECT * FROM tasks ORDER BY created_at ASC")
        rows = await cur.fetchall()
        return [_row_to_task(r) for r in rows]

    async def delete_task(self, task_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def recover_interrupted(self) -> int:
        """Sau khi khởi động lại: task đang chạy dở → queued để chạy tiếp."""
        cur = await self.db.execute(
            "UPDATE tasks SET state='queued', updated_at=? "
            "WHERE state IN ('downloading','analyzing','processing')", (_now(),))
        await self.db.commit()
        return cur.rowcount

    # ---------------- history ----------------
    async def add_history(self, *, task_id: str, url: str, platform_key: str,
                          title: str, file_path: str, file_size: int) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO history (id,url,platform_key,title,file_path,file_size,completed_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (task_id, url, platform_key, title, file_path, file_size, _now()))
        await self.db.commit()

    async def list_history(self, limit: int = 200) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM history ORDER BY completed_at DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def find_duplicate(self, url: str) -> dict | None:
        cur = await self.db.execute(
            "SELECT * FROM history WHERE url=? ORDER BY completed_at DESC LIMIT 1", (url,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_history(self, history_id: str) -> bool:
        """Xóa MỤC LỊCH SỬ — KHÔNG xóa file gốc (theo yêu cầu)."""
        cur = await self.db.execute("DELETE FROM history WHERE id=?", (history_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def count_by_state(self) -> dict[str, int]:
        cur = await self.db.execute("SELECT state, COUNT(*) c FROM tasks GROUP BY state")
        rows = await cur.fetchall()
        return {r["state"]: r["c"] for r in rows}


def _ts_to_f(ts: str) -> float:
    try:
        return float(ts)
    except (TypeError, ValueError):
        return _now()


def _row_to_task(row) -> TaskOut:
    opts = DownloadOptions(**json.loads(row["options_json"]))
    prog = TaskProgress(**json.loads(row["progress_json"] or "{}"))
    err = json.loads(row["error_json"]) if row["error_json"] else None
    return TaskOut(
        id=row["id"], url=row["url"], platform_key=row["platform_key"],
        title=row["title"] or "", state=TaskState(row["state"]), progress=prog,
        options=opts, error=err, file_path=row["file_path"], file_size=row["file_size"],
        created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        attempts=row["attempts"] or 0,
    )


def new_task_id() -> str:
    return uuid.uuid4().hex[:12]
