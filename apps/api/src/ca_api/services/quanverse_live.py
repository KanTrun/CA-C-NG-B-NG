"""Quanverse — dữ liệu VẬN HÀNH THẬT cho bản đồ sống + dự báo (không fixture).

Vì sao: bản đồ sống trước đây lấy "tải" từ fixture nên chỉ là hình minh hoạ.
Tầng này tính từ dữ liệu quán ĐANG có:
- `stations()`: tải + hàng chờ theo khu vực, suy từ đơn quầy thật (`don_list`) +
  nhân sự đang trong ca (`phan_cong_by_week`) + định biên ca (seed).
- `forecast()`: nhu cầu/hàng đợi theo GIỜ, tất định từ lịch sử đơn (`don_quay`)
  trong ngày; chưa có lịch sử thì trả đường phẳng có nhãn "chưa đủ dữ liệu".
- `staff_on_shift()`: tên + số người đang trực theo ca phủ giờ hiện tại.

Nguyên tắc: chỉ ĐỌC, không mutation, không LLM, không bịa số. Chưa có dữ liệu
thật → trả `co_du_lieu=False` để UI tự bày chế độ mẫu (có nhãn).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

# Trạng thái đơn quầy coi là "đang xử lý" (chưa trả khách).
_DANG_XU_LY = {"cho_pha", "dang_pha"}
# Chỉ dùng trạng thái có trong enum đơn quầy — không thêm nhánh chết.
_DA_XONG = {"xong"}

# Khu vực vận hành mặc định (khớp ZoneProjection kind) khi chưa suy được từ đơn.
_KHU_MAC_DINH = [
    ("quay_pha", "Quầy pha chế", "quay_pha"),
    ("quay_thu_ngan", "Quầy thu ngân", "quay_thu_ngan"),
    ("khu_ban", "Khu bàn khách", "phong_khach"),
    ("kho", "Kho nguyên liệu", "kho"),
]

_MUC_DAY_MAC_DINH = 5
_THRESHOLD_KEY = "quanverse_zone_thresholds"


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


def _now_vn() -> datetime:
    return datetime.now(timezone(timedelta(hours=7)))


def _gio_bay_gio() -> int:
    """Giờ hiện tại theo giờ VN (UTC+7)."""
    return int(_now_vn().hour)


def _phut_bay_gio() -> int:
    now = _now_vn()
    return int(now.hour) * 60 + int(now.minute)


def _thu_bay_gio() -> int:
    """0=CN … 6=T7 — khớp JS `getDay()`."""
    return int(_now_vn().weekday() + 1) % 7


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


def _phut_tu_hhmm(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def _muc_day_theo_zone() -> dict[str, int]:
    """Ngưỡng tải theo khu vực — đọc từ kv, fallback mặc định 5.

    Cho phép cấu hình không hardcode: `kv['quanverse_zone_thresholds']` =
    `{ "quay_pha": 6, "default": 5 }`.
    """
    from ca_api.persist import kv_get

    raw = kv_get(_THRESHOLD_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    default = int(raw.get("default") or _MUC_DAY_MAC_DINH)
    out: dict[str, int] = {}
    for zone_id, _, _ in _KHU_MAC_DINH:
        val = raw.get(zone_id, default)
        try:
            out[zone_id] = max(1, int(val))
        except (TypeError, ValueError):
            out[zone_id] = default
    return out


def _seed_ca_va_nv() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    import json as _json

    from ca_api.interfaces.http.main import SEED

    try:
        seed = _json.loads(SEED.read_text(encoding="utf-8"))
    except Exception:
        seed = {}
    ca_meta = {str(c.get("id")): c for c in seed.get("ca_mau_21", []) if c.get("id")}
    ten_theo_id: dict[str, str] = {}
    for nv in seed.get("nhan_vien", []) or []:
        nid = str(nv.get("id") or "")
        if not nid:
            continue
        ten = str(nv.get("ten") or nv.get("name") or "").strip()
        if ten:
            ten_theo_id[nid] = ten
    return ca_meta, ten_theo_id


def staff_on_shift(store_id: str = "quan_01") -> dict[str, Any]:
    """Tên + số nhân sự đang trực theo ca phủ giờ hiện tại (máy chủ tính).

    `count=None` khi không suy ra được ca nào phủ giờ — khác `0` (có ca nhưng
    chưa phân công ai). UI phải hiện "—" cho null.
    """
    del store_id  # một quán / seed hiện tại
    from ca_api.persist import kv_get

    tuan = _tuan_hien_tai()
    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    ca_meta, ten_theo_id = _seed_ca_va_nv()

    # Bổ sung tên từ roster tuần nếu seed thiếu.
    try:
        from ca_api.interfaces.http import sprint45

        life = sprint45._life()  # noqa: SLF001 — cùng nguồn lich-tuan
        for nv in life.get("nhan_vien") or []:
            if not isinstance(nv, dict):
                continue
            nid = str(nv.get("id") or "")
            ten = str(nv.get("ten") or nv.get("name") or "").strip()
            if nid and ten:
                ten_theo_id[nid] = ten
        for ca in life.get("ca") or []:
            if isinstance(ca, dict) and ca.get("id"):
                ca_meta.setdefault(str(ca["id"]), ca)
        if isinstance(life.get("phan_cong"), dict) and not week_assign:
            week_assign = life["phan_cong"]
    except Exception:
        pass

    phut = _phut_bay_gio()
    thu = _thu_bay_gio()
    names: set[str] = set()
    count = 0
    shift_label: str | None = None

    for ca_id, meta in ca_meta.items():
        bat = _phut_tu_hhmm(meta.get("bat_dau"))
        ket = _phut_tu_hhmm(meta.get("ket_thuc"))
        if bat is None or ket is None:
            continue
        thu_ca = meta.get("thu")
        if thu_ca is not None:
            try:
                if int(thu_ca) != thu:
                    continue
            except (TypeError, ValueError):
                pass
        trong_ca = (
            bat <= phut < ket
            if ket >= bat
            else phut >= bat or phut < ket
        )
        if not trong_ca:
            continue
        nguoi = week_assign.get(ca_id) or []
        if not isinstance(nguoi, list):
            nguoi = []
        count += len(nguoi)
        for nv_id in nguoi:
            ten = ten_theo_id.get(str(nv_id))
            if ten:
                names.add(ten)
        shift_label = f"{meta.get('bat_dau') or ''}–{meta.get('ket_thuc') or ''}"

    co_ca = shift_label is not None
    return {
        "co_du_lieu": co_ca,
        "names": sorted(names),
        "count": count if co_ca else None,
        "shift_label": shift_label,
        "gio": _gio_bay_gio(),
        "tuan_iso": tuan,
        "nguon": "phan_cong_by_week" if co_ca else "chua_khop_ca",
    }


def stations(store_id: str = "quan_01") -> dict[str, Any]:
    """Tải + hàng chờ theo khu vực, suy từ đơn quầy + nhân sự đang trong ca."""
    from ca_api.persist import don_list

    del store_id
    orders = don_list()
    dang_xu_ly = [o for o in orders if str(o.get("trang_thai") or "") in _DANG_XU_LY]
    hom_nay = datetime.now(UTC).date().isoformat()
    don_hom_nay = [o for o in orders if str(o.get("luc") or "").startswith(hom_nay)]
    xong_hom_nay = [o for o in don_hom_nay if str(o.get("trang_thai") or "") in _DA_XONG]

    tuan = _tuan_hien_tai()
    from ca_api.persist import kv_get

    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    ca_meta, _ = _seed_ca_va_nv()
    nhan_su_trong_ca = sum(len(v or []) for v in (week_assign or {}).values())

    gio = _gio_bay_gio()
    so_ca_phu = _ca_dang_phu(gio, ca_meta)
    muc_theo_zone = _muc_day_theo_zone()

    cho_pha = len(dang_xu_ly)
    out: list[dict[str, Any]] = []
    for zone_id, ten, kind in _KHU_MAC_DINH:
        muc = muc_theo_zone.get(zone_id, _MUC_DAY_MAC_DINH)
        if zone_id == "quay_pha":
            tai = cho_pha
            hang_cho = cho_pha
        elif zone_id == "quay_thu_ngan":
            tai = len(
                [
                    o
                    for o in don_hom_nay
                    if str(o.get("thanh_toan") or "") in {"", "chua_tt", "cho_tt"}
                ]
            )
            hang_cho = max(0, tai // 2)
        else:
            tai = 0
            hang_cho = 0
        out.append(
            {
                "zone_id": zone_id,
                "ten": ten,
                "kind": kind,
                "tai": tai,
                "hang_cho": hang_cho,
                "muc_day": muc,
                "canh_bao": (
                    "qua_tai"
                    if tai >= muc
                    else ("chu_y" if tai >= muc - 1 else "binh_thuong")
                ),
            }
        )

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

    del store_id
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
