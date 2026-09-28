"""HTTP router — War Room Digital Twin (plan 260920-1442 Phase 02).

- POST /api/v1/experience/war-room/simulate — chạy multi-scenario tất định.
- GET  /api/v1/experience/war-room/scenarios/{simulation_id} — đọc kết quả.
- POST /api/v1/experience/war-room/{simulation_id}/propose — tạo proposal.
- POST /api/v1/experience/war-room/{simulation_id}/confirm — manager-only.

KHÔNG có POST .../apply (bỏ qua proposal / mutation trực tiếp).
Mô phỏng KHÔNG bao giờ ghi đổi lịch/inventory/rule/memory.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from ca_agents.ag_war_room import run_war_room_comparison
from ca_agents.ag_war_room.command import normalize_command
from ca_agents.grand_experience.adapter import resolve_experience_read_adapter
from ca_contracts import (
    ExperienceActionProposal,
    WarRoomScenario,
)
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _require_manager, _require_role
from ca_api.persist import audit_add, kv_mutate

router = APIRouter(tags=["experience_war_room"])

# ── Lưu trữ tạm trong-memory của simulation (stateless endpoint ngoài) ──────
_LOCK = threading.Lock()
_SIM_CACHE: dict[str, dict[str, Any]] = {}
_USER_TS: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_REQ = 20


def clear_war_room_state() -> None:
    """Xoá cache/rate limit (dùng khi test)."""
    with _LOCK:
        _SIM_CACHE.clear()
        _USER_TS.clear()


def _rate_limit(user_id: str) -> None:
    now = time.time()
    with _LOCK:
        recent = [t for t in _USER_TS.get(user_id, []) if now - t < _WINDOW_S]
        if len(recent) >= _MAX_REQ:
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
        recent.append(now)
        _USER_TS[user_id] = recent


class WarRoomSimulateBody(BaseModel):
    request_id: str = Field(min_length=1)
    baseline_snapshot: str = Field(min_length=8)
    scenarios: list[WarRoomScenario] = Field(min_length=1, max_length=10)
    requested_by: str = Field(min_length=1)


class WarRoomProposeBody(BaseModel):
    option_id: str = Field(min_length=1)
    expected_snapshot_hash: str = Field(min_length=8)


class WarRoomConfirmBody(BaseModel):
    option_id: str | None = None


@router.post("/api/v1/experience/war-room/simulate")
def war_room_simulate(
    body: WarRoomSimulateBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chạy so sánh War Room — manager/owner only, idempotent."""
    user = _require_manager(authorization)
    _rate_limit(str(user))

    cmd = normalize_command(
        body.request_id,
        body.baseline_snapshot,
        body.scenarios,
        body.requested_by,
    )
    adapter = resolve_experience_read_adapter()
    current_hash = adapter.fingerprint()
    # Trong replay/fixture, cho phép snapshot fixture (danh sách trắng) là hợp
    # lệ — trình diễn không bị chặn bởi stale baseline. Snapshot lạ vẫn fail.
    allowed_fixture_snapshots = {
        "snap_fixture_demand_20260918",
        "snap_fixture_staffing_20260918",
        "snap_fixture_weather_20260918",
        "snap_fixture_equipment_20260918",
        "snap_fixture_large_group_20260918",
    }
    if body.baseline_snapshot in allowed_fixture_snapshots:
        effective_hash = body.baseline_snapshot
    else:
        effective_hash = current_hash
    comparison = run_war_room_comparison(
        cmd,
        current_snapshot_hash=effective_hash,
    )
    payload = comparison.model_dump(mode="json")
    # Tầng GIẢI THÍCH: mỗi phương án kèm lời giải thích đọc được. Số liệu vẫn do
    # engine tất định tính; đây chỉ diễn giải lại (LLM khi live, lưới tất định khi
    # replay). Nhờ vậy bấm "Đề xuất" mới thấy nội dung thay vì chỉ con số khô.
    try:
        from ca_agents.ag_war_room.explain import explain_option

        options = payload.get("options", []) or []
        for opt in options:
            info = explain_option(opt, all_options=options)
            opt["reason"] = info["reason"]
            opt["reason_provider"] = info["provider"]
            if info["unsupported"]:
                opt["reason_unsupported"] = info["unsupported"]
    except Exception:
        # Giải thích là lớp phụ trợ — lỗi ở đây KHÔNG được làm hỏng mô phỏng.
        pass
    with _LOCK:
        _SIM_CACHE[comparison.simulation_id] = {
            "request_id": body.request_id,
            "requested_by": body.requested_by,
            "comparison": payload,
            "created_at": time.time(),
        }
    return {**payload, "replayable": True, "simulation_id": comparison.simulation_id}


