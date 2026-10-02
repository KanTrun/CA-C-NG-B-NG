"""Bảng nguyên liệu chuẩn — MỘT nguồn cho mã, tên có dấu, đơn vị và nhóm.

Vì sao có module này
--------------------
Trước đây bảng này tồn tại ở **ba bản sao lệch nhau**:

1. `_DON_VI_BOM` trong ``interfaces/http/pos.py`` — chỉ 4 mã và toàn mã CŨ
   (``cafe_g``, ``sua_ml``, ``dao_lat``, ``ly``) không còn món nào dùng →
   15 mã thật (``ca_phe_hat``, ``da``, ``duong``…) rơi về mặc định
   ``"đơn vị"``, nên người dùng thấy ``ca_phe_hat 42 đơn vị``.
2. ``MAT_HANG`` trong ``apps/web/src/lib/present.ts`` — 9 mã.
3. ``BOM_INGREDIENTS`` trong ``apps/web/src/ui/bom-editor.tsx`` — 10 mã.

Hệ quả thấy ngay trên ``/tieu-thu``: tên nguyên liệu hiện ra ``ca_phe_hat``
(không dấu) và ``42 đơn vị``. Nguồn gốc của mã cũ là ``persist._MENU_MAC_DINH``
— menu mặc định khi DB trống từng ghi "Ca phe den" với ``bom={"cafe_g":18}``.

Nguồn chuẩn
-----------
``data/seed/danh-muc.json`` → mảng ``nguyen_lieu`` (mỗi phần tử:
``{ma, ten, don_vi, nhom}``). Bản TS tương ứng ở
``apps/web/src/lib/nguyen-lieu.ts``, và test hai chiều (Python + vitest) chặn
hai bản lệch nhau.

Mã cũ không xoá khỏi dữ liệu: ``ALIAS`` nối ``cafe_g → ca_phe_hat`` để đọc lại
sổ tiêu thụ và ``bom`` món ăn cũ mà không mất số liệu.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# `nguyen_lieu.py` nằm ở `apps/api/src/ca_api/` → cần leo 4 bậc tới repo root.
_ROOT = Path(__file__).resolve().parents[4]
DANH_MUC = _ROOT / "data" / "seed" / "danh-muc.json"

# Mã LEGACY → mã chuẩn. Bốn mã này do `persist._MENU_MAC_DINH` sinh ra và vẫn còn
# nằm trong `menu_mon.bom` / `kv.tieu_thu` của DB đã chạy thật. Không có bảng này
# thì "Cà phê" (cafe_g) và "Cà phê hạt" (ca_phe_hat) thành hai mặt hàng khác
# nhau trong sổ tiêu thụ.
ALIAS: dict[str, str] = {
    "cafe_g": "ca_phe_hat",
    "sua_ml": "sua_tuoi",
    "dao_lat": "dao",
    "ly_nhua": "ly",
}

#: Tên NGƯỜI GÕ TAY từng xuất hiện trong sổ, quy về mã chuẩn. Khác ``ALIAS`` ở
#: chỗ đó khớp MÃ (``cafe_g``), còn đây khớp TÊN khi bỏ dấu ("Ly giay" — dòng do
#: `quanverse_demo.setup()` ghi, không khớp tên chuẩn "Ly / cốc dùng một lần").
#: Mục tiêu lấy theo ``ca_agents.ag_waste.loss.BI_DANH`` để hai bảng bí danh không
#: mỗi nơi một kiểu; ``test_nguyen_lieu.py`` khoá lại bằng assert.
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

_bang: dict[str, dict[str, str]] | None = None
_doc: dict[str, Any] | None = None


def doc_danh_muc() -> dict[str, Any]:
    """Đọc `danh-muc.json`. Nạp trễ để import module không vỡ khi thiếu file."""
    global _doc
    if _doc is None:
        if DANH_MUC.exists():
            _doc = json.loads(DANH_MUC.read_text(encoding="utf-8"))
        else:
            _doc = {}
    return _doc


def bang_nguyen_lieu() -> dict[str, dict[str, str]]:
    """`{"ca_phe_hat": {"ten": "Cà phê hạt", "don_vi": "g", "nhom": "ca_phe"}, …}`."""
    global _bang
    if _bang is None:
        out: dict[str, dict[str, str]] = {}
        for row in doc_danh_muc().get("nguyen_lieu") or []:
            if not isinstance(row, dict):
                continue
            ma = str(row.get("ma") or "").strip()
            if not ma:
                continue
            out[ma] = {
                "ten": str(row.get("ten") or ma),
                "don_vi": str(row.get("don_vi") or "đơn vị"),
                "nhom": str(row.get("nhom") or ""),
            }
        _bang = out
    return _bang


def chuan_hoa_ma(key: str) -> str:
    """``"cafe_g"`` → ``"ca_phe_hat"``; mã đã chuẩn thì giữ nguyên.

    Không đoán: mã lạ (tên gõ tay của nhân viên) trở về chính nó, vì xoá mất nó
    là xoá mất dòng sổ tiêu thụ người ta vừa ghi.
    """
    raw = str(key or "").strip()
    return ALIAS.get(raw, raw)


def ten_nguyen_lieu(key: str) -> str:
    """``"ca_phe_hat"`` → ``"Cà phê hạt"``.

    Mã không có trong bảng → humanise (gạch dưới thành khoảng trắng), KHÔNG bịa
    tiếng Việt cho mã lạ: đọc sai tên nguyên liệu còn tệ hơn hiện mã.
    """
    ma = chuan_hoa_ma(key)
    hit = bang_nguyen_lieu().get(ma)
    if hit:
        return hit["ten"]
    return ma.replace("_", " ").strip() or "Mặt hàng chưa ghi tên"


def don_vi(key: str) -> str:
    """Đơn vị chuẩn — thay cho ``_DON_VI_BOM`` cũ chỉ có 4 mã lỗi."""
    ma = chuan_hoa_ma(key)
    hit = bang_nguyen_lieu().get(ma)
    return hit["don_vi"] if hit else "đơn vị"


def nhom_nguyen_lieu(key: str) -> str:
    """Nhóm của NGUYÊN LIỆU — khoá ``nhom`` dùng để lọc ``/tieu-thu``.

    ``ca_phe_hat → "ca_phe"``, ``tra → "tra"``… Đây là nhóm để người dùng lọc sổ,
    không phải nhóm món (một nguyên liệu đi vào nhiều nhóm món). Chuỗi rỗng khi
    mã lạ — ``tong_hop_tieu_thu`` sẽ mượn nhóm của món liên quan nếu có.
    """
    ma = chuan_hoa_ma(key)
    hit = bang_nguyen_lieu().get(ma)
    return hit["nhom"] if hit else ""


def la_ma_chuan(key: str) -> bool:
    """Mã có trong bảng chuẩn (sau khi đã qua ``ALIAS``)."""
    return chuan_hoa_ma(key) in bang_nguyen_lieu()


def _khoa(text: str) -> str:
    """Bỏ dấu + hạ chữ thường — để khớp "Ca phe hat" với "Cà phê hạt"."""
    import unicodedata

    s = unicodedata.normalize("NFD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def tim_ma_theo_ten(ten: str) -> str | None:
    """``"Ca phe hat"`` / ``"Cà phê hạt"`` → ``"ca_phe_hat"``.

    Sổ tiêu thụ cũ ghi tên MẤT DẤU ("Sua tuoi", "Duong"). Không tra được bằng tên
    thì dòng đó thành mặt hàng riêng biệt, và phép tổng theo nguyên liệu sẽ chia
    đôi một cách vô nghĩa.
    """
    khoa = _khoa(ten)
    if not khoa:
        return None
    truc = TEN_BI_DANH.get(khoa)
    if truc and la_ma_chuan(truc):
        return truc
    for ma, info in bang_nguyen_lieu().items():
        if _khoa(info["ten"]) == khoa:
            return ma
    return None


def chuan_hoa_bom(bom: Any) -> dict[str, float]:
    """Đưa `bom` về mã chuẩn, cộng định mức khi hai khoá quy về một mã.

    ``{"cafe_g": 18, "ca_phe_hat": 10}`` → ``{"ca_phe_hat": 28}``. Bỏ dòng giá
    không đọc được hoặc ≤ 0 thay vì để ``NaN`` làm lệch phép tính hao hụt.

    Số nguyên giữ dạng ``int`` để JSON ghi ``18`` chứ không ``18.0`` — dữ liệu
    so được với ``danh-muc.json`` và người đọc không thấy lẻ thừa.
    """
    out: dict[str, float] = {}
    if not isinstance(bom, dict):
        return out
    for khoa, gia_tri in bom.items():
        try:
            so = float(gia_tri)
        except (TypeError, ValueError):
            continue
        if so <= 0:
            continue
        ma = chuan_hoa_ma(str(khoa))
        tong = out.get(ma, 0.0) + so
        out[ma] = int(tong) if float(tong).is_integer() else tong
    return out


# ── Sổ tiêu thụ ────────────────────────────────────────────────────────────────

#: Trường tối thiểu của một dòng ``kv.tieu_thu`` đọc được.
TRUONG_TOI_THIEU = ("hang", "so_luong")

#: Hình dạng dòng ``kv.tieu_thu`` hỏng: seeder cũ ghi ``order_id/status/items``.
#: Dòng này không có ``hang``/``so_luong`` → UI render ô trống (bug đang thấy).
DONG_HINH_DANG_LE = ("order_id", "items")


def chuan_hoa_dong_tieu_thu(row: Any) -> dict[str, Any] | None:
    """Đưa một dòng ``kv.tieu_thu`` về hình dạng sạch. ``None`` = dòng bỏ đi.

    Dòng bỏ: không phải dict, hoặc thiếu ``hang``/``so_luong`` (đúng hình dạng
    legacy ``{"order_id","status","items":{...}}``). Thà bỏ một dòng hỏng còn
    hơn hiện ô trống lẫn số ``undefined`` trên trang.

    Dòng trả về thêm ``ma`` (mã chuẩn), ``hang`` (tiếng Việt **có dấu**),
    ``don_vi`` (đúng đơn vị) và ``nhom`` (cho bộ lọc nhóm) — nhưng GIỮ NGUYÊN
    ``hang_goc`` và các trường ``mon_*``/``luc``/``nguon`` cũ.
    """
    if not isinstance(row, dict):
        return None
    hang_goc = str(row.get("hang") or "").strip()
    if not hang_goc:
        return None
    so_luong = row.get("so_luong")
    if so_luong is None:
        return None
    try:
        so = float(so_luong)
    except (TypeError, ValueError):
        return None

    ma = chuan_hoa_ma(hang_goc)
    if not la_ma_chuan(ma):
        tim_thay = tim_ma_theo_ten(hang_goc)
        if tim_thay:
            ma = tim_thay

    out = dict(row)
    out["ma"] = ma
    out["hang_goc"] = hang_goc
    out["so_luong"] = so
    if la_ma_chuan(ma):
        # Mã tra được trong bảng → dùng tên CÓ DẤU và đơn vị chuẩn.
        out["hang"] = ten_nguyen_lieu(ma)
        out["don_vi"] = don_vi(ma)
        out["nhom"] = nhom_nguyen_lieu(ma)
    else:
        # Tên tự do chủ quán gõ ("Sữa đặc nhà"), không có trong bảng → giữ nguyên
        # đúng chữ họ ghi. Bịa tiếng Việt cho tên lạ là bịa dữ liệu.
        out["hang"] = hang_goc
        out["don_vi"] = str(row.get("don_vi") or "đơn vị")
        out["nhom"] = str(row.get("nhom") or "")
    return out


def khoa_trung(row: dict[str, Any]) -> tuple[Any, ...] | None:
    """Khóa nhận diện dòng TRÙNG (ghi hai lần cùng một lượt). ``None`` = không gộp.

    ``id`` không dùng được vì mỗi lần ghi sinh id mới — trùng thật là cùng
    ``ma`` + ``luc`` + ``so_luong`` + ``don_quay_id``. Nhưng ``luc`` là thứ cho
    biết "hai dòng này cùng lúc hay không"; thiếu nó thì **không bao giờ gộp**:
    gộp hai dòng không có thời gian là xoá mất một lần kiểm kê thật của người ta,
    và mất âm thầm. Trùng có thời gian vẫn bị bắt.
    """
    luc = row.get("luc") or row.get("created_at")
    if not luc:
        return None
    return (
        row.get("ma") or row.get("hang"),
        str(luc),
        row.get("so_luong"),
        row.get("don_quay_id"),
        row.get("nguon"),
    )


def loc_dong_tieu_thu(rows: Any) -> tuple[list[dict[str, Any]], int]:
    """Dọn một danh sách ``kv.tieu_thu``: bỏ hỏng, chuẩn hoá, khử trùng.

    Trả ``(danh_sach_sach, so_dong_da_bo)`` — ``so_dong_da_bo`` để trang báo cho
    người dùng biết có dòng dữ liệu cũ không đọc được, chứ không im lặng nuốt.
    """
    if not isinstance(rows, list):
        return [], 0
    sach: list[dict[str, Any]] = []
    da_thay: set[tuple[Any, ...]] = set()
    bo = 0
    for row in rows:
        moi = chuan_hoa_dong_tieu_thu(row)
        if moi is None:
            bo += 1
            continue
        khoa = khoa_trung(moi)
        if khoa is not None and khoa in da_thay:
            bo += 1
            continue
        if khoa is not None:
            da_thay.add(khoa)
        sach.append(moi)
    return sach, bo


# ── Gộp sổ theo nguyên liệu ────────────────────────────────────────────────────


def chi_muc_mon_theo_nguyen_lieu(menu: Any) -> dict[str, list[dict[str, str]]]:
    """``{"ca_phe_hat": [{"id": "ca_phe_den", "ten": "Cà phê đen", "nhom": "ca_phe"}, …]}``.

    Đây là chỗ ``/tieu-thu`` nối "Cà phê hạt 24 g" với **món đang bán** — kể cả
    dòng nhân viên đếm tay vốn không mang ``mon_id``. Món đang bị ẩn không tính
    vào, vì nó không còn là món "hiện tại" để bấm vào.
    """
    out: dict[str, list[dict[str, str]]] = {}
    for mon in menu or []:
        if not isinstance(mon, dict):
            continue
        if mon.get("an"):
            continue
        mid = str(mon.get("id") or "")
        if not mid:
            continue
        entry = {
            "id": mid,
            "ten": str(mon.get("ten") or mid),
            "nhom": str(mon.get("nhom") or ""),
        }
        for ma in chuan_hoa_bom(mon.get("bom")):
            out.setdefault(ma, []).append(entry)
    return out


def tong_hop_tieu_thu(rows: Any, menu: Any = None) -> list[dict[str, Any]]:
    """Gộp sổ tiêu thụ theo **một dòng cho một nguyên liệu**.

    Trước đây trang liệt kê từng dòng trừ kho → 60 dòng cho 8 nguyên liệu, không
    lọc được nhóm. Tổng theo ``ma`` (sau khi đã qua ``ALIAS``) cũng là chỗ hai mã
    ``cafe_g`` và ``ca_phe_hat`` — trước là hai mặt hàng riêng — thành một.

    Mỗi dòng trả về: ``ma``/``hang`` (tên có dấu)/``nhom`` (cho bộ lọc)/``don_vi``/
    ``so_luong`` (tổng)/``so_dong`` (số lần ghi)/``moi_nhat`` (lần ghi gần nhất)/
    ``mon_lien_quan`` (món đang bán dùng nguyên liệu này).
    """
    index = chi_muc_mon_theo_nguyen_lieu(menu)
    nhom_theo_mon = {
        str(m.get("id") or ""): str(m.get("nhom") or "")
        for m in menu or []
        if isinstance(m, dict) and not m.get("an")
    }
    gom: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ma = str(row.get("ma") or chuan_hoa_ma(str(row.get("hang") or "")))
        if not ma:
            continue
        try:
            so = float(row.get("so_luong") or 0)
        except (TypeError, ValueError):
            continue
        if so <= 0:
            continue
        dong = gom.get(ma)
        if dong is None:
            known = la_ma_chuan(ma)
            dong = {
                "ma": ma,
                "hang": ten_nguyen_lieu(ma) if known else ma.replace("_", " "),
                "nhom": nhom_nguyen_lieu(ma),
                "don_vi": don_vi(ma),
                "so_luong": 0.0,
                "so_dong": 0,
                "moi_nhat": "",
                "mon_dau": "",
                "mon_lien_quan": [],
            }
            gom[ma] = dong
        dong["so_luong"] += so
        dong["so_dong"] += 1
        luc = str(row.get("luc") or row.get("created_at") or "")
        if luc > dong["moi_nhat"]:
            dong["moi_nhat"] = luc
        if not dong["mon_dau"]:
            dong["mon_dau"] = str(row.get("mon_id") or "")
    for dong in gom.values():
        ds_mon = index.get(dong["ma"]) or []
        dong["mon_lien_quan"] = ds_mon
        dong["so_mon"] = len(ds_mon)
        # Tên tự gõ ("Sữa đặc nhà") không có trong bảng chuẩn nên không tra được
        # nhóm — mượn nhóm của MỐN gây ra dòng đó (dòng ước lượng luôn mang
        # `mon_id`). Không đoán từ "món nào dùng nguyên liệu này": một nguyên liệu
        # đi vào nhiều nhóm món, đoán là đặt món vào sai nhóm trên bộ lọc.
        if not dong["nhom"]:
            dong["nhom"] = nhom_theo_mon.get(dong["mon_dau"], "")
        dong.pop("mon_dau", None)
    return sorted(gom.values(), key=lambda d: (-float(d["so_luong"]), d["hang"]))
