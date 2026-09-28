# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from __future__ import annotations

from ca_api.interfaces.http.main import app
from ca_api.persist import kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_week_assignments_and_pins_are_isolated() -> None:
    kv_set(
        "lich_tuan_results_by_week",
        {
            "2026-W40": {
                "tuan_iso": "2026-W40",
                "ok": True,
                "status": "OPTIMAL",
                "phan_cong": {"w1_c01": ["nv_01"]},
                "kiem_tra": {"coverage": {"passed": True, "filled": 21, "total": 21}},
            },
            "2026-W41": {
                "tuan_iso": "2026-W41",
                "ok": True,
                "status": "OPTIMAL",
                "phan_cong": {"w1_c01": ["nv_02"]},
            },
        },
    )
    kv_set("pins_by_week", {"2026-W40": {"w1_c01|nv_01": True}})

    auth = headers(client, "lan")
    week_40 = client.get("/api/v1/lich-tuan?tuan=2026-W40", headers=auth).json()
    week_41 = client.get("/api/v1/lich-tuan?tuan=2026-W41", headers=auth).json()

    assert week_40["phan_cong"]["w1_c01"] == ["nv_01"]
    assert week_40["pins"] == [{"ca_id": "w1_c01", "nv_id": "nv_01"}]
    assert week_40["kiem_tra"]["coverage"]["filled"] == 21
    assert week_41["phan_cong"]["w1_c01"] == ["nv_02"]
    assert week_41["pins"] == []


def test_khong_hien_ca_thieu_cua_lan_xep_cu(
    _du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None
) -> None:
    """Bảng open_shifts tích luỹ: ca thiếu của LẦN XẾP CŨ không được hiện khi
    đã có lần xếp mới.

    Lỗi gốc: lịch W40 đủ người nhưng khối "Ca còn thiếu người" vẫn liệt kê hàng
    trăm ca cũ từ một lần xếp thất bại trước đó — user bị bắt ghim từng ca vô nghĩa.
    """
    from ca_api.persist import open_shift_create, schedule_run_create

    week = "2026-W43"
    old_run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={"a": 1},
        fingerprint="fp-old", idempotency_key="old-run", created_by="lan", status="computed",
    )
    open_shift_create(
        store_id="quan_01", schedule_run_id=str(old_run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    open_shift_create(
        store_id="quan_01", schedule_run_id=str(old_run["id"]), tuan_iso=week,
        ca_id="w1_c02", deadline_at="2026-11-01T00:00:00Z",
    )

    # Lần xếp MỚI (không có ca thiếu) — phải che ca thiếu của lần cũ.
    new_run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={"a": 2},
        fingerprint="fp-new", idempotency_key="new-run", created_by="lan", status="computed",
    )
    assert str(new_run["id"]) != str(old_run["id"])

    res = client.get(f"/api/v1/lich-tuan?tuan={week}", headers=headers(client, "lan")).json()
    assert str(res["schedule_run"]["id"]) == str(new_run["id"])
    assert res["open_shifts"] == [], "ca thiếu của lần xếp cũ phải bị ẩn"

    # Chợ đổi ca dùng endpoint KHÁC (`/api/v1/open-shifts`) — phải cùng luật,
    # không thì chợ vẫn hiện hàng trăm ca hết hạn dù lịch đã đủ người.
    cho = client.get(f"/api/v1/open-shifts?tuan_iso={week}", headers=headers(client, "lan")).json()
    assert cho["items"] == [], "chợ cũng phải ẩn ca thiếu của lần xếp cũ"


def test_ca_thieu_that_van_hien_tren_cho(
    _du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None
) -> None:
    """Ca thiếu THẬT (thuộc lần xếp gần nhất, chưa đủ người) vẫn phải hiện."""
    from ca_api.persist import open_shift_create
    from ca_api.services.scheduling_service import run_authoritative_schedule

    week = "2026-W44"
    run = run_authoritative_schedule(
        store_id="quan_01", tuan_iso=week, actor_id="lan", idempotency_key="real-gap-test",
    )
    # Môi trường test đủ 12 NV nên lần xếp thường OPTIMAL (không có ca thiếu).
    # Khi đó tự tạo một ca thiếu GẮN VÀO run gần nhất để kiểm luật hiển thị.
    if not run.get("result", {}).get("danh_sach_xung_dot"):
        open_shift_create(
            store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
            ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
        )

    items = client.get(
        f"/api/v1/open-shifts?tuan_iso={week}", headers=headers(client, "lan")
    ).json()["items"]
    assert any(str(i["schedule_run_id"]) == str(run["id"]) for i in items), (
        "ca thiếu của lần xếp gần nhất phải hiện"
    )


def test_manager_can_export_xlsx_and_pdf_for_selected_week() -> None:
    week = "2026-W42"
    kv_set("phan_cong_by_week", {week: {"w1_c01": ["nv_01"]}})
    auth = headers(client, "lan")

    xlsx = client.get(f"/api/v1/lich/xlsx?tuan={week}", headers=auth)
    pdf = client.get(f"/api/v1/lich/pdf?tuan={week}", headers=auth)

    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx.content.startswith(b"PK")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_employee_export_is_blocked_before_publish() -> None:
    week = "2026-W43"
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {week: {"tuan_iso": week, "trang_thai": "cho_duyet"}},
    )
    response = client.get(f"/api/v1/lich/ics?tuan={week}", headers=headers(client, "minh"))
    assert response.status_code == 409
    assert response.json()["detail"] == "lich_chua_cong_bo"
