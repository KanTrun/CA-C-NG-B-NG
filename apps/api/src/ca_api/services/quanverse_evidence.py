"""Quanverse — Evidence Builder (CODE, không LLM, không JEV).

Ranh giới chốt với người dùng:
- Tầng này ĐỌC database thật và quyết định BAO PHỦ (coverage).
- JEV chỉ được gọi khi đủ/tạm đủ căn cứ. Trống hoàn toàn → KHÔNG gọi JEV.
- Action candidates là CLOSED-SET A–E do CODE dựng (đủ điều kiện + lý do).
  JEV chỉ RANK, không phát minh action mới.
"""

from __future__ import annotations

from typing import Any

_DANG_XU_LY = {"cho_pha", "dang_pha"}

# Closed-set hành động — JEV chỉ rank trong tập này.
CANDIDATE_DEFS: list[dict[str, Any]] = [
    {"id": "A", "label": "Mở Lịch tuần", "href": "/lich-tuan", "source": "Lịch tuần"},
    {"id": "B", "label": "Kiểm tra tồn kho", "href": "/tieu-thu", "source": "Kho"},
    {"id": "C", "label": "Xem quầy pha", "href": "/quay", "source": "Đơn quầy"},
    {"id": "D", "label": "Xử lý việc treo", "href": "/treo", "source": "Việc treo"},
    {"id": "E", "label": "Không làm gì", "href": None, "source": "Hệ thống"},
]


def _kho_ton() -> list[dict[str, Any]]:
    try:
        from ca_api.persist import kv_get

        raw = kv_get("tieu_thu", [])
        return [x for x in (raw or []) if isinstance(x, dict)]
    except Exception:
        return []


def _viec_treo_mo() -> list[dict[str, Any]]:
    try:
        from ca_api.persist import kv_get

        raw = kv_get("viec_treo", [])
        rows = [x for x in (raw or []) if isinstance(x, dict)]
        return [x for x in rows if str(x.get("trang_thai") or "") != "xong"]
    except Exception:
        return []


