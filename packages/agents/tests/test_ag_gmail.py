# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests for Gmail management module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ca_agents.ag_gmail.models import (
    GmailAccount,
    GmailFilter,
    GmailLabel,
    GmailMessage,
    GmailSyncState,
    GmailThread,
)
from ca_agents.ag_gmail.oauth import (
    GmailOAuthConfig,
    build_authorization_url,
    create_credentials,
    exchange_code_for_tokens,
    refresh_access_token,
    revoke_token,
)
from ca_agents.ag_gmail.service import GmailService

# Chuỗi giả — KHÔNG phải bí mật. Đặt tên FAKE_* để scanner secret của repo
# không gắn cờ nhầm pattern `token = "..."`.
FAKE_ACCESS = "gia-tri-kiem-thu-khong-phai-that-01"
FAKE_REFRESH = "gia-tri-kiem-thu-khong-phai-that-02"
FAKE_NEW_ACCESS = "gia-tri-kiem-thu-khong-phai-that-03"
FAKE_NEW_REFRESH = "gia-tri-kiem-thu-khong-phai-that-04"


class TestGmailOAuthConfig:
    """Tests for GmailOAuthConfig."""

    def test_default_scopes(self):
        config = GmailOAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )
        assert config.scopes is not None
        assert len(config.scopes) == 5
        assert "https://www.googleapis.com/auth/gmail.readonly" in config.scopes
        assert "https://www.googleapis.com/auth/gmail.send" in config.scopes

    def test_khong_xin_scope_chia_se_hop_thu(self):
        """`gmail.settings.sharing` cho phép đổi quyền chia sẻ hộp thư (delegate).

        Không endpoint/agent nào trong repo dùng ⇒ không được xin: đây là scope
        nhạy cảm khiến Google xét duyệt gắt khi publish app.
        """
        config = GmailOAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )
        assert "https://www.googleapis.com/auth/gmail.settings.sharing" not in config.scopes
        assert "https://www.googleapis.com/auth/gmail.settings.basic" in config.scopes

    def test_custom_scopes(self):
        config = GmailOAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        assert config.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


