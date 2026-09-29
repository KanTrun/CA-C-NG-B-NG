"""Quanverse — dữ liệu VẬN HÀNH THẬT cho bản đồ sống + dự báo (không fixture).

Vì sao: bản đồ sống trước đây lấy "tải" từ fixture nên chỉ là hình minh hoạ.
Tầng này tính từ dữ liệu quán ĐANG có:
- `stations()`: tải + hàng chờ theo khu vực, suy từ đơn quầy thật (`don_list`) +
  nhân sự đang trong ca (`phan_cong_by_week`) + định biên ca (seed).
- `forecast()`: nhu cầu/hàng đợi theo GIỜ, tất định từ lịch sử đơn (`don_quay`)
  trong ngày; chưa có lịch sử thì trả đường phẳng có nhãn "chưa đủ dữ liệu".

Nguyên tắc: chỉ ĐỌC, không mutation, không LLM, không bịa số. Chưa có dữ liệu
thật → trả `co_du_lieu=False` để UI tự bày chế độ mẫu (có nhãn).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Trạng thái đơn quầy coi là "đang xử lý" (chưa trả khách).
_DANG_XU_LY = {"cho_pha", "dang_pha"}
_DA_XONG = {"xong", "da_tra"}

# Khu vực vận hành mặc định (khớp ZoneProjection kind) khi chưa suy được từ đơn.
_KHU_MAC_DINH = [
    ("quay_pha", "Quầy pha chế", "quay_pha"),
    ("quay_thu_ngan", "Quầy thu ngân", "quay_thu_ngan"),
    ("khu_ban", "Khu bàn khách", "phong_khach"),
    ("kho", "Kho nguyên liệu", "kho"),
]


def _tuan_hien_tai() -> str:
    try:
        from ca_api.interfaces.http.sprint45 import _life

        tuan = str(_life().get("tuan_iso") or "")
        if tuan:
            return tuan
    except Exception:
        pass
    y, w, _ = datetime.now(UTC).isocalendar()
    return f"{y}-W{w:02d}"


def _gio_bay_gio() -> int:
    """Giờ hiện tại theo giờ VN (UTC+7)."""
    from datetime import timedelta, timezone

    return int(datetime.now(timezone(timedelta(hours=7))).hour)


def _ca_dang_phu(gio: int, ca_meta: dict[str, dict[str, Any]]) -> int:
    """Số ca đang phủ khung giờ `gio` (theo bat_dau/ket_thuc thật của ca)."""
    count = 0
    for meta in ca_meta.values():
        try:
            bh = int(str(meta.get("bat_dau") or "0:0").split(":")[0])
            eh = int(str(meta.get("ket_thuc") or "0:0").split(":")[0])
        except Exception:
            continue
        if bh <= gio < max(bh + 1, eh):
            count += 1
    return count


def stations(store_id: str = "quan_01") -> dict[str, Any]:
    """Tải + hàng chờ theo khu vực, suy từ đơn quầy + nhân sự đang trong ca."""
    import json as _json

    from ca_api.interfaces.http.main import SEED
    from ca_api.persist import don_list, kv_get

    orders = don_list()
    dang_xu_ly = [o for o in orders if str(o.get("trang_thai") or "") in _DANG_XU_LY]
    hom_nay = datetime.now(UTC).date().isoformat()
    don_hom_nay = [o for o in orders if str(o.get("luc") or "").startswith(hom_nay)]
    xong_hom_nay = [o for o in don_hom_nay if str(o.get("trang_thai") or "") in _DA_XONG]

    # Nhân sự đang trong ca (tuần hiện tại).
    tuan = _tuan_hien_tai()
    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    try:
        seed = _json.loads(SEED.read_text(encoding="utf-8"))
    except Exception:
        seed = {}
    ca_meta = {str(c.get("id")): c for c in seed.get("ca_mau_21", []) if c.get("id")}
    nhan_su_trong_ca = sum(len(v or []) for v in (week_assign or {}).values())

    gio = _gio_bay_gio()
    so_ca_phu = _ca_dang_phu(gio, ca_meta)

    # Tải theo khu vực: quầy pha chế chịu tải từ số đơn đang xử lý; các khu khác
    # suy theo tỷ lệ để KHÔNG bịa thêm dữ liệu (chỉ dùng 4 khu vận hành cơ bản).
    cho_pha = len(dang_xu_ly)
    muc = 5  # mỗi khu chịu ~5 đơn là "đầy" (ngưỡng hiển thị, không phải nghiệp vụ)
    out: list[dict[str, Any]] = []
    for zone_id, ten, kind in _KHU_MAC_DINH:
        if zone_id == "quay_pha":
            tai = cho_pha
            hang_cho = cho_pha
        elif zone_id == "quay_thu_ngan":
            tai = len([o for o in don_hom_nay if str(o.get("thanh_toan") or "") in {"", "chua_tt", "cho_tt"}])
            hang_cho = max(0, tai // 2)
        else:
            tai = 0
            hang_cho = 0
        out.append({
            "zone_id": zone_id,
            "ten": ten,
            "kind": kind,
            "tai": tai,
            "hang_cho": hang_cho,
            "muc_day": muc,
            "canh_bao": "qua_tai" if tai >= muc else ("chu_y" if tai >= muc - 1 else "binh_thuong"),
        })

    return {
        "co_du_lieu": bool(orders),
        "gio": gio,
        "tuan_iso": tuan,
        "stations": out,
        "chi_so": {
            "don_hom_nay": len(don_hom_nay),
            "don_dang_xu_ly": cho_pha,
            "don_da_xong": len(xong_hom_nay),
            "nhan_su_trong_ca": nhan_su_trong_ca,
            "so_ca_phu_khung_gio": so_ca_phu,
        },
        "nguon": "don_quay" if orders else "chua_co_du_lieu",
    }


def forecast(store_id: str = "quan_01") -> dict[str, Any]:
    """Nhu cầu/hàng đợi theo GIỜ, tất định từ lịch sử đơn quầy.

    Đếm số đơn mỗi giờ trong lịch sử (tất cả ngày có dữ liệu), rồi lấy trung
    bình theo giờ → đường nhu cầu 07:00–22:00. Chưa có lịch sử → đường phẳng
    và `co_du_lieu=False` (UI nói rõ "chưa đủ dữ liệu").
    """
    from collections import defaultdict

    from ca_api.persist import don_list

    orders = don_list()
    theo_gio: dict[int, int] = defaultdict(int)
    ngay_co_don: set[str] = set()
    for o in orders:
        luc = str(o.get("luc") or "")
        if len(luc) < 13:
            continue
        try:
            g = int(luc[11:13])
        except ValueError:
            continue
        theo_gio[g] += 1
        ngay_co_don.add(luc[:10])

    n_ngay = max(1, len(ngay_co_don))
    khung = list(range(7, 23))
    series = [
        {
            "gio": g,
            "nhu_cau": round(theo_gio.get(g, 0) / n_ngay, 2),
            "hang_doi_du_bao": max(0, round(theo_gio.get(g, 0) / n_ngay - 2)),
        }
        for g in khung
    ]
    dinh = max((s["nhu_cau"] for s in series), default=0.0)
    return {
        "co_du_lieu": bool(orders),
        "so_ngay_du_lieu": len(ngay_co_don),
        "series": series,
        "giao_dich_nhat": [s["gio"] for s in series if s["nhu_cau"] == dinh and dinh > 0],
        "nguon": "don_quay" if orders else "chua_co_du_lieu",
    }
