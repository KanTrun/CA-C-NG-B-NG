#!/usr/bin/env python3
"""Dọn món trùng tên và nạp danh mục chuẩn vào menu quán.

Vì sao cần script này
---------------------
`data/quan.db` bị lẫn hai nguồn món không thuộc danh mục chuẩn:

1. 8 món `fx_mon_*` — dữ liệu mô phỏng của fixture kiểm thử
   (`data/fixtures/professional/pos.json`, nạp bởi
   `scripts/seed_professional_fixture.py`). Tên các món này bị mất dấu
   ("Bac xiu", "Ca phe den", "Tra dao cam sa"…) và **trùng ý niệm** với món
   thật, có món lệch cả giá.

2. 4 món `mon_*` (`mon_den`, `mon_sua`, `mon_tra`, `mon_da`) — bản seed thô của
   `persist._MENU_MAC_DINH`, không có `nhom` và không có công thức `bom`.

Hệ quả trên `/quay`: hai "Bạc xỉu" khác giá cạnh nhau, cộng loạt món không dấu
nằm lẫn món thật. Cả 12 id đều KHÔNG có trong `data/seed/danh-muc.json`.

Script làm hai việc, theo đúng thứ tự
-------------------------------------
1. XOÁ các id chỉ định (`--xoa`, hoặc nhóm mặc định `fx_*` + 4 món `mon_*`).
2. NẠP danh mục chuẩn từ `data/seed/danh-muc.json` (49 món) qua `menu_upsert`,
   giữ nguyên `nhom` và `bom` — điều mà `persist._seed_menu_neu_trong` bỏ qua.

AN TOÀN
-------
- Mặc định `--dry-run`: chỉ in kế hoạch, KHÔNG ghi. Muốn ghi phải `--apply`.
- `--apply` tự sao lưu DB vào `data/backups/quan-pre-dedup-<mốc>.db` trước khi
  chạm vào bất cứ dòng nào.
- Xoá theo DANH SÁCH ID TƯỜNG MINH, không dùng `LIKE 'fx_%'` trần: một món thật
  do quán tự đặt id bắt đầu bằng `fx_` sẽ không bị xoá oan.

Dùng:
    python scripts/don_menu_trung_ten.py                 # xem kế hoạch
    python scripts/don_menu_trung_ten.py --apply         # ghi thật (có backup)
    python scripts/don_menu_trung_ten.py --apply --xoa id1,id2   # id khác
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
DANH_MUC = ROOT / "data" / "seed" / "danh-muc.json"

for _p in (ROOT / "apps" / "api" / "src",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# 8 món fixture (`fx_mon_*`) + 4 món seed thô (`mon_*`). Kèm lý do để lần sau
# đọc lại biết vì sao đúng những id này.
XOA_MAC_DINH: tuple[str, ...] = (
    # ── fixture mô phỏng: tên mất dấu, trùng món thật ──
    "fx_mon_ca_phe_den",
    "fx_mon_bac_xiu",
    "fx_mon_tra_dao",
    "fx_mon_matcha",
    "fx_mon_croissant",
    "fx_mon_nuoc_loc",
    "fx_mon_coldbrew",
    "fx_mon_combo",
    # ── seed thô `_MENU_MAC_DINH`: không nhóm, không công thức ──
    "mon_den",
    "mon_sua",
    "mon_tra",
    "mon_da",
)


def _db_path() -> Path:
    """Đường dẫn DB thật, đọc QUA persist để tôn trọng `NHIPQUAN_DB`."""
    from ca_api.persist import db_path

    return db_path()


def doc_danh_muc(path: Path | None = None) -> dict[str, Any]:
    p = path or DANH_MUC
    if not p.exists():
        raise SystemExit(f"thiếu danh mục {p}")
    raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw.get("mon"), list) or not raw["mon"]:
        raise SystemExit(f"{p} không có danh sách `mon`")
    return raw


def liet_ke_hien_tai(p: Path) -> list[tuple[str, str]]:
    """(id, ten) của mọi món đang có, đọc read-only."""
    uri = f"file:{p.as_posix()}?mode=ro"
    cx = sqlite3.connect(uri, uri=True)
    try:
        rows = cx.execute("SELECT id, ten FROM menu_mon ORDER BY ten").fetchall()
    finally:
        cx.close()
    return [(str(r[0]), str(r[1])) for r in rows]


def sao_luu(p: Path) -> Path:
    thu_muc = ROOT / "data" / "backups"
    thu_muc.mkdir(parents=True, exist_ok=True)
    moc = datetime.now().strftime("%y%m%d-%H%M%S")
    dich = thu_muc / f"{p.stem}-pre-dedup-{moc}{p.suffix}"
    shutil.copy2(p, dich)
    return dich


def xoa_mon(ids: list[str]) -> int:
    """Xoá theo id tường minh. Trả số dòng thật sự bị xoá."""
    if not ids:
        return 0
    from ca_api.persist import _conn, init_db

    init_db()
    cho = ",".join("?" for _ in ids)
    with _conn() as cx:
        cur = cx.execute(f"DELETE FROM menu_mon WHERE id IN ({cho})", ids)
        return int(cur.rowcount or 0)


def nap_danh_muc(danh_muc: dict[str, Any]) -> tuple[int, int]:
    """Nạp danh mục chuẩn. Trả (thêm mới, cập nhật)."""
    from ca_api.persist import menu_list, menu_upsert

    truoc = {str(m.get("id")) for m in menu_list(gom_an=True)}
    them = cap_nhat = 0
    for m in danh_muc["mon"]:
        mid = str(m["id"]).strip()
        item = {
            "id": mid,
            "ten": str(m["ten"]).strip(),
            "gia": int(m["gia"]),
            "an": bool(m.get("an", False)),
            "bom": {str(k): float(v) for k, v in m["bom"].items()},
            "nhom": str(m.get("nhom") or "").strip(),
        }
        if mid in truoc:
            cap_nhat += 1
        else:
            them += 1
        menu_upsert(item)
    return them, cap_nhat


def main() -> int:
    ap = argparse.ArgumentParser(description="Dọn món trùng tên, nạp danh mục chuẩn.")
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chỉ xem kế hoạch)")
    ap.add_argument(
        "--xoa",
        default="",
        help="danh sách id cần xoá, cách nhau dấu phẩy (mặc định: nhóm fx_* + mon_*)",
    )
    ap.add_argument("--file", type=Path, default=None, help="đường dẫn danh mục khác")
    args = ap.parse_args()

    p = _db_path()
    if not p.exists():
        raise SystemExit(f"không thấy DB ở {p}")

    danh_muc = doc_danh_muc(args.file)
    hien_tai = liet_ke_hien_tai(p)
    ten_hien_tai = {i: t for i, t in hien_tai}

    if args.xoa:
        can_xoa = [x.strip() for x in args.xoa.split(",") if x.strip()]
    else:
        can_xoa = list(XOA_MAC_DINH)

    co_that = [i for i in can_xoa if i in ten_hien_tai]
    khong_co = [i for i in can_xoa if i not in ten_hien_tai]

    print(f"DB: {p}")
    print(f"Hiện có {len(hien_tai)} món · danh mục có {len(danh_muc['mon'])} món")
    print(f"\nSẽ XOÁ {len(co_that)} món:")
    for i in co_that:
        print(f"  - {i}  {ten_hien_tai[i]!r}")
    if khong_co:
        print(f"(bỏ qua {len(khong_co)} id không tồn tại: {', '.join(khong_co)})")

    con_lai = {i for i, _ in hien_tai} - set(co_that)
    them = [str(m["id"]) for m in danh_muc["mon"] if str(m["id"]) not in con_lai]
    print(f"\nSẽ NẠP {len(danh_muc['mon'])} món danh mục ({len(them)} món mới thêm)")

    if not args.apply:
        print("\n[DRY-RUN] chưa ghi gì. Thêm --apply để thực thi.")
        return 0

    ban_sao = sao_luu(p)
    print(f"\nBackup: {ban_sao.relative_to(ROOT).as_posix()}")

    da_xoa = xoa_mon(co_that)
    them_moi, cap_nhat = nap_danh_muc(danh_muc)

    sau = liet_ke_hien_tai(p)
    print(f"\nĐã xoá {da_xoa} món bằng id tường minh.")
    print(f"Đã nạp danh mục: {them_moi} thêm mới · {cap_nhat} cập nhật.")
    print(f"Menu sau khi dọn: {len(sau)} món")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
