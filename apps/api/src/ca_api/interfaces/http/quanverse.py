"""HTTP router — QUÁNVERSE Living Cafe OS (plan 260920-1442 Phase 06).

- GET    /quanverse/snapshot — LivingCafeSnapshot theo role (server strip fields)
- GET    /quanverse/modes
- POST   /quanverse/modes/{mode}/propose
- POST   /quanverse/modes/{mode}/confirm (manager)
- POST   /quanverse/modes/{mode}/deactivate (manager)
- POST   /quanverse/flavor/recommend
- GET    /quanverse/preferences
- POST   /quanverse/preferences/propose
- POST   /quanverse/preferences/{id}/consent
- DELETE /quanverse/preferences/{id}
- GET    /quanverse/tour/{tour_id}
- POST   /quanverse/ar-session (capability gate)

Mọi POST idempotent + proposal/consent based. Không tự đổi lịch/rule/memory.

Thời gian: fixture khai mốc bằng phút tương đối (`minutes_ago`, `starts_in_min`)
để trục "15 phút tới" luôn có mốc thật ở tương lai thay vì mốc quá khứ đóng băng.
Không bịa dữ liệu: chỉ quy đổi mốc, `data_quality` nói rõ đây là fixture.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from ca_agents.ag_quanverse.flavor import FlavorPreference, recommend_from_taste
from ca_agents.ag_quanverse.modes import can_activate_mode, mode_affects, mode_effect
from ca_agents.grand_experience.replay import FixtureReader
from ca_contracts import (
    LivingCafeSnapshot,
    ModeProjection,
    PublicEventProjection,
    ZoneProjection,
)
from ca_contracts.grand_experience import (
    ExperienceMode,
    ExperienceProposalStatus,
    ExperienceRole,
    QuanversePage,
)
from fastapi import APIRouter, Header, HTTPException, Query

from ca_api.interfaces.http.spatial_memory import clear_spatial_state
from ca_api.interfaces.http.sprint3 import _require_manager, _require_role
from ca_api.persist import kv_get, kv_mutate, kv_set

router = APIRouter(tags=["experience_quanverse"])

_LOCK = threading.Lock()
_USER_TS: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_REQ = 20

_PREF_KEY = "experience_preferences"


def clear_quanverse_state() -> None:
    with _LOCK:
        _USER_TS.clear()
    # Xoá mode states kv (test isolation — không để confirm của test trước sót lại)
    try:
        for mode in ExperienceMode:
            kv_set(f"experience_mode_{mode.value}", None)
        kv_set(_PREF_KEY, [])
    except Exception:
        pass


@router.post("/api/v1/experience/quanverse/reset")
def quanverse_reset(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá trạng thái Quánverse trong bộ nhớ + kv — CHỈ khi bật chế độ replay/demo.

    Vì sao cần: `experience_preferences` nằm trong kv (DB) nên **tồn tại qua các
    lần chạy**. Bài `quanverse.spec.ts` "preference reaches stored via consent"
    lưu một sở thích khách ("thích bàn cạnh cửa sổ yên tĩnh") và KHÔNG có bước dọn.
    Sở thích đó gắn với neo `window_table`, nên nó trở thành một ký ức đã xác nhận
    thứ hai ở neo đó. Bài `grand-experience-replay.spec.ts` hỏi về quầy pha chế và
    khẳng định ĐÚNG 1 trích dẫn — chạy sau bài kia thì nhận 2 và đỏ.

    Đo được: sau nhiều lần chạy, kv đã tích **8** bản ghi trùng, mỗi lần chạy thêm
    một bản. Đây là rò trạng thái giữa các bài, không phải lỗi logic của agent —
    API grounding vốn đã đúng (`bar` → 1 ký ức, `stockroom` → 0).

    Cùng khuôn với `/experience/rules/reset` và `replay_role`: production gọi sẽ
    nhận 403. `clear_quanverse_state()` đã làm việc này cho pytest; endpoint này
    mở nó ra cho các bài e2e dùng chung một server.

    Ngoài kv, endpoint còn dựng lại **kho ký ức** (`clear_spatial_state`). Kho đó
    nằm trong biến toàn cục của `spatial_memory.py` và `POST /memories/{id}/consent`
    sửa thẳng vào đó, nên consent cấp cho một bản nháp cũng sống mãi. Fixture khai
    `mem_bar_draft_01` là bản nháp chờ consent; mỗi lần một bài test cấp consent
    cho nó là neo `bar` từ 1 ký ức đã xác nhận thành 2 — và bài
    `grand-experience-replay` khẳng định trích dẫn chứa "1" sẽ đỏ, kể cả khi chạy
    một mình. Reset phải trả CẢ HAI store về nguồn, không chỉ store trong kv.
    """
    import os

    allowed = (
        os.environ.get("CA_AGENT_MODE", "") == "replay"
        or os.environ.get("NHIPQUAN_EXPERIENCE_REPLAY_ROLE", "") == "1"
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="chi_cho_phep_o_che_do_replay")
    _require_role(authorization)
    clear_quanverse_state()
    clear_spatial_state()
    return {"reset": True, "replayable": True}


