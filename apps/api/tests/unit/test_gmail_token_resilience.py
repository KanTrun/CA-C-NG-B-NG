# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Audit khả năng phục hồi khi khoá mã hoá đổi (token không giải mã được).

Kịch bản thật: quản trị viên đổi `NHIPQUAN_ENCRYPTION_KEY` (hoặc trước đó key
sinh tạm rồi restart). Token cũ không giải mã được. Hệ quả mong muốn: app PHẢI
vẫn liệt kê được tài khoản để người dùng bấm "kết nối lại" — không được sập 500.
"""

from __future__ import annotations

from ca_api import persist
from ca_api.interfaces.http.main import app
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

_BASE = "/api/v1/gmail"


def test_list_accounts_survives_undecryptable_token(monkeypatch) -> None:
    """Token hỏng không được làm `GET /accounts` trả 500."""
    acc = persist.gmail_account_create(
        store_id="quan_01", nv_id="nv_02", email="hong.khoa@gmail.com"
    )
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid,
        access_token="KHONG_PHAI_BI_MAT_KIEM_THU_MOT",
        refresh_token=None,
        expires_at="2030-01-01T00:00:00Z",
    )

    # Giả lập: khoá đã đổi ⇒ giải mã ném InvalidToken.
    from cryptography.fernet import InvalidToken

    def _boom(_: str) -> str:
        raise InvalidToken

    monkeypatch.setattr(persist, "_decrypt", _boom)

    res = client.get(_BASE + "/accounts", headers=headers(client, "hung"))

    assert res.status_code == 200, f"UI không mở được để kết nối lại (status={res.status_code})"
    row = next(a for a in res.json()["accounts"] if a["id"] == aid)
    # Phải báo trạng thái để người dùng biết cần kết nối lại.
    assert row["has_tokens"] is False or row.get("token_broken") is True


def test_account_detail_survives_undecryptable_token(monkeypatch) -> None:
    """`GET /accounts/{id}` cũng phải chịu được token hỏng."""
    acc = persist.gmail_account_create(
        store_id="quan_01", nv_id="nv_02", email="hong.khoa.2@gmail.com"
    )
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid,
        access_token="KHONG_PHAI_BI_MAT_KIEM_THU_HAI",
        refresh_token=None,
        expires_at="2030-01-01T00:00:00Z",
    )

    from cryptography.fernet import InvalidToken

    monkeypatch.setattr(persist, "_decrypt", lambda _: (_ for _ in ()).throw(InvalidToken()))

    res = client.get(f"{_BASE}/accounts/{aid}", headers=headers(client, "hung"))
    assert res.status_code == 200


def test_token_status_query_does_not_decrypt() -> None:
    """Truy vấn trạng thái token phải không giải mã (rẻ và không thể ném lỗi)."""
    acc = persist.gmail_account_create(
        store_id="quan_01", nv_id="nv_02", email="trang.thai@gmail.com"
    )
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid,
        access_token="KHONG_PHAI_BI_MAT_KIEM_THU_BA",
        refresh_token=None,
        expires_at="2031-02-03T04:05:06Z",
    )

    status = persist.gmail_token_status(aid)
    assert status is not None
    assert status["expires_at"] == "2031-02-03T04:05:06Z"
    assert status["has_refresh_token"] is False
    assert "access_token" not in status, "trạng thái không được trả token thật"


def test_token_status_none_when_missing() -> None:
    acc = persist.gmail_account_create(
        store_id="quan_01", nv_id="nv_02", email="khong.token@gmail.com"
    )
    assert persist.gmail_token_status(str(acc["id"])) is None
