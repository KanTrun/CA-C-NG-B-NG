# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test bảo mật luồng OAuth Gmail — chống CSRF qua tham số `state`."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.gmail import _consume_oauth_state, _remember_oauth_state
from ca_api.interfaces.http.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

_BASE = "/api/v1/gmail"


def test_callback_rejects_missing_state() -> None:
    """Thiếu `state` ⇒ từ chối trước khi gọi Google (không đổi mã)."""
    res = client.post(
        _BASE + "/oauth/callback",
        json={"code": "ma-gia", "state": ""},
        headers=headers(client, "hung"),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "thieu_state_oauth"


def test_callback_rejects_forged_state() -> None:
    """`state` không do server sinh ⇒ từ chối (chống CSRF)."""
    res = client.post(
        _BASE + "/oauth/callback",
        json={"code": "ma-gia", "state": "state-do-ke-tan-cong-tu-nghi"},
        headers=headers(client, "hung"),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "state_oauth_khong_hop_le"


def test_state_is_single_use() -> None:
    """`state` dùng xong phải bị tiêu thụ — dùng lại lần hai thất bại."""
    _remember_oauth_state("state-dung-mot-lan", {"nv_id": "nv_01", "store_id": "quan_01"})
    owner = _consume_oauth_state("state-dung-mot-lan", "nv_01")  # lần 1 OK
    assert owner["nv_id"] == "nv_01"

    with pytest.raises(HTTPException) as err:
        _consume_oauth_state("state-dung-mot-lan", "nv_01")
    assert err.value.detail == "state_oauth_khong_hop_le"


def test_state_rejects_different_user() -> None:
    """`state` của người này không dùng được cho người khác."""
    _remember_oauth_state("state-cua-lan", {"nv_id": "nv_01", "store_id": "quan_01"})

    with pytest.raises(HTTPException) as err:
        _consume_oauth_state("state-cua-lan", "nv_03")
    assert err.value.detail == "state_oauth_sai_nguoi"


def test_state_expires() -> None:
    """`state` quá hạn 10 phút ⇒ từ chối."""
    from datetime import UTC, datetime, timedelta

    from ca_api.persist import kv_mutate

    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    kv_mutate(
        "gmail_oauth_states",
        lambda bag: {**bag, "state-het-han": {"nv_id": "nv_01", "deadline": past}},
        {},
    )

    with pytest.raises(HTTPException) as err:
        _consume_oauth_state("state-het-han", "nv_01")
    assert err.value.detail == "state_oauth_het_han"


def test_oauth_state_table_does_not_grow_forever() -> None:
    """Ghi state mới phải dọn state đã hết hạn, tránh phình kv."""
    from datetime import UTC, datetime, timedelta

    from ca_api.persist import kv_get

    _remember_oauth_state("state-cu-1", {"nv_id": "nv_01"})
    # Giả lập state cũ đã hết hạn.
    from ca_api.persist import kv_mutate

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    kv_mutate(
        "gmail_oauth_states",
        lambda b: {**b, "state-cu-1": {"nv_id": "nv_01", "deadline": past}},
        {},
    )

    _remember_oauth_state("state-moi", {"nv_id": "nv_01"})

    bag = kv_get("gmail_oauth_states", {})
    assert "state-cu-1" not in bag, "state hết hạn chưa được dọn"
    assert "state-moi" in bag
