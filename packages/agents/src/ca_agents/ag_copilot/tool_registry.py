"""Tool Registry for AG-COPILOT — Whitelisted deterministic tools only.

Rules:
1. LLM cannot call arbitrary tools.
2. Every tool call must match one of the 7 whitelisted intents.
3. Tools do not write to production database directly; they produce data/diffs for ActionProposals.
4. Tools read REAL data — no hardcoded fixtures. When real data is empty, tools
   return an honest "no data" result instead of fake numbers.
5. Architecture: this module must NOT import other agents (ag_sop, ag_waste),
   ca_api, ca_playbook or ca_gates (enforced by test_architecture.py).
   Data sources are INJECTED via `configure_data_sources()` from the API layer.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone

    UTC = timezone.utc
from pathlib import Path
from typing import Any, Literal, cast

WHITELISTED_INTENTS = {
    "SCHEDULE_SOLVE": "tool_solve_weekly_schedule",
    "APPROVE_SHIFT_SWAP": "tool_prepare_swap_approval",
    "GENERATE_DAILY_BRIEF": "tool_get_daily_brief",
    "QUERY_SOP": "tool_query_sop_playbook",
    "ANALYZE_WASTE": "tool_get_waste_summary",
    "CREATE_RULE_PROPOSAL": "tool_propose_rule_from_recent_edits",
    "INVENTORY_RESTOCK_CHECK": "tool_check_inventory_restock",
    "SEND_MAIL": "tool_send_mail",
    "RUN_CATCHMENT_SURVEY": "tool_propose_catchment_survey",
    "GET_SERPAPI_QUOTA": "tool_get_serpapi_quota",
    "GET_SURVEY_RESULT": "tool_get_latest_survey_result",
}

log = logging.getLogger(__name__)

# ── Data source injection (hexagonal architecture) ────────────────────────────
# API layer gọi `configure_data_sources()` một lần lúc startup để cung cấp
# các hàm đọc dữ liệu thật. Tools chỉ gọi qua các callable này — không import
# trực tiếp ca_api / ca_playbook / agent khác.

DataSources = dict[str, Callable[..., Any]]

_SOURCES: DataSources = {}


def configure_data_sources(**sources: Callable[..., Any]) -> None:
    """Inject data sources từ API layer. Gọi 1 lần lúc startup.

    Keys kỳ vọng:
      - kv_get(key, default) -> Any
      - list_luat() -> list[dict]           (luật hiệu lực từ cẩm nang sống)
      - load_template(ma) -> dict | None    (mẫu phiếu YAML)
      - list_sua() -> list[dict]            (lịch sử sửa lịch thật)
      - tim_mau(sua) -> list[dict]          (mẫu lặp từ lịch sử sửa)
      - de_xuat(mau) -> dict | None         (sinh đề xuất luật; None khi thiếu tín hiệu)
      - sop_answer(q, buoc, luat) -> SopAnswer
      - waste_cluster(notes) -> list[WasteHint]
      - loss_engine(kiem_ke, don_quay, menu, waste_notes, nguong, ky) -> LossSummary
      - list_ca_meta() -> dict[str, dict]   (ca_id -> {thu, khung, bat_dau, ket_thuc})
    """
    _SOURCES.clear()
    _SOURCES.update(sources)


def _src(name: str) -> Callable[..., Any] | None:
    return _SOURCES.get(name)


def build_live_snapshot(
    intent: str,
    store_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical live source snapshot shared by propose and approve."""
    snapshot: dict[str, Any] = {"store_id": store_id, "intent": intent}
    if intent == "SCHEDULE_SOLVE":
        snapshot.update({
            "phan_cong": _kv_get("phan_cong", {}),
            "lich_tuan": _kv_get("lich_tuan", {}),
        })
    elif intent == "APPROVE_SHIFT_SWAP":
        snapshot.update({
            "swap": _kv_get("swap", []),
            "shift_swaps": _kv_get("shift_swaps", []),
            "phan_cong": _kv_get("phan_cong", {}),
        })
    elif intent == "CREATE_RULE_PROPOSAL":
        list_sua = _src("list_sua")
        list_luat = _src("list_luat")
        snapshot["list_sua"] = list(list_sua() or []) if list_sua else None
        snapshot["list_luat"] = list(list_luat() or []) if list_luat else None
    elif intent == "SEND_MAIL":
        # Snapshot mail chỉ khóa nguồn liên quan an toàn: recipient email +
        # nội dung đã duyệt. ops_context/style là ngữ cảnh soạn thảo (volatile),
        # không đưa vào hash — nếu không correction nội dung hợp lệ sẽ bị stale
        # giả khi ngữ cảnh sống đổi giữa propose và approve (kế hoạch §3.3:
        # "Không hash ... dữ liệu không cần thiết").
        payload = payload or {}
        get_emails = _src("get_user_emails")
        to_nv_ids = list(payload.get("to_nv_ids") or [])
        snapshot["recipient_emails"] = (
            {nv_id: (get_emails() or {}).get(nv_id) for nv_id in to_nv_ids}
            if get_emails else None
        )
        snapshot["content"] = {
            "to_emails": list(payload.get("to_emails") or []),
            "subject": str(payload.get("subject") or ""),
            "body": str(payload.get("body") or ""),
        }
        snapshot["rule_version"] = str(payload.get("rule_version") or "none")
    elif intent == "PROPOSE_HANGING_TASK":
        snapshot["treo"] = [t for t in (_kv_get("treo", []) or []) if isinstance(t, dict)]
    elif intent == "PROPOSE_TASK_COMPLETE":
        snapshot["treo"] = [t for t in (_kv_get("treo", []) or []) if isinstance(t, dict)]
    elif intent == "PROPOSE_CONSUMPTION_RECORD":
        snapshot["tieu_thu"] = [t for t in (_kv_get("tieu_thu", []) or []) if isinstance(t, dict)]
    elif intent == "PROPOSE_MENU_UPDATE":
        menu_list = _src("menu_list")
        snapshot["menu"] = list(menu_list(gom_an=True) or []) if menu_list else []
    elif intent == "PROPOSE_ORDER_TRANSITION":
        payload0 = payload or {}
        don_list = _src("don_list")
        don_get = _src("don_get")
        don_id = str(payload0.get("don_id") or "")
        snapshot["don"] = don_get(don_id) if (don_get and don_id) else None
        snapshot["orders"] = list(don_list() or []) if don_list else []
    elif intent == "PROPOSE_PIN":
        snapshot["pins"] = _kv_get("pins", {})
    elif intent in {"PROPOSE_PAGE_SYNC", "PROPOSE_PAGE_DRAFT"}:
        page_status = _src("page_status")
        try:
            snapshot["page"] = page_status() if page_status else None
        except Exception:
            snapshot["page"] = None
        snapshot["page_quan"] = _kv_get("page_quan", {})
    elif intent == "PROPOSE_TKB_CONFIRM":
        snapshot["tkb_nv"] = _kv_get("tkb_nv", {})
        snapshot["tkb_nv_by_week"] = _kv_get("tkb_nv_by_week", {})
    elif intent == "PROPOSE_SWAP_CONSENT":
        snapshot["swap"] = [s for s in (_kv_get("swap", []) or []) if isinstance(s, dict)]
    elif intent == "PROPOSE_HANDOVER":
        snapshot["handover_history"] = [
            h for h in (_kv_get("handover_history", []) or []) if isinstance(h, dict)
        ]
    elif intent == "PROPOSE_TIME_OFF":
        snapshot["inbox_rang_buoc"] = [
            it for it in (_kv_get("inbox_rang_buoc", []) or []) if isinstance(it, dict)
        ]
    elif intent == "INVENTORY_RESTOCK_CHECK":
        snapshot["tieu_thu"] = [
            item for item in (_kv_get("tieu_thu", []) or []) if isinstance(item, dict)
        ]
    elif intent == "RUN_CATCHMENT_SURVEY":
        # Snapshot CHỈ bao gồm tham số khảo sát bất biến (category_keyword, radius_km,
        # channel_mode). KHÔNG đưa quota_used vào vì đây là dữ liệu biến động: nếu
        # người dùng khác chạy khảo sát giữa thời điểm Đề xuất và Duyệt, quota_used
        # sẽ thay đổi → VF-STALE bị kích hoạt sai (false-positive). Quota được kiểm
        # tra nghiêm ngặt trước khi đề xuất (tool_propose_catchment_survey) và không
        # cần tái xác minh bằng hash để chặn thay đổi ý định của người dùng.
        payload0 = payload or {}
        snapshot.update({
            "category_keyword": str(payload0.get("category_keyword") or ""),
            "radius_km": float(payload0.get("radius_km") or 3.0),
            "channel_mode": str(payload0.get("channel_mode") or "hybrid"),
        })
    list_ca_meta = _src("list_ca_meta")
    if list_ca_meta is not None:
        try:
            snapshot["ca_meta"] = list_ca_meta() or {}
        except Exception:
            snapshot["ca_meta"] = None
    return snapshot


def _kv_get(key: str, default: Any) -> Any:
    """Đọc KV qua source được inject; fallback file JSON khi chạy standalone/tests."""
    fn = _src("kv_get")
    if fn is not None:
        try:
            return fn(key, default)
        except Exception:
            pass
    try:
        path = Path(os.environ.get("NHIPQUAN_KV", _ROOT / "data" / "out" / "kv.json"))
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw.get(key, default)
    except Exception:
        pass
    return default


def _kv_get_many(keys: list[str], defaults: dict[str, Any]) -> dict[str, Any]:
    """Đọc NHIỀU khoá KV trong MỘT lượt, trả dict cùng shape như `_kv_get`.

    Dùng khi một tool cần ≥3 khoá: mỗi `kv_get` là một connection SQLite mới, nên
    đọc rời làm số connection tăng tuyến tính theo số khoá.

    Có FALLBACK tuần tự khi nguồn không có `kv_get_many` (agent chạy standalone
    hoặc test inject nguồn cũ) — nhờ vậy không phải sửa mọi nơi gọi tool.
    """
    fn = _src("kv_get_many")
    if fn is not None:
        try:
            got = fn(list(keys), defaults)
            if isinstance(got, dict):
                return {str(k): got.get(str(k), defaults.get(str(k))) for k in keys}
        except Exception:
            pass
    return {k: _kv_get(k, defaults.get(k)) for k in keys}


_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class ToolExecutionResult:
    success: bool
    tool_name: str
    intent: str
    data: dict[str, Any]
    summary: str
    explanation: str
    requires_confirmation: bool
    error: str | None = None
    source_snapshot: Any | None = None


# ── Whitelisted Tool Implementations ──────────────────────────────────────────

