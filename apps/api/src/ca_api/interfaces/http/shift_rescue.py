"""HTTP router — AI Shift Rescue (plan 260920-1442 Phase 03).

Endpoints:
- POST /api/v1/experience/shift-rescue/intake — báo vắng → case
- POST /api/v1/experience/shift-rescue/{case_id}/candidates — tìm người bù
- GET  /api/v1/experience/shift-rescue/{case_id} — đọc case
- POST /api/v1/experience/shift-rescue/{case_id}/propose — tạo proposal
- POST /api/v1/experience/shift-rescue/{case_id}/invite — mời
- POST /api/v1/experience/shift-rescue/{case_id}/respond — phản hồi
- POST /api/v1/experience/shift-rescue/{case_id}/confirm — xác nhận (manager)

confirm ủy quyền lifecycle mutation hiện có; MVP replay ghi nhận không mutation
thật. KHÔNG gửi invite trước khi confirmed_proposal.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from ca_agents.ag_shift_rescue.eligibility import (
    StaffProfile,
    filter_eligible,
)
from ca_agents.ag_shift_rescue.intake import normalize_absence, resolve_shift_identity
from ca_agents.ag_shift_rescue.ranking import rank_candidates
from ca_agents.grand_experience.replay import FixtureReader
from ca_contracts import RescueCaseStatus
from ca_ops.shift_rescue_policy import RescueCaseState
from fastapi import APIRouter, Header, HTTPException

from ca_api.interfaces.http.sprint3 import _require_manager, _require_role
from ca_api.persist import audit_add, kv_mutate

router = APIRouter(tags=["experience_shift_rescue"])

_LOCK = threading.Lock()
_CASES: dict[str, dict[str, Any]] = {}
_USER_TS: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_REQ = 15


def clear_shift_rescue_state() -> None:
    with _LOCK:
        _CASES.clear()
        _USER_TS.clear()


def _rate_limit(user_id: str) -> None:
    now = time.time()
    with _LOCK:
        recent = [t for t in _USER_TS.get(user_id, []) if now - t < _WINDOW_S]
        if len(recent) >= _MAX_REQ:
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
        recent.append(now)
        _USER_TS[user_id] = recent


def _fixture() -> dict[str, Any]:
    reader = FixtureReader()
    return cast(dict[str, Any], reader.read_json_path("shift-rescue.json"))


def _tuan_hien_tai() -> str:
    """Tuần ISO hiện tại (nguồn: lịch tuần đang hiệu lực, fallback hôm nay)."""
    try:
        from ca_api.interfaces.http.sprint45 import _life

        tuan = str(_life().get("tuan_iso") or "")
        if tuan:
            return tuan
    except Exception:
        pass
    y, w, _ = datetime.now(UTC).isocalendar()
    return f"{y}-W{w:02d}"


def _live_rescue_data(week: str | None = None) -> dict[str, Any] | None:
    """Dữ liệu cứu ca THẬT từ lịch tuần: ca có người, người trong ca, kỹ năng.

    Trả ``None`` khi chưa có lịch tuần thật (để handler rơi về fixture replay).
    Nguồn: seed `ca_mau_21` (khung/giờ/vị trí ca) + `phan_cong_by_week` (ai đang
    trong ca) + `list_nhan_vien_ops` (danh bạ thật). KHÔNG bịa số: giờ tuần và
    số ca suy từ chính phân công thật.
    """
    import json as _json

    from ca_api.nhan_vien import list_nhan_vien_ops
    from ca_api.persist import kv_get

    tuan = week or _tuan_hien_tai()
    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    if not isinstance(week_assign, dict) or not week_assign:
        # Thử file lịch tuần đang hiệu lực (nguồn solver ghi ra).
        try:
            from ca_api.interfaces.http.sprint45 import _lich_out

            out = _lich_out()
            if out.exists():
                doc = _json.loads(out.read_text(encoding="utf-8"))
                if str(doc.get("tuan_iso") or "") == tuan:
                    week_assign = doc.get("phan_cong", {}) or {}
        except Exception:
            week_assign = {}
    if not isinstance(week_assign, dict) or not week_assign:
        return None

    # Seed chuẩn của app (khung/giờ/vị trí ca) — dùng đúng nguồn như roster.
    from ca_api.interfaces.http.main import SEED

    try:
        seed = _json.loads(SEED.read_text(encoding="utf-8"))
    except Exception:
        seed = {}
    ca_meta = {str(c.get("id")): c for c in seed.get("ca_mau_21", []) if c.get("id")}

    nv_rows = list_nhan_vien_ops()
    ten_by_id = {str(n["id"]): str(n.get("ten") or n["id"]) for n in nv_rows}
    ky_nang_by_id = {str(n["id"]): list(n.get("ky_nang") or []) for n in nv_rows}

    # Đếm số ca + giờ đã xếp mỗi người (từ chính phân công thật).
    so_ca: dict[str, int] = {}
    gio: dict[str, float] = {}
    for ca_id, nvs in week_assign.items():
        meta = ca_meta.get(str(ca_id), {})
        dur = _shift_hours(meta)
        for nv in nvs or []:
            so_ca[str(nv)] = so_ca.get(str(nv), 0) + 1
            gio[str(nv)] = gio.get(str(nv), 0.0) + dur

    # Chỉ trả ca ĐANG có người (báo vắng cho ca trống là vô nghĩa).
    shifts: list[dict[str, Any]] = []
    assignment: dict[str, list[str]] = {}
    for ca_id, nvs in week_assign.items():
        nvs = [str(x) for x in (nvs or [])]
        if not nvs:
            continue
        meta = ca_meta.get(str(ca_id), {})
        shifts.append(
            {
                "id": str(ca_id),
                "thu": str(meta.get("thu") or ""),
                "khung": str(meta.get("khung") or ""),
                "vi_tri": str(meta.get("vi_tri") or ""),
                "bat_dau": str(meta.get("bat_dau") or ""),
                "ket_thuc": str(meta.get("ket_thuc") or ""),
            }
        )
        assignment[str(ca_id)] = nvs

    if not shifts:
        return None

    staff = [
        {
            "nv_id": nv_id,
            "ten": ten_by_id.get(nv_id, nv_id),
            "ky_nang": ky_nang_by_id.get(nv_id, []),
            "gio_da_lam": round(gio.get(nv_id, 0.0), 2),
            "so_ca_tuan": so_ca.get(nv_id, 0),
        }
        for nv_id in {str(x) for nvs in assignment.values() for x in nvs}
    ]
    return {
        "meta": {"schema": "grand_experience_shift_rescue_v1", "note": "Dữ liệu THẬT từ lịch tuần.", "labels": ["live", "roster"]},
        "snapshot_hash": f"snap_live_{tuan}",
        "tuan_iso": tuan,
        "staff": staff,
        "shifts": shifts,
        "current_assignment": assignment,
        "demo_case": {},
        "live": True,
    }


def _shift_hours(meta: dict[str, Any]) -> float:
    """Số giờ của một ca từ 'HH:MM' bat_dau/ket_thuc (mặc định 5.0 nếu thiếu)."""
    try:
        b = str(meta.get("bat_dau") or "")
        e = str(meta.get("ket_thuc") or "")
        bh, bm = (int(x) for x in b.split(":"))
        eh, em = (int(x) for x in e.split(":"))
        return max(0.0, (eh * 60 + em - bh * 60 - bm) / 60.0)
    except Exception:
        return 5.0


def _rescue_data() -> dict[str, Any]:
    """Dữ liệu thật nếu có; nếu chưa có lịch tuần thì rơi về fixture replay."""
    live = _live_rescue_data()
    return live if live else _fixture()


@router.get("/api/v1/experience/shift-rescue/options")
def shift_rescue_options(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Ca đang có người + danh bạ để báo vắng.

    UI trước đây hardcode `nv_absent_quan` / `t7_toi`, nghĩa là nghiệp vụ chỉ
    chạy được đúng một kịch bản. Trả về danh sách thật để người quản lý chọn
    đúng ca và đúng người — vẫn từ fixture, nhưng không còn một đường cứng.
    """
    _require_role(authorization)
    data = _rescue_data()
    staff_rows = data.get("staff", [])
    assignment = data.get("current_assignment", {}) or {}
    shifts = data.get("shifts", [])

    options: list[dict[str, Any]] = []
    for shift in shifts:
        shift_id = str(shift.get("id") or "")
        assigned = [str(x) for x in assignment.get(shift_id, [])]
        options.append(
            {
                "shift_id": shift_id,
                "thu": str(shift.get("thu") or ""),
                "khung": str(shift.get("khung") or ""),
                "vi_tri": str(shift.get("vi_tri") or ""),
                "bat_dau": str(shift.get("bat_dau") or ""),
                "ket_thuc": str(shift.get("ket_thuc") or ""),
                # Chỉ người đang được phân ca mới báo vắng được — báo vắng cho
                # người không có trong ca là dữ liệu vô nghĩa.
                "assigned": [
                    {
                        "nv_id": nv_id,
                        "ten": next(
                            (
                                str(s.get("ten") or nv_id)
                                for s in staff_rows
                                if str(s.get("nv_id") or "") == nv_id
                            ),
                            nv_id,
                        ),
                    }
                    for nv_id in assigned
                ],
            }
        )

    return {
        "shifts": [o for o in options if o["assigned"]],
        "suggested": data.get("demo_case", {}),
        "replayable": not bool(data.get("live")),
        "nguon": "lich_tuan" if data.get("live") else "fixture",
        "tuan_iso": str(data.get("tuan_iso") or ""),
    }


