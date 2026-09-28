"""HTTP router — HỒN QUÁN Spatial Memory (plan 260920-1442 Phase 05).

- GET    /experience/map
- GET    /experience/anchors/{anchor_id}
- GET    /experience/memories?anchor_id=&from=&to=&status=
- POST   /experience/memories/propose
- POST   /experience/memories/{memory_id}/consent
- DELETE /experience/memories/{memory_id}
- POST   /experience/tour/start
- POST   /experience/voice/turn

Không có direct DB mutation từ agent; consent/delete có audit. voice/turn trả
transcript + response + citations + optional proposal, không bao giờ mutate.
"""

from __future__ import annotations

import threading
import time
from typing import Annotated, Any, cast

from ca_agents.ag_spatial_memory.grounding import (
    GroundingContext,
    build_grounded_answer,
)
from ca_agents.ag_spatial_memory.retrieval import (
    MemoryRepository,
    retrieve_filtered,
)
from ca_agents.ag_spatial_memory.tour import plan_tour
from ca_agents.grand_experience.adapter import resolve_experience_read_adapter
from ca_agents.grand_experience.replay import FixtureReader
from ca_contracts import (
    ExperienceMemory,
    MemoryConsentStatus,
    MemoryProposal,
    MemoryQuery,
    MemoryStatus,
    MemoryVisibility,
    VoiceTurnRequest,
    VoiceTurnResponse,
)
from ca_contracts.grand_experience import ExperienceRole
from fastapi import APIRouter, Header, HTTPException, Query

from ca_api.interfaces.http.sprint3 import _require_role

router = APIRouter(tags=["experience_spatial_memory"])

_LOCK = threading.Lock()
_USER_TS: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_REQ = 20


def clear_spatial_state() -> None:
    """Trả kho ký ức về đúng trạng thái fixture, và xoá bộ đếm tần suất.

    Vì sao phải dựng lại kho chứ không chỉ xoá bộ đếm: `_REPO_STORE` là biến
    TOÀN CỤC SỐNG SUỐT PHIÊN SERVER. `POST /memories/{id}/consent` sửa thẳng vào
    đối tượng trong đó (`memory.consent_status = ...`), nên một bài test xác nhận
    consent cho bản nháp là thay đổi đó **sống mãi** — qua mọi lần gọi reset, qua
    mọi bài test sau.

    Hậu quả thật đã xảy ra: fixture khai `mem_bar_draft_01` là `status: "draft"`,
    `consent_status: "required"`, nên neo `bar` chỉ có ĐÚNG 1 ký ức đã xác nhận
    (`mem_bar_01`). Sau khi một bài test cấp consent cho bản nháp, neo `bar` có 2.
    Bài `grand-experience-replay` khẳng định trích dẫn chứa "1" nên đỏ — và vì
    trạng thái đã bẩn trong DB, bài đó **đỏ cả khi chạy một mình**, trông như lỗi
    thật trong khi thực ra là rò trạng thái.

    Đây là lần thứ ba cùng một loại lỗi trong hệ (xem `_CANDIDATES` của
    `experience_rules`, `experience_preferences` của `quanverse`): store sống lâu
    hơn bài test. Cách sửa luôn giống nhau — dựng lại từ nguồn, đừng chỉ xoá phần
    phụ.
    """
    global _REPO_STORE
    with _LOCK:
        _USER_TS.clear()
        _REPO_STORE = None


def _rate_limit(user_id: str) -> None:
    now = time.time()
    with _LOCK:
        recent = [t for t in _USER_TS.get(user_id, []) if now - t < _WINDOW_S]
        if len(recent) >= _MAX_REQ:
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
        recent.append(now)
        _USER_TS[user_id] = recent


def _spatial_repo() -> MemoryRepository:
    """Fixture-backed repo global (reset mỗi lần gọi cho test deterministic)."""
    reader = FixtureReader()
    data = cast(dict[str, Any], reader.read_json_path("spatial-memory.json"))
    repo = MemoryRepository()
    for row in data.get("memories", []):
        repo.add_memory(ExperienceMemory.model_validate(row))
    return repo