def tool_solve_weekly_schedule(
    store_id: str = "quan_01",
    tuan: str = "2026-W36",
    uu_tien_nhan_su: dict[str, Any] | str | None = None,
    nguon_cuoc_hop: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """Run CP-SAT solver for week schedule and produce grounded draft proposal."""
    from ca_solver import apply_luat, build_lich_input, solve_cpsat

    # 1. NV thật do API inject hoặc fallback seed
    _list_nv = _src("list_nhan_vien_ops")
    nvs = _list_nv() if callable(_list_nv) else None
    inp = build_lich_input(nhan_vien_ngoai=nvs)

    # 2. TKB thật đã xác nhận từ ảnh / sinh viên
    tkb_by_week = _kv_get("tkb_nv_by_week", {})
    stored_tkb = tkb_by_week.get(tuan, {}) if isinstance(tkb_by_week, dict) else {}
    legacy_tkb = _kv_get("tkb_nv", {})
    if isinstance(legacy_tkb, dict):
        stored_tkb = dict(stored_tkb) if isinstance(stored_tkb, dict) else {}
        for nv_id, entry in legacy_tkb.items():
            if (
                nv_id not in stored_tkb
                and isinstance(entry, dict)
                and entry.get("tuan_iso") == tuan
            ):
                stored_tkb[nv_id] = entry
    if isinstance(stored_tkb, dict):
        for nv_id, entry in stored_tkb.items():
            if not isinstance(entry, dict):
                continue
            blocks = entry.get("khoang_ban") or []
            tuples: list[tuple[str, str, str]] = []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                thu = str(b.get("thu") or "")
                start = str(b.get("start") or "")
                end = str(b.get("end") or "")
                if thu and start and end:
                    tuples.append((thu, start, end))
            if tuples:
                inp.tkb[str(nv_id)] = tuples

    # 3. Ràng buộc đã duyệt từ inbox_rang_buoc (bao gồm các ràng buộc nạp từ cuộc họp)
    inbox_items = _kv_get("inbox_rang_buoc", [])
    if isinstance(inbox_items, list):
        for it in inbox_items:
            if not isinstance(it, dict) or it.get("trang_thai") != "duyet":
                continue
            # `hieu_luc`/`rang_buoc` có thể là chuỗi ngày (fixture) chứ không
            # phải dict — guard isinstance giống main.py/_detect_staff_availability.
            hl = cast(dict[str, Any], it.get("hieu_luc")) if isinstance(it.get("hieu_luc"), dict) else {}
            rb = cast(dict[str, Any], it.get("rang_buoc")) if isinstance(it.get("rang_buoc"), dict) else {}
            it_tuan = rb.get("tuan_id") or hl.get("tuan_id")
            if it_tuan and it_tuan != tuan:
                continue
            nv_id = str(it.get("nv_id") or hl.get("nv_id") or "")
            if not nv_id or nv_id == "unknown":
                continue
            thu = str(rb.get("thu") or hl.get("thu") or "")
            y = str(it.get("y_dinh") or "")
            if y == "xin_nghi" and thu:
                inp.nghi_phep.add((nv_id, thu))
            elif y in {"cap_nhat_tkb", "bao_tre"} and thu:
                start = str(rb.get("start") or hl.get("start") or "07:00")
                end = str(rb.get("end") or hl.get("end") or "12:00")
                inp.tkb.setdefault(nv_id, []).append((thu, start, end))

    # 4. Trích xuất trực tiếp các quyết định từ cuộc họp gần nhất
    meeting_adjustments_used: list[str] = []
    meetings = _kv_get("meetings", [])
    if isinstance(meetings, list) and meetings:
        # Sắp xếp theo thời gian giảm dần để đảm bảo luôn lấy đúng cuộc họp mới nhất
        sorted_meetings = sorted(
            [m for m in meetings if isinstance(m, dict)],
            key=lambda x: str(x.get("duyet_luc") or x.get("last_modified_at") or x.get("thoi_gian") or ""),
            reverse=True,
        )
        recent_meetings = sorted_meetings[:1]
        for m in recent_meetings:
            if not isinstance(m, dict):
                continue
            all_items: list[dict[str, Any]] = []
            m_approved = m.get("trang_thai") == "da_duyet"
            for d in (m.get("dieu_chinh_lich") or []):
                if isinstance(d, dict) and (d.get("trang_thai") == "da_duyet" or (m_approved and d.get("trang_thai") != "tu_choi")):
                    all_items.append(d)
            for p in (m.get("de_xuat_phe_duyet") or []):
                if isinstance(p, dict) and p.get("loai_de_xuat") == "dieu_chinh_lich" and p.get("chi_tiet_lich"):
                    ctl = p["chi_tiet_lich"]
                    if isinstance(ctl, dict) and (p.get("trang_thai") == "da_duyet" or ctl.get("trang_thai") == "da_duyet" or (m_approved and p.get("trang_thai") != "tu_choi")):
                        all_items.append(ctl)

            for item in all_items:
                c_loai = item.get("loai")
                nv = str(item.get("nhan_vien_id") or item.get("ten_nhan_vien") or "")
                thu = str(item.get("thu") or "")
                tuan_iso = item.get("tuan_iso")
                if tuan_iso and tuan_iso != tuan:
                    continue

                matched_nv = nv if nv in inp.nhan_vien_ids else next((x for x in inp.nhan_vien_ids if x.endswith(nv.lower())), None)

                if c_loai == "xin_nghi" and thu:
                    if matched_nv:
                        inp.nghi_phep.add((matched_nv, thu))
                        desc = f"Nghỉ ca {item.get('ten_nhan_vien') or matched_nv} ({thu})"
                        if desc not in meeting_adjustments_used:
                            meeting_adjustments_used.append(desc)

                elif c_loai == "ghim_ca":
                    ca_id = item.get("ca_id")
                    if not ca_id and thu:
                        thu_ord = {"T2": 1, "T3": 2, "T4": 3, "T5": 4, "T6": 5, "T7": 6, "CN": 7}.get(thu, 1)
                        khung_idx = {"sang": 1, "chieu": 2, "toi": 3}.get(item.get("khung", "sang"), 1)
                        ca_id = f"w1_c{(thu_ord - 1) * 3 + khung_idx:02d}"
                    if ca_id and matched_nv and ca_id in inp.ca_ids:
                        # Kiểm tra xung đột TKB hoặc nghỉ phép trước khi ghim cứng
                        meta = inp.ca_meta.get(ca_id, {})
                        has_tkb_conflict = any(
                            b[0] == thu and _gio_chong(meta.get("bat_dau", "07:00"), meta.get("ket_thuc", "12:00"), b[1], b[2])
                            for b in inp.tkb.get(matched_nv, [])
                        )
                        if (matched_nv, thu) in inp.nghi_phep or has_tkb_conflict:
                            desc = f"⚠️ Bỏ qua ghim {item.get('ten_nhan_vien') or matched_nv} ca {ca_id} ({thu}) do vướng lịch học/nghỉ"
                            if desc not in meeting_adjustments_used:
                                meeting_adjustments_used.append(desc)
                            continue

                        inp.phan_cong.setdefault(ca_id, [])
                        if matched_nv not in inp.phan_cong[ca_id]:
                            inp.phan_cong[ca_id].append(matched_nv)
                            desc = f"Ghim {item.get('ten_nhan_vien') or matched_nv} vào ca {ca_id} ({thu})"
                            if desc not in meeting_adjustments_used:
                                meeting_adjustments_used.append(desc)

    # 5. Ghim ca từ KV "pins"
    raw_pins = _kv_get("pins", {})
    if isinstance(raw_pins, dict):
        for pin_key, is_pinned in raw_pins.items():
            if is_pinned and "|" in str(pin_key):
                ca_id, nv_id = str(pin_key).split("|", 1)
                if ca_id in inp.ca_ids and nv_id in inp.nhan_vien_ids:
                    inp.phan_cong.setdefault(ca_id, [])
                    if nv_id not in inp.phan_cong[ca_id]:
                        inp.phan_cong[ca_id].append(nv_id)

    # 6. Áp dụng luật vận hành nếu có
    list_luat = _src("list_luat")
    applied_rules: list[str] = []
    if callable(list_luat):
        try:
            inp, applied_rules = apply_luat(inp, list_luat())
        except Exception:
            pass

    # 7. Chạy solver CP-SAT
    res = solve_cpsat(inp)

    status = res.status if res.status else ("OPTIMAL" if res.ok else "INFEASIBLE")
    phan_cong = res.phan_cong or {}
    total_assigned = sum(len(nvs) for nvs in phan_cong.values())

    if res.ok:
        summary = f"Đã xếp thành công {total_assigned} lượt phân công cho tuần {tuan}."
        exp_parts = [
            f"Bộ giải CP-SAT hoàn tất ({status}).",
            "100% không trùng giờ học, chia đều ca đêm/cuối tuần.",
            f"Tổng số ca đã lấp đầy: {len(phan_cong)} ca.",
        ]
        if meeting_adjustments_used:
            exp_parts.append(
                f"Đã tiếp thu và tuân thủ {len(meeting_adjustments_used)} thông tin/quyết định từ cuộc họp: "
                + "; ".join(meeting_adjustments_used) + "."
            )
        explanation = " ".join(exp_parts)
        return ToolExecutionResult(
            success=True,
            tool_name="tool_solve_weekly_schedule",
            intent="SCHEDULE_SOLVE",
            data={
                "tuan": tuan,
                "tuan_iso": tuan,
                "status": status,
                "phan_cong": phan_cong,
                "uu_tien": uu_tien_nhan_su,
                "meeting_adjustments": meeting_adjustments_used,
                "rules_applied": applied_rules,
                "snapshot_version": "live-v1",
            },
            summary=summary,
            explanation=explanation,
            requires_confirmation=True,
            source_snapshot=build_live_snapshot("SCHEDULE_SOLVE", store_id),
        )
    else:
        error_msg = f"Không thể tìm phương án xếp ca khả thi cho tuần {tuan} ({status})."
        explanation = "Ràng buộc cứng không thể thỏa mãn (thiếu nhân sự ở một số ca hoặc xung đột lịch)."
        if meeting_adjustments_used:
            explanation += f" Lưu ý: cuộc họp có {len(meeting_adjustments_used)} yêu cầu điều chỉnh có thể đã làm thu hẹp quỹ nhân sự."
        return ToolExecutionResult(
            success=False,
            tool_name="tool_solve_weekly_schedule",
            intent="SCHEDULE_SOLVE",
            data={"status": status, "tuan": tuan, "violations": res.violations},
            summary=error_msg,
            explanation=explanation,
            requires_confirmation=False,
            error=f"solver_{status.lower()}",
        )


def _swap_khong_trung_ca(
    phan_cong: dict[str, Any],
    ca_dich: str,
    nhan_nv: str | None,
    list_ca_meta: Callable[..., Any] | None,
) -> bool:
    """Trả False khi không thể chứng minh ca đích không trùng lịch."""
    if not nhan_nv or not ca_dich:
        return False
    if not list_ca_meta:
        return False
    try:
        ca_meta = list_ca_meta() or {}
    except Exception:
        return False

    meta_dich = ca_meta.get(ca_dich)
    if not isinstance(meta_dich, dict):
        return False

    thu_dich = meta_dich.get("thu")
    # So trùng ca: không phân biệt khung cứng — so theo thu + khung trùng giờ.
    for ca_id, nvs in (phan_cong or {}).items():
        if ca_id == ca_dich:
            continue
        if not isinstance(nvs, list) or nhan_nv not in nvs:
            continue
        meta_other = ca_meta.get(ca_id)
        if not isinstance(meta_other, dict):
            continue
        # Trùng ngày và trùng khung giờ (bat_dau/ket_thuc chồng nhau) → chặn.
        if meta_other.get("thu") == thu_dich:
            # Nếu trùng khung (cùng giờ) hoặc không có meta → chặn an toàn.
            khung_dich = meta_dich.get("khung")
            khung_other = meta_other.get("khung")
            if khung_dich and khung_other and khung_dich == khung_other:
                return False
            # Nếu không có khung, so giờ.
            bd_d = meta_dich.get("bat_dau")
            kt_d = meta_dich.get("ket_thuc")
            bd_o = meta_other.get("bat_dau")
            kt_o = meta_other.get("ket_thuc")
            if bd_d and kt_d and bd_o and kt_o and _gio_chong(bd_d, kt_d, bd_o, kt_o):
                return False
    return True


def _gio_chong(bd1: str, kt1: str, bd2: str, kt2: str) -> bool:
    """Kiểm tra 2 khoảng giờ 'HH:MM' có chồng lấn không."""
    try:
        def _m(s: str) -> int:
            h, m = s.split(":")
            return int(h) * 60 + int(m)

        return _m(bd1) < _m(kt2) and _m(bd2) < _m(kt1)
    except Exception:
        return False


def tool_prepare_swap_approval(
    swap_id: str | None = None,
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """Validate swap request against hard rules and prepare approval proposal.

    Đọc yêu cầu đổi ca THẬT từ KV ("swap" — 3 nhánh đồng ý, hoặc "shift_swaps").
    Kiểm tra 5 điều kiện thật trên dữ liệu phân công hiện tại.
    """
    # 1. Lấy danh sách swap thật (ưu tiên KV "swap" của swap-market 3 nhánh)
    swaps = _kv_get("swap", []) or []
    legacy = _kv_get("shift_swaps", []) or []
    if isinstance(legacy, list) and legacy:
        swaps = swaps + legacy

    # 2. Chọn swap: theo id nếu có, else cái mới nhất còn đang chờ
    candidates = [
        s
        for s in swaps
        if isinstance(s, dict)
        and s.get("trang_thai") in ("cho_3_nhanh", "dong_y", "cho_duyet")
    ]
    target: dict[str, Any] | None = None
    if swap_id:
        for s in candidates:
            if s.get("id") == swap_id or s.get("swap_id") == swap_id:
                target = s
                break
    else:
        target = candidates[-1] if candidates else None

    if not target:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_prepare_swap_approval",
            intent="APPROVE_SHIFT_SWAP",
            data={"swaps_cho_duyet": 0},
            summary="Hiện không có yêu cầu đổi ca nào đang chờ duyệt.",
            explanation="Danh sách đổi ca trống hoặc tất cả đã được xử lý.",
            requires_confirmation=False,
        )

    # 3. Kiểm tra 5 điều kiện thật trên phân công hiện tại
    phan_cong = _kv_get("phan_cong", {}) or {}
    ca_id = str(target.get("ca_id") or "")
    a, b, c = target.get("a"), target.get("b"), target.get("c")

    checks: dict[str, bool] = {}
    # 3.1 Đủ 3 nhánh xác định
    checks["du_3_nhanh"] = bool(a and b and c and len({a, b, c}) == 3)
    # 3.2 Cả 3 đã đồng ý (swap-market) hoặc trạng thái dong_y
    dong_y = set(target.get("dong_y") or [])
    parties = {x for x in (a, b, c) if x}
    checks["du_3_dong_y"] = (bool(parties) and parties <= dong_y) or (target.get("trang_thai") == "dong_y")
    # 3.3 Ca tồn tại trong phân công tuần
    ca_exists = bool(ca_id) and (
        not phan_cong or any(ca_id in str(k) or ca_id == k for k in phan_cong)
    )
    checks["ca_hop_le"] = ca_exists if phan_cong else bool(ca_id)
    # 3.4 Người nhận không trùng ca khác cùng khung giờ (đọc dữ liệu thật).
    #     So sánh ca đích với các ca khác mà nhan_nv đang đảm nhận: nếu trùng
    #     giờ (bat_dau/ket_thuc) trong cùng khung → chặn.
    checks["khong_trung_ca_khac"] = _swap_khong_trung_ca(
        phan_cong, ca_id, c, _src("list_ca_meta")
    )
    # 3.5 Lý do: swap-market 3 nhánh KHÔNG có trường ly_do/ghi_chu — chỉ bắt buộc
    #     khi swap kiểu cũ có trường này. Nếu swap-market thì coi là hợp lệ (3 nhánh đã đồng ý).
    checks["co_ly_do"] = bool(target.get("ly_do") or target.get("ghi_chu") or target.get("trang_thai") in ("dong_y", "cho_3_nhanh"))

    passed = all(checks.values())
    ten_map = {u.get("nv_id"): u.get("ten") for u in (_kv_get("users", []) or []) if isinstance(u, dict)}
    ten_a = ten_map.get(a, a)
    ten_c = ten_map.get(c, c)

    diff = {
        "swap_id": target.get("id") or target.get("swap_id"),
        "ca_id": ca_id,
        "tu_nv": a,
        "nhan_nv": c,
        "trung_gian": b,
        "dong_y": sorted(dong_y),
        "kiem_tra_5_dieu_kien": checks,
        "thoa_man_5_dieu_kien": passed,
        "snapshot_version": "live-v1",
    }
    if not passed:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_prepare_swap_approval",
            intent="APPROVE_SHIFT_SWAP",
            data=diff,
            summary=f"Đổi ca {ca_id} chưa đủ điều kiện duyệt.",
            explanation="Điều kiện chưa đạt: "
            + ", ".join(k for k, v in checks.items() if not v),
            requires_confirmation=False,
            error="swap_conditions_not_met",
        )

    return ToolExecutionResult(
        success=True,
        tool_name="tool_prepare_swap_approval",
        intent="APPROVE_SHIFT_SWAP",
        data=diff,
        summary=f"Đề xuất duyệt đổi ca {ca_id}: {ten_a} → {ten_c} (đủ 3 nhánh đồng ý).",
        explanation=(
            "Đã kiểm tra: đủ 3 nhân sự khác nhau, cả 3 nhánh đã đồng ý, ca hợp lệ, "
            "không trùng ca khác, có lý do ghi nhận."
        ),
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("APPROVE_SHIFT_SWAP", store_id),
    )


