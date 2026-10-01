"""HTTP router — Quán tự viết luật (plan 260920-1442 Phase 04).

- GET  /experience/rules/candidates — danh sách candidate
- POST /experience/rules/discover — chạy discover (deterministic)
- GET  /experience/rules/{candidate_id}/evidence — evidence timeline
- POST /experience/rules/{candidate_id}/shadow-test — shadow test cô lập
- POST /experience/rules/{candidate_id}/confirm — confirm (manager) → vong_doi
- POST /experience/rules/{candidate_id}/reject — reject
- POST /experience/rules/{candidate_id}/revoke — revoke active rule

Confirm/reject ủy quyền vong_doi lifecycle — không có state machine thứ hai.
Không rule nào tự kích hoạt (ADR-008).
"""

from __future__ import annotations

import threading
import time
from typing import Annotated, Any, cast

from ca_agents.ag_rule_learning.discover import (
    DecisionSignal,
    discover_rule_candidates,
    to_vf_condition,
)
from ca_agents.ag_rule_learning.evidence import build_evidence_readmodel
from ca_agents.ag_rule_learning.shadow_test import run_shadow_test
from ca_agents.grand_experience.replay import FixtureReader
from ca_contracts import RuleCandidate
from ca_playbook.vong_doi import de_xuat as vong_doi_de_xuat
from ca_playbook.vong_doi import go_luat, list_luat, save_luat
from ca_playbook.vong_doi import kiem_chung as vong_doi_kiem_chung
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ca_api.interfaces.http.sprint3 import _require_manager, _require_role

router = APIRouter(tags=["experience_rules"])

_LOCK = threading.Lock()
_CANDIDATES: dict[str, dict[str, Any]] = {}
_USER_TS: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_REQ = 15


def clear_rule_state() -> None:
    with _LOCK:
        _CANDIDATES.clear()
        _USER_TS.clear()


