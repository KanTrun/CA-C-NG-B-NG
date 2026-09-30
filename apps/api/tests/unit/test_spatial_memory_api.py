"""Spatial Memory API tests (Phase 05)."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.spatial_memory import clear_spatial_state
from ca_api.persist import init_db
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    clear_spatial_state()


def test_map_lists_anchors() -> None:
    r = client.get("/api/v1/experience/map", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    ids = {a["anchor_id"] for a in r.json()["anchors"]}
    assert {"bar", "blender-02", "espresso-machine-01"} <= ids


def test_anchor_details_confirmed_and_pending() -> None:
    r = client.get("/api/v1/experience/anchors/bar", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(m["memory_id"] == "mem_bar_01" for m in body["confirmed_memories"])
    assert any(m["memory_id"] == "mem_bar_draft_01" for m in body["pending_memories"])


def test_anchor_not_found() -> None:
    r = client.get("/api/v1/experience/anchors/khong_co", headers=headers(client, "lan"))
    assert r.status_code == 404


def test_memories_filter_by_status() -> None:
    r = client.get("/api/v1/experience/memories", params={"status": "confirmed"}, headers=headers(client, "lan"))
    assert r.status_code == 200
    assert all(m["status"] == "confirmed" for m in r.json()["memories"])


def test_memories_bad_status_422() -> None:
    r = client.get("/api/v1/experience/memories", params={"status": "sai"}, headers=headers(client, "lan"))
    assert r.status_code == 422


def test_memory_propose_creates_draft() -> None:
    r = client.post(
        "/api/v1/experience/memories/propose",
        json={
            "proposal_id": "p1",
            "anchor_id": "bar",
            "content": "khách đoàn thích nước suối",
            "owner_scope": "staff_nv",
            "visibility": "staff",
            "proposed_by": "lan",
            "source_event_ids": ["ev_1"],
            "snapshot_hash": "snap_20260918_spatial_001",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending"] is True
    assert body["memory"]["status"] == "draft"


def test_consent_confirm_memory() -> None:
    # Tạo draft rồi consent
    prop = client.post(
        "/api/v1/experience/memories/propose",
        json={
            "proposal_id": "p2",
            "anchor_id": "bar",
            "content": "khách ghi chú fixture",
            "owner_scope": "staff",
            "visibility": "staff",
            "proposed_by": "lan",
            "snapshot_hash": "snap_20260918_spatial_001",
        },
        headers=headers(client, "lan"),
    ).json()["memory"]["memory_id"]
    r = client.post(
        f"/api/v1/experience/memories/{prop}/consent",
        json={"grant": True},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["consent_status"] == "granted"
    assert r.json()["status"] == "confirmed"


def test_consent_revoke_excludes_retrieval() -> None:
    # Revoke memory có sẵn
    r = client.post(
        "/api/v1/experience/memories/mem_bar_01/consent",
        json={"grant": False},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200
    mems = client.get("/api/v1/experience/memories", headers=headers(client, "lan")).json()["memories"]
    ids = [m["memory_id"] for m in mems]
    assert "mem_bar_01" not in ids


def test_delete_memory() -> None:
    r = client.delete("/api/v1/experience/memories/mem_blender_01", headers=headers(client, "lan"))
    assert r.status_code == 200
    mems = client.get("/api/v1/experience/memories", headers=headers(client, "lan")).json()["memories"]
    assert "mem_blender_01" not in {m["memory_id"] for m in mems}


def test_clear_spatial_state_dung_lai_kho_ky_uc() -> None:
    """`clear_spatial_state` phải dựng lại kho, không chỉ xoá bộ đếm tần suất.

    Vì sao có bài này: `_REPO_STORE` là biến toàn cục sống suốt phiên server, và
    `consent` sửa thẳng vào đối tượng trong đó. Bản đầu chỉ gọi `_USER_TS.clear()`
    nên consent cấp cho bản nháp `mem_bar_draft_01` sống mãi qua mọi lần reset.

    Hệ quả thật: fixture khai `mem_bar_draft_01` là draft chờ consent, nên neo
    `bar` chỉ có ĐÚNG 1 ký ức đã xác nhận. Sau khi bị làm bẩn, neo `bar` có 2 →
    bài `grand-experience-replay` khẳng định trích dẫn chứa "1" đỏ, và vì trạng
    thái nằm trong tiến trình đang chạy nên nó **đỏ cả khi chạy một mình**.

    Bài này chứng minh bản sửa chịu tải: làm bẩn kho, gọi clear, đo lại.
    """
    def so_ky_uc_da_xac_nhan_o_bar() -> int:
        r = client.get(
            "/api/v1/experience/memories",
            params={"status": "confirmed"},
            headers=headers(client, "lan"),
        )
        assert r.status_code == 200, r.text
        return sum(1 for m in r.json()["memories"] if m["anchor_id"] == "bar")

    # Điểm xuất phát: đúng fixture — chỉ `mem_bar_01`.
    assert so_ky_uc_da_xac_nhan_o_bar() == 1

    # Làm bẩn: cấp consent cho bản nháp ở cùng neo.
    r = client.post(
        "/api/v1/experience/memories/mem_bar_draft_01/consent",
        json={"grant": True},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    assert so_ky_uc_da_xac_nhan_o_bar() == 2, "consent phải đưa bản nháp thành đã xác nhận"

    # Bản sửa phải dọn được. Nếu chỉ xoá bộ đếm tần suất thì vẫn là 2 → đỏ.
    clear_spatial_state()
    assert so_ky_uc_da_xac_nhan_o_bar() == 1, (
        "clear_spatial_state chua dung lai kho ky uc — consent song qua reset"
    )


def test_tour_start_grounded() -> None:
    """Tour dựng TỪ NEO THẬT (có ký ức xác nhận), không phải route mẫu cứng."""
    r = client.post("/api/v1/experience/tour/start", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    # Có ký ức xác nhận trong fixture → tour bám theo neo thật, không dùng route mẫu.
    assert body["tour_id"] == "tour_that"
    assert len(body["steps"]) >= 2
    assert body["grounded"] is True


def test_voice_turn_answer_grounded() -> None:
    r = client.post(
        "/api/v1/experience/voice/turn",
        json={
            "conversation_id": "c1",
            "transcript": "khách thích gì ở quầy pha chế?",
            "anchor_id": "bar",
            "requester_id": "lan",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grounded"] is True
    assert body["response_text"]
    assert body["citations"]


def test_voice_turn_remember_proposes_memory() -> None:
    r = client.post(
        "/api/v1/experience/voice/turn",
        json={
            "conversation_id": "c2",
            "transcript": "nhớ điều này: khách đoàn thích ngồi gần cửa sổ",
            "anchor_id": "window_table",
            "requester_id": "lan",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal"] is not None
    assert body["proposal"]["anchor_id"] == "window_table"


def test_voice_turn_remember_persists_draft_and_flows_to_consent() -> None:
    """Voice "nhớ điều này…" phải để lại draft DUYỆT ĐƯỢC — không bay màu.

    Bản trước `voice/turn` trả proposal trong response rồi thôi: không lưu vào
    kho nên draft không hiện ở "Chờ quyết định" của neo, quản lý không có gì để
    duyệt, và UI khẳng định "chờ quản lý xác nhận" là lời hứa suông. Luồng ghi
    ký ức gãy giữa chừng ngay tại bước này.

    Bài này chặn hồi quy cho toàn chuỗi: nói → có draft → duyệt → thành
    confirmed → answer có citations từ ký ức vừa duyệt.
    """
    # (1) Nói "nhớ điều này…" ở neo cửa vào.
    r = client.post(
        "/api/v1/experience/voice/turn",
        json={
            "conversation_id": "c_remember_persist",
            "transcript": "nhớ điều này: khách hay để xe ở hàng ghế trước cửa vào",
            "anchor_id": "entrance",
            "requester_id": "lan",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    proposal = r.json()["proposal"]
    assert proposal is not None
    proposal_id = proposal["proposal_id"]

    # (2) Draft phải THẬT sự nằm trong kho — hiện ở pending của neo.
    details = client.get(
        "/api/v1/experience/anchors/entrance",
        headers=headers(client, "lan"),
    )
    assert details.status_code == 200, details.text
    pending = details.json()["pending_memories"]
    assert any(
        m["memory_id"] == f"mem_prop_{proposal_id}" and m["status"] == "draft"
        for m in pending
    ), "draft từ voice phải nằm trong danh sách chờ duyệt của neo"

    # (3) Quản lý duyệt → thành confirmed.
    r = client.post(
        f"/api/v1/experience/memories/mem_prop_{proposal_id}/consent",
        json={"grant": True},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    # (4) Lượt hỏi sau đó PHẢI trả lời được từ ký ức vừa duyệt.
    r = client.post(
        "/api/v1/experience/voice/turn",
        json={
            "conversation_id": "c_remember_persist_2",
            "transcript": "ở cửa vào có gì đáng nhớ?",
            "anchor_id": "entrance",
            "requester_id": "lan",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grounded"] is True
    assert f"mem_prop_{proposal_id}" in body["citations"]


def test_voice_turn_no_confirmed_no_hallucination() -> None:
    r = client.post(
        "/api/v1/experience/voice/turn",
        json={
            "conversation_id": "c3",
            "transcript": "chuyện gì đã xảy ra ở đây?",
            "anchor_id": "stockroom",
            "requester_id": "lan",
        },
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Kho không có memory confirmed → không bịa chuyện
    assert "Chưa có ký ức đã xác nhận" in body["response_text"]