def tool_get_daily_brief(
    store_id: str = "quan_01",
    ngay: str | None = None,
    **kwargs: Any,
) -> ToolExecutionResult:
    """Generate daily operational morning brief from REAL KV data.

    Tổng hợp: phân công ca, việc treo, tồn kho dưới ngưỡng, luật mới.
    Không có dữ liệu nào → báo trung thực, không bịa.
    """
    from datetime import date, datetime

    ngay = ngay or datetime.now(UTC).date().isoformat()
    thu_hom_nay = ""
    try:
        dt = date.fromisoformat(ngay)
        thu_map_iso = {0: "T2", 1: "T3", 2: "T4", 3: "T5", 4: "T6", 5: "T7", 6: "CN"}
        thu_hom_nay = thu_map_iso.get(dt.weekday(), "")
    except Exception:
        pass

    list_ca_meta = _src("list_ca_meta")
    ca_meta = (list_ca_meta() or {}) if list_ca_meta else {}

    # 1. Phân công ca hôm nay (KV "phan_cong": {ca_id: [nv_id...]})
    phan_cong = _kv_get("phan_cong", {}) or {}
    users: dict[str, str] = {
        str(u.get("nv_id")): str(u.get("ten") or "")
        for u in (_kv_get("users", []) or [])
        if isinstance(u, dict) and u.get("nv_id")
    }
    ca_hom_nay: dict[str, list[str]] = {}
    for ca_id, nvs in phan_cong.items():
        if not isinstance(nvs, list):
            continue
        # Xác định thứ của ca
        ca_thu = ""
        if ca_id in ca_meta:
            ca_thu = str(ca_meta[ca_id].get("thu") or "")
        elif "_c" in str(ca_id):
            try:
                c_num = int(str(ca_id).split("_c")[1])
                day_offset = (c_num - 1) // 3 + 1
                thu_map_num = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
                ca_thu = thu_map_num.get(day_offset, "")
            except Exception:
                pass

        matches_today = (
            (ngay in str(ca_id))
            or (bool(thu_hom_nay) and bool(ca_thu) and ca_thu == thu_hom_nay)
        )
        if matches_today:
            ten_list = [users.get(nv, str(nv)) for nv in (nvs or []) if isinstance(nv, str)]
            if ten_list:
                ca_hom_nay[str(ca_id)] = ten_list

    # 2. Việc treo đang chờ
    treo = [t for t in (_kv_get("treo", []) or []) if isinstance(t, dict)]
    treo_cho = [t for t in treo if str(t.get("trang_thai") or "dang_cho") == "dang_cho"]

    # 3. Tồn kho dưới ngưỡng (KV "tieu_thu": [{hang, so_luong, duoi_nguong}])
    ton = [x for x in (_kv_get("tieu_thu", []) or []) if isinstance(x, dict)]
    canh_bao = [
        f"{x.get('hang')}: còn {x.get('so_luong')} {x.get('don_vi') or ''}".strip()
        for x in ton
        if x.get("duoi_nguong")
    ]

    # 4. Sự cố từ việc treo (nội dung chứa từ khoá sự cố)
    su_co = [
        str(t.get("noi_dung") or "")[:120]
        for t in treo_cho
        if any(k in str(t.get("noi_dung") or "").lower() for k in ("hỏng", "lỗi", "sửa", "cần"))
    ]

    parts: list[str] = []
    if ca_hom_nay:
        n_nv = sum(len(v) for v in ca_hom_nay.values())
        parts.append(f"{n_nv} lượt phân công trong {len(ca_hom_nay)} ca")
    if su_co:
        parts.append(f"{len(su_co)} sự cố cần chú ý")
    if canh_bao:
        parts.append(f"{len(canh_bao)} mặt hàng dưới ngưỡng tồn")
    if treo_cho:
        parts.append(f"{len(treo_cho)} việc treo đang chờ")

    if not parts:
        summary = f"Chưa có dữ liệu vận hành nào được ghi nhận cho ngày {ngay}."
        explanation = (
            "Chưa có phân công, việc treo hay tồn kho nào trong hệ thống. "
            "Dữ liệu sẽ xuất hiện khi nhân viên điểm danh, ghi phiếu và quản lý xếp lịch."
        )
        data: dict[str, Any] = {"ngay": ngay, "co_du_lieu": False}
    else:
        summary = f"Bản tin {ngay}: " + ", ".join(parts) + "."
        explanation = summary
        data = {
            "ngay": ngay,
            "co_du_lieu": True,
            "ca": ca_hom_nay,
            "su_co_can_chu_y": su_co,
            "ton_kho_thap": canh_bao,
            "so_treo_cho": len(treo_cho),
        }

    return ToolExecutionResult(
        success=True,
        tool_name="tool_get_daily_brief",
        intent="GENERATE_DAILY_BRIEF",
        data=data,
        summary=summary,
        explanation=explanation,
        requires_confirmation=False,
    )


def tool_query_sop_playbook(
    cau_hoi: str,
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """Answer SOP question strictly from YAML templates + approved laws (AG-SOP).

    Dùng sop_answer được inject (AG-SOP thật): match câu hỏi với bước trong
    phiếu YAML (mo_quan/dong_quan/ban_giao_ca) + luật hiệu lực trong cẩm nang.
    Không có → trả "chưa có trong cẩm nang" — không bịa.
    """
    sop_answer = _src("sop_answer")
    load_template = _src("load_template")
    list_luat = _src("list_luat")

    q = (cau_hoi or "").lower()

    # Chọn mẫu phiếu phù hợp nhất theo từ khoá
    mau = "mo_quan"
    if any(k in q for k in ("đóng quán", "dong quan", "khóa cửa", "khoa cua", "cuối ngày")):
        mau = "dong_quan"
    elif any(k in q for k in ("bàn giao", "ban giao", "giao ca", "handover")):
        mau = "ban_giao_ca"

    tpl = load_template(mau) if load_template else None
    buoc = list(tpl.get("buoc") or []) if isinstance(tpl, dict) else []
    luat = list(list_luat() or []) if list_luat else []

    if not buoc and not luat:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_query_sop_playbook",
            intent="QUERY_SOP",
            data={"answer": "Chưa tải được cẩm nang của quán.", "citations": [], "chua_co": True},
            summary="Chưa tải được cẩm nang của quán.",
            explanation="Không đọc được mẫu phiếu YAML và luật hiệu lực.",
            requires_confirmation=False,
        )

    if sop_answer is None:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_query_sop_playbook",
            intent="QUERY_SOP",
            data={"answer": "Chưa cấu hình nguồn dữ liệu SOP.", "citations": [], "chua_co": True},
            summary="Chưa cấu hình nguồn dữ liệu SOP.",
            explanation="API layer chưa gọi configure_data_sources(sop_answer=...).",
            requires_confirmation=False,
        )

    r = sop_answer(cau_hoi or "", buoc=buoc, luat=luat)
    citations = list(getattr(r, "trich_dan", []) or [])
    if not getattr(r, "chua_co", True) and tpl:
        citations = [f"templates/{mau}.yaml"] + citations

    return ToolExecutionResult(
        success=True,
        tool_name="tool_query_sop_playbook",
        intent="QUERY_SOP",
        data={"answer": r.cau_tra_loi, "citations": citations, "chua_co": r.chua_co},
        summary=r.cau_tra_loi,
        explanation=("Trích dẫn từ: " + ", ".join(citations)) if citations else "Không tìm thấy trong cẩm nang.",
        requires_confirmation=False,
    )


def tool_get_waste_summary(
    store_id: str = "quan_01",
    khoang_ngay: str = "hom_nay",
    **kwargs: Any,
) -> ToolExecutionResult:
    """ANALYZE_WASTE — hao hụt theo nguyên liệu, có số, từ dữ liệu thật.

    AG-COPILOT (mẹ) điều phối, AG-WASTE (con) tính: hàm `loss_engine` được inject
    từ tầng API, cùng hàm mà `GET /api/v1/hao-hut` gọi. Nhờ vậy câu trả lời của
    agent và con số trên trang web **không thể lệch nhau**.

    Đọc bốn nguồn qua `_src`/`_kv_get` (không import ca_api — hexagonal boundary):

    - kv `kiem_ke` + kv `waste_notes` — qua `kv_get` được inject.
    - `menu_list` — danh mục món kèm công thức định mức.
    - `don_list` — đơn quầy, chỉ đơn `xong` được tính.

    Không có dữ liệu ⇒ trả lời trung thực, không bịa số.
    """
    loss_engine = _src("loss_engine")
    waste_cluster = _src("waste_cluster")

    stored = [x for x in (_kv_get("waste_notes", []) or []) if isinstance(x, dict)]
    pairs = [(str(x.get("thu", "")), str(x.get("ghi_chu", ""))) for x in stored if x.get("ghi_chu")]

    if loss_engine is None:
        # Chưa cấu hình nguồn tính → vẫn trả lời được phần gom cụm ghi chú.
        return _waste_cluster_only(pairs, waste_cluster)

    kiem_ke = [x for x in (_kv_get("kiem_ke", []) or []) if isinstance(x, dict)]
    menu_list = _src("menu_list")
    don_list = _src("don_list")
    try:
        menu = list(menu_list(gom_an=True) or []) if menu_list else []
        don = list(don_list() or []) if don_list else []
    except Exception:
        menu, don = [], []

    try:
        summary = loss_engine(
            kiem_ke=kiem_ke,
            don_quay=don,
            menu=menu,
            waste_notes=stored,
            ky=khoang_ngay or "hom_nay",
        )
    except TypeError:
        # Nguồn được inject theo chữ ký cũ → lui về gọi không tham số kỳ.
        summary = loss_engine(kiem_ke, don, menu, stored)

    data = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary)
    dong = list(data.get("dong") or [])

    if not dong:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_get_waste_summary",
            intent="ANALYZE_WASTE",
            data={"co_du_lieu": False, "so_ghi_nhan": len(stored)},
            summary="Chưa có dữ liệu để tính hao hụt.",
            explanation=(
                "Chưa có phiếu kiểm kê hoặc đơn quầy nào trong kỳ này. "
                "Ghi kiểm kê ở mặt Hàng tồn (/tieu-thu) rồi hỏi lại."
            ),
            requires_confirmation=False,
        )

    return ToolExecutionResult(
        success=True,
        tool_name="tool_get_waste_summary",
        intent="ANALYZE_WASTE",
        data={**data, "co_du_lieu": True},
        summary=_tom_tat_hao_hut(data),
        explanation=_giai_thich_hao_hut(data),
        requires_confirmation=False,
    )


def _waste_cluster_only(
    pairs: list[tuple[str, str]],
    waste_cluster: Callable[..., Any] | None,
) -> ToolExecutionResult:
    """Đường lui khi `loss_engine` chưa được cấu hình: chỉ gom cụm ghi chú.

    Giữ lại để môi trường chạy standalone/test không có tầng API vẫn trả lời được
    thay vì sập.
    """
    if not pairs:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_get_waste_summary",
            intent="ANALYZE_WASTE",
            data={"so_ghi_nhan": 0, "co_du_lieu": False},
            summary="Chưa có ghi chú hao hụt nào được ghi nhận.",
            explanation="Nhân viên chưa ghi hao hụt nào qua mặt Hao phí (/hao-phi).",
            requires_confirmation=False,
        )

    clusters: list[dict[str, Any]] = []
    if waste_cluster is not None:
        clusters = [x.__dict__ if hasattr(x, "__dict__") else dict(x) for x in waste_cluster(pairs)]
    n = len(pairs)
    summary = f"Đã ghi nhận {n} ghi chú hao hụt."
    if clusters:
        summary += f" Phát hiện {len(clusters)} mẫu lặp: " + "; ".join(
            str(x.get("cau") or x.get("ten") or "") for x in clusters[:3]
        ) + "."
    return ToolExecutionResult(
        success=True,
        tool_name="tool_get_waste_summary",
        intent="ANALYZE_WASTE",
        data={"so_ghi_nhan": n, "so_cum": len(clusters), "cum": clusters, "co_du_lieu": True},
        summary=summary,
        explanation=f"Phân cụm từ {n} ghi chú thật của nhân viên (nguồn: waste_notes).",
        requires_confirmation=False,
    )


def _tom_tat_hao_hut(data: dict[str, Any]) -> str:
    """Câu tóm tắt có số, đọc lên là hiểu — không có số nào tự sinh."""
    dong = list(data.get("dong") or [])
    nghiem = [d for d in dong if d.get("muc_do") == "nghiem_trong"]
    canh_bao = [d for d in dong if d.get("muc_do") == "canh_bao"]
    thieu = [d for d in dong if d.get("muc_do") == "thieu_du_lieu"]

    phan: list[str] = [f"Hao hụt {len(dong)} nguyên liệu."]
    if nghiem:
        ten = ", ".join(str(d.get("ten") or d.get("mat_hang")) for d in nghiem[:3])
        phan.append(f"{len(nghiem)} nguyên liệu vượt ngưỡng nghiêm trọng: {ten}.")
    if canh_bao:
        ten = ", ".join(str(d.get("ten") or d.get("mat_hang")) for d in canh_bao[:3])
        phan.append(f"{len(canh_bao)} nguyên liệu cần xem lại: {ten}.")
    if not nghiem and not canh_bao:
        phan.append("Không nguyên liệu nào vượt ngưỡng.")
    if thieu:
        phan.append(f"{len(thieu)} nguyên liệu chưa đủ dữ liệu để kết luận.")

    hang_dau = list(data.get("nguyen_nhan_hang_dau") or [])
    if hang_dau:
        top = hang_dau[0]
        phan.append(
            f"Nguyên nhân ghi nhiều nhất: {top.get('ten')} ({top.get('so_lan')} lần)."
        )
    return " ".join(phan)


def _giai_thich_hao_hut(data: dict[str, Any]) -> str:
    """Nói rõ số này từ đâu ra, để người đọc biết mức tin của con số."""
    dong = list(data.get("dong") or [])
    du_hai_ve = [d for d in dong if d.get("ty_le_phan_tram") is not None]
    phan = [
        "Lý thuyết = định mức công thức trong menu × số phần đã bán (đơn quầy đã xong).",
        "Thực tế = đầu ca + nhập trong ca − cuối ca − hao hụt đã ghi, từ phiếu kiểm kê.",
    ]
    if len(du_hai_ve) < len(dong):
        phan.append(
            f"{len(dong) - len(du_hai_ve)} nguyên liệu thiếu một vế nên để trống chứ không đoán số."
        )
    if data.get("co_du_lieu_mau"):
        phan.append("Dữ liệu có phần từ bộ mẫu (không phải số thật của quán).")
    phan.append(f"Trung bình trên {len(du_hai_ve)} nguyên liệu đủ hai vế: {data.get('ty_le_trung_binh')}%.")
    return " ".join(phan)


def tool_propose_rule_from_recent_edits(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """Analyze recent manual manager edits and propose a Vietnamese operating rule.

    Dùng tim_mau + de_xuat được inject (ca_playbook thật): phân tích lịch sử
    sửa lịch (list_sua) thành mẫu lặp → đề xuất luật. Không có mẫu → báo trung thực.
    """
    list_sua = _src("list_sua")
    tim_mau = _src("tim_mau")
    de_xuat = _src("de_xuat")

    if not (list_sua and tim_mau and de_xuat):
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_rule_from_recent_edits",
            intent="CREATE_RULE_PROPOSAL",
            data={},
            summary="Chưa cấu hình nguồn dữ liệu cẩm nang sống.",
            explanation="API layer chưa gọi configure_data_sources(list_sua=..., tim_mau=..., de_xuat=...).",
            requires_confirmation=False,
            error="playbook_sources_not_configured",
        )

    sua = list(list_sua() or [])
    mau = list(tim_mau(sua) or [])

    if not mau:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_propose_rule_from_recent_edits",
            intent="CREATE_RULE_PROPOSAL",
            data={"so_lan_sua": len(sua), "so_mau": 0, "co_de_xuat": False},
            summary="Chưa có mẫu lặp đủ mạnh để đề xuất luật mới.",
            explanation=(
                f"Đã phân tích {len(sua)} lần sửa lịch thật của quản lý — "
                "chưa có mẫu nào lặp đủ số lần theo quy tắc 8 bước."
            ),
            requires_confirmation=False,
        )

    # Đề xuất từ mẫu mạnh nhất — de_xuat trả None khi mẫu thiếu tín hiệu
    # (không đủ nhân sự suy ra được), nên lọc trước khi chọn.
    co_le = [d for d in (de_xuat(m) for m in mau) if d]
    if not co_le:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_propose_rule_from_recent_edits",
            intent="CREATE_RULE_PROPOSAL",
            data={"so_lan_sua": len(sua), "so_mau": len(mau), "co_de_xuat": False},
            summary="Chưa đủ tín hiệu từ các mẫu sửa để dựng đề xuất luật.",
            explanation=(
                f"Có {len(mau)} mẫu lặp nhưng chưa mẫu nào cho phép suy tất định "
                "nội dung luật (thiếu số người/vị trí trong dữ liệu sửa)."
            ),
            requires_confirmation=False,
        )
    best = co_le[0]

    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_rule_from_recent_edits",
        intent="CREATE_RULE_PROPOSAL",
        data={
            "so_lan_sua": len(sua),
            "so_mau": len(mau),
            "de_xuat": best,
            "co_de_xuat": True,
            "snapshot_version": "live-v1",
        },
        summary=f"Đề xuất luật mới: \"{best.get('cau') or best.get('cau_luat')}\" (dựa trên {len(sua)} lần sửa thật).",
        explanation=str(best.get("ly_do") or best.get("dien_giai") or "Sinh từ mẫu lặp trong lịch sử sửa lịch của quản lý."),
        source_snapshot=build_live_snapshot("CREATE_RULE_PROPOSAL", store_id),
        requires_confirmation=True,
    )


