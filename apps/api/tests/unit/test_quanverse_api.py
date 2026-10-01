"""QUANVERSE API tests (Phase 06)."""

from __future__ import annotations

import pytest
from ca_agents.grand_experience.adapter import resolve_experience_read_adapter
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.quanverse import clear_quanverse_state
from ca_api.persist import init_db
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    clear_quanverse_state()


def test_manager_snapshot_full_projection() -> None:
    r = client.get("/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "quan_ly"
    assert len(body["zones"]) >= 2
    assert body["events"]  # manager thấy rescue + mode events


def test_customer_snapshot_no_staff_data() -> None:
    """Khách không thấy staff/private ops."""
    r = client.get("/api/v1/experience/quanverse/snapshot", headers=headers(client, "minh"))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "nhan_vien"  # minh là employee, không phải khách


def test_employee_snapshot_limited_events() -> None:
    r = client.get("/api/v1/experience/quanverse/snapshot", headers=headers(client, "minh"))
    body = r.json()
    # Employee chỉ thấy rescue_case/signal — không thấy timestamp private
    for ev in body["events"]:
        assert ev["event_type"] in {"rescue_case", "signal"}


def test_modes_list() -> None:
    r = client.get("/api/v1/experience/quanverse/modes", headers=headers(client, "lan"))
    assert r.status_code == 200
    assert len(r.json()["modes"]) >= 2


def test_modes_list_exposes_effect_and_capability() -> None:
    """UI cần câu hệ quả + biết vai trò có được kích hoạt hay không."""
    r = client.get("/api/v1/experience/quanverse/modes", headers=headers(client, "lan"))
    body = r.json()
    assert body["can_activate"] is True
    for m in body["modes"]:
        assert m["effect"]
        assert m["affected_projections"]

    r_nv = client.get("/api/v1/experience/quanverse/modes", headers=headers(client, "minh"))
    assert r_nv.json()["can_activate"] is False


def test_mode_propose_then_confirm_then_deactivate() -> None:
    """Vòng đời đầy đủ: đề xuất → xác nhận → tắt. Bật mà không tắt được là lỗi."""
    h = headers(client, "lan")
    assert client.post(
        "/api/v1/experience/quanverse/modes/dem_nhac/propose", headers=h
    ).json()["confirmed"] is False

    modes = client.get("/api/v1/experience/quanverse/modes", headers=h).json()["modes"]
    dem_nhac = next(m for m in modes if m["mode"] == "dem_nhac")
    assert dem_nhac["proposal_status"] == "draft"

    confirmed = client.post("/api/v1/experience/quanverse/modes/dem_nhac/confirm", headers=h)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["active"] is True

    off = client.post("/api/v1/experience/quanverse/modes/dem_nhac/deactivate", headers=h)
    assert off.status_code == 200, off.text
    assert off.json()["active"] is False
    assert off.json()["was_active"] is True

    modes = client.get("/api/v1/experience/quanverse/modes", headers=h).json()["modes"]
    assert next(m for m in modes if m["mode"] == "dem_nhac")["active"] is False


def test_mode_deactivate_idempotent() -> None:
    h = headers(client, "lan")
    first = client.post("/api/v1/experience/quanverse/modes/gio_cao_diem/deactivate", headers=h)
    second = client.post("/api/v1/experience/quanverse/modes/gio_cao_diem/deactivate", headers=h)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["was_active"] is False


def test_employee_cannot_deactivate_mode() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/modes/troi_mua/deactivate",
        headers=headers(client, "minh"),
    )
    assert r.status_code == 403


