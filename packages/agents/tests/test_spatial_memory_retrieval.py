"""Spatial memory retrieval tests (Phase 05)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ca_agents.ag_spatial_memory.retrieval import (
    MemoryRepository,
    retrieve_filtered,
)
from ca_contracts import (
    ExperienceMemory,
    MemoryConsentStatus,
    MemoryQuery,
    MemoryStatus,
    MemoryVisibility,
)
from ca_contracts.grand_experience import ExperienceRole


def _mem(memory_id: str, **over: object) -> ExperienceMemory:
    base: dict[str, Any] = {
        "memory_id": memory_id,
        "anchor_id": "bar",
        "owner_scope": "khach_1",
        "content": "khách thích ít ngọt",
        "consent_status": MemoryConsentStatus.GRANTED,
        "visibility": MemoryVisibility.STAFF,
        "status": MemoryStatus.CONFIRMED,
    }
    base.update(over)
    return ExperienceMemory(**base)


def _store(mems: list[ExperienceMemory]) -> MemoryRepository:
    s = MemoryRepository()
    for m in mems:
        s.add_memory(m)
    return s


def test_confirmed_memory_retrieved_in_scope() -> None:
    store = _store([_mem("m1")])
    q = MemoryQuery(store_id="quan_01", anchor_id="bar", status=MemoryStatus.CONFIRMED, requester_id="lan")
    out = retrieve_filtered(store, q)
    assert [m.memory_id for m in out] == ["m1"]


def test_pending_memory_not_in_confirmed_answer() -> None:
    store = _store([_mem("draft1", status=MemoryStatus.DRAFT)])
    q = MemoryQuery(store_id="quan_01", status=MemoryStatus.CONFIRMED, requester_id="lan")
    assert retrieve_filtered(store, q) == []


def test_revoked_memory_excluded() -> None:
    store = _store([_mem("rev", consent_status=MemoryConsentStatus.REVOKED, status=MemoryStatus.CONFIRMED)])
    q = MemoryQuery(store_id="quan_01", requester_id="lan")
    assert retrieve_filtered(store, q) == []


def test_deleted_memory_excluded() -> None:
    store = _store([_mem("del", status=MemoryStatus.DELETED)])
    q = MemoryQuery(store_id="quan_01", requester_id="lan")
    assert retrieve_filtered(store, q) == []


def test_retention_expired_excluded() -> None:
    store = _store([_mem("exp", retention_until=datetime.now(UTC) - timedelta(days=1))])
    q = MemoryQuery(store_id="quan_01", requester_id="lan")
    assert retrieve_filtered(store, q) == []


def test_customer_cannot_see_staff_private() -> None:
    store = _store([_mem("priv", visibility=MemoryVisibility.PRIVATE, owner_scope="nv_lan")])
    q_khach = MemoryQuery(store_id="quan_01", role=ExperienceRole.KHACH, requester_id="kh_1")
    q_manager = MemoryQuery(store_id="quan_01", role=ExperienceRole.QUAN_LY, requester_id="lan")
    assert retrieve_filtered(store, q_khach) == []
    assert len(retrieve_filtered(store, q_manager)) == 1


def test_customer_staff_visibility_hidden() -> None:
    store = _store([_mem("staff1", visibility=MemoryVisibility.STAFF)])
    q_khach = MemoryQuery(store_id="quan_01", role=ExperienceRole.KHACH, requester_id="kh_1")
    q_nv = MemoryQuery(store_id="quan_01", role=ExperienceRole.NHAN_VIEN, requester_id="nv_1")
    assert retrieve_filtered(store, q_khach) == []
    assert len(retrieve_filtered(store, q_nv)) == 1


def test_keyword_filter_bounded() -> None:
    store = _store([_mem("m1", content="khách thích ít ngọt"), _mem("m2", content="khách khen phục vụ")])
    q = MemoryQuery(store_id="quan_01", keyword="ngọt", requester_id="lan")
    out = retrieve_filtered(store, q)
    assert [m.memory_id for m in out] == ["m1"]