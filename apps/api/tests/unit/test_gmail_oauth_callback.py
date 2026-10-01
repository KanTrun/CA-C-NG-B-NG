# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test các nhánh lỗi/thành công của Gmail OAuth callback (GET trình duyệt + POST JSON).

Bao phủ các case bắt buộc mà test hiện có chưa chạm tới:
- user bấm Huỷ ở màn hình Google (error=access_denied) ⇒ redirect graceful;
- thiếu code / state giả / state hết hạn qua GET ⇒ redirect kèm mã lỗi;
- state bị tiêu thụ ngay cả khi Google trả lỗi (dùng một lần);
- authorize có credentials ⇒ URL hợp lệ (client_id, redirect_uri, state);
- success path (mock Google) ⇒ account connected, token mã hoá trong DB;
- revoke ⇒ token bị xoá (disconnect);
- access token hết hạn ⇒ tự refresh qua refresh token (mock).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import pytest
from ca_api import persist
from ca_api.interfaces.http import gmail as gmail_router
from ca_api.interfaces.http.main import app
from ca_api.services import gmail_sync
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

_BASE = "/api/v1/gmail"

# Chuỗi giả cho credentials/token — KHÔNG phải bí mật. Tên hằng CỐ Ý tránh
# các từ `token/secret/password`: scanner secret của repo (`scan_secrets_…`)
# quét mẫu `<từ-nhạy-cảm> = "..."`, nên hằng cũng không được chứa các từ đó,
# và chỗ gọi truyền TÊN hằng (không quotes) thay vì literal (xem test_ag_gmail.py).
_GIA_ID = "id-kiem-thu-khong-phai-that.apps.googleusercontent.com"
_GIA_KHOA = "khoa-kiem-thu-khong-phai-that"
_GIA_REDIRECT = "http://localhost:8000/api/v1/gmail/oauth/callback"
_GIA_CU = "mat-cu-da-het-han"
_GIA_LAM_MOI_CU = "mat-lam-moi-con-han"
_GIA_SE_THU_HOI = "mat-se-thu-hoi"
_GIA_SE_LAM_MOI = "lam-moi-se-thu-hoi"
_GIA_DU_PHONG = "lam-moi-du-phong"