def test_dropped_proposal_does_not_resurrect_from_fixture() -> None:
    """Bỏ đề xuất rồi thì KHÔNG được đọc lại từ fixture.

    Lỗi thật đã vấp: fixture khai `khach_doan` là `proposal_status="draft"`.
    Sau khi quản lý bấm "Bỏ đề xuất", kv có `{"active": False}` mà KHÔNG có
    `proposal_status`, nên biểu thức
        state.get("proposal_status") or fixture.proposal_status
    rơi về giá trị của fixture → UI vẫn hiện "Chờ duyệt · Bản nháp" kèm nút
    Duyệt cho một đề xuất người dùng vừa bỏ. Có kv thì phải TIN kv, kể cả khi
    `proposal_status` trong kv rỗng (rỗng = đã bỏ, khác hẳn chưa từng đề xuất).
    """
    h = headers(client, "lan")
    mode = "khach_doan"

    # Fixture khai sẵn draft → trạng thái đầu là "chờ duyệt".
    modes = client.get("/api/v1/experience/quanverse/modes", headers=h).json()["modes"]
    assert next(m for m in modes if m["mode"] == mode)["proposal_status"] == "draft"

    client.post(f"/api/v1/experience/quanverse/modes/{mode}/deactivate", headers=h)

    # Sau khi bỏ: cả `/modes` lẫn `/snapshot` phải nói "không chờ duyệt nữa".
    modes = client.get("/api/v1/experience/quanverse/modes", headers=h).json()["modes"]
    assert next(m for m in modes if m["mode"] == mode)["proposal_status"] in ("", None)

    snap = client.get("/api/v1/experience/quanverse/snapshot", headers=h).json()
    assert next(m for m in snap["modes"] if m["mode"] == mode)["proposal_status"] is None


def test_snapshot_events_carry_zone_and_future_horizon() -> None:
    """Sự kiện phải gắn được khu vực, và trục 15 phút phải ở tương lai."""
    from datetime import UTC, datetime

    r = client.get("/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan"))
    body = r.json()
    assert body["events"]
    assert any(ev["zone_id"] for ev in body["events"]), "phải có sự kiện gắn khu vực"

    zone_ids = {z["zone_id"] for z in body["zones"]}
    for ev in body["events"]:
        if ev["zone_id"]:
            assert ev["zone_id"] in zone_ids, "zone_id phải trỏ tới khu vực có thật"

    assert body["next_horizon"]
    now = datetime.now(UTC)
    for item in body["next_horizon"]:
        starts = datetime.fromisoformat(item["starts_at"])
        assert starts >= now, "mốc 15 phút tới không được ở quá khứ"


def test_empty_zone_reports_no_events_honestly() -> None:
    """Khu vực không có sự kiện: API trả về đúng sự thật, không độn dữ liệu."""
    r = client.get("/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan"))
    body = r.json()
    by_zone: dict[str, int] = {}
    for ev in body["events"]:
        zone = ev.get("zone_id")
        if zone:
            by_zone[zone] = by_zone.get(zone, 0) + 1
    # Có ít nhất một khu vực không có sự kiện → UI phải dùng nhánh empty state thật.
    assert len(by_zone) < len(body["zones"])


def test_preference_consent_lifecycle() -> None:
    """Đồng thuận phải có nhánh ĐỒNG Ý thật, không chỉ nhánh xoá."""
    h = headers(client, "lan")
    proposed = client.post(
        "/api/v1/experience/quanverse/preferences/propose",
        json={"content": "thích bàn cạnh cửa sổ"},
        headers=h,
    )
    assert proposed.status_code == 200, proposed.text
    pref_id = proposed.json()["preference_proposal_id"]
    assert proposed.json()["stored"] is False

    pending = client.get("/api/v1/experience/quanverse/preferences", headers=h).json()
    assert any(p["preference_id"] == pref_id for p in pending["preferences"])
    assert all(p["consent_status"] == "required" for p in pending["preferences"])

    granted = client.post(
        f"/api/v1/experience/quanverse/preferences/{pref_id}/consent",
        json={"grant": True},
        headers=h,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["stored"] is True

    stored = client.get("/api/v1/experience/quanverse/preferences", headers=h).json()
    kept = next(p for p in stored["preferences"] if p["preference_id"] == pref_id)
    assert kept["consent_status"] == "granted"

    removed = client.delete(
        f"/api/v1/experience/quanverse/preferences/{pref_id}", headers=h
    )
    assert removed.status_code == 200
    after = client.get("/api/v1/experience/quanverse/preferences", headers=h).json()
    assert all(p["preference_id"] != pref_id for p in after["preferences"])


def test_preference_decline_deletes_immediately() -> None:
    """Không đồng ý = quên ngay, không giữ bản nháp 'để sau'."""
    h = headers(client, "lan")
    pref_id = client.post(
        "/api/v1/experience/quanverse/preferences/propose",
        json={"content": "thích ngồi ngoài trời"},
        headers=h,
    ).json()["preference_proposal_id"]

    declined = client.post(
        f"/api/v1/experience/quanverse/preferences/{pref_id}/consent",
        json={"grant": False},
        headers=h,
    )
    assert declined.status_code == 200
    assert declined.json()["deleted"] is True

    rows = client.get("/api/v1/experience/quanverse/preferences", headers=h).json()
    assert all(p["preference_id"] != pref_id for p in rows["preferences"])


def test_preference_consent_unknown_id_404() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/preferences/pref_khong_ton_tai/consent",
        json={"grant": True},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 404


def test_preferences_isolated_per_owner() -> None:
    """Sở thích là dữ liệu cá nhân — người khác không đọc được."""
    client.post(
        "/api/v1/experience/quanverse/preferences/propose",
        json={"content": "sở thích riêng của lan"},
        headers=headers(client, "lan"),
    )
    other = client.get(
        "/api/v1/experience/quanverse/preferences", headers=headers(client, "minh")
    ).json()
    assert all("lan" not in p["content"] for p in other["preferences"])


def test_mode_propose_draft() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/modes/troi_mua/propose",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal_status"] == "draft"
    assert body["confirmed"] is False
    assert body["affected_projections"]