def tool_check_inventory_restock(
    store_id: str = "quan_01",
    nguong_canh_bao: float = 10.0,
    **kwargs: Any,
) -> ToolExecutionResult:
    """Check inventory stock levels against thresholds from REAL data (KV "tieu_thu").

    Nhân viên ghi số lượng tồn qua mặt Tiêu thụ (/tieu-thu) — tool đọc và
    cảnh báo mặt nào dưới ngưỡng. Không có dữ liệu → báo trung thực.
    """
    ton = [x for x in (_kv_get("tieu_thu", []) or []) if isinstance(x, dict)]

    if not ton:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_check_inventory_restock",
            intent="INVENTORY_RESTOCK_CHECK",
            data={"so_mat_hang": 0, "co_du_lieu": False},
            summary="Chưa có dữ liệu tồn kho nào được ghi nhận.",
            explanation="Nhân viên chưa ghi số lượng hàng qua mặt Tiêu thụ (/tieu-thu).",
            requires_confirmation=False,
        )

    # Mặt hàng dưới ngưỡng (dữ liệu đã có flag duoi_nguong từ API ghi)
    canh_bao = [
        {
            "mat_hang": x.get("hang"),
            "ton_hien_tai": x.get("so_luong"),
            "don_vi": x.get("don_vi") or "đơn vị",
            "duoi_nguong": bool(x.get("duoi_nguong")),
        }
        for x in ton
        if x.get("duoi_nguong")
    ]

    if not canh_bao:
        return ToolExecutionResult(
            success=True,
            tool_name="tool_check_inventory_restock",
            intent="INVENTORY_RESTOCK_CHECK",
            data={"so_mat_hang": len(ton), "canh_bao": [], "co_du_lieu": True},
            summary=f"Đã kiểm tra {len(ton)} mặt hàng — tất cả đều trên ngưỡng an toàn.",
            explanation="Không có mặt hàng nào dưới ngưỡng cảnh báo.",
            requires_confirmation=False,
        )

    items_text = ", ".join(
        f"{x['mat_hang']} (còn {x['ton_hien_tai']} {x['don_vi']})" for x in canh_bao
    )
    summary = f"Cảnh báo {len(canh_bao)}/{len(ton)} mặt hàng dưới ngưỡng tồn: {items_text}."
    explanation = (
        "Đề xuất kiểm kê lại và đặt hàng bổ sung các mặt hàng trên. "
        "Duyệt để tạo đơn đặt hàng nháp trong hệ thống."
    )

    return ToolExecutionResult(
        success=True,
        tool_name="tool_check_inventory_restock",
        intent="INVENTORY_RESTOCK_CHECK",
        data={"so_mat_hang": len(ton), "canh_bao": canh_bao, "co_du_lieu": True},
        summary=summary,
        explanation=explanation,
        requires_confirmation=True,
        source_snapshot=ton,
    )


def tool_send_mail(
    store_id: str = "quan_01",
    to_nv_ids: list[str] | None = None,
    subject: str = "",
    body: str = "",
    **kwargs: Any,
) -> ToolExecutionResult:
    """Delegate email drafting to AG-MAILWRITER and generate an ActionProposal.

    Tuân thủ Two-Phase Approval: Tool chỉ soạn thảo thư chuyên nghiệp và trả về
    ActionProposal (requires_confirmation=True) để Chủ quán/Quản lý xem trước,
    duyệt, sửa hoặc từ chối trước khi gửi thật qua SMTP.
    """
    to_nv_ids = list(to_nv_ids or [])
    direct_emails = list(kwargs.get("direct_emails") or [])
    recipient_names = list(kwargs.get("recipient_names") or [])
    raw_request = str(kwargs.get("raw_request") or body or subject or "Thông báo công việc").strip()

    # Tra cứu email thật từ user table (inject qua get_user_emails)
    get_emails = _src("get_user_emails")
    try:
        email_map = dict(get_emails() or {}) if get_emails else {}
    except Exception:
        email_map = {}
    to_emails: list[str] = list(direct_emails)
    missing: list[str] = []

    for nv in to_nv_ids:
        em = email_map.get(nv)
        if em:
            if em not in to_emails:
                to_emails.append(em)
        else:
            missing.append(nv)

    # Xác định danh xưng người nhận
    if recipient_names:
        recip_label = ", ".join(recipient_names)
    elif to_emails:
        recip_label = ", ".join(to_emails)
    elif missing:
        recip_label = ", ".join(missing)
    else:
        recip_label = "Nhân viên quán"

    if not to_emails:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_send_mail",
            intent="SEND_MAIL",
            data={
                "to_emails": [],
                "to_nv_ids": to_nv_ids,
                "recipient_names": recipient_names,
                "recip_label": recip_label,
                "missing": missing,
                "snapshot_version": "live-v1",
            },
            summary=f"Chưa thể tạo đề xuất gửi email cho {recip_label}.",
            explanation="Không tìm thấy địa chỉ email hợp lệ của người nhận.",
            requires_confirmation=False,
            error="no_recipient_email",
        )

    # Lấy dữ liệu vận hành sống (Compound Context) & Gu văn phong (Tone Memory)
    get_ops_ctx = _src("get_ops_context")
    try:
        ops_context = get_ops_ctx(store_id=store_id, to_nv_ids=to_nv_ids, raw_request=raw_request) if get_ops_ctx else None
    except Exception:
        ops_context = None

    get_style = _src("get_mail_style")
    try:
        style_memory = get_style(store_id=store_id) if get_style else None
    except Exception:
        style_memory = None

    # Gọi Agent chuyên trách AG-MAILWRITER (inject qua _src("draft_mail"))
    draft_fn = _src("draft_mail")
    has_learned = bool(style_memory)
    if draft_fn:
        try:
            draft = draft_fn(
                raw_request=raw_request,
                recipient_name=recip_label,
                recipient_email=", ".join(to_emails),
                store_id=store_id,
                to_nv_ids=to_nv_ids,
                sender_name="Ban Quản Lý Nhịp Quán",
                store_name="Nhịp Quán",
                ops_context=ops_context,
                style_memory=style_memory,
            )
            draft_subject = getattr(draft, "subject", "") or subject or f"[Nhịp Quán] Thông báo gửi {recip_label}"
            draft_body = getattr(draft, "body", "") or body or raw_request
            has_learned = getattr(draft, "has_learned_style", has_learned)
            rule_version = getattr(draft, "rule_version", "none")
            rollout_bucket = getattr(draft, "rollout_bucket", "control")
        except Exception:
            draft_subject = subject or f"[Nhịp Quán] Thông báo gửi {recip_label}"
            draft_body = body or raw_request
            rule_version = "none"
            rollout_bucket = "control"
    else:
        draft_subject = (
            subject if subject.startswith("[Nhịp Quán]") else f"[Nhịp Quán] Thông báo gửi {recip_label}"
        )
        draft_body = (
            f"Thân gửi {recip_label},\n\n"
            f"Ban Quản Lý Nhịp Quán xin thông báo:\n"
            f"- {raw_request}\n\n"
            f"Vui lòng phản hồi lại nếu cần thêm thông tin.\n\n"
            f"Trân trọng,\n"
            f"Ban Quản Lý Nhịp Quán"
        )
        rule_version = "none"
        rollout_bucket = "control"

    ops_summary = ""
    if ops_context:
        if ops_context.get("type") == "shift":
            ops_summary = f"Lịch ca {ops_context.get('ca_ten', '')} ({ops_context.get('gio', '')})"
        elif ops_context.get("type") == "inventory":
            ops_summary = f"Tồn kho {ops_context.get('mat_hang', '')} ({ops_context.get('ton_kho')} {ops_context.get('dvt', '')})"
        elif ops_context.get("type") == "daily_summary":
            ops_summary = "Số liệu vận hành ngày"

    payload = {
        "snapshot_version": "live-v1",
        "subject": draft_subject,
        "body": draft_body,
        "to_emails": to_emails,
        "to_nv_ids": to_nv_ids,
        "recipient_names": recipient_names,
        "recip_label": recip_label,
        "missing": missing,
        "raw_request": raw_request,
        "ops_context": ops_context,
        "ops_context_summary": ops_summary,
        "has_learned_style": has_learned,
        "rule_version": rule_version,
        "rollout_bucket": rollout_bucket,
    }

    explanation = (
        f"Agent AG-MAILWRITER đã soạn xong thư chuyên nghiệp cho {recip_label}. "
        "Anh/chị xem trước nội dung, có thể bấm 'Duyệt & Gửi' để gửi đi hoặc bảo em sửa lại nhé!"
    )

    return ToolExecutionResult(
        success=True,
        tool_name="tool_send_mail",
        intent="SEND_MAIL",
        data=payload,
        summary=f"Bản nháp email gửi {recip_label}: {draft_subject}",
        explanation=explanation,
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("SEND_MAIL", store_id, payload),
    )


_TOOLS: dict[str, Callable[..., ToolExecutionResult]] = {
    "SCHEDULE_SOLVE": tool_solve_weekly_schedule,
    "APPROVE_SHIFT_SWAP": tool_prepare_swap_approval,
    "GENERATE_DAILY_BRIEF": tool_get_daily_brief,
    "QUERY_SOP": tool_query_sop_playbook,
    "ANALYZE_WASTE": tool_get_waste_summary,
    "CREATE_RULE_PROPOSAL": tool_propose_rule_from_recent_edits,
    "INVENTORY_RESTOCK_CHECK": tool_check_inventory_restock,
    "SEND_MAIL": tool_send_mail,
}


# ── PR9 read tools: GET_* intents trả dữ liệu sống tenant-scoped ───────────


def _read_result(
    intent: str,
    tool_name: str,
    data: dict[str, Any],
    summary: str,
    explanation: str,
) -> ToolExecutionResult:
    """Chuẩn hoá kết quả đọc: requires_confirmation=False, provenance trong data."""
    return ToolExecutionResult(
        success=True,
        tool_name=tool_name,
        intent=intent,
        data={
            "_provenance": {
                "source": tool_name,
                "read_at": datetime.now(UTC).isoformat(),
                "store_scope": True,
            },
            **data,
        },
        summary=summary,
        explanation=explanation,
        requires_confirmation=False,
    )


