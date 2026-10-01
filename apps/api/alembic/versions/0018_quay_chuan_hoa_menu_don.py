"""Chuẩn hoá menu quầy và sửa đơn hỏng (tên mất dấu, món trùng, dong sai shape).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-01

Vì sao cần migration này
------------------------
Production chạy PostgreSQL và chỉ đi qua `alembic upgrade head`; script dọn menu
(`scripts/don_menu_trung_ten.py`) chỉ chạy tay trên SQLite local nên production
vẫn giữ nguyên menu 12 món legacy. Ba hậu quả nhìn thấy ngay trên `/quay`:

1. TÊN MẤT DẤU. `fx_mon_*` đến từ fixture kiểm thử (`data/fixtures/professional/
   pos.json`): "Ca phe den", "Combo sang", "Matcha sua", "Tra dao cam sa"…
2. MÓN TRÙNG Ý NIỆM khác giá: `mon_den` "Cà phê đen" 25.000 cạnh `fx_mon_ca_phe_den`
   "Ca phe den" 29.000; `mon_da` "Bạc xỉu" 32.000 cạnh `fx_mon_bac_xiu` 39.000.
3. NHÓM SAI. Món không khai `nhom` được `_nhom_suy_tu_bom` đoán từ BOM và default
   là "tra" (`pos.py`), nên "Combo sang" (đồ ăn) rơi vào Cà phê còn "Bac xiu"
   (cà phê) rơi vào Trà & trà sữa.

Riêng `don_quay` còn bị `quanverse_demo.setup()` ghi sai hình dạng: `thanh_toan`
nhận `"chua_tt"` (mã thật là `chua_thu`) và `dong` ghi `[{"mon":..,"sl":..}]` thay
vì `{mon_id,ten,so_luong,gia}`. Hậu quả trên UI: phiếu pha chế TRỐNG chỉ còn dấu
"×", và mọi đơn demo hiện "Chưa rõ thanh toán".

Nguyên tắc sửa
--------------
- Sửa TẠI CHỖ, không nạp lại danh mục: món do chủ quán tự thêm vẫn còn nguyên.
- Chỉ gộp món khi id nguồn là id legacy biết chắc — KHÔNG suy từ tên, vì tên mới
  là thứ đang hỏng. Bảng `GOP_MON` liệt kê tường minh.
- `gia` là thứ của quán: giữ giá đang có (món đích có sẵn → giữ giá món đích;
  món đích phải tạo mới → lấy giá món nguồn đầu tiên, giá danh mục chỉ dự phòng).
  `don_quay.dong` lưu snapshot `gia`/`so_luong` nên tổng tiền lịch sử KHÔNG đổi.
- `ten`/`nhom`/`bom`/`hinh_url` lấy theo danh mục chuẩn — đây mới là phần hỏng.
- Chạy lại nhiều lần vô hại: đã chuẩn hoá rồi thì không còn dòng nào khớp.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# ── Danh mục chuẩn cho đúng 9 món mà menu legacy chạm tới ──
# `bom` khai theo `data/seed/danh-muc.json`; món nguồn có BOM thật thì BOM nguồn
# thắng (giữ định mức hao hụt của quán).
CATALOG: dict[str, dict[str, Any]] = {
    "ca_phe_den": {
        "ten": "Cà phê đen",
        "nhom": "ca_phe",
        "gia": 25000,
        "bom": {"ca_phe_hat": 18, "duong": 5, "da": 120, "ly": 1},
    },
    "ca_phe_sua": {
        "ten": "Cà phê sữa",
        "nhom": "ca_phe",
        "gia": 30000,
        "bom": {"ca_phe_hat": 16, "sua_dac": 20, "da": 120, "ly": 1},
    },
    "bac_xiu": {
        "ten": "Bạc xỉu",
        "nhom": "ca_phe",
        "gia": 32000,
        "bom": {"ca_phe_hat": 12, "sua_tuoi": 80, "da": 100, "ly": 1},
    },
    "tra_dao": {
        "ten": "Trà đào",
        "nhom": "tra",
        "gia": 35000,
        "bom": {"tra": 8, "dao": 100, "duong": 20, "da": 150, "ly": 1},
    },
    "tra_sua_matcha": {
        "ten": "Trà sữa matcha",
        "nhom": "tra",
        "gia": 45000,
        "bom": {"matcha": 5, "sua_tuoi": 120, "duong": 20, "da": 100, "ly": 1},
    },
    "combo_sang": {
        "ten": "Combo sáng",
        "nhom": "banh",
        "gia": 59000,
        "bom": {"ca_phe_hat": 14, "sua_tuoi": 100, "banh": 1, "ly": 1},
    },
    "croissant": {
        "ten": "Croissant bơ",
        "nhom": "banh",
        "gia": 35000,
        "bom": {"banh": 1},
    },
    "cold_brew": {
        "ten": "Cold brew",
        "nhom": "ca_phe",
        "gia": 49000,
        "bom": {"ca_phe_hat": 22, "da": 130, "ly": 1},
    },
    "nuoc_suoi": {
        "ten": "Nước suối chai",
        "nhom": "nuoc_dong_chai",
        "gia": 12000,
        "bom": {"nuoc_dong_chai": 1},
    },
}

# id nguồn → id đích, THỨ TỰ CÓ Ý NGHĨA: phần tử đầu là món quyết định giá và BOM
# khi phải tạo mới món đích. Đặt món seed thô (`mon_*`) trước vì đó là món quán
# thật sự bán, còn `fx_mon_*` là fixture sinh cho test.
GOP_MON: dict[str, list[str]] = {
    "ca_phe_den": ["mon_den", "fx_mon_ca_phe_den"],
    "bac_xiu": ["mon_da", "fx_mon_bac_xiu"],
    "ca_phe_sua": ["mon_sua"],
    "tra_dao": ["mon_tra", "fx_mon_tra_dao"],
    "tra_sua_matcha": ["fx_mon_matcha"],
    "combo_sang": ["fx_mon_combo"],
    "croissant": ["fx_mon_croissant"],
    "cold_brew": ["fx_mon_coldbrew"],
    "nuoc_suoi": ["fx_mon_nuoc_loc"],
}

# Mã `thanh_toan` hợp lệ theo `DonQuay` trong contracts. Mọi thứ ngoài danh sách
# này (vd "chua_tt" do seeder cũ ghi) đều hỏng.
THANH_TOAN_HOP_LE = ("tien_mat", "da_ck", "chua_thu")

# `mon_id` đặt cho dòng đơn hỏng không tra được món. `menu_get()` trả None cho id
# này nên `_ghi_tieu_thu_uoc_luang` bỏ qua — hơn là KeyError làm 500.
MON_KHONG_XAC_DINH = "mon_unknown"

BAK_MENU = "menu_mon_bak_0018"
BAK_DON = "don_quay_bak_0018"

_COT_MON = "id, ten, gia, an, bom, hinh_url, nhom"


def _khoa_don(x: str) -> str:
    """Bỏ dấu + hạ chữ thường, để khớp tên mất dấu với tên chuẩn."""
    s = unicodedata.normalize("NFD", x.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _nap_json(raw: Any) -> list[dict[str, Any]]:
    """Đọc `don_quay.dong` — cột TEXT nên có thể là chuỗi JSON lẫn list sẵn."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    try:
        val = json.loads(str(raw or ""))
    except (TypeError, ValueError):
        return []
    return [x for x in val if isinstance(x, dict)] if isinstance(val, list) else []


