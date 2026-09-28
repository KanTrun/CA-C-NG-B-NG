"""Shift Rescue API tests (Phase 03)."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.shift_rescue import clear_shift_rescue_state
from ca_api.persist import init_db
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    clear_shift_rescue_state()


def _intake(role: str = "lan") -> dict:
    r = client.post(
        "/api/v1/experience/shift-rescue/intake",
        json={
            "case_id": "rescue_e2e_1",
            "absence_nv_id": "nv_absent_quan",
            "shift_id": "t7_toi",
            "reason": "Ốm đột xuất",
        },
        headers=headers(client, role),
    )
    return r


def test_intake_requires_manager() -> None:
    r = _intake(role="minh")
    assert r.status_code == 403


def test_options_lists_shifts_with_assigned_staff() -> None:
    """UI cần chọn ca thật thay vì hardcode một kịch bản."""
    r = client.get(
        "/api/v1/experience/shift-rescue/options", headers=headers(client, "lan")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shifts"], "phải có ít nhất một ca đang phân người"
    for shift in body["shifts"]:
        assert shift["shift_id"]
        assert shift["assigned"], "ca trả về phải có người, không thì báo vắng vô nghĩa"
        for person in shift["assigned"]:
            assert person["nv_id"]
            # Nhãn hiển thị phải đọc được, không rơi về mã thô khi fixture có tên.
            assert person["ten"]


def test_options_requires_auth() -> None:
    r = client.get("/api/v1/experience/shift-rescue/options")
    assert r.status_code == 401


def test_full_lifecycle_invite_respond_confirm() -> None:
    """Vòng đời đầy đủ — trước đây UI dừng ở invite nên case không bao giờ chốt."""
    h = headers(client, "lan")
    case_id = _intake().json()["case_id"]

    cands = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/candidates", headers=h
    )
    assert cands.status_code == 200, cands.text
    safe = cands.json()["candidates"]
    assert safe, "fixture phải có ít nhất một người an toàn"
    cand_id = safe[0]["candidate_id"]

    assert client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/propose",
        json={"candidate_id": cand_id},
        headers=h,
    ).status_code == 200

    invited = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/invite",
        json={"candidate_ids": [cand_id]},
        headers=h,
    )
    assert invited.status_code == 200, invited.text
    assert invited.json()["status"] == "invited"

    responded = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/respond",
        json={"candidate_id": cand_id, "accept": True},
        headers=h,
    )
    assert responded.status_code == 200, responded.text
    assert responded.json()["status"] == "responded"

    confirmed = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/confirm",
        json={"candidate_id": cand_id},
        headers=h,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["confirmed_candidate_id"] == cand_id


def test_decline_keeps_case_open_for_next_candidate() -> None:
    """Từ chối không được đóng ca — vẫn phải mời được người kế tiếp."""
    h = headers(client, "lan")
    case_id = _intake().json()["case_id"]
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/candidates", headers=h)
    safe = client.get(
        f"/api/v1/experience/shift-rescue/{case_id}", headers=h
    ).json()["candidates"]
    cand_id = safe[0]["candidate_id"]

    client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/propose",
        json={"candidate_id": cand_id},
        headers=h,
    )
    client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/invite",
        json={"candidate_ids": [cand_id]},
        headers=h,
    )
    declined = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/respond",
        json={"candidate_id": cand_id, "accept": False},
        headers=h,
    )
    assert declined.status_code == 200
    assert declined.json()["onboard_next_candidate"] is True
    # Vẫn ở INVITED để còn mời người khác.
    assert declined.json()["status"] == "invited"


def test_intake_creates_case() -> None:
    r = _intake()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reported"
    assert body["shift_id"] == "t7_toi"
    assert body["replayable"] is True


def test_intake_unknown_shift_422() -> None:
    r = client.post(
        "/api/v1/experience/shift-rescue/intake",
        json={"case_id": "c", "absence_nv_id": "nv_1", "shift_id": "khong_co"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 422


def test_intake_missing_fields_422() -> None:
    r = client.post(
        "/api/v1/experience/shift-rescue/intake",
        json={"case_id": "c"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 422


def test_candidates_generated() -> None:
    case_id = _intake().json()["case_id"]
    r = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/candidates",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "candidates_ready"
    # Ít nhất 1 safe + 1 blocked (người thiếu kỹ năng)
    assert len(body["candidates"]) >= 1
    assert any(c["safe"] for c in body["candidates"])


def test_candidates_not_found() -> None:
    r = client.post(
        "/api/v1/experience/shift-rescue/khong_co/candidates",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 404


def test_propose_only_safe() -> None:
    case_id = _intake().json()["case_id"]
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/candidates", headers=headers(client, "lan"))
    cand = client.get(f"/api/v1/experience/shift-rescue/{case_id}", headers=headers(client, "lan")).json()["candidates"][0]

    # propose candidate blocked → 409
    bad = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/propose",
        json={"candidate_id": "cand_khong_an_toan"},
        headers=headers(client, "lan"),
    )
    assert bad.status_code == 409

    good = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/propose",
        json={"candidate_id": cand["candidate_id"]},
        headers=headers(client, "lan"),
    )
    assert good.status_code == 200, good.text


def test_invite_idempotent() -> None:
    case_id = _intake().json()["case_id"]
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/candidates", headers=headers(client, "lan"))
    candidates = client.get(f"/api/v1/experience/shift-rescue/{case_id}", headers=headers(client, "lan")).json()["candidates"]
    ids = [c["candidate_id"] for c in candidates[:1]]

    r1 = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/invite",
        json={"candidate_ids": ids},
        headers=headers(client, "lan"),
    )
    r2 = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/invite",
        json={"candidate_ids": ids},
        headers=headers(client, "lan"),
    )
    assert r1.json()["invited"] == r2.json()["invited"]
    assert len(r1.json()["invited"]) == 1


def test_confirm_stale_snapshot_409() -> None:
    case_id = _intake().json()["case_id"]
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/candidates", headers=headers(client, "lan"))
    cand = client.get(f"/api/v1/experience/shift-rescue/{case_id}", headers=headers(client, "lan")).json()["candidates"][0]
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/propose", json={"candidate_id": cand["candidate_id"]}, headers=headers(client, "lan"))
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/invite", json={"candidate_ids": [cand["candidate_id"]]}, headers=headers(client, "lan"))
    client.post(f"/api/v1/experience/shift-rescue/{case_id}/respond", json={"candidate_id": cand["candidate_id"], "accept": True}, headers=headers(client, "lan"))

    # Giả lập stale: sửa snapshot hash trong case.
    from ca_api.interfaces.http.shift_rescue import _CASES

    _CASES[case_id]["command"]["schedule_snapshot_hash"] = "stale_hash"
    r = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/confirm",
        json={"candidate_id": cand["candidate_id"]},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 409


def test_confirm_employee_forbidden() -> None:
    case_id = _intake().json()["case_id"]
    r = client.post(
        f"/api/v1/experience/shift-rescue/{case_id}/confirm",
        json={"candidate_id": "x"},
        headers=headers(client, "minh"),
    )
    assert r.status_code == 403


def test_options_dung_du_lieu_that_khi_co_lich_tuan() -> None:
    """Có lịch tuần thật → cứu ca lấy ca/người THẬT, không dùng fixture."""
    from ca_api.persist import kv_set

    week = "2026-W40"
    # 2 ca thật có người, dựa trên seed `ca_mau_21` (w1_c01..).
    kv_set("phan_cong_by_week", {week: {"w1_c01": ["nv_that_01", "nv_that_02"], "w1_c04": ["nv_that_03"]}})
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "nhap"}})

    r = client.get(
        "/api/v1/experience/shift-rescue/options", headers=headers(client, "lan")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nguon"] == "lich_tuan", "phải dùng dữ liệu thật khi có lịch tuần"
    assert body["replayable"] is False
    ids = {s["shift_id"] for s in body["shifts"]}
    assert {"w1_c01", "w1_c04"} <= ids, "phải thấy đúng ca thật từ phân công"
    for shift in body["shifts"]:
        for person in shift["assigned"]:
            assert person["nv_id"].startswith("nv_that_"), "người phải là người thật trong ca"
