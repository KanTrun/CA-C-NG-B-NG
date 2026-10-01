"""Quanverse 2.0 — Evidence / JEV judge / Demo Setup (không mock riêng)."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.quanverse import clear_quanverse_state
from ca_api.persist import init_db, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup() -> None:
    init_db()
    clear_quanverse_state()
    # Trắng hoá 3 nguồn để kiểm S3 trước.
    kv_set("phan_cong_by_week", {})
    kv_set("tieu_thu", [])
    kv_set("viec_treo", [])
    with client:
        pass


def _xoa_don_that() -> None:
    from ca_api.persist import _conn

    with _conn() as cx:
        cx.execute("DELETE FROM don_quay")


def test_evidence_trong_khi_chua_co_du_lieu() -> None:
    _xoa_don_that()
    r = client.get("/api/v1/experience/quanverse/evidence", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trang_thai"] == "trong"
    assert body["coverage"] == {"don": "thieu", "lich": "thieu", "kho": "thieu"}
    assert {c["id"] for c in body["candidates"]} == {"A", "B", "C", "D", "E"}


def test_jev_judge_khong_goi_khi_trong() -> None:
    _xoa_don_that()
    r = client.post("/api/v1/experience/quanverse/jev-judge", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jev"]["goi_jev"] is False
    assert body["jev"]["ly_do"] == "insufficient"


def test_demo_setup_tao_ban_ghi_that_va_judge_du() -> None:
    _xoa_don_that()
    h = headers(client, "lan")
    s = client.post("/api/v1/experience/quanverse/demo-setup", headers=h)
    assert s.status_code == 200, s.text
    assert s.json()["orders_total_demo"] == 10

    ev = client.get("/api/v1/experience/quanverse/evidence", headers=h).json()
    assert ev["trang_thai"] == "du"
    assert ev["coverage"] == {"don": "ok", "lich": "ok", "kho": "ok"}
    assert ev["state"]["don_dang_xu_ly"] == 7

    jd = client.post("/api/v1/experience/quanverse/jev-judge", headers=h).json()
    assert jd["jev"]["goi_jev"] is True
    assert jd["jev"]["verdict"] in {"binh_thuong", "theo_doi", "can_xu_ly", "khan_cap"}
    # Rank chỉ trong closed-set, tối đa 3.
    ids = [x["id"] for x in jd["jev"]["ranking"]]
    assert len(ids) <= 3 and set(ids) <= {"A", "B", "C", "D", "E"}

    rs = client.post("/api/v1/experience/quanverse/demo-reset", headers=h)
    assert rs.status_code == 200


def test_demo_setup_doi_manager() -> None:
    h = headers(client, "minh")
    r = client.post("/api/v1/experience/quanverse/demo-setup", headers=h)
    assert r.status_code == 403