class TestGmailModels:
    """Tests for Gmail data models."""

    def test_gmail_account_creation(self):
        account = GmailAccount(
            id="gmail_abc123",
            store_id="quan_01",
            nv_id="nv_01",
            email="test@gmail.com",
            display_name="Test User",
            is_primary=True,
            is_active=True,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert account.id == "gmail_abc123"
        assert account.email == "test@gmail.com"
        assert account.is_primary is True

    def test_gmail_message_creation(self):
        message = GmailMessage(
            id="msg_123",
            account_id="gmail_abc123",
            thread_id="thread_456",
            label_ids=["INBOX", "UNREAD"],
            snippet="Test message",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            cc_emails=[],
            subject="Test Subject",
            body_text="Test body",
            body_html="<p>Test body</p>",
            internal_date="2024-01-01T12:00:00Z",
            is_read=False,
            is_starred=False,
            has_attachment=False,
        )
        assert message.id == "msg_123"
        assert message.thread_id == "thread_456"
        assert "UNREAD" in message.label_ids
        assert message.is_read is False

    def test_gmail_label_creation(self):
        label = GmailLabel(
            id="Label_1",
            account_id="gmail_abc123",
            name="Important",
            label_type="user",
            message_list_visibility="show",
            label_list_visibility="labelShow",
            color_background="#ff0000",
            color_text="#ffffff",
            total_messages=10,
            unread_messages=2,
            updated_at="2024-01-01T00:00:00Z",
        )
        assert label.name == "Important"
        assert label.color_background == "#ff0000"

    def test_gmail_filter_creation(self):
        filter_obj = GmailFilter(
            id="filter_1",
            account_id="gmail_abc123",
            criteria={"from": "test@example.com"},
            action={"addLabelIds": ["Label_1"]},
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert filter_obj.criteria == {"from": "test@example.com"}
        assert filter_obj.action == {"addLabelIds": ["Label_1"]}

    def test_gmail_sync_state_creation(self):
        sync_state = GmailSyncState(
            account_id="gmail_abc123",
            last_history_id="12345",
            last_sync_at="2024-01-01T00:00:00Z",
            sync_cursor="cursor_123",
            total_messages=100,
            unread_count=5,
            updated_at="2024-01-01T00:00:00Z",
        )
        assert sync_state.last_history_id == "12345"
        assert sync_state.total_messages == 100

    def test_gmail_thread_creation(self):
        thread = GmailThread(
            id="thread_123",
            account_id="gmail_abc123",
            message_ids=["msg_1", "msg_2"],
            subject="Test Thread",
            participants=["a@example.com", "b@example.com"],
            last_message_date="2024-01-01T12:00:00Z",
            is_unread=True,
            label_ids=["INBOX"],
        )
        assert thread.id == "thread_123"
        assert len(thread.message_ids) == 2
        assert thread.is_unread is True


class TestGmailService:
    """Tests for GmailService."""

    @pytest.fixture
    def mock_credentials(self):
        creds = MagicMock()
        creds.token = FAKE_ACCESS
        creds.refresh_token = FAKE_REFRESH
        creds.expiry = None
        creds.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        return creds

    @pytest.fixture
    def mock_service(self, mock_credentials):
        with patch("ca_agents.ag_gmail.service.build") as mock_build:
            with patch.dict("os.environ", {
                "NHIPQUAN_GMAIL_CLIENT_ID": "test_client_id",
                "NHIPQUAN_GMAIL_CLIENT_SECRET": "test_client_secret",
            }):
                mock_service = MagicMock()
                mock_build.return_value = mock_service
                service = GmailService(FAKE_ACCESS, FAKE_REFRESH)
                yield service, mock_service

    def test_parse_message(self, mock_service):
        service, _ = mock_service
        raw_message = {
            "id": "msg_123",
            "threadId": "thread_456",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "Test snippet",
            "internalDate": "1704110400000",  # 2024-01-01T12:00:00Z in ms
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                ],
                "mimeType": "text/plain",
                "body": {"data": "VGVzdCBib2R5"},  # "Test body" in base64
            },
        }
        parsed = GmailService.parse_message(raw_message)
        assert parsed.id == "msg_123"
        assert parsed.thread_id == "thread_456"
        assert parsed.from_email == "sender@example.com"
        assert parsed.to_emails == ["recipient@example.com"]
        assert parsed.subject == "Test Subject"
        assert parsed.body_text == "Test body"
        assert parsed.is_read is False  # UNREAD in labels
        assert parsed.is_starred is False

    def test_parse_label(self, mock_service):
        service, _ = mock_service
        raw_label = {
            "id": "Label_1",
            "name": "Important",
            "type": "user",
            "messageListVisibility": "show",
            "labelListVisibility": "labelShow",
            "color": {"backgroundColor": "#ff0000", "textColor": "#ffffff"},
            "messagesTotal": 10,
            "messagesUnread": 2,
        }
        parsed = GmailService.parse_label(raw_label, "gmail_abc123")
        assert parsed.id == "Label_1"
        assert parsed.account_id == "gmail_abc123"
        assert parsed.name == "Important"
        assert parsed.color_background == "#ff0000"
        assert parsed.total_messages == 10

    def test_parse_filter(self, mock_service):
        service, _ = mock_service
        raw_filter = {
            "id": "filter_1",
            "criteria": {"from": "test@example.com"},
            "action": {"addLabelIds": ["Label_1"]},
        }
        parsed = GmailService.parse_filter(raw_filter, "gmail_abc123")
        assert parsed.id == "filter_1"
        assert parsed.account_id == "gmail_abc123"
        assert parsed.criteria == {"from": "test@example.com"}
        assert parsed.action == {"addLabelIds": ["Label_1"]}


