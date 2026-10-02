"""Chuẩn hoá sổ tiêu thụ và nạp nốt danh mục sản phẩm cho menu.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-02

Vì sao cần migration này
------------------------
0018 gộp 12 món legacy vào id chuẩn nhưng **không nạp danh mục**, nên production
sau khi chạy chỉ còn khoảng 9 món, trong khi `data/seed/danh-muc.json` có 49.
Nạp danh mục là việc tay (`scripts/seed_danh_muc.py`), deploy không chạy nó.

Ba lỗi người dùng đang nhìn thấy trên `/tieu-thu` và `/quay`:

1. **Sổ tiêu thụ lẫn lộn ba hình dạng.** Seeder cũ ghi
   `{"order_id","status","items"}` — không có `hang`/`so_luong` → UI render ô
   trống. Dòng khác ghi tên MẤT DẤU ("Ca phe hat", "Sua tuoi", "Ly giay") và mã
   legacy ("cafe_g"), nên một nguyên liệu ra 2–3 mặt hàng khác nhau.
2. **Món bán được lẫn món bao bì.** 8 món `nhom="nguyen_lieu"` (Gói cà phê 250g,
   Bịch đá 2kg…) là nguyên liệu bán sỉ, không phải món pha cho khách, nhưng `an=0`
   nên vẫn hiện trên `/quay`.
3. **Món trùng và tên mất dấu còn sót** sau 0018 — `fx_mon_*` và các bản sao của
   món chuẩn chưa được đụng tới.

Nguyên tắc sửa
--------------
- Sửa TẠI CHỖ và chỉ **thêm** — không xoá hàng nào. Món do chủ quán tự thêm
  (id ngoài danh mục, tên có dấu) giữ nguyên mọi trường.
- Chèn món thiếu từ `data/seed/danh-muc.json` theo `id`: có rồi thì bỏ qua, không
  ghi đè giá/tên/công thức của quán.
- Chỉ SỬA tên khi tên hiện tại đúng bằng bản bỏ dấu của tên chuẩn — tức nó là
  "Ca phe den" của món "Cà phê đen". Tên khác nghĩa là chủ quán đã đổi tên, đụng
  vào là bịa lại sự thật.
- Ẩn (`an=1`) theo đúng hai nhánh người dùng đã chốt: (a) danh mục bảo ẩn;
  (b) id khớp `^(fx_)?mon_` (dòng fixture/seed) HOẶC tên trùng bản bỏ dấu của một
  món trong danh mục. **Không** ẩn theo "tên không dấu" chung chung — món chủ quán
  gõ "Tra da" hay tên tiếng Anh sẽ bị ẩn nhầm.
- Bao giờ cũng `an=1`, không bao giờ ép `an=0`: chủ quán ẩn món nào thì để đó.
- Chạy lại nhiều lần vô hại: đã chuẩn hoá rồi thì không còn gì để đổi.

Vì sao đọc file danh mục chứ không chép vào đây
-----------------------------------------------
Chép 49 món vào migration là một bản sao thứ hai của danh mục, và bản sao đó cũ
ngay khi ai đó sửa `danh-muc.json`. File này nằm trong image (`Dockerfile.api`
COPY `data/`) và đường dẫn `parents[4]` đúng cả local lẫn `/app`; thiếu file thì
migration dừng với thông báo rõ ràng thay vì lặng lẽ nạp rỗng.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

#: Mã LEGACY → mã chuẩn. PHẢI giống `ca_api.nguyen_lieu.ALIAS`; test
#: `test_nguyen_lieu.py` khoá hai bên bằng assert để một bên đổi bên kia đỏ ngay.
ALIAS: dict[str, str] = {
    "cafe_g": "ca_phe_hat",
    "sua_ml": "sua_tuoi",
    "dao_lat": "dao",
    "ly_nhua": "ly",
}

#: Tên người gõ tay từng xuất hiện trong sổ, khớp ở dạng đã bỏ dấu.
TEN_BI_DANH: dict[str, str] = {
    "ca phe": "ca_phe_hat",
    "suatuoi": "sua_tuoi",
    "sua": "sua_tuoi",
    "tra da": "tra",
    "tra g": "tra",
    "da vien": "da",
    "ly nhua": "ly",
    "ly giay": "ly",
    "banh kem": "banh",
}

#: `parents[4]` từ `apps/api/alembic/versions/x.py` = repo root (local) hoặc
#: `/app` trong image. Cùng quy ước với `ca_api.nguyen_lieu`.
DANH_MUC = Path(__file__).resolve().parents[4] / "data" / "seed" / "danh-muc.json"

BAK_MENU = "menu_mon_bak_0019"
BAK_KV = "kv_tieu_thu_bak_0019"

_COT_MON = "id, ten, gia, an, bom, hinh_url, nhom"

#: id dòng fixture/seed — không phải món chủ quán tự đặt tên.
_RE_MON_LEGACY = re.compile(r"^(fx_)?mon_")


def _khoa(x: str) -> str:
    """Bỏ dấu + hạ chữ thường, để "Ca phe den" so được với "Cà phê đen"."""
    s = unicodedata.normalize("NFD", str(x or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def _doc_danh_muc() -> dict[str, Any]:
    if not DANH_MUC.exists():
        raise RuntimeError(
            f"thiếu {DANH_MUC} — migration 0019 cần danh mục sản phẩm để nạp menu. "
            "File này phải có trong image (Dockerfile.api COPY data ./data)."
        )
    try:
        raw = json.loads(DANH_MUC.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"không đọc được danh mục {DANH_MUC}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("mon"), list):
        raise RuntimeError(f"{DANH_MUC} thiếu danh sách `mon`")
    return raw


def _chuan_hoa_bom(raw: Any) -> str:
    """Đưa `menu_mon.bom` về khoá chuẩn, cộng định mức khi hai khoá trùng một mã.

    Trả về chuỗi JSON để ghi thẳng vào cột TEXT. Bỏ dòng không đọc được hoặc ≤ 0
    thay vì để `NaN` làm lệch phép tính hao hụt.
    """
    try:
        bom = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, ValueError):
        bom = {}
    if not isinstance(bom, dict):
        bom = {}
    out: dict[str, Any] = {}
    for khoa, gia_tri in bom.items():
        try:
            so = float(gia_tri)
        except (TypeError, ValueError):
            continue
        if so <= 0:
            continue
        ma = ALIAS.get(str(khoa).strip(), str(khoa).strip())
        tong = out.get(ma, 0.0) + so
        out[ma] = int(tong) if float(tong).is_integer() else tong
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def _bang_nguyen_lieu(dm: dict[str, Any]) -> tuple[set[str], dict[str, str]]:
    """`(mã chuẩn, {tên đã bỏ dấu: mã})` từ mảng `nguyen_lieu` của danh mục."""
    ma: set[str] = set()
    ten: dict[str, str] = {}
    for row in dm.get("nguyen_lieu") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("ma") or "").strip()
        if not mid:
            continue
        ma.add(mid)
        ten[_khoa(str(row.get("ten") or ""))] = mid
    return ma, ten


def _chuan_hoa_hang(hang: str, ma_chuan: set[str], bang_ten: dict[str, str]) -> str:
    """Quy `kv.tieu_thu.hang` về mã chuẩn. Không tra được thì giữ nguyên chữ gốc."""
    ma = ALIAS.get(hang, hang)
    if ma in ma_chuan:
        return ma
    if hang in ma_chuan:
        return hang
    do_khoa = _khoa(hang)
    truc = TEN_BI_DANH.get(do_khoa)
    if truc and truc in ma_chuan:
        return truc
    tim = bang_ten.get(do_khoa)
    return tim if tim else hang


def _don_sach(
    rows: list[Any], ma_chuan: set[str], bang_ten: dict[str, str]
) -> tuple[list[Any], int]:
    """Bỏ dòng hỏng, quy `hang` về mã chuẩn. Trả `(danh_sach, số dòng bị bỏ)`."""
    sach: list[Any] = []
    bo = 0
    for row in rows:
        if not isinstance(row, dict):
            bo += 1
            continue
        hang = str(row.get("hang") or "").strip()
        if not hang:
            bo += 1
            continue
        try:
            float(row.get("so_luong"))
        except (TypeError, ValueError):
            bo += 1
            continue
        ma = _chuan_hoa_hang(hang, ma_chuan, bang_ten)
        sach.append({**row, "hang": ma} if ma != hang else row)
    return sach, bo


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 0. Bảng chặn. Chạy trước mọi sửa đổi để `downgrade()` khôi phục được. ──
    if not inspector.has_table(BAK_MENU):
        bind.execute(sa.text(f'CREATE TABLE "{BAK_MENU}" AS SELECT * FROM "menu_mon"'))
    if not inspector.has_table(BAK_KV):
        bind.execute(
            sa.text(f"CREATE TABLE \"{BAK_KV}\" AS SELECT k, v FROM \"kv\" WHERE k = 'tieu_thu'")
        )

    dm = _doc_danh_muc()
    mon_dm = {str(m["id"]): m for m in dm["mon"] if isinstance(m, dict) and m.get("id")}
    ma_chuan, bang_ten = _bang_nguyen_lieu(dm)
    khoa_mon_trong_dm = {_khoa(str(m.get("ten") or "")) for m in mon_dm.values()}

    # ── 1. Sửa từng dòng menu đang có. ──
    for row in bind.execute(sa.text(f"SELECT {_COT_MON} FROM menu_mon")).mappings():
        mid = str(row["id"])
        ten = str(row["ten"] or "")
        nhom = str(row["nhom"] or "")
        hien = int(row["an"] or 0)
        spec = mon_dm.get(mid)

        bom_moi = _chuan_hoa_bom(row["bom"])
        ten_moi = ten
        if spec and _khoa(ten) == _khoa(str(spec.get("ten") or "")):
            ten_moi = str(spec["ten"])
        nhom_moi = nhom or (str(spec.get("nhom") or "") if spec else "")
        if spec:
            # Danh mục bảo ẩn thì ẩn; còn lại GIỮ trạng thái hiện tại — không bao
            # giờ tự bật lại món chủ quán đã ẩn.
            an_moi = 1 if spec.get("an") else hien
        else:
            an_moi = 1 if _la_mon_le(mid, ten_moi, khoa_mon_trong_dm) else hien

        if bom_moi == str(row["bom"] or "{}") and ten_moi == ten and nhom_moi == nhom and an_moi == hien:
            continue
        bind.execute(
            sa.text(
                "UPDATE menu_mon SET ten=:ten, nhom=:nhom, an=:an, bom=:bom WHERE id=:id"
            ),
            {"ten": ten_moi, "nhom": nhom_moi, "an": an_moi, "bom": bom_moi, "id": mid},
        )

    # ── 2. Chèn món trong danh mục chưa có. Chỉ INSERT — không đụng món đã có. ──
    da_co = {str(r[0]) for r in bind.execute(sa.text("SELECT id FROM menu_mon"))}
    for mid, spec in mon_dm.items():
        if mid in da_co:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO menu_mon (id, ten, gia, an, bom, hinh_url, nhom)"
                " VALUES (:id, :ten, :gia, :an, :bom, :hinh_url, :nhom)"
            ),
            {
                "id": mid,
                "ten": str(spec.get("ten") or mid),
                "gia": int(spec.get("gia") or 0),
                "an": 1 if spec.get("an") else 0,
                "bom": _chuan_hoa_bom(json.dumps(spec.get("bom") or {}, ensure_ascii=False)),
                "hinh_url": str(spec.get("hinh_url") or ""),
                "nhom": str(spec.get("nhom") or ""),
            },
        )

    # ── 3. Dọn `kv.tieu_thu`: bỏ dòng hỏng, quy `hang` về mã chuẩn. ──
    row = bind.execute(sa.text("SELECT v FROM kv WHERE k = 'tieu_thu'")).fetchone()
    if row is not None:
        try:
            rows = json.loads(row[0])
        except (TypeError, ValueError):
            rows = None
        if isinstance(rows, list):
            sach, _ = _don_sach(rows, ma_chuan, bang_ten)
            bind.execute(
                sa.text("UPDATE kv SET v = :v WHERE k = 'tieu_thu'"),
                {"v": json.dumps(sach, ensure_ascii=False)},
            )


def _la_mon_le(mid: str, ten: str, khoa_mon_trong_dm: set[str]) -> bool:
    """Món VÔ NGHĨA cần ẩn — đúng hai nhánh người dùng đã chốt.

    Không dùng "tên không dấu" chung chung: chủ quán gõ "Tra da" hay đặt tên
    tiếng Anh là món thật, ẩn nhầm thì quán mất hàng đang bán (và người ta phải
    vào `/menu` mở lại mới thấy).
    """
    if _RE_MON_LEGACY.match(mid):
        return True
    khoa = _khoa(ten)
    return bool(khoa) and khoa in khoa_mon_trong_dm


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(BAK_MENU):
        # `DELETE` + `INSERT` thay vì DROP/rename: giữ nguyên index và ràng buộc
        # đã khai trên bảng gốc, không phụ thuộc thứ tự cột.
        bind.execute(sa.text('DELETE FROM "menu_mon"'))
        bind.execute(sa.text('INSERT INTO "menu_mon" SELECT * FROM "menu_mon_bak_0019"'))
        bind.execute(sa.text('DROP TABLE "menu_mon_bak_0019"'))

    if inspector.has_table(BAK_KV):
        bind.execute(sa.text("DELETE FROM kv WHERE k = 'tieu_thu'"))
        bind.execute(
            sa.text('INSERT INTO kv (k, v) SELECT k, v FROM "kv_tieu_thu_bak_0019"')
        )
        bind.execute(sa.text('DROP TABLE "kv_tieu_thu_bak_0019"'))
