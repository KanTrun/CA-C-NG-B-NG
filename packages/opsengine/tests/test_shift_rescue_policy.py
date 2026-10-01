"""Shift Rescue policy state machine tests (opsengine, Phase 03)."""

from __future__ import annotations

import pytest
from ca_ops.shift_rescue_policy import (
    RescueCaseState,
    RescueState,
)


def _case() -> RescueCaseState:
    c = RescueCaseState(case_id="c1", schedule_snapshot_hash="snap_1234abcd")
    c.transition(RescueState.RESOLVING, actor="quan_ly_test")
    c.transition(RescueState.CANDIDATES_READY, actor="quan_ly_test")
    return c


def test_full_lifecycle() -> None:
    c = _case()
    c.transition(RescueState.PROPOSED, actor="quan_ly_test")
    c.invite(["nv_1", "nv_2"], actor="quan_ly_test")
    assert c.state is RescueState.INVITED
    assert c.invited_candidates == ["nv_1", "nv_2"]
    c.respond("nv_1", accept=True, actor="nv_1")
    state_after: RescueState = c.state
    assert state_after is RescueState.RESPONDED
    c.confirm("nv_1", actor="quan_ly_test")
    state_confirmed: RescueState = c.state
    assert state_confirmed is RescueState.CONFIRMED
    assert c.confirmed_candidate_id == "nv_1"


def test_invalid_transition_rejected() -> None:
    c = RescueCaseState(case_id="c2")
    with pytest.raises(ValueError):
        c.confirm("nv_1", actor="x")  # REPORTED → CONFIRMED không hợp lệ


def test_invite_idempotent_no_duplicate() -> None:
    c = _case()
    c.transition(RescueState.PROPOSED, actor="x")
    c.invite(["nv_1"], actor="x")
    before = list(c.invited_candidates)
    # gọi lại invite cùng id → không thêm trùng
    c.invite(["nv_1"], actor="x")
    assert c.invited_candidates == before


def test_invite_requires_proposed() -> None:
    c = _case()  # đang CANDIDATES_READY
    with pytest.raises(ValueError):
        c.invite(["nv_1"], actor="x")


def test_reject_keeps_state() -> None:
    c = _case()
    c.transition(RescueState.PROPOSED, actor="x")
    c.invite(["nv_1", "nv_2"], actor="x")
    c.respond("nv_1", accept=False, actor="nv_1")
    # vẫn INVITED (chờ ứng viên khác)
    assert c.state == RescueState.INVITED
    assert c.responded_candidate_id == "nv_1"


def test_expire_locked() -> None:
    c = _case()
    c.transition(RescueState.PROPOSED, actor="x")
    c.expire()
    assert c.state == RescueState.EXPIRED
    # Confirm sau expire phải từ chối
    with pytest.raises(ValueError):
        c.confirm("nv_1", actor="x")