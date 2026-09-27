"""Neutral application adapter for the weekly CP-SAT solver."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from ca_playbook import list_luat
from ca_solver import apply_luat, build_lich_input, solve_cpsat

from ca_api.nhan_vien import list_nhan_vien_ops
from ca_api.persist import kv_get, kv_mutate, kv_set

_ROOT = Path(__file__).resolve().parents[5]

# Ngân sách thời gian cho CP-SAT.
#
# Vì sao không để 60s: `solve_cpsat` dùng HẾT ngân sách để chứng minh phương án
# đã tối ưu (objective = max_debt*1000 + điểm mềm). Đo trên dữ liệu thật của quán
# (25 nhân viên / 70 ca) bằng `scripts/bench_solver_budget.py`:
#
#     ngân sách   thời gian thực   objective   vi phạm
#        2.0s          1.63s        200014        0
#        8.0s          7.64s        200006        0
#       15.0s         14.65s        200002        0
#       60.0s         59.66s        200002        0
#
# Từ 15s trở lên cho ra CÙNG một phương án như 60s (chênh 0, cùng 0 vi phạm).
# 45 giây còn lại không mua thêm gì — chỉ để solver tự chứng minh tối ưu, việc
# không ai đọc. Đổi lại, 60s đẩy tổng thời gian một lượt chat vượt ngưỡng chờ
# của client (60s trong `scripts/e2e_http_copilot.py`), gây `TimeoutError` chập
# chờn: cùng một câu hỏi, lần chạy 59.9s thì lọt, lần chạy 60.1s thì vỡ.
# 15s vừa giữ nguyên chất lượng lịch, vừa chừa biên an toàn gấp ~4 lần.
#
# Đặt qua `CA_SOLVER_TIME_LIMIT_S` (mặc định `_DEFAULT_TIME_LIMIT_S` trong
# `ca_solver.cpsat`) để mọi đường gọi — kể cả copilot — dùng cùng một ngân sách.

_DAYS = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
_SHIFT_FRAMES = {
    "Sáng": ("06:30", "12:00"),
    "Chiều": ("12:00", "17:30"),
    "Tối": ("17:30", "22:30"),
}


def _week_value(key: str, week: str, default: Any) -> Any:
    raw = kv_get(key, None)
    if isinstance(raw, dict) and raw:
        return raw.get(week, default)
    if key.endswith("_by_week"):
        legacy = kv_get(key.removesuffix("_by_week"), None)
        if legacy is not None:
            return legacy
    return default


def _previous_week(week: str) -> str | None:
    try:
        year, number = week.split("-W")
        year_i = int(year)
        number_i = int(number)
        # Clamp số tuần vào phạm vi hợp lệ của năm (1..số tuần thực của năm).
        # Nếu tuần không hợp lệ (vd 2025-W53), dùng tuần cuối hợp lệ của năm.
        max_weeks = date(year_i, 12, 28).isocalendar().week
        number_i = max(1, min(number_i, max_weeks))
        previous = date.fromisocalendar(year_i, number_i, 1).toordinal() - 7
        iso = date.fromordinal(previous).isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except (TypeError, ValueError):
        return None


def _output_path() -> Path:
    return Path(os.environ.get("NHIPQUAN_LICH_TUAN_OUT", _ROOT / "data/out/lich_tuan.json"))


def _current_week() -> str:
    """Tuần đang hiệu lực.

    Fallback cuối dùng tuần ISO HIỆN TẠI — trước đây hardcode `2026-W01` nên
    khi KV trống (quán mới), solver giải SAI tuần (bug QA đợt 4).
    """
    lifecycle = kv_get("lich_tuan_lifecycle", None)
    if isinstance(lifecycle, dict) and lifecycle.get("tuan_iso"):
        return str(lifecycle["tuan_iso"])
    legacy = kv_get("lifecycle", None)
    if isinstance(legacy, dict) and legacy.get("tuan_iso"):
        return str(legacy["tuan_iso"])
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    try:
        start_a_minutes = int(start_a[:2]) * 60 + int(start_a[3:])
        end_a_minutes = int(end_a[:2]) * 60 + int(end_a[3:])
        start_b_minutes = int(start_b[:2]) * 60 + int(start_b[3:])
        end_b_minutes = int(end_b[:2]) * 60 + int(end_b[3:])
        return max(start_a_minutes, start_b_minutes) < min(end_a_minutes, end_b_minutes)
    except (TypeError, ValueError):
        return False


def run_solver(
    tuan_iso: str | None = None,
    *,
    extra_pin: tuple[str, str] | None = None,
    confirmed_availability: dict[str, dict[str, list[str]]] | None = None,
    store_id: str = "quan_01",
    time_limit_s: float | None = None,
) -> dict[str, Any]:
    """Build the authoritative input, solve it, and persist the result.

    This function intentionally has no dependency on an HTTP router. Legacy
    routes may keep a thin compatibility wrapper around this entrypoint.
    """
    input_data = build_lich_input(nhan_vien_ngoai=list_nhan_vien_ops())
    week = tuan_iso or _current_week()

    if confirmed_availability:
        allowed_ids = set(confirmed_availability)
        input_data.nhan_vien_ids = [nv_id for nv_id in input_data.nhan_vien_ids if nv_id in allowed_ids]
        configured_frames = kv_get("khung_gio", {})
        frames = dict(_SHIFT_FRAMES)
        _SHIFT_KEY_MAP = {"Sáng": "sang", "Chiều": "chieu", "Tối": "toi"}
        for shift, frame in frames.items():
            conf_key = _SHIFT_KEY_MAP.get(shift, shift)
            configured = (
                (configured_frames.get(conf_key) or configured_frames.get(shift))
                if isinstance(configured_frames, dict)
                else None
            )
            if isinstance(configured, dict):
                frames[shift] = (str(configured.get("bat_dau") or frame[0]), str(configured.get("ket_thuc") or frame[1]))
        input_data.tkb = {
            nv_id: [
                (day, *frames[shift])
                for day in _DAYS
                for shift in frames
                if shift not in (confirmed_availability.get(nv_id) or {}).get(day, [])
            ]
            for nv_id in input_data.nhan_vien_ids
        }

    configured_frames = kv_get("khung_gio", {})
    if isinstance(configured_frames, dict):
        for meta in cast(dict[str, dict[str, str]], input_data.ca_meta).values():
            configured_frame = configured_frames.get(meta.get("khung", ""))
            if isinstance(configured_frame, dict):
                meta["bat_dau"] = str(configured_frame.get("bat_dau") or meta["bat_dau"])
                meta["ket_thuc"] = str(configured_frame.get("ket_thuc") or meta["ket_thuc"])

    debt = _week_value("fairness_debt_by_week", week, {})
    if isinstance(debt, dict) and debt:
        input_data.debt = debt
    previous_week = _previous_week(week)
    if previous_week:
        previous = _week_value("phan_cong_by_week", previous_week, {})
        if isinstance(previous, dict):
            input_data.phan_cong_tuan_truoc = {str(ca): list(ids) for ca, ids in previous.items() if isinstance(ids, list)}

    stored_by_week = kv_get("tkb_nv_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    stored = stored_by_week.get(week_key, {}) if isinstance(stored_by_week, dict) else {}
    legacy = kv_get("tkb_nv", {})
    if isinstance(legacy, dict):
        stored = dict(stored) if isinstance(stored, dict) else {}
        for nv_id, entry in legacy.items():
            if nv_id not in stored and isinstance(entry, dict) and entry.get("tuan_iso") == week:
                stored[nv_id] = entry
    if isinstance(stored, dict):
        for nv_id, entry in stored.items():
            if not isinstance(entry, dict):
                continue
            blocks = []
            for block in entry.get("khoang_ban") or []:
                if isinstance(block, dict) and block.get("thu") and block.get("start") and block.get("end"):
                    blocks.append((str(block["thu"]), str(block["start"]), str(block["end"])))
            if blocks:
                if confirmed_availability:
                    current = input_data.tkb.setdefault(str(nv_id), [])
                    input_data.tkb[str(nv_id)] = current + [block for block in blocks if block not in current]
                else:
                    input_data.tkb[str(nv_id)] = blocks

    decisions = kv_get("roster_nv_status", {})
    for nv_id, status in (decisions.get(week, {}) if isinstance(decisions, dict) else {}).items():
        if status in {"du_bi", "bo_ca"}:
            input_data.nghi_phep.update((str(nv_id), day) for day in _DAYS)

    inbox_items = kv_get("inbox_rang_buoc", [])
    added_leave: set[tuple[str, str]] = set()
    added_tkb: set[tuple[str, str, str, str]] = set()
    for item in inbox_items if isinstance(inbox_items, list) else []:
        if not isinstance(item, dict) or item.get("trang_thai") != "duyet":
            continue
        effective = cast(dict[str, Any], item.get("hieu_luc")) if isinstance(item.get("hieu_luc"), dict) else {}
        if effective.get("loai") != "rang_buoc_cho_solver":
            continue
        constraint = cast(dict[str, Any], item.get("rang_buoc")) if isinstance(item.get("rang_buoc"), dict) else {}
        if (constraint.get("tuan_id") or effective.get("tuan_id")) not in {None, week}:
            continue
        nv_id = str(item.get("nv_id") or effective.get("nv_id") or "")
        day = str(constraint.get("thu") or effective.get("thu") or "")
        if not nv_id or nv_id == "unknown" or not day:
            continue
        if item.get("y_dinh") == "xin_nghi":
            pair = (nv_id, day)
            if pair not in added_leave:
                added_leave.add(pair)
                input_data.nghi_phep.add(pair)
        elif item.get("y_dinh") in {"cap_nhat_tkb", "bao_tre"}:
            start = str(constraint.get("start") or effective.get("start") or "07:00")
            end = str(constraint.get("end") or effective.get("end") or "12:00")
            key = (nv_id, day, start, end)
            if key not in added_tkb:
                added_tkb.add(key)
                input_data.tkb.setdefault(nv_id, []).append((day, start, end))

    for pin_key, pinned in (_week_value("pins_by_week", week, {}) or {}).items():
        if pinned and "|" in str(pin_key):
            ca_id, nv_id = str(pin_key).split("|", 1)
            if ca_id in input_data.ca_ids and nv_id in input_data.nhan_vien_ids:
                input_data.phan_cong.setdefault(ca_id, [])
                if nv_id not in input_data.phan_cong[ca_id]:
                    input_data.phan_cong[ca_id].append(nv_id)
    if extra_pin:
        ca_id, nv_id = extra_pin
        input_data.phan_cong.setdefault(ca_id, [])
        if nv_id not in input_data.phan_cong[ca_id]:
            input_data.phan_cong[ca_id].append(nv_id)

    input_data, applied = apply_luat(input_data, list_luat())
    result = solve_cpsat(input_data, time_limit_s=time_limit_s)
    gaps: list[str] = []
    if not result.ok or "INFEASIBLE" in result.status:
        for ca_id in input_data.ca_ids:
            meta = input_data.ca_meta.get(ca_id, {})
            required = input_data.so_nguoi_toi_thieu.get(ca_id, 1)
            shift_day = str(meta.get("thu") or "")
            shift_start = str(meta.get("bat_dau") or "07:00")
            shift_end = str(meta.get("ket_thuc") or "12:00")
            available = sum(
                1
                for nv_id in input_data.nhan_vien_ids
                if (nv_id, shift_day) not in input_data.nghi_phep
                and not any(
                    block_day == shift_day and _overlaps(shift_start, shift_end, block_start, block_end)
                    for block_day, block_start, block_end in input_data.tkb.get(nv_id, [])
                )
            )
            if available < required:
                gaps.append(f"Ca {ca_id} ({shift_day} {shift_start}-{shift_end}) cần tối thiểu {required} người nhưng chỉ còn {available} nhân viên khả dụng do ràng buộc nghỉ phép/TKB.")

    slots = {(str(meta.get("thu") or ""), str(meta.get("khung") or "")) for meta in input_data.ca_meta.values() if meta.get("thu") and meta.get("khung")}
    filled = {(str(input_data.ca_meta.get(ca_id, {}).get("thu") or ""), str(input_data.ca_meta.get(ca_id, {}).get("khung") or "")) for ca_id, ids in result.phan_cong.items() if ids}
    payload = {"nguon": "quan", "adr": "ADR-012", "tuan_iso": week, "status": result.status, "ok": result.ok, "elapsed_s": round(result.elapsed_s, 3), "objective": result.objective, "violations": result.violations, "phan_cong": result.phan_cong, "debt_after": result.debt_after, "luat_ap_dung": applied, "danh_sach_xung_dot": gaps, "tong_so_o_ca": len(slots), "so_o_ca_da_xep": len(filled & slots)}
    payload["kiem_tra"] = {
        "hard": {"passed": result.ok and not result.violations, "gates": ["C01", "C02", "C03", "C04", "C05", "C06"], "violations": result.violations},
        "vf": {
            "applies_to_solver": False,
            "message": "VF kiểm dữ liệu do agent trích xuất và lời giải thích; CP-SAT được hậu kiểm bằng C01–C06.",
            "gates": ["VF-SCHEMA", "VF-TRACE", "VF-CONF", "VF-CONFLICT", "VF-NUM", "VF-RULE"],
        },
        "coverage": {"passed": len(filled & slots) == len(slots), "filled": len(filled & slots), "total": len(slots)},
    }
    output = _output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.ok:
        # Ghi nhật ký thay đổi TRƯỚC khi ghi đè `phan_cong_by_week`. Đây là điểm
        # chốt DUY NHẤT mọi lần xếp lịch đi qua (xếp tự động, xếp lại sau TKB,
        # và các đường gọi solver khác), nên ghi ở đây thì mọi nguồn đều có vết —
        # không phải nhớ thêm ở từng router. Bọc try để nhật ký hỏng KHÔNG được
        # làm hỏng việc xếp lịch.
        try:
            _ghi_nhat_ky_thay_doi(week, result.phan_cong, input_data.ca_meta)
        except Exception:
            pass
        _week_store("phan_cong_by_week", week, result.phan_cong)
        _week_store("lich_tuan_results_by_week", week, payload)
        _week_store("fairness_debt_by_week", week, result.debt_after)
        kv_set("phan_cong", result.phan_cong)
    return {"status": result.status, "ok": result.ok, "best_effort": result.ok, "luat_ap_dung": applied, "violations": len(result.violations), "danh_sach_xung_dot": gaps, "tong_so_o_ca": len(slots), "so_o_ca_da_xep": len(filled & slots), "kiem_tra": payload["kiem_tra"], "phan_cong": result.phan_cong, "ca_meta": input_data.ca_meta}


NHAT_KY_TOI_DA = 20


def _ghi_nhat_ky_thay_doi(week: str, sau: dict[str, list[str]], ca_meta: Any) -> None:
    """Lưu diff trước/sau của MỘT lần xếp lịch vào kv `lich_thay_doi_by_week`.

    Giữ tối đa `NHAT_KY_TOI_DA` bản gần nhất mỗi tuần: nhật ký là để ĐỌC LẠI
    ("ai đổi ca với ai lúc nào"), không phải kho lịch sử vô hạn. Không giới hạn
    thì mỗi lần bấm xếp lịch lại nối thêm một khối vào một giá trị kv duy nhất —
    giá trị đó phình theo thời gian và mọi lần đọc đều phải parse toàn bộ.
    """
    from ca_api.services.schedule_diff import so_sanh_phan_cong, tom_tat_thay_doi

    truoc_doc = kv_get("phan_cong_by_week", {})
    truoc = truoc_doc.get(week, {}) if isinstance(truoc_doc, dict) else {}
    if not isinstance(truoc, dict):
        truoc = {}

    diff = so_sanh_phan_cong(truoc, sau, ca_meta=ca_meta if isinstance(ca_meta, dict) else {})
    if (
        not diff["them"]
        and not diff["bot"]
        and not diff["hoan_doi"]
        and not diff["doi_giua_hai_ca"]
    ):
        # Không đổi gì thì không ghi — nhật ký toàn dòng "không đổi" là nhiễu.
        return

    ban_ghi = {
        "luc": datetime.now(UTC).isoformat(),
        "nguon": "xep_tu_dong",
        "tuan_iso": week,
        "diff": diff,
        "tom_tat": tom_tat_thay_doi(diff),
    }

    def mutate(raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raw = {}
        items = raw.get(week)
        if not isinstance(items, list):
            items = []
        items = [*items, ban_ghi][-NHAT_KY_TOI_DA:]
        raw[week] = items
        return raw

    kv_mutate("lich_thay_doi_by_week", mutate, {})



def _week_store(key: str, week: str, value: Any) -> None:
    def mutate(raw: dict[str, Any]) -> dict[str, Any]:
        raw[week] = value
        return raw

    kv_mutate(key, mutate, {})