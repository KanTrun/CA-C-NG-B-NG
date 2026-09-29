"""War Room API tests — Phase 02."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.war_room import clear_war_room_state
from ca_api.persist import init_db
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

SNAP = "snap_fixture_demand_20260918"

SCENARIOS = [
    {
        "scenario_id": "s_demand",
        "loai": "demand_surge",
        "tham_so": {"ty_le_gia_tang": 1.3},
    },
    {
        "scenario_id": "s_staff",
        "loai": "add_staff_to_shift",
        "tham_so": {"ca_id": "t7_toi", "thu": "T7", "khung": "toi"},
    },
]


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    clear_war_room_state()


def _simulate(role: str = "lan") -> dict:
    r = client.post(
        "/api/v1/experience/war-room/simulate",
        json={
            "request_id": "req_demo_1",
            "baseline_snapshot": SNAP,
            "scenarios": SCENARIOS,
            "requested_by": "quan_ly_test",
        },
        headers=headers(client, role),
    )
    return r


def test_simulate_requires_manager() -> None:
    r = _simulate(role="minh")
    assert r.status_code == 403


def test_simulate_returns_comparison() -> None:
    r = _simulate()
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["options"]) >= 2
    assert body["replayable"] is True
    assert "simulation_id" in body
    assert "baseline_snapshot_hash" in body


def test_simulate_live_tinh_tren_lich_tuan_that() -> None:
    """War Room mô phỏng trên LỊCH TUẦN THẬT: số ca lấy từ phân công thật."""
    from ca_api.persist import kv_set

    week = "2026-W40"
    kv_set("phan_cong_by_week", {week: {"w1_c01": ["nv_01"], "w1_c04": ["nv_02"]}})
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "nhap"}})

    r = client.post(
        "/api/v1/experience/war-room/simulate-live",
        json={},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["co_du_lieu"] is True
    assert body["nguon"] == "lich_tuan"
    assert body["baseline"]["tuan_iso"] == week
    # w1_c01 cần 2 người, chỉ có 1 → thiếu; phải có phương án xử lý ca thiếu.
    assert body["baseline"]["chi_so"]["so_ca_thieu"] >= 1
    ids = {o["option_id"] for o in body["options"]}
    assert "opt_giu_nguyen" in ids
    assert any(o["option_id"] in {"opt_tang_nguoi", "opt_dieu_chuyen"} for o in body["options"])
    for o in body["options"]:
        assert o.get("reason"), "phương án trên dữ liệu thật vẫn phải có lời giải thích"


def test_simulate_live_khong_co_lich_tra_co_du_lieu_false() -> None:
    """Chưa xếp lịch tuần → co_du_lieu=False (UI rơi về mô phỏng mẫu)."""
    r = client.post(
        "/api/v1/experience/war-room/simulate-live",
        json={"tuan_iso": "1999-W01"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200
    assert r.json()["co_du_lieu"] is False


def test_moi_phuong_an_co_loi_giai_thich() -> None:
    """Bấm 'Đề xuất' phải thấy nội dung, không chỉ số khô.

    Ở replay, lời giải thích là bản TẤT ĐỊNH (không gọi LLM) nhưng vẫn phải có.
    """
    r = _simulate()
    options = r.json()["options"]
    for opt in options:
        assert opt.get("reason"), f"phương án {opt['option_id']} thiếu lời giải thích"
        assert opt.get("reason_provider") == "replay"


def test_get_scenarios_after_simulate() -> None:
    r = _simulate()
    sim_id = r.json()["simulation_id"]
    g = client.get(
        f"/api/v1/experience/war-room/scenarios/{sim_id}",
        headers=headers(client, "lan"),
    )
    assert g.status_code == 200, g.text
    assert len(g.json()["options"]) >= 2


def test_propose_option() -> None:
    sim_id = _simulate().json()["simulation_id"]
    option_id = _simulate().json()["options"][0]["option_id"]
    p = client.post(
        f"/api/v1/experience/war-room/{sim_id}/propose",
        json={
            "option_id": option_id,
            "expected_snapshot_hash": "snap_12345678",
        },
        headers=headers(client, "lan"),
    )
    assert p.status_code == 200, p.text
    assert p.json()["proposal"]["status"] == "draft"


def test_propose_missing_option_404() -> None:
    sim_id = _simulate().json()["simulation_id"]
    p = client.post(
        f"/api/v1/experience/war-room/{sim_id}/propose",
        json={"option_id": "khong_co", "expected_snapshot_hash": "snap_12345678"},
        headers=headers(client, "lan"),
    )
    assert p.status_code == 404


def test_confirm_manager_only() -> None:
    sim_id = _simulate().json()["simulation_id"]

    r_emp = client.post(
        f"/api/v1/experience/war-room/{sim_id}/confirm",
        headers=headers(client, "minh"),
    )
    assert r_emp.status_code == 403

    r_mgr = client.post(
        f"/api/v1/experience/war-room/{sim_id}/confirm",
        headers=headers(client, "lan"),
    )
    assert r_mgr.status_code == 200, r_mgr.text
    assert r_mgr.json()["mutation"] == "none"


def test_same_request_id_idempotent() -> None:
    a = _simulate().json()
    b = _simulate().json()
    assert a["simulation_id"] == b["simulation_id"]
    assert a["options"] == b["options"]


def test_no_apply_endpoint() -> None:
    """KHÔNG được phép tồn tại POST apply bỏ qua proposal."""
    from ca_api.interfaces.http.main import app as app_obj

    paths = {getattr(r, "path", "") for r in app_obj.routes}
    assert not any("/war-room" in p and "apply" in p for p in paths)