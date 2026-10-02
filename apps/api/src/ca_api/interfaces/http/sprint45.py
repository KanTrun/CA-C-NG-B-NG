"""Sprint 4–5 HTTP — lifecycle, audit, inbox, fairness, playbook, SOP, QR, swap."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, cast

try:
    from datetime import UTC, date, datetime, timedelta
except ImportError:
    from datetime import date, datetime, timedelta, timezone

    UTC = timezone.utc

from ca_agents.ag_handover import extract as extract_handover
from ca_agents.ag_rule import propose as propose_rule
from ca_agents.ag_sop import answer as sop_answer
from ca_agents.ag_sop.context import load_all_buoc
from ca_agents.ag_sop.ops import default_ops_context, ops_context_from_dict
from ca_agents.ag_waste import cluster as cluster_waste
from ca_agents.smart_swap import find_swap_candidates
from ca_gates import detect_number_conflicts, present_conflict, validate_num
from ca_playbook import (
    count_luat_that_quan,
    de_xuat,
    derive_rule_from_edits,
    duyet,
    enrich_luat_ui,
    go_luat,
    is_demo_luat,
    kiem_chung,
    list_luat,
    list_sua,
    pipeline_snapshot,
    record_sua,
    save_luat,
    sua_rows_for_mau,
    tap_su_tu_sua,
    tim_mau,
)
from ca_solver.fairness import AXES, update_debt_from_assignment, zero_debt
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ca_api.context_providers import ngay_hom_nay_vn
from ca_api.interfaces.http.sprint3 import (
    _known_ca,
    _known_nv,
    _require_chu_quan,
    _require_manager,
    _require_role,
)
from ca_api.nguyen_lieu import (
    chuan_hoa_ma,
    la_ma_chuan,
    loc_dong_tieu_thu,
    tim_ma_theo_ten,
    tong_hop_tieu_thu,
)
from ca_api.nguyen_lieu import (
    don_vi as don_vi_nguyen_lieu,
)
from ca_api.nhan_vien import list_nhan_vien_ops
from ca_api.orchestration import Clock
from ca_api.persist import (
    audit_add,
    audit_list,
    authoritative_assignments_list,
    availability_confirmed_list,
    ghi_diem_danh,
    kv_get,
    kv_mutate,
    kv_set,
    list_users,
    open_shift_create,
    open_shift_list,
    schedule_run_get,
    shift_application_claim_first,
    thong_bao_lich_ack,
    thong_bao_lich_create_for_week,
    thong_bao_lich_list,
)
from ca_api.persist import session as auth_session
from ca_api.services.chat_ws import notify_ops_changed
from ca_api.services.scheduling_service import resolve_schedule_gaps, run_authoritative_schedule

router = APIRouter()
ROOT = Path(__file__).resolve().parents[6]
SEED = ROOT / "data" / "seed" / "sample.json"


def _lich_out() -> Path:
    """Output solver — đọc MỖI LẦN GỌI, không phải lúc import module.

    Conftest set ``NHIPQUAN_LICH_TUAN_OUT`` per-test (sau import), nên nếu
    đọc env một lần lúc import thì test vẫn ghi đè ``data/out/lich_tuan.json``
    thật của quán. Đọc mỗi lần gọi mới trỏ đúng tmp_path của test.
    """
    env = os.environ.get("NHIPQUAN_LICH_TUAN_OUT")
    if env:
        return Path(env)
    return ROOT / "data" / "out" / "lich_tuan.json"
_clock = Clock()
_THU_MAP = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
_VI_TRI_VI = {
    "thu_ngan": "Thu ngân",
    "pha_che": "Pha chế",
    "phuc_vu": "Phục vụ",
    "kho": "Kho",
    "quan_ly_ca": "Quản lý ca",
    "da_nang": "Đa năng",
}
_ALLOWED = {
    "may_sinh": {"nhap"},
    "nhap": {"dang_giai"},
    "dang_giai": {"cho_duyet", "nhap"},
    "cho_duyet": {"da_duyet", "da_cong_bo", "nhap"},
    "da_duyet": {"da_cong_bo", "nhap"},
    "da_cong_bo": {"da_dong", "nhap"},
    "da_dong": {"nhap"},
}
# Tên MÔ TẢ cho cùng ma trận trên — `main.py` import tên này để hai đường vòng đời
# dùng chung một nguồn. `_ALLOWED` giữ lại vì nhiều chỗ trong tệp này đã tham chiếu.
#
# Ô `da_cong_bo` CỐ Ý cho phép `nhap`: mở lại lịch đã công bố là nghiệp vụ thật
# (quán đổi ca đột xuất). Bản `main.py` từng thiếu `nhap` ở đây — xem ADR-020.
_SHARED_ALLOWED: dict[str, set[str]] = _ALLOWED
_REASON = {
    "cuoi_tuan": "R-WKND",
    "dem": "R-NIGHT",
    "gio": "R-HRS",
    "vun": "R-SHORT",
}


def _la_ban_ghi_mau(row: Any) -> bool:
    """Một bản ghi là dữ liệu mẫu khi mang nhãn fixture hoặc id fx_."""
    if not isinstance(row, dict):
        return False
    if row.get("nguon") == "mo_phong_fixture":
        return True
    return str(row.get("id") or "").startswith("fx_")


def _co_du_lieu_mau(rows: Any) -> bool:
    """True khi danh sách có ít nhất một bản ghi fixture — để UI gắn nhãn mẫu."""
    if not isinstance(rows, list):
        return False
    return any(_la_ban_ghi_mau(r) for r in rows)


def _audit(hanh: str, ai: str, payload: dict[str, Any]) -> None:
    audit_add(_clock.now_iso(), ai, hanh, payload)


def _hao_hut_hom_nay() -> dict[str, Any]:
    """Bản rút gọn của hao hụt hôm nay cho bảng Hôm nay.

    Gọi **đúng hàm** mà `/api/v1/hao-hut` và agent mẹ gọi
    (`ca_agents.ag_waste.tinh_tu_nguon`), nên con số trên trang Hôm nay không thể
    lệch với trang Hao phí. Chỉ trả phần cần cho một dòng tóm tắt; chi tiết theo
    nguyên liệu vẫn nằm ở `/hao-phi`.
    """
    from ca_agents.ag_waste import tinh_tu_nguon

    from ca_api.interfaces.http.hao_hut import _ds, _ds_don, _nguong
    from ca_api.persist import menu_list

    tom_tat = tinh_tu_nguon(
        kiem_ke=_ds("kiem_ke"),
        don_quay=_ds_don(),
        menu=menu_list(gom_an=True),
        waste_notes=_ds("waste_notes"),
        nguong=_nguong(),
        ky="hom_nay",
    )
    vuot = [d for d in tom_tat.dong if d.muc_do in {"canh_bao", "nghiem_trong"}]
    return {
        "co_du_lieu": tom_tat.tong_dong > 0,
        "tong_dong": tom_tat.tong_dong,
        "so_nghiem_trong": tom_tat.so_nghiem_trong,
        "so_canh_bao": tom_tat.so_canh_bao,
        "so_thieu_du_lieu": tom_tat.so_thieu_du_lieu,
        "ty_le_trung_binh": tom_tat.ty_le_trung_binh,
        "mat_hang_vuot": [
            {"ten": d.ten or d.mat_hang, "ty_le": d.ty_le_phan_tram, "muc_do": d.muc_do}
            for d in vuot[:5]
        ],
        "nguyen_nhan_hang_dau": [
            {"ten": c.ten, "so_lan": c.so_lan} for c in tom_tat.nguyen_nhan_hang_dau[:3]
        ],
    }


def _week_value(key: str, tuan_iso: str, default: Any) -> Any:
    """Read week-scoped KV with a one-way compatible fallback to legacy data."""
    raw = kv_get(key, None)
    if isinstance(raw, dict) and raw:
        return raw.get(tuan_iso, default)
    if key.endswith("_by_week"):
        legacy = kv_get(key.removesuffix("_by_week"), None)
        if legacy is not None:
            # Legacy doc có tuan_iso: chỉ fallback khi đúng tuần được hỏi,
            # tránh tuần mới thừa hưởng trạng thái của tuần cũ.
            if isinstance(legacy, dict) and "tuan_iso" in legacy:
                return legacy if legacy.get("tuan_iso") == tuan_iso else default
            return legacy
    return default


def _set_week_value(key: str, tuan_iso: str, value: Any) -> None:
    def mut(raw: dict[str, Any]) -> dict[str, Any]:
        raw[tuan_iso] = value
        return raw

    kv_mutate(key, mut, {})


def _publish_schedule_notification(week: str, store_id: str = "quan_01") -> int:
    """Persist one exact-week notification for each active real account."""
    users = [
        user
        for user in list_users(store_id=store_id)
        if user.get("role") in {"nhan_vien", "quan_ly", "chu_quan"}
        and str(user.get("status") or "active") == "active"
        and str(user.get("nv_id") or "")
    ]
    created = 0
    manager_ids = [str(u["nv_id"]) for u in users if u.get("role") in {"quan_ly", "chu_quan"}]
    staff_ids = [str(u["nv_id"]) for u in users if u.get("role") == "nhan_vien"]

    if manager_ids:
        created += thong_bao_lich_create_for_week(
            tuan_iso=week,
            su_kien="da_cong_bo",
            tieu_de=f"Lịch tuần {week} đã được công bố",
            noi_dung="Lịch mới đã sẵn sàng. Mở để xem bảng phân công toàn quán.",
            url=f"/lich-tuan?tuan={week}",
            nv_ids=manager_ids,
            store_id=store_id,
        )
    if staff_ids:
        created += thong_bao_lich_create_for_week(
            tuan_iso=week,
            su_kien="da_cong_bo",
            tieu_de=f"Lịch tuần {week} đã được công bố",
            noi_dung="Lịch mới đã sẵn sàng. Mở để xem ca làm và xác nhận lịch của bạn.",
            url=f"/toi?tuan={week}",
            nv_ids=staff_ids,
            store_id=store_id,
        )
    return created


@router.get("/api/v1/lich/thong-bao")
def lich_notifications(
    unread_only: bool = False,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    session = _require_role_session(authorization)
    items = thong_bao_lich_list(str(session.get("nv_id") or ""), unread_only=unread_only)
    return {"ok": True, "notifications": items, "unread": sum(1 for item in items if not item.get("da_xem"))}


@router.post("/api/v1/lich/thong-bao/{notification_id}/ack")
def ack_lich_notification(
    notification_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    session = _require_role_session(authorization)
    return {"ok": thong_bao_lich_ack(notification_id, str(session.get("nv_id") or ""))}


def _previous_week(tuan_iso: str) -> str | None:
    try:
        year, week = tuan_iso.split("-W")
        previous = date.fromisocalendar(int(year), int(week), 1) - timedelta(days=7)
        iso = previous.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except (TypeError, ValueError):
        return None


def _run_solver(
    tuan_iso: str | None = None,
    *,
    extra_pin: tuple[str, str] | None = None,
    confirmed_availability: dict[str, dict[str, list[str]]] | None = None,
    store_id: str = "quan_01",
    time_limit_s: float | None = None,
) -> dict[str, Any]:
    """Compatibility entrypoint for older imports and focused solver tests."""
    from ca_api.services.solver_adapter import run_solver

    return run_solver(
        tuan_iso,
        extra_pin=extra_pin,
        confirmed_availability=confirmed_availability,
        store_id=store_id,
        time_limit_s=time_limit_s,
    )


def _tuan_hien_tai_iso() -> str:
    """Tuần ISO hiện tại theo đồng hồ thật (fallback khi KV chưa có lifecycle)."""
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _life(tuan_iso: str | None = None, *, store_id: str = "quan_01") -> dict[str, Any]:
    """Trạng thái lịch tuần — SSOT là kv `lich_tuan_lifecycle_by_week`; fallback
    đọc kv `lich_tuan_lifecycle` (toàn cục) khi tuần TRÙNG, rồi `lifecycle` cũ;
    thiếu hẳn thì về tuần ISO HIỆN TẠI (trước đây hardcode `2026-W01`)."""
    requested = tuan_iso
    if requested:
        by_week = kv_get("lich_tuan_lifecycle_by_week", {})
        week_key = requested if store_id == "quan_01" else f"{store_id}:{requested}"
        if isinstance(by_week, dict) and isinstance(by_week.get(week_key), dict):
            return cast(dict[str, Any], by_week[week_key])

        # FALLBACK QUAN TRỌNG — nếu thiếu, KHÔNG DUYỆT ĐƯỢC LỊCH.
        #
        # Khoá theo tuần CÓ THỂ RỖNG dù tuần đó đã được duyệt từ trước: đường
        # duyệt cũ (`copilot_duyet`, và `main.py` trước khi nhất hoá) chỉ ghi
        # `lich_tuan_lifecycle` — khoá TOÀN CỤC — mà không ghi bản theo tuần.
        #
        # Hệ quả THẬT đã gặp: màn lịch đọc khoá toàn cục nên hiện `da_duyet`,
        # nhưng `_life("2026-W40")` rơi vào nhánh `nhap` cứng bên dưới → phép
        # chuyển `cho_duyet -> da_duyet` thành `nhap -> da_duyet` → API trả
        # 409 `illegal:nhap->da_duyet` → quản lý bấm "Duyệt và công bố" không
        # có tác dụng.
        #
        # CHỈ nhận fallback khi khoá toàn cục mô tả ĐÚNG tuần đang hỏi. Nếu nó
        # thuộc tuần khác thì bỏ qua — không mượn trạng thái tuần khác (đúng
        # lỗi mà `_week_value` từng mắc: tuần mới thừa hưởng trạng thái tuần cũ).
        if store_id == "quan_01":
            for key in ("lich_tuan_lifecycle", "lifecycle"):
                doc = kv_get(key, None)
                if (
                    isinstance(doc, dict)
                    and doc.get("trang_thai")
                    and str(doc.get("tuan_iso") or "") == requested
                ):
                    return cast(dict[str, Any], doc)

        return {"tuan_iso": requested, "trang_thai": "nhap", "nguon": "quan"}
    if store_id != "quan_01":
        return {"tuan_iso": _tuan_hien_tai_iso(), "trang_thai": "may_sinh", "nguon": "quan"}
    moi = kv_get("lich_tuan_lifecycle", None)
    if isinstance(moi, dict) and moi.get("trang_thai"):
        return cast(dict[str, Any], moi)
    cu = kv_get("lifecycle", None)
    if isinstance(cu, dict) and cu.get("trang_thai"):
        return cast(dict[str, Any], cu)
    return {"tuan_iso": _tuan_hien_tai_iso(), "trang_thai": "may_sinh", "nguon": "quan"}


def _save_life(
    doc: dict[str, Any],
    *,
    store_id: str = "quan_01",
    dong_bo_toan_cuc: bool = True,
) -> None:
    # Ghi CẢ HAI khóa: mới là nguồn sự thật, cũ giữ đồng bộ cho tiến trình
    # còn đọc chưa nâng cấp (đọc soft ở trên tự bỏ qua khi mới tồn tại).
    #
    # `dong_bo_toan_cuc=False` khi ghi trạng thái cho một tuần KHÁC tuần đang
    # làm việc: khoá toàn cục là con trỏ "tuần hiện tại" mà nhiều màn hình đọc
    # ngầm định, gán nó sang tuần khác sẽ khiến luồng nhận/nhả ca và công bố
    # lịch nhảy tuần. Bản theo tuần (`lich_tuan_lifecycle_by_week`) mới là chỗ
    # đúng để lưu trạng thái của tuần đích.
    if store_id == "quan_01" and dong_bo_toan_cuc:
        kv_set("lich_tuan_lifecycle", doc)
        kv_set("lifecycle", doc)
    week = str(doc.get("tuan_iso") or _tuan_hien_tai_iso())
    _set_week_value(
        "lich_tuan_lifecycle_by_week",
        week if store_id == "quan_01" else f"{store_id}:{week}",
        doc,
    )


def _seed_inbox() -> list[dict[str, Any]]:
    items = kv_get("inbox_rang_buoc", [])
    if items:
        return cast(list[dict[str, Any]], items)
    if os.environ.get("NHIPQUAN_INBOX_SEED_FIXTURE", "0").strip().lower() not in {"1", "true", "yes"}:
        return []
    items = [
        {
            "id": f"in_{i + 1}",
            "agent": "ag_msg" if i % 2 == 0 else "ag_handover",
            "tom_tat": f"Ràng buộc #{i + 1} — chờ duyệt",
            "trang_thai": "cho_duyet",
            "nguon": "mo_phong_fixture",
        }
        for i in range(10)
    ]
    kv_set("inbox_rang_buoc", items)
    return items


def _phan(tuan_iso: str | None = None) -> dict[str, list[str]]:
    week = tuan_iso or str(_life().get("tuan_iso") or _tuan_hien_tai_iso())
    stored = _week_value("phan_cong_by_week", week, None)
    if stored:
        return cast(dict[str, list[str]], stored)
    out = _lich_out()
    if out.exists():
        doc = json.loads(out.read_text(encoding="utf-8"))
        if not doc.get("tuan_iso") or doc.get("tuan_iso") == week:
            return cast(dict[str, list[str]], doc.get("phan_cong", {}))
    return {}


class LifeBody(BaseModel):
    to: str
    ly_do: str | None = None
    tuan_iso: str | None = None


class InboxBody(BaseModel):
    quyet_dinh: str
    ca_id: str | None = None
    doi_tac_nv_id: str | None = None
    ap_dat: bool = False
    tu_dong_xep_lich: bool = False
    ly_do: str | None = Field(default=None, max_length=500)


class SmartApproveBody(BaseModel):
    selected_nv_id: str | None = None
    ap_dat: bool = True


class HandoverBody(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    alt_claim: str | None = Field(default=None, max_length=5000)


class SopBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    ngu_canh: dict[str, str] | None = None
    chi_luat_that: bool = False


class SwapBody(BaseModel):
    a: str
    b: str
    ca_id: str
    # Tuần của ca cần đổi — mặc định tuần hiện tại của quán. Cho phép ghi rõ
    # để phiếu không rơi nhầm tuần khi người mở đang xem tuần khác.
    tuan: str | None = None


class OpenShiftBody(BaseModel):
    schedule_run_id: str
    tuan_iso: str
    ca_id: str
    deadline_at: str | None = None


class ShiftClaimBody(BaseModel):
    open_shift_id: str


class ResolveScheduleBody(BaseModel):
    schedule_run_id: str
    tuan_iso: str
    expected_fingerprint: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    ca_id: str | None = None
    nv_id: str | None = None


class DuyetLuatBody(BaseModel):
    id: str
    ok: bool = True


class QrBody(BaseModel):
    nv_id: str
    ca_id: str = "w1_c01"


@router.get("/api/v1/lich/lifecycle")
def lich_life(
    authorization: Annotated[str | None, Header()] = None,
    tuan: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_role(authorization)
    session = auth_session(authorization) or {}
    return _life(tuan, store_id=str(session.get("store_id") or "quan_01"))


@router.post("/api/v1/lich/lifecycle")
async def lich_transition(
    body: LifeBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    session = auth_session(authorization) or {}
    store_id = str(session.get("store_id") or "quan_01")
    current = _life(store_id=store_id)
    week = (body.tuan_iso or "").strip() or str(current.get("tuan_iso") or "2026-W01")
    doc = _life(week, store_id=store_id) if body.tuan_iso else current
    cur = doc.get("trang_thai", "may_sinh")
    if body.to not in _ALLOWED.get(cur, set()):
        raise HTTPException(status_code=409, detail=f"illegal:{cur}->{body.to}")
    if body.to == "da_dong":
        _require_chu_quan(authorization)
    reopening_locked = cur in {"da_duyet", "da_cong_bo", "da_dong"} and body.to == "nhap"
    if reopening_locked:
        if cur == "da_dong":
            _require_chu_quan(authorization)
        if not body.ly_do or not body.ly_do.strip():
            raise HTTPException(status_code=400, detail="can_ly_do_mo_lai_lich")
        _audit("schedule.lifecycle_reopen", role, {"entity_type": "schedule", "entity_id": doc.get("tuan_iso", "2026-W01"), "from": cur, "to": body.to, "ly_do": body.ly_do.strip()})

    effective_target = "da_cong_bo" if body.to == "da_duyet" else body.to
    if effective_target == "da_cong_bo":
        _guard_authoritative_lifecycle(week, effective_target, store_id)

    doc["tuan_iso"] = week
    doc["trang_thai"] = effective_target
    if body.to == "dang_giai":
        try:
            from ca_api.services.scheduling_service import authoritative_input_fingerprint
            _, fingerprint = authoritative_input_fingerprint(store_id, week)
            authoritative = run_authoritative_schedule(
                store_id=store_id, tuan_iso=week, actor_id=role,
                idempotency_key=f"lifecycle:{week}:solve:{fingerprint[:16]}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        solver = authoritative.get("result") or {}
        doc["solver"] = solver
        doc["schedule_run"] = authoritative
        doc["trang_thai"] = "cho_duyet" if solver.get("ok") else "nhap"
    _save_life(doc, store_id=store_id)
    _audit("schedule.lifecycle", role, {"entity_type": "schedule", "entity_id": doc.get("tuan_iso", "2026-W01"), "from": cur, "to": effective_target})
    if effective_target == "da_cong_bo":
        _publish_schedule_notification(week, store_id)
    await notify_ops_changed("roster:lifecycle", doc.get("tuan_iso"))
    return doc


def _guard_authoritative_lifecycle(week: str, target: str, store_id: str) -> dict[str, Any]:
    from ca_api.persist import schedule_run_latest
    from ca_api.services.scheduling_service import authoritative_input_fingerprint

    run = schedule_run_latest(store_id, week)
    if not run:
        raise HTTPException(status_code=409, detail="authoritative_schedule_run_required")
    _, current_fingerprint = authoritative_input_fingerprint(store_id, week)
    if run.get("fingerprint") != current_fingerprint:
        raise HTTPException(status_code=409, detail="stale_schedule_run")
    # Ca thiếu THẬT = ca mà PHÂN CÔNG HIỆN TẠI chưa đủ người tối thiểu.
    #
    # Vì sao KHÔNG dùng `run.status`: ghim ca (`POST /lich-tuan/pin`) chạy
    # `run_solver` TRỰC TIẾP (không tạo run mới), nên một run cũ
    # `needs_gap_resolution` vẫn đóng băng mãi — dù quản lý đã ghim đủ người,
    # nút "Duyệt và công bố" vẫn 409 `schedule_has_unresolved_gaps`. Tương tự,
    # `open_shifts` là bảng tích luỹ không tự dọn khi ghim tay lấp ca.
    #
    # Nguồn đúng là phân công đang hiển thị: ca nào `assigned < so_nguoi_toi_thieu`
    # mới thực sự còn thiếu. Đủ hết thì cho công bố, bất kể run cũ nói gì.
    if target in {"da_cong_bo", "da_duyet"}:
        phan_cong = _phan(week)
        toi_thieu = _so_nguoi_toi_thieu_map()
        thieu = [
            ca_id for ca_id in toi_thieu
            if len(set(phan_cong.get(ca_id, []))) < toi_thieu.get(ca_id, 1)
        ]
        if thieu:
            raise HTTPException(status_code=409, detail="schedule_has_unresolved_gaps")
    return run


@router.post("/api/v1/lich/resolve-gaps")
async def resolve_gaps(
    body: ResolveScheduleBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    session = auth_session(authorization) or {}
    try:
        run = resolve_schedule_gaps(
            store_id=str(session.get("store_id") or "quan_01"), tuan_iso=body.tuan_iso,
            actor_id=str(session.get("nv_id") or role), schedule_run_id=body.schedule_run_id,
            expected_fingerprint=body.expected_fingerprint, idempotency_key=body.idempotency_key,
            ca_id=body.ca_id, nv_id=body.nv_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = run.get("result") or {}
    if result.get("ok"):
        store_id = str((auth_session(authorization) or {}).get("store_id") or "quan_01")
        doc = _life(body.tuan_iso, store_id=store_id)
        doc["trang_thai"] = "cho_duyet"
        doc["schedule_run"] = run
        doc["solver"] = result
        _save_life(doc, store_id=store_id)
    _audit("schedule.resolve_gaps", role, {"entity_type": "schedule_run", "entity_id": body.schedule_run_id, "tuan_iso": body.tuan_iso, "ok": bool(result.get("ok"))})
    await notify_ops_changed("roster:gap-resolution", body.tuan_iso)
    return {"ok": bool(result.get("ok")), "schedule_run": run, "solver": result}


def _export_rows(
    authorization: str | None,
    tuan: str | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    s = _require_role_session(authorization)
    store_id = str(s.get("store_id") or "quan_01")
    tuan_iso = (tuan or "").strip() or str(_life(store_id=store_id).get("tuan_iso") or "2026-W01")
    life = _life(tuan_iso, store_id=store_id)
    if s.get("role") == "nhan_vien" and life.get("trang_thai") not in {"da_cong_bo", "da_dong"}:
        raise HTTPException(status_code=409, detail="lich_chua_cong_bo")
    phan = _phan(tuan_iso)
    try:
        y_str, w_str = tuan_iso.split("-W")
        iso_year, iso_week = int(y_str), int(w_str)
    except Exception:
        raise HTTPException(status_code=422, detail="tuan_iso_khong_hop_le") from None

    seed_data = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    ca_meta_map = {c["id"]: c for c in seed_data.get("ca_mau_21", [])}
    ten_map = {
        str(nv["id"]): str(nv.get("ten") or nv["id"])
        for nv in list_nhan_vien_ops()
    }
    khung_gio = kv_get("khung_gio", {})
    personal = s.get("role") == "nhan_vien"
    rows: list[dict[str, Any]] = []
    for ca_id, assigned_raw in phan.items():
        assigned = list(assigned_raw)
        if personal:
            assigned = [nv for nv in assigned if nv == s.get("nv_id")]
        if not assigned:
            continue
        meta = ca_meta_map.get(ca_id, {})
        frame = khung_gio.get(meta.get("khung"), {}) if isinstance(khung_gio, dict) else {}
        start = str(frame.get("bat_dau") or meta.get("bat_dau", "07:00"))
        finish = str(frame.get("ket_thuc") or meta.get("ket_thuc", "12:00"))
        day_offset = int(meta.get("ngay_offset", 1))
        shift_date = date.fromisocalendar(iso_year, iso_week, day_offset)
        rows.append(
            {
                "ca_id": ca_id,
                "date": shift_date,
                "thu": _THU_MAP.get(day_offset, "T2"),
                "khung": str(meta.get("khung") or ""),
                "bat_dau": start,
                "ket_thuc": finish,
                "vi_tri": _VI_TRI_VI.get(str(meta.get("vi_tri") or ""), str(meta.get("vi_tri") or "")),
                "nhan_vien": [ten_map.get(nv, nv) for nv in assigned],
            }
        )
    rows.sort(key=lambda row: (row["date"], row["bat_dau"], row["vi_tri"]))
    return tuan_iso, s, rows


@router.post("/api/v1/open-shifts")
def create_open_shift(
    body: OpenShiftBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    store_id = str((auth_session(authorization) or {}).get("store_id") or "quan_01")
    deadline_at = body.deadline_at
    if not deadline_at:
        sla_minutes = int(os.environ.get("OPEN_SHIFT_SLA_MINUTES", "120"))
        deadline_at = (datetime.now(UTC) + timedelta(minutes=sla_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return open_shift_create(
        store_id=store_id,
        schedule_run_id=body.schedule_run_id,
        tuan_iso=body.tuan_iso,
        ca_id=body.ca_id,
        deadline_at=deadline_at,
    )


@router.get("/api/v1/open-shifts")
def list_open_shifts(
    authorization: Annotated[str | None, Header()] = None,
    tuan_iso: str | None = Query(default=None),
) -> dict[str, Any]:
    role = _require_role(authorization)
    store_id = str((auth_session(authorization) or {}).get("store_id") or "quan_01")
    if not tuan_iso:
        items = open_shift_list(store_id)
        if role in {"quan_ly", "chu_quan"}:
            items.extend(open_shift_list(store_id, status="claimed"))
        return {"items": items}
    # Ca thiếu THẬT cho tuần: chỉ giữ bản ghi open_shift mà ca đó VẪN chưa đủ
    # người trong phân công hiện tại. `open_shifts` là bảng tích luỹ — không lọc
    # thì chợ hiện hàng chục ca "hết hạn" dù ghim tay đã lấp đủ (lỗi user thấy).
    phan_cong = _phan(tuan_iso)
    toi_thieu = _so_nguoi_toi_thieu_map()

    def con_thieu(s: dict[str, Any]) -> bool:
        ca_id = str(s.get("ca_id") or "")
        return len(set(phan_cong.get(ca_id, []))) < toi_thieu.get(ca_id, 1)

    items = [s for s in open_shift_list(store_id, tuan_iso=tuan_iso) if con_thieu(s)]
    if role in {"quan_ly", "chu_quan"}:
        items.extend(
            s for s in open_shift_list(store_id, tuan_iso=tuan_iso, status="claimed")
            if con_thieu(s)
        )
    return {"items": items}


@router.post("/api/v1/open-shifts/claim")
def claim_open_shift(
    body: ShiftClaimBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    session = auth_session(authorization)
    if not session:
        raise HTTPException(status_code=401, detail="thieu_token")
    if session.get("role") != "nhan_vien":
        raise HTTPException(status_code=403, detail="chi_nhan_vien_duoc_nhan_ca")
    store_id = str(session.get("store_id") or "quan_01")
    shifts = [item for item in open_shift_list(store_id) if item["id"] == body.open_shift_id]
    if not shifts:
        raise HTTPException(status_code=404, detail="open_shift_khong_ton_tai")
    shift = shifts[0]
    run = schedule_run_get(str(shift["schedule_run_id"]))
    if (
        not run
        or run.get("store_id") != store_id
        or run.get("tuan_iso") != shift["tuan_iso"]
        or run.get("status") != "needs_gap_resolution"
    ):
        raise HTTPException(status_code=409, detail="open_shift_khong_thuoc_run_gap_hop_le")
    confirmed = availability_confirmed_list(store_id, shift["tuan_iso"])
    if not any(item["nv_id"] == session.get("nv_id") for item in confirmed):
        raise HTTPException(status_code=409, detail="chua_xac_nhan_kha_dung_dung_tuan")
    assignments = authoritative_assignments_list(str(run["id"]))
    if any(
        item["nv_id"] == str(session["nv_id"])
        and item["ca_id"] == str(shift["ca_id"])
        for item in assignments
    ):
        raise HTTPException(status_code=409, detail="nhan_vien_da_duoc_xep_ca")
    claimed = shift_application_claim_first(
        open_shift_id=body.open_shift_id,
        store_id=store_id,
        nv_id=str(session["nv_id"]),
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail="ca_da_duoc_nhan")
    return claimed


@router.get("/api/v1/lich/ics")
def lich_ics(
    authorization: Annotated[str | None, Header()] = None,
    download: bool = Query(default=False),
    tuan: str | None = Query(default=None, description="Tuần ISO muốn xuất, vd 2026-W37"),
) -> Any:
    tuan_iso, s, rows = _export_rows(authorization, tuan)
    now_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NHIPQUAN//CA//VI",
        "CALSCALE:GREGORIAN",
        "X-WR-TIMEZONE:Asia/Ho_Chi_Minh",
    ]
    for row in rows:
        uid = f"{row['ca_id']}_{tuan_iso}_{s['nv_id']}@nhipquan.local"
        d_str = row["date"].strftime("%Y%m%d")
        dtstart = f"{d_str}T{str(row['bat_dau']).replace(':', '')}00"
        dtend = f"{d_str}T{str(row['ket_thuc']).replace(':', '')}00"
        summary = _ics_escape(
            f"{row['vi_tri']} — {' · '.join(row['nhan_vien'])}"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;TZID=Asia/Ho_Chi_Minh:{dtstart}",
            f"DTEND;TZID=Asia/Ho_Chi_Minh:{dtend}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics_text = "\r\n".join(lines)
    if download:
        return Response(
            content=ics_text,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="lich_tuan_{tuan_iso}.ics"',
            },
        )
    return {"ics": ics_text, "nguon": "quan", "tuan_iso": tuan_iso}


@router.get("/api/v1/lich/xlsx")
def lich_xlsx(
    authorization: Annotated[str | None, Header()] = None,
    tuan: str | None = Query(default=None),
) -> Response:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    tuan_iso, _session, rows = _export_rows(authorization, tuan)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lịch tuần"
    sheet.append(["Tuần", "Ngày", "Thứ", "Khung", "Giờ", "Vị trí", "Nhân viên"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="8C5A3C")
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        sheet.append(
            [
                tuan_iso,
                row["date"].strftime("%d/%m/%Y"),
                row["thu"],
                row["khung"],
                f"{row['bat_dau']}–{row['ket_thuc']}",
                row["vi_tri"],
                ", ".join(row["nhan_vien"]),
            ]
        )
    for width, column in zip((14, 14, 8, 12, 16, 18, 42), "ABCDEFG", strict=True):
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="lich_tuan_{tuan_iso}.xlsx"'},
    )


@router.get("/api/v1/lich/pdf")
def lich_pdf(
    authorization: Annotated[str | None, Header()] = None,
    tuan: str | None = Query(default=None),
) -> Response:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    tuan_iso, _session, rows = _export_rows(authorization, tuan)
    font_name = "Helvetica"
    for font_path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont("NhipQuanUnicode", font_path))
            font_name = "NhipQuanUnicode"
            break
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontName = font_name
    story: list[Any] = [Paragraph(f"Lịch tuần {tuan_iso}", styles["Title"])]
    data = [["Ngày", "Khung giờ", "Vị trí", "Nhân viên"]]
    data.extend(
        [
            row["date"].strftime("%d/%m/%Y"),
            f"{row['khung']} {row['bat_dau']}–{row['ket_thuc']}",
            row["vi_tri"],
            ", ".join(row["nhan_vien"]),
        ]
        for row in rows
    )
    table = Table(data, colWidths=[35 * mm, 45 * mm, 42 * mm, 145 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8C5A3C")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4EEE9")]),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="lich_tuan_{tuan_iso}.pdf"'},
    )


@router.get("/api/v1/audit")
def audit_get(
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    return {"items": audit_list(limit=limit), "nguon": "quan"}


def _ics_escape(text: str) -> str:
    """Escape ký tự theo RFC 5545 TEXT: backslash, chấm phẩy, phẩy, xuống dòng."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _require_role_session(authorization: str | None) -> dict[str, Any]:
    """Yêu cầu đăng nhập và trả về session (để chèn người duyệt vào UID ICS)."""
    role = _require_role(authorization)
    from ca_api.persist import session as auth_session

    s = auth_session(authorization)
    return s if s else {"nv_id": role, "role": role}


