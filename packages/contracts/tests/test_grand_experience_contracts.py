"""Hợp đồng dữ liệu — Grand AI Experience Portfolio (plan 260920-1442 Phase 01).

Kiểm tra valid, invalid, stale, unauthorized, revoked payloads + fail-closed
tại write boundary + replay determinism (không mở mạng).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ca_contracts import (
    CONTRACTS,
    ExperienceActionProposal,
    ExperienceCapability,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceMemory,
    ExperienceProposalStatus,
    ExperienceRole,
    LivingCafeSnapshot,
    MemoryConsentStatus,
    MemoryStatus,
    MemoryVisibility,
    SpatialAnchor,
    VoiceTurn,
    WarRoomOption,
    WarRoomScenario,
    experience_capabilities_for_role,
    experience_role_can,
)
from pydantic import ValidationError

# ── Helpers ───────────────────────────────────────────────────────────────────


def _utc(offset_hours: float = -1.0) -> datetime:
    return datetime.now(UTC) + timedelta(hours=offset_hours)


def _valid_event(**over: object) -> ExperienceEvent:
    data: dict[str, Any] = {
        "event_id": "evt_001",
        "event_type": ExperienceEventType.INCIDENT.value,
        "occurred_at": _utc(),
        "actor_id": "nv_quan",
        "role": ExperienceRole.NHAN_VIEN,
        "anchor_id": "bar",
        "payload": {"loai": "vo_ly"},
        "evidence_refs": ["ev_1"],
        "source": "user",
    }
    data.update(over)
    return ExperienceEvent(**data)


# ── Event / anchor ────────────────────────────────────────────────────────────


def test_valid_event_accepted_and_replayable() -> None:
    ev = _valid_event()
    assert ev.event_id == "evt_001"
    assert ev.anchor_id == "bar"
    assert ev.source == "user"
    # Tái serialize byte-deterministic — replay so sánh theo hash
    assert ExperienceEvent.model_validate(ev.model_dump(mode="json")) == ev


def test_unknown_event_type_rejected_write_boundary() -> None:
    with pytest.raises(ValidationError):
        _valid_event(event_type="khong_tontai")


def test_malformed_event_id_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_event(event_id="")


def test_malformed_timestamp_rejected() -> None:
    base = _valid_event().model_dump(mode="json")
    base["occurred_at"] = "khong_phai_iso"
    with pytest.raises(ValidationError):
        ExperienceEvent.model_validate(base)


def test_actor_optional_but_role_scope_preserved() -> None:
    ev = _valid_event(actor_id=None, role=None, anchor_id=None)
    assert ev.actor_id is None
    assert ev.role is None


def test_anchor_bounds_checked() -> None:
    with pytest.raises(ValidationError):
        SpatialAnchor(
            anchor_id="blender-02",
            khu_vuc="bar",
            label="Máy xay",
            x=5000.0,
            y=0.0,
            kind="thiet_bi",
        )


# ── Voice turn ────────────────────────────────────────────────────────────────


def test_voice_turn_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        VoiceTurn(
            turn_id="t1",
            conversation_id="c1",
            transcript="xin chao",
            confidence=1.5,
        )


def test_voice_turn_defaults() -> None:
    vt = VoiceTurn(turn_id="t1", conversation_id="c1", transcript="xin chao")
    assert vt.confidence == 0.0
    assert vt.intent is None


# ── Memory / consent ──────────────────────────────────────────────────────────


def test_memory_requires_consent_fields() -> None:
    m = ExperienceMemory(
        memory_id="m1",
        owner_scope="khach_psid_1",
        content="thich it ngot",
    )
    # consent mặc định required — không bao giờ ngầm định là granted
    assert m.consent_status == MemoryConsentStatus.REQUIRED
    assert m.status == MemoryStatus.DRAFT
    assert m.visibility == MemoryVisibility.STAFF


def test_consent_revoked_excluded_from_retrieval() -> None:
    m = ExperienceMemory(
        memory_id="m1",
        owner_scope="khach_psid_1",
        content="thich it ngot",
        consent_status=MemoryConsentStatus.REVOKED,
    )
    # Retrieval layer (Phase 05) bỏ qua revoked; đây là invariant ở contract:
    # revoked phải được biểu diễn tường minh.
    assert m.consent_status == MemoryConsentStatus.REVOKED
    assert m.model_dump(mode="json")["consent_status"] == "revoked"


def test_memory_status_is_closed_set() -> None:
    with pytest.raises(ValidationError):
        ExperienceMemory(
            memory_id="m1",
            owner_scope="abc",
            content="x",
            status="cho_xac_nhan",  # type: ignore[arg-type]  # chỉ draft/confirmed/superseded/deleted
        )


def test_memory_retention_optional() -> None:
    m = ExperienceMemory(memory_id="m1", owner_scope="abc", content="x")
    assert m.retention_until is None


# ── Proposal ──────────────────────────────────────────────────────────────────


def test_proposal_requires_snapshot_hash() -> None:
    with pytest.raises(ValidationError):
        ExperienceActionProposal(
            proposal_id="p1",
            action_type="memory_confirm",
            snapshot_hash="a",  # min_length=8
            requested_by="quan",
            evidence_refs=["ev_1"],
        )


def test_proposal_default_status_draft() -> None:
    p = ExperienceActionProposal(
        proposal_id="p1",
        action_type="memory_confirm",
        snapshot_hash="snap1234",
        requested_by="quan",
        evidence_refs=["ev_1"],
    )
    assert p.status == ExperienceProposalStatus.DRAFT


def test_proposal_fail_closed_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        ExperienceActionProposal(
            proposal_id="p1",
            action_type="memory_confirm",
            snapshot_hash="snap1234",
            requested_by="quan",
            evidence_refs=[],  # fail-closed: ít nhất một bằng chứng
        )


# ── Capability policy (fail-closed) ───────────────────────────────────────────


def test_capability_matrix_read_all_roles() -> None:
    for role in ExperienceRole:
        assert ExperienceCapability.READ.value in experience_capabilities_for_role(role)


def test_capability_simulate_manager_only() -> None:
    assert ExperienceCapability.SIMULATE.value not in experience_capabilities_for_role(
        ExperienceRole.NHAN_VIEN
    )
    assert ExperienceCapability.SIMULATE.value not in experience_capabilities_for_role(
        ExperienceRole.KHACH
    )
    assert ExperienceCapability.SIMULATE.value in experience_capabilities_for_role(
        ExperienceRole.QUAN_LY
    )
    assert ExperienceCapability.SIMULATE.value in experience_capabilities_for_role(
        ExperienceRole.CHU_QUAN
    )


def test_capability_confirm_manager_only() -> None:
    assert not experience_role_can(ExperienceRole.NHAN_VIEN, ExperienceCapability.CONFIRM.value)
    assert experience_role_can(ExperienceRole.CHU_QUAN, ExperienceCapability.CONFIRM.value)


def test_unknown_role_fail_closed() -> None:
    assert experience_capabilities_for_role("khong_biet") == frozenset()
    assert not experience_role_can("khong_biet", ExperienceCapability.READ.value)


# ── War Room (Phase 02 contracts sớm giữ invariant) ───────────────────────────


def test_war_room_scenario_closed_enum() -> None:
    with pytest.raises(ValidationError):
        WarRoomScenario(
            scenario_id="s1",
            loai="phan_tich_thi_truong",  # type: ignore[arg-type]  # lạ
        )


def test_war_room_option_labels_estimate_marked() -> None:
    opt = WarRoomOption(
        option_id="o1",
        scenario_id="s1",
        input_assumptions={"so_nguoi": 3},
        outputs={"doanh_thu": 1000.0},
        labels=["mo_phong"],
    )
    assert opt.labels == ["mo_phong"]


def test_war_room_option_rejects_unknown_label() -> None:
    with pytest.raises(ValidationError):
        WarRoomOption(
            option_id="o1",
            scenario_id="s1",
            labels=["thuc_te"],  # type: ignore[list-item]  # chỉ "mo_phong"|"uoc_tinh"
        )


# ── Registry + TS export ──────────────────────────────────────────────────────


def test_contracts_registered() -> None:
    for name in (
        "SpatialAnchor",
        "ExperienceEvent",
        "VoiceTurn",
        "ExperienceMemory",
        "ExperienceActionProposal",
        "WarRoomScenario",
        "WarRoomOption",
        "WarRoomComparison",
        "RuleCandidate",
        "ShadowTestResult",
        "RescueCandidate",
        "RescueCase",
        "LivingCafeSnapshot",
    ):
        assert name in CONTRACTS, f"{name} phải có trong CONTRACTS registry"


def test_living_snapshot_role_required() -> None:
    with pytest.raises(ValidationError):
        LivingCafeSnapshot(snapshot_id="s1", store_id="quan_01")  # type: ignore[call-arg]  # thiếu role


def test_living_snapshot_valid() -> None:
    snap = LivingCafeSnapshot(snapshot_id="s1", store_id="quan_01", role=ExperienceRole.CHU_QUAN)
    assert snap.zones == []
    assert snap.data_quality == []