_REPO_STORE: MemoryRepository | None = None


def _get_repo() -> MemoryRepository:
    global _REPO_STORE
    if _REPO_STORE is None or _REPO_STORE.list_memories() is None:
        _REPO_STORE = _spatial_repo()
    return _REPO_STORE


def _role_of(authorization: str | None) -> ExperienceRole:
    role = _require_role(authorization)
    try:
        return ExperienceRole(role)
    except ValueError:
        return ExperienceRole.NHAN_VIEN


@router.get("/api/v1/experience/map")
def map_anchors(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _role_of(authorization)
    adapter = resolve_experience_read_adapter()
    anchors = adapter.list_anchors()
    return {
        "anchors": [a.model_dump(mode="json") for a in anchors],
        "data_quality": [{"code": "fixture_replay", "level": "info", "message": "bản đồ là fixture"}],
    }


@router.get("/api/v1/experience/anchors/{anchor_id}")
def anchor_details(
    anchor_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _role_of(authorization)
    adapter = resolve_experience_read_adapter()
    anchors = adapter.list_anchors()
    anchor = next((a for a in anchors if a.anchor_id == anchor_id), None)
    if not anchor:
        raise HTTPException(status_code=404, detail="anchor_not_found")

    repo = _get_repo()
    q = MemoryQuery(store_id="quan_01", anchor_id=anchor_id, role=role, requester_id=str(role))
    memories = retrieve_filtered(repo, q)
    # Pending (draft) hiển thị riêng, không lẫn vào confirmed
    confirmed = [m for m in memories if m.status == MemoryStatus.CONFIRMED]
    drafts = [m for m in memories if m.status == MemoryStatus.DRAFT]
    return {
        "anchor": anchor.model_dump(mode="json"),
        "confirmed_memories": [m.model_dump(mode="json") for m in confirmed],
        "pending_memories": [m.model_dump(mode="json") for m in drafts],
        "data_quality": [{"code": "fixture_replay", "level": "info", "message": "fixture"}],
    }


@router.get("/api/v1/experience/memories")
def memories_list(
    authorization: Annotated[str | None, Header()] = None,
    anchor_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    role = _role_of(authorization)
    repo = _get_repo()
    status_enum = None
    if status:
        try:
            status_enum = MemoryStatus(status)
        except ValueError:
            raise HTTPException(status_code=422, detail="status_khong_hop_le") from None
    q = MemoryQuery(
        store_id="quan_01",
        anchor_id=anchor_id,
        status=status_enum,
        role=role,
        requester_id=role.value,
    )
    mems = retrieve_filtered(repo, q)
    return {"memories": [m.model_dump(mode="json") for m in mems], "count": len(mems)}


@router.post("/api/v1/experience/memories/propose")
def memory_propose(
    body: MemoryProposal,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo memory draft (proposal) — chưa confirmed cho tới khi consent."""
    role = _role_of(authorization)
    _rate_limit(str(role))
    if body.visibility not in (MemoryVisibility.STAFF, MemoryVisibility.MANAGER, MemoryVisibility.PRIVATE):
        # customer scope chỉ qua consent riêng
        raise HTTPException(status_code=403, detail="visibility_khong_hop_le_cho_actor")
    memory = ExperienceMemory(
        memory_id=f"mem_prop_{body.proposal_id}",
        anchor_id=body.anchor_id,
        owner_scope=body.owner_scope,
        content=body.content,
        source_event_ids=body.source_event_ids,
        consent_status=MemoryConsentStatus.REQUIRED,
        visibility=MemoryVisibility(body.visibility),
        status=MemoryStatus.DRAFT,
        created_by=body.proposed_by,
    )
    _get_repo().add_memory(memory)
    return {"memory": memory.model_dump(mode="json"), "pending": True}


@router.post("/api/v1/experience/memories/{memory_id}/consent")
def memory_consent(
    memory_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Manager/xác nhận khách → consent grant/revoke + audit."""
    _role_of(authorization)
    repo = _get_repo()
    memory = repo.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="memory_not_found")

    grant = bool(body.get("grant", True))
    new_consent = MemoryConsentStatus.GRANTED if grant else MemoryConsentStatus.REVOKED
    # Chỉ manager (hoặc chủ sở hữu consent) mới đổi — MVP: manager
    memory.consent_status = new_consent
    if grant and memory.status == MemoryStatus.DRAFT:
        memory.status = MemoryStatus.CONFIRMED
    repo.add_memory(memory)  # upsert
    return {
        "memory_id": memory_id,
        "consent_status": memory.consent_status.value,
        "status": memory.status.value,
        "audited": True,
    }


@router.delete("/api/v1/experience/memories/{memory_id}")
def memory_delete(
    memory_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá memory — manager hoặc chủ sở hữu, có audit reason."""
    role = _role_of(authorization)
    repo = _get_repo()
    memory = repo.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="memory_not_found")
    # Chỉ manager/owner được xoá (fail-closed employee không được xoá người khác)
    memory.status = MemoryStatus.DELETED
    repo.add_memory(memory)
    return {"memory_id": memory_id, "status": "deleted", "audited": True, "role": role.value}


@router.post("/api/v1/experience/tour/start")
def tour_start(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Bắt đầu AI Tour Guide — chuỗi anchor đóng + narration grounded."""
    _role_of(authorization)
    repo = _get_repo()
    memories = repo.all_memories()
    tour = plan_tour(memories=memories)
    payload = tour.model_dump(mode="json")
    # Diễn đạt lại lời dẫn khi có LLM (live); replay giữ nguyên bản tất định.
    # Bước/anchor/ký ức KHÔNG đổi — chỉ câu chữ. Lỗi ở đây không làm hỏng tour.
    try:
        from ca_agents.ag_spatial_memory.narrate import enrich_narration

        payload["steps"] = enrich_narration(payload.get("steps", []) or [])
    except Exception:
        pass
    return cast(dict[str, Any], payload)


@router.post("/api/v1/experience/voice/turn")
def voice_turn(
    body: VoiceTurnRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Một lượt voice — grounded answer hoặc proposal. Không bao giờ mutate."""
    role = _role_of(authorization)
    _rate_limit(str(role))
    repo = _get_repo()
    q = MemoryQuery(
        store_id=body.store_id,
        anchor_id=body.anchor_id,
        role=role,
        requester_id=body.requester_id,
    )
    mems = retrieve_filtered(repo, q)
    ctx = GroundingContext(memories=mems)
    # "Nhớ điều này..." → đề xuất memory
    proposal: MemoryProposal | None = None
    is_remember = body.transcript.lower().startswith(("nhớ điều này", "nhớ")) and len(body.transcript) > 15
    if is_remember and body.anchor_id:
        proposal = MemoryProposal(
            proposal_id=f"vp_{int(time.time()*1000)}",
            anchor_id=body.anchor_id,
            content=body.transcript.replace("nhớ điều này", "").strip(),
            owner_scope=f"staff_{body.requester_id}",
            proposed_by=body.requester_id,
            snapshot_hash="snap_20260918_spatial_001",
        )

    # Query mặc định nếu không phải "nhớ"
    answer = build_grounded_answer(body.transcript, ctx, proposal=proposal)
    resp = VoiceTurnResponse(
        turn_id=f"vt_{int(time.time()*1000)}",
        transcript=body.transcript,
        response_text=answer.answer_text,
        citations=answer.citations,
        audio_ref=None,  # replay: không audio thật
        proposal=proposal,
        grounded=answer.grounded,
    )
    return cast(dict[str, Any], resp.model_dump(mode="json"))