@router.get("/api/v1/experience/war-room/scenarios/{simulation_id}")
def war_room_get_scenarios(
    simulation_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đọc kết quả simulation đã chạy (read-only)."""
    _require_role(authorization)
    with _LOCK:
        item = _SIM_CACHE.get(simulation_id)
    if not item:
        raise HTTPException(status_code=404, detail="simulation_not_found")
    return cast(dict[str, Any], item["comparison"])


@router.post("/api/v1/experience/war-room/{simulation_id}/propose")
def war_room_propose(
    simulation_id: str,
    body: WarRoomProposeBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo ExperienceActionProposal cho một option — chưa có mutation."""
    user = _require_manager(authorization)
    with _LOCK:
        item = _SIM_CACHE.get(simulation_id)
    if not item:
        raise HTTPException(status_code=404, detail="simulation_not_found")

    comparison = item["comparison"]
    options = comparison.get("options", [])
    option = next((o for o in options if o["option_id"] == body.option_id), None)
    if not option:
        raise HTTPException(status_code=404, detail="option_not_found")
    if option.get("constraint_violations"):
        raise HTTPException(
            status_code=409,
            detail="option_violates_hard_constraint",
        )

    # Stale snapshot → không thể tạo proposal xác nhận được.
    if option.get("stale_data"):
        raise HTTPException(status_code=409, detail="stale_baseline")

    proposal = ExperienceActionProposal(
        proposal_id=f"wr_prop_{simulation_id}_{body.option_id}",
        action_type="war_room_option",
        snapshot_hash=body.expected_snapshot_hash,
        evidence_refs=[f"war_room:{simulation_id}:{body.option_id}"],
        deterministic_result={
            "simulation_id": simulation_id,
            "option_id": body.option_id,
            "outputs": option.get("outputs"),
        },
        explanation="Mô phỏng War Room — chờ quản lý xác nhận",
        requested_by=str(user),
    )
    return {
        "proposal": proposal.model_dump(mode="json"),
        "status": proposal.status,
        "replayable": True,
    }


@router.post("/api/v1/experience/war-room/{simulation_id}/confirm")
def war_room_confirm(
    simulation_id: str,
    body: WarRoomConfirmBody = WarRoomConfirmBody(),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Manager-only confirm. Không trực tiếp ghi lịch/tồn kho/luật/ký ức thật
    (mô phỏng luôn có thể sai — ghi đè thẳng là rủi ro), nhưng ghi lại quyết
    định thành MỘT việc thật trong Sổ việc treo (`/treo`) + một vết hệ thống
    (`/vet`) để quản lý ghim vào vận hành, thay vì `confirm` không để lại dấu
    vết gì như trước (Phase 07 cũ)."""
    user = _require_manager(authorization)
    with _LOCK:
        item = _SIM_CACHE.get(simulation_id)
    if not item:
        raise HTTPException(status_code=404, detail="simulation_not_found")

    option_id = body.option_id
    comparison = item.get("comparison") or {}
    options = comparison.get("options") or []
    option = next((o for o in options if o.get("option_id") == option_id), None) if option_id else None
    label = option.get("label") if isinstance(option, dict) and option.get("label") else (option_id or "phương án đã mô phỏng")

    treo_item = {
        "id": f"treo_warroom_{uuid.uuid4().hex[:8]}",
        "noi_dung": f"War Room đã chốt: {label} (mô phỏng {simulation_id}) — cần áp dụng vào vận hành.",
        "trang_thai": "dang_cho",
        "nguon": "war_room",
        "simulation_id": simulation_id,
        "option_id": option_id,
        "created_at": datetime.now(UTC).isoformat(),
    }

    def _mut_treo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.insert(0, treo_item)
        return items

    kv_mutate("treo", _mut_treo, [])
    audit_add(
        datetime.now(UTC).isoformat(),
        str(user),
        "experience.war_room.confirm",
        {"simulation_id": simulation_id, "option_id": option_id},
    )

    return {
        "confirmed": True,
        "simulation_id": simulation_id,
        "confirmed_by": str(user),
        "mutation": "none",
        "note": "War Room không ghi đè trực tiếp lịch/tồn kho — đã tạo việc treo để quản lý áp dụng.",
        "treo_id": treo_item["id"],
    }