"""HTTP router — QUÁNVERSE demo/mock surface (plan quanverse-ops-cockpit).

Ba route CHỈ-ĐỌC trả **đúng hình dạng** của bề mặt vận hành thật:

    GET /api/v1/experience/quanverse/snapshot
    GET /api/v1/experience/quanverse/stations
    GET /api/v1/experience/quanverse/forecast

Mục đích: cho `/quanverse` chạy được khi quán CHƯA có đơn thật, mà không phải
nới lỏng hay bịa số ở tầng UI. Dữ liệu ở đây là fixture biên soạn tay, **không**
đọc DB, **không** gọi LLM, **không** ghi gì.

TÊN FILE — ĐỪNG ĐỔI THÀNH `test_*.py`
--------------------------------------
`pyproject.toml` khai `testpaths = ["apps", "packages"]` và dùng quy ước mặc
định `python_files = test_*.py`. Một file trong `apps/` tên `test_quanverse.py`
sẽ bị pytest **thu như module test** và gọi thẳng các hàm route với fixture
của pytest — `scenario` nhận object `Query(...)` thay vì chuỗi `"cao_diem"`,
rồi `_lay_kich_ban` ném 404 `scenario_khong_ton_tai`. Lỗi này **không thấy được**
khi chạy `pytest <đúng file test>`; nó chỉ nổ ở job CI quét cả `apps/`.

Vì sao KHÔNG nhét vào `quanverse.py`: tách file để (a) route fixture không lẫn
vào router production có cổng vai thật (`_require_manager`), (b) xoá được bằng
một `git rm` khi hết nhu cầu demo, (c) `include_in_schema=False` giữ
`/openapi.json` sạch — bề mặt mock không phải hợp đồng sản phẩm.

Đánh dấu nguồn: mọi payload trả `"nguon": "fixture_mock"` (stations/forecast)
hoặc `data_quality[].code == "fixture_mock"` (snapshot) để UI luôn hiện được
nhãn "Dữ liệu mô phỏng" thay vì trộn lẫn với dữ liệu đo thật.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["experience_quanverse_test"])

# ── Kịch bản mock ─────────────────────────────────────────────────────────
#
# Mỗi kịch bản phải NHẤT QUÁN NỘI BỘ: `chi_so.don_dang_xu_ly` == tổng `tai`
# của 4 khu vực, và `don_hom_nay` == don_dang_xu_ly + don_da_xong. Ràng buộc
# này được chốt bằng test (apps/api/tests/unit/test_quanverse_test_api.py).
#
# Ngưỡng tải `muc_day` = 5 khớp hằng số trong `services/quanverse_live.py`.

_KHU_MAC_DINH: tuple[tuple[str, str, str], ...] = (
    ("quay_pha", "Quầy pha chế", "quay_pha"),
    ("quay_thu_ngan", "Quầy thu ngân", "quay_thu_ngan"),
    ("khu_ban", "Khu bàn", "phong_khach"),
    ("kho", "Kho", "kho"),
)

_MUC_DAY = 5


def _canh_bao(tai: int) -> str:
    """Cùng ngưỡng với `services/quanverse_live.py`: >=5 quá tải, >=4 chú ý."""
    if tai >= _MUC_DAY:
        return "qua_tai"
    if tai >= _MUC_DAY - 1:
        return "chu_y"
    return "binh_thuong"


#: `tai` (đơn đang xử lý), `hang_cho` (đơn chờ), `nhan_su` (người trực khu vực)
_KICH_BAN: dict[str, dict[str, Any]] = {
    "binh_thuong": {
        "ten": "Ca thường",
        "gio": 10,
        "khu": {
            "quay_pha": (2, 0, 2),
            "quay_thu_ngan": (1, 1, 1),
            "khu_ban": (0, 0, 2),
            "kho": (0, 0, 1),
        },
        "da_xong": 9,
        "nhan_su_trong_ca": 6,
        "so_ca_phu_khung_gio": 2,
        "tu_van_hanh": [
            {
                "gio": 10,
                "tieu_de": "Bàn giao quầy pha",
                "loai": "handover",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
            {
                "gio": 11,
                "tieu_de": "Kiểm tra tồn kho sữa",
                "loai": "kiem_ke",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
        ],
        "su_kien": [
            {
                "zone_id": "quay_pha",
                "event_type": "process",
                "status": "ok",
                "summary": "Mẻ cà phê đầu ca đạt chuẩn",
                "source": "fixture_mock",
                "minutes_ago": 12,
            },
            {
                "zone_id": "quay_thu_ngan",
                "event_type": "operation_memory",
                "status": "ok",
                "summary": "Đã thu tiền 3 đơn chuyển khoản",
                "source": "fixture_mock",
                "minutes_ago": 6,
            },
        ],
    },
    "cao_diem": {
        "ten": "Giờ cao điểm",
        "gio": 17,
        "khu": {
            "quay_pha": (4, 3, 2),
            "quay_thu_ngan": (2, 1, 1),
            "khu_ban": (1, 0, 2),
            "kho": (0, 0, 1),
        },
        "da_xong": 34,
        "nhan_su_trong_ca": 6,
        "so_ca_phu_khung_gio": 3,
        "tu_van_hanh": [
            {
                "gio": 17,
                "tieu_de": "Bàn giao quầy pha",
                "loai": "handover",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
            {
                "gio": 17,
                "tieu_de": "Kiểm tra tồn kho sữa",
                "loai": "kiem_ke",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
            {
                "gio": 18,
                "tieu_de": "Ca mới bắt đầu",
                "loai": "doi_ca",
                "nguon": "lich_tuan",
                "trang_thai": "sap_toi",
            },
            {
                "gio": 18,
                "tieu_de": "Kiểm tra vệ sinh khu khách",
                "loai": "ve_sinh",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
        ],
        "su_kien": [
            {
                "zone_id": "quay_pha",
                "event_type": "incident",
                "status": "warning",
                "summary": "Quầy pha chế vượt ngưỡng tải (7 đơn)",
                "source": "fixture_mock",
                "minutes_ago": 3,
            },
            {
                "zone_id": "quay_thu_ngan",
                "event_type": "process",
                "status": "ok",
                "summary": "Hàng chờ thanh toán 2 đơn",
                "source": "fixture_mock",
                "minutes_ago": 5,
            },
            {
                "zone_id": None,
                "event_type": "signal",
                "status": "warning",
                "summary": "Ca 18:00 còn thiếu 1 người so với định biên",
                "source": "fixture_mock",
                "minutes_ago": 9,
            },
        ],
    },
    "qua_tai_pha": {
        "ten": "Quầy pha quá tải",
        "gio": 15,
        "khu": {
            "quay_pha": (7, 4, 2),
            "quay_thu_ngan": (1, 0, 1),
            "khu_ban": (0, 0, 1),
            "kho": (0, 0, 1),
        },
        "da_xong": 18,
        "nhan_su_trong_ca": 5,
        "so_ca_phu_khung_gio": 2,
        "tu_van_hanh": [
            {
                "gio": 15,
                "tieu_de": "Dồn nguyên liệu sang quầy pha",
                "loai": "tiep_ung",
                "nguon": "sop",
                "trang_thai": "sap_toi",
            },
            {
                "gio": 15,
                "tieu_de": "Kiểm tra vệ sinh máy pha",
                "loai": "ve_sinh",
                "nguon": "sop",
                "trang_thai": "qua_han",
            },
            {
                "gio": 16,
                "tieu_de": "Điều 1 người từ khu bàn sang quầy pha",
                "loai": "dieu_chuyen",
                "nguon": "phan_cong",
                "trang_thai": "sap_toi",
            },
        ],
        "su_kien": [
            {
                "zone_id": "quay_pha",
                "event_type": "incident",
                "status": "critical",
                "summary": "Quầy pha chế quá tải kéo dài — 11 đơn dồn",
                "source": "fixture_mock",
                "minutes_ago": 2,
            },
            {
                "zone_id": "kho",
                "event_type": "signal",
                "status": "warning",
                "summary": "Kho cần kiểm tra — nguyên liệu dưới ngưỡng",
                "source": "fixture_mock",
                "minutes_ago": 14,
            },
            {
                "zone_id": "quay_pha",
                "event_type": "incident",
                "status": "warning",
                "summary": "SOP 'vệ sinh máy pha' quá hạn",
                "source": "fixture_mock",
                "minutes_ago": 21,
            },
        ],
    },
}

_MAC_DINH = "cao_diem"


def _lay_kich_ban(scenario: str) -> dict[str, Any]:
    kb = _KICH_BAN.get(scenario)
    if kb is None:
        raise HTTPException(
            status_code=404,
            detail=f"scenario_khong_ton_tai:{scenario}",
        )
    return kb


def _cau_truc_khu(kb: dict[str, Any]) -> list[dict[str, Any]]:
    ra: list[dict[str, Any]] = []
    for zone_id, ten, kind in _KHU_MAC_DINH:
        tai, hang_cho, nhan_su = kb["khu"][zone_id]
        ra.append(
            {
                "zone_id": zone_id,
                "ten": ten,
                "kind": kind,
                "tai": tai,
                "hang_cho": hang_cho,
                "muc_day": _MUC_DAY,
                "canh_bao": _canh_bao(tai),
                "nhan_su": nhan_su,
            }
        )
    return ra


@router.get(
    "/api/v1/test/quanverse/stations",
    include_in_schema=False,
    summary="[mock] Tải theo khu vực — fixture biên soạn tay",
)
def test_quanverse_stations(
    scenario: str = Query(default=_MAC_DINH),
) -> dict[str, Any]:
    """Bản mock của `GET /api/v1/experience/quanverse/stations`.

    Cùng khoá top-level để adapter thật/mock dùng CHUNG một bộ đọc dữ liệu.
    """
    kb = _lay_kich_ban(scenario)
    khu = _cau_truc_khu(kb)
    don_dang_xu_ly = sum(k["tai"] for k in khu)
    return {
        "co_du_lieu": True,
        "gio": kb["gio"],
        "tuan_iso": "2026-W40",
        "stations": khu,
        "chi_so": {
            "don_hom_nay": don_dang_xu_ly + kb["da_xong"],
            "don_dang_xu_ly": don_dang_xu_ly,
            "don_da_xong": kb["da_xong"],
            "nhan_su_trong_ca": kb["nhan_su_trong_ca"],
            "so_ca_phu_khung_gio": kb["so_ca_phu_khung_gio"],
        },
        "nguon": "fixture_mock",
    }


@router.get(
    "/api/v1/test/quanverse/forecast",
    include_in_schema=False,
    summary="[mock] Dự báo nhu cầu theo giờ — fixture biên soạn tay",
)
def test_quanverse_forecast(
    scenario: str = Query(default=_MAC_DINH),
) -> dict[str, Any]:
    """Bản mock của `GET /api/v1/experience/quanverse/forecast`.

    16 điểm 7h→22h đúng như bản thật (`services/quanverse_live.forecast`).
    """
    kb = _lay_kich_ban(scenario)
    gio_cao_diem = kb["gio"]
    # Đường nhu cầu: dốc lên tới giờ cao điểm rồi giảm — hình dạng cố định theo
    # kịch bản, KHÔNG random, để test so khớp được.
    series: list[dict[str, Any]] = []
    for gio in range(7, 23):
        khoang_cach = abs(gio - gio_cao_diem)
        nhu_cau = max(0.0, round(8.0 - khoang_cach * 1.4, 2))
        if khoang_cach == 0:
            nhu_cau = 8.0
        series.append(
            {
                "gio": gio,
                "nhu_cau": nhu_cau,
                "hang_doi_du_bao": max(0, round(nhu_cau - 2)),
            }
        )
    dinh = max(s["nhu_cau"] for s in series)
    return {
        "co_du_lieu": True,
        "so_ngay_du_lieu": 4,
        "series": series,
        "giao_dich_nhat": [s["gio"] for s in series if s["nhu_cau"] == dinh and dinh > 0],
        "nguon": "fixture_mock",
    }


@router.get(
    "/api/v1/test/quanverse/snapshot",
    include_in_schema=False,
    summary="[mock] Trạng thái quán — fixture biên soạn tay",
)
def test_quanverse_snapshot(
    scenario: str = Query(default=_MAC_DINH),
) -> dict[str, Any]:
    """Bản mock của `GET /api/v1/experience/quanverse/snapshot`.

    Trả cùng khoá `zones / events / next_horizon / data_quality` mà bản thật
    trả, nhưng KHÔNG đi qua `_project_role` (mock dành cho màn demo, không
    phải bề mặt phân quyền) — vì vậy nhãn chất lượng dữ liệu nói thẳng đây là
    fixture mock.
    """
    kb = _lay_kich_ban(scenario)
    khu = _cau_truc_khu(kb)

    zones = [
        {
            "zone_id": k["zone_id"],
            "label": k["ten"],
            "kind": k["kind"],
            "active": True,
            "load_signal": k["canh_bao"],
        }
        for k in khu
    ]

    events = []
    for i, sk in enumerate(kb["su_kien"], start=1):
        events.append(
            {
                "event_id": f"mock_ev_{scenario}_{i:02d}",
                "event_type": sk["event_type"],
                "status": sk["status"],
                "occurred_at": f"mock+{sk['minutes_ago']}m",
                "source": sk["source"],
                "summary": sk["summary"],
                "zone_id": sk["zone_id"],
            }
        )

    next_horizon = [
        {
            "item_id": f"mock_hz_{scenario}_{i:02d}",
            "kind": tv["loai"],
            "title": tv["tieu_de"],
            "starts_at": f"{tv['gio']:02d}:00",
            "source": tv["nguon"],
            "status": tv["trang_thai"],
        }
        for i, tv in enumerate(kb["tu_van_hanh"], start=1)
    ]

    return {
        "snapshot_id": f"mock_snap_{scenario}",
        "store_id": "quan_01",
        "generated_at": "mock",
        "role": "quan_ly",
        "zones": zones,
        "events": events,
        "modes": [],
        "next_horizon": next_horizon,
        "data_quality": [
            {
                "code": "fixture_mock",
                "level": "info",
                "message": (
                    f"Dữ liệu mô phỏng — kịch bản '{kb['ten']}'. "
                    "Không phải số đo từ quán."
                ),
            }
        ],
    }
