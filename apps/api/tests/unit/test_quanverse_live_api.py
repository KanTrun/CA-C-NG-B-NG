"""Quanverse live data — stations + forecast đọc dữ liệu THẬT (đơn quầy)."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import init_db
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")


def test_stations_chua_co_don_tra_co_du_lieu_false() -> None:
    r = client.get("/api/v1/experience/quanverse/stations", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "stations" in body
    assert body["co_du_lieu"] in (True, False)
    # Có 4 khu vận hành cơ bản, mỗi khu có tải + hàng chờ.
    assert len(body["stations"]) == 4
    for s in body["stations"]:
        assert {"zone_id", "tai", "hang_cho", "canh_bao"} <= set(s)


def test_forecast_tra_duong_theo_gio() -> None:
    r = client.get("/api/v1/experience/quanverse/forecast", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["series"]) == 16, "khung 07:00–22:00"
    gios = [s["gio"] for s in body["series"]]
    assert gios == list(range(7, 23))
    for s in body["series"]:
        assert s["nhu_cau"] >= 0
        assert s["hang_doi_du_bao"] >= 0


def test_stations_requires_auth() -> None:
    r = client.get("/api/v1/experience/quanverse/stations")
    assert r.status_code == 401


def test_forecast_requires_auth() -> None:
    r = client.get("/api/v1/experience/quanverse/forecast")
    assert r.status_code == 401