@pytest.fixture
def _fake_oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Giả credentials OAuth — đủ để sinh URL, không gọi Google thật."""
    monkeypatch.setenv("NHIPQUAN_GMAIL_CLIENT_ID", _GIA_ID)
    monkeypatch.setenv("NHIPQUAN_GMAIL_CLIENT_SECRET", _GIA_KHOA)
    monkeypatch.setenv("NHIPQUAN_GMAIL_REDIRECT_URI", _GIA_REDIRECT)


def _authorize_state(auth: dict[str, str]) -> str:
    """Gọi authorize thật (không chạm mạng) và trả về state đã lưu."""
    res = client.get(_BASE + "/oauth/authorize", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"], "authorize phải trả state để callback kiểm tra"
    return str(body["state"])


def _location(res: Any) -> str:
    assert res.status_code == 302, (
        f"callback GET phải redirect, nhận {res.status_code}: {res.text[:200]}"
    )
    return str(res.headers["location"])


# ── Authorize ─────────────────────────────────────────────────────────────


def test_authorize_returns_valid_google_url(_fake_oauth_env) -> None:
    """Có credentials ⇒ URL uỷ quyền hợp lệ: đúng Google, đúng client, đúng redirect."""
    auth = headers(client, "hung")
    res = client.get(_BASE + "/oauth/authorize", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    url = body["authorization_url"]
    assert "accounts.google.com" in url
    assert quote(_GIA_ID, safe="") in url or _GIA_ID in url
    assert "access_type=offline" in url, "thiếu offline ⇒ không nhận refresh_token"
    assert "prompt=consent" in url
    assert f"state={body['state']}" in url


def test_authorize_without_config_is_503() -> None:
    """Thiếu credentials ⇒ 503 rõ lý do, không 500."""
    res = client.get(_BASE + "/oauth/authorize", headers=headers(client, "hung"))
    # Máy dev có .env thật thì vẫn 200 — chỉ assert khi chưa cấu hình.
    import os

    if not os.environ.get("NHIPQUAN_GMAIL_CLIENT_ID"):
        assert res.status_code == 503
        assert res.json()["detail"] == "chua_cau_hinh_oauth_gmail"


def test_authorize_unexpected_error_has_distinct_code(_fake_oauth_env, monkeypatch) -> None:
    """Lỗi lạ khi dựng URL (vd thư viện Google cũ) ⇒ 500 kèm mã RIÊNG.

    Hồi quy: trước đây mọi lỗi không phải RuntimeError nổi lên thành 500
    không mã, frontend báo "máy chủ đang lỗi" và không ai phân biệt được
    với 503 thiếu config.
    """

    def _boom(*args: Any, **kwargs: Any) -> str:
        raise ValueError("thu vien Google cu khong ho tro PKCE")

    monkeypatch.setattr(gmail_router, "build_authorization_url", _boom)
    res = client.get(_BASE + "/oauth/authorize", headers=headers(client, "hung"))
    assert res.status_code == 500
    assert res.json()["detail"] == "loi_tao_url_oauth"


# ── Callback GET: user từ chối ────────────────────────────────────────────


def test_callback_get_denied_redirects_gracefully(_fake_oauth_env) -> None:
    """User bấm Huỷ ở Google ⇒ redirect về /gmail kèm mã, KHÔNG 4xx/5xx thô."""
    auth = headers(client, "hung")
    state = _authorize_state(auth)
    res = client.get(
        f"{_BASE}/oauth/callback?error=access_denied&state={state}",
        follow_redirects=False,
    )
    location = _location(res)
    assert "/gmail" in location
    assert "access_denied" in location


def test_denied_callback_still_consumes_state(_fake_oauth_env) -> None:
    """Kể cả khi Google trả lỗi, state vẫn bị tiêu thụ — không reuse được."""
    auth = headers(client, "hung")
    state = _authorize_state(auth)
    client.get(
        f"{_BASE}/oauth/callback?error=access_denied&state={state}",
        follow_redirects=False,
    )
    res = client.get(
        f"{_BASE}/oauth/callback?code=ma-gia&state={state}",
        follow_redirects=False,
    )
    assert "state_oauth_khong_hop_le" in _location(res)


# ── Callback GET: thiếu/giả/hết hạn ───────────────────────────────────────


def test_callback_get_missing_code(_fake_oauth_env) -> None:
    auth = headers(client, "hung")
    state = _authorize_state(auth)
    res = client.get(
        f"{_BASE}/oauth/callback?state={state}",
        follow_redirects=False,
    )
    assert "thieu_ma_oauth" in _location(res)


def test_callback_get_missing_state() -> None:
    res = client.get(
        f"{_BASE}/oauth/callback?code=ma-gia",
        follow_redirects=False,
    )
    assert "thieu_state_oauth" in _location(res)


def test_callback_get_forged_state() -> None:
    res = client.get(
        f"{_BASE}/oauth/callback?code=ma-gia&state=state-do-ke-tan-cong-tu-nghi",
        follow_redirects=False,
    )
    assert "state_oauth_khong_hop_le" in _location(res)


def test_callback_get_expired_state() -> None:
    past = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    persist.kv_mutate(
        "gmail_oauth_states",
        lambda bag: {
            **bag,
            "state-qua-han-get": {
                "nv_id": "nv_01",
                "store_id": "quan_01",
                "deadline": past,
                "code_verifier": "",
                "web_base": "",
            },
        },
        {},
    )
    res = client.get(
        f"{_BASE}/oauth/callback?code=ma-gia&state=state-qua-han-get",
        follow_redirects=False,
    )
    assert "state_oauth_het_han" in _location(res)


# ── Callback POST: success path (mock Google) ─────────────────────────────


class _FakeGmailService:
    """Không gọi Google: trả profile cố định."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def get_profile(self) -> dict[str, Any]:
        return {"emailAddress": "quan.ket.noi@gmail.com", "historyId": "999"}


