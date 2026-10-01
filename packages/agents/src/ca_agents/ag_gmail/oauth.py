"""Gmail OAuth 2.0 flow management."""

# google-auth / googleapiclient không ship type stubs đầy đủ — tắt đúng mã lỗi
# no-untyped-call để không phải cast từng lời gọi thư viện.
# mypy: disable-error-code="no-untyped-call"

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

# Gmail API scopes needed for full management.
#
# CỐ Ý KHÔNG xin `gmail.settings.sharing`: scope đó cho phép đọc/thay đổi quyền
# chia sẻ hộp thư (delegate, chuyển quyền truy cập). Không endpoint, agent hay
# màn hình nào trong repo dùng tới (`service.py` chỉ chạm `sendAs`/filters —
# thuộc `gmail.settings.basic`). Đây là scope nhạy cảm bậc nhất của Gmail nên
# Google xét duyệt rất gắt khi publish app ⇒ xin thừa chỉ tăng rủi ro bị từ chối
# mà không mở thêm chức năng nào.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

# Google có thể trả về tập scope KHÁC tập đã xin:
#   - người dùng bỏ tick một vài quyền ở màn hình đồng ý (granular consent);
#   - lần kết nối lại sau khi ta thu hẹp scope, Google trả kèm scope cũ đã cấp
#     (`include_granted_scopes=true`).
# Mặc định oauthlib coi đó là lỗi và NÉM Warning trong `fetch_token` ⇒ token
# exchange đổ, người dùng chỉ thấy `doi_ma_oauth_that_bai` mà không hiểu vì sao.
# Ta chấp nhận đúng tập scope Google thực cấp (đã lưu vào DB) và để từng lời gọi
# API fail rõ ràng nếu thiếu quyền cụ thể.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# Bảng ký tự hợp lệ của PKCE `code_verifier` (RFC 7636 §4.1) — trùng alphabet mà
# chính google-auth-oauthlib dùng khi tự sinh, để hành vi không đổi.
_PKCE_ALPHABET = string.ascii_letters + string.digits + "-._~"


def new_pkce_verifier() -> str:
    """Sinh `code_verifier` cho PKCE (RFC 7636: 43–128 ký tự).

    Vì sao phải tự sinh và LƯU lại: `Flow` chỉ sinh verifier khi dựng
    authorization URL, còn callback là một HTTP request khác, dựng `Flow` MỚI.
    Nếu không mang verifier sang bước đổi mã thì Google nhận `code_challenge`
    lúc uỷ quyền mà không nhận `code_verifier` lúc đổi mã và trả `invalid_grant`
    — luồng OAuth không bao giờ hoàn tất.
    """
    return "".join(secrets.choice(_PKCE_ALPHABET) for _ in range(64))


@dataclass
class GmailOAuthConfig:
    """Gmail OAuth configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = field(default_factory=lambda: list(GMAIL_SCOPES))


def _get_config() -> GmailOAuthConfig:
    """Get OAuth config from environment."""
    client_id = os.environ.get("NHIPQUAN_GMAIL_CLIENT_ID")
    client_secret = os.environ.get("NHIPQUAN_GMAIL_CLIENT_SECRET")
    redirect_uri = os.environ.get("NHIPQUAN_GMAIL_REDIRECT_URI", "http://localhost:8000/api/v1/gmail/oauth/callback")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Gmail OAuth not configured. Set NHIPQUAN_GMAIL_CLIENT_ID and NHIPQUAN_GMAIL_CLIENT_SECRET"
        )

    return GmailOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


def _client_config(config: GmailOAuthConfig) -> dict[str, dict[str, Any]]:
    """Cấu hình client kiểu Google `client_secrets.json` (nhánh `web`)."""
    return {
        "web": {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uris": [config.redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _build_flow(config: GmailOAuthConfig, *, code_verifier: str | None) -> Flow:
    """Dựng `Flow` với PKCE đã định trước (hoặc tắt PKCE nếu không có verifier).

    `autogenerate_code_verifier` chỉ có tác dụng ở `authorization_url()`. Đặt
    theo `code_verifier` để hai nhánh luôn nhất quán: có verifier ⇒ URL mang
    `code_challenge`, không có ⇒ URL không mang, và lúc đổi mã cũng không gửi
    verifier. Lệch nhau giữa hai bước chính là lỗi `invalid_grant`.
    """
    return Flow.from_client_config(
        _client_config(config),
        scopes=config.scopes,
        redirect_uri=config.redirect_uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is not None,
    )


def build_authorization_url(
    *,
    state: str,
    access_type: str = "offline",
    prompt: str = "consent",
    code_verifier: str | None = None,
) -> str:
    """Build Google OAuth authorization URL.

    Truyền `code_verifier` (xem `new_pkce_verifier`) để bật PKCE; khi đó BẮT BUỘC
    lưu verifier lại và truyền tiếp vào `exchange_code_for_tokens`, nếu không
    Google sẽ từ chối ở bước đổi mã.
    """
    config = _get_config()
    flow = _build_flow(config, code_verifier=code_verifier)

    auth_url, _ = flow.authorization_url(
        access_type=access_type,
        prompt=prompt,
        state=state,
        include_granted_scopes="true",
    )
    return cast(str, auth_url)


async def exchange_code_for_tokens(code: str, *, code_verifier: str | None = None) -> dict[str, Any]:
    """Exchange authorization code for access/refresh tokens.

    `code_verifier` phải ĐÚNG BẰNG giá trị đã dùng khi dựng authorization URL.
    """
    config = _get_config()
    flow = _build_flow(config, code_verifier=code_verifier)

    flow.fetch_token(code=code)
    credentials = flow.credentials

    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "expires_at": credentials.expiry.isoformat() if credentials.expiry else "",
        "scope": " ".join(credentials.scopes) if credentials.scopes else "",
        "token_type": "Bearer",
    }


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh access token using refresh token."""
    config = _get_config()

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.client_id,
        client_secret=config.client_secret,
        scopes=config.scopes,
    )

    request = Request()
    credentials.refresh(request)

    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "expires_at": credentials.expiry.isoformat() if credentials.expiry else "",
        "scope": " ".join(credentials.scopes) if credentials.scopes else "",
        "token_type": "Bearer",
    }


async def revoke_token(access_token: str) -> bool:
    """Revoke access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": access_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    return response.status_code == 200


def create_credentials(access_token: str, refresh_token: str | None, scopes: list[str] | None = None) -> Credentials:
    """Create Google Credentials object from tokens."""
    config = _get_config()
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.client_id,
        client_secret=config.client_secret,
        scopes=scopes or config.scopes,
    )