def build_evidence(store_id: str = "quan_01") -> dict[str, Any]:
    """Dựng STATE gọn + COVERAGE + candidates từ DB thật. Chỉ ĐỌC."""
    del store_id
    from ca_api.persist import don_list, kv_get
    from ca_api.services.quanverse_live import (
        _tuan_hien_tai,
        forecast,
        staff_on_shift,
        stations,
    )

    orders = don_list()
    try:
        st = stations()
    except Exception:
        st = {"co_du_lieu": False, "stations": [], "chi_so": {}}
    try:
        fc = forecast()
    except Exception:
        fc = {"co_du_lieu": False, "so_ngay_du_lieu": 0, "giao_dich_nhat": []}
    try:
        staff = staff_on_shift()
    except Exception:
        staff = {"co_du_lieu": False, "names": [], "count": None, "shift_label": None}

    tuan = _tuan_hien_tai()
    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    ton = _kho_ton()
    canh_bao = [str(x.get("hang") or "").strip() for x in ton if x.get("duoi_nguong")]
    canh_bao = [x for x in canh_bao if x]
    treo_mo = _viec_treo_mo()

    chi_so = st.get("chi_so") or {} if isinstance(st, dict) else {}
    don_dang_xu_ly = int(chi_so.get("don_dang_xu_ly") or 0)
    stations_rows = st.get("stations") or [] if isinstance(st, dict) else []
    pha = next((s for s in stations_rows if s.get("zone_id") == "quay_pha"), {})
    pha_tai = pha.get("tai")
    pha_muc = pha.get("muc_day", 5)
    pha_canh_bao = pha.get("canh_bao", "binh_thuong")

    don_ok = bool(orders)
    lich_ok = bool(week_assign)
    kho_ok = bool(ton)

    if don_ok and lich_ok and kho_ok:
        trang_thai = "du"
    elif don_ok or lich_ok or kho_ok:
        trang_thai = "thieu_1_phan"
    else:
        trang_thai = "trong"

    staff_count = staff.get("count") if isinstance(staff, dict) else None
    try:
        staff_count_int = int(staff_count) if staff_count is not None else None
    except (TypeError, ValueError):
        staff_count_int = None

    # Candidates do CODE quyết định đủ điều kiện — JEV chỉ rank.
    candidates: list[dict[str, Any]] = []
    # A — lịch
    if not lich_ok:
        candidates.append({
            "id": "A", "label": "Mở Lịch tuần", "href": "/lich-tuan",
            "source": "Lịch tuần", "eligible": True,
            "reason": "Chưa có phân công tuần — cần phân ca trước.",
        })
    elif staff_count_int is not None and staff_count_int < 3:
        candidates.append({
            "id": "A", "label": "Mở Lịch tuần", "href": "/lich-tuan",
            "source": "Lịch tuần", "eligible": True,
            "reason": f"Ca hiện tại chỉ có {staff_count_int} người trực.",
        })
    else:
        candidates.append({
            "id": "A", "label": "Mở Lịch tuần", "href": "/lich-tuan",
            "source": "Lịch tuần", "eligible": False,
            "reason": "Lịch đã đủ người trực.",
        })
    # B — kho
    if not kho_ok:
        candidates.append({
            "id": "B", "label": "Kiểm tra tồn kho", "href": "/tieu-thu",
            "source": "Kho", "eligible": True,
            "reason": "Chưa có số liệu tồn kho — cần nhập để đánh giá.",
        })
    elif canh_bao:
        candidates.append({
            "id": "B", "label": "Kiểm tra tồn kho", "href": "/tieu-thu",
            "source": "Kho", "eligible": True,
            "reason": f"{len(canh_bao)} mặt hàng dưới ngưỡng: {', '.join(canh_bao[:3])}.",
        })
    else:
        candidates.append({
            "id": "B", "label": "Kiểm tra tồn kho", "href": "/tieu-thu",
            "source": "Kho", "eligible": False,
            "reason": "Tồn kho trong ngưỡng.",
        })
    # C — quầy pha
    if pha_canh_bao == "qua_tai":
        candidates.append({
            "id": "C", "label": "Xem quầy pha", "href": "/quay",
            "source": "Đơn quầy", "eligible": True,
            "reason": f"Quầy pha {pha_tai} đơn, ngưỡng {pha_muc}.",
        })
    elif pha_canh_bao == "chu_y":
        candidates.append({
            "id": "C", "label": "Xem quầy pha", "href": "/quay",
            "source": "Đơn quầy", "eligible": True,
            "reason": f"Quầy pha gần ngưỡng ({pha_tai}/{pha_muc}).",
        })
    else:
        candidates.append({
            "id": "C", "label": "Xem quầy pha", "href": "/quay",
            "source": "Đơn quầy", "eligible": False,
            "reason": "Quầy pha trong ngưỡng.",
        })
    # D — việc treo
    if treo_mo:
        candidates.append({
            "id": "D", "label": "Xử lý việc treo", "href": "/treo",
            "source": "Việc treo", "eligible": True,
            "reason": f"{len(treo_mo)} việc treo chưa xong.",
        })
    else:
        candidates.append({
            "id": "D", "label": "Xử lý việc treo", "href": "/treo",
            "source": "Việc treo", "eligible": False,
            "reason": "Không có việc treo mở.",
        })
    # E — luôn đủ điều kiện để Top3 không rỗng
    candidates.append({
        "id": "E", "label": "Không làm gì", "href": None,
        "source": "Hệ thống", "eligible": True,
        "reason": "Giữ nguyên khi mọi thứ trong ngưỡng.",
    })

    return {
        "trang_thai": trang_thai,
        "coverage": {
            "don": "ok" if don_ok else "thieu",
            "lich": "ok" if lich_ok else "thieu",
            "kho": "ok" if kho_ok else "thieu",
        },
        "state": {
            "don_dang_xu_ly": don_dang_xu_ly,
            "tong_don": len(orders),
            "quay_pha_tai": pha_tai,
            "quay_pha_muc": pha_muc,
            "quay_pha_canh_bao": pha_canh_bao,
            "nhan_vien_truc": staff_count_int,
            "ca_hien_tai": (staff.get("shift_label") if isinstance(staff, dict) else None),
            "ton_duoi_nguong": canh_bao,
            "viec_treo_mo": len(treo_mo),
            "so_ngay_du_lieu": fc.get("so_ngay_du_lieu") if isinstance(fc, dict) else 0,
            "gio_dinh": (fc.get("giao_dich_nhat") or []) if isinstance(fc, dict) else [],
            "tuan_iso": tuan,
        },
        "candidates": candidates,
        "nguon": "database_that",
    }
