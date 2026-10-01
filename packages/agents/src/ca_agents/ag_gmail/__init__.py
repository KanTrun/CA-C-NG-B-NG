"""Gmail management module — OAuth, service, models.

Lưu ý kiến trúc: phần đồng bộ cần ghi DB nằm ở `ca_api.services.gmail_sync`,
KHÔNG ở đây — gate `test_architecture` cấm package agents import `ca_api`.
"""

from __future__ import annotations

from ca_agents.ag_gmail.models import (
    GmailAccount,
    GmailFilter,
    GmailLabel,
    GmailMessage,
    GmailOAuthTokens,
    GmailSyncState,
    GmailThread,
)
from ca_agents.ag_gmail.oauth import (
    GmailOAuthConfig,
    build_authorization_url,
    create_credentials,
    exchange_code_for_tokens,
    new_pkce_verifier,
    refresh_access_token,
    revoke_token,
)
from ca_agents.ag_gmail.service import GmailService

__all__ = [
    "GmailAccount",
    "GmailFilter",
    "GmailLabel",
    "GmailMessage",
    "GmailOAuthConfig",
    "GmailOAuthTokens",
    "GmailService",
    "GmailSyncState",
    "GmailThread",
    "build_authorization_url",
    "create_credentials",
    "exchange_code_for_tokens",
    "new_pkce_verifier",
    "refresh_access_token",
    "revoke_token",
]
