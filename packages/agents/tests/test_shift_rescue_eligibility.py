"""Shift Rescue eligibility tests (Phase 03)."""

from __future__ import annotations

from typing import Any

from ca_agents.ag_shift_rescue.eligibility import (
    BLOCK_REASONS,
    StaffProfile,
    eligibility_reasons,
    filter_eligible,
)

CA_META = {
    "ca_id": "t7_toi",
    "thu": "T7",
    "khung": "toi",
    "bat_dau": "17:00",
    "ket_thuc": "22:00",
}
REQUIRED = "pha_che"


def _staff(**over: object) -> StaffProfile:
    base: dict[str, Any] = {
        "nv_id": "nv_1",
        "ten": "NV 1",
        "ky_nang": {"pha_che", "phuc_vu"},
        "gio_da_lam": 20.0,
        "so_ca_tuan": 3,
    }
    base.update(over)
    return StaffProfile(**base)


def test_safe_candidate_empty_reasons() -> None:
    s = _staff()
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert reasons == []


def test_missing_skill_blocked() -> None:
    s = _staff(ky_nang={"phuc_vu"})
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert BLOCK_REASONS["SKILL"] in reasons


def test_shift_overlap_blocked_c03() -> None:
    s = _staff(
        ca_ids={"t7_toi_cu"},
        ca_meta={"t7_toi_cu": {"thu": "T7", "khung": "toi"}},
    )
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert BLOCK_REASONS["C03"] in reasons


def test_rest_minimum_blocked_c04() -> None:
    # Đã có ca liền trước chiều T7 → ca tối T7 vi phạm khoảng nghỉ (8h)
    s = _staff(
        ca_ids={"t7_chieu"},
        ca_meta={"t7_chieu": {"thu": "T7", "khung": "chieu"}},
    )
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=None,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert BLOCK_REASONS["C04"] in reasons


def test_weekly_cap_blocked_c05() -> None:
    s = _staff(gio_da_lam=46.0)
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=None,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert BLOCK_REASONS["C05"] in reasons


def test_self_not_safe() -> None:
    s = _staff()
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
        is_self=True,
    )
    assert BLOCK_REASONS["SELF"] in reasons


def test_nghi_phep_blocked_c06() -> None:
    s = _staff(nghi_phep_approved=True)
    reasons = eligibility_reasons(
        s,
        ca_meta=CA_META,
        required_skill=None,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert BLOCK_REASONS["C06"] in reasons


def test_filter_eligible_skips_absent_and_blocked() -> None:
    staff = [
        _staff(nv_id="nv_absent", ten="Absent"),
        _staff(nv_id="nv_safe", ten="Safe"),
        _staff(nv_id="nv_no_skill", ky_nang={"phuc_vu"}),
    ]
    safe = filter_eligible(
        staff,
        absence_nv_id="nv_absent",
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    ids = {s.nv_id for s in safe}
    assert "nv_absent" not in ids
    assert "nv_no_skill" not in ids
    assert "nv_safe" in ids


def test_no_safe_candidate_empty() -> None:
    staff = [_staff(nv_id="x1", ky_nang={"phuc_vu"})]
    safe = filter_eligible(
        staff,
        absence_nv_id="x0",
        ca_meta=CA_META,
        required_skill=REQUIRED,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    assert safe == []