def _get_swap_candidates_for_item(it: dict[str, Any]) -> list[dict[str, Any]]:
    """Tính toán danh sách ứng viên đổi ca phù hợp cho một inbox item."""
    nv_id = str(it.get("nv_id") or "")
    rb = it.get("rang_buoc") or {}
    ca_id = str(rb.get("ca_id") or "")

    thu = str(rb.get("thu") or "")
    start = str(rb.get("start") or "")
    khung = "sang" if "07" in start else ("chieu" if "12" in start else ("toi" if "17" in start else ""))
    vi_tri = str(rb.get("vi_tri") or "pha_che")
    shift_info = {"thu": thu, "khung": khung, "vi_tri": vi_tri}

    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    # Ứng viên thế ca phải là NV CÓ THẬT trong pool đang xếp lịch. Trước đây đọc
    # `seed["nhan_vien"]` (25 mã nv_01..nv_25) nên xếp hạng cả người không tồn
    # tại trong DB (bug QA đợt 4). Seed chỉ là fallback khi pool thật rỗng.
    staff_list = list_nhan_vien_ops()
    if not staff_list:
        staff_list = seed.get("nhan_vien", [])
    raw_ca = seed.get("ca_mau_21", [])
    ca_list = []
    for c in raw_ca:
        item_c = dict(c)
        if "thu" not in item_c:
            item_c["thu"] = _THU_MAP.get(int(item_c.get("ngay_offset") or 1), "T2")
        ca_list.append(item_c)

    phan_cong: dict[str, list[str]] = {}
    lich_out = _lich_out()
    if lich_out.exists():
        try:
            lich_data = json.loads(lich_out.read_text(encoding="utf-8"))
            phan_cong = lich_data.get("phan_cong", {})
        except Exception:
            pass

    cands = find_swap_candidates(
        requester_id=nv_id,
        ca_id=ca_id if ca_id else None,
        shift_info=shift_info,
        staff_list=staff_list,
        ca_list=ca_list,
        phan_cong=phan_cong,
        max_ca_lien_tuc=2,
    )
    return [c.to_dict() for c in cands]