class TestOAuthFunctions:
    """Tests for OAuth functions (mocked)."""

    @patch.dict("os.environ", {
        "NHIPQUAN_GMAIL_CLIENT_ID": "test_client_id",
        "NHIPQUAN_GMAIL_CLIENT_SECRET": "test_client_secret",
        "NHIPQUAN_GMAIL_REDIRECT_URI": "http://localhost/callback",
    })
    def test_build_authorization_url(self) -> None:
        url = build_authorization_url(state="test_state")
        assert "accounts.google.com/o/oauth2/auth" in url
        assert "client_id=test_client_id" in url
        assert "state=test_state" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    @patch.dict("os.environ", {
        "NHIPQUAN_GMAIL_CLIENT_ID": "test_client_id",
        "NHIPQUAN_GMAIL_CLIENT_SECRET": "test_client_secret",
        "NHIPQUAN_GMAIL_REDIRECT_URI": "http://localhost/callback",
    })
    @patch("ca_agents.ag_gmail.oauth.Flow.from_client_config")
    def test_exchange_code_for_tokens(self, mock_flow_class) -> None:
        mock_flow = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = FAKE_ACCESS
        mock_credentials.refresh_token = FAKE_REFRESH
        mock_credentials.expiry = None
        mock_credentials.scopes = ["scope1", "scope2"]
        mock_flow.credentials = mock_credentials
        mock_flow_class.return_value = mock_flow

        result = asyncio.run(exchange_code_for_tokens("ma_uuy_quyen_gia"))
        assert result["access_token"] == FAKE_ACCESS
        assert result["refresh_token"] == FAKE_REFRESH
        assert result["scope"] == "scope1 scope2"
        assert result["token_type"] == "Bearer"

    @patch.dict("os.environ", {
        "NHIPQUAN_GMAIL_CLIENT_ID": "test_client_id",
        "NHIPQUAN_GMAIL_CLIENT_SECRET": "test_client_secret",
        "NHIPQUAN_GMAIL_REDIRECT_URI": "http://localhost/callback",
    })
    @patch("ca_agents.ag_gmail.oauth.Credentials")
    @patch("ca_agents.ag_gmail.oauth.Request")
    def test_refresh_access_token(self, mock_request_class, mock_credentials_class) -> None:
        mock_credentials = MagicMock()
        mock_credentials.token = FAKE_NEW_ACCESS
        mock_credentials.refresh_token = FAKE_NEW_REFRESH
        mock_credentials.expiry = None
        mock_credentials.scopes = ["scope1"]
        mock_credentials_class.return_value = mock_credentials

        result = asyncio.run(refresh_access_token("refresh_gia_cu"))
        assert result["access_token"] == FAKE_NEW_ACCESS
        assert result["refresh_token"] == FAKE_NEW_REFRESH
        mock_credentials.refresh.assert_called_once()

    @patch("ca_agents.ag_gmail.oauth.httpx.AsyncClient")
    def test_revoke_token(self, mock_client_class) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = asyncio.run(revoke_token(FAKE_ACCESS))
        assert result is True
        mock_client.post.assert_called_once_with(
            "https://oauth2.googleapis.com/revoke",
            params={"token": FAKE_ACCESS},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def test_create_credentials(self):
        with patch.dict("os.environ", {
            "NHIPQUAN_GMAIL_CLIENT_ID": "test_client_id",
            "NHIPQUAN_GMAIL_CLIENT_SECRET": "test_client_secret",
        }):
            creds = create_credentials(FAKE_ACCESS, FAKE_REFRESH, ["scope1"])
            assert creds.token == FAKE_ACCESS
            assert creds.refresh_token == FAKE_REFRESH
            assert creds.client_id == "test_client_id"
            assert creds.client_secret == "test_client_secret"
            assert creds.scopes == ["scope1"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])