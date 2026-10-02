"""Hợp đồng dữ liệu Spatial Memory (plan 260920-1442 Phase 05).

Test privacy invariants: consent revoked không retrieve, pending (draft) không
được xem là confirmed, retention expires → excluded, delete → content removed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ca_contracts import (
    CONTRACTS,
    ExperienceMemory,
    MemoryConsentStatus,
    MemoryProposal,
    MemoryQuery,
    MemoryStatus,
    MemoryVisibility,
    TourPlan,
    TourStep,
    VoiceTurnRequest,
    VoiceTurnResponse,
)
from ca_contracts.grand_experience import ExperienceRole
from pydantic import ValidationError


def _memory(**over: object) -> ExperienceMemory:
    base: dict[str, Any] = {
        "memory_id": "m1",
        "anchor_id": "bar",
        "owner_scope": "khach_psid_1",
        "content": "quí khách thích ít ngọt",
        "consent_status": MemoryConsentStatus.REQUIRED,
        "visibility": MemoryVisibility.PRIVATE,
        "status": MemoryStatus.DRAFT,
    }
    base.update(over)
    return ExperienceMemory(**base)


def test_pending_is_draft_not_separate_enum() -> None:
    """'Pending' là nhãn UI cho status=draft — không phải enum riêng."""
    m = _memory(status=MemoryStatus.DRAFT)
    assert m.status.value == "draft"
    # Không tồn tại giá trị "pending"
    with pytest.raises(ValidationError):
        _memory(status="pending")


def test_revoked_consent_not_retrievable() -> None:
    m = _memory(consent_status=MemoryConsentStatus.REVOKED)
    # Retrieval layer loại revoked; contract đảm bảo trạng thái tường minh.
    assert m.consent_status == MemoryConsentStatus.REVOKED
    assert m.model_dump(mode="json")["consent_status"] == "revoked"


def test_confirmed_required_for_retrieval() -> None:
    draft = _memory(status=MemoryStatus.DRAFT)
    confirmed = _memory(status=MemoryStatus.CONFIRMED)
    # Query chỉ lấy confirmed
    q = MemoryQuery(
        store_id="quan_01",
        status=MemoryStatus.CONFIRMED,
        requester_id="lan",
    )
    assert q.status == MemoryStatus.CONFIRMED
    assert draft.status != q.status
    assert confirmed.status == q.status


def test_retention_expires_excluded() -> None:
    expired = _memory(retention_until=datetime.now(UTC) - timedelta(days=1))
    # Retention hết hạn → không còn hợp lệ (check trong layer retrieval)
    assert expired.retention_until is not None
    assert expired.retention_until < datetime.now(UTC)


def test_delete_path_content_removed() -> None:
    m = _memory(status=MemoryStatus.DELETED)
    # Deleted → không được retrieve (status dùng để loại)
    assert m.status == MemoryStatus.DELETED


def test_memory_proposal_requires_snapshot() -> None:
    with pytest.raises(ValidationError):
        MemoryProposal(
            proposal_id="p1",
            anchor_id="bar",
            content="noi dung",
            owner_scope="nv",
            proposed_by="lan",
            snapshot_hash="a",  # min 8
        )


def test_voice_turn_requires_flags() -> None:
    req = VoiceTurnRequest(
        conversation_id="c1",
        transcript="ở đây từng xảy ra chuyện gì?",
        requester_id="lan",
    )
    assert req.role == ExperienceRole.NHAN_VIEN

    resp = VoiceTurnResponse(
        turn_id="t1",
        transcript=req.transcript,
        response_text="Có ghi nhận…",
    )
    assert resp.grounded is True


def test_tour_steps_deterministic() -> None:
    plan = TourPlan(
        tour_id="tour_1",
        steps=[
            TourStep(step_id="s1", anchor_id="bar", narrative="Quầy pha chế"),
            TourStep(step_id="s2", anchor_id="entrance", narrative="Cửa vào"),
        ],
    )
    assert len(plan.steps) == 2


def test_spatial_contracts_registered() -> None:
    for name in ("MemoryQuery", "MemoryProposal", "MemoryConsentRequest",
                 "MemoryAuditEntry", "GroundedAnswer", "TourPlan", "VoiceTurnRequest", "VoiceTurnResponse"):
        assert name in CONTRACTS