@router.post("/api/v1/experience/rules/reset")
def rules_reset(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá ứng viên trong bộ nhớ — CHỈ khi bật chế độ replay/demo.

    Vì sao cần: `_CANDIDATES` là store trong BỘ NHỚ, sống suốt phiên server. Mỗi
    bài e2e đều chạy cùng một server nên trạng thái của bài trước rò sang bài sau:
    bài "từ chối ứng viên" chạy sau bài "thu hồi luật" sẽ thấy ứng viên đã ở trạng
    thái `revoked` (không còn nút Từ chối), rồi đỏ.

    Trước đây lỗi này bị CHE vì `discover` luôn ghi đè `status: "draft"` — mỗi lần
    bấm "Tìm quyết định lặp lại" là trạng thái cũ bị xoá. Nhưng chính hành vi ghi
    đè đó là lỗi thật ở phần sản phẩm (bấm discover lần hai là mất luật đã ban
    hành, không thu hồi được). Đã sửa gốc, nên cần cơ chế cách ly tường minh.

    Cùng khuôn với `clear_rule_state()` (pytest dùng) và `replay_role` của
    quanverse: production KHÔNG được phép gọi. Không có flag thì trả 403.
    """
    import os

    allowed = (
        os.environ.get("CA_AGENT_MODE", "") == "replay"
        or os.environ.get("NHIPQUAN_EXPERIENCE_REPLAY_ROLE", "") == "1"
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="chi_cho_phep_o_che_do_replay")
    _require_manager(authorization)
    clear_rule_state()
    return {"reset": True, "replayable": True}


def _rate_limit(user_id: str) -> None:
    import os

    if os.environ.get("NHIPQUAN_DISABLE_RATE_LIMIT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return
    now = time.time()
    with _LOCK:
        recent = [t for t in _USER_TS.get(user_id, []) if now - t < _WINDOW_S]
        if len(recent) >= _MAX_REQ:
            raise HTTPException(status_code=429, detail="rate_limit_exceeded")
        recent.append(now)
        _USER_TS[user_id] = recent


def _decisions() -> list[dict[str, Any]]:
    reader = FixtureReader()
    data = cast(dict[str, Any], reader.read_json_path("rule-learning.json"))
    return list(data.get("decisions", []))


def _snapshot_hash() -> str:
    reader = FixtureReader()
    data = cast(dict[str, Any], reader.read_json_path("rule-learning.json"))
    return str(data.get("snapshot_hash") or "snap_rule_fixture")


@router.get("/api/v1/experience/rules/candidates")
def rules_candidates(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Ứng viên luật — CHỈ quản lý/chủ quán (bug QA đợt 6 #39).

    UI `/quanverse/rules` nằm trong `MANAGER_ONLY` nhưng API chỉ đòi token.
    """
    _require_manager(authorization)
    with _LOCK:
        items = [
            {"candidate_id": cid, "sentence": c["sentence"], "confidence": c["confidence"], "status": c.get("status", "draft")}
            for cid, c in _CANDIDATES.items()
        ]
    return {"candidates": items}


@router.post("/api/v1/experience/rules/discover")
def rules_discover(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chạy discover deterministic trên fixture decisions."""
    _require_manager(authorization)
    _rate_limit(str(_require_manager(authorization)))
    rows = _decisions()
    signals = [
        DecisionSignal(
            signal_id=str(r["event_id"]),
            decision=str(r["decision"]),
            day_part=r.get("day_part"),
            station=r.get("station"),
            skill=r.get("skill"),
            demand_band=r.get("demand_band"),
            absence_type=r.get("absence_type"),
            outcome=str(r.get("outcome") or ""),
            source_kind=str(r.get("event_type") or "decision"),
            occurred_at=str(r.get("occurred_at") or ""),
        )
        for r in rows
    ]
    candidates = discover_rule_candidates(signals, snapshot_hash=_snapshot_hash())
    with _LOCK:
        for c in candidates:
            cid = c.candidate_id
            # KHÔNG ghi đè ứng viên đã có. Bản trước luôn gán `status: "draft"`,
            # nên bấm "Tìm quyết định lặp lại" lần thứ hai sẽ XOÁ vòng đời của ứng
            # viên đã duyệt: `confirmed` (đã ban hành luật) tụt về `draft`, mất luôn
            # `shadow_result`. Hệ quả thấy được trên giao diện: sau khi duyệt, nút
            # "Thu hồi luật" chỉ hiện khi status là `confirmed` — chạy lại discover
            # là nút biến mất, quán không thu hồi được luật của chính mình.
            # Discover chỉ nên THÊM ứng viên mới, không sửa cái đã quyết.
            if cid in _CANDIDATES:
                continue
            _CANDIDATES[cid] = {
                **c.model_dump(mode="json"),
                "status": "draft",
            }
    return {
        "discovered": [c.candidate_id for c in candidates],
        "count": len(candidates),
        "sources": "fixture_replay",
    }


@router.get("/api/v1/experience/rules/{candidate_id}/evidence")
def rules_evidence(
    candidate_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    with _LOCK:
        item = _CANDIDATES.get(candidate_id)
    if not item:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    candidate = RuleCandidate.model_validate(item)
    tl = build_evidence_readmodel(candidate, _decisions())
    return {
        "candidate_id": candidate_id,
        "timeline": tl.events,
        "repeated_decisions": tl.repeated_decisions,
        "actors": tl.actors,
        "affected_shifts": tl.affected_shifts,
        "counterexamples": tl.counterexamples,
        "confidence": tl.confidence,
    }


class ShadowBody(BaseModel):
    pass


@router.post("/api/v1/experience/rules/{candidate_id}/shadow-test")
def rules_shadow_test(
    candidate_id: str,
    body: ShadowBody | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    with _LOCK:
        item = _CANDIDATES.get(candidate_id)
    if not item:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    candidate = RuleCandidate.model_validate(item)
    result = run_shadow_test(
        candidate,
        historical_events=_decisions(),
        base_snapshot={"hard_constraints_ok": True, "luat_ap_dung": 0},
    )
    with _LOCK:
        item["shadow_result"] = result.model_dump(mode="json")
        _CANDIDATES[candidate_id] = item
    return {"candidate_id": candidate_id, "shadow": result.model_dump(mode="json")}


@router.post("/api/v1/experience/rules/{candidate_id}/confirm")
def rules_confirm(
    candidate_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Confirm → đưa candidate vào vong_doi (bước 3). Không tự kích hoạt."""
    _require_manager(authorization)
    with _LOCK:
        item = _CANDIDATES.get(candidate_id)
    if not item:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    if not item.get("shadow_result"):
        raise HTTPException(status_code=409, detail="chua_chay_shadow_test")

    # Bridge vào vong_doi 8-step — sole writer.
    mau = {
        "mau": item["candidate_id"],
        "loai_luat": "nhu_cau_ca",
        "n": len(item["evidence_refs"]),
        "bang_chung": item["evidence_refs"],
        "nguon": "fixture_replay",
    }
    luat = vong_doi_de_xuat(
        mau,
        ban_nhap={
            "cau": item["sentence"],
            "dieu_kien": to_vf_condition(item["condition"]),
            "bang_chung": item["evidence_refs"],
        },
    )
    if luat is None:
        raise HTTPException(status_code=409, detail="khong_du_bang_chung")
    verified = vong_doi_kiem_chung(luat)
    if verified.get("trang_thai") == "loai":
        raise HTTPException(status_code=422, detail="vf_rule_loai")

    # Publish vào kho luật của quán.
    #
    # Trước đây hàm này chỉ trả về trạng thái vừa kiểm chứng rồi quên luật:
    # `luat` chỉ sống trong biến cục bộ, không lần nào ghi xuống `cam_nang.json`.
    # Hệ quả: "xác nhận" xong luật biến mất, và `revoke` — vốn đòi trạng thái
    # `hieu_luc` — vĩnh viễn trả 409 `chua_phai_luat_hieu_luc`. Quán không thu
    # hồi được thứ mình chưa từng thực sự ban hành.
    #
    # Ở đây ghi xuống với trạng thái `qua_vf_rule`: luật đã qua kiểm chứng và
    # nằm trong kho, nhưng CHƯA hiệu lực — đúng ADR-008 (AI đề xuất, người
    # quyết định; không tự kích hoạt tham số lõi).
    published = verified
    published["nguon"] = "quan_tu_viet_luat"
    existing = [x for x in list_luat() if x.get("id") != published["id"]]
    save_luat([*existing, published])

    with _LOCK:
        item["status"] = "confirmed"
        item["playbook_ref"] = published["id"]
        # Ghi cả trạng thái playbook: `revoke` đọc lại từ đây để biết luật đã
        # thực sự được ban hành hay chưa.
        item["playbook_status"] = published["trang_thai"]
        _CANDIDATES[candidate_id] = item
    return {
        "candidate_id": candidate_id,
        "playbook_id": published["id"],
        "playbook_status": published["trang_thai"],
        "playbook_buoc": published["buoc"],
        "not_auto_activated": True,
    }


@router.post("/api/v1/experience/rules/{candidate_id}/reject")
def rules_reject(
    candidate_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    with _LOCK:
        item = _CANDIDATES.get(candidate_id)
    if not item:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    item["status"] = "rejected"
    _CANDIDATES[candidate_id] = item
    return {"candidate_id": candidate_id, "status": "rejected"}


@router.post("/api/v1/experience/rules/{candidate_id}/revoke")
def rules_revoke(
    candidate_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Thu hồi luật đã ban hành — dùng `vong_doi.go_luat`, không xoá vết.

    Nhận cả hai trạng thái hợp lệ: `hieu_luc` (luật đã chạy thật, do 8 bước
    phê duyệt) và `qua_vf_rule` (luật vừa xác nhận từ bề mặt Trải nghiệm).
    Chỉ chặn khi luật chưa từng được ban hành — thu hồi một thứ chưa tồn tại
    là thao tác vô nghĩa, và im lặng cho qua sẽ che mất lỗi ở tầng gọi.
    """
    user = _require_manager(authorization)
    with _LOCK:
        item = _CANDIDATES.get(candidate_id)
    if not item:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    revocable = {"hieu_luc", "qua_vf_rule"}
    status = str(item.get("playbook_status") or "")
    if status not in revocable:
        raise HTTPException(status_code=409, detail="chua_phai_luat_da_ban_hanh")

    # Gỡ khỏi kho luật của quán — nguồn sự thật là `cam_nang.json`, không phải
    # cache trong bộ nhớ, nên phải cập nhật cả hai.
    playbook_ref = str(item.get("playbook_ref") or "")
    revoked_rows = 0
    if playbook_ref:
        rows = list_luat()
        for i, row in enumerate(rows):
            if row.get("id") == playbook_ref:
                rows[i] = go_luat(row, ai=str(user))
                revoked_rows += 1
        if revoked_rows:
            save_luat(rows)

    with _LOCK:
        item["status"] = "revoked"
        item["playbook_status"] = "da_go"
        _CANDIDATES[candidate_id] = item
    return {
        "candidate_id": candidate_id,
        "status": "revoked",
        "playbook_id": playbook_ref,
        "playbook_revoked": bool(revoked_rows),
        "reason_required": True,
    }