def _dung_dong(
    dong: list[dict[str, Any]],
    remap: dict[str, str],
    menu: dict[str, dict[str, Any]],
    *,
    chua_quet_lai_ten: bool,
) -> list[dict[str, Any]]:
    """Đưa một dòng đơn về đúng shape `DongDon` = {mon_id, ten, so_luong, gia}.

    `chua_quet_lai_ten=True` cho đơn CÒN LÀM (chờ pha / đang pha): tên món lấy
    từ menu sau khi chuẩn hoá để nhân viên pha đọc đúng "Cà phê đen" thay vì
    "Ca phe den". Đơn đã xong/huỷ giữ nguyên tên ghi lúc bán — đó là lịch sử,
    sửa nó là bịa lại sự thật.
    """
    out: list[dict[str, Any]] = []
    for line in dong:
        ten = str(line.get("ten") or line.get("mon") or "").strip()
        mon_id = str(line.get("mon_id") or "").strip()
        if mon_id:
            mon_id = remap.get(mon_id, mon_id)
        # Dòng hỏng của seeder cũ chỉ có `mon` + `sl` → tra món qua tên đã bỏ dấu.
        if not mon_id and ten:
            for mid, mon in menu.items():
                if _khoa_don(str(mon["ten"])) == _khoa_don(ten):
                    mon_id = mid
                    break
        if not mon_id:
            mon_id = MON_KHONG_XAC_DINH
        mon = menu.get(mon_id)

        try:
            so_luong = int(line.get("so_luong", line.get("sl", 1)) or 1)
        except (TypeError, ValueError):
            so_luong = 1
        gia = line.get("gia")
        try:
            gia = int(gia) if gia is not None else 0
        except (TypeError, ValueError):
            gia = 0
        if gia <= 0 and mon:
            gia = int(mon["gia"] or 0)

        if chua_quet_lai_ten and mon:
            ten = str(mon["ten"])
        out.append(
            {
                "mon_id": mon_id,
                # Đơn đã kết thúc giữ tên ghi lúc bán; còn lại thì lấy tên menu,
                # hỏng cả hai thì nói thẳng là không rõ thay vì để trống — để
                # trống chính là lỗi nhân viên pha nhìn thấy (bug QA đợt 8).
                "ten": ten or "Món không rõ tên",
                "so_luong": max(1, so_luong),
                "gia": max(0, gia),
            }
        )
    return out


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 0. Bảng chặn. Lớp thứ hai sau `pg_dump` của workflow deploy: giữ nguyên
    #    trạng để `downgrade()` khôi phục được kể cả khi chạy sai.
    for ten_bak, ten_bang in ((BAK_MENU, "menu_mon"), (BAK_DON, "don_quay")):
        if not inspector.has_table(ten_bak):
            bind.execute(sa.text(f'CREATE TABLE "{ten_bak}" AS SELECT * FROM "{ten_bang}"'))

    # ── 1. Đọc menu trước, dùng làm từ điển dựng lại dòng đơn hỏng. ──
    menu = {
        str(r["id"]): dict(r)
        for r in bind.execute(sa.text(f"SELECT {_COT_MON} FROM menu_mon")).mappings()
    }

    # ── 2. Gộp món legacy vào id chuẩn. ──
    remap: dict[str, str] = {}
    for dich, nguon_list in GOP_MON.items():
        spec = CATALOG[dich]
        nguon = [mid for mid in nguon_list if mid in menu]
        if not nguon:
            # Đã chuẩn hoá từ lần chạy trước (hoặc menu vốn đã sạch) → không đụng
            # giá/tên của món đích, chỉ chữa `nhom` còn trống.
            if dich in menu and not str(menu[dich].get("nhom") or "").strip():
                bind.execute(
                    sa.text("UPDATE menu_mon SET nhom=:nhom, ten=:ten WHERE id=:id"),
                    {"nhom": spec["nhom"], "ten": spec["ten"], "id": dich},
                )
            continue

        if dich in menu:
            # Món đích đã có sẵn (chủ quán tự thêm, hoặc đã nạp danh mục) → giữ
            # nguyên giá của nó, chỉ gom đơn về và chữa `nhom` còn trống.
            gia = int(menu[dich]["gia"] or 0)
            bom = str(menu[dich].get("bom") or "")
            if not str(menu[dich].get("nhom") or "").strip():
                bind.execute(
                    sa.text("UPDATE menu_mon SET nhom=:nhom WHERE id=:id"),
                    {"nhom": spec["nhom"], "id": dich},
                )
        else:
            gia = 0
            bom = ""

        for mid in nguon:
            gia = gia or int(menu[mid]["gia"] or 0)
            bom = bom or str(menu[mid].get("bom") or "")
            remap[mid] = dich

        gia = gia or int(spec["gia"])
        bom = bom or json.dumps(spec["bom"], ensure_ascii=False)
        hinh = next(
            (str(menu[m].get("hinh_url") or "") for m in nguon if menu[m].get("hinh_url")),
            "",
        )

        if dich in menu:
            # Giữ `hinh_url` của món đích nếu đã có, không ghi đè ảnh đang dùng.
            hinh = str(menu[dich].get("hinh_url") or "") or hinh
            bind.execute(
                sa.text("UPDATE menu_mon SET bom=:bom, hinh_url=:hinh WHERE id=:id"),
                {"bom": bom, "hinh": hinh, "id": dich},
            )
            menu[dich].update(bom=bom, hinh_url=hinh)
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO menu_mon (id, ten, gia, an, bom, hinh_url, nhom)"
                    " VALUES (:id, :ten, :gia, 0, :bom, :hinh_url, :nhom)"
                ),
                {
                    "id": dich,
                    "ten": spec["ten"],
                    "gia": gia,
                    "bom": bom,
                    "hinh_url": hinh,
                    "nhom": spec["nhom"],
                },
            )
            menu[dich] = {
                "id": dich,
                "ten": spec["ten"],
                "gia": gia,
                "an": 0,
                "bom": bom,
                "hinh_url": hinh,
                "nhom": spec["nhom"],
            }

    # Món nguồn đã hết vai trò → xoá khỏi menu. `remap` gom đơn về id đích ở bước
    # 3, nên bước 3 KHÔNG cần dòng nguồn còn tồn tại. Lịch sử đơn giữ nguyên vì
    # `dong` là snapshot tên/giá/số lượng, không join sang menu_mon nữa.
    for nguon_list in GOP_MON.values():
        for mid in nguon_list:
            if mid in menu:
                bind.execute(sa.text("DELETE FROM menu_mon WHERE id=:id"), {"id": mid})
                menu.pop(mid, None)

    # ── 3. Sửa đơn: `mon_id` gom về id chuẩn, `dong` về đúng shape, `thanh_toan`
    #    về mã thật. ──
    for row in bind.execute(
        sa.text("SELECT id, trang_thai, dong, thanh_toan FROM don_quay")
    ).mappings():
        dong = _nap_json(row["dong"])
        moi = _dung_dong(
            dong,
            remap,
            menu,
            # Chỉ đơn còn làm mới cần tên đúng; đơn xong/huỷ là lịch sử.
            chua_quet_lai_ten=str(row["trang_thai"]) not in ("xong", "huy"),
        )
        thanh = str(row["thanh_toan"] or "")
        if thanh not in THANH_TOAN_HOP_LE:
            thanh = "chua_thu"
        if moi == dong and thanh == row["thanh_toan"]:
            continue
        bind.execute(
            sa.text("UPDATE don_quay SET dong=:dong, thanh_toan=:tt WHERE id=:id"),
            {"dong": json.dumps(moi, ensure_ascii=False), "tt": thanh, "id": row["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for ten_bak, ten_bang in ((BAK_MENU, "menu_mon"), (BAK_DON, "don_quay")):
        if not inspector.has_table(ten_bak):
            continue
        # `DELETE` + `INSERT` thay vì `DROP`/rename: giữ nguyên index và ràng
        # buộc đã khai trên bảng gốc, không phụ thuộc thứ tự cột.
        bind.execute(sa.text(f'DELETE FROM "{ten_bang}"'))
        bind.execute(sa.text(f'INSERT INTO "{ten_bang}" SELECT * FROM "{ten_bak}"'))
        bind.execute(sa.text(f'DROP TABLE "{ten_bak}"'))
