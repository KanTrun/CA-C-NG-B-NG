"""AI FORECAST — thời tiết hôm nay (Open-Meteo) + ảnh hưởng quán."""

from __future__ import annotations

import urllib.parse
from typing import Any

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import init_db, kv_set
from ca_api.services import thoi_tiet as thoi_tiet_mod
from ca_api.services.store_public_context import set_store_profile
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    # Xoá cache + profile giữa các test.
    kv_set(thoi_tiet_mod._CACHE_KEY, None)
    set_store_profile(
        {
            "ten_quan": "",
            "dia_chi": "",
            "tinh": "",
            "thanh_pho": "",
            "lat": None,
            "lon": None,
            "hotline": "",
            "gio_mo_cua": "",
            "wifi_ssid": "",
            "wifi_pass": "",
            "mo_ta": "",
            "chinh_sach_dat_ban": "",
            "huong_dan_agent": "",
        }
    )


def test_weather_group_map() -> None:
    assert thoi_tiet_mod.weather_group(0)[0] == "nang"
    assert thoi_tiet_mod.weather_group(63)[0] == "mua"
    assert thoi_tiet_mod.weather_group(65)[0] == "mua_to"
    assert thoi_tiet_mod.weather_group(95)[0] == "bao"
    assert thoi_tiet_mod.weather_group(None)[0] == "may"


def test_anh_huong_mua_de_xuat_troi_mua() -> None:
    impact = thoi_tiet_mod._anh_huong_quan(
        nhom="mua_to", nhiet_do=26.0, mua_mm=8.0, mo_ta="Mưa to"
    )
    assert impact["de_xuat_mode"] == "troi_mua"
    assert impact["he_so_ngoai_troi"] < 1
    assert impact["yeu_to"]


