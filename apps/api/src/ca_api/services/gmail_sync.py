"""Gmail incremental sync — tầng API (cần ghi DB, không thuộc package agents).

Lý do tách khỏi `ca_agents.ag_gmail`: gate `test_architecture` cấm package agents
import `ca_api`/`psycopg`. Phần gọi Gmail API nằm ở `ag_gmail.service`; phần lưu
trữ và điều phối nằm ở đây.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ca_agents.ag_gmail import GmailService, refresh_access_token

from ca_api.persist import (
    gmail_account_get,
    gmail_account_list,
    gmail_filter_upsert,
    gmail_label_upsert,
    gmail_message_apply_labels,
    gmail_message_delete,
    gmail_message_get,
    gmail_message_upsert,
    gmail_sync_state_get,
    gmail_sync_state_upsert,
    gmail_token_get,
    gmail_token_save,
)


class GmailSyncError(Exception):
    """Gmail sync error."""


# Làm mới sớm 5 phút để không dùng token đã cận hết hạn giữa chừng request.
_REFRESH_SKEW = timedelta(minutes=5)


def _parse_expiry(value: str | None) -> datetime | None:
    """Chuẩn hoá `expires_at` thành datetime AWARE UTC; None nếu không đọc được.

    Vì sao cần: `google-auth` ghi `expiry` dạng NAIVE UTC (hàm `utcnow()` của
    thư viện cố tình bỏ tzinfo để tương thích ngược). Nếu ta parse chuỗi đó
    thành aware rồi so với `datetime.now()` theo giờ máy (VN, +07), kết quả
    lệch đúng 7 tiếng — token còn hạn bị coi là hết hạn (hoặc ngược lại).
    """
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Chuỗi không kèm offset ⇒ hiểu là UTC (đúng quy ước của google-auth).
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _token_needs_refresh(expires_at: str | None, *, now: datetime | None = None) -> bool:
    """Token đã hết hạn (hoặc cận hạn) hay chưa. Không đọc được thời gian ⇒ False."""
    exp = _parse_expiry(expires_at)
    if exp is None:
        return False
    current = now or datetime.now(UTC)
    return exp - _REFRESH_SKEW <= current


async def _ensure_fresh_token(account_id: str) -> dict[str, Any]:
    """Lấy token còn hạn; tự làm mới nếu đã hết hạn."""
    tokens = gmail_token_get(account_id)
    if not tokens:
        raise GmailSyncError(f"No OAuth tokens for account {account_id}")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token or not _token_needs_refresh(tokens.get("expires_at")):
        return tokens

    new_tokens = await refresh_access_token(str(refresh_token))
    expires_at = _parse_expiry(new_tokens.get("expires_at"))
    gmail_token_save(
        account_id,
        access_token=str(new_tokens["access_token"]),
        refresh_token=new_tokens.get("refresh_token") or str(refresh_token),
        expires_at=expires_at.isoformat() if expires_at else "",
        scope=str(new_tokens.get("scope", "")),
        token_type=str(new_tokens.get("token_type", "Bearer")),
    )
    return new_tokens


def _persist_message(account_id: str, raw_message: dict[str, Any]) -> bool:
    """Lưu một message vào DB. Trả True nếu là email chưa đọc."""
    parsed = GmailService.parse_message(raw_message)
    parsed.account_id = account_id
    gmail_message_upsert(
        account_id=account_id,
        message_id=parsed.id,
        thread_id=parsed.thread_id,
        label_ids=parsed.label_ids,
        snippet=parsed.snippet,
        from_email=parsed.from_email,
        to_emails=parsed.to_emails,
        cc_emails=parsed.cc_emails,
        subject=parsed.subject,
        body_text=parsed.body_text,
        body_html=parsed.body_html,
        internal_date=parsed.internal_date,
        is_read=parsed.is_read,
        is_starred=parsed.is_starred,
        has_attachment=parsed.has_attachment,
        raw_headers=parsed.raw_headers,
    )
    return not parsed.is_read


def _upsert_from_history(account_id: str, service: GmailService, message_id: str) -> int:
    """Lấy bản đầy đủ của email mới rồi lưu. Trả 1 nếu lưu được, 0 nếu lỗi.

    History API chỉ trả metadata rút gọn (thiếu subject/body), nên phải gọi
    `messages.get` để lấy nội dung thật.
    """
    try:
        raw = service.get_message(message_id)
    except Exception:  # noqa: BLE001 — message có thể đã bị xoá giữa chừng
        return 0
    _persist_message(account_id, raw)
    return 1


def _apply_label_change(account_id: str, change: dict[str, Any], *, added: bool) -> bool:
    """Áp dụng thay đổi nhãn từ history lên email local.

    History báo `{message: {id, labelIds}, labelIds: [...]}`. Ta lấy tập nhãn
    hiện có, thêm/bớt đúng phần thay đổi, rồi ghi lại kèm suy ra is_read/is_starred.
    """
    msg = change.get("message", {}) if isinstance(change, dict) else {}
    message_id = str(msg.get("id", "")) if isinstance(msg, dict) else ""
    if not message_id:
        return False

    delta = [str(x) for x in change.get("labelIds", []) or []]
    if not delta:
        return False

    current = gmail_message_get(account_id, message_id)
    if current is None:
        return False

    labels = set(current.get("label_ids") or [])
    labels.update(delta) if added else labels.difference_update(delta)
    return gmail_message_apply_labels(account_id, message_id, sorted(labels))


async def sync_account(account_id: str, *, full_sync: bool = False) -> dict[str, Any]:
    """Đồng bộ một tài khoản: toàn bộ hoặc tăng dần theo history."""
    account = gmail_account_get(account_id)
    if not account:
        raise GmailSyncError(f"Account {account_id} not found")

    tokens = await _ensure_fresh_token(account_id)
    service = GmailService(str(tokens["access_token"]), tokens.get("refresh_token"))
    email = str(account["email"])

    sync_state = gmail_sync_state_get(account_id)
    start_history_id = (
        str(sync_state["last_history_id"])
        if sync_state and sync_state.get("last_history_id")
        else None
    )

    if full_sync or not start_history_id:
        return await _full_sync(account_id, service, email)
    return await _incremental_sync(account_id, service, start_history_id, email)


async def _full_sync(account_id: str, service: GmailService, email: str) -> dict[str, Any]:
    """Đồng bộ toàn bộ: nhãn, bộ lọc, rồi tải hết email theo trang."""
    errors: list[str] = []
    labels_synced = 0
    filters_synced = 0
    messages_synced = 0
    unread_count = 0

    # ── Nhãn ──
    raw_labels = service.list_labels()
    for raw_label in raw_labels:
        parsed_label = GmailService.parse_label(raw_label, account_id)
        gmail_label_upsert(
            account_id=account_id,
            label_id=parsed_label.id,
            name=parsed_label.name,
            label_type=parsed_label.label_type,
            message_list_visibility=parsed_label.message_list_visibility,
            label_list_visibility=parsed_label.label_list_visibility,
            color_background=parsed_label.color_background,
            color_text=parsed_label.color_text,
            total_messages=parsed_label.total_messages,
            unread_messages=parsed_label.unread_messages,
        )
    labels_synced = len(raw_labels)

    # ── Bộ lọc ──
    raw_filters = service.list_filters()
    for raw_filter in raw_filters:
        parsed_filter = GmailService.parse_filter(raw_filter, account_id)
        gmail_filter_upsert(
            account_id=account_id,
            filter_id=parsed_filter.id,
            criteria=parsed_filter.criteria,
            action=parsed_filter.action,
        )
    filters_synced = len(raw_filters)

    # ── Email (phân trang, gộp 500 mỗi lượt) ──
    page_token: str | None = None
    while True:
        result = service.list_messages(max_results=500, page_token=page_token)
        messages = result.get("messages", [])
        if not messages:
            break

        message_ids = [str(m["id"]) for m in messages]
        for msg_data in service.batch_get_messages(message_ids):
            if "error" in msg_data:
                errors.append(f"Message {msg_data.get('id', 'unknown')}: {msg_data['error']}")
                continue
            if _persist_message(account_id, msg_data):
                unread_count += 1
            messages_synced += 1

        next_page = result.get("nextPageToken")
        page_token = str(next_page) if next_page else None
        if not page_token:
            break

    profile = service.get_profile()
    gmail_sync_state_upsert(
        account_id,
        last_history_id=str(profile.get("historyId", "")) or None,
        last_sync_at=datetime.now(UTC).isoformat(),
        total_messages=messages_synced,
        unread_count=unread_count,
    )

    return {
        "account_id": account_id,
        "email": email,
        "type": "full",
        "messages_synced": messages_synced,
        "labels_synced": labels_synced,
        "filters_synced": filters_synced,
        "errors": errors,
    }


async def _incremental_sync(
    account_id: str,
    service: GmailService,
    start_history_id: str,
    email: str,
) -> dict[str, Any]:
    """Đồng bộ tăng dần theo history API.

    Phải ÁP DỤNG mọi loại thay đổi (thêm/xoá/đổi nhãn), không chỉ đếm: nếu chỉ
    đếm thì email đã xoá vẫn nằm trong hộp thư app, và trạng thái đã đọc/có sao
    sẽ lệch vĩnh viễn so với Gmail.
    """
    errors: list[str] = []
    messages_added = 0
    messages_modified = 0
    messages_deleted = 0

    try:
        page_token: str | None = None
        latest_history_id = start_history_id

        while True:
            result = service.list_history(
                start_history_id=start_history_id,
                max_results=1000,
                page_token=page_token,
            )

            for record in result.get("history", []):
                if "id" in record:
                    latest_history_id = str(record["id"])

                for msg_added in record.get("messagesAdded", []):
                    msg = msg_added.get("message", {})
                    if msg and "id" in msg:
                        # History chỉ kèm metadata rút gọn; cần lấy bản đầy đủ
                        # để có subject/body (nếu không, email mới sẽ trống nội dung).
                        messages_added += _upsert_from_history(account_id, service, str(msg["id"]))

                for msg_deleted in record.get("messagesDeleted", []):
                    msg = msg_deleted.get("message", {})
                    if msg and "id" in msg and gmail_message_delete(account_id, str(msg["id"])):
                        messages_deleted += 1

                for change in record.get("labelsAdded", []):
                    if _apply_label_change(account_id, change, added=True):
                        messages_modified += 1

                for change in record.get("labelsRemoved", []):
                    if _apply_label_change(account_id, change, added=False):
                        messages_modified += 1

            next_page = result.get("nextPageToken")
            page_token = str(next_page) if next_page else None
            if not page_token:
                break

        gmail_sync_state_upsert(
            account_id,
            last_history_id=latest_history_id,
            last_sync_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:
        errors.append(str(exc))
        raise GmailSyncError(f"Incremental sync failed: {exc}") from exc

    return {
        "account_id": account_id,
        "email": email,
        "type": "incremental",
        "messages_added": messages_added,
        "messages_modified": messages_modified,
        "messages_deleted": messages_deleted,
        "errors": errors,
    }


async def sync_all_accounts(
    store_id: str, *, nv_id: str | None = None, full_sync: bool = False
) -> list[dict[str, Any]]:
    """Đồng bộ các tài khoản Gmail của một quán (hoặc của một người khi có `nv_id`)."""
    accounts = gmail_account_list(store_id, nv_id)
    results: list[dict[str, Any]] = []

    for account in accounts:
        account_id = str(account["id"])
        try:
            results.append(await sync_account(account_id, full_sync=full_sync))
        except Exception as exc:
            results.append(
                {
                    "account_id": account_id,
                    "email": str(account.get("email", "")),
                    "type": "error",
                    "error": str(exc),
                }
            )

    return results


def message_payload(account_id: str, raw_message: dict[str, Any]) -> str:
    """Chuỗi JSON để log/audit (không chứa token)."""
    parsed = GmailService.parse_message(raw_message)
    return json.dumps(
        {"account_id": account_id, "message_id": parsed.id, "subject": parsed.subject},
        ensure_ascii=False,
    )