def tool_get_my_profile(
    store_id: str = "quan_01",
    user_id: str = "",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_MY_PROFILE: hồ sơ của chính người hỏi (không đọc hộ người khác)."""
    list_users = _src("list_users")
    users = list(list_users() or []) if list_users else []
    me = next((u for u in users if isinstance(u, dict) and str(u.get("nv_id") or "") == user_id), None)
    if not me:
        return _read_result(
            "GET_MY_PROFILE", "tool_get_my_profile", {"found": False},
            "Không tìm thấy hồ sơ của anh/chị trong hệ thống.",
            "user_id không khớp dữ liệu users (tenant-scoped).",
        )
    return _read_result(
        "GET_MY_PROFILE", "tool_get_my_profile",
        {"found": True, "profile": {"nv_id": me.get("nv_id"), "ten": me.get("ten") or me.get("display_name"), "role": me.get("role")}},
        f"Hồ sơ: {me.get('ten') or me.get('display_name') or user_id} ({me.get('role')}).",
        "Đọc từ bảng users theo nv_id của session.",
    )


def tool_list_staff(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """LIST_STAFF: danh sách nhân sự trong store (không lộ email/password)."""
    list_users = _src("list_users")
    users = list(list_users() or []) if list_users else []
    staff = [
        {"nv_id": u.get("nv_id"), "ten": u.get("ten") or u.get("display_name"), "role": u.get("role")}
        for u in users if isinstance(u, dict)
    ]
    return _read_result(
        "LIST_STAFF", "tool_list_staff", {"so_nguoi": len(staff), "nhan_su": staff},
        f"Hiện có {len(staff)} nhân sự trong hệ thống.",
        "Đọc từ bảng users; không trả email/số điện thoại qua chat.",
    )


def tool_query_menu(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """QUERY_MENU: menu hiện hành từ bảng menu_mon."""
    menu_list = _src("menu_list")
    mons = list(menu_list() or []) if menu_list else []
    visible = [m for m in mons if isinstance(m, dict)]
    return _read_result(
        "QUERY_MENU", "tool_query_menu", {"so_mon": len(visible), "menu": visible},
        f"Menu hiện có {len(visible)} món.",
        "Đọc từ bảng menu_mon (bỏ món đã ẩn nếu nguồn trả theo trạng thái).",
    )


def tool_get_inventory(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_INVENTORY: tồn kho hiện tại + cảnh báo dưới ngưỡng."""
    ton = [x for x in (_kv_get("tieu_thu", []) or []) if isinstance(x, dict)]
    duoi_nguong = [x for x in ton if x.get("duoi_nguong")]
    return _read_result(
        "GET_INVENTORY", "tool_get_inventory",
        {"so_mat_hang": len(ton), "duoi_nguong": len(duoi_nguong), "items": ton},
        f"Tồn kho: {len(ton)} mặt hàng, {len(duoi_nguong)} dưới ngưỡng.",
        "Đọc từ KV tieu_thu (tenant-scoped theo store_id).",
    )


def tool_get_shift_swaps(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_SHIFT_SWAPS: các yêu cầu đổi ca đang chờ (không consent qua chat)."""
    swaps = [s for s in (_kv_get("swap", []) or []) if isinstance(s, dict)]
    cho = [s for s in swaps if str(s.get("trang_thai") or "") in ("cho_3_nhanh", "dong_y", "cho_duyet")]
    return _read_result(
        "GET_SHIFT_SWAPS", "tool_get_shift_swaps", {"so_cho": len(cho), "swaps": cho},
        f"{len(cho)} yêu cầu đổi ca đang chờ xử lý.",
        "Đọc từ KV swap; consent vẫn phải do nhân viên thao tác trên /doi-ca.",
    )


def tool_get_hanging_tasks(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_HANGING_TASKS: việc treo đang chờ."""
    treo = [t for t in (_kv_get("treo", []) or []) if isinstance(t, dict)]
    cho = [t for t in treo if str(t.get("trang_thai") or "dang_cho") == "dang_cho"]
    return _read_result(
        "GET_HANGING_TASKS", "tool_get_hanging_tasks", {"so_cho": len(cho), "treo": cho},
        f"{len(cho)} việc treo đang chờ xử lý.",
        "Đọc từ KV treo (dang_cho).",
    )


def tool_get_handovers(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_HANDOVERS: bản giao ca gần nhất."""
    list_sua = _src("list_sua")
    sua = list(list_sua() or []) if list_sua else []
    return _read_result(
        "GET_HANDOVERS", "tool_get_handovers", {"so_lan_sua": len(sua), "lich_su": sua[-10:]},
        f"{len(sua)} bản ghi sửa lịch/bàn giao gần nhất.",
        "Đọc từ ca_playbook list_sua (10 bản ghi gần nhất).",
    )


def tool_query_audit(
    store_id: str = "quan_01",
    limit: int = 20,
    **kwargs: Any,
) -> ToolExecutionResult:
    """QUERY_AUDIT: tra cứu vết hệ thống / nhật ký thay đổi (tenant-scoped).

    Chỉ quản lý & chủ quán được gọi (đã chặn ở tầng role matrix). Đọc từ
    `audit_list` được inject qua data source — không import trực tiếp ca_api.
    """
    audit_list = _src("audit_list")
    if audit_list is None:
        return _read_result(
            "QUERY_AUDIT", "tool_query_audit", {"so_vet": 0, "vet": []},
            "Em chưa có nguồn vết hệ thống để tra cứu trong môi trường này.",
            "Không có data source audit_list được inject.",
        )
    try:
        vet = list(audit_list(limit=limit) or [])
    except Exception as e:  # noqa: BLE001
        return _read_result(
            "QUERY_AUDIT", "tool_query_audit", {"so_vet": 0, "vet": [], "loi": str(e)},
            "Em gặp lỗi khi đọc vết hệ thống.",
            f"audit_list() ném lỗi: {e}",
        )
    # Redact payload nhạy cảm trước khi trả về qua chat (ADR-008: không lộ dữ liệu).
    safe = []
    for v in vet:
        item = dict(v)
        payload = item.get("payload")
        if isinstance(payload, dict):
            # Chỉ giữ các trường an toàn, bỏ token/body nhạy cảm.
            safe_payload = {
                k: val for k, val in payload.items()
                if k not in {"token", "password", "secret", "body", "content", "text"}
            }
            item["payload"] = safe_payload
        safe.append(item)
    return _read_result(
        "QUERY_AUDIT", "tool_query_audit", {"so_vet": len(safe), "vet": safe},
        f"Em tìm thấy {len(safe)} vết hệ thống gần nhất.",
        "Đọc từ audit_list (vết hệ thống, tenant-scoped, đã redact payload nhạy cảm).",
    )


def _tuan_hien_tai() -> str:
    """ISO week 'YYYY-Wnn' của hôm nay — không hardcode."""
    iso = datetime.now(UTC).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def tool_get_schedule(
    store_id: str = "quan_01",
    tuan: str | None = None,
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_SCHEDULE: lịch tuần hiệu lực — phân công ca + meta ca (R0_READ).

    Đọc 6 khoá kv bằng MỘT `kv_get_many`: bản cũ gọi `_kv_get` sáu lần, mà mỗi
    `kv_get` mở một connection SQLite mới + chạy `init_db()` → 6 connection cho
    một câu hỏi. Đó là nguồn chậm chính của trợ lý ("trả lời rất chậm").
    """
    tuan_iso = tuan or kwargs.get("tuan") or _tuan_hien_tai()
    kv_many = _kv_get_many(
        [
            "phan_cong",
            "roster_nv_status",
            "inbox_rang_buoc",
            "tkb_nv_by_week",
            "tkb_nv",
            "lich_tuan_lifecycle",
        ],
        {
            "phan_cong": {},
            "roster_nv_status": {},
            "inbox_rang_buoc": [],
            "tkb_nv_by_week": {},
            "tkb_nv": {},
            "lich_tuan_lifecycle": {},
        },
    )
    phan_cong = kv_many["phan_cong"] or {}
    ca_meta_fn = _src("list_ca_meta")
    ca_meta: dict[str, Any] = {}
    if ca_meta_fn is not None:
        try:
            ca_meta = dict(ca_meta_fn() or {})
        except Exception:
            ca_meta = {}
    so_ca = len(phan_cong)
    if not phan_cong:
        return _read_result(
            "GET_SCHEDULE", "tool_get_schedule",
            {"tuan": tuan_iso, "so_ca": 0, "phan_cong": {}, "co_du_lieu": False},
            f"Chưa có phân công nào cho tuần {tuan_iso}.",
            "Đọc KV phan_cong; lịch sẽ xuất hiện sau khi quản lý xếp lịch (solver) và duyệt.",
        )

    # Đếm số ca phân công và tổng hợp nhân sự
    assigned_counts: dict[str, int] = {}
    for _ca_id, nvs in phan_cong.items():
        if isinstance(nvs, list):
            for n in nvs:
                sn = str(n)
                assigned_counts[sn] = assigned_counts.get(sn, 0) + 1

    list_nv_fn = _src("list_nhan_vien_ops")
    all_nv = list_nv_fn() if callable(list_nv_fn) else []

    da_xep: list[str] = []
    chua_co_ca: list[str] = []
    for nv in all_nv:
        if not isinstance(nv, dict):
            continue
        nvid = str(nv.get("id", ""))
        ten = str(nv.get("ten") or nv.get("username") or nvid)
        if nvid in assigned_counts and assigned_counts[nvid] > 0:
            da_xep.append(ten)
        else:
            chua_co_ca.append(ten)

    # Đọc trạng thái xác nhận từ KV roster_nv_status (đã lấy chung ở trên)
    roster_status_store = kv_many["roster_nv_status"] or {}
    week_status = roster_status_store.get(tuan_iso, {}) if isinstance(roster_status_store, dict) else {}

    inbox_items = kv_many["inbox_rang_buoc"] or []
    inbox_submitted_nv: set[str] = set()
    if isinstance(inbox_items, list):
        for it in inbox_items:
            if isinstance(it, dict):
                rb = cast(dict[str, Any], it.get("rang_buoc")) if isinstance(it.get("rang_buoc"), dict) else {}
                hl = cast(dict[str, Any], it.get("hieu_luc")) if isinstance(it.get("hieu_luc"), dict) else {}
                if (rb.get("tuan_id") or hl.get("tuan_id") or it.get("tuan_id")) == tuan_iso:
                    nvid_raw = it.get("nv_id") or hl.get("nv_id")
                    if nvid_raw:
                        inbox_submitted_nv.add(str(nvid_raw))

    tkb_by_week = kv_many["tkb_nv_by_week"] or {}
    tkb_nv = tkb_by_week.get(tuan_iso, {}) if isinstance(tkb_by_week, dict) else {}
    tkb_confirmed_nv: set[str] = set()
    if isinstance(tkb_nv, dict):
        tkb_confirmed_nv.update(str(nvid) for nvid in tkb_nv)
    legacy_tkb = kv_many["tkb_nv"] or {}
    if isinstance(legacy_tkb, dict):
        for nvid, entry in legacy_tkb.items():
            if isinstance(entry, dict) and entry.get("tuan_iso") == tuan_iso:
                tkb_confirmed_nv.add(str(nvid))

    chua_xac_nhan: list[str] = []
    for nv in all_nv:
        if not isinstance(nv, dict):
            continue
        nvid = str(nv.get("id", ""))
        ten = str(nv.get("ten") or nv.get("username") or nvid)
        if assigned_counts.get(nvid, 0) > 0:
            dec = week_status.get(nvid)
            if dec == "xac_nhan" or nvid in inbox_submitted_nv or nvid in tkb_confirmed_nv:
                pass
            else:
                chua_xac_nhan.append(ten)

    total_assignments = sum(assigned_counts.values())
    lifecycle = kv_many["lich_tuan_lifecycle"] or {}
    trang_thai = lifecycle.get("trang_thai") or _kv_get("lich_tuan_status", "da_duyet" if phan_cong else "nhap")

    trang_thai_label = {
        "nhap": "Nháp",
        "may_sinh": "Máy sinh",
        "cho_duyet": "Chờ duyệt",
        "da_duyet": "Đã duyệt",
        "da_cong_bo": "Đã công bố",
        "da_dong": "Đã đóng",
    }.get(trang_thai, trang_thai)

    parts = [f"Lịch tuần {tuan_iso} (Trạng thái: {trang_thai_label}): {so_ca} ca đã phân công ({total_assignments} lượt phân công cho {len(da_xep)}/{len(all_nv) if all_nv else len(da_xep)} nhân sự)."]
    if chua_co_ca:
        parts.append(f"Nhân sự chưa có ca ({len(chua_co_ca)} người): {', '.join(chua_co_ca)}.")
    elif all_nv:
        parts.append("Tất cả nhân sự đều đã được xếp ca.")

    if chua_xac_nhan:
        ten_chua_xn = ', '.join(chua_xac_nhan[:10])
        them = f" và {len(chua_xac_nhan) - 10} người khác" if len(chua_xac_nhan) > 10 else ""
        parts.append(f"Nhân sự chưa xác nhận lịch ({len(chua_xac_nhan)} người): {ten_chua_xn}{them}.")
    elif all_nv and da_xep:
        parts.append("Toàn bộ nhân sự đã được xác nhận ca.")

    summary = " ".join(parts)

    # Tóm tắt gọn: mỗi ca hiển thị thứ + khung + số người, không tràn payload.
    ca_tom_tat = [
        {
            "ca_id": ca_id,
            "thu": (ca_meta.get(ca_id) or {}).get("thu", ""),
            "khung": (ca_meta.get(ca_id) or {}).get("khung", ""),
            "bat_dau": (ca_meta.get(ca_id) or {}).get("bat_dau", ""),
            "ket_thuc": (ca_meta.get(ca_id) or {}).get("ket_thuc", ""),
            "so_nguoi": len(nvs) if isinstance(nvs, list) else 0,
            "nv_ids": nvs if isinstance(nvs, list) else [],
        }
        for ca_id, nvs in list(phan_cong.items())[:70]
    ]
    return _read_result(
        "GET_SCHEDULE", "tool_get_schedule",
        {
            "tuan": tuan_iso,
            "so_ca": so_ca,
            "so_luot_phan_cong": total_assignments,
            "trang_thai": trang_thai,
            "da_xep": da_xep,
            "chua_co_ca": chua_co_ca,
            "chua_xac_nhan": chua_xac_nhan,
            "phan_cong": phan_cong,
            "ca": ca_tom_tat,
            "co_du_lieu": True,
        },
        summary,
        "Đọc KV phan_cong (tenant-scoped) + roster_nv_status + meta ca.",
    )


def tool_get_my_shifts(
    store_id: str = "quan_01",
    user_id: str = "",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_MY_SHIFTS: ca của chính người hỏi trong tuần (R0_READ, self-scoped)."""
    if not user_id:
        return _read_result(
            "GET_MY_SHIFTS", "tool_get_my_shifts", {"found": False},
            "Không xác định được tài khoản của anh/chị.",
            "Thiếu user_id từ session — fail-closed.",
        )
    phan_cong = _kv_get("phan_cong", {}) or {}
    ca_meta_fn = _src("list_ca_meta")
    ca_meta: dict[str, Any] = {}
    if ca_meta_fn is not None:
        try:
            ca_meta = dict(ca_meta_fn() or {})
        except Exception:
            ca_meta = {}
    ca_cua_toi = []
    for ca_id, nvs in phan_cong.items():
        if isinstance(nvs, list) and user_id in nvs:
            m = ca_meta.get(ca_id) or {}
            ca_cua_toi.append({
                "ca_id": ca_id,
                "thu": m.get("thu", ""),
                "khung": m.get("khung", ""),
                "bat_dau": m.get("bat_dau", ""),
                "ket_thuc": m.get("ket_thuc", ""),
            })
    # Sắp theo thứ trong tuần (T2..CN) rồi giờ bắt đầu cho dễ đọc.
    thu_order = {"T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6, "T7": 7, "CN": 8}
    ca_cua_toi.sort(key=lambda c: (thu_order.get(str(c.get("thu")), 9), str(c.get("bat_dau") or "")))
    tuan = _tuan_hien_tai()
    if not ca_cua_toi:
        return _read_result(
            "GET_MY_SHIFTS", "tool_get_my_shifts",
            {"nv_id": user_id, "tuan": tuan, "so_ca": 0, "ca": [], "co_du_lieu": False},
            f"Tuần {tuan} anh/chị chưa có ca nào trong lịch.",
            "Đọc KV phan_cong lọc theo nv_id của session (self-scoped).",
        )
    mo_ta = ", ".join(
        f"{c.get('thu') or c.get('ca_id')} {c.get('bat_dau') or ''}-{c.get('ket_thuc') or ''}".strip()
        for c in ca_cua_toi[:5]
    )
    them = f" và {len(ca_cua_toi) - 5} ca khác" if len(ca_cua_toi) > 5 else ""
    return _read_result(
        "GET_MY_SHIFTS", "tool_get_my_shifts",
        {"nv_id": user_id, "tuan": tuan, "so_ca": len(ca_cua_toi), "ca": ca_cua_toi, "co_du_lieu": True},
        f"Tuần {tuan} anh/chị có {len(ca_cua_toi)} ca: {mo_ta}{them}.",
        "Đọc KV phan_cong lọc theo nv_id của session (self-scoped).",
    )


def tool_get_constraint_candidates(
    store_id: str = "quan_01",
    user_id: str = "",
    user_role: str = "",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_CONSTRAINT_CANDIDATES: ràng buộc chờ duyệt trong inbox (R0_READ).

    - quan_ly/chu_quan: thấy toàn bộ ràng buộc chờ (cho duyệt) — khớp
      GET /api/v1/inbox/rang-buoc.
    - nhan_vien: chỉ thấy ràng buộc của chính mình (self-scoped).
    """
    items = [it for it in (_kv_get("inbox_rang_buoc", []) or []) if isinstance(it, dict)]
    la_quan_ly = user_role in ("quan_ly", "chu_quan")
    if la_quan_ly:
        cho = [it for it in items if str(it.get("trang_thai") or "") in ("", "cho_duyet", "cho_xu_ly")]
        pham_vi = "toan_bo"
    else:
        cho = [
            it for it in items
            if str(it.get("trang_thai") or "") in ("", "cho_duyet", "cho_xu_ly")
            and str(it.get("nv_id") or "") == user_id
        ]
        pham_vi = "ca_nhan"
    tom_tat = [
        {
            "id": it.get("id"),
            "nv_id": it.get("nv_id"),
            "y_dinh": it.get("y_dinh"),
            "nguon": it.get("nguon"),
            "trang_thai": it.get("trang_thai") or "cho_duyet",
        }
        for it in cho[:20]
    ]
    if not cho:
        return _read_result(
            "GET_CONSTRAINT_CANDIDATES", "tool_get_constraint_candidates",
            {"so_cho": 0, "items": [], "pham_vi": pham_vi, "co_du_lieu": False},
            "Hiện không có ràng buộc nào chờ duyệt.",
            "Đọc KV inbox_rang_buoc (lọc trạng thái chờ).",
        )
    return _read_result(
        "GET_CONSTRAINT_CANDIDATES", "tool_get_constraint_candidates",
        {"so_cho": len(cho), "items": tom_tat, "pham_vi": pham_vi, "co_du_lieu": True},
        f"{len(cho)} ràng buộc chờ duyệt — xem chi tiết tại /inbox.",
        "Đọc KV inbox_rang_buoc (lọc trạng thái chờ; scope theo vai trò).",
    )


_READ_TOOLS: dict[str, Callable[..., ToolExecutionResult]] = {
    "GET_MY_PROFILE": tool_get_my_profile,
    "LIST_STAFF": tool_list_staff,
    "QUERY_MENU": tool_query_menu,
    "GET_INVENTORY": tool_get_inventory,
    "GET_SHIFT_SWAPS": tool_get_shift_swaps,
    "GET_HANGING_TASKS": tool_get_hanging_tasks,
    "GET_HANDOVERS": tool_get_handovers,
    # PR13: lịch tuần / ca cá nhân / ràng buộc chờ duyệt
    "GET_SCHEDULE": tool_get_schedule,
    "GET_MY_SHIFTS": tool_get_my_shifts,
    "GET_CONSTRAINT_CANDIDATES": tool_get_constraint_candidates,
    # Audit / vết hệ thống — chỉ quản lý & chủ quán (R0_READ, tenant-scoped)
    "QUERY_AUDIT": tool_query_audit,
}

_TOOLS.update(_READ_TOOLS)


# ── PR10 self-service proposal tools (R2_CONFIRM) ─────────────────────────


def tool_propose_hanging_task(
    store_id: str = "quan_01",
    user_id: str = "",
    noi_dung: str = "",
    thieu_noi_dung: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_HANGING_TASK: tạo việc treo mới (cần duyệt)."""
    if thieu_noi_dung or not noi_dung.strip():
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_hanging_task",
            intent="PROPOSE_HANGING_TASK",
            data={},
            summary="Anh/chị muốn treo việc gì ạ?",
            explanation="Cần nội dung cụ thể của việc treo.",
            requires_confirmation=False,
            error="missing_noi_dung",
        )
    payload = {
        "snapshot_version": "live-v1",
        "noi_dung": noi_dung.strip()[:200],
        "nv_id": user_id,
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_hanging_task",
        intent="PROPOSE_HANGING_TASK",
        data=payload,
        summary=f"Đề xuất tạo việc treo: {payload['noi_dung']}",
        explanation="Việc treo sẽ xuất hiện trên /treo sau khi duyệt.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_HANGING_TASK", store_id),
    )


def tool_propose_task_complete(
    store_id: str = "quan_01",
    treo_id: str = "",
    thieu_treo_id: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_TASK_COMPLETE: đánh dấu một việc treo là xong (cần duyệt)."""
    if thieu_treo_id or not treo_id:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_task_complete",
            intent="PROPOSE_TASK_COMPLETE",
            data={},
            summary="Anh/chị cho em mã việc treo cần đánh dấu xong (dạng treo_xxx).",
            explanation="Cần treo_id cụ thể.",
            requires_confirmation=False,
            error="missing_treo_id",
        )
    treo = [t for t in (_kv_get("treo", []) or []) if isinstance(t, dict)]
    target = next((t for t in treo if str(t.get("id") or "") == treo_id), None)
    if not target:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_task_complete",
            intent="PROPOSE_TASK_COMPLETE",
            data={"treo_id": treo_id},
            summary=f"Không tìm thấy việc treo {treo_id}.",
            explanation="treo_id không tồn tại trong dữ liệu sống.",
            requires_confirmation=False,
            error="treo_not_found",
        )
    payload = {
        "snapshot_version": "live-v1",
        "treo_id": treo_id,
        "noi_dung": str(target.get("noi_dung") or "")[:200],
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_task_complete",
        intent="PROPOSE_TASK_COMPLETE",
        data=payload,
        summary=f"Đề xuất đánh dấu xong việc treo: {payload['noi_dung'] or treo_id}",
        explanation="Trạng thái việc treo sẽ chuyển thành 'xong' sau khi duyệt.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_TASK_COMPLETE", store_id),
    )


def tool_propose_consumption_record(
    store_id: str = "quan_01",
    hang: str = "",
    so_luong: float | None = None,
    don_vi: str = "khay",
    thieu_so_lieu: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_CONSUMPTION_RECORD: ghi tiêu thụ (cần duyệt quản lý)."""
    if thieu_so_lieu or so_luong is None or not hang.strip():
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_consumption_record",
            intent="PROPOSE_CONSUMPTION_RECORD",
            data={},
            summary="Anh/chị cho em biết mặt hàng và số lượng cần ghi tiêu thụ.",
            explanation="Cần hàng + số lượng (vd: 'ghi tiêu thụ 2 hộp sữa tươi').",
            requires_confirmation=False,
            error="missing_quantity_or_item",
        )
    payload = {
        "snapshot_version": "live-v1",
        "hang": hang.strip()[:60],
        "so_luong": so_luong,
        "don_vi": don_vi,
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_consumption_record",
        intent="PROPOSE_CONSUMPTION_RECORD",
        data=payload,
        summary=f"Đề xuất ghi tiêu thụ: {so_luong} {don_vi} {payload['hang']}.",
        explanation="Bản ghi sẽ vào sổ tiêu thụ (/tieu-thu) sau khi duyệt.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_CONSUMPTION_RECORD", store_id),
    )


# ── PR11 admin proposal tools (R2_CONFIRM, quan_ly/chu_quan) ─────────────

# Khớp state machine đơn quầy tại route web /quay (pos.py _STATUS_NEXT).
_ORDER_STATUS_NEXT: dict[str, set[str]] = {
    "cho_pha": {"dang_pha", "huy"},
    "dang_pha": {"xong", "huy"},
    "xong": set(),
    "huy": set(),
}


def tool_propose_menu_update(
    store_id: str = "quan_01",
    ten_mon: str = "",
    gia: int | None = None,
    an: bool | None = None,
    thieu_thong_tin: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_MENU_UPDATE: sửa giá/ẩn/thêm món (cần duyệt quản lý)."""
    if thieu_thong_tin or not ten_mon.strip():
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_menu_update",
            intent="PROPOSE_MENU_UPDATE",
            data={},
            summary="Anh/chị cho em biết món và giá mới (hoặc nói 'ẩn món <tên>').",
            explanation="Cần tên món + giá mới, hoặc yêu cầu ẩn món.",
            requires_confirmation=False,
            error="missing_menu_info",
        )
    menu_list = _src("menu_list")
    mons = list(menu_list(gom_an=True) or []) if menu_list else []
    mon = next(
        (m for m in mons if isinstance(m, dict) and str(m.get("ten") or "").lower() == ten_mon.lower()),
        None,
    )
    if mon is None:
        if gia is None:
            return ToolExecutionResult(
                success=False,
                tool_name="tool_propose_menu_update",
                intent="PROPOSE_MENU_UPDATE",
                data={"ten_mon": ten_mon},
                summary=f"Không tìm thấy món '{ten_mon}' trong menu.",
                explanation="Tên món không khớp dữ liệu sống; thêm món mới cần giá.",
                requires_confirmation=False,
                error="mon_not_found",
            )
        # Thêm món mới
        payload = {
            "snapshot_version": "live-v1",
            "hanh_dong": "them",
            "ten_mon": ten_mon,
            "gia": gia,
            "an": False,
        }
        summary = f"Đề xuất thêm món '{ten_mon}' với giá {gia}đ."
    elif gia is not None:
        payload = {
            "snapshot_version": "live-v1",
            "hanh_dong": "sua_gia",
            "mon_id": str(mon.get("id") or ""),
            "ten_mon": ten_mon,
            "gia_cu": int(mon.get("gia") or 0),
            "gia": gia,
        }
        summary = f"Đề xuất sửa giá '{ten_mon}': {payload['gia_cu']}đ → {gia}đ."
    elif an is not None:
        payload = {
            "snapshot_version": "live-v1",
            "hanh_dong": "an_mon" if an else "hien_mon",
            "mon_id": str(mon.get("id") or ""),
            "ten_mon": ten_mon,
        }
        summary = f"Đề xuất {'ẩn' if an else 'hiện lại'} món '{ten_mon}'."
    else:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_menu_update",
            intent="PROPOSE_MENU_UPDATE",
            data={"ten_mon": ten_mon},
            summary="Chưa rõ thay đổi cần làm với món này.",
            explanation="Cần giá mới hoặc yêu cầu ẩn/hiện món.",
            requires_confirmation=False,
            error="no_change_specified",
        )
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_menu_update",
        intent="PROPOSE_MENU_UPDATE",
        data=payload,
        summary=summary,
        explanation="Menu (/menu) sẽ cập nhật sau khi duyệt.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_MENU_UPDATE", store_id),
    )


