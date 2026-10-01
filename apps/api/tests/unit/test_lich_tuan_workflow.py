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
    """Bảng open_shifts tích luỹ: bản ghi cũ của ca ĐÃ ĐỦ người không được hiện.

    Lỗi gốc: lịch đủ người nhưng khối "Ca còn thiếu người" (và chợ đổi ca) vẫn
    liệt kê hàng chục ca cũ từ lần xếp thất bại trước đó. Luật đúng là theo
    PHÂN CÔNG HIỆN TẠI: ca nào đã đủ định biên thì không còn là việc phải làm.
    """
    from ca_api.persist import open_shift_create, schedule_run_create

    week = "2026-W43"
    run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={"a": 1},
        fingerprint="fp-old", idempotency_key="old-run", created_by="lan", status="needs_gap_resolution",
    )
    for ca_id in ("w1_c01", "w1_c02"):
        open_shift_create(
            store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
            ca_id=ca_id, deadline_at="2026-11-01T00:00:00Z",
        )
    # Phân công thực đã ĐỦ người cho cả hai ca (định biên từ seed: c01 cần 2).
    # Đặt ở `lich_tuan_results_by_week` để `/lich-tuan` đi nhánh solver.
    from ca_api.interfaces.http.sprint45 import _so_nguoi_toi_thieu_map
    need = _so_nguoi_toi_thieu_map()
    du = lambda ca_id: [f"nv_{i:02d}" for i in range(1, need.get(ca_id, 1) + 1)]  # noqa: E731
    phan = {"w1_c01": du("w1_c01"), "w1_c02": du("w1_c02")}
    kv_set("lich_tuan_results_by_week", {
        week: {"tuan_iso": week, "ok": True, "status": "OPTIMAL", "phan_cong": phan},
    })
    kv_set("phan_cong_by_week", {week: phan})

    res = client.get(f"/api/v1/lich-tuan?tuan={week}", headers=headers(client, "lan")).json()
    assert res["open_shifts"] == [], "ca đã đủ người không được hiện là ca thiếu"

    # Chợ đổi ca dùng endpoint KHÁC (`/api/v1/open-shifts`) — phải cùng luật.
    cho = client.get(f"/api/v1/open-shifts?tuan_iso={week}", headers=headers(client, "lan")).json()
    assert cho["items"] == [], "chợ cũng phải ẩn ca đã đủ người"


def test_ca_thieu_that_van_hien_tren_cho(
    _du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None
) -> None:
    """Ca thiếu THẬT (phân công hiện tại CHƯA đủ định biên) vẫn phải hiện."""
    from ca_api.persist import open_shift_create, schedule_run_create

    week = "2026-W44"
    run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={"a": 1},
        fingerprint="fp-real", idempotency_key="real-gap-test", created_by="lan",
        status="needs_gap_resolution",
    )
    open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    # w1_c01 KHÔNG có ai → vẫn thiếu; w1_c02 đủ người → không hiện.
    kv_set("phan_cong_by_week", {week: {"w1_c02": ["nv_02"]}})

    items = client.get(
        f"/api/v1/open-shifts?tuan_iso={week}", headers=headers(client, "lan")
    ).json()["items"]
    assert any(str(i["ca_id"]) == "w1_c01" for i in items), "ca thiếu thật phải hiện"
    assert all(str(i["ca_id"]) != "w1_c02" for i in items), "ca đủ người phải ẩn"


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