def _chay_autopilot_nen(store_id: str) -> None:
    """Chạy `auto_process` ở background task; lỗi thì nuốt, không làm hỏng GET.

    Tách riêng (thay vì lambda) để background task có stack trace đọc được khi
    cần debug, và để test patch được bằng tên hàm.
    """
    try:
        from ca_api.services.inbox_autopilot import auto_process

        auto_process(store_id=store_id)
    except Exception:
        pass


@router.get("/api/v1/inbox/rang-buoc")
def inbox_list(
    background_tasks: BackgroundTasks,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    existing = kv_get("inbox_rang_buoc", [])
    has_real_channel = any(
        isinstance(it, dict) and it.get("nguon") in {"telegram", "zalo", "facebook"}
        for it in existing
    )
    if not existing and not has_real_channel:
        _seed_inbox()

    # Trang này giờ CHỈ XEM — AI tự động duyệt/từ chối ngay khi yêu cầu được
    # ghi vào hộp thư (xem `_enqueue_inbox` ở channels.py). Quét lại đây là
    # lưới an toàn cho các luồng ghi không gọi autopilot trực tiếp, để không
    # bao giờ còn mục "cho_duyet" đọng lại chờ người bấm nút.
    #
    # Quét chạy ở BACKGROUND, không chặn response: nó kéo theo giải CP-SAT cho
    # từng tuần có ràng buộc mới, và đo được 194s khi quét 14 mục — quản lý
    # bấm vào Hộp thư không được phép đứng chờ vài phút mới thấy danh sách.
    # Các luồng ghi thật vẫn gọi autopilot trực tiếp nên lần mở trang này
    # thường không có gì để quét; đây chỉ là lưới an toàn bù đắp.
    session = auth_session(authorization) or {}
    store_id = str(session.get("store_id") or "quan_01")
    background_tasks.add_task(_chay_autopilot_nen, store_id)

    items = kv_get("inbox_rang_buoc", [])
    enriched = []
    for it in items:
        if isinstance(it, dict):
            item_copy = dict(it)
            rb = item_copy.get("rang_buoc") or {}
            item_copy["khan_cap"] = bool(rb.get("khan_cap"))
            if item_copy.get("y_dinh") in {"doi_ca", "nhan_ca"}:
                try:
                    cands = _get_swap_candidates_for_item(item_copy)
                    item_copy["goi_y_doi_tac"] = cands[:3]
                except Exception:
                    item_copy["goi_y_doi_tac"] = []
            enriched.append(item_copy)
        else:
            enriched.append(it)
    return {"items": enriched, "nguon": "quan", "co_du_lieu_mau": _co_du_lieu_mau(enriched)}


def _giai_lich_cho_tuan_dich(
    *,
    store_id: str,
    week: str,
    role: str,
    actor_id: str,
    item_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Chạy solver cho TUẦN ĐÍCH rồi cập nhật lifecycle của tuần đó.

    Tách khỏi `_decide_inbox_item` để `services/inbox_autopilot.py` gọi lại được
    theo TUẦN thay vì theo từng mục: một lượt quét có thể quyết n mục, mà mỗi
    mục một lần gọi CP-SAT thì trang Hộp thư phải chờ n × thời gian giải (đo
    được 194s cho 14 mục). Giải MỘT lần cho cả nhóm vừa nhanh hơn, vừa đúng
    hơn: lịch sinh ra phải thỏa TẤT CẢ ràng buộc vừa duyệt, không phải lần
    lượt chỉ biết một mục.

    Trả về `solver_result` (kèm `schedule_run_id`/`schedule_run_status`).
    """
    life = _life(store_id=store_id)
    # Cổng khoá phải xét trạng thái của TUẦN ĐÍCH, không phải tuần đang làm
    # việc. Trường hợp thật: lịch tuần này đã công bố, nhân viên nhắn báo bận
    # cho TUẦN SAU (còn nháp) — xét tuần hiện tại sẽ trả LIFECYCLE_LOCKED và
    # AI không bao giờ xếp lại tuần đích, dù tuần đó hoàn toàn được phép.
    tuan_hien_tai = str(life.get("tuan_iso") or "")
    if week == tuan_hien_tai:
        life_tuan_dich = life
        dong_bo_toan_cuc = True
    else:
        life_tuan_dich = _life(week, store_id=store_id)
        dong_bo_toan_cuc = False
    # Neo khoá tuần trước khi lưu: `_save_life` suy ra khoá ghi
    # `lich_tuan_lifecycle_by_week` từ `doc["tuan_iso"]`; thiếu nó thì bản
    # ghi rơi vào tuần hiện tại của đồng hồ, tức trạng thái `cho_duyet` của
    # tuần đích bị ghi nhầm chỗ.
    life_tuan_dich["tuan_iso"] = week
    current_state = str(life_tuan_dich.get("trang_thai") or "may_sinh")
    if current_state in {"da_duyet", "da_cong_bo", "da_dong"}:
        solver_result: dict[str, Any] = {
            "ok": False,
            "skipped": True,
            "status": "LIFECYCLE_LOCKED",
            "detail": f"lich_{current_state}_khong_tu_dong_xep_lai",
        }
    else:
        # Đi qua application service authoritative để mọi trigger dùng chung
        # một đường CP-SAT (schedule_run/fingerprint/audit/open_shift).
        try:
            authoritative = run_authoritative_schedule(
                store_id=store_id,
                tuan_iso=week,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
            )
            solver_result = authoritative.get("result") or {}
            # KHÔNG gán toàn bộ `authoritative` vào `result` (gây tham chiếu vòng
            # khi serialize JSON). Chỉ giữ metadata run ở mức solver_result.
            solver_result["schedule_run_id"] = authoritative.get("id")
            solver_result["schedule_run_status"] = authoritative.get("status")
        except Exception:
            solver_result = {
                "ok": False,
                "status": "ERROR",
                "detail": "khong_the_chay_solver",
            }
        if solver_result.get("ok"):
            life_tuan_dich["trang_thai"] = "cho_duyet"
            life_tuan_dich["solver"] = solver_result
            life_tuan_dich["schedule_run_id"] = solver_result.get("schedule_run_id")
            life_tuan_dich["cap_nhat_luc"] = _clock.now_iso()
            life_tuan_dich["cap_nhat_boi"] = role
            _save_life(
                life_tuan_dich,
                store_id=store_id,
                dong_bo_toan_cuc=dong_bo_toan_cuc,
            )
    return solver_result


def _decide_inbox_item(
    item_id: str,
    *,
    quyet_dinh: str,
    role: str,
    store_id: str,
    actor_id: str,
    ly_do: str | None = None,
    ca_id: str | None = None,
    doi_tac_nv_id: str | None = None,
    ap_dat: bool = False,
    tu_dong_xep_lich: bool = False,
) -> dict[str, Any]:
    """Lõi quyết định một mục hộp thư ràng buộc (duyệt/từ chối + hiệu lực +
    tự động xếp lịch nếu cần) — dùng chung cho:
      - `inbox_decide` (endpoint HTTP, người quản lý bấm nút Duyệt/Từ chối)
      - `services/inbox_autopilot.py` (AI tự động duyệt, không có phiên HTTP)
    Tách khỏi endpoint để hai nơi gọi cùng MỘT đường ghi kv/swap/solver,
    không có hai bản logic có thể lệch nhau."""
    tuan_default = _life(store_id=store_id).get("tuan_iso", "2026-W01")
    found: dict[str, Any] | None = None
    pending_swap: dict[str, Any] | None = None

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal found, pending_swap
        for it in items:
            if it.get("id") == item_id:
                if quyet_dinh not in {"duyet", "tu_choi"}:
                    raise HTTPException(status_code=400, detail="quyet_dinh")
                it["trang_thai"] = quyet_dinh
                if ly_do and str(ly_do).strip():
                    it["ly_do_quyet"] = str(ly_do).strip()[:500]
                if quyet_dinh == "duyet":
                    y = str(it.get("y_dinh") or "")
                    rb = it.get("rang_buoc") or {}
                    tuan_id = rb.get("tuan_id") or tuan_default
                    if y in {"doi_ca", "nhan_ca"}:
                        eff_ca_id = (ca_id or rb.get("ca_id") or "").strip()
                        eff_doi_tac = (doi_tac_nv_id or rb.get("doi_tac") or "").strip()
                        if it.get("doi_tac_khong_ro") and not doi_tac_nv_id:
                            raise HTTPException(
                                status_code=400,
                                detail="doi_tac_khong_ro_can_chon_nhan_vien",
                            )
                        if not eff_ca_id or not eff_doi_tac:
                            raise HTTPException(
                                status_code=400,
                                detail="doi_ca_can_ca_id_va_doi_tac",
                            )
                        is_ap_dat = bool(ap_dat)
                        swap_status = "dong_y" if is_ap_dat else "cho_xac_nhan"
                        dong_y_list = [it.get("nv_id") or "unknown", eff_doi_tac] if is_ap_dat else [it.get("nv_id") or "unknown"]
                        pending_swap = {
                            "id": f"sw_inbox_{uuid.uuid4().hex[:6]}",
                            "a": it.get("nv_id") or "unknown",
                            "b": eff_doi_tac,
                            "ca_id": eff_ca_id,
                            "trang_thai": swap_status,
                            "dong_y": dong_y_list,
                            "ap_dat": is_ap_dat,
                            "nguon": it.get("nguon") or "inbox",
                            "tu_inbox": item_id,
                            "tom_tat": it.get("tom_tat"),
                            "tuan_id": tuan_id,
                        }
                        it["hieu_luc"] = {
                            "loai": "cho_doi_ca",
                            "swap_id": pending_swap["id"],
                            "ghi": (
                                f"Đã áp đặt đổi ca {eff_ca_id} với {eff_doi_tac}"
                                if is_ap_dat
                                else f"Đã mở phiếu đổi ca {eff_ca_id} với {eff_doi_tac} — chờ đối tác xác nhận"
                            ),
                            "tuan_id": tuan_id,
                        }
                    elif y == "xin_nghi":
                        thu = rb.get("thu", "")
                        start = str(rb.get("start") or "")
                        end = str(rb.get("end") or "")
                        hl_xn: dict[str, Any] = {
                            "loai": "rang_buoc_cho_solver",
                            "nv_id": it.get("nv_id"),
                            "thu": thu,
                            "tuan_id": tuan_id,
                        }
                        if start and end:
                            # Nghỉ ĐÚNG một ca — giữ khung giờ để solver chỉ chặn ca đó,
                            # KHÔNG xoá cả ngày (sửa lỗi "bận 1 ca thành nghỉ cả ngày").
                            hl_xn["start"] = start
                            hl_xn["end"] = end
                            hl_xn["ghi"] = (
                                f"Đã duyệt nghỉ ca {thu} {start}-{end} ({tuan_id}) — áp vào lượt xếp lịch tới"
                            )
                        else:
                            hl_xn["ghi"] = (
                                f"Đã duyệt nghỉ phép {thu} ({tuan_id}) — áp vào lượt xếp lịch tới"
                            )
                        it["hieu_luc"] = hl_xn
                    elif y in {"bao_tre", "cap_nhat_tkb"}:
                        thu = rb.get("thu", "")
                        start = rb.get("start", "07:00")
                        end = rb.get("end", "12:00")
                        it["hieu_luc"] = {
                            "loai": "rang_buoc_cho_solver",
                            "ghi": f"Đã duyệt TKB bận {thu} {start}-{end} ({tuan_id}) — áp vào lượt xếp lịch tới",
                            "nv_id": it.get("nv_id"),
                            "thu": thu,
                            "start": start,
                            "end": end,
                            "tuan_id": tuan_id,
                        }
                    else:
                        it["hieu_luc"] = {
                            "loai": "ghi_nhan",
                            "ghi": "Đã ghi nhận — không đổi lịch",
                        }
                found = it
                break
        return items

    kv_mutate("inbox_rang_buoc", mut, [])
    if pending_swap is not None:
        def add_swap(items_sw: list[dict[str, Any]]) -> list[dict[str, Any]]:
            items_sw.append(pending_swap)
            return items_sw

        kv_mutate("swap", add_swap, [])
        if pending_swap.get("trang_thai") == "dong_y":
            _apply_swap_to_assignments(
                giver=str(pending_swap.get("a") or ""),
                taker=str(pending_swap.get("b") or ""),
                ca_id=str(pending_swap.get("ca_id") or ""),
                week=str(pending_swap.get("tuan_id") or tuan_default),
                swap_id=str(pending_swap.get("id") or ""),
                actor=str(role),
            )
    if not found:
        raise HTTPException(status_code=404, detail="inbox_item")

    y_dinh = str(found.get("y_dinh") or "")
    if y_dinh == "doi_ca":
        action_name = (
            "shift_swap.approve"
            if quyet_dinh == "duyet"
            else "shift_swap.reject"
        )
    else:
        action_name = (
            "constraint.approve"
            if quyet_dinh == "duyet"
            else "constraint.reject"
        )
    _audit(
        action_name,
        role,
        {
            "entity_type": "inbox_item",
            "entity_id": item_id,
            "q": quyet_dinh,
            "y": y_dinh,
        },
    )

    response = dict(found)
    if (
        quyet_dinh == "duyet"
        and tu_dong_xep_lich
        and found.get("hieu_luc", {}).get("loai") == "rang_buoc_cho_solver"
    ):
        rb = found.get("rang_buoc") or {}
        tuan_hien_tai = str(_life(store_id=store_id).get("tuan_iso") or "")
        week = str(rb.get("tuan_id") or tuan_hien_tai or "2026-W01")
        solver_result = _giai_lich_cho_tuan_dich(
            store_id=store_id,
            week=week,
            role=role,
            actor_id=actor_id,
            item_id=item_id,
            idempotency_key=f"inbox:{item_id}:{week}:solve",
        )
        response["tu_dong_xep_lich"] = solver_result
        _audit(
            "inbox_auto_schedule",
            role,
            {
                "id": item_id,
                "ok": solver_result.get("ok"),
                "status": solver_result.get("status"),
                "so_o_ca_da_xep": solver_result.get("so_o_ca_da_xep"),
                "tong_so_o_ca": solver_result.get("tong_so_o_ca"),
            },
        )
    return response


@router.post("/api/v1/inbox/rang-buoc/{item_id}")
def inbox_decide(
    item_id: str,
    body: InboxBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    session = auth_session(authorization) or {}
    store_id = str(session.get("store_id") or "quan_01")
    actor_id = str(session.get("nv_id") or role)
    return _decide_inbox_item(
        item_id,
        quyet_dinh=body.quyet_dinh,
        role=role,
        store_id=store_id,
        actor_id=actor_id,
        ly_do=body.ly_do,
        ca_id=body.ca_id,
        doi_tac_nv_id=body.doi_tac_nv_id,
        ap_dat=body.ap_dat,
        tu_dong_xep_lich=body.tu_dong_xep_lich,
    )


@router.get("/api/v1/inbox/candidates/{item_id}")
def get_swap_candidates(
    item_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lấy danh sách xếp hạng các ứng viên đổi ca cho một yêu cầu."""
    _require_manager(authorization)
    items = kv_get("inbox_rang_buoc", [])
    found = next((it for it in items if it.get("id") == item_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="item_not_found")

    cands = _get_swap_candidates_for_item(found)
    return {
        "item_id": item_id,
        "nv_id": found.get("nv_id"),
        "candidates": cands,
    }


@router.post("/api/v1/inbox/rang-buoc/{item_id}/smart-approve")
def inbox_smart_approve(
    item_id: str,
    body: SmartApproveBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Duyệt đổi ca 1-chạm với ứng viên AI đề xuất tốt nhất (hoặc ứng viên được chọn)."""
    _require_manager(authorization)
    items = kv_get("inbox_rang_buoc", [])
    found = next((it for it in items if it.get("id") == item_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="item_not_found")

    target_nv = body.selected_nv_id
    if not target_nv:
        cands = _get_swap_candidates_for_item(found)
        top_cand = next((c for c in cands if c.get("score", 0) > 0), None)
        if not top_cand:
            raise HTTPException(status_code=400, detail="khong_co_ung_vien_phu_hop")
        target_nv = top_cand["nv_id"]

    rb = found.get("rang_buoc") or {}
    ca_id = (rb.get("ca_id") or "w1_c01").strip()

    decide_body = InboxBody(
        quyet_dinh="duyet",
        doi_tac_nv_id=target_nv,
        ca_id=ca_id,
        ap_dat=body.ap_dat,
    )
    res = inbox_decide(item_id, decide_body, authorization)
    res["selected_candidate"] = target_nv
    res["smart_matched"] = True
    
    _require_manager(authorization)
    role = _require_manager(authorization)
    _audit("shift_swap.smart_approve", role, {"entity_type": "inbox_item", "entity_id": item_id, "selected_candidate": target_nv})
    return res


@router.get("/api/v1/cong-bang")
def cong_bang(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    # Danh sách NV lấy từ NGUỒN THẬT (pool đang xếp lịch), KHÔNG phải seed.
    # Bug QA đợt 4: trước đây đọc thẳng `seed["nhan_vien"]` (25 mã nv_01..nv_25)
    # nên báo cáo công bằng hiện số dư cho 6 người không tồn tại trong DB
    # (DB thật có 19). Seed chỉ dùng làm fallback khi pool thật rỗng.
    nvs = [str(n["id"]) for n in list_nhan_vien_ops() if n.get("id")]
    if not nvs:
        nvs = [str(n["id"]) for n in seed.get("nhan_vien", [])]
    meta = {
        c["id"]: {
            "thu": {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}.get(
                int(c.get("ngay_offset", 1)), "T2"
            ),
            "khung": c.get("khung", ""),
            "bat_dau": c.get("bat_dau", "07:00"),
            "ket_thuc": c.get("ket_thuc", "12:00"),
        }
        for c in seed.get("ca_mau_21", [])
    }
    debt = update_debt_from_assignment(zero_debt(nvs), _phan(), meta)
    # `update_debt_from_assignment` dùng `setdefault` nên TẠO key cho mã nhân sự
    # có trong lịch phân công mà không có trong pool (`nvs`). Với dữ liệu fixture
    # cũ, lịch có thể tham chiếu nv_20..nv_25 trong khi DB chỉ có 19 người — nếu
    # giữ nguyên, báo cáo công bằng sẽ hiện số dư cho người không tồn tại. Lọc
    # về đúng pool đang xếp lịch (bug QA đợt 4).
    debt = {nv: debt[nv] for nv in nvs if nv in debt}
    means = {a: 0.0 for a in AXES}
    if nvs:
        for a in AXES:
            means[a] = sum(debt[n][a] for n in nvs) / len(nvs)
    me = s["nv_id"]
    if s["role"] in {"quan_ly", "chu_quan"}:
        so_du = debt
        ma_ly_do = {nv: [_REASON[a] for a in AXES if debt[nv][a] > means[a]] for nv in nvs}
    else:
        so_du = {me: debt.get(me, {a: 0.0 for a in AXES})}
        ma_ly_do = {me: [_REASON[a] for a in AXES if so_du[me][a] > means[a]]}
    return {
        "axes": list(AXES),
        "means": means,
        "so_du": so_du,
        "ma_ly_do": ma_ly_do,
        "nv_id": me,
        "nguon": "quan",
        "khong_xep_hang_ten": True,
    }


@router.get("/api/v1/cong-bang/bao-cao")
def cong_bang_bao_cao(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    body = cong_bang(authorization)
    lines = [
        "NHIP QUAN — báo cáo công bằng",
        f"nguon={body['nguon']}",
        "khong xep hang ten",
    ]
    for a, m in body["means"].items():
        lines.append(f"TB {a}={m:.2f}")
    return {"text": "\n".join(lines), "dinh_dang": "text/plain"}


class TieuThuBody(BaseModel):
    hang: str = Field(min_length=1, max_length=100)
    so_luong: float = Field(ge=0)
    don_vi: str = Field(default="khay", min_length=1, max_length=30)


class WasteNoteBody(BaseModel):
    thu: str = "T2"
    ghi_chu: str = ""
    mon_id: str | None = None
    so_luong: float | None = Field(default=None, ge=0)
    don_vi: str | None = None
    ly_do: str | None = None


@router.get("/api/v1/hom-nay")
def hom_nay(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    role = _require_role(authorization)
    life = _life()
    treo = kv_get("treo", [])
    # Chỉ tính việc treo đang mở (chưa xong) — khớp với /treo, brief sáng và
    # hàng đợi "việc treo trong ca". Việc đã xong không còn là việc treo.
    treo_mo = [t for t in treo if isinstance(t, dict) and t.get("trang_thai") != "xong"]
    inbox = kv_get("inbox_rang_buoc", [])
    cho = sum(1 for x in inbox if x.get("trang_thai") == "cho_duyet")
    if role == "nhan_vien":
        cho = 0
    luat = list_luat()
    ton = kv_get("tieu_thu", [])
    canh_bao = [x["hang"] for x in ton if x.get("duoi_nguong")]
    so_nv = sum(1 for u in list_users() if u.get("role") == "nhan_vien")
    treo_preview = [
        {
            "id": t.get("id"),
            "noi_dung": str(t.get("noi_dung") or "")[:120],
            "trang_thai": t.get("trang_thai") or "dang_cho",
            "nhan_vien": t.get("nhan_vien") or t.get("nv_id"),
        }
        for t in treo_mo[:5]
    ]
    sua_gan_day = [
        {
            "loai": row.get("loai"),
            "luc": row.get("at"),
            "ai": row.get("ai"),
        }
        for row in list(reversed(list_sua(include_synthetic=False)))[:5]
    ]
    ton_tom_tat = [
        {
            "hang": x.get("hang"),
            "so_luong": x.get("so_luong"),
            "don_vi": x.get("don_vi") or "đơn vị",
            "duoi_nguong": bool(x.get("duoi_nguong")),
        }
        for x in ton[-8:]
        if isinstance(x, dict)
    ]
    treo_counts: dict[str, int] = {}
    for t in treo_mo:
        st = str(t.get("trang_thai") or "dang_cho")
        treo_counts[st] = treo_counts.get(st, 0) + 1
    treo_theo_trang_thai = [{"trang_thai": k, "so_luong": v} for k, v in sorted(treo_counts.items(), key=lambda x: -x[1])]

    # Hao hụt hôm nay: mặt hàng nào vượt ngưỡng, bao nhiêu mặt hàng chưa kết luận
    # được vì thiếu vế. Bọc `try` vì đây là trang mở đầu sau đăng nhập — hỏng
    # phần hao hụt không được phép làm sập cả bảng hôm nay.
    try:
        hao_hut = _hao_hut_hom_nay()
    except Exception:
        hao_hut = {"co_du_lieu": False, "ly_do": "khong_doc_duoc"}

    # Hàng đợi "Việc của bạn hôm nay" — quản lý/chủ quán thấy ngay việc chờ mình.
    # Mỗi mục: việc gì, vì sao, bấm vào đâu. NV chỉ thấy việc ca của mình.
    viec_cho_toi: list[dict[str, Any]] = []
    de_xuat_lich = kv_get("worker_de_xuat_lich", None)
    if role in {"quan_ly", "chu_quan"}:
        life_trang_thai = str(life.get("trang_thai") or "nhap")
        if cho > 0:
            viec_cho_toi.append(
                {
                    "id": "inbox_cho",
                    "tieu_de": f"Duyệt {cho} mục hộp thư",
                    "chi_tiet": "Yêu cầu của nhân viên đang chờ quyết.",
                    "link": "/inbox",
                    "muc": cho,
                }
            )
        if de_xuat_lich and de_xuat_lich.get("trang_thai") == "cho_duyet":
            viec_cho_toi.append(
                {
                    "id": "lich_tuan_cho",
                    "tieu_de": "Duyệt lịch tuần sau",
                    "chi_tiet": f"Worker đã xếp sẵn ({de_xuat_lich.get('tong_so_luot', 0)} lượt) — xem rồi công bố.",
                    "link": "/roster",
                    "muc": 1,
                }
            )
        if life_trang_thai in {"may_sinh", "nhap"}:
            viec_cho_toi.append(
                {
                    "id": "xep_lich",
                    "tieu_de": "Xếp lịch tuần",
                    "chi_tiet": "Lịch tuần chưa được duyệt — chạy solver để có lịch công bố.",
                    "link": "/roster",
                    "muc": 1,
                }
            )
        luat_cho = [
            lt for lt in luat if isinstance(lt, dict) and lt.get("trang_thai") == "cho_chu_quan"
        ]
        if luat_cho and role == "chu_quan":
            viec_cho_toi.append(
                {
                    "id": "luat_cho",
                    "tieu_de": f"Chốt {len(luat_cho)} luật cẩm nang",
                    "chi_tiet": "Luật đã qua tập sự — chốt để có hiệu lực.",
                    "link": "/cam-nang",
                    "muc": len(luat_cho),
                }
            )
        qua_han = [t for t in treo if isinstance(t, dict) and t.get("trang_thai") == "qua_han"]
        if qua_han:
            viec_cho_toi.append(
                {
                    "id": "treo_qua_han",
                    "tieu_de": f"{len(qua_han)} việc treo quá hạn",
                    "chi_tiet": "Việc kẹt quá hạn cần xử lý trước cuối ca.",
                    "link": "/treo",
                    "muc": len(qua_han),
                }
            )
    else:
        mo = [t for t in treo if isinstance(t, dict) and t.get("trang_thai") != "xong"]
        if mo:
            viec_cho_toi.append(
                {
                    "id": "treo_ca",
                    "tieu_de": f"{len(mo)} việc treo trong ca của bạn",
                    "chi_tiet": "Đọc việc từ ca trước và xử lý trong ca.",
                    "link": "/treo",
                    "muc": len(mo),
                }
            )
    return {
        # Ngày theo giờ QUÁN (UTC+7) — phải khớp `ngay` mà worker ghi vào
        # brief/tổng kết, và khớp `active_date` gửi agent. Trước đây dùng UTC
        # nên sau 17:00 giờ VN, /hom-nay hiện "ngày mai" còn brief ghi hôm nay
        # (bug QA đợt 4).
        "ngay": ngay_hom_nay_vn(),
        "lich": life,
        "so_treo": len(treo_mo),
        "so_inbox_cho": cho,
        "so_luat": len(luat),
        "canh_bao_ton": canh_bao,
        "so_nhan_vien": so_nv if role == "chu_quan" else 0,
        "treo_preview": treo_preview,
        "treo_theo_trang_thai": treo_theo_trang_thai,
        "sua_gan_day": sua_gan_day,
        "ton_tom_tat": ton_tom_tat,
        "hao_hut": hao_hut,
        "viec_cho_toi": viec_cho_toi,
        "brief_hom_nay": kv_get("brief_hom_nay", None),
        "de_xuat_lich": de_xuat_lich,
        "co_du_lieu_mau": _co_du_lieu_mau([*treo, *inbox, *ton]),
        "nguon": "quan",
    }


@router.get("/api/v1/tieu-thu")
def tieu_thu_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Sổ tiêu thụ trong ca.

    Trả **hai** hình, vì hai việc đọc khác nhau:

    * ``tong_hop`` — một dòng cho một nguyên liệu, đã gộp ``cafe_g`` với
      ``ca_phe_hat``, tên có dấu, kèm ``nhom`` để lọc và ``mon_lien_quan`` để
      bấm về món đang bán. Đây là thứ trang ``/tieu-thu`` vẽ.
    * ``items`` — từng dòng đã dọn (bỏ dòng hỏng, bỏ trùng), giữ ``luc``/``ai``/
      ``mon_*``. Lịch sử ghi tay không bị mất khi gộp.

    ``da_bo_qua`` = số dòng dữ liệu cũ không đọc được (thiếu ``hang``/``so_luong``,
    đúng hình seeder ``order_id/status/items``). Báo ra chứ không nuốt im lặng.
    """
    _require_role(authorization)
    from ca_api.persist import menu_list

    ton = kv_get("tieu_thu", [])
    sach, da_bo_qua = loc_dong_tieu_thu(ton)
    return {
        "tong_hop": tong_hop_tieu_thu(sach, menu_list()),
        "items": sach,
        "da_bo_qua": da_bo_qua,
        "nguon": "quan",
        "ghi": "số lượng, không kế toán",
        "co_du_lieu_mau": _co_du_lieu_mau(ton),
    }


@router.post("/api/v1/tieu-thu")
def tieu_thu_ghi(
    body: TieuThuBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    # Ghi tay nhập "Cà phê hạt" / "Ca phe hat" / "ca_phe_hat" → cùng MÃ chuẩn.
    # Không tra được ("Sữa đặc nhà") thì giữ nguyên đúng chữ người ta gõ.
    raw = body.hang.strip()
    ma = tim_ma_theo_ten(raw)
    if ma is None:
        cung_ma = chuan_hoa_ma(raw)
        ma = cung_ma if la_ma_chuan(cung_ma) else raw
    item = {
        "id": f"tt_{uuid.uuid4().hex[:8]}",
        "hang": ma,
        "so_luong": body.so_luong,
        "don_vi": don_vi_nguyen_lieu(ma) if la_ma_chuan(ma) else body.don_vi,
        "duoi_nguong": body.so_luong < 2,
        "ai": role,
        "luc": datetime.now(UTC).isoformat(),
    }

    def mut(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.append(item)
        return rows

    kv_mutate("tieu_thu", mut, [])
    _audit("tieu_thu", role, item)
    return item


@router.post("/api/v1/waste")
def waste_ghi(
    body: WasteNoteBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_role(authorization)
    thu = (body.thu or "T2").strip()
    ghi_chu = (body.ghi_chu or "").strip()
    if not ghi_chu:
        if body.ly_do:
            ghi_chu = body.ly_do.strip()
        elif body.mon_id:
            ghi_chu = f"Hao phí {body.mon_id}: {body.so_luong or 1} {body.don_vi or 'đơn vị'}"
        else:
            ghi_chu = "Ghi nhận hao phí"
    note = {
        "thu": thu,
        "ghi_chu": ghi_chu,
        "mon_id": body.mon_id,
        "so_luong": body.so_luong,
        "don_vi": body.don_vi,
        "ly_do": body.ly_do,
        "ai": role,
        "luc": datetime.now(UTC).isoformat(),
    }

    def mut(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.append(note)
        return rows

    kv_mutate("waste_notes", mut, [])
    # Ghi dữ liệu vận hành phải để lại vết (ADR-008). `tieu_thu_ghi` cùng file đã
    # gọi `_audit`; đường này thiếu, nên mọi lần ghi hao hụt trước đây vô hình
    # trong sổ vết.
    _audit(
        "hao_hut",
        role,
        {
            "entity_type": "waste_note",
            "entity_id": note.get("id") or note.get("luc"),
            "thu": thu,
            "ghi_chu": ghi_chu[:200],
        },
    )
    return {"ok": True, **note}


@router.get("/api/v1/handover")
def handover_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_role(authorization)
    return {"items": kv_get("handover_history", []), "nguon": "quan"}


@router.post("/api/v1/handover")
def handover(
    body: HandoverBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_role(authorization)
    s = auth_session(authorization) or {}
    h = extract_handover(body.text)
    out = h.__dict__
    nums = validate_num(body.text, {"2", "3", "8", "15"})
    out["vf_num"] = nums.__dict__
    # VF-NUM mở rộng: hai ca khai lệch tiền cho cùng chủ đề → nêu ra, không tự chọn
    # bên nào (ADR-008). Sửa 2026-09-26 sau QA phát hiện bàn giao bỏ sót lệch số.
    conflicts = detect_number_conflicts(body.text)
    out["vf_number_conflict"] = [
        {"chu_de": c.chu_de, "gia_tri": c.gia_tri, "cau": c.cau} for c in conflicts
    ]
    out["co_lech_so"] = bool(conflicts)
    nv_id = s.get("nv_id") or role
    if body.alt_claim:
        other = {
            "nguoi": nv_id,
            "khung": "sang",
            "claim": body.alt_claim,
        }
        mine = {"nguoi": nv_id, "khung": "sang", "claim": h.tinh_hinh}
        c = present_conflict(mine, other)
        out["vf_conflict"] = c.__dict__
    entry = {
        "id": f"ho_{uuid.uuid4().hex[:8]}",
        "luc": datetime.now(UTC).isoformat(),
        "ai": role,
        **out,
    }

    def mut_hist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.append(entry)
        return rows[-50:]

    kv_mutate("handover_history", mut_hist, [])
    out["id"] = entry["id"]
    out["luc"] = entry["luc"]
    return out


@router.get("/api/v1/cam-nang")
def cam_nang_get(
    authorization: Annotated[str | None, Header()] = None,
    nguon: Annotated[str | None, Query(description="Loc nguon luat: that|mau|all (mac dinh all)")] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    tat_ca = [enrich_luat_ui(x) for x in list_luat()]
    che_do = (nguon or "all").strip().lower()
    if che_do == "that":
        items = [x for x in tat_ca if not is_demo_luat(x) and not _la_ban_ghi_mau(x)]
    elif che_do == "mau":
        items = [x for x in tat_ca if is_demo_luat(x) or _la_ban_ghi_mau(x)]
    else:
        items = tat_ca
    snap = pipeline_snapshot()
    return {
        "items": items,
        "mau": tim_mau(list_sua(include_synthetic=False)),
        "pipeline": snap,
        "nguon": "dung_lai_8_tuan",
        "nguon_loc": che_do if che_do in {"that", "mau", "all"} else "all",
        "so_luat_that_quan": snap["so_luat_that_quan"],
        "co_du_lieu_mau": _co_du_lieu_mau(tat_ca),
    }


@router.post("/api/v1/cam-nang/chay-8-buoc")
def cam_nang_run(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    role = _require_manager(authorization)
    sua_that = list_sua(include_synthetic=False)
    if len(sua_that) < 3:
        raise HTTPException(status_code=409, detail="chua_du_mau")
    mau_list = tim_mau(sua_that)
    if not mau_list:
        raise HTTPException(status_code=409, detail="chua_du_mau")

    existing = {x.get("id"): x for x in list_luat()}
    cho_chot: dict[str, Any] | None = None
    bi_loai: dict[str, Any] | None = None
    ung_vien: list[dict[str, Any]] = []

    for mau in mau_list:
        sua_loai = sua_rows_for_mau(mau, sua_that)
        goi_y = derive_rule_from_edits(mau, sua_loai)
        draft = propose_rule(mau, sua_mau=sua_loai, goi_y=goi_y)
        luat = de_xuat(
            mau,
            sua_rows=sua_loai,
            ban_nhap=asdict(draft) if draft is not None else None,
        )
        if luat is None:
            ung_vien.append(
                {"mau": mau["mau"], "trang_thai": "khong_du_tin_hieu", "buoc": 3, "id": None}
            )
            continue

        luat = kiem_chung(luat)
        if luat.get("trang_thai") == "loai":
            existing[luat["id"]] = luat
            if bi_loai is None:
                bi_loai = luat
            ung_vien.append(
                {
                    "mau": mau["mau"],
                    "id": luat["id"],
                    "trang_thai": luat["trang_thai"],
                    "buoc": luat["buoc"],
                    "vf_rule": luat.get("vf_rule", ""),
                }
            )
            continue

        luat = tap_su_tu_sua(luat, sua_loai)
        if luat.get("trang_thai") == "du_tap_su":
            luat["buoc"] = 6
            luat["trang_thai"] = "cho_chu_quan"
            luat["nguoi_de_xuat"] = role
            luat["nguoi_duyet_tap_su"] = role
            if cho_chot is None:
                cho_chot = luat
        existing[luat["id"]] = luat
        ung_vien.append(
            {
                "mau": mau["mau"],
                "id": luat["id"],
                "trang_thai": luat["trang_thai"],
                "buoc": luat["buoc"],
                "tap_su_dung": luat.get("tap_su_dung", 0),
            }
        )

    saved = list(existing.values())
    save_luat(saved)
    so_that = count_luat_that_quan(saved)
    _audit(
        "cam_nang_8_buoc",
        role,
        {
            "so_mau": len(mau_list),
            "cho_chu_quan": (cho_chot or {}).get("id"),
            "bi_loai": (bi_loai or {}).get("id"),
        },
    )
    return {
        "cho_chot": cho_chot,
        "bi_loai": bi_loai,
        "ung_vien": ung_vien,
        "nguon": mau_list[0].get("nguon", "ghi_truc_tiep"),
        "so_luat_that_quan": so_that,
        "pipeline": pipeline_snapshot(),
    }


@router.post("/api/v1/cam-nang/duyet")
def cam_nang_duyet(
    body: DuyetLuatBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    if body.ok:
        _require_chu_quan(authorization)
        role = "chu_quan"
    items = list_luat()
    for i, it in enumerate(items):
        if it.get("id") == body.id:
            if body.ok and it.get("trang_thai") != "cho_chu_quan":
                raise HTTPException(status_code=409, detail="luat_chua_cho_chu_quan")
            items[i] = duyet(it, ok=body.ok, ai=role)
            save_luat(items)
            _audit("cam_nang_chot", role, {"id": body.id, "ok": body.ok})
            return cast(dict[str, Any], items[i])
    raise HTTPException(status_code=404, detail="luat")


class GoLuatBody(BaseModel):
    id: str


@router.post("/api/v1/cam-nang/go")
def cam_nang_go(
    body: GoLuatBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_chu_quan(authorization)
    items = list_luat()
    for i, it in enumerate(items):
        if it.get("id") == body.id:
            if it.get("trang_thai") != "hieu_luc":
                raise HTTPException(status_code=409, detail="luat_chua_hieu_luc")
            items[i] = go_luat(it, ai=role)
            save_luat(items)
            _audit("cam_nang_go", role, {"id": body.id})
            return cast(dict[str, Any], items[i])
    raise HTTPException(status_code=404, detail="luat")


@router.post("/api/v1/sop")
def sop(
    body: SopBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    ctx = ops_context_from_dict(body.ngu_canh) or default_ops_context()
    luat = list_luat()
    if body.chi_luat_that:
        luat = [x for x in luat if not is_demo_luat(x) and not _la_ban_ghi_mau(x)]
    r = sop_answer(
        body.question,
        buoc=load_all_buoc(),
        luat=luat,
        ops_context=ctx,
    )
    return r.__dict__


@router.get("/api/v1/sop/golden")
def sop_golden(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_role(authorization)
    path = ROOT / "data" / "golden" / "sop" / "questions.jsonl"
    if not path.exists():
        raise HTTPException(status_code=409, detail="thieu_golden_sop")
    buoc = load_all_buoc()
    laws = list_luat()
    ctx = default_ops_context()
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    answers = []
    for row in rows:
        a = sop_answer(row["q"], buoc=buoc, luat=laws, ops_context=ctx)
        answers.append({"q": row["q"], **a.__dict__})
    chua = sum(1 for x in answers if x["chua_co"])
    cited = sum(1 for x in answers if x["trich_dan"] or x["chua_co"])
    return {
        "n": len(answers),
        "moi_cau_co_nguon_hoac_chua_co": cited == len(answers),
        "co_cau_chua_co": chua >= 1,
        "items": answers,
    }


@router.get("/api/v1/waste")
def waste(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_role(authorization)
    stored = kv_get("waste_notes", [])
    pairs = [(str(x.get("thu", "")), str(x.get("ghi_chu", ""))) for x in stored if x.get("ghi_chu")]
    return {
        "items": [x.__dict__ for x in cluster_waste(pairs)] if pairs else [],
        "ghi_chu": stored,
        "nguon": "quan",
        "co_du_lieu_mau": _co_du_lieu_mau(stored),
    }


@router.post("/api/v1/qr")
def qr_issue(
    body: QrBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    # 404 khi nhân viên không tồn tại — "không tìm thấy tài nguyên", KHÁC 422
    # (dữ liệu sai định dạng). Bug QA đợt 5: trước đây trả 422 nên client không
    # phân biệt được "mã NV sai" với "thiếu trường trong body".
    if not _known_nv(body.nv_id):
        raise HTTPException(status_code=404, detail="nhan_vien_khong_ton_tai")
    if not _known_ca(body.ca_id):
        raise HTTPException(status_code=404, detail="ca_khong_hop_le")
    tok = uuid.uuid4().hex

    def mut(bag: dict[str, Any]) -> dict[str, Any]:
        bag[tok] = {"nv_id": body.nv_id, "ca_id": body.ca_id, "used": False}
        return bag

    kv_mutate("qr", mut, {})
    return {"token": tok, "mot_lan": True}


@router.post("/api/v1/qr/{token}")
def qr_use(
    token: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    used: dict[str, Any] | None = None

    def mut(bag: dict[str, Any]) -> dict[str, Any]:
        nonlocal used
        row = bag.get(token)
        if not row:
            raise HTTPException(status_code=404, detail="qr")
        if row["used"]:
            raise HTTPException(status_code=409, detail="qr_da_dung")
        if row.get("nv_id") != caller["nv_id"]:
            raise HTTPException(status_code=403, detail="qr_khong_phai_cua_ban")
        row = dict(row)
        row["used"] = True
        bag[token] = row
        used = row
        return bag

    kv_mutate("qr", mut, {})
    assert used is not None

    # Khoá theo ngày {ngay: [nv_id, ...]} — đồng bộ với /api/v1/diem-danh.
    ghi_diem_danh(used["nv_id"])
    _audit(
        "attendance.check_in",
        used["nv_id"],
        {
            "entity_type": "attendance",
            "entity_id": used["nv_id"],
            "nv_id": used["nv_id"],
            "ca_id": used.get("ca_id"),
            "source": "qr",
        },
    )
    return {"ok": True, "nv_id": used["nv_id"]}


def _o_truc_con_thieu(ca_id: str, week: str) -> dict[str, Any] | None:
    """Ô ngày+khung chứa ca vừa đổi còn thiếu người không?

    Lưới lịch tuần gom các ca VỊ TRÍ cùng khung giờ thành MỘT ô và đếm theo
    SUẤT trực (mỗi vị trí một suất), nên kiểm tra thiếu phải cùng đơn vị:
    tổng suất đã xếp so với tổng định biên của cả ô. Trả None khi đã đủ —
    caller hiện cảnh báo chỉ khi có dict (tránh spam khi mọi thứ đã ổn).
    """
    meta = _ca_meta_map().get(str(ca_id))
    if not meta:
        return None
    thu, khung = str(meta.get("thu") or ""), str(meta.get("khung") or "")
    if not thu or not khung:
        return None
    metas = _ca_meta_map()
    o_ca_ids = [
        cid for cid, m in metas.items()
        if str(m.get("thu")) == thu and str(m.get("khung")) == khung
    ]
    if not o_ca_ids:
        return None
    dinh_bien = _so_nguoi_toi_thieu_map()
    pc = _phan_cong_tuan(week)
    da_xep = sum(len(pc.get(cid, [])) for cid in o_ca_ids)
    can = sum(int(dinh_bien.get(cid, 1)) for cid in o_ca_ids)
    if da_xep >= can:
        return None
    return {"thu": thu, "khung": khung, "da_xep": da_xep, "can": can, "thieu": can - da_xep}


def _apply_swap_to_assignments(
    *, giver: str, taker: str, ca_id: str, week: str, swap_id: str, actor: str,
) -> None:
    """Cập nhật hoán đổi nhân viên ca làm việc thật trên lịch khi lệnh đổi ca được đồng ý.

    Sau khi ghi phân công, luôn ghi nhật ký `lich_thay_doi_by_week` nguồn `doi_ca`
    — đây là điểm gãy cũ: duyệt đổi ca đổi người thật nhưng panel "ai đổi ca với
    ai" trên `/lich-tuan` im lặng vì không có bản ghi.
    """
    if not giver or not taker or not ca_id:
        return

    # Chụp phân công TRƯỚC khi mutate để diff A→B chính xác.
    by_week_truoc = kv_get("phan_cong_by_week", {})
    week_truoc_raw = by_week_truoc.get(week, {}) if isinstance(by_week_truoc, dict) else {}
    truoc: dict[str, list[str]] = {}
    if isinstance(week_truoc_raw, dict):
        truoc = {str(k): list(v) if isinstance(v, list) else [] for k, v in week_truoc_raw.items()}
    elif isinstance(kv_get("phan_cong", {}), dict):
        flat = kv_get("phan_cong", {})
        truoc = {str(k): list(v) if isinstance(v, list) else [] for k, v in flat.items()}

    def mut_pc(cur: dict[str, Any]) -> dict[str, Any]:
        assigned = list(cur.get(ca_id, []))
        if giver in assigned:
            assigned = [x for x in assigned if x != giver]
        if taker not in assigned:
            assigned.append(taker)
        cur[ca_id] = assigned
        return cur

    kv_mutate("phan_cong", mut_pc, {})

    def mut_pc_by_week(all_weeks: dict[str, Any]) -> dict[str, Any]:
        week_pc = all_weeks.setdefault(week, {})
        mut_pc(week_pc)
        return all_weeks

    kv_mutate("phan_cong_by_week", mut_pc_by_week, {})

    def mut_results_by_week(results: dict[str, Any]) -> dict[str, Any]:
        if week in results and isinstance(results[week], dict):
            pc = results[week].setdefault("phan_cong", {})
            mut_pc(pc)
        return results

    kv_mutate("lich_tuan_results_by_week", mut_results_by_week, {})

    # Diff sau mutate → nhật ký nguồn doi_ca (không để panel lịch tuần trống).
    try:
        from ca_api.services.solver_adapter import ghi_nhat_ky_thay_doi

        by_week_sau = kv_get("phan_cong_by_week", {})
        week_sau_raw = by_week_sau.get(week, {}) if isinstance(by_week_sau, dict) else {}
        sau: dict[str, list[str]] = {}
        if isinstance(week_sau_raw, dict):
            sau = {
                str(k): list(v) if isinstance(v, list) else []
                for k, v in week_sau_raw.items()
            }
        ghi_nhat_ky_thay_doi(week, sau, nguon="doi_ca", truoc=truoc)
    except Exception:
        pass

    record_sua(
        loai="doi_ca",
        truoc={"ca_id": ca_id, "nv_id": giver},
        sau={"ca_id": ca_id, "nv_id": taker, "swap_id": swap_id, "tuan_iso": week},
        ai=actor,
        now_iso=datetime.now(UTC).isoformat(),
    )


@router.post("/api/v1/cho-doi-ca")
async def swap_open(
    body: SwapBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    if body.a == body.b or not _known_ca(body.ca_id):
        raise HTTPException(status_code=422, detail="doi_ca_khong_hop_le")
    if caller["role"] == "nhan_vien" and caller["nv_id"] != body.a:
        raise HTTPException(status_code=403, detail="khong_phai_nguoi_tham_gia")
    if not _known_nv(body.a) or (body.b != "all" and not _known_nv(body.b)):
        raise HTTPException(status_code=422, detail="nhan_vien_khong_hop_le")
    week = (body.tuan or "").strip() or str(_life().get("tuan_iso") or "2026-W01")
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise HTTPException(status_code=422, detail="tuan_khong_hop_le")
    # Người nhả PHẢI đang giữ ca đó trong tuần của phiếu. Không kiểm ở đây thì
    # mở được phiếu nhả ca của người khác — phiếu rác, tới lúc duyệt mới lộ
    # (`ca_khong_trong_phan_cong_cua_nguoi_nhuong`).
    phan_tuan = _phan_cong_tuan(week)
    if body.a not in [str(x) for x in phan_tuan.get(body.ca_id, [])]:
        raise HTTPException(status_code=409, detail="nguoi_nhuong_khong_trong_ca")
    item = {
        "id": f"sw_{uuid.uuid4().hex[:8]}",
        "a": body.a,
        "b": body.b,
        "ca_id": body.ca_id,
        "trang_thai": "cho_xac_nhan",
        "nguon": "quan",
        "tuan_id": week,
    }

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.append(item)
        return items

    kv_mutate("swap", mut, [])
    
    actor = str(caller.get("nv_id") or caller.get("username") or caller["role"])
    audit_payload = {
        "entity_type": "shift_swap",
        "entity_id": item["id"],
        "a": body.a,
        "b": body.b,
        "ca_id": body.ca_id,
        "trang_thai": item["trang_thai"],
    }
    _audit("shift_swap.request", actor, audit_payload)
    await notify_ops_changed(
        "audit:shift_swap",
        details={"action": "shift_swap.request", "swap_id": item["id"]},
    )
    return item


@router.get("/api/v1/cho-doi-ca")
def swap_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Phiếu đổi ca mà NGƯỜI GỌI được thấy, kèm rủi ro kẹt ca của từng người.

    Vì sao phải lọc ở server: bản cũ trả nguyên `kv_get("swap", [])` cho mọi vai
    đăng nhập — nghĩa là một nhân viên đọc được toàn bộ phiếu đổi ca của quán,
    kể cả phiếu không liên quan tới mình. Lọc ở client (`doi-ca/page.tsx`) không
    phải là bảo vệ: chỉ cần gọi thẳng API là thấy hết.

    Kèm `rui_ro` cho từng phiếu để trả lời câu người dùng hỏi: "họ có bị kẹt ở ca
    nào không, sao mà biết được". Đây là phép ĐO, không phải lời khuyên.
    """
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = str(caller.get("role") or "")
    is_manager = role in {"quan_ly", "chu_quan"}
    caller_ids = {caller.get("nv_id"), caller.get("username")} - {None, ""}

    items = kv_get("swap", [])
    if not isinstance(items, list):
        items = []

    ra: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        b = it.get("b")
        parties = {it.get("a"), b} - {None, "", "all"}
        cong_khai = b == "all"
        if not is_manager and not (caller_ids & parties) and not cong_khai:
            continue
        ra.append(
            {
                **it,
                "rui_ro": _rui_ro_doi_ca(it),
                "la_nguoi_tham_gia": bool(caller_ids & parties) or cong_khai,
            }
        )

    return {
        "items": ra,
        "toi_la_quan_ly": is_manager,
        "me_nv_id": caller.get("nv_id"),
    }


def _rui_ro_doi_ca(item: dict[str, Any]) -> dict[str, Any]:
    """Đo rủi ro của một phiếu đổi ca: người nhận có bị kẹt ca không.

    Trả dữ liệu THÔ để UI tự trình bày, không trả câu khuyên. Ba thứ được đo:
      - `ca_giver`: ca người nhường có thật nằm trong phân công của họ không
        (nếu không thì phiếu này không thể thực hiện được).
      - `nguoi_nhan_dang_trung`: người nhận đã có ca khác giao giờ chưa.
      - `co_the_nhan`: kết luận, kèm `ly_do_chan` nói RÕ vì sao bị chặn.
    """
    week = str(item.get("tuan_id") or "")
    ca_id = str(item.get("ca_id") or "")
    a = str(item.get("a") or "")
    b = str(item.get("b") or "")

    phan = _phan_cong_tuan(week)
    meta = _ca_meta_map()
    ca_meta = meta.get(ca_id) or {}

    ca_giver = [x for x in phan.get(ca_id, []) if x == a]
    trung: list[dict[str, Any]] = []
    if b and b != "all":
        bat_dau = str(ca_meta.get("bat_dau") or "")
        ket_thuc = str(ca_meta.get("ket_thuc") or "")
        thu = str(ca_meta.get("thu") or "")
        for other_ca, ids in phan.items():
            if other_ca == ca_id or b not in [str(x) for x in ids]:
                continue
            om = meta.get(other_ca)
            if not isinstance(om, dict) or str(om.get("thu") or "") != thu:
                continue
            if _giao_nhau_gio(bat_dau, ket_thuc, str(om.get("bat_dau") or ""), str(om.get("ket_thuc") or "")):
                trung.append(
                    {
                        "ca_id": other_ca,
                        "thu": thu,
                        "gio": f"{om.get('bat_dau')}-{om.get('ket_thuc')}",
                    }
                )

    ly_do_chan = ""
    if not ca_giver:
        ly_do_chan = "ca_khong_trong_phan_cong_cua_nguoi_nhuong"
    elif trung:
        ly_do_chan = "nguoi_nhan_dang_co_ca_trung_gio"

    return {
        "tuan_id": week,
        "ca_id": ca_id,
        "ca": {
            "thu": str(ca_meta.get("thu") or ""),
            "gio": f"{ca_meta.get('bat_dau')}-{ca_meta.get('ket_thuc')}"
            if ca_meta.get("bat_dau")
            else "",
            "vi_tri": str(ca_meta.get("vi_tri") or ""),
        },
        "nguoi_nhuong_dang_trong_ca": bool(ca_giver),
        "nguoi_nhan": b,
        "nguoi_nhan_dang_trung": trung,
        "co_the_nhan": bool(ca_giver) and not trung,
        "ly_do_chan": ly_do_chan,
        "can_quan_ly_duyet": True,
    }


def _phan_cong_tuan(week: str) -> dict[str, list[str]]:
    """Phân công của một tuần, đọc `phan_cong_by_week` trước `phan_cong`."""
    if week:
        by_week = kv_get("phan_cong_by_week", {})
        if isinstance(by_week, dict):
            week_doc = by_week.get(week)
            if isinstance(week_doc, dict):
                return {str(k): [str(x) for x in v] for k, v in week_doc.items() if isinstance(v, list)}
    flat = kv_get("phan_cong", {})
    if isinstance(flat, dict):
        return {str(k): [str(x) for x in v] for k, v in flat.items() if isinstance(v, list)}
    return {}


def _ca_meta_map() -> dict[str, dict[str, Any]]:
    """ca_id → {thu, bat_dau, ket_thuc, vi_tri}, đọc từ seed `ca_mau_21`."""
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    out: dict[str, dict[str, Any]] = {}
    for c in seed.get("ca_mau_21", []):
        if not isinstance(c, dict) or not c.get("id"):
            continue
        out[str(c["id"])] = {
            "thu": str(c.get("thu") or _THU_MAP.get(int(c.get("ngay_offset", 1)), "T2")),
            "khung": str(c.get("khung") or ""),
            "bat_dau": str(c.get("bat_dau") or ""),
            "ket_thuc": str(c.get("ket_thuc") or ""),
            "vi_tri": str(c.get("vi_tri") or ""),
        }
    return out


def _so_nguoi_toi_thieu_map() -> dict[str, int]:
    """ca_id → số người tối thiểu, đọc từ seed `ca_mau_21` (mặc định 1)."""
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    out: dict[str, int] = {}
    for c in seed.get("ca_mau_21", []):
        if not isinstance(c, dict) or not c.get("id"):
            continue
        out[str(c["id"])] = int(c.get("so_nguoi_toi_thieu") or 1)
    return out


def _giao_nhau_gio(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """Hai khung giờ giao nhau? Chạm mép KHÔNG tính (nửa mở)."""
    def _p(t: str) -> int:
        try:
            hh, mm = t.strip()[:5].split(":")
            return int(hh) * 60 + int(mm)
        except (ValueError, AttributeError):
            return -1

    a1, a2, b1, b2 = _p(a_start), _p(a_end), _p(b_start), _p(b_end)
    if min(a1, a2, b1, b2) < 0:
        return False
    return a1 < b2 and b1 < a2


@router.post("/api/v1/cho-doi-ca/{swap_id}/dong-y")
@router.post("/api/v1/doi-ca/{swap_id}/xac-nhan")
async def swap_dong_y(
    swap_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    nv = caller.get("nv_id")
    found: dict[str, Any] | None = None

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal found
        for it in items:
            if it.get("id") != swap_id:
                continue
            # Swap đã bị từ chối thì không ai "đồng ý" hồi sinh được nữa.
            if it.get("trang_thai") == "tu_choi":
                raise HTTPException(status_code=409, detail="swap_da_tu_choi")
            parties = {it.get("a"), it.get("b")} - {None, "", "all"}
            caller_ids = {caller.get("nv_id"), caller.get("username")} - {None, ""}
            is_open_to_all = it.get("b") == "all"
            if not (caller_ids & parties) and not is_open_to_all and caller.get("role") not in {"quan_ly", "chu_quan"}:
                raise HTTPException(status_code=403, detail="khong_phai_nguoi_tham_gia")
            agreed = set(it.get("dong_y", []))
            if nv and (nv in parties or is_open_to_all or caller.get("role") in {"quan_ly", "chu_quan"}):
                agreed.add(nv)
            it["dong_y"] = sorted(agreed)
            if (is_open_to_all and nv != it["a"]) or (it["b"] != "all" and nv == it["b"]):
                it["trang_thai"] = "dong_y"
                if is_open_to_all and nv:
                    it["b"] = nv
            found = dict(it)
            return items
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")

    kv_mutate("swap", mut, [])
    if not found:
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")

    if found.get("trang_thai") == "dong_y":
        giver = str(found.get("a") or "")
        taker = str(found.get("b") or "")
        ca_id = str(found.get("ca_id") or "")
        swap_week = str(found.get("tuan_id") or _life().get("tuan_iso") or "2026-W01")

        # ── Cổng công bố ──
        # Đổi ca ở tuần CHƯA công bố là sửa một bản nháp quản lý còn đang xếp →
        # chặn. Ở tuần ĐÃ công bố thì phiếu vẫn cần một lượt quản lý duyệt, vì
        # đây là thay đổi lịch mà người khác đang chạy theo. Trước đây cả hai
        # trường hợp đều ghi thẳng vào phân công, chỉ cần hai bên bấm đồng ý.
        _guard_swap_cong_bo(swap_week, caller)

        _apply_swap_to_assignments(
            giver=giver,
            taker=taker,
            ca_id=ca_id,
            week=swap_week,
            swap_id=swap_id,
            actor=str(nv or caller.get("username") or caller["role"]),
        )

    _audit(
        "shift_swap.confirm",
        nv or caller["role"],
        {
            "entity_type": "shift_swap",
            "entity_id": swap_id,
            "dong_y": found.get("dong_y", []),
            "trang_thai": found.get("trang_thai"),
        },
    )
    await notify_ops_changed(
        "audit:shift_swap",
        details={"action": "shift_swap.confirm", "swap_id": swap_id},
    )
    # Báo cho UI biết ô trực sau đổi còn thiếu người không — đổi ca là thay
    # người (tổng suất không đổi) nên ô vốn thiếu vẫn thiếu; im lặng sẽ khiến
    # người đọc tưởng hệ thống quên cộng người.
    return {**found, "con_thieu": _o_truc_con_thieu(ca_id, swap_week)}


@router.post("/api/v1/cho-doi-ca/{swap_id}/tu-choi")
@router.post("/api/v1/doi-ca/{swap_id}/tu-choi")
async def swap_tu_choi(
    swap_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    nv = caller.get("nv_id")
    found: dict[str, Any] | None = None

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal found
        for it in items:
            if it.get("id") != swap_id:
                continue
            parties = {it.get("a"), it.get("b")} - {None, "", "all"}
            caller_ids = {caller.get("nv_id"), caller.get("username")} - {None, ""}
            if it.get("b") != "all" and not (caller_ids & parties) and caller.get("role") not in {"quan_ly", "chu_quan"}:
                raise HTTPException(status_code=403, detail="khong_phai_nguoi_tham_gia")
            it["trang_thai"] = "tu_choi"
            found = dict(it)
            return items
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")

    kv_mutate("swap", mut, [])
    if not found:
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")
    _audit(
        "shift_swap.reject",
        nv or caller["role"],
        {
            "entity_type": "shift_swap",
            "entity_id": swap_id,
            "trang_thai": found.get("trang_thai"),
        },
    )
    await notify_ops_changed(
        "audit:shift_swap",
        details={"action": "shift_swap.reject", "swap_id": swap_id},
    )
    return found


def _guard_swap_cong_bo(week: str, caller: dict[str, Any]) -> None:
    """Chặn đổi ca ở tuần chưa công bố; tuần đã công bố thì đòi quyền quản lý.

    Vì sao hai mức khác nhau:
      - Tuần CHƯA công bố: phân công chưa chốt, quản lý còn đang xếp. Cho nhân
        viên đổi ca ở đây là sửa bản nháp sau lưng người xếp → chặn hẳn.
      - Tuần ĐÃ công bố: lịch đã chốt và người khác đang chạy theo, nên đổi ca
        là thay đổi có hậu quả thật → cho phép, nhưng PHẢI có một người có quyền
        duyệt. Đây đúng là điều `test_capability_coverage` vẫn ghi trong mô tả
        ("consent bắt buộc") mà mã nguồn chưa hề thực thi.
    """
    trang_thai = str(_life(week).get("trang_thai") or "nhap")
    # `da_duyet` cũng là tuần đã chốt (nhất quán với /toi/lich và /ca/nha).
    if trang_thai not in {"da_duyet", "da_cong_bo", "da_dong"}:
        raise HTTPException(status_code=409, detail="lich_chua_cong_bo")
    if str(caller.get("role") or "") not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=409, detail="doi_ca_can_quan_ly_duyet")


@router.post("/api/v1/cho-doi-ca/{swap_id}/duyet")
async def swap_duyet(
    swap_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Quản lý duyệt và áp dụng phiếu đổi ca đã có đủ đồng ý của hai bên.

    Tách khỏi `dong-y` để hai việc khác nhau không lẫn vào nhau: `dong-y` là
    "tôi đồng ý", `duyet` là "tôi chịu trách nhiệm cho thay đổi này". Gộp lại thì
    quyền duyệt bị lẫn với quyền đồng ý, và không còn cách nào biết ai đã duyệt.
    """
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    if str(caller.get("role") or "") not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="chi_quan_ly_duyet_doi_ca")

    found: dict[str, Any] | None = None

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal found
        for it in items:
            if it.get("id") != swap_id:
                continue
            if it.get("trang_thai") == "tu_choi":
                raise HTTPException(status_code=409, detail="swap_da_tu_choi")
            if it.get("da_duyet_boi"):
                raise HTTPException(status_code=409, detail="swap_da_duyet_roi")
            # Chặn duyệt phiếu không bao giờ áp được: người nhường không giữ
            # ca MÀ người nhận cũng chưa có ca (phiếu hỏng từ lúc mở). Còn khi
            # người nhận đã vào ca (phiếu áp rồi ở bước đồng ý của quản lý/chủ)
            # thì duyệt chỉ ghi nhận phê chuẩn — `_apply` là noop an toàn.
            # Chưa có người nhận (`b == "all"`) cũng không được duyệt: tránh ghi
            # chuỗi "all" vào phân công. Xung đột giờ của người nhận thì KHÔNG
            # chặn: đó là quyết định của quản lý khi đã thấy cảnh báo.
            if str(it.get("b") or "") == "all":
                raise HTTPException(status_code=409, detail="swap_chua_co_nguoi_nhan")
            wk = str(it.get("tuan_id") or _life().get("tuan_iso") or "2026-W01")
            danh_sach = [
                str(x)
                for x in _phan_cong_tuan(wk).get(str(it.get("ca_id") or ""), [])
            ]
            con_nhuong = str(it.get("a") or "") in danh_sach
            da_nhan = str(it.get("b") or "") in danh_sach
            if not con_nhuong and not da_nhan:
                raise HTTPException(
                    status_code=409,
                    detail="ca_khong_trong_phan_cong_cua_nguoi_nhuong",
                )
            it["da_duyet_boi"] = str(caller.get("nv_id") or caller.get("username") or "")
            it["trang_thai"] = "da_duyet"
            found = dict(it)
            return items
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")

    kv_mutate("swap", mut, [])
    if not found:
        raise HTTPException(status_code=404, detail="swap_khong_tim_thay")

    week = str(found.get("tuan_id") or _life().get("tuan_iso") or "2026-W01")
    ca_id = str(found.get("ca_id") or "")
    _apply_swap_to_assignments(
        giver=str(found.get("a") or ""),
        taker=str(found.get("b") or ""),
        ca_id=ca_id,
        week=week,
        swap_id=swap_id,
        actor=str(caller.get("nv_id") or caller.get("username") or "quan_ly"),
    )
    _audit(
        "shift_swap.approve",
        str(caller.get("nv_id") or caller["role"]),
        {"entity_type": "shift_swap", "entity_id": swap_id, "tuan_id": week},
    )
    await notify_ops_changed(
        "audit:shift_swap",
        details={"action": "shift_swap.approve", "swap_id": swap_id},
    )
    return {**found, "con_thieu": _o_truc_con_thieu(ca_id, week)}


@router.get("/api/v1/ops/pickers")
def ops_pickers(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Nhân viên và ca cho dropdown — mọi vai đăng nhập."""
    _require_role(authorization)
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    staff = [
        {"id": n["id"], "ten": n.get("ten") or n["id"]}
        for n in list_nhan_vien_ops()
        if isinstance(n, dict) and n.get("id")
    ]
    shifts = []
    for c in seed.get("ca_mau_21", []):
        if not isinstance(c, dict) or not c.get("id"):
            continue
        thu = c.get("thu") or _THU_MAP.get(int(c.get("ngay_offset", 1)), "T2")
        vi = _VI_TRI_VI.get(str(c.get("vi_tri", "")), str(c.get("vi_tri", "")).replace("_", " "))
        bat = c.get("bat_dau", "")
        ket = c.get("ket_thuc", "")
        label = f"{thu} · {bat}–{ket} · {vi}".strip(" ·")
        shifts.append(
            {
                "id": c["id"],
                "label": label,
                "thu": thu,
                "bat_dau": bat,
                "ket_thuc": ket,
                "vi_tri": c.get("vi_tri"),
            }
        )
    me = auth_session(authorization)
    return {
        "nhan_vien": staff,
        "ca": shifts,
        "me_nv_id": me.get("nv_id") if me else None,
        "nguon": "quan",
    }


@router.get("/api/v1/ab")
def ab_table() -> dict[str, Any]:
    return {
        "nguon": "quan",
        "hang": [
            {"ten": "1 agent xử lô", "p50_ms": None, "ghi": "chưa đo live"},
            {"ten": "N agent song song", "p50_ms": None, "ghi": "chưa đo live"},
            {"ten": "replay 8 task orc", "p50_ms": 0, "ghi": "cùng process"},
        ],
    }


@router.get("/api/v1/vf/conflict")
@router.get("/api/v1/vf/conflict-demo")
def conflict_sample() -> dict[str, Any]:
    a = {"nguoi": "nv_03", "khung": "sang", "claim": "có mặt"}
    b = {"nguoi": "nv_03", "khung": "sang", "claim": "vắng"}
    return cast(dict[str, Any], present_conflict(a, b).__dict__)