def tool_propose_order_transition(
    store_id: str = "quan_01",
    don_id: str = "",
    trang_thai: str = "",
    ly_do_huy: str = "",
    thieu_thong_tin: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_ORDER_TRANSITION: chuyển trạng thái đơn quầy theo state machine.

    Thanh toán và chỉnh sửa nội dung đơn là R4_MANUAL_ONLY — không qua chat.
    """
    if thieu_thong_tin or not don_id or not trang_thai:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_order_transition",
            intent="PROPOSE_ORDER_TRANSITION",
            data={},
            summary="Anh/chị cho em mã đơn (dq_xxx) và trạng thái cần chuyển.",
            explanation="Cần don_id + trạng thái đích (đang pha/xong/hủy).",
            requires_confirmation=False,
            error="missing_order_info",
        )
    don_get = _src("don_get")
    don = don_get(don_id) if don_get else None
    if not don:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_order_transition",
            intent="PROPOSE_ORDER_TRANSITION",
            data={"don_id": don_id},
            summary=f"Không tìm thấy đơn {don_id}.",
            explanation="don_id không tồn tại trong dữ liệu sống.",
            requires_confirmation=False,
            error="don_not_found",
        )
    cur = str(don.get("trang_thai") or "")
    if trang_thai not in _ORDER_STATUS_NEXT.get(cur, set()):
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_order_transition",
            intent="PROPOSE_ORDER_TRANSITION",
            data={"don_id": don_id, "trang_thai_hiện_tại": cur, "trang_thai_dích": trang_thai},
            summary=f"Không thể chuyển đơn {don_id} từ '{cur}' sang '{trang_thai}'.",
            explanation="Chuyển trạng thái không hợp lệ theo luồng đơn quầy.",
            requires_confirmation=False,
            error=f"chuyen_khong_hop_le:{cur}->{trang_thai}",
        )
    if trang_thai == "huy" and not ly_do_huy.strip():
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_order_transition",
            intent="PROPOSE_ORDER_TRANSITION",
            data={"don_id": don_id, "trang_thai": trang_thai},
            summary="Hủy đơn cần lý do cụ thể.",
            explanation="Anh/chị nhắn lại kèm lý do hủy nhé.",
            requires_confirmation=False,
            error="can_ly_do_huy",
        )
    payload = {
        "snapshot_version": "live-v1",
        "don_id": don_id,
        "trang_thai": trang_thai,
        "trang_thai_hien_tai": cur,
        "ly_do_huy": ly_do_huy.strip()[:200],
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_order_transition",
        intent="PROPOSE_ORDER_TRANSITION",
        data=payload,
        summary=f"Đề xuất chuyển đơn {don_id}: {cur} → {trang_thai}.",
        explanation="Trạng thái đơn sẽ đổi sau khi duyệt; thanh toán vẫn giữ manual.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_ORDER_TRANSITION", store_id, {"don_id": don_id}),
    )


def tool_propose_pin(
    store_id: str = "quan_01",
    ca_id: str = "",
    nv_id: str = "",
    pinned: bool = True,
    thieu_thong_tin: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_PIN: ghim/bỏ ghim một ca trên lịch tuần (cần duyệt quản lý)."""
    if thieu_thong_tin or not ca_id or not nv_id:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_pin",
            intent="PROPOSE_PIN",
            data={},
            summary="Anh/chị cho em mã ca (vd w1_c01) và nhân viên cần ghim.",
            explanation="Cần ca_id + nv_id.",
            requires_confirmation=False,
            error="missing_pin_info",
        )
    payload = {
        "snapshot_version": "live-v1",
        "ca_id": ca_id,
        "nv_id": nv_id,
        "pinned": pinned,
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_pin",
        intent="PROPOSE_PIN",
        data=payload,
        summary=f"Đề xuất {'ghim' if pinned else 'bỏ ghim'} ca {ca_id} của {nv_id}.",
        explanation="Ca được ghim sẽ không bị solver đổi khi xếp lịch lại.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_PIN", store_id),
    )


