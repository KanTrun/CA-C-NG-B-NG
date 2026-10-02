"""Persistent quán store backed by PostgreSQL or a local SQLite file."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar, Token

try:
    from datetime import UTC, datetime, timedelta, timezone
except ImportError:
    from datetime import datetime, timedelta, timezone

    UTC = timezone.utc
from pathlib import Path
from typing import Any, cast

from ca_api.audit_trace import ActorType, resolve_actor_type

ROOT = Path(__file__).resolve().parents[4]

_INITIALIZED = False
_AUDIT_REQUEST_STATE: ContextVar[dict[str, bool] | None] = ContextVar(
    "audit_request_state",
    default=None,
)

try:
    import psycopg

    _DB_INTEGRITY_ERRORS: tuple[type[Exception], ...] = (
        sqlite3.IntegrityError,
        psycopg.IntegrityError,
    )
except ImportError:
    _DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

# Giờ Việt Nam — dùng cho các khoá kv theo ngày (điểm danh, tổng kết...).
_VN_TZ = timezone(timedelta(hours=7))

# ── Encryption for sensitive data (OAuth tokens) ──────────────────────────
# Sử dụng Fernet (AES-128-GCM) từ cryptography. Key lấy từ env NHIPQUAN_ENCRYPTION_KEY
# (base64-encoded 32 bytes). Nếu chưa có, tự sinh và cảnh báo (chỉ dev).
#
# Fernet được dựng LAZY (lần mã hoá/giải mã đầu tiên), KHÔNG phải lúc import:
# lifespan của API nạp `.env` SAU khi import module — đọc key lúc import thì key
# trong `.env` không bao giờ được dùng, token mã hoá bằng key tạm và hỏng sau
# restart (đúng lỗi "Cần kết nối lại" sau mỗi lần khởi động lại API).
_FernetCls: Any
try:
    from cryptography.fernet import Fernet as _FernetCls

    _FERNET_IMPORT_OK = True
except ImportError:  # pragma: no cover — cryptography là dependency bắt buộc
    _FernetCls = None
    _FERNET_IMPORT_OK = False

_FERNET: Any = None
_FERNET_KEY: str | None = None
_FERNET_WARNED = False


def _fernet() -> Any:
    """Fernet theo key HIỆN TẠI trong env. Cache theo giá trị key."""
    global _FERNET, _FERNET_KEY, _FERNET_WARNED
    if not _FERNET_IMPORT_OK or _FernetCls is None:
        raise RuntimeError("cryptography not installed; cannot encrypt")
    key = os.environ.get("NHIPQUAN_ENCRYPTION_KEY")
    if _FERNET is None or key != _FERNET_KEY:
        if key:
            _FERNET = _FernetCls(key.encode())
        else:
            # Dev fallback: sinh key tạm (KHÔNG dùng production)
            import warnings

            _FERNET = _FernetCls(_FernetCls.generate_key())
            if not _FERNET_WARNED:
                warnings.warn(
                    "NHIPQUAN_ENCRYPTION_KEY not set; using ephemeral key. "
                    "Tokens will be unreadable after restart. Set NHIPQUAN_ENCRYPTION_KEY in production.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _FERNET_WARNED = True
        _FERNET_KEY = key
    return _FERNET


def _encrypt(plaintext: str) -> str:
    """Mã hoá chuỗi nhạy cảm (OAuth token). Trả về base64 string."""
    return cast(str, _fernet().encrypt(plaintext.encode()).decode())


def _decrypt(ciphertext: str) -> str:
    """Giải mã chuỗi đã mã hoá."""
    return cast(str, _fernet().decrypt(ciphertext.encode()).decode())


USERS = (
    ("lan", "nhipquan", "quan_ly", "nv_01", "Lan — quản lý"),
    ("minh", "nhipquan", "nhan_vien", "nv_03", "Minh — ca sáng"),
    ("hung", "nhipquan", "chu_quan", "nv_02", "Hùng — chủ quán"),
)


# ── Mật khẩu ──────────────────────────────────────────────────────────────
# Bản đầu hash SHA256 trần, không salt. Khi chỉ có 3 tài khoản fixture thì đó
# là nợ chấp nhận được; từ lúc mở màn hình đăng ký thì nó thành lỗ hổng thật
# (cùng mật khẩu → cùng digest, tra bảng rainbow ra ngay). Nên chuyển sang
# PBKDF2-HMAC-SHA256 có salt riêng từng tài khoản — vẫn thuần stdlib.
#
# Cột `password_sha` giữ nguyên tên để không phải migrate; nó lưu:
#   - "pbkdf2_sha256$<vòng>$<salt hex>$<hash hex>"  (bản mới)
#   - "<sha256 hex>"                                 (bản cũ, vẫn đăng nhập được)
PBKDF2_VONG = int(
    os.environ.get(
        "NHIPQUAN_PBKDF2_VONG",
        "1000"
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("PYTEST_VERSION")
        else "240000",
    )
)
_PREFIX = "pbkdf2_sha256"

# Vai trò người tự đăng ký. KHÔNG bao giờ là quan_ly/chu_quan: nếu tự đăng ký
# mà lấy được vai quản lý thì bất kỳ ai cũng duyệt được ràng buộc và phát được
# mã điểm danh. Nâng vai là việc của chủ quán, làm ngoài luồng đăng ký.
VAI_TU_DANG_KY = "nhan_vien"
# Vai KHÔNG phải người: bot/agent nội bộ. Tài khoản bot `ai_scheduler` được tạo
# tự động để thoả khoá ngoại `chat_participants.nv_id → users.nv_id`, nhưng nó
# KHÔNG phải nhân sự — không được xuất hiện trong danh sách người, không được
# tính vào số nhân viên, không được nhận việc. Giữ một nguồn duy nhất ở đây;
# `ca_api.nhan_vien.VAI_KHONG_XEP_LICH` là chốt thứ hai cho pool xếp lịch.
VAI_BOT = {"ai_assistant"}
DEFAULT_STORE_ID = os.environ.get("NHIPQUAN_DEFAULT_STORE_ID", "quan_01").strip() or "quan_01"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Băm mật khẩu bằng PBKDF2-HMAC-SHA256 kèm salt riêng."""
    s = salt if salt is not None else os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), s, PBKDF2_VONG)
    return f"{_PREFIX}${PBKDF2_VONG}${s.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """So mật khẩu với giá trị đã lưu. Chấp nhận cả bản cũ SHA256 trần."""
    if stored.startswith(f"{_PREFIX}$"):
        try:
            _, vong_raw, salt_hex, hash_hex = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt_hex), int(vong_raw)
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(dk.hex(), hash_hex)
    # Bản cũ: so bằng compare_digest để không lộ thông tin qua thời gian so sánh.
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def db_path() -> Path:
    override = os.environ.get("NHIPQUAN_DB")
    return Path(override) if override else ROOT / "data" / "quan.db"


def _database_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


def _demo_seed_enabled() -> bool:
    return os.environ.get("NHIPQUAN_SEED_DEMO", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


class _PostgresRow(dict[str, Any]):
    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _NullCursor:
    """Cursor giả cho câu lệnh điều khiển giao dịch (COMMIT/ROLLBACK/BEGIN).

    Khi `_PostgresConnection.execute()` dịch COMMIT/ROLLBACK/BEGIN sang gọi
    method trên connection, không có cursor thật để trả về. Các caller theo
    phong cách SQLite (`cx.execute("COMMIT")`) không dùng giá trị trả về, nên
    một cursor rỗng là đủ — nhưng phải có đủ thuộc tính mà `_PostgresCursor`
    cần đọc (`rowcount`, `description`, `fetchone`, `fetchall`) để không vỡ
    nếu caller có kiểm tra.
    """

    description: Any = None
    rowcount: int = -1

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []


class _PostgresCursor:
    def __init__(self, cursor: Any, *, mapping: bool) -> None:
        self._cursor = cursor
        self._mapping = mapping

    @property
    def lastrowid(self) -> None:
        return None

    @property
    def description(self) -> Any:
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def _row(self, row: Any) -> Any:
        if row is None or not self._mapping:
            return row
        if not self._cursor.description:
            return row
        columns = [column.name for column in self._cursor.description]
        return _PostgresRow(zip(columns, row, strict=True))

    def fetchone(self) -> Any:
        return self._row(self._cursor.fetchone())

    def fetchall(self) -> list[Any]:
        return [self._row(row) for row in self._cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.row_factory: Any = None
        self.isolation_level: Any = None

    def __enter__(self) -> _PostgresConnection:
        self._connection.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._connection.__exit__(*args)

    def execute(self, query: str, params: Any = None) -> _PostgresCursor:
        sql = query.replace("BEGIN IMMEDIATE", "BEGIN").replace("?", "%s")
        # psycopg3 CHẶN câu lệnh điều khiển giao dịch qua cursor.execute():
        # `cursor.execute("COMMIT")` ném lỗi "can't execute COMMIT inside a
        # transaction block; use commit() instead" (hoặc tương tự). Nhiều hàm
        # trong persist.py gọi `cx.execute("COMMIT")` / `("ROLLBACK")` theo
        # phong cách SQLite, nên phải dịch sang method tương ứng — nếu không,
        # endpoint trả HTTP 500 trên Postgres (bug QA đợt 3: /chat/scheduler).
        stripped = sql.strip().rstrip(";").upper()
        if stripped == "COMMIT":
            self._connection.commit()
            return _PostgresCursor(_NullCursor(), mapping=False)
        if stripped == "ROLLBACK":
            self._connection.rollback()
            return _PostgresCursor(_NullCursor(), mapping=False)
        if stripped == "BEGIN":
            # psycopg tự mở transaction khi câu lệnh đầu tiên chạy → BEGIN là no-op.
            return _PostgresCursor(_NullCursor(), mapping=False)
        if "INSERT OR IGNORE INTO" in sql:
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "ON CONFLICT" not in sql:
                stripped_sql = sql.rstrip()
                if stripped_sql.endswith(";"):
                    sql = stripped_sql[:-1] + " ON CONFLICT DO NOTHING;"
                else:
                    sql = stripped_sql + " ON CONFLICT DO NOTHING"
        cursor = self._connection.execute(sql, params)
        return _PostgresCursor(cursor, mapping=self.row_factory is not None)

    def executemany(self, query: str, params_seq: Any) -> None:
        for params in params_seq:
            self.execute(query, params)

    def commit(self) -> None:
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def rollback(self) -> None:
        if hasattr(self._connection, "rollback"):
            self._connection.rollback()


def _conn() -> Any:
    url = _database_url()
    if url:
        import psycopg

        psycopg_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        return _PostgresConnection(psycopg.connect(psycopg_url))

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(path, timeout=30)
    cx.execute("PRAGMA journal_mode=WAL")
    # SQLite TẮT foreign key mặc định ⇒ `ON DELETE CASCADE` vô hiệu âm thầm,
    # xoá tài khoản Gmail sẽ bỏ lại token/email/nhãn/bộ lọc mồ côi. Bật tường
    # minh cho MỌI kết nối (pragma theo connection, không theo database).
    cx.execute("PRAGMA foreign_keys=ON")
    return cx


def acquire_write_lock(cx: Any, scope: str) -> None:
    """Giành quyền ghi độc quyền theo `scope` trong transaction hiện tại.

    Vì sao cần: SQLite có `BEGIN IMMEDIATE` để lấy write lock NGAY khi mở
    transaction. Postgres không có cú pháp tương đương — `_PostgresConnection`
    hạ nó xuống `BEGIN` (transaction thường), nên pattern đọc-rồi-ghi vẫn có
    khe TOCTOU: hai request cùng đọc "bàn còn trống" rồi cùng ghi.

    Dùng `pg_advisory_xact_lock` với khoá băm từ `scope` — đúng cơ chế
    `kv_mutate` đã dùng. Khoá tự nhả khi transaction kết thúc. Trên SQLite hàm
    này là no-op vì `BEGIN IMMEDIATE` đã lo việc đó.
    """
    if not _database_url():
        return
    lock_id = int.from_bytes(
        hashlib.sha256(scope.encode()).digest()[:8], byteorder="big", signed=True
    )
    cx.execute("SELECT pg_advisory_xact_lock(?)", (lock_id,))


_INITIALIZED_PATHS: set[str] = set()
_INIT_DB_LOCK = threading.Lock()


def init_db() -> None:
    p_str = str(db_path())
    if p_str in _INITIALIZED_PATHS:
        return
    with _INIT_DB_LOCK:
        if p_str in _INITIALIZED_PATHS:
            return
        _init_db_locked(p_str)


def _init_db_locked(p_str: str) -> None:
    global _INITIALIZED
    with _conn() as cx:
        acquire_write_lock(cx, "nhipquan_init_db")
        # Luôn chạy DDL IF NOT EXISTS — thêm bảng mới (kenh_bind) không bị kẹt
        # vì cờ _INITIALIZED sớm trên DB cũ.
        if not _database_url():
            cx.executescript(
                """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_sha TEXT NOT NULL,
                role TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                store_id TEXT NOT NULL DEFAULT 'quan_01'
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS kv (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                ai TEXT NOT NULL,
                hanh TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kenh_bind (
                channel TEXT NOT NULL,
                external_user_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (channel, external_user_id)
            );
            CREATE TABLE IF NOT EXISTS kenh_bind_code (
                code TEXT PRIMARY KEY,
                nv_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS menu_mon (
                id TEXT PRIMARY KEY,
                ten TEXT NOT NULL,
                gia INTEGER NOT NULL,
                an INTEGER NOT NULL DEFAULT 0,
                bom TEXT NOT NULL DEFAULT '{}',
                nhom TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS don_quay (
                id TEXT PRIMARY KEY,
                nv_id TEXT NOT NULL,
                trang_thai TEXT NOT NULL,
                thanh_toan TEXT NOT NULL,
                dong TEXT NOT NULL,
                ly_do_huy TEXT,
                luc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS copilot_draft_actions (
                action_id TEXT PRIMARY KEY,
                intent TEXT NOT NULL,
                status TEXT NOT NULL,
                store_id TEXT NOT NULL,
                created_by TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT NOT NULL,
                explanation TEXT NOT NULL,
                payload_diff TEXT NOT NULL,
                requires_confirmation INTEGER NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                executed_at TEXT,
                amended_from TEXT,
                amended_by TEXT
            );
            CREATE TABLE IF NOT EXISTS copilot_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                decision TEXT NOT NULL,
                payload_diff TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                latency_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS copilot_execution_receipts (
                store_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                outcome TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                PRIMARY KEY (store_id, action_id, idempotency_key)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_copilot_receipt_action
                ON copilot_execution_receipts(store_id, action_id);
            CREATE TABLE IF NOT EXISTS copilot_mail_delivery_receipts (
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                outcome TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                PRIMARY KEY (store_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS gmail_accounts (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                nv_id TEXT NOT NULL,
                email TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                is_primary INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gmail_accounts_store_nv ON gmail_accounts(store_id, nv_id, is_active);
            CREATE TABLE IF NOT EXISTS gmail_oauth_tokens (
                account_id TEXT PRIMARY KEY REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT,
                expires_at TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT '',
                token_type TEXT NOT NULL DEFAULT 'Bearer',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gmail_sync_state (
                account_id TEXT PRIMARY KEY REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                last_history_id TEXT,
                last_sync_at TEXT,
                sync_cursor TEXT,
                total_messages INTEGER NOT NULL DEFAULT 0,
                unread_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gmail_messages (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL,
                label_ids TEXT NOT NULL DEFAULT '[]',
                snippet TEXT NOT NULL DEFAULT '',
                from_email TEXT NOT NULL DEFAULT '',
                to_emails TEXT NOT NULL DEFAULT '[]',
                cc_emails TEXT NOT NULL DEFAULT '[]',
                subject TEXT NOT NULL DEFAULT '',
                body_text TEXT,
                body_html TEXT,
                internal_date TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_starred INTEGER NOT NULL DEFAULT 0,
                has_attachment INTEGER NOT NULL DEFAULT 0,
                raw_headers TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gmail_messages_account_thread ON gmail_messages(account_id, thread_id);
            CREATE INDEX IF NOT EXISTS idx_gmail_messages_account_date ON gmail_messages(account_id, internal_date DESC);
            CREATE INDEX IF NOT EXISTS idx_gmail_messages_unread ON gmail_messages(account_id, is_read, internal_date DESC);
            CREATE TABLE IF NOT EXISTS gmail_labels (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                label_type TEXT NOT NULL DEFAULT 'user',
                message_list_visibility TEXT NOT NULL DEFAULT 'show',
                label_list_visibility TEXT NOT NULL DEFAULT 'labelShow',
                color_background TEXT,
                color_text TEXT,
                total_messages INTEGER NOT NULL DEFAULT 0,
                unread_messages INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gmail_labels_account ON gmail_labels(account_id);
            CREATE TABLE IF NOT EXISTS gmail_filters (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES gmail_accounts(id) ON DELETE CASCADE,
                criteria TEXT NOT NULL DEFAULT '{}',
                action TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gmail_filters_account ON gmail_filters(account_id);
            CREATE TABLE IF NOT EXISTS fb_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                source TEXT NOT NULL CHECK (source IN ('messenger','comment')),
                external_thread_id TEXT NOT NULL,
                external_psid TEXT NOT NULL,
                external_user_name TEXT,
                post_id TEXT,
                post_is_sensitive INTEGER NOT NULL DEFAULT 0,
                message_text TEXT NOT NULL,
                detected_intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                policy_action TEXT NOT NULL,
                assigned_role TEXT CHECK (assigned_role IN ('quan_ly','chu_quan')),
                proposed_response TEXT,
                ai_generation_id TEXT,
                flagged_reasons TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','edited_approved','rejected','sent','expired','auto_sent')),
                decided_by TEXT,
                decided_at TEXT,
                final_response TEXT,
                audit_sent INTEGER,
                trace_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                event_at TEXT,
                expires_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fbrq_status ON fb_review_queue(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_fbrq_role ON fb_review_queue(assigned_role, status);
            CREATE INDEX IF NOT EXISTS idx_fbrq_thread ON fb_review_queue(external_thread_id, created_at);
            CREATE TABLE IF NOT EXISTS fb_escalation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_queue_id INTEGER NOT NULL REFERENCES fb_review_queue(id),
                escalated_to TEXT NOT NULL,
                reason TEXT NOT NULL,
                notified_channel TEXT,
                notified_at TEXT,
                acked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS fb_psid_blacklist (
                psid TEXT PRIMARY KEY,
                strikes INTEGER NOT NULL DEFAULT 1,
                blocked_until TEXT NOT NULL,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS fb_processed_events (
                event_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fb_event_receipts (
                idempotency_key TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                page_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                external_event_id TEXT NOT NULL,
                processed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fb_event_receipts_scope
                ON fb_event_receipts(store_id, page_id, event_type, processed_at);
            CREATE TABLE IF NOT EXISTS ai_generation_records (
                id TEXT PRIMARY KEY, store_id TEXT NOT NULL, channel TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(store_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_generation_store_created ON ai_generation_records(store_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS ai_feedback_events (
                id TEXT PRIMARY KEY, store_id TEXT NOT NULL, generation_id TEXT NOT NULL,
                channel TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(store_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_feedback_store_generation ON ai_feedback_events(store_id, generation_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS ai_evaluations (
                id TEXT PRIMARY KEY, store_id TEXT NOT NULL, generation_id TEXT NOT NULL,
                channel TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(store_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_evaluation_store_generation ON ai_evaluations(store_id, generation_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS ai_rule_proposals (
                id TEXT PRIMARY KEY, store_id TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL,
                version INTEGER NOT NULL, idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(store_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_rule_proposal_store_status ON ai_rule_proposals(store_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS chat_conversations (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                type TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT,
                is_locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_conv_store ON chat_conversations(store_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS chat_participants (
                conversation_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'active',
                muted INTEGER NOT NULL DEFAULT 0,
                last_read_at TEXT,
                joined_at TEXT NOT NULL,
                archived_at TEXT,
                PRIMARY KEY (conversation_id, nv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_chat_part_user ON chat_participants(nv_id, status);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'text',
                content TEXT NOT NULL DEFAULT '',
                reply_to_id TEXT,
                is_unsent INTEGER NOT NULL DEFAULT 0,
                edited_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_msg_conv ON chat_messages(conversation_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS chat_reactions (
                message_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                emoji TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (message_id, nv_id)
            );

            CREATE TABLE IF NOT EXISTS chat_read_receipts (
                conversation_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                last_read_message_id TEXT,
                read_at TEXT,
                PRIMARY KEY (conversation_id, nv_id)
            );

            CREATE TABLE IF NOT EXISTS ban_an (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                ten_ban TEXT NOT NULL,
                suc_chua INTEGER NOT NULL,
                vi_tri TEXT NOT NULL,
                can_combine_with TEXT NOT NULL DEFAULT '[]',
                trang_thai_hoat_dong INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_ban_an_store ON ban_an(store_id, trang_thai_hoat_dong);

            CREATE TABLE IF NOT EXISTS dat_ban (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                psid TEXT NOT NULL DEFAULT '',
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                booking_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 120,
                party_size INTEGER NOT NULL,
                table_ids TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                source TEXT NOT NULL DEFAULT 'ai_auto',
                notes TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL DEFAULT '',
                notified_nv_id TEXT,
                notification_acked_at TEXT,
                cancelled_by TEXT,
                cancelled_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_dat_ban_idem ON dat_ban(idempotency_key) WHERE status NOT IN ('cancelled', 'no_show') AND idempotency_key != '';
            CREATE INDEX IF NOT EXISTS idx_dat_ban_time ON dat_ban(store_id, booking_time, status);
            CREATE INDEX IF NOT EXISTS idx_dat_ban_psid ON dat_ban(store_id, psid, status);

            CREATE TABLE IF NOT EXISTS dat_ban_lich_su (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dat_ban_id TEXT NOT NULL,
                hanh_dong TEXT NOT NULL,
                trang_thai_cu TEXT,
                trang_thai_moi TEXT,
                thuc_hien_boi TEXT NOT NULL,
                ly_do TEXT NOT NULL DEFAULT '',
                thoi_gian TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS thong_bao_ca (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                dat_ban_id TEXT NOT NULL,
                ca_id TEXT NOT NULL DEFAULT '',
                nv_id TEXT NOT NULL,
                tieu_de TEXT NOT NULL,
                noi_dung TEXT NOT NULL,
                da_xem INTEGER NOT NULL DEFAULT 0,
                escalated_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_thong_bao_ca_user ON thong_bao_ca(store_id, nv_id, da_xem, created_at DESC);

            CREATE TABLE IF NOT EXISTS thong_bao_lich (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                tuan_iso TEXT NOT NULL,
                su_kien TEXT NOT NULL,
                tieu_de TEXT NOT NULL,
                noi_dung TEXT NOT NULL,
                url TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                da_xem INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(store_id, tuan_iso, su_kien, nv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_thong_bao_lich_user ON thong_bao_lich(store_id, nv_id, da_xem, created_at DESC);
            """
            )
        if not _database_url():
            _migrate_schema(cx)
        _ensure_scheduling_schema(cx)
        # Production/fresh database không được tự nhồi tài khoản, menu hay bàn
        # minh họa. Chỉ seed khi operator bật NHIPQUAN_SEED_DEMO rõ ràng.
        if _demo_seed_enabled():
            for u, pw, role, nv, name in USERS:
                cx.execute(
                    """
                    INSERT INTO users(username, password_sha, role, nv_id, display_name, store_id, status)
                    VALUES (?,?,?,?,?,?,'active')
                    ON CONFLICT(username) DO NOTHING
                    """,
                    (u, hash_password(pw), role, nv, name, DEFAULT_STORE_ID),
                )
            _seed_menu_neu_trong(cx)
            _seed_tables_neu_trong(cx)
        _seed_chat_neu_trong(cx)
        _INITIALIZED_PATHS.add(p_str)
    _INITIALIZED = True


def _ensure_scheduling_schema(cx: Any) -> None:
    """Create the additive scheduling tables used by the authoritative flow."""
    acquire_write_lock(cx, "nhipquan_ensure_scheduling_schema")
    cx.execute(
        """
        CREATE TABLE IF NOT EXISTS availability_confirmations (
            id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            nv_id TEXT NOT NULL,
            tuan_iso TEXT NOT NULL,
            availability TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(store_id, nv_id, tuan_iso)
        )
        """
    )
    cx.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_availability_week
        ON availability_confirmations(store_id, tuan_iso, nv_id, status)
        """
    )
    cx.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_runs (
            id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            tuan_iso TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            input_snapshot TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            result_snapshot TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(store_id, tuan_iso, version),
            UNIQUE(store_id, tuan_iso, idempotency_key)
        )
        """
    )
    cx.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_runs_week
        ON schedule_runs(store_id, tuan_iso, version DESC)
        """
    )
    cx.execute(
        """
        CREATE TABLE IF NOT EXISTS authoritative_assignments (
            id TEXT PRIMARY KEY,
            schedule_run_id TEXT NOT NULL,
            store_id TEXT NOT NULL,
            tuan_iso TEXT NOT NULL,
            ca_id TEXT NOT NULL,
            nv_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(schedule_run_id, ca_id, nv_id)
        )
        """
    )
    cx.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_authoritative_assignments_week
        ON authoritative_assignments(store_id, tuan_iso, ca_id, nv_id)
        """
    )
    cx.execute(
        """
        CREATE TABLE IF NOT EXISTS open_shifts (
            id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            schedule_run_id TEXT NOT NULL,
            tuan_iso TEXT NOT NULL,
            ca_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            deadline_at TEXT NOT NULL,
            claimed_by TEXT,
            claimed_at TEXT,
            escalated_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(store_id, schedule_run_id, ca_id)
        )
        """
    )
    cx.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_applications (
            id TEXT PRIMARY KEY,
            open_shift_id TEXT NOT NULL,
            store_id TEXT NOT NULL,
            nv_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT,
            UNIQUE(open_shift_id, nv_id)
        )
        """
    )
    cx.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_shift_applications_claim
        ON shift_applications(open_shift_id, status, created_at)
        """
    )


def availability_confirmed_list(store_id: str, tuan_iso: str) -> list[dict[str, Any]]:
    """Return only confirmed availability for the exact employee/week key."""
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """
            SELECT id, nv_id, tuan_iso, availability, source, created_at, updated_at
            FROM availability_confirmations
            WHERE store_id=? AND tuan_iso=? AND status='da_xac_nhan'
            ORDER BY nv_id, updated_at DESC
            """,
            (store_id, tuan_iso),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "nv_id": str(row[1]),
            "tuan_iso": str(row[2]),
            "availability": json.loads(row[3]),
            "source": str(row[4]),
            "created_at": str(row[5]),
            "updated_at": str(row[6]),
        }
        for row in rows
    ]


def availability_confirmation_upsert(
    *,
    item_id: str,
    store_id: str,
    nv_id: str,
    tuan_iso: str,
    availability: dict[str, Any],
    status: str,
    source: str = "chat",
) -> None:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        existing = cx.execute(
            "SELECT id, created_at FROM availability_confirmations WHERE store_id=? AND nv_id=? AND tuan_iso=? ORDER BY updated_at DESC LIMIT 1",
            (store_id, nv_id, tuan_iso),
        ).fetchone()
        if existing:
            cx.execute(
                """
                UPDATE availability_confirmations
                SET availability=?, status=?, source=?, updated_at=?
                WHERE id=?
                """,
                (
                    json.dumps(availability, ensure_ascii=False),
                    status,
                    source,
                    now,
                    str(existing[0]),
                ),
            )
        else:
            cx.execute(
                """
                INSERT INTO availability_confirmations
                    (id, store_id, nv_id, tuan_iso, availability, status, source, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    item_id,
                    store_id,
                    nv_id,
                    tuan_iso,
                    json.dumps(availability, ensure_ascii=False),
                    status,
                    source,
                    now,
                    now,
                ),
            )


def chat_get_or_create_scheduler_direct(store_id: str, nv_id: str) -> dict[str, Any]:
    """Return the single private employee <-> scheduler conversation."""
    init_db()
    conv_id = f"conv_scheduler_{store_id}_{nv_id}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            cx.execute(
                """
                INSERT INTO chat_conversations
                    (id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING
                """,
                (conv_id, store_id, "direct", "AI Scheduler", "", False, now, now),
            )
            # Migration 0008 khai `chat_participants.nv_id` có khoá ngoại tới
            # `users.nv_id`. Trên Postgres, chèn participant `ai_scheduler` khi
            # bot chưa có trong `users` sẽ vi phạm FK → HTTP 500. Bảo đảm bot
            # tồn tại trước khi mời vào hội thoại.
            cx.execute(
                """
                INSERT INTO users(username, password_sha, role, nv_id, display_name, store_id, status)
                VALUES ('ai_scheduler', 'bot_internal', 'ai_assistant', 'ai_scheduler', 'Agent Xếp Lịch 📅', ?, 'active')
                ON CONFLICT(username) DO NOTHING
                """,
                (store_id,),
            )
            for participant, role in ((nv_id, "member"), ("ai_scheduler", "admin")):
                cx.execute(
                    """
                    INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
                    VALUES (?,?,?,?,?) ON CONFLICT(conversation_id, nv_id) DO NOTHING
                    """,
                    (conv_id, participant, role, "active", now),
                )
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
    return chat_conversation_get(conv_id, nv_id) or {"id": conv_id, "type": "direct"}


def schedule_run_create(
    *,
    store_id: str,
    tuan_iso: str,
    input_snapshot: dict[str, Any],
    fingerprint: str,
    idempotency_key: str,
    created_by: str,
    status: str = "computed",
    result_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = f"schedule_run_{uuid.uuid4().hex}"
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            existing = cx.execute(
                "SELECT id, version, status, fingerprint FROM schedule_runs WHERE store_id=? AND tuan_iso=? AND idempotency_key=?",
                (store_id, tuan_iso, idempotency_key),
            ).fetchone()
            if existing:
                cx.execute("COMMIT")
                return {
                    "id": str(existing[0]),
                    "version": int(existing[1]),
                    "status": str(existing[2]),
                    "fingerprint": str(existing[3]),
                    "reused": True,
                }
            version_row = cx.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM schedule_runs WHERE store_id=? AND tuan_iso=?",
                (store_id, tuan_iso),
            ).fetchone()
            version = int(version_row[0])
            cx.execute(
                "INSERT INTO schedule_runs(id, store_id, tuan_iso, version, status, input_snapshot, fingerprint, result_snapshot, idempotency_key, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    store_id,
                    tuan_iso,
                    version,
                    status,
                    json.dumps(input_snapshot, ensure_ascii=False, sort_keys=True),
                    fingerprint,
                    json.dumps(result_snapshot or {}, ensure_ascii=False, sort_keys=True),
                    idempotency_key,
                    created_by,
                    now,
                ),
            )
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
    return {
        "id": run_id,
        "version": version,
        "status": status,
        "fingerprint": fingerprint,
        "reused": False,
    }


def schedule_run_update_result(
    run_id: str, *, status: str, result_snapshot: dict[str, Any]
) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "UPDATE schedule_runs SET status=?, result_snapshot=? WHERE id=?",
            (status, json.dumps(result_snapshot, ensure_ascii=False, sort_keys=True), run_id),
        )


def schedule_run_get(run_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT id, store_id, tuan_iso, version, status, input_snapshot, fingerprint, result_snapshot, idempotency_key, created_by, created_at FROM schedule_runs WHERE id=?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "store_id": str(row[1]),
        "tuan_iso": str(row[2]),
        "version": int(row[3]),
        "status": str(row[4]),
        "input_snapshot": json.loads(row[5]),
        "fingerprint": str(row[6]),
        "result": json.loads(row[7]),
        "idempotency_key": str(row[8]),
        "created_by": str(row[9]),
        "created_at": str(row[10]),
    }


def schedule_run_latest(store_id: str, tuan_iso: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT id FROM schedule_runs WHERE store_id=? AND tuan_iso=? ORDER BY version DESC LIMIT 1",
            (store_id, tuan_iso),
        ).fetchone()
    return schedule_run_get(str(row[0])) if row else None


def authoritative_assignments_list(schedule_run_id: str) -> list[dict[str, str]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            "SELECT ca_id, nv_id FROM authoritative_assignments WHERE schedule_run_id=? ORDER BY ca_id, nv_id",
            (schedule_run_id,),
        ).fetchall()
    return [{"ca_id": str(row[0]), "nv_id": str(row[1])} for row in rows]


def authoritative_assignments_replace(
    *, schedule_run_id: str, store_id: str, tuan_iso: str, assignments: dict[str, list[str]]
) -> None:
    """Replace the assignment projection for one immutable solver run."""
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            "DELETE FROM authoritative_assignments WHERE schedule_run_id=?", (schedule_run_id,)
        )
        for ca_id, nv_ids in assignments.items():
            for nv_id in nv_ids:
                cx.execute(
                    """
                    INSERT INTO authoritative_assignments
                        (id, schedule_run_id, store_id, tuan_iso, ca_id, nv_id, created_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        f"assignment_{uuid.uuid4().hex}",
                        schedule_run_id,
                        store_id,
                        tuan_iso,
                        str(ca_id),
                        str(nv_id),
                        now,
                    ),
                )


def shift_application_claim_first(
    *, open_shift_id: str, store_id: str, nv_id: str, now: str | None = None
) -> dict[str, Any] | None:
    """Atomically claim an open shift; the first eligible claimant wins."""
    init_db()
    claimed_at = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    application_id = f"shift_application_{uuid.uuid4().hex}"
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            shift = cx.execute(
                "SELECT id, status, deadline_at FROM open_shifts WHERE id=? AND store_id=?",
                (open_shift_id, store_id),
            ).fetchone()
            if not shift or str(shift[1]) != "open":
                cx.execute("ROLLBACK")
                return None
            cx.execute(
                "INSERT INTO shift_applications(id, open_shift_id, store_id, nv_id, status, created_at, decided_at) VALUES (?,?,?,?,?,?,?)",
                (
                    application_id,
                    open_shift_id,
                    store_id,
                    nv_id,
                    "accepted",
                    claimed_at,
                    claimed_at,
                ),
            )
            cx.execute(
                """UPDATE open_shifts SET status='claimed', claimed_by=?, claimed_at=?
                   WHERE id=? AND status='open' AND deadline_at>? AND escalated_at IS NULL""",
                (nv_id, claimed_at, open_shift_id, claimed_at),
            )
            if cx.execute("SELECT changes()").fetchone()[0] != 1:
                cx.execute("ROLLBACK")
                return None
            cx.execute("COMMIT")
        except _DB_INTEGRITY_ERRORS:
            cx.execute("ROLLBACK")
            return None
        except Exception:
            cx.execute("ROLLBACK")
            raise
    return {
        "id": application_id,
        "open_shift_id": open_shift_id,
        "nv_id": nv_id,
        "status": "accepted",
        "claimed_at": claimed_at,
    }


def open_shift_create(
    *, store_id: str, schedule_run_id: str, tuan_iso: str, ca_id: str, deadline_at: str
) -> dict[str, Any]:
    init_db()
    shift_id = f"open_shift_{uuid.uuid4().hex}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO open_shifts
                (id, store_id, schedule_run_id, tuan_iso, ca_id, status, deadline_at, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(store_id, schedule_run_id, ca_id) DO NOTHING
            """,
            (shift_id, store_id, schedule_run_id, tuan_iso, ca_id, "open", deadline_at, now),
        )
        row = cx.execute(
            "SELECT id, status, deadline_at, claimed_by, claimed_at, escalated_at FROM open_shifts WHERE store_id=? AND schedule_run_id=? AND ca_id=?",
            (store_id, schedule_run_id, ca_id),
        ).fetchone()
    return {
        "id": str(row[0]),
        "status": str(row[1]),
        "deadline_at": str(row[2]),
        "claimed_by": row[3],
        "claimed_at": row[4],
    }


def open_shift_list(
    store_id: str, *, tuan_iso: str | None = None, status: str = "open"
) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        query = "SELECT id, schedule_run_id, tuan_iso, ca_id, status, deadline_at, claimed_by, claimed_at, escalated_at FROM open_shifts WHERE store_id=? AND status=?"
        params: list[Any] = [store_id, status]
        if tuan_iso:
            query += " AND tuan_iso=?"
            params.append(tuan_iso)
        rows = cx.execute(query + " ORDER BY deadline_at, created_at", params).fetchall()
    return [
        {
            "id": str(row[0]),
            "schedule_run_id": str(row[1]),
            "tuan_iso": str(row[2]),
            "ca_id": str(row[3]),
            "status": str(row[4]),
            "deadline_at": str(row[5]),
            "claimed_by": row[6],
            "claimed_at": row[7],
            "escalated_at": row[8],
        }
        for row in rows
    ]


def open_shift_resolve_for_week(store_id: str, tuan_iso: str) -> int:
    init_db()
    with _conn() as cx:
        result = cx.execute(
            "UPDATE open_shifts SET status='resolved' WHERE store_id=? AND tuan_iso=? AND status IN ('open', 'claimed')",
            (store_id, tuan_iso),
        )
    return int(result.rowcount)


def open_shift_escalate_due(store_id: str, *, now_iso: str) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """
            SELECT id, tuan_iso, ca_id, deadline_at
            FROM open_shifts
            WHERE store_id=? AND status='open' AND escalated_at IS NULL AND deadline_at<=?
            ORDER BY deadline_at, created_at
            """,
            (store_id, now_iso),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "tuan_iso": str(row[1]),
            "ca_id": str(row[2]),
            "deadline_at": str(row[3]),
        }
        for row in rows
    ]


def open_shift_mark_escalated(open_shift_id: str, *, store_id: str, escalated_at: str) -> bool:
    init_db()
    with _conn() as cx:
        result = cx.execute(
            """UPDATE open_shifts SET escalated_at=?
               WHERE id=? AND store_id=? AND status='open' AND escalated_at IS NULL""",
            (escalated_at, open_shift_id, store_id),
        )
    return bool(result.rowcount == 1)


def shift_application_claim_eligible(
    *, open_shift_id: str, store_id: str, nv_id: str, eligible: bool
) -> dict[str, Any] | None:
    if not eligible:
        return None
    return shift_application_claim_first(
        open_shift_id=open_shift_id, store_id=store_id, nv_id=nv_id
    )


def _migrate_schema(cx: sqlite3.Connection) -> None:
    def _safe_alter(sql: str) -> None:
        try:
            cx.execute(sql)
        except sqlite3.OperationalError:
            pass

    cols = {r[1] for r in cx.execute("PRAGMA table_info(menu_mon)")}
    if "hinh_url" not in cols:
        _safe_alter("ALTER TABLE menu_mon ADD COLUMN hinh_url TEXT NOT NULL DEFAULT ''")
    # Nhóm sản phẩm (ca_phe/tra/...) để màn hình quầy phân mục menu. Trước đây
    # chỉ suy từ BOM lúc vẽ ảnh nên API không trả về được — UI phải hiện một
    # danh sách phẳng. Cột rỗng = chưa khai nhóm, đọc lên suy từ BOM cho tương thích.
    if "nhom" not in cols:
        _safe_alter("ALTER TABLE menu_mon ADD COLUMN nhom TEXT NOT NULL DEFAULT ''")
    ucols = {r[1] for r in cx.execute("PRAGMA table_info(users)")}
    if "email" not in ucols:
        _safe_alter("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if "store_id" not in ucols:
        _safe_alter("ALTER TABLE users ADD COLUMN store_id TEXT NOT NULL DEFAULT 'quan_01'")
    if "status" not in ucols:
        _safe_alter("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    cx.execute("UPDATE users SET store_id=? WHERE TRIM(store_id)=''", (DEFAULT_STORE_ID,))
    # dat_ban: thêm cột email riêng (trước đây email bị nhét vào notes, khiến
    # record đọc lại từ DB không có field email → không gửi được phiếu xác nhận).
    dcols = {r[1] for r in cx.execute("PRAGMA table_info(dat_ban)")}
    if "email" not in dcols:
        _safe_alter("ALTER TABLE dat_ban ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        # Backfill email đã lưu trong notes dạng "Email: xxx@yyy.zz"
        cx.execute(
            "UPDATE dat_ban SET email=TRIM(SUBSTR(notes, 8)) "
            "WHERE email='' AND notes LIKE 'Email: %@%'"
        )
    scols = {r[1] for r in cx.execute("PRAGMA table_info(sessions)")}
    if "store_id" not in scols:
        _safe_alter("ALTER TABLE sessions ADD COLUMN store_id TEXT NOT NULL DEFAULT 'quan_01'")
    if "created_at" not in scols:
        # Phiên cũ không có mốc tạo → TTL coi như chưa từng hết hạn nhưng vẫn
        # được ghi mốc mới từ lần đăng nhập kế tiếp (migration an toàn, idempotent).
        _safe_alter("ALTER TABLE sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    cx.execute(
        "UPDATE sessions SET store_id=(SELECT store_id FROM users WHERE users.username=sessions.username) WHERE store_id='quan_01' AND EXISTS (SELECT 1 FROM users WHERE users.username=sessions.username)"
    )
    evaluation_cols = {r[1] for r in cx.execute("PRAGMA table_info(ai_evaluations)")}
    if "idempotency_key" not in evaluation_cols:
        _safe_alter(
            "ALTER TABLE ai_evaluations ADD COLUMN idempotency_key TEXT NOT NULL DEFAULT ''"
        )
        _safe_alter(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_evaluation_store_idem ON ai_evaluations(store_id, idempotency_key)"
        )
    proposal_cols = {r[1] for r in cx.execute("PRAGMA table_info(ai_rule_proposals)")}
    if "idempotency_key" not in proposal_cols:
        _safe_alter(
            "ALTER TABLE ai_rule_proposals ADD COLUMN idempotency_key TEXT NOT NULL DEFAULT ''"
        )
        _safe_alter(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_rule_proposal_store_idem ON ai_rule_proposals(store_id, idempotency_key)"
        )
    review_cols = {r[1] for r in cx.execute("PRAGMA table_info(fb_review_queue)")}
    if "ai_generation_id" not in review_cols:
        _safe_alter("ALTER TABLE fb_review_queue ADD COLUMN ai_generation_id TEXT")
    if "event_at" not in review_cols:
        _safe_alter("ALTER TABLE fb_review_queue ADD COLUMN event_at TEXT")
    if "store_id" not in review_cols:
        _safe_alter(
            "ALTER TABLE fb_review_queue ADD COLUMN store_id TEXT NOT NULL DEFAULT 'quan_01'"
        )

    ccols = {r[1] for r in cx.execute("PRAGMA table_info(chat_conversations)")}
    if ccols and "display_name" not in ccols:
        cx.execute("DROP TABLE IF EXISTS chat_read_receipts")
        cx.execute("DROP TABLE IF EXISTS chat_reactions")
        cx.execute("DROP TABLE IF EXISTS chat_messages")
        cx.execute("DROP TABLE IF EXISTS chat_participants")
        cx.execute("DROP TABLE IF EXISTS chat_conversations")
        cx.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL DEFAULT 'quan_01',
                type TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT,
                is_locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_conv_store ON chat_conversations(store_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS chat_participants (
                conversation_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'active',
                muted INTEGER NOT NULL DEFAULT 0,
                last_read_at TEXT,
                joined_at TEXT NOT NULL,
                archived_at TEXT,
                PRIMARY KEY (conversation_id, nv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_chat_part_user ON chat_participants(nv_id, status);
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'text',
                content TEXT NOT NULL DEFAULT '',
                reply_to_id TEXT,
                is_unsent INTEGER NOT NULL DEFAULT 0,
                edited_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_msg_conv ON chat_messages(conversation_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS chat_reactions (
                message_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                emoji TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (message_id, nv_id)
            );
            CREATE TABLE IF NOT EXISTS chat_read_receipts (
                conversation_id TEXT NOT NULL,
                nv_id TEXT NOT NULL,
                last_read_message_id TEXT,
                read_at TEXT,
                PRIMARY KEY (conversation_id, nv_id)
            );
            """
        )

    # Truy vết tác nhân cho sổ vết hệ thống (actor_type/agent_name/controller).
    acols = {r[1] for r in cx.execute("PRAGMA table_info(audit)")}
    if "actor_type" not in acols:
        _safe_alter("ALTER TABLE audit ADD COLUMN actor_type TEXT NOT NULL DEFAULT 'human'")
    if "agent_name" not in acols:
        _safe_alter("ALTER TABLE audit ADD COLUMN agent_name TEXT")
    if "controller_user_id" not in acols:
        _safe_alter("ALTER TABLE audit ADD COLUMN controller_user_id TEXT")
    _safe_alter("CREATE INDEX IF NOT EXISTS idx_audit_actor_type ON audit(actor_type, at)")

    cal_cols = {r[1] for r in cx.execute("PRAGMA table_info(copilot_audit_log)")}
    if "agent_name" not in cal_cols:
        _safe_alter("ALTER TABLE copilot_audit_log ADD COLUMN agent_name TEXT")
    if "controller_user_id" not in cal_cols:
        _safe_alter("ALTER TABLE copilot_audit_log ADD COLUMN controller_user_id TEXT")
    _safe_alter(
        "CREATE INDEX IF NOT EXISTS idx_copilot_audit_agent ON copilot_audit_log(agent_name, timestamp)"
    )


_MENU_MAC_DINH = (
    # Khóa BOM viết MÃ CHUẨN (`ca_phe_hat`, `sua_tuoi`, `dao`) chứ không mã legacy
    # (`cafe_g`, `sua_ml`, `dao_lat`). Bảng seed này là NƠI SINH RA mã legacy ấy
    # trên DB mới; để nguyên thì mỗi lượt khởi tạo lại dựng menu "Cà phê đen" +
    # BOM mã cũ, và sổ tiêu thụ lại sinh thêm mặt hàng trùng.
    ("mon_den", "Cà phê đen", 25000, {"ca_phe_hat": 18, "ly": 1}, "ca_phe"),
    ("mon_sua", "Cà phê sữa", 30000, {"ca_phe_hat": 16, "sua_tuoi": 40, "ly": 1}, "ca_phe"),
    ("mon_tra", "Trà đào", 35000, {"dao": 3, "ly": 1}, "tra"),
    ("mon_da", "Bạc xỉu", 32000, {"ca_phe_hat": 12, "sua_tuoi": 80, "ly": 1}, "ca_phe"),
    # Nước đóng chai: bán nguyên chai, không qua pha chế. Thiếu nhóm này thì danh
    # mục mặc định chỉ có đồ pha — quán mới mở không bán được nước suối, và ô
    # chọn nguyên liệu ở menu có `nuoc_dong_chai` mà không món nào dùng.
    ("mon_nuoc_suoi", "Nước suối", 12000, {"nuoc_dong_chai": 1}, "nuoc_dong_chai"),
    # Bánh kèm: nhóm ăn kèm của quán cà phê, cũng là mặt hàng đếm theo cái.
    ("mon_banh_quy", "Bánh quy bơ", 20000, {"banh": 1}, "banh"),
)


def _seed_menu_neu_trong(cx: sqlite3.Connection) -> None:
    n = cx.execute("SELECT COUNT(*) FROM menu_mon").fetchone()[0]
    if int(n) > 0:
        return
    for mid, ten, gia, bom, nhom in _MENU_MAC_DINH:
        cx.execute(
            "INSERT INTO menu_mon(id, ten, gia, an, bom, nhom) VALUES (?,?,?,?,?,?)",
            (mid, ten, gia, 0, json.dumps(bom, ensure_ascii=False), nhom),
        )


def kenh_bind_get(channel: str, external_user_id: str) -> str | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT nv_id FROM kenh_bind WHERE channel=? AND external_user_id=?",
            (channel, external_user_id),
        ).fetchone()
    return str(row[0]) if row else None


def kenh_bind_set(channel: str, external_user_id: str, nv_id: str) -> None:
    from datetime import datetime

    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO kenh_bind(channel, external_user_id, nv_id, created_at)
            VALUES (?,?,?,?)
            ON CONFLICT(channel, external_user_id) DO UPDATE SET nv_id=excluded.nv_id
            """,
            (channel, external_user_id, nv_id, now),
        )


def kenh_bind_list(nv_id: str | None = None) -> list[dict[str, str]]:
    init_db()
    with _conn() as cx:
        if nv_id:
            rows = cx.execute(
                "SELECT channel, external_user_id, nv_id, created_at FROM kenh_bind WHERE nv_id=?",
                (nv_id,),
            ).fetchall()
        else:
            rows = cx.execute(
                "SELECT channel, external_user_id, nv_id, created_at FROM kenh_bind"
            ).fetchall()
    return [
        {
            "channel": str(r[0]),
            "external_user_id": str(r[1]),
            "nv_id": str(r[2]),
            "created_at": str(r[3]),
        }
        for r in rows
    ]


_FAILED_BINDS: dict[str, list[float]] = {}


def kenh_bind_code_issue(nv_id: str) -> str:
    from datetime import datetime

    init_db()
    code = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            "INSERT INTO kenh_bind_code(code, nv_id, created_at) VALUES (?,?,?)",
            (code, nv_id, now),
        )
    return code


def kenh_bind_code_consume(
    code: str, channel: str, external_user_id: str, max_age_seconds: int = 300
) -> str | None:
    import time
    from datetime import datetime

    now_ts = time.time()
    user_key = f"{channel}:{external_user_id}"

    # Rate limit: tối đa 5 lần sai trong 15 phút
    attempts = [t for t in _FAILED_BINDS.get(user_key, []) if now_ts - t < 900]
    if len(attempts) >= 5:
        return None

    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT nv_id, created_at FROM kenh_bind_code WHERE code=?", (code.strip().lower(),)
        ).fetchone()
        if not row:
            attempts.append(now_ts)
            _FAILED_BINDS[user_key] = attempts
            return None

        nv_id = str(row[0])
        created_at_str = str(row[1]) if len(row) > 1 else ""

        # Kiểm tra TTL
        if created_at_str:
            try:
                created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                age = (datetime.now(UTC) - created_dt).total_seconds()
                if age > max_age_seconds:
                    cx.execute("DELETE FROM kenh_bind_code WHERE code=?", (code.strip().lower(),))
                    attempts.append(now_ts)
                    _FAILED_BINDS[user_key] = attempts
                    return None
            except Exception:
                pass

        cx.execute("DELETE FROM kenh_bind_code WHERE code=?", (code.strip().lower(),))
        _FAILED_BINDS.pop(user_key, None)

    kenh_bind_set(channel, external_user_id, nv_id)
    return nv_id


def reset_init_flag() -> None:
    """Tests may swap NHIPQUAN_DB between cases."""
    global _INITIALIZED
    _INITIALIZED = False


def login(username: str, password: str) -> dict[str, str] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT username, role, nv_id, display_name, password_sha, store_id, status
            FROM users WHERE username=?
            """,
            (username.strip().lower(),),
        ).fetchone()
        # Không tách "không có tài khoản" khỏi "sai mật khẩu": tách ra là cho
        # người ngoài dò được username nào tồn tại.
        #
        # Bug QA đợt 6 (#35 — Critical): tài khoản đã `deactivate` (status
        # `inactive`) VẪN đăng nhập được vì truy vấn không đọc `status`.
        # Offboarding coi như vô hiệu trên UI nhưng kẻ đã biết mật khẩu vẫn vào
        # được — `user_deactivate` còn xoá session nên chỉ cần đăng nhập lại.
        # Gộp vào cùng nhánh "sai thông tin" để KHÔNG lộ tài khoản nào bị khoá.
        if not row or str(row[6] or "active") != "active" or not verify_password(password, row[4]):
            cx.execute(
                "INSERT INTO audit(at, ai, hanh, payload) VALUES (?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    "system",
                    "user.login_failed",
                    json.dumps(
                        {"entity_type": "user", "entity_id": username.strip().lower()},
                        ensure_ascii=False,
                    ),
                ),
            )
            return None
        token = uuid.uuid4().hex
        cx.execute(
            "INSERT INTO sessions(token, username, role, nv_id, store_id, created_at) VALUES (?,?,?,?,?,?)",
            (token, row[0], row[1], row[2], row[5], datetime.now(UTC).isoformat()),
        )
        cx.execute(
            "INSERT INTO audit(at, ai, hanh, payload) VALUES (?,?,?,?)",
            (
                datetime.now(UTC).isoformat(),
                row[2],
                "user.login",
                json.dumps(
                    {"entity_type": "session", "entity_id": token, "username": row[0]},
                    ensure_ascii=False,
                ),
            ),
        )
        return {
            "token": token,
            "role": row[1],
            "nv_id": row[2],
            "display_name": row[3],
            "store_id": row[5],
        }


# ── Đăng ký ───────────────────────────────────────────────────────────────
_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,24}$")
MK_TOI_THIEU = 8


class DangKyLoi(ValueError):
    """Lỗi đăng ký có mã máy đọc được; tầng HTTP dịch thành câu tiếng Việt."""

    def __init__(self, ma: str) -> None:
        super().__init__(ma)
        self.ma = ma


def _nv_id_ke_tiep(cx: sqlite3.Connection) -> str:
    """Cấp mã nhân viên chưa dùng, dạng nv_XX.

    Bắt đầu từ 26: dải nv_01–nv_25 dành cho seed lịch sử (ADR-012), tránh
    id user thật đụng NV seed trong pool xếp lịch (`ca_api.nhan_vien`).
    """
    dung = {r[0] for r in cx.execute("SELECT nv_id FROM users").fetchall() if isinstance(r[0], str)}
    i = 26
    while f"nv_{i:02d}" in dung:
        i += 1
    return f"nv_{i:02d}"


def register(username: str, password: str, display_name: str) -> dict[str, str]:
    """Tạo tài khoản nhân viên mới.

    Luôn cấp vai `nhan_vien` — xem `VAI_TU_DANG_KY`. Trả về đúng payload như
    `login()` để màn hình đăng ký vào được ngay, không phải đăng nhập lại.

    Raises:
        DangKyLoi: `ten_khong_hop_le` · `mat_khau_qua_ngan` · `thieu_ten_hien_thi`
            · `ten_da_ton_tai`
    """
    init_db()
    u = (username or "").strip().lower()
    ten = (display_name or "").strip()
    store_id = DEFAULT_STORE_ID
    if not _USERNAME_RE.match(u):
        raise DangKyLoi("ten_khong_hop_le")
    if len(password or "") < MK_TOI_THIEU:
        raise DangKyLoi("mat_khau_qua_ngan")
    if not (2 <= len(ten) <= 60):
        raise DangKyLoi("thieu_ten_hien_thi")

    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            if cx.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
                raise DangKyLoi("ten_da_ton_tai")
            nv = _nv_id_ke_tiep(cx)
            cx.execute(
                """
                INSERT INTO users(username, password_sha, role, nv_id, display_name, store_id, status)
                VALUES (?,?,?,?,?,?,'active')
                """,
                (u, hash_password(password), VAI_TU_DANG_KY, nv, ten, store_id),
            )
            token = uuid.uuid4().hex
            cx.execute(
                "INSERT INTO sessions(token, username, role, nv_id, store_id, created_at) VALUES (?,?,?,?,?,?)",
                (token, u, VAI_TU_DANG_KY, nv, store_id, datetime.now(UTC).isoformat()),
            )

            # Tự động đưa nhân viên mới vào Nhóm Chung Toàn Quán
            conv_general_id = f"conv_general_{store_id}"
            now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            cx.execute(
                """
                INSERT INTO chat_conversations(id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at)
                VALUES (?,?,?,?,?,TRUE,?,?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    conv_general_id,
                    store_id,
                    "general",
                    "☕ NHỊP QUÁN · Hội Quán Chung",
                    "",
                    now_iso,
                    now_iso,
                ),
            )
            cx.execute(
                """
                INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
                VALUES (?,?,'member','active',?)
                ON CONFLICT(conversation_id, nv_id) DO NOTHING
                """,
                (conv_general_id, nv, now_iso),
            )
            # Tin nhắn hệ thống chào đón thành viên mới
            msg_welcome_id = f"msg_{uuid.uuid4().hex[:12]}"
            cx.execute(
                """
                INSERT INTO chat_messages(id, conversation_id, sender_id, type, content, is_unsent, created_at)
                VALUES (?,?,'system','system',?,FALSE,?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    msg_welcome_id,
                    conv_general_id,
                    f"🎉 Chào mừng {ten} gia nhập đại gia đình NHỊP QUÁN!",
                    now_iso,
                ),
            )
            cx.execute(
                "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
                (now_iso, conv_general_id),
            )

            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
    return {
        "token": token,
        "role": VAI_TU_DANG_KY,
        "nv_id": nv,
        "display_name": ten,
        "store_id": store_id,
    }


# TTL phiên đăng nhập (ngày). Hết hạn → token bị xóa, phải đăng nhập lại.
SESSION_TTL_DAYS = float(os.environ.get("NHIPQUAN_SESSION_TTL_DAYS", "7") or 7)


def _session_expired(created_at: str) -> bool:
    """Phiên không có mốc tạo (bản cũ trước migration) coi như còn hiệu lực
    cho đến khi đăng nhập lại ghi mốc mới; có mốc thì kiểm tra quá 7 ngày."""
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created > timedelta(days=SESSION_TTL_DAYS)


def session(authorization: str | None) -> dict[str, str] | None:
    if not authorization:
        return None
    init_db()
    raw = authorization.removeprefix("Bearer ").strip()
    with _conn() as cx:
        row = cx.execute(
            "SELECT s.username, s.role, s.nv_id, u.email, s.store_id, s.created_at, "
            "COALESCE(u.status, 'active') FROM sessions s "
            "LEFT JOIN users u ON u.nv_id = s.nv_id WHERE s.token=?",
            (raw,),
        ).fetchone()
        if not row:
            return None
        if _session_expired(str(row[5] or "")):
            cx.execute("DELETE FROM sessions WHERE token=?", (raw,))
            return None
        # Bug QA đợt 6 (#35): phiên của tài khoản ĐÃ vô hiệu hoá phải bị từ chối
        # ngay cả khi token còn hạn — nếu không, offboarding chỉ có tác dụng khi
        # người dùng tự đăng xuất. Xoá token luôn để không phải kiểm lại.
        if str(row[6] or "active") != "active":
            cx.execute("DELETE FROM sessions WHERE token=?", (raw,))
            return None
        return {
            "username": row[0],
            "role": row[1],
            "nv_id": row[2],
            "email": str(row[3] or ""),
            "store_id": row[4],
        }


def logout(token: str) -> bool:
    """Đăng xuất: xóa đúng token này khỏi sessions. Trả True nếu có xóa."""
    init_db()
    raw = token.removeprefix("Bearer ").strip()
    if not raw:
        return False
    with _conn() as cx:
        cur = cx.execute("DELETE FROM sessions WHERE token=?", (raw,))
        return bool(cur.rowcount)


def kv_get(key: str, default: Any) -> Any:
    init_db()
    with _conn() as cx:
        row = cx.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    if not row:
        return default
    return json.loads(row[0])


def kv_get_many(keys: Sequence[str], defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Đọc NHIỀU khoá kv trong MỘT connection, trả dict cùng shape như `kv_get`.

    Vì sao cần: `kv_get` mở một connection SQLite MỚI và gọi `init_db()` MỖI lần.
    Một câu hỏi lịch tuần của trợ lý đọc 6+ khoá (`phan_cong`,
    `roster_nv_status`, `inbox_rang_buoc`, `tkb_nv_by_week`, `tkb_nv`,
    `lich_tuan_lifecycle`, ...) → 6+ connection cho MỘT câu hỏi. Cộng với
    `timeout=30` của SQLite, một câu hỏi nặng có thể chặn câu khác tới 30 giây —
    đúng triệu chứng "trả lời rất chậm" mà người dùng gặp.

    Hợp đồng: khoá nào không có trong DB thì lấy `defaults[key]`; khoá không khai
    trong `defaults` thì trả `None` (giống `kv_get(key, None)`).
    """
    keys = list(dict.fromkeys(str(k) for k in keys))
    if not keys:
        return {}
    defaults = dict(defaults or {})
    init_db()
    out: dict[str, Any] = {k: defaults.get(k) for k in keys}
    # SQLite giới hạn số biến trong câu lệnh; chia lô để an toàn với danh sách dài.
    with _conn() as cx:
        for i in range(0, len(keys), 500):
            lo = keys[i : i + 500]
            placeholders = ",".join("?" for _ in lo)
            rows = cx.execute(f"SELECT k, v FROM kv WHERE k IN ({placeholders})", lo).fetchall()
            for k, v in rows:
                try:
                    out[str(k)] = json.loads(v)
                except (TypeError, ValueError):
                    # Giá trị hỏng: giữ default thay vì làm sập cả câu trả lời.
                    out[str(k)] = defaults.get(str(k))
    return out


def kv_set(key: str, value: Any) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def kv_mutate(key: str, fn: Callable[[Any], Any], default: Any) -> Any:
    """Atomically read, mutate, and write one key across connections."""
    init_db()
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            if _database_url():
                lock_id = int.from_bytes(
                    hashlib.sha256(key.encode()).digest()[:8],
                    byteorder="big",
                    signed=True,
                )
                cx.execute("SELECT pg_advisory_xact_lock(?)", (lock_id,))
            row = cx.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
            cur = json.loads(row[0]) if row else default
            if isinstance(default, dict) and isinstance(cur, dict):
                cur = dict(cur)
            elif isinstance(default, list) and isinstance(cur, list):
                cur = list(cur)
            new = fn(cur)
            cx.execute(
                "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, json.dumps(new, ensure_ascii=False)),
            )
            cx.execute("COMMIT")
            return new
        except Exception:
            cx.execute("ROLLBACK")
            raise


def page_store_map_list() -> list[dict[str, str]]:
    raw = kv_get("page_store_map", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def resolve_store_id_from_page_id(page_id: str) -> str:
    page_id = str(page_id or "").strip()
    for item in page_store_map_list():
        if str(item.get("page_id") or "").strip() == page_id:
            return str(item.get("store_id") or "quan_01")
    return "quan_01"


def copilot_commit_internal_execution(
    *,
    store_id: str,
    action_id: str,
    idempotency_key: str,
    intent: str,
    actor_user_id: str,
    payload_diff: dict[str, Any],
    outcome: dict[str, Any],
    kv_mutations: dict[str, tuple[Callable[[Any], Any], Any]],
    channel: str = "web",
    latency_ms: int = 0,
) -> bool:
    """Commit internal Copilot writes, action and audit in one transaction."""
    init_db()
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            receipt = cx.execute(
                "SELECT 1 FROM copilot_execution_receipts "
                "WHERE store_id=? AND action_id=? AND idempotency_key=? AND status='pending'",
                (store_id, action_id, idempotency_key),
            ).fetchone()
            if not receipt:
                raise RuntimeError("internal_execution_receipt_missing")

            for key, (mutator, default) in kv_mutations.items():
                row = cx.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
                current = json.loads(row[0]) if row else default
                if isinstance(default, dict) and isinstance(current, dict):
                    current = dict(current)
                elif isinstance(default, list) and isinstance(current, list):
                    current = list(current)
                updated = mutator(current)
                cx.execute(
                    "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (key, json.dumps(updated, ensure_ascii=False)),
                )

            draft_update = cx.execute(
                "UPDATE copilot_draft_actions SET status='executed', executed_at=? "
                "WHERE action_id=? AND store_id=? AND status='executing'",
                (_iso_now(), action_id, store_id),
            )
            if draft_update.rowcount != 1:
                raise RuntimeError("internal_execution_action_claim_missing")

            now_iso = _iso_now()
            cx.execute(
                "INSERT INTO copilot_audit_log("
                "action_id, actor_user_id, store_id, intent, decision, payload_diff, "
                "timestamp, channel, latency_ms) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    action_id,
                    actor_user_id,
                    store_id,
                    intent,
                    "approve",
                    json.dumps(payload_diff, ensure_ascii=False),
                    now_iso,
                    channel,
                    latency_ms,
                ),
            )
            receipt_update = cx.execute(
                "UPDATE copilot_execution_receipts "
                "SET status='completed', outcome=?, completed_at=? "
                "WHERE store_id=? AND action_id=? AND idempotency_key=? AND status='pending'",
                (
                    json.dumps(outcome, ensure_ascii=False),
                    now_iso,
                    store_id,
                    action_id,
                    idempotency_key,
                ),
            )
            if receipt_update.rowcount != 1:
                raise RuntimeError("internal_execution_receipt_update_failed")
            cx.execute("COMMIT")
            return True
        except Exception:
            cx.execute("ROLLBACK")
            raise


def audit_request_begin() -> Token[dict[str, bool] | None]:
    """Bắt đầu theo dõi audit cho một HTTP request.

    Giá trị là dict mutable để endpoint sync chạy trong threadpool vẫn đánh
    dấu được cho middleware ở event-loop thread.
    """
    return _AUDIT_REQUEST_STATE.set({"written": False})


def audit_request_had_entry() -> bool:
    state = _AUDIT_REQUEST_STATE.get()
    return bool(state and state.get("written"))


def audit_request_end(token: Token[dict[str, bool] | None]) -> None:
    _AUDIT_REQUEST_STATE.reset(token)


def audit_add(
    at: str,
    ai: str,
    hanh: str,
    payload: dict[str, Any],
    *,
    actor_type: str | ActorType | None = None,
    agent_name: str | None = None,
    controller_user_id: str | None = None,
) -> None:
    """Ghi một vết vào sổ vết hệ thống.

    actor_type/agent_name/controller_user_id là truy vết tác nhân:
      - actor_type: human / agent / system / guest (mặc định suy từ `ai`)
      - agent_name: tên agent nếu actor là agent (vd "ag_copilot")
      - controller_user_id: người điều khiển agent (người duyệt/kích hoạt)
    """
    init_db()
    resolved_type = (
        actor_type.value if isinstance(actor_type, ActorType) else actor_type
    ) or resolve_actor_type(ai).value
    with _conn() as cx:
        cx.execute(
            """INSERT INTO audit(at, ai, hanh, payload, actor_type, agent_name, controller_user_id)
               VALUES (?,?,?,?,?,?,?)""",
            (
                at,
                ai,
                hanh,
                json.dumps(payload, ensure_ascii=False),
                resolved_type,
                agent_name,
                controller_user_id,
            ),
        )
    state = _AUDIT_REQUEST_STATE.get()
    if state is not None:
        state["written"] = True


def list_users(
    *, store_id: str | None = None, include_bots: bool = False, include_inactive: bool = False
) -> list[dict[str, str]]:
    """Liệt kê tài khoản NGƯỜI THẬT đang hoạt động của quán.

    Bug QA đợt 5: bot nội bộ `ai_scheduler` (vai `ai_assistant`) lọt vào danh
    sách nhân sự ở `/api/v1/nguoi` — trang Người dùng hiện "20 TỔNG TÀI KHOẢN"
    và vẽ bot trong biểu đồ phân bố vai trò, dù quán chỉ có 19 người. Bot được
    tạo tự động ở `chat_get_or_create_scheduler_direct` để thoả khoá ngoại của
    `chat_participants`, KHÔNG phải nhân sự.

    Bug QA đợt 6 (#36): tài khoản đã `deactivate` (status `inactive`) VẪN hiện
    trong danh sách — offboarding không có tác dụng trên UI, và mọi bề mặt đếm
    người (`/nguoi`, `/cong-bang`, Copilot `LIST_STAFF`) báo sai. Tài khoản rác
    do người ngoài tự đăng ký qua `/auth/register` cũng nằm lại vĩnh viễn.

    Lọc ở TẦNG DỮ LIỆU (không ở giao diện) để mọi bề mặt dùng chung đều đúng:
    `/nguoi`, `channels` (gợi ý người nhận), `AG-MEETING`, provider của Copilot,
    và phép đếm `so_nv`. Truyền `include_bots=True` ở nơi thật sự cần bot,
    `include_inactive=True` cho màn hình quản trị cần thấy cả người đã nghỉ.
    """
    init_db()
    # `status` có thể thiếu ở bản ghi rất cũ (cột thêm sau bằng _safe_alter) →
    # COALESCE về 'active' để không ẩn nhầm người đang làm việc.
    loc = "" if include_inactive else " AND COALESCE(status, 'active') = 'active'"
    with _conn() as cx:
        if store_id:
            rows = cx.execute(
                "SELECT username, role, nv_id, display_name, email FROM users WHERE store_id=?"
                + loc
                + " ORDER BY username",
                (store_id,),
            ).fetchall()
        else:
            rows = cx.execute(
                "SELECT username, role, nv_id, display_name, email FROM users WHERE 1=1"
                + loc
                + " ORDER BY username"
            ).fetchall()
    return [
        {
            "username": str(r[0]),
            "role": str(r[1]),
            "nv_id": str(r[2]),
            "display_name": str(r[3]),
            "email": str(r[4] or ""),
        }
        for r in rows
        if include_bots or str(r[1]) not in VAI_BOT
    ]


def thong_bao_lich_create_for_week(
    *,
    tuan_iso: str,
    su_kien: str,
    tieu_de: str,
    noi_dung: str,
    url: str,
    nv_ids: list[str],
    store_id: str = DEFAULT_STORE_ID,
) -> int:
    """Tạo thông báo lịch cho người dùng thật; lặp lại cùng sự kiện là no-op."""
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = 0
    with _conn() as cx:
        for nv_id in sorted({str(value).strip() for value in nv_ids if str(value).strip()}):
            cur = cx.execute(
                """INSERT OR IGNORE INTO thong_bao_lich
                   (id, store_id, tuan_iso, su_kien, tieu_de, noi_dung, url, nv_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    f"tbl_{uuid.uuid4().hex[:12]}",
                    store_id,
                    tuan_iso,
                    su_kien,
                    tieu_de,
                    noi_dung,
                    url,
                    nv_id,
                    now,
                ),
            )
            created += int(cur.rowcount > 0)
    return created


def thong_bao_lich_list(
    nv_id: str,
    *,
    unread_only: bool = False,
    store_id: str = DEFAULT_STORE_ID,
) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        sql = "SELECT * FROM thong_bao_lich WHERE store_id=? AND nv_id=?"
        params: list[Any] = [store_id, nv_id]
        if unread_only:
            sql += " AND da_xem=0"
        sql += " ORDER BY created_at DESC LIMIT 50"
        return [dict(row) for row in cx.execute(sql, params).fetchall()]


def thong_bao_lich_list_for_week(
    tuan_iso: str,
    *,
    store_id: str = DEFAULT_STORE_ID,
) -> list[dict[str, Any]]:
    """Liệt kê MỌI thông báo của một tuần trong quán (không lọc theo nhân viên).

    Dùng để kiểm tra công bố lịch đã phát đủ cho từng VAI TRÒ chưa: quản lý nhận
    link `/lich-tuan` (xem cả quán), nhân viên nhận link `/toi` (lịch của mình).
    `thong_bao_lich_list` không trả được câu trả lời đó vì nó buộc lọc một nv_id.
    """
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            """SELECT * FROM thong_bao_lich
               WHERE store_id=? AND tuan_iso=?
               ORDER BY created_at DESC LIMIT 200""",
            (store_id, tuan_iso),
        ).fetchall()
        return [dict(row) for row in rows]


def thong_bao_lich_ack(
    notification_id: str, nv_id: str, *, store_id: str = DEFAULT_STORE_ID
) -> bool:
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE thong_bao_lich SET da_xem=1 WHERE id=? AND store_id=? AND nv_id=?",
            (notification_id, store_id, nv_id),
        )
        return bool(cur.rowcount > 0)


def set_user_email(username: str, email: str) -> dict[str, str]:
    """Nick cập nhật gmail của chính mình (hoặc quản lý cập nhật cho NV)."""
    u = (username or "").strip().lower()
    em = (email or "").strip()
    init_db()
    with _conn() as cx:
        row = cx.execute("SELECT username FROM users WHERE username=?", (u,)).fetchone()
        if not row:
            raise DangKyLoi("khong_co_tai_khoan")
        cx.execute("UPDATE users SET email=? WHERE username=?", (em, u))
        return {"username": u, "email": em}


def get_user_emails() -> dict[str, str]:
    """Trả map nv_id -> email (đã set). Dùng cho AI gửi mail."""
    init_db()
    with _conn() as cx:
        rows = cx.execute("SELECT nv_id, email FROM users WHERE email != ''").fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


# ── Gmail Account Management ──────────────────────────────────────────────


def gmail_account_create(
    *,
    store_id: str,
    nv_id: str,
    email: str,
    display_name: str = "",
    is_primary: bool = False,
) -> dict[str, Any]:
    """Tạo tài khoản Gmail mới cho nhân viên."""
    import uuid
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        # Nếu set is_primary, bỏ primary của account cũ
        if is_primary:
            cx.execute(
                "UPDATE gmail_accounts SET is_primary=0 WHERE store_id=? AND nv_id=?",
                (store_id, nv_id),
            )
        account_id = f"gmail_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        cx.execute(
            """INSERT INTO gmail_accounts
               (id, store_id, nv_id, email, display_name, is_primary, is_active, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (account_id, store_id, nv_id, email, display_name, 1 if is_primary else 0, 1, now, now),
        )
    return {
        "id": account_id,
        "store_id": store_id,
        "nv_id": nv_id,
        "email": email,
        "display_name": display_name,
        "is_primary": is_primary,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


def gmail_account_list(store_id: str, nv_id: str | None = None) -> list[dict[str, Any]]:
    """Liệt kê tài khoản Gmail của quán hoặc nhân viên."""
    init_db()
    with _conn() as cx:
        if nv_id:
            rows = cx.execute(
                """SELECT id, store_id, nv_id, email, display_name, is_primary, is_active, created_at, updated_at
                   FROM gmail_accounts WHERE store_id=? AND nv_id=? AND is_active=1
                   ORDER BY is_primary DESC, created_at DESC""",
                (store_id, nv_id),
            ).fetchall()
        else:
            rows = cx.execute(
                """SELECT id, store_id, nv_id, email, display_name, is_primary, is_active, created_at, updated_at
                   FROM gmail_accounts WHERE store_id=? AND is_active=1
                   ORDER BY nv_id, is_primary DESC, created_at DESC""",
                (store_id,),
            ).fetchall()
    return [
        {
            "id": str(r[0]),
            "store_id": str(r[1]),
            "nv_id": str(r[2]),
            "email": str(r[3]),
            "display_name": str(r[4]),
            "is_primary": bool(r[5]),
            "is_active": bool(r[6]),
            "created_at": str(r[7]),
            "updated_at": str(r[8]),
        }
        for r in rows
    ]


def gmail_account_get(account_id: str) -> dict[str, Any] | None:
    """Lấy chi tiết tài khoản Gmail."""
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """SELECT id, store_id, nv_id, email, display_name, is_primary, is_active, created_at, updated_at
               FROM gmail_accounts WHERE id=?""",
            (account_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "store_id": str(row[1]),
        "nv_id": str(row[2]),
        "email": str(row[3]),
        "display_name": str(row[4]),
        "is_primary": bool(row[5]),
        "is_active": bool(row[6]),
        "created_at": str(row[7]),
        "updated_at": str(row[8]),
    }


def gmail_account_update(
    account_id: str,
    *,
    display_name: str | None = None,
    is_primary: bool | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    """Cập nhật tài khoản Gmail."""
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT store_id, nv_id FROM gmail_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if not row:
            return None
        store_id, nv_id = str(row[0]), str(row[1])
        if is_primary:
            cx.execute(
                "UPDATE gmail_accounts SET is_primary=0 WHERE store_id=? AND nv_id=?",
                (store_id, nv_id),
            )
        sets = []
        params: list[str | int] = []
        if display_name is not None:
            sets.append("display_name=?")
            params.append(display_name)
        if is_primary is not None:
            sets.append("is_primary=?")
            params.append(1 if is_primary else 0)
        if is_active is not None:
            sets.append("is_active=?")
            params.append(1 if is_active else 0)
        if not sets:
            return gmail_account_get(account_id)
        sets.append("updated_at=?")
        params.append(datetime.now(UTC).isoformat())
        params.append(account_id)
        cx.execute(f"UPDATE gmail_accounts SET {', '.join(sets)} WHERE id=?", params)
    return gmail_account_get(account_id)


def gmail_account_delete(account_id: str) -> bool:
    """Xoá tài khoản Gmail kèm toàn bộ dữ liệu con.

    Xoá con TƯỜNG MINH thay vì trông cậy `ON DELETE CASCADE`: DB tạo trước khi
    có ràng buộc FK (hoặc Postgres chưa migrate) vẫn phải dọn sạch, nếu không
    token/email mồ côi sẽ tồn tại vĩnh viễn trong DB.
    """
    init_db()
    with _conn() as cx:
        for table in (
            "gmail_oauth_tokens",
            "gmail_messages",
            "gmail_labels",
            "gmail_filters",
            "gmail_sync_state",
        ):
            cx.execute(f"DELETE FROM {table} WHERE account_id=?", (account_id,))
        cur = cx.execute("DELETE FROM gmail_accounts WHERE id=?", (account_id,))
    return bool(cur.rowcount > 0)


# ── Gmail OAuth Tokens ────────────────────────────────────────────────────


def gmail_token_save(
    account_id: str,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_at: str,
    scope: str = "",
    token_type: str = "Bearer",
) -> None:
    """Lưu OAuth token (đã mã hoá) cho tài khoản Gmail."""
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        cx.execute(
            """INSERT INTO gmail_oauth_tokens
               (account_id, access_token_enc, refresh_token_enc, expires_at, scope, token_type, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(account_id) DO UPDATE SET
                 access_token_enc=excluded.access_token_enc,
                 refresh_token_enc=excluded.refresh_token_enc,
                 expires_at=excluded.expires_at,
                 scope=excluded.scope,
                 token_type=excluded.token_type,
                 updated_at=excluded.updated_at""",
            (
                account_id,
                _encrypt(access_token),
                _encrypt(refresh_token) if refresh_token else None,
                expires_at,
                scope,
                token_type,
                datetime.now(UTC).isoformat(),
            ),
        )


def gmail_token_get(account_id: str) -> dict[str, Any] | None:
    """Lấy OAuth token (giải mã) cho tài khoản Gmail."""
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """SELECT access_token_enc, refresh_token_enc, expires_at, scope, token_type, updated_at
               FROM gmail_oauth_tokens WHERE account_id=?""",
            (account_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "access_token": _decrypt(str(row[0])),
        "refresh_token": _decrypt(str(row[1])) if row[1] else None,
        "expires_at": str(row[2]),
        "scope": str(row[3]),
        "token_type": str(row[4]),
        "updated_at": str(row[5]),
    }


def gmail_token_health(account_id: str) -> str | None:
    """Sức khoẻ token: `None` (chưa có), `"ok"`, hay `"broken"` (không giải mã được).

    Gọi sau `gmail_token_status` khi cần biết token có DÙNG ĐƯỢC hay không —
    ví dụ khoá mã hoá đã đổi thì UI phải mời người dùng kết nối lại thay vì
    hiển thị "Đã kết nối" rồi để mọi thao tác thất bại.
    """
    if gmail_token_status(account_id) is None:
        return None
    try:
        tokens = gmail_token_get(account_id)
    except Exception:  # noqa: BLE001 — InvalidToken của Fernet khi khoá đổi
        return "broken"
    return "ok" if tokens and tokens.get("access_token") else "broken"


def gmail_token_status_bulk(account_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Trạng thái token cho NHIỀU tài khoản trong MỘT truy vấn.

    Tránh N+1 khi liệt kê tài khoản: gọi `gmail_token_status` cho từng tài khoản
    tốn 1 query mỗi lần, nên danh sách 20 tài khoản thành 20+ query.
    """
    if not account_ids:
        return {}
    init_db()
    placeholders = ",".join("?" * len(account_ids))
    with _conn() as cx:
        rows = cx.execute(
            f"""SELECT account_id, expires_at, scope, token_type,
                       refresh_token_enc IS NOT NULL, updated_at
                FROM gmail_oauth_tokens WHERE account_id IN ({placeholders})""",
            tuple(account_ids),
        ).fetchall()
    return {
        str(r[0]): {
            "expires_at": str(r[1]) if r[1] else None,
            "scope": str(r[2]),
            "token_type": str(r[3]),
            "has_refresh_token": bool(r[4]),
            "updated_at": str(r[5]),
        }
        for r in rows
    }


def gmail_token_delete(account_id: str) -> bool:
    """Xoá OAuth token."""
    init_db()
    with _conn() as cx:
        cur = cx.execute("DELETE FROM gmail_oauth_tokens WHERE account_id=?", (account_id,))
    return bool(cur.rowcount > 0)


def gmail_token_status(account_id: str) -> dict[str, Any] | None:
    """Trạng thái token KHÔNG giải mã — an toàn để hiển thị trên UI.

    Dùng cho các endpoint chỉ cần biết "đã kết nối chưa" và "hết hạn chưa".
    Không bao giờ gọi `_decrypt` ở đây: nếu khoá mã hoá đã đổi (hoặc key tạm
    sinh rồi restart), giải mã sẽ ném `InvalidToken` và làm sập cả trang, khiến
    người dùng KHÔNG mở được UI để kết nối lại.
    """
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """SELECT expires_at, scope, token_type, refresh_token_enc IS NOT NULL, updated_at
               FROM gmail_oauth_tokens WHERE account_id=?""",
            (account_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "expires_at": str(row[0]) if row[0] else None,
        "scope": str(row[1]),
        "token_type": str(row[2]),
        "has_refresh_token": bool(row[3]),
        "updated_at": str(row[4]),
    }


# ── Gmail Sync State ──────────────────────────────────────────────────────


def gmail_sync_state_get(account_id: str) -> dict[str, Any] | None:
    """Lấy trạng thái đồng bộ Gmail."""
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """SELECT account_id, last_history_id, last_sync_at, sync_cursor, total_messages, unread_count, updated_at
               FROM gmail_sync_state WHERE account_id=?""",
            (account_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "account_id": str(row[0]),
        "last_history_id": str(row[1]) if row[1] else None,
        "last_sync_at": str(row[2]) if row[2] else None,
        "sync_cursor": str(row[3]) if row[3] else None,
        "total_messages": int(row[4]),
        "unread_count": int(row[5]),
        "updated_at": str(row[6]),
    }


def gmail_sync_state_upsert(
    account_id: str,
    *,
    last_history_id: str | None = None,
    last_sync_at: str | None = None,
    sync_cursor: str | None = None,
    total_messages: int | None = None,
    unread_count: int | None = None,
) -> dict[str, Any]:
    """Cập nhật trạng thái đồng bộ Gmail.

    `total_messages`/`unread_count` chỉ ghi khi được truyền tường minh. Truyền
    `None` (ví dụ đồng bộ tăng dần chỉ biết history id) phải GIỮ giá trị cũ,
    không được hạ về 0.
    """
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        now = datetime.now(UTC).isoformat()
        cx.execute(
            """INSERT INTO gmail_sync_state
               (account_id, last_history_id, last_sync_at, sync_cursor, total_messages, unread_count, updated_at)
               VALUES (?,?,?,?,COALESCE(?,0),COALESCE(?,0),?)
               ON CONFLICT(account_id) DO UPDATE SET
                 last_history_id=COALESCE(excluded.last_history_id, gmail_sync_state.last_history_id),
                 last_sync_at=COALESCE(excluded.last_sync_at, gmail_sync_state.last_sync_at),
                 sync_cursor=COALESCE(excluded.sync_cursor, gmail_sync_state.sync_cursor),
                 total_messages=COALESCE(?, gmail_sync_state.total_messages),
                 unread_count=COALESCE(?, gmail_sync_state.unread_count),
                 updated_at=excluded.updated_at""",
            (
                account_id,
                last_history_id,
                last_sync_at or now,
                sync_cursor,
                total_messages,
                unread_count,
                now,
                total_messages,
                unread_count,
            ),
        )
    return gmail_sync_state_get(account_id) or {}


# ── Gmail Messages ────────────────────────────────────────────────────────


def gmail_message_upsert(
    account_id: str,
    *,
    message_id: str,
    thread_id: str,
    label_ids: list[str],
    snippet: str,
    from_email: str,
    to_emails: list[str],
    cc_emails: list[str],
    subject: str,
    body_text: str | None,
    body_html: str | None,
    internal_date: str,
    is_read: bool,
    is_starred: bool,
    has_attachment: bool,
    raw_headers: str | None = None,
) -> None:
    """Upsert email message."""
    import json
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        cx.execute(
            """INSERT INTO gmail_messages
               (id, account_id, thread_id, label_ids, snippet, from_email, to_emails, cc_emails,
                subject, body_text, body_html, internal_date, is_read, is_starred, has_attachment, raw_headers, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 thread_id=excluded.thread_id,
                 label_ids=excluded.label_ids,
                 snippet=excluded.snippet,
                 from_email=excluded.from_email,
                 to_emails=excluded.to_emails,
                 cc_emails=excluded.cc_emails,
                 subject=excluded.subject,
                 body_text=excluded.body_text,
                 body_html=excluded.body_html,
                 internal_date=excluded.internal_date,
                 is_read=excluded.is_read,
                 is_starred=excluded.is_starred,
                 has_attachment=excluded.has_attachment,
                 raw_headers=excluded.raw_headers""",
            (
                message_id,
                account_id,
                thread_id,
                json.dumps(label_ids, ensure_ascii=False),
                snippet,
                from_email,
                json.dumps(to_emails, ensure_ascii=False),
                json.dumps(cc_emails, ensure_ascii=False),
                subject,
                body_text,
                body_html,
                internal_date,
                1 if is_read else 0,
                1 if is_starred else 0,
                1 if has_attachment else 0,
                raw_headers,
                datetime.now(UTC).isoformat(),
            ),
        )


def gmail_messages_list(
    account_id: str,
    *,
    label_ids: list[str] | None = None,
    query: str | None = None,
    is_read: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Liệt kê email với bộ lọc."""
    import json

    init_db()
    with _conn() as cx:
        where = ["account_id=?"]
        params: list[Any] = [account_id]
        if label_ids:
            # `label_ids` lưu dạng JSON array. So khớp phần tử chính xác bằng
            # cặp dấu ngoặc kép bao quanh, và escape ký tự đại diện của LIKE
            # để nhãn chứa `%`/`_` không khớp nhầm.
            like_conditions = " OR ".join(["label_ids LIKE ? ESCAPE '\\'"] * len(label_ids))
            where.append(f"({like_conditions})")
            for lid in label_ids:
                escaped = str(lid).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                params.append(f'%"{escaped}"%')
        if query:
            where.append(
                "(subject LIKE ? ESCAPE '\\' OR snippet LIKE ? ESCAPE '\\' "
                "OR from_email LIKE ? ESCAPE '\\')"
            )
            escaped = str(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            q = f"%{escaped}%"
            params.extend([q, q, q])
        if is_read is not None:
            where.append("is_read=?")
            params.append(1 if is_read else 0)
        sql = f"""SELECT id, account_id, thread_id, label_ids, snippet, from_email, to_emails, cc_emails,
                         subject, body_text, body_html, internal_date, is_read, is_starred, has_attachment, raw_headers, created_at
                  FROM gmail_messages
                  WHERE {" AND ".join(where)}
                  ORDER BY internal_date DESC
                  LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        rows = cx.execute(sql, params).fetchall()
    return [
        {
            "id": str(r[0]),
            "account_id": str(r[1]),
            "thread_id": str(r[2]),
            "label_ids": json.loads(r[3]),
            "snippet": str(r[4]),
            "from_email": str(r[5]),
            "to_emails": json.loads(r[6]),
            "cc_emails": json.loads(r[7]),
            "subject": str(r[8]),
            "body_text": r[9],
            "body_html": r[10],
            "internal_date": str(r[11]),
            "is_read": bool(r[12]),
            "is_starred": bool(r[13]),
            "has_attachment": bool(r[14]),
            "raw_headers": r[15],
            "created_at": str(r[16]),
        }
        for r in rows
    ]


def gmail_message_get(account_id: str, message_id: str) -> dict[str, Any] | None:
    """Lấy chi tiết một email."""
    import json

    init_db()
    with _conn() as cx:
        row = cx.execute(
            """SELECT id, account_id, thread_id, label_ids, snippet, from_email, to_emails, cc_emails,
                         subject, body_text, body_html, internal_date, is_read, is_starred, has_attachment, raw_headers, created_at
                  FROM gmail_messages WHERE account_id=? AND id=?""",
            (account_id, message_id),
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "account_id": str(row[1]),
        "thread_id": str(row[2]),
        "label_ids": json.loads(row[3]),
        "snippet": str(row[4]),
        "from_email": str(row[5]),
        "to_emails": json.loads(row[6]),
        "cc_emails": json.loads(row[7]),
        "subject": str(row[8]),
        "body_text": row[9],
        "body_html": row[10],
        "internal_date": str(row[11]),
        "is_read": bool(row[12]),
        "is_starred": bool(row[13]),
        "has_attachment": bool(row[14]),
        "raw_headers": row[15],
        "created_at": str(row[16]),
    }


def gmail_message_mark_read(account_id: str, message_id: str, is_read: bool = True) -> bool:
    """Đánh dấu email đã đọc/chưa đọc."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE gmail_messages SET is_read=? WHERE account_id=? AND id=?",
            (1 if is_read else 0, account_id, message_id),
        )
    return bool(cur.rowcount > 0)


def gmail_message_star(account_id: str, message_id: str, is_starred: bool = True) -> bool:
    """Gắn/bỏ sao email."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE gmail_messages SET is_starred=? WHERE account_id=? AND id=?",
            (1 if is_starred else 0, account_id, message_id),
        )
    return bool(cur.rowcount > 0)


def gmail_message_delete(account_id: str, message_id: str) -> bool:
    """Xoá một email (Gmail báo đã xoá vĩnh viễn qua history)."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "DELETE FROM gmail_messages WHERE account_id=? AND id=?", (account_id, message_id)
        )
    return bool(cur.rowcount > 0)


def gmail_message_apply_labels(account_id: str, message_id: str, label_ids: list[str]) -> bool:
    """Ghi lại tập nhãn mới và suy ra `is_read`/`is_starred` từ nhãn.

    Gmail biểu diễn "chưa đọc" bằng nhãn `UNREAD` và "có sao" bằng `STARRED`,
    nên khi history báo đổi nhãn thì trạng thái đọc/sao phải cập nhật theo —
    nếu không, hộp thư trong app sẽ mãi hiển thị trạng thái cũ.
    """
    import json

    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """UPDATE gmail_messages
               SET label_ids=?, is_read=?, is_starred=?
               WHERE account_id=? AND id=?""",
            (
                json.dumps(label_ids, ensure_ascii=False),
                0 if "UNREAD" in label_ids else 1,
                1 if "STARRED" in label_ids else 0,
                account_id,
                message_id,
            ),
        )
    return bool(cur.rowcount > 0)


def gmail_message_exists(account_id: str, message_id: str) -> bool:
    """Email đã có trong DB local chưa."""
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT 1 FROM gmail_messages WHERE account_id=? AND id=?", (account_id, message_id)
        ).fetchone()
    return row is not None


# ── Gmail Labels ──────────────────────────────────────────────────────────


def gmail_label_upsert(
    account_id: str,
    *,
    label_id: str,
    name: str,
    label_type: str = "user",
    message_list_visibility: str = "show",
    label_list_visibility: str = "labelShow",
    color_background: str | None = None,
    color_text: str | None = None,
    total_messages: int = 0,
    unread_messages: int = 0,
) -> None:
    """Upsert Gmail label."""
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        cx.execute(
            """INSERT INTO gmail_labels
               (id, account_id, name, label_type, message_list_visibility, label_list_visibility,
                color_background, color_text, total_messages, unread_messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name,
                 label_type=excluded.label_type,
                 message_list_visibility=excluded.message_list_visibility,
                 label_list_visibility=excluded.label_list_visibility,
                 color_background=excluded.color_background,
                 color_text=excluded.color_text,
                 total_messages=excluded.total_messages,
                 unread_messages=excluded.unread_messages,
                 updated_at=excluded.updated_at""",
            (
                label_id,
                account_id,
                name,
                label_type,
                message_list_visibility,
                label_list_visibility,
                color_background,
                color_text,
                total_messages,
                unread_messages,
                datetime.now(UTC).isoformat(),
            ),
        )


def gmail_labels_list(account_id: str) -> list[dict[str, Any]]:
    """Liệt kê labels của tài khoản."""
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """SELECT id, account_id, name, label_type, message_list_visibility, label_list_visibility,
                      color_background, color_text, total_messages, unread_messages, updated_at
               FROM gmail_labels WHERE account_id=?
               ORDER BY name""",
            (account_id,),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "account_id": str(r[1]),
            "name": str(r[2]),
            "label_type": str(r[3]),
            "message_list_visibility": str(r[4]),
            "label_list_visibility": str(r[5]),
            "color_background": r[6],
            "color_text": r[7],
            "total_messages": int(r[8]),
            "unread_messages": int(r[9]),
            "updated_at": str(r[10]),
        }
        for r in rows
    ]


def gmail_label_delete(account_id: str, label_id: str) -> bool:
    """Xoá label."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "DELETE FROM gmail_labels WHERE account_id=? AND id=?", (account_id, label_id)
        )
    return bool(cur.rowcount > 0)


# ── Gmail Filters ─────────────────────────────────────────────────────────


def gmail_filter_upsert(
    account_id: str,
    *,
    filter_id: str,
    criteria: dict[str, Any],
    action: dict[str, Any],
) -> None:
    """Upsert Gmail filter."""
    import json
    from datetime import UTC, datetime

    init_db()
    with _conn() as cx:
        cx.execute(
            """INSERT INTO gmail_filters
               (id, account_id, criteria, action, created_at, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 criteria=excluded.criteria,
                 action=excluded.action,
                 updated_at=excluded.updated_at""",
            (
                filter_id,
                account_id,
                json.dumps(criteria, ensure_ascii=False),
                json.dumps(action, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )


def gmail_filters_list(account_id: str) -> list[dict[str, Any]]:
    """Liệt kê filters của tài khoản."""
    import json

    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """SELECT id, account_id, criteria, action, created_at, updated_at
               FROM gmail_filters WHERE account_id=?
               ORDER BY created_at DESC""",
            (account_id,),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "account_id": str(r[1]),
            "criteria": json.loads(r[2]),
            "action": json.loads(r[3]),
            "created_at": str(r[4]),
            "updated_at": str(r[5]),
        }
        for r in rows
    ]


def gmail_filter_delete(account_id: str, filter_id: str) -> bool:
    """Xoá filter."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "DELETE FROM gmail_filters WHERE account_id=? AND id=?", (account_id, filter_id)
        )
    return bool(cur.rowcount > 0)


class NangVaiLoi(ValueError):
    def __init__(self, ma: str) -> None:
        super().__init__(ma)
        self.ma = ma


def set_role(username: str, role: str) -> dict[str, str]:
    """Chủ quán nâng nhân viên lên quản lý. Không tự phong chủ quán."""
    if role != "quan_ly":
        raise NangVaiLoi("vai_khong_hop_le")
    u = (username or "").strip().lower()
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT username, role, nv_id, display_name FROM users WHERE username=?", (u,)
        ).fetchone()
        if not row:
            raise NangVaiLoi("khong_co_tai_khoan")
        if row[1] == "chu_quan":
            raise NangVaiLoi("khong_doi_chu_quan")
        if row[1] == "quan_ly":
            return {
                "username": str(row[0]),
                "role": str(row[1]),
                "nv_id": str(row[2]),
                "display_name": str(row[3]),
            }
        if row[1] != "nhan_vien":
            raise NangVaiLoi("vai_khong_hop_le")
        cx.execute("UPDATE users SET role=? WHERE username=?", (role, u))
        cx.execute("UPDATE sessions SET role=? WHERE username=?", (role, u))
        return {
            "username": str(row[0]),
            "role": role,
            "nv_id": str(row[2]),
            "display_name": str(row[3]),
        }


def ha_vai(username: str) -> dict[str, str]:
    """Chủ quán hạ quản lý xuống nhân viên."""
    u = (username or "").strip().lower()
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT username, role, nv_id, display_name FROM users WHERE username=?", (u,)
        ).fetchone()
        if not row:
            raise NangVaiLoi("khong_co_tai_khoan")
        if row[1] == "chu_quan":
            raise NangVaiLoi("khong_doi_chu_quan")
        if row[1] != "quan_ly":
            raise NangVaiLoi("vai_khong_hop_le")
        cx.execute("UPDATE users SET role=? WHERE username=?", ("nhan_vien", u))
        cx.execute("UPDATE sessions SET role=? WHERE username=?", ("nhan_vien", u))
        return {
            "username": str(row[0]),
            "role": "nhan_vien",
            "nv_id": str(row[2]),
            "display_name": str(row[3]),
        }


def _menu_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "ten": str(row[1]),
        "gia": int(row[2]),
        "an": bool(row[3]),
        "bom": json.loads(row[4]) if row[4] else {},
        "hinh_url": str(row[5]) if len(row) > 5 and row[5] else "",
        "nhom": str(row[6]) if len(row) > 6 and row[6] else "",
    }


_MENU_COLS = "id, ten, gia, an, bom, hinh_url, nhom"


def menu_list(*, gom_an: bool = False) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(f"SELECT {_MENU_COLS} FROM menu_mon ORDER BY ten").fetchall()
    out = []
    for row in rows:
        if not gom_an and int(row[3]):
            continue
        out.append(_menu_from_row(row))
    return out


def menu_upsert(mon: dict[str, Any]) -> dict[str, Any]:
    init_db()
    from ca_api.nguyen_lieu import chuan_hoa_bom

    mid = str(mon["id"]).strip()
    ten = str(mon["ten"]).strip()
    gia = int(mon["gia"])
    an = 1 if mon.get("an") else 0
    hinh_url = str(mon.get("hinh_url") or "").strip()
    nhom = str(mon.get("nhom") or "").strip()
    # Cửa chặn DUY NHẤT khi ghi menu: khoá BOM quy về mã chuẩn trước khi chạm DB.
    # `menu_luu` (PUT món) đã làm việc này, nhưng seed/migration/script ghi thẳng
    # qua đây — bỏ qua thì mã legacy lại chui vào và sinh mặt hàng trùng ở
    # `/tieu-thu`.
    bom = json.dumps(chuan_hoa_bom(mon.get("bom")), ensure_ascii=False)
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO menu_mon(id, ten, gia, an, bom, hinh_url, nhom)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET ten=excluded.ten, gia=excluded.gia,
                an=excluded.an, bom=excluded.bom, hinh_url=excluded.hinh_url,
                nhom=excluded.nhom
            """,
            (mid, ten, gia, an, bom, hinh_url, nhom),
        )
    return _menu_from_row((mid, ten, gia, an, bom, hinh_url, nhom))


def menu_get(mon_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(f"SELECT {_MENU_COLS} FROM menu_mon WHERE id=?", (mon_id,)).fetchone()
    if not row:
        return None
    return _menu_from_row(row)


def menu_set_hinh(mon_id: str, hinh_url: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(f"SELECT {_MENU_COLS} FROM menu_mon WHERE id=?", (mon_id,)).fetchone()
        if not row:
            return None
        cx.execute("UPDATE menu_mon SET hinh_url=? WHERE id=?", (hinh_url, mon_id))
    return _menu_from_row((*row[:5], hinh_url, row[6]))


def don_insert(don: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO don_quay(id, nv_id, trang_thai, thanh_toan, dong, ly_do_huy, luc)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                don["id"],
                don["nv_id"],
                don["trang_thai"],
                don["thanh_toan"],
                json.dumps(don["dong"], ensure_ascii=False),
                don.get("ly_do_huy"),
                don["luc"],
            ),
        )
    return don


def don_list(
    *,
    trang_thai: str | None = None,
    tu: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Đơn quầy, mới trước.

    `tu` lọc theo mốc thời gian (ISO-8601) để cột "đã xong"/"đã hủy" không vẽ
    cả lịch sử của quán. `limit` chặn trả nguyên bảng — bản trước không có hai
    tham số này nên `/pha` vẽ hết mọi đơn từng tồn tại.

    Có `trang_thai` thì SẮP XẾP CŨ TRƯỚC (đơn nào tới trước thì pha trước),
    không có thì MỚI TRƯỚC (bảng điều khiển muốn thấy cái vừa xảy ra).
    """
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if trang_thai:
        where.append("trang_thai=?")
        params.append(trang_thai)
    if tu:
        where.append("luc>=?")
        params.append(tu)
    dieu_kien = f" WHERE {' AND '.join(where)}" if where else ""
    thu_tu = "luc" if trang_thai else "luc DESC"
    # `limit` gắn vào SQL chứ không cắt sau: cắt sau thì trang offset phải kéo cả
    # bảng về, và mốc cắt không ổn định khi có đơn mới chen vào.
    han = f" LIMIT {int(limit)}" if limit else ""
    with _conn() as cx:
        rows = cx.execute(
            f"""
            SELECT id, nv_id, trang_thai, thanh_toan, dong, ly_do_huy, luc
            FROM don_quay{dieu_kien} ORDER BY {thu_tu}{han}
            """,
            tuple(params),
        ).fetchall()
    return [_don_row(r) for r in rows]


def don_get(don_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT id, nv_id, trang_thai, thanh_toan, dong, ly_do_huy, luc
            FROM don_quay WHERE id=?
            """,
            (don_id,),
        ).fetchone()
    return _don_row(row) if row else None


def don_update(don: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _conn() as cx:
        cx.execute(
            """
            UPDATE don_quay SET trang_thai=?, thanh_toan=?, dong=?, ly_do_huy=?
            WHERE id=?
            """,
            (
                don["trang_thai"],
                don["thanh_toan"],
                json.dumps(don["dong"], ensure_ascii=False),
                don.get("ly_do_huy"),
                don["id"],
            ),
        )
    return don


def don_chuyen_trang_thai(
    don_id: str, *, tu: str, sang: str, ly_do_huy: str | None = None
) -> dict[str, Any] | None:
    """Chuyển trạng thái đơn quầy bằng COMPARE-AND-SWAP nguyên tử.

    Vì sao không dùng `don_get` rồi `don_update`: đó là read-then-write không
    khoá. Hai request đồng thời (double-click, retry mạng) cùng đọc
    ``cho_pha``, cùng thấy hợp lệ, rồi cùng ghi ``xong`` — cả hai đều qua cổng
    `_STATUS_NEXT` nên đều trả 200, và `_ghi_tieu_thu_uoc_luong` chạy HAI lần
    → kho bị trừ gấp đôi (bug QA đợt 5, tái hiện được: +6 dòng thay vì +3).

    Câu UPDATE dưới đây chỉ khớp khi trạng thái trong DB VẪN là ``tu``; kẻ đến
    sau thấy ``rowcount == 0`` nên biết mình thua cuộc đua và trả ``None``.
    Cách này đúng trên cả SQLite (ghi tuần tự, ``rowcount`` đáng tin) lẫn
    Postgres (row bị khoá khi UPDATE), không cần thêm lock ngoài.
    """
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """
            UPDATE don_quay SET trang_thai=?, ly_do_huy=?
            WHERE id=? AND trang_thai=?
            """,
            (sang, ly_do_huy, don_id, tu),
        )
        if cur.rowcount != 1:
            return None
    return don_get(don_id)


def _don_row(r: tuple[Any, ...]) -> dict[str, Any]:
    # `dong` là TEXT do nhiều nơi ghi (API, seeder Quảnverse, script dọn dữ liệu).
    # Đọc hỏng KHÔNG được làm sập cả danh sách đơn: hàng đó vẫn hiện được ở
    # `/pha` với `dong = []` để nhân viên còn hủy được, thay vì 500 làm mất trắng
    # mọi đơn khác. Nguyên nhân gốc đã bị chặn ở migration 0018 + seeder.
    try:
        dong = json.loads(r[4])
    except (TypeError, ValueError):
        dong = []
    return {
        "id": str(r[0]),
        "nv_id": str(r[1]),
        "trang_thai": str(r[2]),
        "thanh_toan": str(r[3]),
        "dong": [x for x in dong if isinstance(x, dict)] if isinstance(dong, list) else [],
        "ly_do_huy": r[5],
        "luc": str(r[6]),
        "nguon": "quay_noi_bo",
    }


def tieu_thu_append(item: dict[str, Any]) -> None:
    def mut(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.append(item)
        return rows

    kv_mutate("tieu_thu", mut, [])


def diem_danh_hom_nay() -> list[str]:
    """Danh sách nv_id đã điểm danh HÔM NAY (giờ Việt Nam, UTC+7).

    Trước đây khoá kv ``diem_danh`` là list nv_id tích luỹ vĩnh viễn —
    sau lần check-in đầu tiên, cổng ``chua_diem_danh`` ở ``phieu_start``
    thông mãi mãi, ngày hôm sau không quét QR vẫn mở được phiếu.
    Giờ khoá này là dict ``{ngay: [nv_id, ...]}`` keyed theo ngày ISO;
    list cũ (dạng ``[nv_id, ...]``) được đọc tương thích ngược.
    """
    raw = kv_get("diem_danh", {})
    if isinstance(raw, list):
        # Bản cũ: không biết check-in ngày nào → coi như ngày đầu tiên
        # có dữ liệu (an toàn phía nhân viên, không khoá ai ngoài giờ).
        return [str(x) for x in raw]
    if not isinstance(raw, dict):
        return []
    hom_nay = datetime.now(_VN_TZ).date().isoformat()
    rows = raw.get(hom_nay)
    if isinstance(rows, list):
        return [str(x) for x in rows]
    return []


def da_diem_danh(nv_id: str) -> bool:
    return nv_id in set(diem_danh_hom_nay())


def ghi_diem_danh(nv_id: str) -> None:
    """Ghi nhận nv_id đã có mặt hôm nay (giờ Việt Nam).

    Khoá kv ``diem_danh`` từng là list nv_id tích luỹ vĩnh viễn, nay là dict
    ``{ngay: [nv_id, ...]}``. ``diem_danh_hom_nay`` vẫn đọc được list cũ nên
    DB seed từ trước còn giữ dạng đó; nếu hàm ghi chỉ biết dict thì nó ném
    ``AttributeError`` và endpoint trả 500 — nhân viên không điểm danh được,
    phiếu không mở. Vì vậy list cũ được nâng cấp tại chỗ thành dict, giữ đúng
    ngữ nghĩa mà bên đọc đã quy ước (coi như điểm danh hôm nay).
    """
    hom_nay = datetime.now(_VN_TZ).date().isoformat()

    def mut(dd: Any) -> dict[str, list[str]]:
        if not isinstance(dd, dict):
            # Bản cũ dạng list, hoặc dữ liệu hỏng → nâng cấp, không giữ lại rác.
            cu = [str(x) for x in dd] if isinstance(dd, list) else []
            dd = {hom_nay: cu} if cu else {}
        hom_nay_list = dd.get(hom_nay)
        if not isinstance(hom_nay_list, list):
            hom_nay_list = []
        if nv_id not in hom_nay_list:
            hom_nay_list.append(nv_id)
        dd[hom_nay] = hom_nay_list
        return cast(dict[str, list[str]], dd)

    kv_mutate("diem_danh", mut, {})


def audit_list(limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            "SELECT id, at, ai, hanh, payload, actor_type, agent_name, controller_user_id "
            "FROM audit ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    out = []
    for row in rows:
        row_id, at, ai, hanh, payload, actor_type, agent_name, controller_user_id = row
        details = json.loads(payload) if payload else {}
        item = dict(details) if isinstance(details, dict) else {"value": details}
        item.update(
            {
                "id": row_id,
                "at": at,
                "ai": ai,
                "hanh": hanh,
                "payload": details,
                "actor_type": actor_type or resolve_actor_type(ai).value,
                "agent_name": agent_name,
                "controller_user_id": controller_user_id,
            }
        )
        out.append(item)
    return out


# ── Copilot Drafts & Audit ───────────────────────────────────────────────────


def copilot_draft_save(draft: dict[str, Any]) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO copilot_draft_actions(
                action_id, intent, status, store_id, created_by, confidence,
                summary, explanation, payload_diff, requires_confirmation,
                data_snapshot_hash, expires_at, created_at, executed_at,
                amended_from, amended_by
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(action_id) DO UPDATE SET
                status=excluded.status,
                summary=excluded.summary,
                explanation=excluded.explanation,
                payload_diff=excluded.payload_diff,
                data_snapshot_hash=excluded.data_snapshot_hash,
                expires_at=excluded.expires_at,
                executed_at=excluded.executed_at,
                amended_from=excluded.amended_from,
                amended_by=excluded.amended_by
            """,
            (
                draft["action_id"],
                draft["intent"],
                draft.get("status", "draft"),
                draft.get("store_id", "quan_01"),
                draft.get("created_by", "system"),
                float(draft.get("confidence", 1.0)),
                draft.get("summary", ""),
                draft.get("explanation", ""),
                json.dumps(draft.get("payload_diff", {}), ensure_ascii=False),
                1 if draft.get("requires_confirmation", True) else 0,
                draft.get("data_snapshot_hash", ""),
                draft.get("expires_at", ""),
                draft.get("created_at", ""),
                draft.get("executed_at"),
                draft.get("amended_from"),
                draft.get("amended_by"),
            ),
        )


def copilot_draft_get(action_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT action_id, intent, status, store_id, created_by, confidence,
                   summary, explanation, payload_diff, requires_confirmation,
                   data_snapshot_hash, expires_at, created_at, executed_at,
                   amended_from, amended_by
            FROM copilot_draft_actions WHERE action_id=?
            """,
            (action_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "action_id": str(row[0]),
            "intent": str(row[1]),
            "status": str(row[2]),
            "store_id": str(row[3]),
            "created_by": str(row[4]),
            "confidence": float(row[5]),
            "summary": str(row[6]),
            "explanation": str(row[7]),
            "payload_diff": json.loads(row[8]),
            "requires_confirmation": bool(row[9]),
            "data_snapshot_hash": str(row[10]),
            "expires_at": str(row[11]),
            "created_at": str(row[12]),
            "executed_at": str(row[13]) if row[13] else None,
            "amended_from": str(row[14]) if row[14] else None,
            "amended_by": str(row[15]) if row[15] else None,
        }


def copilot_draft_update_status(
    action_id: str,
    status: str,
    executed_at: str | None = None,
    amended_from: str | None = None,
    amended_by: str | None = None,
) -> bool:
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """
            UPDATE copilot_draft_actions
            SET status=?, executed_at=?, amended_from=?, amended_by=?
            WHERE action_id=?
            """,
            (status, executed_at, amended_from, amended_by, action_id),
        )
        return bool(cur.rowcount > 0)


def copilot_draft_compare_and_set_status(
    action_id: str,
    expected_status: str,
    new_status: str,
) -> bool:
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """
            UPDATE copilot_draft_actions
            SET status=?
            WHERE action_id=? AND status=?
            """,
            (new_status, action_id, expected_status),
        )
        return bool(cur.rowcount == 1)


def copilot_execution_reserve(
    store_id: str,
    action_id: str,
    idempotency_key: str,
    request_hash: str,
) -> tuple[str, dict[str, Any] | None]:
    init_db()
    with _conn() as cx:
        try:
            cx.execute(
                """
                INSERT INTO copilot_execution_receipts(
                    store_id, action_id, idempotency_key, request_hash, status, created_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (store_id, action_id, idempotency_key, request_hash, "pending", _iso_now()),
            )
            return "reserved", None
        except _DB_INTEGRITY_ERRORS:
            if hasattr(cx, "rollback"):
                cx.rollback()
            row = cx.execute(
                """
                SELECT idempotency_key, request_hash, status, outcome
                FROM copilot_execution_receipts
                WHERE store_id=? AND action_id=?
                """,
                (store_id, action_id),
            ).fetchone()
            if not row or str(row[0]) != idempotency_key or str(row[1]) != request_hash:
                return "conflict", None
            if str(row[2]) == "completed" and row[3]:
                return "replay", json.loads(row[3])
            return "pending", None


def copilot_execution_rearm_internal(
    store_id: str,
    action_id: str,
    idempotency_key: str,
    request_hash: str,
) -> bool:
    """Re-arm a failed KV-only execution after its transaction rolled back."""
    init_db()
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN IMMEDIATE")
        try:
            row = cx.execute(
                "SELECT status FROM copilot_execution_receipts WHERE store_id=? AND action_id=?",
                (store_id, action_id),
            ).fetchone()
            if not row or str(row[0]) != "failed":
                cx.execute("ROLLBACK")
                return False
            action = cx.execute(
                "UPDATE copilot_draft_actions SET status='ready_for_approval', executed_at=NULL "
                "WHERE action_id=? AND store_id=? AND status='execution_failed'",
                (action_id, store_id),
            )
            if action.rowcount != 1:
                cx.execute("ROLLBACK")
                return False
            receipt = cx.execute(
                "DELETE FROM copilot_execution_receipts "
                "WHERE store_id=? AND action_id=? AND status='failed'",
                (store_id, action_id),
            )
            if receipt.rowcount != 1:
                cx.execute("ROLLBACK")
                return False
            cx.execute("COMMIT")
            return True
        except Exception:
            cx.execute("ROLLBACK")
            raise


def copilot_execution_complete(
    store_id: str,
    action_id: str,
    idempotency_key: str,
    outcome: dict[str, Any],
) -> bool:
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """
            UPDATE copilot_execution_receipts
            SET status='completed', outcome=?, completed_at=?
            WHERE store_id=? AND action_id=? AND idempotency_key=? AND status='pending'
            """,
            (
                json.dumps(outcome, ensure_ascii=False),
                _iso_now(),
                store_id,
                action_id,
                idempotency_key,
            ),
        )
        return bool(cur.rowcount == 1)


def copilot_execution_fail(
    store_id: str,
    action_id: str,
    idempotency_key: str,
    error_type: str,
) -> bool:
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            """
            UPDATE copilot_execution_receipts
            SET status='failed', outcome=?, completed_at=?
            WHERE store_id=? AND action_id=? AND idempotency_key=? AND status='pending'
            """,
            (
                json.dumps({"error_type": error_type}, ensure_ascii=False),
                _iso_now(),
                store_id,
                action_id,
                idempotency_key,
            ),
        )
        return bool(cur.rowcount == 1)


def copilot_mail_delivery_reserve(
    store_id: str,
    idempotency_key: str,
    request_hash: str,
) -> tuple[str, dict[str, Any] | None]:
    """Reserve one external mail request and replay a known terminal outcome."""
    init_db()
    with _conn() as cx:
        try:
            cx.execute(
                "INSERT INTO copilot_mail_delivery_receipts("
                "store_id, idempotency_key, request_hash, status, created_at) "
                "VALUES (?,?,?,?,?)",
                (store_id, idempotency_key, request_hash, "pending", _iso_now()),
            )
            return "reserved", None
        except _DB_INTEGRITY_ERRORS:
            if hasattr(cx, "rollback"):
                cx.rollback()
            row = cx.execute(
                "SELECT request_hash, status, outcome "
                "FROM copilot_mail_delivery_receipts WHERE store_id=? AND idempotency_key=?",
                (store_id, idempotency_key),
            ).fetchone()
            if not row or str(row[0]) != request_hash:
                return "conflict", None
            if str(row[1]) in {"sent", "transport_failed", "delivery_unknown"} and row[2]:
                return "replay", json.loads(row[2])
            return "pending", None


def copilot_mail_delivery_complete(
    store_id: str,
    idempotency_key: str,
    status: str,
    outcome: dict[str, Any],
) -> bool:
    if status not in {"sent", "transport_failed", "delivery_unknown"}:
        raise ValueError("invalid_mail_delivery_status")
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE copilot_mail_delivery_receipts SET status=?, outcome=?, completed_at=? "
            "WHERE store_id=? AND idempotency_key=? AND status='pending'",
            (
                status,
                json.dumps(outcome, ensure_ascii=False),
                _iso_now(),
                store_id,
                idempotency_key,
            ),
        )
        return bool(cur.rowcount == 1)


def copilot_draft_list(
    store_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    query = """
        SELECT action_id, intent, status, store_id, created_by, confidence,
               summary, explanation, payload_diff, requires_confirmation,
               data_snapshot_hash, expires_at, created_at, executed_at,
               amended_from, amended_by
        FROM copilot_draft_actions
    """
    params: list[Any] = []
    conds = []
    if store_id:
        conds.append("store_id=?")
        params.append(store_id)
    if status:
        conds.append("status=?")
        params.append(status)
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _conn() as cx:
        rows = cx.execute(query, params).fetchall()
        return [
            {
                "action_id": str(r[0]),
                "intent": str(r[1]),
                "status": str(r[2]),
                "store_id": str(r[3]),
                "created_by": str(r[4]),
                "confidence": float(r[5]),
                "summary": str(r[6]),
                "explanation": str(r[7]),
                "payload_diff": json.loads(r[8]),
                "requires_confirmation": bool(r[9]),
                "data_snapshot_hash": str(r[10]),
                "expires_at": str(r[11]),
                "created_at": str(r[12]),
                "executed_at": str(r[13]) if r[13] else None,
                "amended_from": str(r[14]) if r[14] else None,
                "amended_by": str(r[15]) if r[15] else None,
            }
            for r in rows
        ]


def copilot_audit_add(
    action_id: str,
    actor_user_id: str,
    store_id: str,
    intent: str,
    decision: str,
    payload_diff: dict[str, Any] | None = None,
    channel: str = "web",
    latency_ms: int = 0,
    *,
    agent_name: str | None = None,
    controller_user_id: str | None = None,
) -> None:
    try:
        from datetime import UTC, datetime
    except ImportError:
        from datetime import datetime, timezone

        UTC = timezone.utc

    init_db()
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO copilot_audit_log(
                action_id, actor_user_id, store_id, intent, decision,
                payload_diff, timestamp, channel, latency_ms,
                agent_name, controller_user_id
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                action_id,
                actor_user_id,
                store_id,
                intent,
                decision,
                json.dumps(payload_diff or {}, ensure_ascii=False),
                now_iso,
                channel,
                latency_ms,
                agent_name,
                controller_user_id,
            ),
        )


def copilot_audit_list(store_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    query = (
        "SELECT action_id, actor_user_id, store_id, intent, decision, payload_diff, "
        "timestamp, channel, latency_ms, agent_name, controller_user_id "
        "FROM copilot_audit_log"
    )
    params: list[Any] = []
    if store_id:
        query += " WHERE store_id=?"
        params.append(store_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _conn() as cx:
        rows = cx.execute(query, params).fetchall()
        return [
            {
                "action_id": str(r[0]),
                "actor_user_id": str(r[1]),
                "store_id": str(r[2]),
                "intent": str(r[3]),
                "decision": str(r[4]),
                "payload_diff": json.loads(r[5]),
                "timestamp": str(r[6]),
                "channel": str(r[7]),
                "latency_ms": int(r[8]),
                "agent_name": r[9],
                "controller_user_id": r[10],
                # copilot_audit_log không có cột actor_type; suy từ agent_name.
                "actor_type": "agent" if r[9] else "human",
            }
            for r in rows
        ]


# ── FB moderation store (kế hoạch chatbot §3.7) ───────────────────────────


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fb_try_claim_event(event_id: str) -> bool:
    """True nếu lần đầu thấy event_id (mid/comment_id); False nếu đã xử lý.

    Idempotency chống webhook retry của Meta (kế hoạch §6.2b).
    """
    init_db()
    with _conn() as cx:
        try:
            cx.execute(
                "INSERT INTO fb_processed_events(event_id, processed_at) VALUES (?,?)",
                (event_id, _iso_now()),
            )
            return True
        except Exception as exc:
            if _database_url():
                import psycopg

                if isinstance(exc, psycopg.IntegrityError):
                    cx.execute("ROLLBACK")
                    return False
            elif isinstance(exc, sqlite3.IntegrityError):
                return False
            raise


def fb_try_claim_scoped_event(
    *, store_id: str, page_id: str, event_type: str, external_event_id: str
) -> bool:
    """Atomically claim one Facebook event in its tenant/Page/type scope."""
    if not all(value.strip() for value in (store_id, page_id, event_type, external_event_id)):
        return False
    idempotency_key = hashlib.sha256(
        f"{store_id}:{page_id}:{event_type}:{external_event_id}".encode()
    ).hexdigest()
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "INSERT INTO fb_event_receipts(idempotency_key, store_id, page_id, event_type, external_event_id, processed_at) VALUES (?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING",
            (idempotency_key, store_id, page_id, event_type, external_event_id, _iso_now()),
        )
        return bool(cur.rowcount == 1)


_AI_LEARNING_TABLES = {
    "generation": "ai_generation_records",
    "feedback": "ai_feedback_events",
    "evaluation": "ai_evaluations",
    "rule_proposal": "ai_rule_proposals",
}


def _ai_generation_exists(cx: sqlite3.Connection, *, store_id: str, generation_id: str) -> bool:
    return (
        cx.execute(
            "SELECT 1 FROM ai_generation_records WHERE store_id=? AND id=?",
            (store_id, generation_id),
        ).fetchone()
        is not None
    )


def ai_learning_save(kind: str, record: dict[str, Any]) -> bool:
    """Persist a pre-redacted AI-learning record; return False for idempotent replay."""
    if kind not in _AI_LEARNING_TABLES:
        raise ValueError("ai_learning_record_invalid")
    try:
        store_id, record_id, channel, created_at = (
            str(record[key]).strip() for key in ("store_id", "id", "channel", "created_at")
        )
    except (KeyError, TypeError):
        raise ValueError("ai_learning_record_invalid") from None
    if not all((store_id, record_id, channel, created_at)):
        raise ValueError("ai_learning_record_invalid")
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    init_db()
    with _conn() as cx:
        if kind == "generation":
            cur = cx.execute(
                "INSERT INTO ai_generation_records(id, store_id, channel, idempotency_key, payload, created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(store_id, idempotency_key) DO NOTHING",
                (record_id, store_id, channel, str(record["idempotency_key"]), payload, created_at),
            )
        elif kind == "feedback":
            if not _ai_generation_exists(
                cx, store_id=store_id, generation_id=str(record["generation_id"])
            ):
                raise ValueError("ai_learning_cross_tenant_generation")
            cur = cx.execute(
                "INSERT INTO ai_feedback_events(id, store_id, generation_id, channel, idempotency_key, payload, created_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(store_id, idempotency_key) DO NOTHING",
                (
                    record_id,
                    store_id,
                    str(record["generation_id"]),
                    channel,
                    str(record["idempotency_key"]),
                    payload,
                    created_at,
                ),
            )
        elif kind == "evaluation":
            if not _ai_generation_exists(
                cx, store_id=store_id, generation_id=str(record["generation_id"])
            ):
                raise ValueError("ai_learning_cross_tenant_generation")
            cur = cx.execute(
                "INSERT INTO ai_evaluations(id, store_id, generation_id, channel, idempotency_key, payload, created_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(store_id, idempotency_key) DO NOTHING",
                (
                    record_id,
                    store_id,
                    str(record["generation_id"]),
                    channel,
                    str(record["idempotency_key"]),
                    payload,
                    created_at,
                ),
            )
        else:
            evidence_ids = [str(value) for value in record.get("evidence_ids", [])]
            if not evidence_ids:
                raise ValueError("ai_learning_evidence_missing")
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = cx.execute(
                f"SELECT id FROM ai_feedback_events WHERE store_id=? AND id IN ({placeholders})",
                [store_id, *evidence_ids],
            ).fetchall()
            if {str(row[0]) for row in rows} != set(evidence_ids):
                raise ValueError("ai_learning_cross_tenant_evidence")
            cur = cx.execute(
                "INSERT INTO ai_rule_proposals(id, store_id, channel, status, version, idempotency_key, payload, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(store_id, idempotency_key) DO NOTHING",
                (
                    record_id,
                    store_id,
                    channel,
                    str(record.get("status", "pending")),
                    int(record["version"]),
                    str(record["idempotency_key"]),
                    payload,
                    created_at,
                    str(record["updated_at"]),
                ),
            )
        return bool(cur.rowcount == 1)


def ai_learning_list(kind: str, *, store_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read AI-learning records only from the requested tenant."""
    if kind not in _AI_LEARNING_TABLES or not store_id.strip():
        raise ValueError("ai_learning_query_invalid")
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            f"SELECT payload FROM {_AI_LEARNING_TABLES[kind]} WHERE store_id=? ORDER BY created_at, id LIMIT ?",
            (store_id, max(1, min(limit, 200))),
        ).fetchall()
    return [json.loads(str(row[0])) for row in rows]


_AI_RULE_TRANSITIONS = {
    "pending": {"approved", "rejected", "conflict_pending"},
    "conflict_pending": {"approved", "rejected"},
    "approved": {"active", "rejected"},
    "active": {"paused", "rolled_back"},
    "paused": {"active", "rolled_back"},
}


def ai_rule_proposal_get(*, store_id: str, proposal_id: str) -> dict[str, Any] | None:
    """Return one proposal only when it belongs to the requested tenant."""
    if not store_id.strip() or not proposal_id.strip():
        raise ValueError("ai_learning_query_invalid")
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT payload FROM ai_rule_proposals WHERE store_id=? AND id=?",
            (store_id, proposal_id),
        ).fetchone()
    return json.loads(str(row[0])) if row else None


def ai_rule_proposal_list(
    *, store_id: str, channel: str | None = None, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """List proposal records scoped to one tenant, optionally by channel/status."""
    if not store_id.strip():
        raise ValueError("ai_learning_query_invalid")
    init_db()
    query = "SELECT payload FROM ai_rule_proposals WHERE store_id=?"
    params: list[Any] = [store_id]
    if channel:
        query += " AND channel=?"
        params.append(channel)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))
    with _conn() as cx:
        rows = cx.execute(query, params).fetchall()
    return [json.loads(str(row[0])) for row in rows]


def ai_rule_proposal_transition(
    *,
    store_id: str,
    proposal_id: str,
    target_status: str,
    actor_id: str,
    updated_at: str,
    rejection_reason: str | None = None,
) -> dict[str, Any] | None:
    """Atomically apply a legal, tenant-scoped human rule lifecycle transition."""
    if not all(
        value.strip() for value in (store_id, proposal_id, target_status, actor_id, updated_at)
    ):
        raise ValueError("ai_learning_transition_invalid")
    init_db()
    with _conn() as cx:
        row = cx.execute(
            "SELECT status, payload FROM ai_rule_proposals WHERE store_id=? AND id=?",
            (store_id, proposal_id),
        ).fetchone()
        if not row:
            return None
        current_status = str(row[0])
        if target_status not in _AI_RULE_TRANSITIONS.get(current_status, set()):
            raise ValueError("ai_learning_transition_invalid")
        proposal = json.loads(str(row[1]))
        proposal["status"] = target_status
        proposal["updated_at"] = updated_at
        if target_status in {"approved", "active"}:
            proposal["approved_by"] = actor_id
            proposal["approved_at"] = updated_at
            proposal["rejection_reason"] = None
        elif target_status == "rejected":
            proposal["rejection_reason"] = (rejection_reason or "rejected_by_owner").strip()
        payload = json.dumps(proposal, ensure_ascii=False, separators=(",", ":"))
        cur = cx.execute(
            "UPDATE ai_rule_proposals SET status=?, payload=?, updated_at=? WHERE store_id=? AND id=? AND status=?",
            (target_status, payload, updated_at, store_id, proposal_id, current_status),
        )
        return proposal if cur.rowcount == 1 else None


def ai_rule_active_list(*, store_id: str, channel: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return active rules ordered deterministically for prompt construction."""
    rules = ai_rule_proposal_list(store_id=store_id, channel=channel, status="active", limit=limit)
    return sorted(
        rules,
        key=lambda rule: (
            -int((rule.get("rule") or {}).get("priority", 0)),
            str(rule.get("created_at", "")),
            str(rule.get("id", "")),
        ),
    )


def ai_learning_snapshot(*, store_id: str) -> dict[str, Any]:
    """Return a consistent per-store export and SHA-256 manifest for backup tooling."""
    if not store_id.strip():
        raise ValueError("ai_learning_query_invalid")
    init_db()
    with _conn() as cx:
        cx.isolation_level = None
        cx.execute("BEGIN")
        try:
            records = {
                kind: [
                    json.loads(str(row[0]))
                    for row in cx.execute(
                        f"SELECT payload FROM {table} WHERE store_id=? ORDER BY created_at, id",
                        (store_id,),
                    ).fetchall()
                ]
                for kind, table in _AI_LEARNING_TABLES.items()
            }
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
    snapshot = {"schema_version": 1, "store_id": store_id, "records": records}
    payload = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {"snapshot": snapshot, "checksum_sha256": hashlib.sha256(payload).hexdigest()}


def ai_learning_backup(*, store_id: str, directory: Path | None = None) -> dict[str, Any]:
    """Write a tenant-scoped consistent snapshot plus checksum manifest atomically."""
    from ca_api.ai_learning.security import require_encrypted_data_path

    backup = ai_learning_snapshot(store_id=store_id)
    output_dir = directory or Path(
        os.environ.get("NHIPQUAN_AI_LEARNING_BACKUP_DIR", ROOT / "data" / "backups")
    )
    require_encrypted_data_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_store = re.sub(r"[^A-Za-z0-9_.-]", "_", store_id)
    snapshot_path = output_dir / f"ai-learning-{safe_store}-{stamp}.json"
    manifest_path = snapshot_path.with_suffix(".sha256.json")
    snapshot_payload = json.dumps(backup["snapshot"], ensure_ascii=False, sort_keys=True, indent=2)
    manifest = {
        "backup_format_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": backup["snapshot"]["schema_version"],
        "store_id": store_id,
        "store_coverage": [store_id],
        "record_counts": {
            kind: len(records) for kind, records in backup["snapshot"]["records"].items()
        },
        "checksum_sha256": backup["checksum_sha256"],
        "snapshot_file": snapshot_path.name,
    }
    for path, content in (
        (snapshot_path, snapshot_payload),
        (manifest_path, json.dumps(manifest, indent=2, sort_keys=True)),
    ):
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return {**backup, "snapshot_path": str(snapshot_path), "manifest_path": str(manifest_path)}


def ai_learning_verify_backup(*, snapshot_path: Path, manifest_path: Path) -> bool:
    """Verify backup format, manifest coverage, and SHA-256 before a restore."""
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return bool(
        manifest.get("backup_format_version") == 1
        and manifest.get("schema_version") == snapshot.get("schema_version") == 1
        and manifest.get("store_coverage") == [snapshot.get("store_id")]
        and manifest.get("checksum_sha256") == digest
    )


def fb_review_insert(item: dict[str, Any]) -> int:
    """Ghi 1 hàng vào fb_review_queue, trả về id."""
    init_db()
    with _conn() as cx:
        returning = " RETURNING id" if _database_url() else ""
        cur = cx.execute(
            """
            INSERT INTO fb_review_queue(
                store_id, source, external_thread_id, external_psid, external_user_name,
                post_id, post_is_sensitive, message_text, detected_intent,
                confidence, policy_action, assigned_role, proposed_response,
                flagged_reasons, status, trace_id, created_at, event_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """
            + returning,
            (
                item.get("store_id", "quan_01"),
                item["source"],
                item["external_thread_id"],
                item["external_psid"],
                item.get("external_user_name"),
                item.get("post_id"),
                1 if item.get("post_is_sensitive") else 0,
                item["message_text"],
                item["detected_intent"],
                float(item["confidence"]),
                item["policy_action"],
                item.get("assigned_role"),
                item.get("proposed_response"),
                json.dumps(item.get("flagged_reasons") or [], ensure_ascii=False),
                item.get("status", "pending"),
                item.get("trace_id", ""),
                item["created_at"],
                item.get("event_at"),
                item.get("expires_at"),
            ),
        )
        if _database_url():
            row = cur.fetchone()
            return int(row[0])
        return int(cur.lastrowid or 0)


def fb_review_list(
    *,
    status: str | None = None,
    assigned_role: str | None = None,
    store_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    q = "SELECT * FROM fb_review_queue WHERE 1=1"
    params: list[Any] = []
    if status:
        q += " AND status=?"
        params.append(status)
    if assigned_role:
        q += " AND assigned_role=?"
        params.append(assigned_role)
    if store_id:
        q += " AND store_id=?"
        params.append(store_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def fb_review_get(item_id: int) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        row = cx.execute("SELECT * FROM fb_review_queue WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def fb_review_link_generation(item_id: int, *, generation_id: str) -> None:
    """Attach the exact AI generation that produced this review draft."""
    init_db()
    with _conn() as cx:
        cx.execute(
            "UPDATE fb_review_queue SET ai_generation_id=? WHERE id=?",
            (generation_id, item_id),
        )


def fb_review_update_proposed(item_id: int, *, proposed_response: str) -> bool:
    """Nâng cấp bản nháp trong hàng duyệt (vd LLM thay template) — chỉ khi pending."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE fb_review_queue SET proposed_response=? WHERE id=? AND status='pending'",
            (proposed_response, item_id),
        )
        return bool(cur.rowcount == 1)


def fb_review_transition_pending(item_id: int, *, status: str) -> bool:
    """Atomically claim a pending review item for one terminal workflow."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE fb_review_queue SET status=? WHERE id=? AND status='pending'",
            (status, item_id),
        )
        return bool(cur.rowcount == 1)


def fb_review_release_claim(item_id: int) -> bool:
    """Return a delivery claim to the review queue after a provider failure."""
    init_db()
    with _conn() as cx:
        cur = cx.execute(
            "UPDATE fb_review_queue SET status='pending', "
            "assigned_role=COALESCE(assigned_role, 'quan_ly') "
            "WHERE id=? AND status='approved'",
            (item_id,),
        )
        return bool(cur.rowcount == 1)


def fb_review_finalize_claim(
    item_id: int,
    *,
    status: str,
    decided_by: str,
    final_response: str,
) -> dict[str, Any] | None:
    """Finalize an item previously claimed by pending -> approved."""
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        cx.execute(
            "UPDATE fb_review_queue SET status=?, decided_by=?, decided_at=?, final_response=? "
            "WHERE id=? AND status='approved'",
            (status, decided_by, _iso_now(), final_response, item_id),
        )
        row = cx.execute("SELECT * FROM fb_review_queue WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def fb_review_decide(
    item_id: int,
    *,
    status: str,
    decided_by: str,
    final_response: str | None = None,
) -> dict[str, Any] | None:
    """Cập nhật quyết định duyệt/từ chối. Idempotent: đã quyết thì không đổi."""
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        row = cx.execute("SELECT status FROM fb_review_queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        if str(row["status"]) != "pending":
            return dict(row)
        cur = cx.execute(
            "UPDATE fb_review_queue SET status=?, decided_by=?, decided_at=?, final_response=? "
            "WHERE id=? AND status='pending'",
            (status, decided_by, _iso_now(), final_response, item_id),
        )
        if cur.rowcount != 1:
            return None
        row2 = cx.execute("SELECT * FROM fb_review_queue WHERE id=?", (item_id,)).fetchone()
    return dict(row2) if row2 else None


def fb_review_mark_sent(item_id: int, *, final_response: str, audit_id: int) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "UPDATE fb_review_queue SET status='sent', final_response=?, audit_sent=? WHERE id=?",
            (final_response, audit_id, item_id),
        )


def fb_escalation_add(
    review_queue_id: int, *, escalated_to: str, reason: str, notified_channel: str
) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "INSERT INTO fb_escalation_log(review_queue_id, escalated_to, reason, notified_channel, notified_at) "
            "VALUES (?,?,?,?,?)",
            (review_queue_id, escalated_to, reason, notified_channel, _iso_now()),
        )
        cx.execute(
            "UPDATE fb_review_queue SET assigned_role = ? WHERE id = ?",
            (escalated_to, review_queue_id),
        )


def fb_escalation_unacked() -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            "SELECT e.*, q.message_text, q.detected_intent FROM fb_escalation_log e "
            "JOIN fb_review_queue q ON q.id = e.review_queue_id "
            "WHERE e.acked_at IS NULL ORDER BY e.notified_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def fb_blacklist_check(psid: str) -> bool:
    """True nếu PSID đang bị chặn (blocked_until > now)."""
    init_db()
    now = _iso_now()
    with _conn() as cx:
        # So sánh bên SQL: SQLite so TEXT cùng format, Postgres tự ép chuỗi
        # ISO sang TIMESTAMPTZ — so chuỗi Python sẽ sai ký tự ở vị trí 10.
        row = cx.execute(
            "SELECT 1 FROM fb_psid_blacklist WHERE psid=? AND blocked_until > ?",
            (psid, now),
        ).fetchone()
    return row is not None


def fb_blacklist_bump(psid: str, *, strikes: int, blocked_until: str, reason: str) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "INSERT INTO fb_psid_blacklist(psid, strikes, blocked_until, reason) VALUES (?,?,?,?) "
            "ON CONFLICT(psid) DO UPDATE SET strikes=excluded.strikes, "
            "blocked_until=excluded.blocked_until, reason=excluded.reason",
            (psid, strikes, blocked_until, reason),
        )


def fb_stats(store_id: str | None = None) -> dict[str, Any]:
    """Đếm theo status + auto rate (kế hoạch §5.4)."""
    init_db()
    with _conn() as cx:
        by_status = {
            str(r[0]): int(r[1])
            for r in cx.execute(
                "SELECT status, COUNT(*) FROM fb_review_queue"
                + (" WHERE store_id=?" if store_id else "")
                + " GROUP BY status",
                (store_id,) if store_id else (),
            ).fetchall()
        }
        total = sum(by_status.values())
    auto = by_status.get("auto_sent", 0)
    return {
        "by_status": by_status,
        "total": total,
        "auto_sent": auto,
        "auto_rate": round(auto / total, 4) if total else 0.0,
        "escalation_unacked": len(fb_escalation_unacked()),
    }


# ── Chat Nội Bộ Nhân Viên (Messenger-Style) ──────────────────────────────────


def _seed_chat_neu_trong(cx: sqlite3.Connection) -> None:
    """Tạo phòng chat chung mặc định '☕ NHỊP QUÁN · Hội Quán Chung' (is_locked=1) và mời toàn bộ nhân viên active."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conv_id = f"conv_general_{DEFAULT_STORE_ID}"
    cx.execute(
        """
        INSERT INTO chat_conversations(id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at)
        VALUES (?,?,?,?,?,TRUE,?,?)
        ON CONFLICT(id) DO NOTHING
        """,
        (conv_id, DEFAULT_STORE_ID, "general", "☕ NHỊP QUÁN · Hội Quán Chung", "", now, now),
    )
    users = cx.execute(
        "SELECT nv_id, role, status FROM users WHERE store_id=?", (DEFAULT_STORE_ID,)
    ).fetchall()
    for nv, role, st in users:
        if st == "inactive":
            continue
        part_role = "admin" if role in ("quan_ly", "chu_quan") else "member"
        cx.execute(
            """
            INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(conversation_id, nv_id) DO NOTHING
            """,
            (conv_id, nv, part_role, "active", now),
        )
    has_msg = cx.execute(
        "SELECT 1 FROM chat_messages WHERE conversation_id=? LIMIT 1", (conv_id,)
    ).fetchone()
    if not has_msg:
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        cx.execute(
            """
            INSERT INTO chat_messages(id, conversation_id, sender_id, type, content, is_unsent, created_at)
            VALUES (?,?,'system','system',?,FALSE,?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                msg_id,
                conv_id,
                "Chào mừng cả nhà đến với kênh Chat Hội Quán NHỊP QUÁN! ☕✨ Trao đổi ca làm việc, hỗ trợ quầy, pha chế và thông báo tại đây nhé.",
                now,
            ),
        )


def user_is_active(nv_id: str) -> bool:
    """Kiểm tra tài khoản nhân viên có đang hoạt động (active) hay không."""
    init_db()
    with _conn() as cx:
        row = cx.execute("SELECT status FROM users WHERE nv_id=?", (nv_id,)).fetchone()
        if not row:
            return False
        return str(row[0]).lower() == "active"


def chat_participant_deactivate(nv_id: str) -> None:
    """Hook Offboarding: Đưa thành viên vào trạng thái 'archived' trên mọi hội thoại."""
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            UPDATE chat_participants
            SET status = 'archived', archived_at = ?
            WHERE nv_id = ? AND status = 'active'
            """,
            (now, nv_id),
        )


def user_deactivate(nv_id: str, store_id: str = "quan_01") -> bool:
    """Vô hiệu hóa tài khoản nhân viên (Offboarding):
    - Đổi status = 'inactive' trong bảng users
    - Xóa toàn bộ token trong sessions (force revoke/disconnect)
    - Set status = 'archived' trong chat_participants
    - Ghi log audit
    """
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        user = cx.execute(
            "SELECT username, display_name FROM users WHERE nv_id=?", (nv_id,)
        ).fetchone()
        if not user:
            return False
        u_name, d_name = str(user[0]), str(user[1])
        cx.execute("UPDATE users SET status = 'inactive' WHERE nv_id = ?", (nv_id,))
        cx.execute("DELETE FROM sessions WHERE nv_id = ?", (nv_id,))
        cx.execute(
            """
            UPDATE chat_participants
            SET status = 'archived', archived_at = ?
            WHERE nv_id = ?
            """,
            (now, nv_id),
        )
        cx.execute(
            "INSERT INTO audit(at, ai, hanh, payload) VALUES (?,?,?,?)",
            (
                now,
                "system",
                "user_deactivate",
                json.dumps({"nv_id": nv_id, "username": u_name, "name": d_name}),
            ),
        )
    return True


def chat_conversation_create(
    store_id: str,
    conv_type: str,
    display_name: str,
    created_by: str,
    participant_nv_ids: list[str],
    is_locked: bool = False,
    avatar_url: str = "",
) -> dict[str, Any]:
    init_db()
    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO chat_conversations(id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (conv_id, store_id, conv_type, display_name, avatar_url, bool(is_locked), now, now),
        )
        all_participants = set(participant_nv_ids)
        if created_by:
            all_participants.add(created_by)
        for nv in all_participants:
            role = "admin" if nv == created_by else "member"
            cx.execute(
                """
                INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(conversation_id, nv_id) DO NOTHING
                """,
                (conv_id, nv, role, "active", now),
            )
    return chat_conversation_get(conv_id, created_by) or {"id": conv_id}


def chat_get_or_create_direct(store_id: str, nv1_id: str, nv2_id: str) -> dict[str, Any]:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT c.id FROM chat_conversations c
            JOIN chat_participants p1 ON c.id = p1.conversation_id AND p1.nv_id = ?
            JOIN chat_participants p2 ON c.id = p2.conversation_id AND p2.nv_id = ?
            WHERE c.type = 'direct' AND c.store_id = ?
            LIMIT 1
            """,
            (nv1_id, nv2_id, store_id),
        ).fetchone()
        if row:
            conv_id = str(row[0])
            return chat_conversation_get(conv_id, nv1_id) or {"id": conv_id}

    return chat_conversation_create(
        store_id=store_id,
        conv_type="direct",
        display_name="",
        created_by=nv1_id,
        participant_nv_ids=[nv1_id, nv2_id],
    )


def chat_conversation_get(conv_id: str, current_nv_id: str | None = None) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at
            FROM chat_conversations WHERE id = ?
            """,
            (conv_id,),
        ).fetchone()
        if not row:
            return None
        conv: dict[str, Any] = {
            "id": str(row[0]),
            "store_id": str(row[1]),
            "type": str(row[2]),
            "display_name": str(row[3]),
            "avatar_url": str(row[4] or ""),
            "is_locked": bool(row[5]),
            "created_at": str(row[6]),
            "updated_at": str(row[7]),
        }
        # Lấy thành viên
        p_rows = cx.execute(
            """
            SELECT p.nv_id, p.role, p.status, p.muted, p.last_read_at, p.joined_at, p.archived_at,
                   COALESCE(u.display_name, p.nv_id) as user_name,
                   COALESCE(u.role, 'nhan_vien') as user_role,
                   COALESCE(u.status, 'active') as user_status
            FROM chat_participants p
            LEFT JOIN users u ON p.nv_id = u.nv_id
            WHERE p.conversation_id = ?
            """,
            (conv_id,),
        ).fetchall()
        conv["participants"] = [
            {
                "nv_id": str(r[0]),
                "role": str(r[1]),
                "status": str(r[2]),
                "muted": bool(r[3]),
                "last_read_at": str(r[4] or ""),
                "joined_at": str(r[5]),
                "archived_at": str(r[6] or ""),
                "display_name": str(r[7]),
                "user_role": str(r[8]),
                "user_status": str(r[9]),
            }
            for r in p_rows
        ]

        if conv["type"] == "direct" and current_nv_id:
            other = next((p for p in conv["participants"] if p["nv_id"] != current_nv_id), None)
            if other:
                conv["display_name"] = other["display_name"]
                conv["other_user"] = other

        # Tin nhắn cuối
        last_msg_row = cx.execute(
            """
            SELECT m.id, m.sender_id, m.type, m.content, m.created_at, m.is_unsent,
                   COALESCE(u.display_name, m.sender_id) as sender_name
            FROM chat_messages m
            LEFT JOIN users u ON m.sender_id = u.nv_id
            WHERE m.conversation_id = ?
            ORDER BY m.created_at DESC LIMIT 1
            """,
            (conv_id,),
        ).fetchone()
        if last_msg_row:
            conv["last_message"] = {
                "id": str(last_msg_row[0]),
                "sender_id": str(last_msg_row[1]),
                "type": str(last_msg_row[2]),
                "content": str(last_msg_row[3]),
                "created_at": str(last_msg_row[4]),
                "is_unsent": bool(last_msg_row[5]),
                "sender_name": str(last_msg_row[6]),
            }
        else:
            conv["last_message"] = None

        return conv


def chat_conversation_list_for_user(nv_id: str, store_id: str = "quan_01") -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        # Nếu user bị inactive, không trả về hộp thư
        u_row = cx.execute("SELECT status FROM users WHERE nv_id = ?", (nv_id,)).fetchone()
        if not u_row or str(u_row[0]) == "inactive":
            return []

        # Đảm bảo user luôn có mặt trong nhóm chung của quán
        conv_general_id = f"conv_general_{store_id}"
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        cx.execute(
            """
            INSERT INTO chat_conversations(id, store_id, type, display_name, avatar_url, is_locked, created_at, updated_at)
            VALUES (?,?,?,?,?,TRUE,?,?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                conv_general_id,
                store_id,
                "general",
                "☕ NHỊP QUÁN · Hội Quán Chung",
                "",
                now_iso,
                now_iso,
            ),
        )
        cx.execute(
            """
            INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
            VALUES (?,?,'member','active',?)
            ON CONFLICT(conversation_id, nv_id) DO NOTHING
            """,
            (conv_general_id, nv_id, now_iso),
        )
        cx.execute(
            """
            INSERT INTO users(username, password_sha, role, nv_id, display_name, store_id, status)
            VALUES ('ai_scheduler', 'bot_internal', 'ai_assistant', 'ai_scheduler', 'Agent Xếp Lịch 📅', ?, 'active')
            ON CONFLICT(username) DO NOTHING
            """,
            (store_id,),
        )
        cx.execute(
            """
            INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
            VALUES (?,'ai_scheduler','member','active',?)
            ON CONFLICT(conversation_id, nv_id) DO NOTHING
            """,
            (conv_general_id, now_iso),
        )

        # Lấy tất cả hội thoại mà nv_id đang tham gia và status = 'active'
        c_rows = cx.execute(
            """
            SELECT c.id, c.store_id, c.type, c.display_name, c.avatar_url, c.is_locked,
                   c.created_at, c.updated_at, p.muted, p.last_read_at, p.joined_at, p.archived_at,
                   COALESCE(u.display_name, p.nv_id) as participant_display_name,
                   COALESCE(u.role, 'nhan_vien') as user_role,
                   COALESCE(u.status, 'active') as user_status
            FROM chat_conversations c
            JOIN chat_participants p ON c.id = p.conversation_id AND p.nv_id = ?
            LEFT JOIN users u ON p.nv_id = u.nv_id
            WHERE c.store_id = ? AND p.status = 'active'
            ORDER BY c.updated_at DESC
            """,
            (nv_id, store_id),
        ).fetchall()

        result = []
        for r in c_rows:
            conv_id = str(r[0])
            conv: dict[str, Any] = {
                "id": conv_id,
                "store_id": str(r[1]),
                "type": str(r[2]),
                "display_name": str(r[3]),
                "avatar_url": str(r[4] or ""),
                "is_locked": bool(r[5]),
                "created_at": str(r[6]),
                "updated_at": str(r[7]),
                "muted": bool(r[8]),
                "last_read_at": str(r[9] or ""),
                "joined_at": str(r[10]),
                "archived_at": str(r[11] or ""),
                "participant_display_name": str(r[12]),
                "user_role": str(r[13]),
                "user_status": str(r[14]),
            }

            # Thành viên
            p_rows = cx.execute(
                """
                SELECT p.nv_id, p.role, p.status, p.muted,
                       COALESCE(u.display_name, p.nv_id) as display_name,
                       COALESCE(u.role, 'nhan_vien') as user_role,
                       COALESCE(u.status, 'active') as user_status
                FROM chat_participants p
                LEFT JOIN users u ON p.nv_id = u.nv_id
                WHERE p.conversation_id = ? AND p.status = 'active'
                """,
                (conv_id,),
            ).fetchall()
            conv["participants"] = [
                {
                    "nv_id": str(pr[0]),
                    "role": str(pr[1]),
                    "status": str(pr[2]),
                    "muted": bool(pr[3]),
                    "display_name": str(pr[4]),
                    "user_role": str(pr[5]),
                    "user_status": str(pr[6]),
                }
                for pr in p_rows
            ]

            if conv["type"] == "direct":
                other = next((p for p in conv["participants"] if p["nv_id"] != nv_id), None)
                if other:
                    conv["display_name"] = other["display_name"]
                    conv["other_user"] = other

            # Đếm số tin chưa đọc dựa trên chat_read_receipts
            receipt = cx.execute(
                "SELECT last_read_message_id, read_at FROM chat_read_receipts WHERE conversation_id = ? AND nv_id = ?",
                (conv_id, nv_id),
            ).fetchone()
            if receipt and receipt[1]:
                read_at = str(receipt[1])
                unread_n = cx.execute(
                    """
                    SELECT COUNT(*) FROM chat_messages
                    WHERE conversation_id = ? AND sender_id != ? AND created_at > ? AND is_unsent = FALSE
                    """,
                    (conv_id, nv_id, read_at),
                ).fetchone()[0]
            else:
                unread_n = cx.execute(
                    """
                    SELECT COUNT(*) FROM chat_messages
                    WHERE conversation_id = ? AND sender_id != ? AND is_unsent = FALSE
                    """,
                    (conv_id, nv_id),
                ).fetchone()[0]
            conv["unread_count"] = int(unread_n)

            # Tin nhắn cuối
            last_msg_row = cx.execute(
                """
                SELECT m.id, m.sender_id, m.type, m.content, m.created_at, m.is_unsent,
                       COALESCE(u.display_name, m.sender_id) as sender_name
                FROM chat_messages m
                LEFT JOIN users u ON m.sender_id = u.nv_id
                WHERE m.conversation_id = ?
                ORDER BY m.created_at DESC LIMIT 1
                """,
                (conv_id,),
            ).fetchone()
            if last_msg_row:
                conv["last_message"] = {
                    "id": str(last_msg_row[0]),
                    "sender_id": str(last_msg_row[1]),
                    "type": str(last_msg_row[2]),
                    "content": str(last_msg_row[3]),
                    "created_at": str(last_msg_row[4]),
                    "is_unsent": bool(last_msg_row[5]),
                    "sender_name": str(last_msg_row[6]),
                }
            else:
                conv["last_message"] = None

            result.append(conv)
        return result


def chat_conversation_mute(conv_id: str, nv_id: str, muted: bool = True) -> None:
    init_db()
    with _conn() as cx:
        cx.execute(
            "UPDATE chat_participants SET muted = ? WHERE conversation_id = ? AND nv_id = ?",
            (bool(muted), conv_id, nv_id),
        )


def chat_participants_list(conv_id: str) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """
            SELECT p.nv_id, p.role, p.status, p.muted, p.last_read_at, p.joined_at, p.archived_at,
                   COALESCE(u.display_name, p.nv_id) as display_name,
                   COALESCE(u.role, 'nhan_vien') as user_role,
                   COALESCE(u.status, 'active') as user_status
            FROM chat_participants p
            LEFT JOIN users u ON p.nv_id = u.nv_id
            WHERE p.conversation_id = ?
            """,
            (conv_id,),
        ).fetchall()
        return [
            {
                "nv_id": str(r[0]),
                "role": str(r[1]),
                "status": str(r[2]),
                "muted": bool(r[3]),
                "last_read_at": str(r[4] or ""),
                "joined_at": str(r[5]),
                "archived_at": str(r[6] or ""),
                "display_name": str(r[7]),
                "user_role": str(r[8]),
                "user_status": str(r[9]),
            }
            for r in rows
        ]


def chat_participant_add(conv_id: str, nv_id: str, role: str = "member") -> None:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO chat_participants(conversation_id, nv_id, role, status, joined_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(conversation_id, nv_id) DO UPDATE SET status = 'active'
            """,
            (conv_id, nv_id, role, "active", now),
        )


def chat_participant_remove(conv_id: str, nv_id: str) -> bool:
    """Xóa thành viên khỏi nhóm tự do. Nhóm bị khóa (is_locked=1) không được xóa."""
    init_db()
    with _conn() as cx:
        locked = cx.execute(
            "SELECT is_locked FROM chat_conversations WHERE id=?", (conv_id,)
        ).fetchone()
        if locked and bool(locked[0]):
            return False
        cx.execute(
            "DELETE FROM chat_participants WHERE conversation_id = ? AND nv_id = ?",
            (conv_id, nv_id),
        )
        return True


def chat_message_create(
    conv_id: str,
    sender_id: str,
    content: str = "",
    msg_type: str = "text",
    metadata: dict[str, Any] | None = None,
    reply_to_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    # Kiểm tra quyền: nếu không phải system/copilot/ai_scheduler thì tài khoản phải active và participant status phải active
    if sender_id not in ("system", "copilot", "ai_scheduler"):
        if not user_is_active(sender_id):
            raise ValueError("tai_khoan_da_vo_hieu_hoa")

    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)

    with _conn() as cx:
        # Kiểm tra người gửi có trong phòng và status = 'active' không
        if sender_id not in ("system", "copilot", "ai_scheduler"):
            part = cx.execute(
                "SELECT status FROM chat_participants WHERE conversation_id = ? AND nv_id = ?",
                (conv_id, sender_id),
            ).fetchone()
            if not part or str(part[0]) != "active":
                raise ValueError("khong_phai_thanh_vien_active")

        cx.execute(
            """
            INSERT INTO chat_messages(id, conversation_id, sender_id, type, content, reply_to_id, is_unsent, metadata, created_at)
            VALUES (?,?,?,?,?,?,FALSE,?,?)
            """,
            (msg_id, conv_id, sender_id, msg_type, content, reply_to_id, meta_json, now),
        )
        cx.execute(
            "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )
        # Đánh dấu đã đọc cho người gửi
        if sender_id != "system":
            cx.execute(
                """
                INSERT INTO chat_read_receipts(conversation_id, nv_id, last_read_message_id, read_at)
                VALUES (?,?,?,?)
                ON CONFLICT(conversation_id, nv_id) DO UPDATE SET last_read_message_id = excluded.last_read_message_id, read_at = excluded.read_at
                """,
                (conv_id, sender_id, msg_id, now),
            )
            cx.execute(
                "UPDATE chat_participants SET last_read_at = ? WHERE conversation_id = ? AND nv_id = ?",
                (now, conv_id, sender_id),
            )
    return chat_message_get(msg_id) or {
        "id": msg_id,
        "conversation_id": conv_id,
        "content": content,
    }


def chat_message_get(message_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        row = cx.execute(
            """
            SELECT m.id, m.conversation_id, m.sender_id, m.type, m.content,
                   m.reply_to_id, m.is_unsent, m.edited_at, m.metadata, m.created_at,
                   COALESCE(u.display_name, CASE WHEN m.sender_id = 'copilot' THEN 'AG-Copilot 🤖' WHEN m.sender_id = 'ai_scheduler' THEN 'Agent Xếp Lịch 📅' ELSE m.sender_id END) as sender_name,
                   COALESCE(u.role, CASE WHEN m.sender_id IN ('copilot', 'ai_scheduler') THEN 'ai_assistant' ELSE 'nhan_vien' END) as sender_role
            FROM chat_messages m
            LEFT JOIN users u ON m.sender_id = u.nv_id
            WHERE m.id = ?
            """,
            (message_id,),
        ).fetchone()
        if not row:
            return None

        # Reactions
        react_rows = cx.execute(
            """
            SELECT r.emoji, r.nv_id, COALESCE(u.display_name, r.nv_id) as display_name
            FROM chat_reactions r
            LEFT JOIN users u ON r.nv_id = u.nv_id
            WHERE r.message_id = ?
            """,
            (message_id,),
        ).fetchall()
        reactions: dict[str, list[dict[str, str]]] = {}
        for r_emoji, r_nv, r_name in react_rows:
            reactions.setdefault(str(r_emoji), []).append({"nv_id": str(r_nv), "name": str(r_name)})

        # Reply snippet
        reply_snippet = None
        reply_id = row[5]
        if reply_id:
            r_msg = cx.execute(
                """
                SELECT m.id, m.sender_id, m.content, m.type,
                       COALESCE(u.display_name, m.sender_id) as sender_name
                FROM chat_messages m
                LEFT JOIN users u ON m.sender_id = u.nv_id
                WHERE m.id = ?
                """,
                (str(reply_id),),
            ).fetchone()
            if r_msg:
                reply_snippet = {
                    "id": str(r_msg[0]),
                    "sender_id": str(r_msg[1]),
                    "content": str(r_msg[2]),
                    "type": str(r_msg[3]),
                    "sender_name": str(r_msg[4]),
                }

        meta: dict[str, Any] = {}
        if isinstance(row[8], dict):
            meta = row[8]
        elif row[8]:
            try:
                meta = json.loads(row[8])
            except (TypeError, ValueError):
                pass

        return {
            "id": str(row[0]),
            "conversation_id": str(row[1]),
            "sender_id": str(row[2]),
            "type": str(row[3]),
            "content": str(row[4]),
            "reply_to_id": str(row[5]) if row[5] else None,
            "reply_snippet": reply_snippet,
            "is_unsent": bool(row[6]),
            "edited_at": str(row[7]) if row[7] else None,
            "metadata": meta,
            "created_at": str(row[9]),
            "sender_name": str(row[10]),
            "sender_role": str(row[11]),
            "reactions": reactions,
        }


def chat_message_edit(message_id: str, sender_id: str, new_content: str) -> dict[str, Any] | None:
    """Sửa tin nhắn (trong vòng 15 phút, chỉ tác giả mới được sửa)."""
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        msg = cx.execute(
            "SELECT sender_id, created_at, is_unsent FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not msg:
            return None
        if str(msg[0]) != sender_id or bool(msg[2]):
            return None
        # Kiểm tra thời hạn 15 phút (900s)
        try:
            created_dt = datetime.fromisoformat(str(msg[1]).replace("Z", "+00:00"))
            if (datetime.now(UTC) - created_dt).total_seconds() > 900:
                return None
        except Exception:
            pass

        cx.execute(
            "UPDATE chat_messages SET content = ?, edited_at = ? WHERE id = ?",
            (new_content.strip(), now, message_id),
        )
    return chat_message_get(message_id)


def chat_message_delete(message_id: str, sender_id: str) -> dict[str, Any] | None:
    """Thu hồi tin nhắn (is_unsent = 1)."""
    init_db()
    with _conn() as cx:
        msg = cx.execute(
            "SELECT sender_id, conversation_id FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not msg:
            return None
        s_id = str(msg[0])
        user_role = cx.execute("SELECT role FROM users WHERE nv_id = ?", (sender_id,)).fetchone()
        role_str = str(user_role[0]) if user_role else "nhan_vien"
        if s_id != sender_id and role_str not in ("quan_ly", "chu_quan"):
            return None

        cx.execute(
            """
            UPDATE chat_messages
            SET is_unsent = TRUE, content = 'Tin nhắn đã được thu hồi'
            WHERE id = ?
            """,
            (message_id,),
        )
    return chat_message_get(message_id)


def chat_message_react(message_id: str, nv_id: str, emoji: str) -> dict[str, Any]:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        existing = cx.execute(
            "SELECT emoji FROM chat_reactions WHERE message_id = ? AND nv_id = ?",
            (message_id, nv_id),
        ).fetchone()
        if existing and str(existing[0]) == emoji:
            cx.execute(
                "DELETE FROM chat_reactions WHERE message_id = ? AND nv_id = ?",
                (message_id, nv_id),
            )
        else:
            cx.execute(
                """
                INSERT INTO chat_reactions(message_id, nv_id, emoji, created_at)
                VALUES (?,?,?,?)
                ON CONFLICT(message_id, nv_id) DO UPDATE SET emoji = excluded.emoji, created_at = excluded.created_at
                """,
                (message_id, nv_id, emoji, now),
            )
    return chat_message_get(message_id) or {"id": message_id}


def chat_messages_list(
    conv_id: str, limit: int = 50, before_id: str | None = None
) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        if before_id:
            b_row = cx.execute(
                "SELECT created_at FROM chat_messages WHERE id = ?", (before_id,)
            ).fetchone()
            if b_row:
                before_time = str(b_row[0])
                rows = cx.execute(
                    """
                    SELECT id FROM chat_messages
                    WHERE conversation_id = ? AND created_at < ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (conv_id, before_time, limit),
                ).fetchall()
            else:
                rows = []
        else:
            rows = cx.execute(
                """
                SELECT id FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (conv_id, limit),
            ).fetchall()

    msg_ids = [str(r[0]) for r in reversed(rows)]
    return [m for mid in msg_ids if (m := chat_message_get(mid)) is not None]


def chat_messages_search(
    query: str, nv_id: str, conv_id: str | None = None, store_id: str = "quan_01"
) -> list[dict[str, Any]]:
    """Tìm kiếm nội dung tin nhắn trong các hội thoại mà người dùng có quyền xem."""
    init_db()
    q = f"%{query.strip()}%"
    with _conn() as cx:
        if conv_id:
            rows = cx.execute(
                """
                SELECT m.id FROM chat_messages m
                JOIN chat_participants p ON m.conversation_id = p.conversation_id AND p.nv_id = ?
                WHERE m.conversation_id = ? AND m.content LIKE ? AND m.is_unsent = FALSE AND p.status = 'active'
                ORDER BY m.created_at DESC LIMIT 50
                """,
                (nv_id, conv_id, q),
            ).fetchall()
        else:
            rows = cx.execute(
                """
                SELECT m.id FROM chat_messages m
                JOIN chat_conversations c ON m.conversation_id = c.id
                JOIN chat_participants p ON m.conversation_id = p.conversation_id AND p.nv_id = ?
                WHERE c.store_id = ? AND m.content LIKE ? AND m.is_unsent = FALSE AND p.status = 'active'
                ORDER BY m.created_at DESC LIMIT 50
                """,
                (nv_id, store_id, q),
            ).fetchall()
    return [m for r in rows if (m := chat_message_get(str(r[0]))) is not None]


def chat_read_receipts_update(conv_id: str, nv_id: str, message_id: str) -> list[dict[str, Any]]:
    """Cập nhật trạng thái đã xem (Seen receipt)."""
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO chat_read_receipts(conversation_id, nv_id, last_read_message_id, read_at)
            VALUES (?,?,?,?)
            ON CONFLICT(conversation_id, nv_id) DO UPDATE SET last_read_message_id = excluded.last_read_message_id, read_at = excluded.read_at
            """,
            (conv_id, nv_id, message_id, now),
        )
        cx.execute(
            "UPDATE chat_participants SET last_read_at = ? WHERE conversation_id = ? AND nv_id = ?",
            (now, conv_id, nv_id),
        )
    return chat_read_receipts(conv_id)


def chat_message_read(conv_id: str, nv_id: str, message_id: str) -> list[dict[str, Any]]:
    """Compatibility name used by the WebSocket chat service."""
    return chat_read_receipts_update(conv_id, nv_id, message_id)


def chat_message_pin(message_id: str, sender_id: str, pinned: bool = True) -> dict[str, Any] | None:
    """Pin state is stored in message metadata for the current chat schema."""
    message = chat_message_get(message_id)
    if not message:
        return None
    init_db()
    with _conn() as cx:
        user_role = cx.execute("SELECT role FROM users WHERE nv_id = ?", (sender_id,)).fetchone()
        role_str = str(user_role[0]) if user_role else "nhan_vien"
        if message.get("sender_id") != sender_id and role_str not in ("quan_ly", "chu_quan"):
            return None
        metadata = dict(message.get("metadata") or {})
        metadata["pinned"] = pinned
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        cx.execute(
            "UPDATE chat_messages SET metadata=?, edited_at=? WHERE id=?",
            (json.dumps(metadata, ensure_ascii=False), now, message_id),
        )
    return chat_message_get(message_id)


def chat_read_receipts(conv_id: str) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            """
            SELECT r.nv_id, COALESCE(u.display_name, r.nv_id) as display_name,
                   r.last_read_message_id, r.read_at, COALESCE(u.role, 'nhan_vien') as role
            FROM chat_read_receipts r
            LEFT JOIN users u ON r.nv_id = u.nv_id
            WHERE r.conversation_id = ?
            """,
            (conv_id,),
        ).fetchall()
        return [
            {
                "nv_id": str(r[0]),
                "display_name": str(r[1]),
                "last_read_message_id": str(r[2]),
                "read_at": str(r[3]),
                "role": str(r[4]),
            }
            for r in rows
        ]


def chat_unread_count_total(nv_id: str, store_id: str = "quan_01") -> int:
    init_db()
    convs = chat_conversation_list_for_user(nv_id, store_id)
    return sum(c.get("unread_count", 0) for c in convs)


# ── Sơ đồ Bàn & Đặt Bàn Tự Động (Auto Reservation) ──────────────────────────


def _seed_tables_neu_trong(cx: sqlite3.Connection) -> None:
    count = cx.execute("SELECT COUNT(*) FROM ban_an").fetchone()[0]
    if count == 0:
        default_tables = [
            ("B101", "quan_01", "Bàn 101", 2, "Tầng 1 - Cửa sổ", json.dumps(["B102"])),
            ("B102", "quan_01", "Bàn 102", 2, "Tầng 1 - Cửa sổ", json.dumps(["B101"])),
            ("B103", "quan_01", "Bàn 103", 2, "Tầng 1 - Trong nhà", json.dumps([])),
            ("B104", "quan_01", "Bàn 104", 2, "Tầng 1 - Trong nhà", json.dumps([])),
            ("B105", "quan_01", "Bàn 105", 4, "Tầng 1 - Sân vườn", json.dumps([])),
            ("B106", "quan_01", "Bàn 106", 4, "Tầng 1 - Sân vườn", json.dumps([])),
            ("B201", "quan_01", "Bàn 201", 4, "Tầng 2 - Yên tĩnh", json.dumps([])),
            ("B202", "quan_01", "Bàn 202", 4, "Tầng 2 - Yên tĩnh", json.dumps([])),
            ("B203", "quan_01", "Bàn 203", 4, "Tầng 2 - Nhóm lớn", json.dumps(["B204"])),
            ("B204", "quan_01", "Bàn 204", 4, "Tầng 2 - Nhóm lớn", json.dumps(["B203"])),
        ]
        cx.executemany(
            """
            INSERT INTO ban_an(id, store_id, ten_ban, suc_chua, vi_tri, can_combine_with)
            VALUES (?,?,?,?,?,?)
            """,
            default_tables,
        )


def table_list(store_id: str = "quan_01") -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            "SELECT * FROM ban_an WHERE store_id=? AND trang_thai_hoat_dong=1 ORDER BY id ASC",
            (store_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["can_combine_with"] = json.loads(d.get("can_combine_with") or "[]")
            except Exception:
                d["can_combine_with"] = []
            result.append(d)
        return result


def table_get(table_id: str, store_id: str = "quan_01") -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        r = cx.execute(
            "SELECT * FROM ban_an WHERE id=? AND store_id=?", (table_id, store_id)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["can_combine_with"] = json.loads(d.get("can_combine_with") or "[]")
        except Exception:
            d["can_combine_with"] = []
        return d


def reservation_create(record: dict[str, Any]) -> str:
    init_db()
    res_id = record.get("id") or f"res_{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    table_ids = record.get("table_ids") or []
    if isinstance(table_ids, list):
        table_ids_str = json.dumps(table_ids)
    else:
        table_ids_str = str(table_ids)

    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO dat_ban(
                id, store_id, psid, customer_name, phone, booking_time, duration_minutes,
                party_size, table_ids, status, source, notes, idempotency_key, notified_nv_id,
                notification_acked_at, cancelled_by, cancelled_reason, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                res_id,
                record.get("store_id", "quan_01"),
                record.get("psid", ""),
                record.get("customer_name", ""),
                record.get("phone", ""),
                record.get("booking_time", ""),
                int(record.get("duration_minutes", 120)),
                int(record.get("party_size", 2)),
                table_ids_str,
                record.get("status", "confirmed"),
                record.get("source", "ai_auto"),
                record.get("notes", ""),
                record.get("idempotency_key", ""),
                record.get("notified_nv_id"),
                record.get("notification_acked_at"),
                record.get("cancelled_by"),
                record.get("cancelled_reason"),
                record.get("created_at") or now,
                record.get("updated_at") or now,
            ),
        )
        cx.execute(
            """
            INSERT INTO dat_ban_lich_su(dat_ban_id, hanh_dong, trang_thai_cu, trang_thai_moi, thuc_hien_boi, ly_do, thoi_gian)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                res_id,
                "tao_moi",
                None,
                record.get("status", "confirmed"),
                record.get("source", "ai_auto"),
                "Khách đặt bàn",
                now,
            ),
        )
    return res_id


def reservation_get(res_id: str) -> dict[str, Any] | None:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        r = cx.execute("SELECT * FROM dat_ban WHERE id=?", (res_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["table_ids"] = json.loads(d.get("table_ids") or "[]")
        except Exception:
            d["table_ids"] = []
        return d


def reservation_get_by_idempotency(
    idem_key: str, store_id: str = "quan_01"
) -> dict[str, Any] | None:
    if not idem_key:
        return None
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        r = cx.execute(
            "SELECT * FROM dat_ban WHERE store_id=? AND idempotency_key=? AND status NOT IN ('cancelled', 'no_show')",
            (store_id, idem_key),
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["table_ids"] = json.loads(d.get("table_ids") or "[]")
        except Exception:
            d["table_ids"] = []
        return d


def reservation_list(
    store_id: str = "quan_01",
    date: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        query = "SELECT * FROM dat_ban WHERE store_id=?"
        params: list[Any] = [store_id]
        if date:
            query += " AND booking_time LIKE ?"
            params.append(f"{date}%")
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY booking_time ASC LIMIT ?"
        params.append(limit)

        rows = cx.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["table_ids"] = json.loads(d.get("table_ids") or "[]")
            except Exception:
                d["table_ids"] = []
            result.append(d)
        return result


def reservation_update_status(
    res_id: str,
    new_status: str,
    actor: str = "system",
    reason: str = "",
    cancelled_by: str | None = None,
) -> bool:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.execute("SELECT status FROM dat_ban WHERE id=?", (res_id,)).fetchone()
        if not cur:
            return False
        old_status = cur["status"]
        if old_status == new_status:
            return True

        if cancelled_by:
            cx.execute(
                """
                UPDATE dat_ban
                SET status=?, updated_at=?, cancelled_by=?, cancelled_reason=?
                WHERE id=?
                """,
                (new_status, now, cancelled_by, reason, res_id),
            )
        else:
            cx.execute(
                "UPDATE dat_ban SET status=?, updated_at=? WHERE id=?",
                (new_status, now, res_id),
            )

        cx.execute(
            """
            INSERT INTO dat_ban_lich_su(dat_ban_id, hanh_dong, trang_thai_cu, trang_thai_moi, thuc_hien_boi, ly_do, thoi_gian)
            VALUES (?,?,?,?,?,?,?)
            """,
            (res_id, f"chuyen_{new_status}", old_status, new_status, actor, reason, now),
        )
        return True


def reservation_find_active_by_psid(psid: str, store_id: str = "quan_01") -> list[dict[str, Any]]:
    if not psid:
        return []
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            """
            SELECT * FROM dat_ban
            WHERE store_id=? AND psid=? AND status IN ('held', 'confirmed')
            ORDER BY booking_time ASC
            """,
            (store_id, psid),
        ).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            try:
                d["table_ids"] = json.loads(d.get("table_ids") or "[]")
            except Exception:
                d["table_ids"] = []
            res.append(d)
        return res


def reservation_find_active_by_phone(phone: str, store_id: str = "quan_01") -> list[dict[str, Any]]:
    if not phone:
        return []
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            """
            SELECT * FROM dat_ban
            WHERE store_id=? AND phone=? AND status IN ('held', 'confirmed')
            ORDER BY booking_time ASC
            """,
            (store_id, phone),
        ).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            try:
                d["table_ids"] = json.loads(d.get("table_ids") or "[]")
            except Exception:
                d["table_ids"] = []
            res.append(d)
        return res


def reservation_count_no_shows(phone: str = "", psid: str = "", store_id: str = "quan_01") -> int:
    init_db()
    with _conn() as cx:
        conds = []
        params: list[Any] = [store_id]
        if phone:
            conds.append("phone=?")
            params.append(phone)
        if psid:
            conds.append("psid=?")
            params.append(psid)
        if not conds:
            return 0
        sql = f"SELECT COUNT(*) FROM dat_ban WHERE store_id=? AND status='no_show' AND ({' OR '.join(conds)})"
        row = cx.execute(sql, params).fetchone()
        return int(row[0]) if row else 0


def thong_bao_ca_create(row: dict[str, Any]) -> str:
    init_db()
    tb_id = row.get("id") or f"tb_{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute(
            """
            INSERT INTO thong_bao_ca(id, store_id, dat_ban_id, ca_id, nv_id, tieu_de, noi_dung, da_xem, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                tb_id,
                row.get("store_id", "quan_01"),
                row.get("dat_ban_id", ""),
                row.get("ca_id", ""),
                row.get("nv_id", ""),
                row.get("tieu_de", "Thông báo đặt bàn"),
                row.get("noi_dung", ""),
                int(row.get("da_xem", 0)),
                row.get("created_at") or now,
            ),
        )
    return tb_id


def thong_bao_ca_list(
    nv_id: str, unread_only: bool = False, store_id: str = "quan_01"
) -> list[dict[str, Any]]:
    init_db()
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        sql = "SELECT * FROM thong_bao_ca WHERE store_id=? AND nv_id=?"
        params: list[Any] = [store_id, nv_id]
        if unread_only:
            sql += " AND da_xem=0"
        sql += " ORDER BY created_at DESC LIMIT 50"
        rows = cx.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def thong_bao_ca_ack(thong_bao_id: str, nv_id: str) -> bool:
    init_db()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        res = cx.execute(
            "UPDATE thong_bao_ca SET da_xem=1 WHERE id=? AND nv_id=?",
            (thong_bao_id, nv_id),
        )
        if res.rowcount > 0:
            # Also update dat_ban notification_acked_at
            tb = cx.execute(
                "SELECT dat_ban_id FROM thong_bao_ca WHERE id=?", (thong_bao_id,)
            ).fetchone()
            if tb and tb[0]:
                cx.execute(
                    "UPDATE dat_ban SET notification_acked_at=? WHERE id=? AND notification_acked_at IS NULL",
                    (now, tb[0]),
                )
            return True
        return False


def list_active_stores() -> list[str]:
    """Trả về danh sách store_id đang hoạt động (có user hoặc ca trống)."""
    init_db()
    with _conn() as cx:
        # Lấy store_id từ users
        user_stores = cx.execute(
            "SELECT DISTINCT store_id FROM users WHERE store_id IS NOT NULL AND store_id != ''"
        ).fetchall()
        # Lấy store_id từ open_shifts
        shift_stores = cx.execute(
            "SELECT DISTINCT store_id FROM open_shifts WHERE store_id IS NOT NULL AND store_id != ''"
        ).fetchall()
    stores = set()
    for r in user_stores:
        stores.add(str(r[0]))
    for r in shift_stores:
        stores.add(str(r[0]))
    # Luôn bao gồm store mặc định
    stores.add(DEFAULT_STORE_ID)
    return sorted(stores)