def _rate_limit(user_id: str) -> None:
    now = time.time()
    with _LOCK:
        recent = [t for t in _USER_TS.get(user_id, []) if now - t < _WINDOW_S]
        if len(recent) >= _MAX_REQ:
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
        recent.append(now)
        _USER_TS[user_id] = recent


def _fixture(name: str) -> dict[str, Any]:
    reader = FixtureReader()
    return cast(dict[str, Any], reader.read_json_path(name))


def _now() -> datetime:
    return datetime.now(UTC)


def _iso_at(minutes_from_now: float) -> str:
    """Mốc ISO cách hiện tại `minutes_from_now` phút (âm = quá khứ)."""
    return (_now() + timedelta(minutes=minutes_from_now)).isoformat()


def _event_time(row: dict[str, Any]) -> str:
    """Mốc sự kiện: ưu tiên `occurred_at` tuyệt đối, nếu không thì `minutes_ago`."""
    absolute = row.get("occurred_at")
    if absolute:
        return str(absolute)
    return _iso_at(-float(row.get("minutes_ago") or 0))


def _horizon_time(row: dict[str, Any]) -> str:
    """Mốc tầm nhìn: ưu tiên `starts_at` tuyệt đối, nếu không thì `starts_in_min`."""
    absolute = row.get("starts_at")
    if absolute:
        return str(absolute)
    return _iso_at(float(row.get("starts_in_min") or 0))


# ── Role projection matrix (server-side strip — không dựa vào client) ────────


