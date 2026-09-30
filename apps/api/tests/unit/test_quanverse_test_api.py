"""Test bề mặt MOCK của Quánverse — `/api/v1/test/quanverse/*`.

Chốt ba điều:
1. Ba route trả 200 KHÔNG cần token (đây là fixture demo, không phải bề mặt
   phân quyền — quyền vẫn do các route THẬT quyết định).
2. Hình dạng trả về ĐÚNG khoá mà adapter thật đọc, để thật/mock dùng chung một
   bộ đọc dữ liệu ở tầng UI.
3. Dữ liệu mock NHẤT QUÁN NỘI BỘ: `chi_so.don_dang_xu_ly` == tổng `tai` của 4
   khu vực, và `don_hom_nay` == dang_xu_ly + da_xong. Không có số rời rạc.
"""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.quanverse_fixtures import _KICH_BAN
from fastapi.testclient import TestClient

from ca_api.interfaces.http.main import app

client = TestClient(app)

KICH_BAN = sorted(_KICH_BAN)


@pytest.mark.parametrize("scenario", KICH_BAN)
def test_stations_dung_khoa_va_nhat_quan(scenario: str) -> None:
    res = client.get(f"/api/v1/test/quanverse/stations?scenario={scenario}")
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {
        "co_du_lieu",
        "gio",
        "tuan_iso",
        "stations",
        "chi_so",
        "nguon",
    }
    assert body["nguon"] == "fixture_mock"
    assert body["co_du_lieu"] is True
    assert len(body["stations"]) == 4

    for k in body["stations"]:
        assert set(k) == {
            "zone_id",
            "ten",
            "kind",
            "tai",
            "hang_cho",
            "muc_day",
            "canh_bao",
            "nhan_su",
        }
        assert k["canh_bao"] in {"qua_tai", "chu_y", "binh_thuong"}

    # NHẤT QUÁN: tổng tải khu vực phải bằng chỉ số tổng.
    tong_tai = sum(k["tai"] for k in body["stations"])
    assert body["chi_so"]["don_dang_xu_ly"] == tong_tai, "số rời rạc giữa zone và chi_so"
    assert body["chi_so"]["don_hom_nay"] == tong_tai + body["chi_so"]["don_da_xong"]


@pytest.mark.parametrize("scenario", KICH_BAN)
def test_forecast_16_diem_7_den_22(scenario: str) -> None:
    res = client.get(f"/api/v1/test/quanverse/forecast?scenario={scenario}")
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {
        "co_du_lieu",
        "so_ngay_du_lieu",
        "series",
        "giao_dich_nhat",
        "nguon",
    }
    assert body["nguon"] == "fixture_mock"
    assert [s["gio"] for s in body["series"]] == list(range(7, 23))
    for s in body["series"]:
        assert set(s) == {"gio", "nhu_cau", "hang_doi_du_bao"}
        assert s["nhu_cau"] >= 0
        assert s["hang_doi_du_bao"] >= 0


@pytest.mark.parametrize("scenario", KICH_BAN)
def test_snapshot_dung_khoa_va_bao_mock(scenario: str) -> None:
    res = client.get(f"/api/v1/test/quanverse/snapshot?scenario={scenario}")
    assert res.status_code == 200
    body = res.json()

    assert set(body) == {
        "snapshot_id",
        "store_id",
        "generated_at",
        "role",
        "zones",
        "events",
        "modes",
        "next_horizon",
        "data_quality",
    }
    assert len(body["zones"]) == 4
    # Bắt buộc có nhãn "đây là dữ liệu mô phỏng" — UI dựa vào đây để hiện badge.
    codes = {q["code"] for q in body["data_quality"]}
    assert "fixture_mock" in codes, "mock phải tự khai nguồn gốc"

    zone_ids = {z["zone_id"] for z in body["zones"]}
    for ev in body["events"]:
        assert ev["zone_id"] is None or ev["zone_id"] in zone_ids


def test_scenario_khong_ton_tai_tra_404() -> None:
    res = client.get("/api/v1/test/quanverse/stations?scenario=khong_co")
    assert res.status_code == 404
    assert "scenario_khong_ton_tai" in res.json()["detail"]


def test_mock_khong_can_token() -> None:
    """Fixture demo không đòi đăng nhập — nhưng cũng KHÔNG trả dữ liệu thật."""
    for path in ("snapshot", "stations", "forecast"):
        res = client.get(f"/api/v1/test/quanverse/{path}")
        assert res.status_code == 200, f"{path} phải mở cho màn demo"


def test_mock_an_khoi_openapi() -> None:
    """Bề mặt mock không được phơi ra `/openapi.json` (không phải hợp đồng sản phẩm)."""
    paths = set(app.openapi().get("paths", {}))
    assert not any(p.startswith("/api/v1/test/quanverse") for p in paths)
