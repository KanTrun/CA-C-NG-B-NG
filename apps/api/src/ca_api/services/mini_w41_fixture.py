"""Fixture ít nhân sự cho tuần W41 — tự kiểm được trong vài phút.

Vì sao tách: QA phàn nàn không biết cách test `/lich-tuan` (19 người, tuần
trống, xếp im). Bộ này cố ý NHỎ: 4 NV có tên rõ + 1 tuần `2026-W41`, seed
phân công tối thiểu để chạy xếp / nhật ký / swap mà không cần fixture quán đầy.

Luồng dùng:
  1. `seed_mini_w41_roster()` — chuẩn bị availability + phân công mẫu + lifecycle nháp
  2. QL sang `?tuan=2026-W41` → «Xếp lịch tự động» (hoặc giữ phân công mẫu)
  3. Đọc panel nhật ký «Ai đổi ca với ai»
  4. Duyệt 1 phiếu đổi ca → nhật ký nguồn `doi_ca` hiện A → B
"""

from __future__ import annotations

from typing import Any

from ca_api.persist import (
    availability_confirmation_upsert,
    init_db,
    kv_mutate,
    kv_set,
    list_users,
    register,
)

MINI_W41_WEEK = "2026-W41"

# 3 tài khoản login sẵn + 1 NV demo (đăng ký nếu thiếu). Không tạo 19 người.
MINI_W41_CORE: tuple[str, ...] = ("nv_01", "nv_02", "nv_03")

_DAYS = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
_SHIFTS = ("Sáng", "Chiều", "Tối")


def _full_availability() -> dict[str, list[str]]:
    return {day: list(_SHIFTS) for day in _DAYS}


def _ensure_fourth_staff() -> str:
    """Đảm bảo có NV thứ 4 — fixture login mặc định chỉ có lan/hung/minh."""
    init_db()
    for u in list_users():
        if str(u.get("username")) == "an_nv":
            return str(u.get("nv_id") or "")
    try:
        # username ≥ 3 ký tự (ràng buộc register); mật khẩu ≥ 8.
        created = register("an_nv", "nhipquan", "An — ca chiều")
        return str(created.get("nv_id") or "")
    except Exception:
        for u in list_users():
            if str(u.get("username")) == "an_nv":
                return str(u.get("nv_id") or "")
    return ""


def seed_mini_w41_roster(*, store_id: str = "quan_01") -> dict[str, Any]:
    """Seed tuần W41 với 4 NV + phân công mẫu + lifecycle nháp.

    Phân công mẫu cố ý nhỏ (vài ca) để swap A→B đọc được ngay, không phụ thuộc
    solver có đủ 10 người/ngày. Khi QL bấm xếp tự động, availability đã sẵn
    cho 4 NV; nếu pool users lớn hơn thì authoritative path vẫn có thể xếp
    rộng hơn — nhật ký vẫn ghi theo tuần W41.
    """
    week = MINI_W41_WEEK
    availability = _full_availability()
    nv4 = _ensure_fourth_staff()
    staff = [*(MINI_W41_CORE), *([nv4] if nv4 else [])]

    for nv_id in staff:
        availability_confirmation_upsert(
            item_id=f"mini-w41-{nv_id}",
            store_id=store_id,
            nv_id=nv_id,
            tuan_iso=week,
            availability=availability,
            status="da_xac_nhan",
            source="mini_w41_fixture",
        )

    # Phân công mẫu: vài ca rõ ràng để swap/journal không cần chờ solver.
    # w1_c01 cần 2 người trong seed — gán nv_01 + nv_02; w1_c02 gán nv_03.
    phan_mau: dict[str, list[str]] = {
        "w1_c01": ["nv_01", "nv_02"],
        "w1_c02": ["nv_03"],
    }
    if nv4:
        phan_mau["w1_c03"] = [nv4]

    def mut_pc(all_weeks: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(all_weeks, dict):
            all_weeks = {}
        all_weeks[week] = dict(phan_mau)
        return all_weeks

    kv_mutate("phan_cong_by_week", mut_pc, {})
    kv_set("phan_cong", dict(phan_mau))

    life = {
        "tuan_iso": week,
        "trang_thai": "nhap",
        "cap_nhat_boi": "mini_w41_fixture",
    }

    def mut_life(all_weeks: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(all_weeks, dict):
            all_weeks = {}
        all_weeks[week] = dict(life)
        return all_weeks

    kv_mutate("lich_tuan_lifecycle_by_week", mut_life, {})
    kv_set("lich_tuan_lifecycle", dict(life))

    # Xoá nhật ký tuần cũ để checklist bắt đầu sạch.
    def mut_log(raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raw = {}
        raw[week] = []
        return raw

    kv_mutate("lich_thay_doi_by_week", mut_log, {})

    return {
        "ok": True,
        "tuan_iso": week,
        "nv_ids": staff,
        "phan_cong": phan_mau,
        "trang_thai": "nhap",
        "huong_dan": [
            f"Mở /lich-tuan?tuan={week}",
            "Bấm «Xếp lịch tự động» (hoặc giữ phân công mẫu)",
            "Đọc panel «Ai đổi ca với ai» (mở sẵn)",
            "Công bố → tạo phiếu đổi ca nv_01↔nv_03 trên w1_c01 → duyệt → thấy A→B nguồn Chợ đổi ca",
        ],
    }


def publish_mini_w41_for_swap() -> dict[str, Any]:
    """Chuyển W41 sang đã công bố để cổng đổi ca cho phép duyệt."""
    week = MINI_W41_WEEK
    life = {
        "tuan_iso": week,
        "trang_thai": "da_cong_bo",
        "cap_nhat_boi": "mini_w41_fixture",
    }

    def mut_life(all_weeks: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(all_weeks, dict):
            all_weeks = {}
        all_weeks[week] = dict(life)
        return all_weeks

    kv_mutate("lich_tuan_lifecycle_by_week", mut_life, {})
    kv_set("lich_tuan_lifecycle", dict(life))
    return {"ok": True, "tuan_iso": week, "trang_thai": "da_cong_bo"}