def _project_role(role: ExperienceRole) -> dict[str, Any]:
    """Dựng snapshot projection theo role. Fail-closed: chùi field không thuộc."""
    data = _fixture("quanverse.json")
    zones = [ZoneProjection.model_validate(z) for z in data.get("zones", [])]
    events = [
        PublicEventProjection.model_validate({**e, "occurred_at": _event_time(e)})
        for e in data.get("events", [])
    ]
    modes = [ModeProjection.model_validate(m) for m in data.get("modes", [])]
    # Ghi đè trạng thái mode bằng kv (trạng thái thật do người dùng tạo khi replay).
    #
    # BẪY ĐÃ GẶP: bản trước chỉ lấy `active` từ kv rồi đặt
    #   proposal_status = "confirmed" if active else m.proposal_status
    # — tức khi mode CHƯA bật thì nó vứt giá trị trong kv và dùng lại giá trị của
    # FIXTURE. Hệ quả: `POST /modes/{mode}/propose` ghi `proposal_status="draft"`
    # vào kv thành công, nhưng `GET /snapshot` (chính endpoint mà UI đọc) không bao
    # giờ thấy giá trị đó, nên giao diện vẫn hiện "Đang tắt" và KHÔNG hiện nút
    # "Duyệt" — vòng đời đề xuất → duyệt bị kẹt ngay ở bước đề xuất.
    # Endpoint `/modes` (thêm sau) đã đọc đúng; ở đây phải đọc giống hệt.
    # Thứ tự ưu tiên: kv → fixture → None. `confirmed` chỉ khi đang active.
    for i, m in enumerate(modes):
        state = kv_get(f"experience_mode_{m.mode.value}", None) or {}
        active = bool(state.get("active", m.active))
        if active:
            proposal_status: str | None = "confirmed"
        else:
            raw = state.get("proposal_status") or (
                m.proposal_status.value if m.proposal_status else None
            )
            # `confirmed` trong khi chưa active là vô nghĩa (mâu thuẫn trạng thái),
            # và UI đọc nó thành "chờ duyệt" nên sẽ hiện nút Duyệt sai. Bỏ đi.
            proposal_status = None if raw == "confirmed" else str(raw) if raw else None
        modes[i] = ModeProjection(
            mode=m.mode,
            active=active,
            proposed_by=str(state.get("confirmed_by") or state.get("proposed_by") or m.proposed_by),
            proposal_status=cast(ExperienceProposalStatus | None, proposal_status),
        )

    horizon = [
        {**h, "starts_at": _horizon_time(h)} for h in data.get("horizon", [])
    ]

    if role == ExperienceRole.KHACH:
        # Chỉ thấy chỗ ngồi + hướng dẫn menu; KHÔNG thấy staff/private ops.
        modes_proj: list[ModeProjection] = [
            ModeProjection(mode=m.mode, active=m.active) for m in modes
        ]
        return {
            "zones": [z for z in zones if z.kind in ("phong_khach", "loi_vao")],
            "events": [],
            "modes": modes_proj,
            "next_horizon": [],
            "data_quality": [
                {
                    "code": "public_mode",
                    "level": "info",
                    "message": "Bản chiếu khách — không có dữ liệu vận hành",
                }
            ],
        }
    if role == ExperienceRole.NHAN_VIEN:
        # NV thấy attention points, không thấy private customer memory.
        # Ranh giới này do test_employee_snapshot_limited_events giữ: chỉ
        # rescue_case + signal. Mở rộng thêm loại sự kiện là thay đổi quyền,
        # không phải chi tiết hiển thị.
        events_proj = [e for e in events if e.event_type in {"rescue_case", "signal"}]
        return {
            "zones": zones,
            "events": [e.model_dump(mode="json") for e in events_proj],
            "modes": [m.model_dump(mode="json") for m in modes],
            "next_horizon": horizon,
            "data_quality": [{"code": "fixture_replay", "level": "info", "message": "fixture"}],
        }
    # Manager / Chu quan — full authorized projection
    return {
        "zones": [z.model_dump(mode="json") for z in zones],
        "events": [e.model_dump(mode="json") for e in events],
        "modes": [m.model_dump(mode="json") for m in modes],
        "next_horizon": horizon,
        "data_quality": [{"code": "fixture_replay", "level": "info", "message": "fixture"}],
    }


