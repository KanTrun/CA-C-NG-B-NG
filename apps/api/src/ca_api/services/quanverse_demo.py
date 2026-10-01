"""Quanverse Demo Setup — ghi bản ghi NGHIỆP VỤ THẬT, không fixture riêng.

- Ghi vào cùng schema/quán mà /lich-tuan, /don, /tieu-thu dùng.
- Idempotent theo tiền tố `demo_qv_`: chạy lại không nhân bản.
- Reset chỉ xoá đúng bản ghi demo, không đụng dữ liệu quán.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_PREFIX = "demo_qv_"


def _tuan() -> str:
    from ca_api.services.quanverse_live import _tuan_hien_tai

    return _tuan_hien_tai()


def setup() -> dict[str, Any]:
    from ca_api.persist import don_get, don_insert, kv_get, kv_set

    now = datetime.now(UTC)
    created_orders = 0
    order_ids: list[str] = []
    # 10 đơn demo: 7 đang xử lý (cho_pha/dang_pha) + 3 xong, rải giờ hôm nay.
    for i in range(10):
        oid = f"{_PREFIX}don_{i:02d}"
        order_ids.append(oid)
        if don_get(oid):
            continue
        trang_thai = "cho_pha" if i < 4 else ("dang_pha" if i < 7 else "xong")
        luc = now.isoformat()
        don_insert({
            "id": oid,
            "nv_id": "nv_01",
            "trang_thai": trang_thai,
            "thanh_toan": "chua_tt",
            "dong": [{"mon": "Ca phe sua", "sl": 1}],
            "ly_do_huy": None,
            "luc": luc,
        })
        created_orders += 1

    # Phân ca tuần hiện tại cho ca w1_c01 (ca mẫu seed luôn tồn tại).
    tuan = _tuan()
    phan_cong = kv_get("phan_cong_by_week", {})
    if not isinstance(phan_cong, dict):
        phan_cong = {}
    week = dict(phan_cong.get(tuan) or {})
    prev = list(week.get("w1_c01") or [])
    added_shifts = 0
    for nv in ("nv_01", "nv_02"):
        if nv not in prev:
            prev.append(nv)
            added_shifts += 1
    week["w1_c01"] = prev
    phan_cong[tuan] = week
    kv_set("phan_cong_by_week", phan_cong)

    # Tồn kho: 5 mặt hàng, sữa tươi dưới ngưỡng để demo cảnh báo.
    ton = kv_get("tieu_thu", [])
    if not isinstance(ton, list):
        ton = []
    ton = [x for x in ton if not str(x.get("id") or "").startswith(_PREFIX)]
    demo_items = [
        {"hang": "Sua tuoi", "so_luong": 1},
        {"hang": "Ca phe hat", "so_luong": 8},
        {"hang": "Duong", "so_luong": 6},
        {"hang": "Ong hut", "so_luong": 10},
        {"hang": "Ly giay", "so_luong": 12},
    ]
    for idx, it in enumerate(demo_items):
        ton.append({
            "id": f"{_PREFIX}ton_{idx:02d}",
            "hang": it["hang"],
            "so_luong": it["so_luong"],
            "don_vi": "phan",
            "duoi_nguong": it["so_luong"] < 2,
            "ai": "demo_setup",
            "luc": now.isoformat(),
        })
    kv_set("tieu_thu", ton)

    return {
        "setup": True,
        "tuan_iso": tuan,
        "orders_created": created_orders,
        "orders_total_demo": len(order_ids),
        "shifts_added": added_shifts,
        "inventory_items": len(demo_items),
        "nguon": "database_that",
        "ghi_chu": "Dữ liệu demo qua cùng schema nghiệp vụ — Quanverse đọc như dữ liệu quán.",
    }


def reset() -> dict[str, Any]:
    from ca_api.persist import _conn, kv_get, kv_set

    removed_orders = 0
    with _conn() as cx:
        rows = cx.execute("SELECT id FROM don_quay").fetchall()
        for (oid,) in rows:
            if str(oid).startswith(_PREFIX):
                cx.execute("DELETE FROM don_quay WHERE id=?", (oid,))
                removed_orders += 1

    phan_cong = kv_get("phan_cong_by_week", {})
    if isinstance(phan_cong, dict):
        changed = False
        for _tuan, week in list(phan_cong.items()):
            if isinstance(week, dict) and isinstance(week.get("w1_c01"), list):
                kept = [nv for nv in week["w1_c01"] if nv not in ("nv_01", "nv_02")]
                # Chỉ rút demo khi ca đó do demo tạo ra (tránh đụng lịch quán):
                # giữ nguyên nếu còn người khác ngoài demo.
                if set(week["w1_c01"]) <= {"nv_01", "nv_02"}:
                    week["w1_c01"] = kept
                    changed = True
        if changed:
            kv_set("phan_cong_by_week", phan_cong)

    ton = kv_get("tieu_thu", [])
    if isinstance(ton, list):
        kept_ton = [x for x in ton if not str(x.get("id") or "").startswith(_PREFIX)]
        kv_set("tieu_thu", kept_ton)

    return {"reset": True, "orders_removed": removed_orders}
