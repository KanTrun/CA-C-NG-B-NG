# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test cột BOOLEAN của Postgres — không được ghi Python `int` (0/1).

Bug QA đợt 3 (2026-09-27): `GET /api/v1/chat/scheduler` và
`POST /api/v1/chat/conversations/{id}/mute` trả HTTP 500 **trên production**
(Postgres) nhưng PASS trên SQLite local.

Nguyên nhân gốc: migration tạo cột kiểu BOOLEAN
(`0001_initial_tables.py`: `pinned`, `la_sinh_vien`;
`0008_add_chat_tables.py`: `is_locked`, `muted`, `is_unsent`), trong khi code
ghi Python `int` — `0` / `1` / `1 if x else 0`. SQLite chấp nhận (INTEGER đa
hình) nên test local xanh; psycopg3 gửi tham số kiểu `smallint` và Postgres
từ chối với `column "..." is of type boolean but expression is of type
smallint`.

Test này KHÔNG cần Postgres thật: nó chạy trên SQLite nhưng bọc connection
bằng proxy ghi lại `(sql, params)` để soi **kiểu Python** của tham số — đúng
thứ quyết định Postgres chấp nhận hay từ chối.
"""

from __future__ import annotations

from typing import Any

import pytest
from ca_api import persist


class _SpyCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def description(self) -> Any:
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def lastrowid(self) -> Any:
        return getattr(self._cursor, "lastrowid", None)

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    def __iter__(self) -> Any:
        return iter(self._cursor)


class _SpyConnection:
    """Proxy quanh connection thật: ghi lại mọi (sql, params) đi qua."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.log: list[tuple[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def execute(self, sql: str, params: Any = None) -> _SpyCursor:
        self.log.append((sql, params))
        if params is None:
            return _SpyCursor(self._conn.execute(sql))
        return _SpyCursor(self._conn.execute(sql, params))

    def executemany(self, sql: str, seq: Any) -> None:
        self.log.append((sql, seq))
        self._conn.executemany(sql, seq)

    def executescript(self, script: str) -> Any:
        return self._conn.executescript(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def __enter__(self) -> _SpyConnection:
        self._conn.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._conn.__exit__(*args)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Chạy hàm persist trên connection thật nhưng có ghi log SQL/params."""
    real_conn = persist._conn
    holder: dict[str, _SpyConnection] = {}

    def factory() -> _SpyConnection:
        if "cx" not in holder:
            holder["cx"] = _SpyConnection(real_conn())
        return holder["cx"]

    monkeypatch.setattr(persist, "_conn", factory)
    return holder


def _tim_conv_scheduler(log: list[tuple[str, Any]]) -> Any:
    """Câu INSERT vào chat_conversations của hội thoại scheduler.

    Nhận diện qua `conv_id` trong tham số (`conv_scheduler_...`) — SQL dùng
    placeholder `?` nên tên "AI Scheduler" nằm ở params, không ở câu lệnh.
    """
    for sql, params in log:
        flat = " ".join(sql.split())
        if "INSERT INTO chat_conversations" in flat and params:
            if str(params[0]).startswith("conv_scheduler_"):
                return params
    raise AssertionError("không thấy INSERT chat_conversations của hội thoại scheduler")


def test_is_locked_khong_duoc_la_int(spy: Any) -> None:
    """`chat_conversations.is_locked` là BOOLEAN → tham số phải là `bool`.

    Trước fix: giá trị `0` (int) → Postgres báo
    'column "is_locked" is of type boolean but expression is of type smallint'.
    """
    persist.chat_get_or_create_scheduler_direct("quan_01", "nv_01")
    params = _tim_conv_scheduler(spy["cx"].log)
    # Thứ tự cột trong câu INSERT của hàm: id, store_id, type, display_name,
    # avatar_url, is_locked, created_at, updated_at
    is_locked = params[5]
    assert isinstance(is_locked, bool), (
        f"is_locked phải là bool, nhận {type(is_locked).__name__}={is_locked!r} "
        "→ Postgres từ chối, HTTP 500"
    )


def test_mute_khong_duoc_la_int(spy: Any) -> None:
    """`chat_participants.muted` là BOOLEAN → tham số phải là `bool`."""
    for value in (True, False):
        persist.chat_conversation_mute("conv_test", "nv_01", value)
    calls = [
        p
        for sql, p in spy["cx"].log
        if "UPDATE chat_participants SET muted" in " ".join(sql.split())
    ]
    assert len(calls) == 2, "phải thấy 2 lần gọi mute"
    for params in calls:
        assert isinstance(params[0], bool), (
            f"muted phải là bool, nhận {type(params[0]).__name__}={params[0]!r}"
        )


def test_scheduler_tao_bot_ai_scheduler_truoc_khi_moi(spy: Any) -> None:
    """Bot `ai_scheduler` phải có trong `users` trước khi chèn participant.

    Migration 0008 khai `chat_participants.nv_id` có FK → `users.nv_id`. Trên
    Postgres, chèn participant cho bot chưa tồn tại sẽ vi phạm FK → HTTP 500
    (đường này không bật FK trên SQLite nên local vẫn xanh).
    """
    persist.chat_get_or_create_scheduler_direct("quan_01", "nv_02")
    flat = [" ".join(sql.split()) for sql, _ in spy["cx"].log]
    co_users = next((i for i, s in enumerate(flat) if "INSERT INTO users" in s), None)
    co_part = next(
        (i for i, s in enumerate(flat) if "chat_participants" in s and "INSERT" in s),
        None,
    )
    assert co_users is not None, "phải INSERT users(ai_scheduler) để thoả FK"
    assert co_part is not None, "phải INSERT chat_participants"
    assert co_users < co_part, "phải INSERT users TRƯỚC chat_participants"