@router.get("/api/v1/experience/quanverse/snapshot")
def quanverse_snapshot(
    authorization: Annotated[str | None, Header()] = None,
    replay_role: str | None = Query(default=None),
) -> dict[str, Any]:
    """Snapshot theo role — server strip fields trước khi trả.

    `replay_role` chỉ áp dụng khi flag demo/replay bật
    (NHIPQUAN_EXPERIENCE_REPLAY_ROLE=1 hoặc CA_AGENT_MODE=replay) — production
    luôn dùng role từ token, không cho khách tự chọn.
    """
    import os

    replay_allowed = (
        os.environ.get("CA_AGENT_MODE", "") == "replay"
        or os.environ.get("NHIPQUAN_EXPERIENCE_REPLAY_ROLE", "") == "1"
    )
    role_str = _require_role(authorization)
    if replay_role and replay_allowed:
        try:
            role = ExperienceRole(replay_role)
        except ValueError:
            raise HTTPException(status_code=403, detail="role_khong_hop_le") from None
    else:
        try:
            role = ExperienceRole(role_str)
        except ValueError:
            raise HTTPException(status_code=403, detail="role_khong_hop_le") from None
    _rate_limit(role_str)

    proj = _project_role(role)
    snap = LivingCafeSnapshot(
        snapshot_id=f"snap_{int(time.time()*1000)}",
        store_id="quan_01",
        role=role,
        zones=[ZoneProjection.model_validate(z) for z in proj["zones"]],
        events=[PublicEventProjection.model_validate(e) for e in proj["events"]],
        modes=[ModeProjection.model_validate(m) for m in proj["modes"]],
        next_horizon=proj["next_horizon"],
        data_quality=proj["data_quality"],
    )
    return cast(dict[str, Any], snap.model_dump(mode="json"))