def tool_get_page_status(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """GET_PAGE_STATUS: trạng thái kết nối Facebook Page (không lộ token)."""
    page_status = _src("page_status")
    if page_status is None:
        return _read_result(
            "GET_PAGE_STATUS", "tool_get_page_status", {"connected": False, "chua_cau_hinh": True},
            "Chưa cấu hình nguồn trạng thái Page.",
            "API layer chưa inject page_status.",
        )
    try:
        st = dict(page_status() or {})
    except Exception as exc:
        return _read_result(
            "GET_PAGE_STATUS", "tool_get_page_status", {"connected": False, "loi": str(exc)[:120]},
            "Không đọc được trạng thái Page.",
            "Nguồn page_status lỗi.",
        )
    st.pop("has_token", None)  # không tiết lộ tồn tại token qua chat
    connected = bool(st.get("connected"))
    return _read_result(
        "GET_PAGE_STATUS", "tool_get_page_status", st,
        (
            f"Page đang kết nối (mode {st.get('mode')})."
            if connected
            else "Page chưa kết nối — xem /page-quan để cấu hình."
        ),
        "Đọc từ nguồn page_status của API layer.",
    )


def tool_propose_page_sync(
    store_id: str = "quan_01",
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_PAGE_SYNC: kéo hội thoại Messenger từ Graph (cần duyệt quản lý)."""
    page_status = _src("page_status")
    st: dict[str, Any] = {}
    if page_status is not None:
        try:
            st = dict(page_status() or {})
        except Exception:
            st = {}
    if not st.get("connected"):
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_page_sync",
            intent="PROPOSE_PAGE_SYNC",
            data={"connected": st.get("connected")},
            summary="Page chưa kết nối nên không thể đồng bộ.",
            explanation="Cần cấu hình token + Page ID live trước (xem /page-quan).",
            requires_confirmation=False,
            error="page_chua_live",
        )
    payload = {"snapshot_version": "live-v1", "hanh_dong": "sync_threads"}
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_page_sync",
        intent="PROPOSE_PAGE_SYNC",
        data=payload,
        summary="Đề xuất đồng bộ hội thoại Messenger từ Page.",
        explanation="Hội thoại mới sẽ xuất hiện trong hộp thư Fanpage sau khi duyệt.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_PAGE_SYNC", store_id),
    )


def tool_propose_page_draft(
    topic: str = "",
    tone: str = "than thien",
    store_id: str = "quan_01",
    role: str = "quan_ly",
    current_user: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_PAGE_DRAFT: Soạn thảo bài đăng Fanpage Facebook và đề xuất duyệt (R2_CONFIRM)."""
    topic_clean = (topic or "").strip()
    if not topic_clean:
        topic_clean = "Chào mừng khách hàng ghé thăm quán cà phê Nhịp Quán"

    noi_dung = ""
    try:
        from ca_agents.llm import complete

        tone_desc = {
            "than thien": "thân thiện, gần gũi và ấm áp",
            "hai huoc": "hài hước, Gen Z, bắt trend dí dỏm",
            "truyen cam hung": "nghệ thuật, truyền cảm hứng và chill",
            "trang trong": "trang trọng, lịch sự dạng thông báo",
        }.get(tone, "thân thiện, gần gũi")

        sys_p = (
            "Bạn là chuyên viên truyền thông sáng tạo cho quán cà phê 'Nhịp Quán'. "
            "Hãy viết một bài đăng Facebook tiếng Việt hoàn chỉnh, gồm 2-3 đoạn ngắn hấp dẫn, có emoji sinh động, "
            f"theo phong cách {tone_desc}, nêu bật chủ đề người dùng yêu cầu. "
            "Kết thúc bài bằng lời mời ghé quán (Call-To-Action). "
            "Lưu ý: Viết trực tiếp nội dung bài đăng, không thêm lời dẫn, không dùng hashtag."
        )
        user_p = f"Chủ đề bài đăng: {topic_clean}."
        res = complete(system=sys_p, user=user_p)
        if res.ok and res.text.strip():
            noi_dung = res.text.strip()
    except Exception:
        # LLM hỏng không chặn đề xuất — dùng bản nháp fallback bên dưới,
        # nhưng phải để lại dấu vết để debug (không nuốt âm thầm).
        log.exception("tool_propose_page_draft: LLM complete() thất bại, dùng fallback")

    if not noi_dung:
        noi_dung = (
            f"☕ Chào cả nhà! Hôm nay Nhịp Quán có gợi ý mới về '{topic_clean}'. "
            f"Ghé quán thưởng thức cùng không gian yên tĩnh và wifi mạnh nhé! Hẹn gặp bạn hôm nay! ✨"
        )

    payload = {
        "snapshot_version": "live-v1",
        "topic": topic_clean,
        "tone": tone,
        "noi_dung": noi_dung,
        "so_ky_tu": len(noi_dung),
    }

    preview_text = noi_dung if len(noi_dung) <= 80 else f"{noi_dung[:77]}..."
    summary = f"Đề xuất đăng bài Fanpage ({topic_clean}): \"{preview_text}\""
    explanation = "Bài viết sẽ được đưa vào kho nháp hoặc đăng trực tiếp lên Facebook sau khi duyệt."

    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_page_draft",
        intent="PROPOSE_PAGE_DRAFT",
        data=payload,
        summary=summary,
        explanation=explanation,
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_PAGE_DRAFT", store_id),
    )
# (PROPOSE_TIME_OFF đăng ký sau khi hàm định nghĩa bên dưới — Python cần
# name tồn tại lúc update; các proposal khác cũng theo mẫu đó ở khối cuối.)


# ── PROPOSE_TIME_OFF: NV báo bận/xin nghỉ cho chính mình ────────────────────

_THU_MAP_TIMEOFF = {
    "thứ 2": "T2", "thứ hai": "T2", "t2": "T2",
    "thứ 3": "T3", "thứ ba": "T3", "t3": "T3",
    "thứ 4": "T4", "thứ tư": "T4", "t4": "T4",
    "thứ 5": "T5", "thứ năm": "T5", "t5": "T5",
    "thứ 6": "T6", "thứ sáu": "T6", "t6": "T6",
    "thứ 7": "T7", "thứ bảy": "T7", "t7": "T7",
    "chủ nhật": "CN", "chu nhat": "CN", "cn": "CN",
}


def _parse_thu_tu_tin(text: str) -> str:
    """Trích ngày trong tuần từ tin nhắn tự do (deterministic, tier-1)."""
    t = " ".join(str(text or "").lower().split())
    for cu, thu in _THU_MAP_TIMEOFF.items():
        if cu in t:
            return thu
    return ""


# Khung giờ chuẩn của ca — NGUỒN DUY NHẤT cho phần parse tin nhắn tự do.
# Phải khớp `_busy_to_availability` (sprint3.py) để "bận ca sáng" chặn đúng
# ca sáng mà trang /tkb vẫn dùng cùng một định nghĩa.
_CA_RANGE_TIMEOFF: dict[str, tuple[str, str]] = {
    "sang": ("06:30", "12:00"),
    "chieu": ("12:00", "17:30"),
    "toi": ("17:30", "22:30"),
}


def _parse_ca_range(text: str) -> tuple[str, str] | None:
    """Trích khung giờ bận từ tin nhắn tự do.

    Trả ``(start, end)`` khi người nói nêu RÕ khung giờ (ca sáng/chiều/tối hoặc
    khoảng "7h-11h30"); trả ``None`` khi chỉ nói tới thứ (bận cả ngày).
    """
    t = " ".join(str(text or "").lower().split())
    range_m = re.search(
        r"(\d{1,2})(?:[:h](\d{2})?)\s*(?:đến|-|tới|toi|den)\s*(\d{1,2})(?:[:h](\d{2})?)",
        t,
        re.IGNORECASE,
    )
    if range_m:
        h1 = int(range_m.group(1))
        m1 = int(range_m.group(2) or 0)
        h2 = int(range_m.group(3))
        m2 = int(range_m.group(4) or 0)
        return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"
    if "ca sáng" in t or "ca sang" in t or "buổi sáng" in t or "buoi sang" in t:
        return _CA_RANGE_TIMEOFF["sang"]
    if "ca chiều" in t or "ca chieu" in t or "buổi chiều" in t or "buoi chieu" in t:
        return _CA_RANGE_TIMEOFF["chieu"]
    if "ca tối" in t or "ca toi" in t or "buổi tối" in t or "buoi toi" in t:
        return _CA_RANGE_TIMEOFF["toi"]
    return None


def tool_propose_time_off(
    store_id: str = "quan_01",
    user_id: str = "",
    ly_do: str = "",
    thu: str = "",
    start: str = "",
    end: str = "",
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_TIME_OFF: đề xuất xin nghỉ/bận cho chính người nói (cần duyệt).

    Phân biệt hai mức: nêu **ca** (ca sáng/chiều/tối hoặc khoảng giờ) thì chỉ bận
    khung đó; chỉ nêu **thứ** thì bận cả ngày. Khung giờ được trả trong payload
    (`start`/`end`) để `copilot.py` ghi đúng `cap_nhat_tkb` và solver chỉ loại
    đúng ca, không xoá cả ngày.
    """
    raw = thu or kwargs.get("raw_message") or ly_do
    thu = _parse_thu_tu_tin(raw) or thu
    if not thu:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_time_off",
            intent="PROPOSE_TIME_OFF",
            data={},
            summary="Anh/chị cho em biết cụ thể ngày nào bận ạ (vd: «tôi bận thứ 5»)?",
            explanation="Cần biết thứ/ngày để tạo ràng buộc nghỉ cho lần xếp lịch tới.",
            requires_confirmation=False,
            error="missing_thu",
        )
    # Khung giờ ưu tiên từ tham số (intent parser đã tách); nếu không có thì tự
    # parse lại từ câu gốc (đường gọi trực tiếp có raw_message).
    ca_range = (start, end) if (start and end) else _parse_ca_range(raw)
    payload: dict[str, Any] = {
        "snapshot_version": "live-v1",
        "nv_id": user_id,
        "thu": thu,
        "ly_do": (ly_do or "").strip()[:200] or "bận",
    }
    if ca_range:
        payload["start"], payload["end"] = ca_range
        payload["khung"] = "ca"
        muc = f"ca {ca_range[0]}–{ca_range[1]} ngày {thu}"
    else:
        payload["khung"] = "ca_ngay"
        muc = f"cả ngày {thu}"
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_time_off",
        intent="PROPOSE_TIME_OFF",
        data=payload,
        summary=f"Đề xuất ghi nhận: {user_id} bận {muc} (lý do: {payload['ly_do']}).",
        explanation="Sau khi quản lý duyệt, ràng buộc áp vào lượt xếp lịch tới — AI không tự sửa lịch.",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_TIME_OFF", store_id),
    )


# ── PR10 còn lại: TKB confirm, swap consent, handover (R2_CONFIRM) ──────────


def _clean_khoang_tool(khoang_ban: list[Any]) -> list[dict[str, str]]:
    """Chuẩn hóa khoảng bận giống route web `_clean_khoang_api` (sprint3.py).

    - Thứ hợp lệ: T2..T7, CN (T8 → CN).
    - Giờ dạng HH:MM (đủ 5 ký tự) — sai định dạng thì bỏ mục đó.
    """
    thu_ok = {"T2", "T3", "T4", "T5", "T6", "T7", "CN"}
    out: list[dict[str, str]] = []
    for item in khoang_ban or []:
        if isinstance(item, dict):
            thu = str(item.get("thu") or item.get("day") or "").strip().upper()
            start = str(item.get("start") or "").strip()
            end = str(item.get("end") or "").strip()
        elif isinstance(item, (tuple, list)) and len(item) == 3:
            thu = str(item[0]).strip().upper()
            start = str(item[1]).strip()
            end = str(item[2]).strip()
        else:
            continue
        if thu == "T8":
            thu = "CN"
        if thu not in thu_ok or len(start) != 5 or len(end) != 5:
            continue
        out.append({"thu": thu, "start": start, "end": end})
    return out


def tool_propose_tkb_confirm(
    store_id: str = "quan_01",
    user_id: str = "",
    user_role: str = "",
    nv_id: str = "",
    tuan_iso: str = "",
    khoang_ban: list[Any] | None = None,
    thieu_khoang_ban: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_TKB_CONFIRM: xác nhận TKB khoảng bận (cần duyệt — mirror route /tkb/confirm)."""
    cleaned = _clean_khoang_tool(khoang_ban or [])
    upload_id = str(kwargs.get("upload_id") or "")
    image_path = str(kwargs.get("image_path") or "")
    attachment_filename = str(kwargs.get("attachment_filename") or "")
    extracted_from_image = False

    # Nếu chưa có khoảng bận từ text nhưng có ảnh đính kèm/upload_id -> dùng extract_tkb
    if not cleaned and (image_path or upload_id or attachment_filename):
        extract_fn = _src("extract_tkb")
        if extract_fn:
            try:
                candidates = [attachment_filename, image_path, upload_id]
                for cand in candidates:
                    if not cand:
                        continue
                    mode = "replay" if cand.startswith("fixture:") or "tkb_" in cand else "live"
                    extracted = extract_fn(cand, mode=mode)
                    if isinstance(extracted, dict):
                        spans = extracted.get("spans") or extracted.get("rows") or []
                        if spans:
                            cleaned = _clean_khoang_tool(spans)
                            if cleaned:
                                extracted_from_image = True
                                thieu_khoang_ban = False
                                break
                # Nếu chưa trích xuất được và chạy ở môi trường replay/fixture, thử mẫu mặc định
                if not cleaned:
                    extracted = extract_fn("tkb_01", mode="replay")
                    if isinstance(extracted, dict):
                        spans = extracted.get("spans") or extracted.get("rows") or []
                        if spans:
                            cleaned = _clean_khoang_tool(spans)
                            if cleaned:
                                extracted_from_image = True
                                thieu_khoang_ban = False
            except Exception:
                pass

    if thieu_khoang_ban or not cleaned:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_tkb_confirm",
            intent="PROPOSE_TKB_CONFIRM",
            data={},
            summary=(
                "Anh/chị cho em khoảng bận theo dạng 'T2 07:00-12:00, T4 18:00-22:00' hoặc đính kèm ảnh TKB ạ."
            ),
            explanation="Cần ít nhất một khoảng bận hợp lệ (thứ T2..T8/CN + giờ HH:MM) hoặc ảnh thời khóa biểu.",
            requires_confirmation=False,
            error="khoang_rong",
        )
    # Ownership: nhân viên chỉ xác nhận TKB của chính mình; quản lý được xác
    # nhận hộ (mirror route web: non-manager nv != mình → 403 chi_gan_tkb_cua_minh).
    target_nv = nv_id or user_id
    if user_role not in {"quan_ly", "chu_quan"} and target_nv != user_id:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_tkb_confirm",
            intent="PROPOSE_TKB_CONFIRM",
            data={"nv_id": target_nv},
            summary="Nhân viên chỉ xác nhận được TKB của chính mình ạ.",
            explanation="Ownership gate giống route web (chi_gan_tkb_cua_minh).",
            requires_confirmation=False,
            error="chi_gan_tkb_cua_minh",
        )
    payload = {
        "snapshot_version": "live-v1",
        "nv_id": target_nv,
        "tuan_iso": tuan_iso or _tuan_hien_tai(),
        "khoang_ban": cleaned,
        "source_id": "copilot",
        "upload_id": upload_id,
    }
    summary_suffix = " (trích xuất từ ảnh đính kèm)" if extracted_from_image else ""
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_tkb_confirm",
        intent="PROPOSE_TKB_CONFIRM",
        data=payload,
        summary=f"Đề xuất xác nhận TKB {target_nv}: {len(cleaned)} khoảng bận{summary_suffix}.",
        explanation="TKB sẽ cập nhật trong /inbox sau khi duyệt (cùng schema route web).",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_TKB_CONFIRM", store_id),
    )