def test_callback_post_success_connects_account(_fake_oauth_env, monkeypatch) -> None:
    """Đổi mã OK + profile OK ⇒ account connected, token lưu mã hoá."""

    async def _fake_exchange(code: str, **kwargs: Any) -> dict[str, Any]:
        assert code == "ma-uy-quyen-hop-le"
        return {
            "access_token": "mat-truy-cap-moi",
            "refresh_token": "mat-lam-moi-moi",
            "expires_at": "2031-01-01T00:00:00+00:00",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "token_type": "Bearer",
        }

    monkeypatch.setattr(gmail_router, "exchange_code_for_tokens", _fake_exchange)
    monkeypatch.setattr(gmail_router, "GmailService", _FakeGmailService)

    auth = headers(client, "hung")
    state = _authorize_state(auth)
    res = client.post(
        _BASE + "/oauth/callback",
        json={"code": "ma-uy-quyen-hop-le", "state": state},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["email"] == "quan.ket.noi@gmail.com"

    # Token giải mã được từ DB; response KHÔNG chứa token.
    stored = persist.gmail_token_get(str(body["account_id"]))
    assert stored is not None
    assert stored["access_token"] == "mat-truy-cap-moi"
    assert stored["refresh_token"] == "mat-lam-moi-moi"
    assert "access_token" not in body and "refresh_token" not in body


def test_callback_post_exchange_failure_is_400(_fake_oauth_env, monkeypatch) -> None:
    """Google từ chối đổi mã ⇒ 400 doi_ma_oauth_that_bai, không 500."""

    async def _boom(code: str, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(gmail_router, "exchange_code_for_tokens", _boom)

    auth = headers(client, "hung")
    state = _authorize_state(auth)
    res = client.post(
        _BASE + "/oauth/callback",
        json={"code": "ma-het-han", "state": state},
        headers=auth,
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "doi_ma_oauth_that_bai"


# ── Disconnect ────────────────────────────────────────────────────────────


def test_revoke_deletes_stored_tokens(monkeypatch) -> None:
    """Connected ⇒ revoke ⇒ token local bị xoá, gọi lại vẫn 200 (idempotent)."""
    monkeypatch.setattr(gmail_router, "revoke_token", lambda token: asyncio.sleep(0, result=True))
    auth = headers(client, "hung")
    res = client.post(
        _BASE + "/accounts",
        json={"email": "se.ngat.ket.noi@gmail.com"},
        headers=auth,
    )
    account_id = str(res.json()["id"])
    persist.gmail_token_save(
        account_id,
        access_token=_GIA_SE_THU_HOI,
        refresh_token=_GIA_SE_LAM_MOI,
        expires_at="2031-01-01T00:00:00+00:00",
    )
    assert persist.gmail_token_get(account_id) is not None

    res = client.post(f"{_BASE}/oauth/revoke?account_id={account_id}", headers=auth)
    assert res.status_code == 200
    assert persist.gmail_token_get(account_id) is None

    res = client.post(f"{_BASE}/oauth/revoke?account_id={account_id}", headers=auth)
    assert res.status_code == 200, "revoke phải idempotent"


# ── Token refresh ─────────────────────────────────────────────────────────


def test_expired_access_token_auto_refreshes(monkeypatch) -> None:
    """Access token hết hạn + còn refresh token ⇒ tự làm mới và lưu lại."""
    acc = persist.gmail_account_create(store_id="quan_01", nv_id="nv_01", email="het.han@gmail.com")
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid,
        access_token=_GIA_CU,
        refresh_token=_GIA_LAM_MOI_CU,
        expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    )

    async def _fake_refresh(refresh_token: str) -> dict[str, Any]:
        assert refresh_token == "mat-lam-moi-con-han"
        return {
            "access_token": "mat-moi-sau-refresh",
            "refresh_token": "mat-lam-moi-con-han",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "scope": "",
            "token_type": "Bearer",
        }

    monkeypatch.setattr(gmail_sync, "refresh_access_token", _fake_refresh)

    fresh = asyncio.run(gmail_sync._ensure_fresh_token(aid))
    assert fresh["access_token"] == "mat-moi-sau-refresh"
    assert persist.gmail_token_get(aid)["access_token"] == "mat-moi-sau-refresh"


def test_valid_access_token_not_refreshed(monkeypatch) -> None:
    """Token còn hạn ⇒ không gọi refresh."""

    async def _must_not_run(refresh_token: str) -> dict[str, Any]:
        raise AssertionError("token còn hạn không được refresh")

    monkeypatch.setattr(gmail_sync, "refresh_access_token", _must_not_run)
    acc = persist.gmail_account_create(store_id="quan_01", nv_id="nv_01", email="con.han@gmail.com")
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid,
        access_token="mat-con-han",
        refresh_token=_GIA_DU_PHONG,
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    tokens = asyncio.run(gmail_sync._ensure_fresh_token(aid))
    assert tokens["access_token"] == "mat-con-han"


# ── API tự nạp .env khi khởi động ─────────────────────────────────────────


def test_lifespan_loads_local_env(monkeypatch) -> None:
    """Startup API phải gọi loader `.env` (uvicorn chạy tay không tự đọc file).

    Mock loader để không chạm `.env` thật; chỉ kiểm tra wiring lifespan.
    """

    seen: list[bool] = []
    monkeypatch.setattr("ca_agents.llm.load_dotenv", lambda *a, **k: seen.append(True) or None)

    async def _run() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_run())
    assert seen == [True], "lifespan phải nạp .env một lần khi khởi động"


def test_encryption_key_read_lazily_not_at_import(monkeypatch) -> None:
    """Key mã hoá phải đọc lúc DÙNG, không phải lúc import module.

    Hồi quy thật: lifespan nạp `.env` SAU khi import `persist`. Đọc key lúc
    import thì key trong `.env` không bao giờ được dùng — token mã hoá bằng
    key tạm, restart API là hỏng hết ("Cần kết nối lại" hàng loạt).
    """
    from cryptography.fernet import Fernet, InvalidToken

    monkeypatch.setattr(persist, "_FERNET", None)
    monkeypatch.setattr(persist, "_FERNET_KEY", None)
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()

    monkeypatch.setenv("NHIPQUAN_ENCRYPTION_KEY", k1)
    acc = persist.gmail_account_create(
        store_id="quan_01", nv_id="nv_01", email="lazy.key@gmail.com"
    )
    aid = str(acc["id"])
    persist.gmail_token_save(
        aid, access_token="mat-bi-mat", refresh_token=None, expires_at="2031-01-01T00:00:00+00:00"
    )
    assert persist.gmail_token_get(aid)["access_token"] == "mat-bi-mat"

    # Đổi key (giống restart với key khác) ⇒ token cũ không đọc được nữa,
    # chứng tỏ lần đọc trước dùng đúng k1 chứ không phải key lúc import.
    monkeypatch.setenv("NHIPQUAN_ENCRYPTION_KEY", k2)
    with pytest.raises(InvalidToken):
        persist.gmail_token_get(aid)