@router.get("/api/v1/experience/quanverse/modes")
def quanverse_modes(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_role(authorization)
    data = _fixture("quanverse.json")
    modes = [ModeProjection.model_validate(m) for m in data.get("modes", [])]
    with_state: list[dict[str, Any]] = []
    for m in modes:
        impact = mode_affects(m.mode)
        state = kv_get(f"experience_mode_{m.mode.value}", None) or {}
        active = bool(state.get("active", m.active))
        if active:
            proposal_status = "confirmed"
        else:
            # Đề xuất đã ghi vào kv phải đọc lại được — nếu không, UI hiện
            # "Đang tắt" cho một chế độ đang chờ duyệt.
            proposal_status = str(
                state.get("proposal_status")
                or (m.proposal_status.value if m.proposal_status else "")
                or ""
            )
        with_state.append(
            {
                "mode": m.mode.value,
                "active": active,
                "proposed_by": state.get("confirmed_by") or m.proposed_by,
                "proposal_status": proposal_status,
                "affected_projections": impact,
                "effect": mode_effect(m.mode),
            }
        )
    return {"modes": with_state, "role": role, "can_activate": can_activate_mode(role)}


@router.post("/api/v1/experience/quanverse/modes/{mode}/propose")
def quanverse_mode_propose(
    mode: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đề xuất kích hoạt mode — chưa kích hoạt. Manager-only (theo policy).

    Ghi đề xuất vào kv để `snapshot` thấy được trạng thái "đang chờ duyệt";
    không đụng tới lịch, nhân sự hay bất kỳ lifecycle nào khác.
    """
    user = _require_manager(authorization)
    _rate_limit(str(user))
    try:
        mode_enum = ExperienceMode(mode)
    except ValueError:
        raise HTTPException(status_code=422, detail="mode_khong_hop_le") from None

    key = f"experience_mode_{mode_enum.value}"
    existing = kv_get(key, None)
    if existing and existing.get("active"):
        return {
            "mode": mode_enum.value,
            "proposal_status": "confirmed",
            "affected_projections": mode_affects(mode_enum),
            "confirmed": True,
            "already_active": True,
            "replayable": True,
        }

    kv_set(
        key,
        {
            "active": False,
            "proposal_status": "draft",
            "proposed_by": str(user),
            "at": time.time(),
        },
    )
    return {
        "mode": mode_enum.value,
        "proposal_status": "draft",
        "affected_projections": mode_affects(mode_enum),
        "effect": mode_effect(mode_enum),
        "confirmed": False,
        "replayable": True,
    }


@router.post("/api/v1/experience/quanverse/modes/{mode}/confirm")
def quanverse_mode_confirm(
    mode: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Manager confirm → mode active + emit scoped event (read-only projection)."""
    user = _require_manager(authorization)
    if not can_activate_mode(str(user)):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        mode_enum = ExperienceMode(mode)
    except ValueError:
        raise HTTPException(status_code=422, detail="mode_khong_hop_le") from None
    impacts = mode_affects(mode_enum)
    # Lưu trạng thái mode qua kv (audit lý tưởng), không đổi lifecycle khác.
    key = f"experience_mode_{mode_enum.value}"
    kv_set(key, {"active": True, "confirmed_by": str(user), "at": time.time()})
    return {
        "mode": mode_enum.value,
        "active": True,
        "affected_projections": impacts,
        "audited": True,
        "events": [{"event_type": "mode_change", "mode": mode_enum.value, "source": "replay"}],
    }


@router.post("/api/v1/experience/quanverse/modes/{mode}/deactivate")
def quanverse_mode_deactivate(
    mode: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Manager tắt mode đang bật — idempotent, có ghi vết người tắt.

    Bật mà không tắt được là vòng đời một chiều: quán sẽ kẹt ở chế độ cũ sau
    khi tình huống đã qua. Tắt mode không đụng lịch hay nhân sự.
    """
    user = _require_manager(authorization)
    if not can_activate_mode(str(user)):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        mode_enum = ExperienceMode(mode)
    except ValueError:
        raise HTTPException(status_code=422, detail="mode_khong_hop_le") from None
    key = f"experience_mode_{mode_enum.value}"
    was_active = bool((kv_get(key, None) or {}).get("active"))
    kv_set(key, {"active": False, "deactivated_by": str(user), "at": time.time()})
    return {
        "mode": mode_enum.value,
        "active": False,
        "was_active": was_active,
        "affected_projections": mode_affects(mode_enum),
        "audited": True,
        "events": [{"event_type": "mode_change", "mode": mode_enum.value, "source": "replay"}],
    }


# ── Flavor Universe ───────────────────────────────────────────────────────────


@router.post("/api/v1/experience/quanverse/flavor/recommend")
def flavor_recommend(
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Recommend từ khẩu vị — deterministic catalog scorer, không infer allergy."""
    _require_role(authorization)
    _rate_limit(str(_require_role(authorization)))
    do_ngot = str(body.get("do_ngot") or "vua")
    huong_tra = bool(body.get("huong_tra", False))
    co_sua = bool(body.get("co_sua", True))
    allergies = [str(a) for a in body.get("dietary_allergy") or []]
    if not isinstance(allergies, list):
        allergies = []
    pref = FlavorPreference(do_ngot=do_ngot, huong_tra=huong_tra, co_sua=co_sua, dietary_allergy=allergies)
    try:
        catalog = _fixture("menu-taste-profile.json").get("items", [])
    except FileNotFoundError:
        catalog = []
    results = recommend_from_taste(pref, catalog)
    return {
        "recommendations": [
            {"mon_id": r.mon_id, "ten": r.ten, "score": r.score, "reasons": r.reasons, "allergy_flag": r.allergy_flag}
            for r in results
        ],
        "note": "phù hợp theo khẩu vị bạn khai báo — không phải tư vấn y tế/bỏ sót dị ứng bạn chưa khai",
    }


# ── Preferences (consent) ─────────────────────────────────────────────────────


def _preferences() -> list[dict[str, Any]]:
    rows = kv_get(_PREF_KEY, [])
    return list(rows) if isinstance(rows, list) else []


@router.get("/api/v1/experience/quanverse/preferences")
def preference_list(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Sở thích của chính người gọi — chỉ trả bản ghi do chính họ tạo."""
    user = str(_require_role(authorization))
    rows = [p for p in _preferences() if p.get("owner") == user]
    return {
        "preferences": rows,
        "count": len(rows),
        "note": "Sở thích lưu kèm trạng thái đồng thuận; thu hồi thì ngừng dùng ngay.",
    }


@router.post("/api/v1/experience/quanverse/preferences/propose")
def preference_propose(
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Propose lưu sở thích khách — ghi ở trạng thái CHỜ ĐỒNG THUẬN.

    Không lưu "thật" trước khi khách đồng ý: bản ghi tồn tại để khách nhìn thấy
    đúng thứ đang chờ, và `consent_status=required` là thứ chặn việc dùng nó.
    """
    user = str(_require_role(authorization))
    content = str(body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="thieu_content")
    pref_id = f"pref_prop_{int(time.time() * 1000)}"
    entry = {
        "preference_id": pref_id,
        "content": content,
        "owner": user,
        "consent_status": "required",
        "stored": False,
        "created_at": _iso_at(0),
    }
    kv_mutate(_PREF_KEY, lambda cur: [*(cur or []), entry], [])
    return {
        "preference_proposal_id": pref_id,
        "content": content,
        "needs_consent": True,
        "stored": False,
    }


@router.post("/api/v1/experience/quanverse/preferences/{pref_id}/consent")
def preference_consent(
    pref_id: str,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Khách đồng ý (hoặc từ chối) lưu sở thích — quyết định của chính họ.

    Từ chối = xoá ngay, không giữ bản nháp "để sau". Đồng ý = chuyển sang
    `granted` + `stored=True` để lần ghé sau dùng được.
    """
    user = str(_require_role(authorization))
    grant = bool(body.get("grant", True))
    found: dict[str, Any] = {}

    def _apply(cur: Any) -> list[dict[str, Any]]:
        rows = list(cur or [])
        if not grant:
            return [p for p in rows if p.get("preference_id") != pref_id]
        for p in rows:
            if p.get("preference_id") == pref_id:
                if p.get("owner") != user:
                    raise HTTPException(status_code=403, detail="khong_phai_chu_so_thich")
                p["consent_status"] = "granted"
                p["stored"] = True
                p["granted_at"] = _iso_at(0)
                found.update(p)
        return rows

    rows = kv_mutate(_PREF_KEY, _apply, [])
    if grant and not found:
        raise HTTPException(status_code=404, detail="preference_not_found")
    return {
        "preference_id": pref_id,
        "consent_status": "granted" if grant else "revoked",
        "stored": grant,
        "deleted": not grant,
        "audited": True,
        "remaining": len([p for p in rows if p.get("owner") == user]),
    }


@router.delete("/api/v1/experience/quanverse/preferences/{pref_id}")
def preference_delete(
    pref_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá sở thích — audit; nếu chưa tồn tại vẫn 200 (idempotent)."""
    user = str(_require_role(authorization))

    def _apply(cur: Any) -> list[dict[str, Any]]:
        return [p for p in list(cur or []) if p.get("preference_id") != pref_id]

    rows = kv_mutate(_PREF_KEY, _apply, [])
    return {
        "pref_id": pref_id,
        "deleted": True,
        "audited": True,
        "remaining": len([p for p in rows if p.get("owner") == user]),
    }


# ── Tour + AR-lite ────────────────────────────────────────────────────────────


@router.get("/api/v1/experience/quanverse/tour/{tour_id}")
def quanverse_tour(
    tour_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tour entry point — ủy quyền Phase 05 plan_tour (read-only).

    Trả 404 khi `tour_id` không có trong danh mục (trước đây bỏ qua tham số và
    luôn trả tour mặc định — bug QA đợt 4).
    """
    _require_role(authorization)
    from ca_agents.ag_spatial_memory.tour import danh_muc_tour, plan_tour

    tour = plan_tour(tour_id=tour_id)
    if tour is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "tour_not_found",
                "message": f"Không có tour '{tour_id}'.",
                "hop_le": danh_muc_tour(),
            },
        )
    return cast(dict[str, Any], tour.model_dump(mode="json"))


@router.post("/api/v1/experience/quanverse/ar-session")
def ar_session(
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """AR-lite: capability-gated; không face tracking/SLAM. Fallback map/QR/text."""
    _require_role(authorization)
    qr = str(body.get("qr") or "")
    if not qr:
        raise HTTPException(status_code=422, detail="thieu_qr")
    return {
        "ar_mode": "qr_anchor",
        "anchor_target": qr,
        "requires_camera": False,
        "fallback": "map_or_qr_text",
        "private_ops_not_exposed": True,
    }


# ── Trợ lý Quánverse — tóm tắt tất định + hỏi đáp có căn cứ ──────────────────
#
# Điểm cốt lõi: cả hai route dưới đây đọc dữ liệu TỪ HỆ THỐNG rồi gọi CÙNG một
# hàm `build_brief`. Nhờ vậy bản tóm tắt người dùng thấy trên màn hình và ngữ
# cảnh đưa cho LLM là MỘT khối duy nhất — không có đường nào để hai bên lệch số.


def _payload_for_page(page: QuanversePage, role: ExperienceRole) -> dict[str, Any]:
    """Đọc dữ liệu thật của một trang Quánverse thành tham số cho `build_brief`.

    Mỗi nhánh chỉ ĐỌC và CHUYỂN DẠNG; mọi phép tính nằm trong `ag_quanverse.brief`
    (tất định). Nhờ vậy thêm trang mới chỉ là thêm một nhánh đọc ở đây.
    """
    if page == QuanversePage.LIVING_MAP:
        proj = _project_role(role)

        def _as_dicts(rows: Any) -> list[dict[str, Any]]:
            """`_project_role` trả dict cho khách/nhân viên nhưng Pydantic object
            cho quản lý. Chuẩn hoá về dict để `build_brief` chỉ phải xử lý MỘT
            hình dạng — nếu không, brief sẽ vỡ đúng ở bản chiếu quản lý."""
            out: list[dict[str, Any]] = []
            for row in rows or []:
                if isinstance(row, dict):
                    out.append(row)
                elif hasattr(row, "model_dump"):
                    out.append(cast(dict[str, Any], row.model_dump(mode="json")))
            return out

        return {
            "zones": _as_dicts(proj["zones"]),
            "events": _as_dicts(proj["events"]),
            "modes": _as_dicts(proj["modes"]),
            "horizon": _as_dicts(proj["next_horizon"]),
            "data_quality": _as_dicts(proj["data_quality"]),
        }

    if page == QuanversePage.WAR_ROOM:
        # Mô phỏng gần nhất còn trong cache (nếu có). Cache rỗng là trạng thái
        # bình thường khi chưa ai chạy mô phỏng — brief phải nói rõ, không bịa.
        from ca_api.interfaces.http import war_room as war_room_mod

        latest: dict[str, Any] | None = None
        cache = getattr(war_room_mod, "_SIM_CACHE", None)
        if isinstance(cache, dict) and cache:
            last_key = next(reversed(cache))
            entry = cache[last_key]
            if isinstance(entry, dict) and "options" in entry:
                latest = entry
            elif hasattr(entry, "model_dump"):
                latest = cast(dict[str, Any], entry.model_dump(mode="json"))
        return {"simulation": latest}

    if page == QuanversePage.SHIFT_RESCUE:
        from ca_api.interfaces.http import shift_rescue as rescue_mod

        cases = getattr(rescue_mod, "_CASES", None)
        case: dict[str, Any] | None = None
        if isinstance(cases, dict) and cases:
            entry = cases[next(reversed(cases))]
            if hasattr(entry, "model_dump"):
                case = cast(dict[str, Any], entry.model_dump(mode="json"))
            elif isinstance(entry, dict):
                case = entry
        return {"case": case, "shifts": []}

    if page == QuanversePage.RULES:
        from ca_api.interfaces.http import experience_rules as rules_mod

        store = getattr(rules_mod, "_CANDIDATES", None)
        candidates: list[dict[str, Any]] = []
        if isinstance(store, dict):
            for entry in store.values():
                if hasattr(entry, "model_dump"):
                    candidates.append(cast(dict[str, Any], entry.model_dump(mode="json")))
                elif isinstance(entry, dict):
                    candidates.append(entry)
        elif isinstance(store, list):
            for entry in store:
                if hasattr(entry, "model_dump"):
                    candidates.append(cast(dict[str, Any], entry.model_dump(mode="json")))
                elif isinstance(entry, dict):
                    candidates.append(entry)
        return {"candidates": candidates, "sources": []}

    if page == QuanversePage.SPATIAL_MEMORY:
        # Neo đến từ READ ADAPTER (cùng nguồn với `GET /api/v1/experience/map`),
        # KHÔNG nằm trong fixture `spatial-memory.json` — fixture đó chỉ có
        # `memories`/`audit`/`tour_route`. Đọc sai nguồn sẽ luôn ra "0 neo" dù
        # quán có đủ neo, và brief sẽ nói dối về trạng thái thật của hệ thống.
        from ca_agents.grand_experience.adapter import resolve_experience_read_adapter

        adapter = resolve_experience_read_adapter()
        anchors = [a.model_dump(mode="json") for a in adapter.list_anchors()]
        data = _fixture("spatial-memory.json")
        counts: dict[str, int] = {}
        for row in data.get("memories") or []:
            if str(row.get("status") or "") == "confirmed":
                aid = str(row.get("anchor_id") or "")
                counts[aid] = counts.get(aid, 0) + 1
        return {"anchors": anchors, "memory_counts": counts, "selected_anchor": None}

    return {}


@router.get("/api/v1/experience/quanverse/brief/{page}")
def quanverse_brief(
    page: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tóm tắt TẤT ĐỊNH của một trang Quánverse — không gọi LLM.

    Đây là dữ liệu để UI tự vẽ (không cần chờ mạng tới provider), và cũng là
    ngữ cảnh mà `POST /ask` dùng. Tách riêng để panel tóm tắt luôn hiện được kể
    cả khi không có API key LLM nào.
    """
    from ca_agents.ag_quanverse.brief import build_brief

    role_str = _require_role(authorization)
    _rate_limit(role_str)
    try:
        page_enum = QuanversePage(page)
    except ValueError:
        raise HTTPException(status_code=404, detail="trang_khong_ho_tro") from None
    try:
        role = ExperienceRole(role_str)
    except ValueError:
        role = ExperienceRole.NHAN_VIEN

    payload = _payload_for_page(page_enum, role)
    brief = build_brief(page_enum, **payload)
    return cast(dict[str, Any], brief.model_dump(mode="json"))


@router.post("/api/v1/experience/quanverse/ask")
def quanverse_ask(
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Hỏi Trợ lý Quánverse về MỘT trang — trả lời có căn cứ, không bịa số.

    Ở chế độ replay (mặc định) câu trả lời dựng thẳng từ brief tất định. Ở chế
    độ live, LLM chỉ được diễn đạt lại brief và phải qua cổng grounding: câu trả
    lời nhắc số không có trong brief sẽ bị BỎ và ghi lại lý do.
    """
    from ca_agents.ag_quanverse.assistant import answer_question
    from ca_agents.ag_quanverse.brief import build_brief

    role_str = _require_role(authorization)
    _rate_limit(role_str)

    raw_page = str(body.get("page") or "")
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="thieu_cau_hoi")
    if len(question) > 500:
        raise HTTPException(status_code=422, detail="cau_hoi_qua_dai")
    try:
        page_enum = QuanversePage(raw_page)
    except ValueError:
        raise HTTPException(status_code=404, detail="trang_khong_ho_tro") from None
    try:
        role = ExperienceRole(role_str)
    except ValueError:
        role = ExperienceRole.NHAN_VIEN

    payload = _payload_for_page(page_enum, role)
    brief = build_brief(page_enum, **payload)
    answer = answer_question(page=page_enum, question=question, brief=brief)
    return cast(dict[str, Any], answer.model_dump(mode="json"))