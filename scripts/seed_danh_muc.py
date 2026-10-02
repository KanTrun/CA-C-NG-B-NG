#!/usr/bin/env python3
"""Nạp danh mục sản phẩm chuẩn vào menu của quán.

Đọc `data/seed/danh-muc.json` và upsert `menu_mon` theo `id`.

Vì sao cần script này
---------------------
`persist._MENU_MAC_DINH` chỉ có 4 món và chỉ được seed khi operator bật
`NHIPQUAN_SEED_DEMO`. Quán mới mở vì vậy không có sản phẩm, không có nước đóng
chai, không có nguyên liệu — trong khi mọi bảng hao hụt đều cần công thức món để
tính vế "lý thuyết".

TẤT ĐỊNH và IDEMPOTENT
----------------------
Upsert theo `id`: chạy bao nhiêu lần cũng ra cùng một menu. Món do quán tự thêm
(id không có trong danh mục) **không bị chạm**, và món quán đã sửa (giá, công
thức) theo id có trong danh mục thì bị ghi đè theo danh mục — đó là chủ ý: danh
mục là nguồn chuẩn, muốn giữ bản sửa thì đổi id.

Dùng:
    python scripts/seed_danh_muc.py
    python scripts/seed_danh_muc.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DANH_MUC = ROOT / "data" / "seed" / "danh-muc.json"

for _p in (ROOT / "apps" / "api" / "src",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def doc_danh_muc(path: Path | None = None) -> dict[str, Any]:
    p = path or DANH_MUC
    if not p.exists():
        raise SystemExit(f"thiếu {p}")
    raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    mon = raw.get("mon")
    if not isinstance(mon, list) or not mon:
        raise SystemExit(f"{p} không có danh sách `mon`")
    return raw


def kiem_tra(danh_muc: dict[str, Any]) -> list[str]:
    """Kiểm cấu trúc trước khi ghi. Trả danh sách lỗi (rỗng = hợp lệ)."""
    loi: list[str] = []
    mon = danh_muc.get("mon") or []
    nhom_hop_le = {n["ma"] for n in danh_muc.get("nhom") or [] if isinstance(n, dict)}

    dem_id: Counter[str] = Counter()
    for i, m in enumerate(mon):
        if not isinstance(m, dict):
            loi.append(f"món #{i} không phải object")
            continue
        mid = str(m.get("id") or "").strip()
        if not mid:
            loi.append(f"món #{i} thiếu id")
            continue
        dem_id[mid] += 1
        if not str(m.get("ten") or "").strip():
            loi.append(f"{mid}: thiếu tên")
        gia = m.get("gia")
        if not isinstance(gia, int) or gia < 0:
            loi.append(f"{mid}: giá phải là số nguyên ≥ 0")
        nhom = str(m.get("nhom") or "")
        if nhom_hop_le and nhom not in nhom_hop_le:
            loi.append(f"{mid}: nhóm `{nhom}` không có trong danh sách nhóm")
        bom = m.get("bom")
        if not isinstance(bom, dict) or not bom:
            loi.append(f"{mid}: thiếu công thức `bom` — không có định mức thì không tính được hao hụt")
            continue
        for nl, dinh_muc in bom.items():
            if not isinstance(dinh_muc, (int, float)) or dinh_muc <= 0:
                loi.append(f"{mid}: định mức `{nl}` phải là số > 0")

    for mid, n in dem_id.items():
        if n > 1:
            loi.append(f"id trùng {n} lần: {mid}")
    return loi


def nap(danh_muc: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    from ca_api.persist import menu_list, menu_upsert

    truoc = {str(m.get("id")) for m in menu_list(gom_an=True)}
    mon = danh_muc.get("mon") or []
    moi_them: list[str] = []
    cap_nhat: list[str] = []

    for m in mon:
        mid = str(m["id"]).strip()
        item = {
            "id": mid,
            "ten": str(m["ten"]).strip(),
            "gia": int(m["gia"]),
            "an": bool(m.get("an", False)),
            # `nhom` PHẢI gửi kèm: thiếu thì `menu_upsert` ghi chuỗi rỗng, 49 món
            # mất nhóm và rơi vào `_nhom_suy_tu_bom` đoán — món bao bì thành "Cà
            # phê", "Combo sáng" thành "Cà phê" thay vì "Đồ ăn".
            "nhom": str(m.get("nhom") or "").strip(),
            "bom": {str(k): float(v) for k, v in m["bom"].items()},
        }
        if mid in truoc:
            cap_nhat.append(mid)
        else:
            moi_them.append(mid)
        if not dry_run:
            menu_upsert(item)

    sau = {str(m.get("id")) for m in menu_list(gom_an=True)} if not dry_run else truoc | {str(m["id"]) for m in mon}
    ngoai_danh_muc = sorted(sau - {str(m["id"]) for m in mon})
    nhom_dem = Counter(str(m.get("nhom") or "khac") for m in mon)

    return {
        "tong": len(mon),
        "moi_them": len(moi_them),
        "cap_nhat": len(cap_nhat),
        "ngoai_danh_muc": ngoai_danh_muc,
        "theo_nhom": dict(nhom_dem),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Nạp danh mục sản phẩm chuẩn vào menu quán.")
    ap.add_argument("--dry-run", action="store_true", help="kiểm và in kế hoạch, không ghi")
    ap.add_argument("--file", type=Path, default=None, help="đường dẫn danh mục khác")
    args = ap.parse_args()

    danh_muc = doc_danh_muc(args.file)
    loi = kiem_tra(danh_muc)
    if loi:
        print("Danh mục KHÔNG hợp lệ:")
        for x in loi:
            print(f"  - {x}")
        return 1

    kq = nap(danh_muc, dry_run=args.dry_run)
    if args.dry_run:
        print("[dry-run] không ghi gì cả.")
    print(f"Danh mục: {kq['tong']} món")
    print(f"  thêm mới : {kq['moi_them']}")
    print(f"  cập nhật : {kq['cap_nhat']}")
    print("  theo nhóm: " + ", ".join(f"{k}={v}" for k, v in sorted(kq["theo_nhom"].items())))
    if kq["ngoai_danh_muc"]:
        print(f"  giữ nguyên {len(kq['ngoai_danh_muc'])} món ngoài danh mục: {', '.join(kq['ngoai_danh_muc'][:8])}")
    print("Xong. Món có công thức ⇒ tính được vế lý thuyết của hao hụt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