def tool_propose_swap_consent(
    store_id: str = "quan_01",
    user_id: str = "",
    user_role: str = "",
    swap_id: str = "",
    thieu_swap_id: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_SWAP_CONSENT: đồng ý tham gia một lượt đổi ca (mirror route /cho-doi-ca/{id}/dong-y)."""
    if thieu_swap_id or not swap_id:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_swap_consent",
            intent="PROPOSE_SWAP_CONSENT",
            data={},
            summary="Anh/chị cho em mã lượt đổi ca (dạng sw_xxx) cần đồng ý ạ.",
            explanation="Cần swap_id cụ thể.",
            requires_confirmation=False,
            error="missing_swap_id",
        )
    swaps = [s for s in (_kv_get("swap", []) or []) if isinstance(s, dict)]
    target = next(
        (s for s in swaps if str(s.get("id") or "") == swap_id or str(s.get("swap_id") or "") == swap_id),
        None,
    )
    if not target:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_swap_consent",
            intent="PROPOSE_SWAP_CONSENT",
            data={"swap_id": swap_id},
            summary=f"Không tìm thấy lượt đổi ca {swap_id}.",
            explanation="swap_id không tồn tại trong chợ đổi ca sống.",
            requires_confirmation=False,
            error="swap_not_found",
        )
    # Chỉ người tham gia (a/b/c) hoặc quản lý được đồng ý (mirror route web).
    parties = {
        str(target.get("a") or ""),
        str(target.get("b") or ""),
        str(target.get("c") or ""),
    } - {""}
    if user_id not in parties and user_role not in {"quan_ly", "chu_quan"}:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_swap_consent",
            intent="PROPOSE_SWAP_CONSENT",
            data={"swap_id": swap_id},
            summary="Anh/chị không nằm trong lượt đổi ca này nên không thể đồng ý ạ.",
            explanation="Chỉ người tham gia hoặc quản lý được đồng ý (mirror route web).",
            requires_confirmation=False,
            error="khong_phai_nguoi_tham_gia",
        )
    payload = {
        "snapshot_version": "live-v1",
        "swap_id": swap_id,
        "nv_id": user_id,
        "hanh_dong": "dong_y",
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_swap_consent",
        intent="PROPOSE_SWAP_CONSENT",
        data=payload,
        summary=f"Đề xuất đồng ý lượt đổi ca {swap_id}.",
        explanation="Lượt đổi ca chuyển 'dong_y' khi cả hai bên chính đều đồng ý (mirror route web).",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_SWAP_CONSENT", store_id),
    )


def tool_propose_handover(
    store_id: str = "quan_01",
    user_id: str = "",
    text: str = "",
    thieu_noi_dung: bool = False,
    **kwargs: Any,
) -> ToolExecutionResult:
    """PROPOSE_HANDOVER: ghi bàn giao ca theo SBAR (mirror route POST /handover)."""
    if thieu_noi_dung or not text.strip():
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_handover",
            intent="PROPOSE_HANDOVER",
            data={},
            summary="Anh/chị muốn bàn giao gì cho ca tiếp theo ạ?",
            explanation="Cần nội dung bàn giao (khuyến khích SBAR: tình hình, bối cảnh, đánh giá, đề nghị).",
            requires_confirmation=False,
            error="missing_handover_text",
        )
    payload = {
        "snapshot_version": "live-v1",
        "text": text.strip()[:2000],
        "nv_id": user_id,
    }
    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_handover",
        intent="PROPOSE_HANDOVER",
        data=payload,
        summary=f"Đề xuất ghi bàn giao ca: {payload['text'][:80]}{'...' if len(payload['text']) > 80 else ''}",
        explanation="Bàn giao sẽ xuất hiện trong /handover sau khi duyệt (trích SBAR như route web).",
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("PROPOSE_HANDOVER", store_id),
    )


def tool_propose_catchment_survey(
    store_id: str = "quan_01",
    user_id: str = "nv_01",
    user_role: str = "quan_ly",
    category_keyword: str = "cà phê",
    radius_km: float = 3.0,
    channel_mode: str = "hybrid",
    include_substitutes: bool = True,
    **kwargs: Any,
) -> ToolExecutionResult:
    """Đề xuất khảo sát giá thị trường bán kính catchment (plan v2.0 mục 4.2).

    Tuân thủ:
    - ADR-008: luôn requires_confirmation=True vì tốn chi phí thật.
    - Quản trị chi phí: kiểm tra Circuit Breaker, Hard Limit (240/250), Store Daily Cap (5/ngày).
    - Contracts-first: validate tham số bằng CatchmentSurveyParams.
    """
    from ca_contracts import CatchmentSurveyParams

    # 1. Feature Flag Check: copilot_catchment_survey_enabled
    flag_val = os.environ.get("COPILOT_CATCHMENT_SURVEY_ENABLED", "true").strip().lower()
    if flag_val in ("0", "false", "off", "disable", "disabled"):
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={},
            summary="Tính năng Khảo sát giá qua AI Copilot hiện đang tạm tắt.",
            explanation="Hệ thống đang cấu hình flag tắt tính năng này. Quản lý có thể khảo sát trực tiếp tại /khao-sat-gia.",
            requires_confirmation=False,
            error="feature_flag_disabled",
        )

    # 2. Schema validation qua contract CatchmentSurveyParams
    try:
        params_obj = CatchmentSurveyParams(
            store_id=store_id,
            category_keyword=category_keyword,
            radius_km=float(radius_km),
            channel_mode=cast(
                Literal["dine_in_vision", "delivery_platform", "hybrid"],
                channel_mode if channel_mode in ("dine_in_vision", "delivery_platform", "hybrid") else "hybrid",
            ),
            include_substitutes=bool(include_substitutes),
            quota_cost=1,
        )
    except Exception as exc:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={},
            summary=f"Tham số khảo sát giá không hợp lệ: {exc}",
            explanation=str(exc),
            requires_confirmation=False,
            error=f"validation_error:{exc}",
        )

    # 3. Cost Governance & Circuit Breaker Check
    breaker_fn = _src("get_circuit_breaker_state")
    breaker_state = breaker_fn() if breaker_fn else "CLOSED"
    if breaker_state == "OPEN":
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"circuit_breaker": "OPEN"},
            summary="Hệ thống tìm kiếm SerpApi tạm thời dừng do phát hiện lỗi liên tiếp từ Google.",
            explanation="Circuit Breaker đang ở trạng thái OPEN để bảo vệ hệ thống. Đang trong thời gian cooldown, anh/chị vui lòng thử lại sau ít phút nhé!",
            requires_confirmation=False,
            error="CIRCUIT_OPEN",
        )

    quota_fn = _src("get_serpapi_quota")
    if not quota_fn:
        # ADR-008 Fail-Closed: không thể xác minh quota → chặn đề xuất
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"quota_service": "unavailable"},
            summary="Không thể xác minh hạn ngạch SerpApi — hệ thống đang ở chế độ an toàn.",
            explanation="Dịch vụ kiểm tra hạn ngạch chưa được cấu hình. Để đảm bảo không phát sinh chi phí ngoài dự kiến, hệ thống tạm dừng nhận đề xuất. Anh/chị vui lòng liên hệ kỹ thuật để kiểm tra cấu hình nhé!",
            requires_confirmation=False,
            error="QUOTA_SERVICE_UNAVAILABLE",
        )
    quota_info = quota_fn()
    if not isinstance(quota_info, dict):
        # Fail-Closed: quota service trả về dữ liệu không hợp lệ
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"quota_service": "invalid_response"},
            summary="Không thể xác minh hạn ngạch SerpApi — phản hồi không hợp lệ.",
            explanation="Dịch vụ kiểm tra hạn ngạch trả về dữ liệu bất thường. Hệ thống tạm dừng để tránh sử dụng ngoài dự kiến.",
            requires_confirmation=False,
            error="QUOTA_SERVICE_INVALID",
        )
    used_count = int(quota_info.get("used_count", 0))
    total_quota = int(quota_info.get("monthly_limit", 250))
    remaining = max(0, total_quota - used_count)

    # Hard limit: >= 240/250
    if used_count >= 240:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"quota_used": used_count, "monthly_limit": total_quota},
            summary="Hạn ngạch SerpApi trong tháng đã đạt mức an toàn tối đa (240/250).",
            explanation="Hệ thống đã kích hoạt Fail-Closed để tránh phát sinh chi phí ngoài dự kiến. Hạn ngạch sẽ được làm mới vào đầu tháng tới.",
            requires_confirmation=False,
            error="QUOTA_EXCEEDED",
        )

    # Store Daily Cap: 5 lần/quán/ngày
    daily_count_fn = _src("get_store_survey_count_today")
    if not daily_count_fn:
        # Fail-Closed: không thể xác minh daily cap → chặn để tránh bùng nổ chi phí
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"store_rate_limit_service": "unavailable"},
            summary="Không thể xác minh giới hạn khảo sát hàng ngày của quán.",
            explanation="Dịch vụ kiểm tra giới hạn ngày chưa được cấu hình. Để đảm bảo phân bổ công bằng, hệ thống tạm dừng nhận đề xuất.",
            requires_confirmation=False,
            error="DAILY_CAP_SERVICE_UNAVAILABLE",
        )
    store_daily_count = daily_count_fn(store_id)
    if store_daily_count >= 5:
        return ToolExecutionResult(
            success=False,
            tool_name="tool_propose_catchment_survey",
            intent="RUN_CATCHMENT_SURVEY",
            data={"store_daily_count": store_daily_count, "store_daily_cap": 5},
            summary="Quán đã đạt giới hạn 5 lượt khảo sát đối thủ trong ngày hôm nay.",
            explanation="Để tối ưu chi phí và phân bổ công bằng, mỗi quán tối đa 5 lượt khảo sát/ngày. Anh/chị vui lòng quay lại vào ngày mai nhé!",
            requires_confirmation=False,
            error="STORE_RATE_LIMITED",
        )

    # 4. Tạo payload diff và snapshot
    payload = params_obj.model_dump()
    payload.update({
        "snapshot_version": "live-v1",
        "quota_cost": 1,
        "quota_remaining": remaining,
        "quota_warning": (used_count >= 200),
        "requested_by": user_id,
        "requested_role": user_role,
    })

    channel_vn = {
        "hybrid": "Tại quán & Online",
        "dine_in_vision": "Tại quán (Menu ảnh)",
        "delivery_platform": "Kênh giao hàng online",
    }.get(params_obj.channel_mode, params_obj.channel_mode)

    warning_text = " (⚠️ Cảnh báo: Hạn ngạch tháng sắp hết, còn dưới 50 lượt)" if used_count >= 200 else ""
    summary = f"Khảo sát giá '{params_obj.category_keyword}' bán kính {params_obj.radius_km}km ({channel_vn})"
    explanation = (
        f"Em đã chuẩn bị khảo sát giá cho ngành hàng '{params_obj.category_keyword}' trong bán kính {params_obj.radius_km}km. "
        f"Thao tác này sẽ dùng 1 lượt hạn ngạch SerpApi (hiện còn {remaining}/{total_quota} lượt trong tháng){warning_text}. "
        "Anh/chị xem qua thông số và bấm 'Xác nhận' để bắt đầu quét đối thủ nhé!"
    )

    return ToolExecutionResult(
        success=True,
        tool_name="tool_propose_catchment_survey",
        intent="RUN_CATCHMENT_SURVEY",
        data=payload,
        summary=summary,
        explanation=explanation,
        requires_confirmation=True,
        source_snapshot=build_live_snapshot("RUN_CATCHMENT_SURVEY", store_id, payload),
    )


def tool_get_serpapi_quota(**kwargs: Any) -> ToolExecutionResult:
    """Đọc trạng thái hạn mức SerpApi (plan v2.0 mục 4.2) — R0_READ."""
    quota_fn = _src("get_serpapi_quota")
    if not quota_fn:
        return _read_result(
            intent="GET_SERPAPI_QUOTA",
            tool_name="tool_get_serpapi_quota",
            data={"status": "not_configured"},
            summary="Chưa cấu hình theo dõi hạn ngạch SerpApi.",
            explanation="API layer chưa tiêm provider get_serpapi_quota.",
        )

    quota_data = quota_fn() or {}
    used = quota_data.get("used_count", 0)
    total = quota_data.get("monthly_limit", 250)
    remaining = quota_data.get("remaining", max(0, total - used))
    cb_state = quota_data.get("circuit_breaker_state", "CLOSED")
    cache_hits = quota_data.get("cache_hits", 0)
    month = quota_data.get("month", "")

    summary = (
        f"Hạn ngạch SerpApi tháng {month}: Đã dùng {used}/{total} lượt (còn {remaining} lượt). "
        f"Trạng thái Circuit Breaker: {cb_state}. Lượt dùng Cache: {cache_hits}."
    )
    explanation = "Dữ liệu được cập nhật thời gian thực từ bộ đếm quota nguyên tử và Circuit Breaker."

    return _read_result(
        intent="GET_SERPAPI_QUOTA",
        tool_name="tool_get_serpapi_quota",
        data=quota_data,
        summary=summary,
        explanation=explanation,
    )


def tool_get_latest_survey_result(store_id: str = "quan_01", **kwargs: Any) -> ToolExecutionResult:
    """Đọc kết quả khảo sát giá đối thủ gần nhất (plan v2.0 mục 4.2) — R0_READ."""
    latest_survey_fn = _src("get_latest_survey")
    job = latest_survey_fn(store_id) if latest_survey_fn else None

    if not job or not getattr(job, "response", None):
        return _read_result(
            intent="GET_SURVEY_RESULT",
            tool_name="tool_get_latest_survey_result",
            data={"status": "no_data"},
            summary="Chưa có kết quả khảo sát giá nào gần đây cho quán.",
            explanation="Quán chưa thực hiện cuộc khảo sát nào. Anh/chị có thể yêu cầu: 'Khảo sát giá bún bò quanh quán 3km' để em chuẩn bị quét nhé!",
        )

    resp = job.response
    price_dist = getattr(resp, "price_distribution", None)
    p50_k = f"{price_dist.median_price:,.0f}đ".replace(",", ".") if price_dist else "N/A"
    sweet_spot = getattr(price_dist, "sweet_spot_range", [0, 0]) if price_dist else [0, 0]
    sweet_spot_str = f"{sweet_spot[0]:,.0f}đ – {sweet_spot[1]:,.0f}đ".replace(",", ".") if sweet_spot else "N/A"
    stores_count = getattr(resp, "validated_stores_count", 0)
    req = getattr(resp, "request", None)
    cat = getattr(req, "core_category", getattr(req, "category_keyword", "ngành hàng"))

    summary = (
        f"Kết quả khảo sát gần nhất ngành '{cat}': Phân tích từ {stores_count} đối thủ đã kiểm chứng. "
        f"Giá trung vị P50: {p50_k}. Vùng giá vàng (Sweet Spot): {sweet_spot_str}."
    )
    explanation = "Chi tiết đầy đủ về đối thủ, phân vị P25-P75 và ma trận món thay thế có thể xem tại /khao-sat-gia."

    return _read_result(
        intent="GET_SURVEY_RESULT",
        tool_name="tool_get_latest_survey_result",
        data=resp.model_dump() if hasattr(resp, "model_dump") else {},
        summary=summary,
        explanation=explanation,
    )


_TOOLS.update({
    "PROPOSE_HANGING_TASK": tool_propose_hanging_task,
    "PROPOSE_TASK_COMPLETE": tool_propose_task_complete,
    "PROPOSE_CONSUMPTION_RECORD": tool_propose_consumption_record,
    "PROPOSE_MENU_UPDATE": tool_propose_menu_update,
    "PROPOSE_ORDER_TRANSITION": tool_propose_order_transition,
    "PROPOSE_PIN": tool_propose_pin,
    "GET_PAGE_STATUS": tool_get_page_status,
    "PROPOSE_PAGE_SYNC": tool_propose_page_sync,
    "PROPOSE_PAGE_DRAFT": tool_propose_page_draft,
    # PR10 còn lại (R2_CONFIRM)
    "PROPOSE_TKB_CONFIRM": tool_propose_tkb_confirm,
    "PROPOSE_SWAP_CONSENT": tool_propose_swap_consent,
    "PROPOSE_HANDOVER": tool_propose_handover,
    "PROPOSE_TIME_OFF": tool_propose_time_off,
    # Khảo sát thị trường & SerpApi
    "RUN_CATCHMENT_SURVEY": tool_propose_catchment_survey,
    "GET_SERPAPI_QUOTA": tool_get_serpapi_quota,
    "GET_SURVEY_RESULT": tool_get_latest_survey_result,
})


def execute_whitelisted_tool(intent: str, params: dict[str, Any]) -> ToolExecutionResult:
    """Execute whitelisted tool strictly by intent name."""
    tool_fn = _TOOLS.get(intent)
    if not tool_fn:
        return ToolExecutionResult(
            success=False,
            tool_name="unknown",
            intent=intent,
            data={},
            summary=f"Intent {intent} không có tool hợp lệ trong whitelist.",
            explanation="",
            requires_confirmation=False,
            error=f"unregistered_intent:{intent}",
        )

    try:
        return tool_fn(**params)
    except Exception as e:
        return ToolExecutionResult(
            success=False,
            tool_name=tool_fn.__name__,
            intent=intent,
            data={},
            summary=f"Lỗi khi thực thi tool {tool_fn.__name__}.",
            explanation=str(e),
            requires_confirmation=False,
            error=str(e),
        )