@router.post("/api/v1/experience/shift-rescue/intake")
def shift_rescue_intake(
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Nhận báo vắng, tạo case (đã resolve shift)."""
    user = _require_manager(authorization)
    _rate_limit(str(user))
    case_id = str(body.get("case_id") or f"rescue_{int(time.time())}")
    absence_nv_id = str(body.get("absence_nv_id") or "")
    shift_id = str(body.get("shift_id") or "")
    reason = str(body.get("reason") or "")

    if not absence_nv_id or not shift_id:
        raise HTTPException(status_code=422, detail="thieu_nv_hoac_ca")

    data = _rescue_data()
    known_shift_ids = {s["id"] for s in data.get("shifts", [])}
    try:
        resolved_shift = resolve_shift_identity(
            known_shift_ids=known_shift_ids,
            suggested_shift_id=shift_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cmd = normalize_absence(
        case_id=case_id,
        absence_nv_id=absence_nv_id,
        shift_id=resolved_shift,
        reported_by=str(user),
        reason=reason,
        schedule_snapshot_hash=str(data.get("snapshot_hash") or "snap_shift_fixture"),
    )
    case_state = RescueCaseState(
        case_id=cmd.case_id,
        schedule_snapshot_hash=cmd.schedule_snapshot_hash,
    )
    with _LOCK:
        _CASES[cmd.case_id] = {
            "command": cmd.model_dump(mode="json"),
            "state": case_state,
            "candidates": [],
        }
    return {
        "case_id": cmd.case_id,
        "status": RescueCaseStatus.REPORTED.value,
        "shift_id": cmd.shift_id,
        "replayable": True,
    }


@router.post("/api/v1/experience/shift-rescue/{case_id}/candidates")
def shift_rescue_candidates(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tìm người bù: eligibility + ranking deterministic."""
    _require_role(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")

    data = _rescue_data()
    staff_rows = data.get("staff", [])
    shift_id = str(item["command"]["shift_id"])
    shift = next((s for s in data.get("shifts", []) if s["id"] == shift_id), None)
    if not shift:
        raise HTTPException(status_code=404, detail="shift_not_found")

    required_skill = str(shift.get("vi_tri") or "")  # vd pha_che
    ca_meta = {
        "ca_id": shift_id,
        "thu": str(shift.get("thu") or ""),
        "khung": str(shift.get("khung") or ""),
        "bat_dau": str(shift.get("bat_dau") or ""),
        "ket_thuc": str(shift.get("ket_thuc") or ""),
    }

    # Dựng profile cho từng người (chỉ cần public/eligible fields)
    profiles: list[StaffProfile] = []
    for row in staff_rows:
        nv_id = str(row.get("nv_id") or "")
        profiles.append(
            StaffProfile(
                nv_id=nv_id,
                ten=str(row.get("ten") or ""),
                ky_nang=set(str(k) for k in row.get("ky_nang") or []),
                gio_da_lam=float(row.get("gio_da_lam") or 0.0),
                so_ca_tuan=int(row.get("so_ca_tuan") or 0),
            )
        )

    absence_nv_id = str(item["command"]["absence_nv_id"])
    safe = filter_eligible(
        profiles,
        absence_nv_id=absence_nv_id,
        ca_meta=ca_meta,
        required_skill=required_skill,
        tran_gio_tuan=48.0,
        khoang_nghi_gio=8.0,
        hours_to_add=5.0,
    )
    debt_by_nv = {p.nv_id: {"gio": float(p.gio_da_lam)} for p in profiles}
    hours_by_nv = {p.nv_id: float(p.gio_da_lam) for p in profiles}
    shift_count_by_nv = {p.nv_id: int(p.so_ca_tuan) for p in profiles}

    ranked = rank_candidates(
        safe,
        required_skill=required_skill,
        debt_by_nv=debt_by_nv,
        hours_by_nv=hours_by_nv,
        shift_count_by_nv=shift_count_by_nv,
    )

    # Xây candidate card: safe/blocked + lý do tối thiểu an toàn privacy
    blocked: list[dict[str, Any]] = []
    for p in profiles:
        if p.nv_id == absence_nv_id:
            continue
        if p.nv_id in {r.nv_id for r in ranked}:
            continue
        reasons: list[str] = []
        if required_skill not in p.ky_nang:
            reasons.append("thieu_ky_nang")
        if p.gio_da_lam + 5.0 > 48.0:
            reasons.append("vuot_tran_gio")
        blocked.append(
            {
                "candidate_id": f"cand_{p.nv_id}",
                "nv_id": p.nv_id,
                "nv_ten": p.ten,
                "safe": False,
                "reason_blocks": reasons,
            }
        )

    candidates = [
        {
            "candidate_id": f"cand_{r.nv_id}",
            "nv_id": r.nv_id,
            "nv_ten": r.nv_ten,
            "safe": True,
            "reason_passes": r.reason_passes,
            "fairness_delta": r.fairness_delta,
            "added_hours": r.added_hours,
            "skill_coverage": r.skill_coverage,
            "rank": r.rank,
        }
        for r in ranked
    ]

    # No safe → escalation plan (không broadcast)
    escalation: dict[str, Any] | None = None
    if not ranked:
        escalation = {
            "level": "none_safe",
            "options": [
                "manager_cover_shift",
                "reduce_capacity",
                "close_station",
                "enter_crisis_room",
            ],
            "no_broadcast": True,
        }

    with _LOCK:
        item["candidates"] = candidates
        item["blocked"] = blocked
        # Transition hợp lệ: reported -> resolving -> candidates_ready
        current_state = item["state"].state.value
        if current_state == RescueCaseStatus.REPORTED.value:
            item["state"].transition("resolving", actor="system", note="resolve shift")
            item["state"].transition("candidates_ready", actor="system", note="candidates computed")
        _CASES[case_id] = item

    return {
        "case_id": case_id,
        "candidates": candidates,
        "blocked": blocked,
        "escalation": escalation,
        "status": RescueCaseStatus.CANDIDATES_READY.value,
        "replayable": True,
    }


@router.get("/api/v1/experience/shift-rescue/{case_id}")
def shift_rescue_get(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")
    return {
        "case_id": case_id,
        "status": item["state"].state.value,
        "candidates": item.get("candidates", []),
        "blocked": item.get("blocked", []),
        "invited": item["state"].invited_candidates,
        "replayable": True,
    }


@router.post("/api/v1/experience/shift-rescue/{case_id}/propose")
def shift_rescue_propose(
    case_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo proposal trước khi invite — không tự invite."""
    _require_manager(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")
    candidate_id = str(body.get("candidate_id") or "")
    cand = next((c for c in item.get("candidates", []) if c["candidate_id"] == candidate_id), None)
    if not cand or not cand.get("safe"):
        raise HTTPException(status_code=409, detail="candidate_khong_an_toan")

    if item["state"].state.value == RescueCaseStatus.CANDIDATES_READY.value:
        item["state"].transition("proposed", actor="system", note=f"propose {candidate_id}")
    return {
        "case_id": case_id,
        "proposal_status": "draft",
        "candidate_id": candidate_id,
        "replayable": True,
    }


@router.post("/api/v1/experience/shift-rescue/{case_id}/invite")
def shift_rescue_invite(
    case_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Gửi invite chỉ sau khi proposal — idempotent."""
    _require_manager(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")
    candidate_ids = [str(x) for x in body.get("candidate_ids", [])]
    if not candidate_ids:
        raise HTTPException(status_code=422, detail="thieu_candidate_ids")
    if item["state"].state.value == RescueCaseStatus.CANDIDATES_READY.value:
        item["state"].transition("proposed", actor="system", note="auto proposed before invite")
    item["state"].invite(candidate_ids, actor=str(_require_manager(authorization)))
    return {
        "case_id": case_id,
        "invited": item["state"].invited_candidates,
        "status": item["state"].state.value,
        "replayable": True,
    }


@router.post("/api/v1/experience/shift-rescue/{case_id}/respond")
def shift_rescue_respond(
    case_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Nhân viên phản hồi invite — accept hoặc reject."""
    _require_role(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")
    candidate_id = str(body.get("candidate_id") or "")
    accept = bool(body.get("accept", False))
    item["state"].respond(candidate_id, accept=accept, actor=str(_require_role(authorization)))
    return {
        "case_id": case_id,
        "status": item["state"].state.value,
        "onboard_next_candidate": not accept,
        "replayable": True,
    }


@router.post("/api/v1/experience/shift-rescue/{case_id}/confirm")
def shift_rescue_confirm(
    case_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Manager confirm — ủy quyền lifecycle mutation hiện có (MVP: none)."""
    user = _require_manager(authorization)
    with _LOCK:
        item = _CASES.get(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="case_not_found")
    candidate_id = str(body.get("candidate_id") or "")
    # Stale snapshot check: snapshot trong case phải khớp fixture hiện tại.
    current_hash = _fixture().get("snapshot_hash")
    if item["command"]["schedule_snapshot_hash"] != current_hash:
        raise HTTPException(status_code=409, detail="stale_schedule_recompute")

    item["state"].confirm(candidate_id, actor=str(user))

    # Ghi lại quyết định thành một việc thật (Sổ việc treo) + một vết hệ
    # thống — quản lý mở /treo hoặc /vet sẽ thấy đúng người đã bù ca cho ai,
    # ca nào. Dữ liệu case/candidate ở router này vẫn là mô phỏng có kịch bản
    # cố định (không gian mã ca khác lịch tuần thật), nên KHÔNG tự ghi đè
    # `phan_cong` — ghi một việc rõ ràng để quản lý ghim vào lịch tuần là lựa
    # chọn an toàn hơn tự đoán đúng ô ca.
    shift_id = str(item["command"].get("shift_id") or "")
    absence_nv = str(item["command"].get("absence_nv_id") or "")
    treo_item = {
        "id": f"treo_rescue_{uuid.uuid4().hex[:8]}",
        "noi_dung": f"Cứu ca {shift_id}: {candidate_id} nhận thay {absence_nv} — cần ghim vào lịch tuần.",
        "trang_thai": "dang_cho",
        "nguon": "cuu_ca",
        "case_id": case_id,
        "shift_id": shift_id,
        "candidate_id": candidate_id,
        "created_at": datetime.now(UTC).isoformat(),
    }

    def _mut_treo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.insert(0, treo_item)
        return items

    kv_mutate("treo", _mut_treo, [])
    audit_add(
        datetime.now(UTC).isoformat(),
        str(user),
        "experience.shift_rescue.confirm",
        {"case_id": case_id, "shift_id": shift_id, "candidate_id": candidate_id, "absence_nv_id": absence_nv},
    )

    return {
        "case_id": case_id,
        "status": item["state"].state.value,
        "confirmed_candidate_id": candidate_id,
        "mutation": "viec_treo_da_tao",
        "treo_id": treo_item["id"],
        "replayable": True,
    }