def test_thieu_vi_tri_tra_co_du_lieu_false() -> None:
    r = client.get("/api/v1/thoi-tiet/hom-nay", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["co_du_lieu"] is False
    assert body["can_cau_hinh"] is True
    ly_do = (body.get("ly_do") or "").lower()
    assert "vị trí" in ly_do or "gps" in ly_do or "địa chỉ" in ly_do


def test_resolve_vi_tri_uu_tien_gps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Có lat/lon → không gọi geocode."""

    def boom(url: str) -> dict[str, Any] | None:
        raise AssertionError(f"không được geocode khi có GPS: {url}")

    monkeypatch.setattr(thoi_tiet_mod, "_http_get_json", boom)
    vi = thoi_tiet_mod.resolve_vi_tri(
        {
            "lat": 10.7756,
            "lon": 106.7019,
            "thanh_pho": "Quận 1",
            "tinh": "Hồ Chí Minh",
            "dia_chi": "",
        }
    )
    assert vi is not None
    assert vi["nguon"] == "gps"
    assert abs(vi["lat"] - 10.7756) < 0.001
    assert abs(vi["lon"] - 106.7019) < 0.001


def test_resolve_vi_tri_fallback_tinh(monkeypatch: pytest.MonkeyPatch) -> None:
    """'Quận 1, Hồ Chí Minh' có thể rỗng — phải fallback về tỉnh."""
    calls: list[str] = []

    def fake_get(url: str) -> dict[str, Any] | None:
        calls.append(url)
        if "name=Qu%E1%BA%ADn" in url or "Qu%E1%BA%ADn+1" in url or "Quận" in urllib.parse.unquote(url):
            return {"results": []}
        if (
            "H%E1%BB%93+Ch%C3%AD+Minh" in url
            or "Ho+Chi+Minh" in url
            or "Hồ Chí Minh" in urllib.parse.unquote(url)
        ):
            return {
                "results": [
                    {
                        "name": "Thành phố Hồ Chí Minh",
                        "admin1": "Thành phố Hồ Chí Minh",
                        "latitude": 10.823,
                        "longitude": 106.63,
                    }
                ]
            }
        return {"results": []}

    monkeypatch.setattr(thoi_tiet_mod, "_http_get_json", fake_get)
    vi = thoi_tiet_mod.resolve_vi_tri({"thanh_pho": "Quận 1", "tinh": "Hồ Chí Minh", "dia_chi": ""})
    assert vi is not None
    assert vi["tinh"] == "Hồ Chí Minh"
    assert vi["thanh_pho"] == "Quận 1"
    assert abs(vi["lat"] - 10.823) < 0.01


def test_requires_auth() -> None:
    assert client.get("/api/v1/thoi-tiet/hom-nay").status_code == 401


def _mock_http(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, dict[str, Any]]) -> None:
    def fake_get(url: str) -> dict[str, Any] | None:
        for key, payload in payloads.items():
            if key in url:
                return payload
        return None

    monkeypatch.setattr(thoi_tiet_mod, "_http_get_json", fake_get)


def test_hom_nay_voi_gps(monkeypatch: pytest.MonkeyPatch) -> None:
    set_store_profile({"lat": 10.7756, "lon": 106.7019})
    from datetime import datetime as _dt

    ngay = _dt.now(thoi_tiet_mod._VN_TZ).date().isoformat()
    _mock_http(
        monkeypatch,
        {
            "api.open-meteo.com": {
                "current": {
                    "temperature_2m": 31.2,
                    "relative_humidity_2m": 70,
                    "precipitation": 0.0,
                    "weather_code": 1,
                },
                "hourly": {
                    "time": [f"{ngay}T{h:02d}:00" for h in range(24)],
                    "temperature_2m": [28 + (h % 5) for h in range(24)],
                    "weather_code": [1 if h < 14 else 61 for h in range(24)],
                    "precipitation": [0.0 if h < 14 else 1.2 for h in range(24)],
                },
            },
        },
    )

    r = client.get("/api/v1/thoi-tiet/hom-nay", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["co_du_lieu"] is True
    assert body["vi_tri"]["nguon"] == "gps"
    assert body["hien_tai"]["nhom"] == "nang"
    assert body["anh_huong_quan"]["tom_tat"]


def test_hom_nay_voi_tinh_thanh(monkeypatch: pytest.MonkeyPatch) -> None:
    set_store_profile({"tinh": "Hồ Chí Minh", "thanh_pho": "Quận 1"})
    from datetime import datetime as _dt

    ngay = _dt.now(thoi_tiet_mod._VN_TZ).date().isoformat()
    _mock_http(
        monkeypatch,
        {
            "geocoding-api.open-meteo.com": {
                "results": [
                    {
                        "name": "Quận 1",
                        "admin1": "Hồ Chí Minh",
                        "latitude": 10.7756,
                        "longitude": 106.7019,
                    }
                ]
            },
            "api.open-meteo.com": {
                "current": {
                    "temperature_2m": 31.2,
                    "relative_humidity_2m": 70,
                    "precipitation": 0.0,
                    "weather_code": 1,
                },
                "hourly": {
                    "time": [f"{ngay}T{h:02d}:00" for h in range(24)],
                    "temperature_2m": [28 + (h % 5) for h in range(24)],
                    "weather_code": [1 if h < 14 else 61 for h in range(24)],
                    "precipitation": [0.0 if h < 14 else 1.2 for h in range(24)],
                },
            },
        },
    )

    r = client.get("/api/v1/thoi-tiet/hom-nay", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["co_du_lieu"] is True
    assert body["vi_tri"]["thanh_pho"]
    assert body["hien_tai"]["nhom"] == "nang"
    assert isinstance(body["theo_gio"], list) and len(body["theo_gio"]) >= 10
    assert body["anh_huong_quan"]["tom_tat"]
    assert body["nguon"] == "open-meteo"

    # Lần 2 phải lấy từ cache.
    r2 = client.get("/api/v1/thoi-tiet/hom-nay", headers=headers(client, "lan"))
    assert r2.json().get("tu_cache") is True


def test_profile_co_lat_lon_va_tinh_thanh() -> None:
    ql = headers(client, "lan")
    r = client.put(
        "/api/v1/store/profile",
        json={
            "ten_quan": "Café Test",
            "dia_chi": "45 Nguyễn Huệ",
            "tinh": "Hồ Chí Minh",
            "thanh_pho": "Quận 1",
            "lat": 10.7756,
            "lon": 106.7019,
            "hotline": "0901234567",
            "gio_mo_cua": "07:00-22:00",
        },
        headers=ql,
    )
    assert r.status_code == 200, r.text
    got = client.get("/api/v1/store/profile", headers=ql).json()
    assert got["tinh"] == "Hồ Chí Minh"
    assert got["thanh_pho"] == "Quận 1"
    assert abs(float(got["lat"]) - 10.7756) < 0.001
    assert abs(float(got["lon"]) - 106.7019) < 0.001