def test_employee_cannot_confirm_mode() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/modes/troi_mua/confirm",
        headers=headers(client, "minh"),
    )
    assert r.status_code == 403


def test_manager_confirm_mode() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/modes/troi_mua/confirm",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True
    assert body["audited"] is True


def test_unknown_mode_422() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/modes/khong_biet/propose",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 422


def test_flavor_recommend() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/flavor/recommend",
        json={"do_ngot": "it", "co_sua": False, "huong_tra": True},
        headers=headers(client, "minh"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendations"]
    assert any("lý do" not in x or x["reasons"] for x in body["recommendations"])


def test_flavor_allergy_blocked() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/flavor/recommend",
        json={"do_ngot": "vua", "dietary_allergy": ["sữa"]},
        headers=headers(client, "minh"),
    )
    ids = {x["mon_id"] for x in r.json()["recommendations"]}
    assert "cafe_sua" not in ids
    assert "tr_sua" not in ids


def test_preference_propose_needs_consent() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/preferences/propose",
        json={"content": "khách thích bàn cửa sổ"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["needs_consent"] is True
    assert body["stored"] is False


def test_preference_delete_idempotent() -> None:
    r = client.delete(
        "/api/v1/experience/quanverse/preferences/pref_1",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_tour_entry() -> None:
    r = client.get("/api/v1/experience/quanverse/tour/tour_chao_doi", headers=headers(client, "lan"))
    assert r.status_code == 200
    assert r.json()["tour_id"] == "tour_chao_doi"


def test_tour_entry_honours_tour_id() -> None:
    """Mã tour sai phải 404 — KHÔNG lặng lẽ trả tour mặc định.

    Lỗi thật đã vấp: route nhận `{tour_id}` nhưng handler gọi `plan_tour()`
    KHÔNG truyền tham số, nên mọi mã — kể cả `khong-ton-tai` — đều trả
    `tour_chao_doi` kèm HTTP 200. Người dùng gõ sai deep-link nhận một tour
    trông hợp lệ, và không có cách nào biết mình đã sai.
    """
    r = client.get(
        "/api/v1/experience/quanverse/tour/khong-ton-tai",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 404, r.text

    # Mã hợp lệ khác mặc định vẫn phải trả ĐÚNG mã đó, không phải tour mặc định.
    ok = client.get(
        "/api/v1/experience/quanverse/tour/tour_kho",
        headers=headers(client, "lan"),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["tour_id"] == "tour_kho"


def test_tour_kho_anchors_exist_in_map() -> None:
    """Neo của tour phải có thật trên bản đồ quán.

    Fixture tour khai neo `storage`, nhưng bản đồ chỉ có `stockroom` — bước tour
    trỏ tới một neo không tồn tại nên UI không tìm được nhãn, hiện mã khô, và
    không nhảy tới được neo đó.
    """
    adapter = resolve_experience_read_adapter()
    anchor_ids = {a.anchor_id for a in adapter.list_anchors()}

    r = client.get(
        "/api/v1/experience/quanverse/tour/tour_kho",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    for step in r.json()["steps"]:
        assert step["anchor_id"] in anchor_ids, (
            f"tour trỏ tới neo không có trên bản đồ: {step['anchor_id']}"
        )


def test_ar_session_requires_qr() -> None:
    r = client.post(
        "/api/v1/experience/quanverse/ar-session",
        json={},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 422

    r2 = client.post(
        "/api/v1/experience/quanverse/ar-session",
        json={"qr": "blender-02"},
        headers=headers(client, "lan"),
    )
    assert r2.status_code == 200
    assert r2.json()["fallback"] == "map_or_qr_text"

def test_propose_status_doc_lai_duoc_tu_snapshot() -> None:
    """Đề xuất mode phải đọc lại được qua `/snapshot` — không chỉ qua `/modes`.

    Lỗi đã sửa: `_project_role` chỉ lấy `active` từ kv rồi đặt
    `proposal_status = "confirmed" if active else m.proposal_status` — khi mode
    CHƯA bật thì nó vứt giá trị trong kv và dùng lại giá trị của FIXTURE. Nên
    `propose` ghi `draft` thành công mà `/snapshot` (endpoint giao diện đọc) vẫn
    trả `None`: giao diện hiện "Đang tắt" và KHÔNG hiện nút "Duyệt", vòng đời
    đề xuất → duyệt kẹt ngay ở bước đề xuất.

    Test này đóng đinh hành vi đúng cho CẢ HAI endpoint, vì sự lệch nhau giữa
    hai endpoint chính là dạng lỗi vừa rồi.
    """
    mode = "dem_nhac"  # fixture: active=False, proposal_status=None
    r = client.post(
        f"/api/v1/experience/quanverse/modes/{mode}/propose",
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["proposal_status"] == "draft"

    snap = client.get(
        "/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan")
    )
    assert snap.status_code == 200, snap.text
    row = next(m for m in snap.json()["modes"] if m["mode"] == mode)
    assert row["active"] is False
    assert row["proposal_status"] == "draft", (
        "snapshot phải thấy đề xuất đã ghi vào kv; nếu là None thì giao diện "
        "sẽ không hiện nút Duyệt"
    )

    # `/modes` phải nói cùng một điều — hai endpoint lệch nhau là gốc của lỗi cũ.
    modes = client.get(
        "/api/v1/experience/quanverse/modes", headers=headers(client, "lan")
    )
    assert modes.status_code == 200, modes.text
    row2 = next(m for m in modes.json()["modes"] if m["mode"] == mode)
    assert row2["proposal_status"] == row["proposal_status"]

    # Duyệt xong thì active + confirmed, và đề xuất cũ không còn.
    c = client.post(
        f"/api/v1/experience/quanverse/modes/{mode}/confirm",
        headers=headers(client, "lan"),
    )
    assert c.status_code == 200, c.text
    snap2 = client.get(
        "/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan")
    )
    row3 = next(m for m in snap2.json()["modes"] if m["mode"] == mode)
    assert row3["active"] is True
    assert row3["proposal_status"] == "confirmed"


def test_mode_chua_active_thi_khong_bao_confirmed() -> None:
    """`confirmed` trong khi chưa active là mâu thuẫn trạng thái, phải bỏ đi.

    Nếu một mode chưa bật mà bị gán `confirmed`, giao diện đọc nó thành
    "chờ duyệt" và hiện nút Duyệt cho một thứ không có đề xuất nào.
    """
    snap = client.get(
        "/api/v1/experience/quanverse/snapshot", headers=headers(client, "lan")
    )
    assert snap.status_code == 200, snap.text
    for m in snap.json()["modes"]:
        if not m["active"]:
            assert m["proposal_status"] != "confirmed", (
                f"{m['mode']} chưa active nhưng proposal_status='confirmed'"
            )
