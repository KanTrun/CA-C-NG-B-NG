# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Unit tests cho luồng nối logic lịch ↔ inbox ↔ TKB ↔ Solver lifecycle."""

from __future__ import annotations

import pytest
from ca_agents.ag_msg.extract import classify
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.sprint45 import _run_solver
from ca_api.persist import audit_list, kv_get, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_inbound_xin_nghi_classification_and_extraction() -> None:
    """Test 1: Trích xuất thứ, tuần, phân loại xin nghỉ chuẩn xác."""
    r = classify("Em xin nghỉ thứ 5 tuần này ạ", base_iso_week="2026-W01")
    assert r.intent == "xin_nghi"
    assert r.rang_buoc.get("thu") == "T5"
    assert r.rang_buoc.get("tuan_id") == "2026-W01"
    assert r.do_tin_cay >= 0.7
    assert r.rang_buoc.get("can_xac_minh") is False


def test_duyet_xin_nghi_wires_into_solver_nghi_phep(monkeypatch: pytest.MonkeyPatch, _du_nhan_vien_xep_lich: None) -> None:
    """Test 2: Duyệt xin nghỉ nạp vào inp.nghi_phep và solver không xếp nhân viên đó vào thứ 5."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    ql = headers(client, "lan")

    item_id = "test_inbox_xin_nghi_01"
    item = {
        "id": item_id,
        "agent": "ag_msg",
        "tom_tat": "Xin nghỉ T5",
        "trang_thai": "cho_duyet",
        "nguon": "zalo",
        "y_dinh": "xin_nghi",
        "do_tin_cay": 0.86,
        "nv_id": "nv_01",
        "rang_buoc": {"thu": "T5", "tuan_id": "2026-W01"},
    }
    kv_set("inbox_rang_buoc", [item])

    res = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet"},
        headers=ql,
    )
    assert res.status_code == 200
    assert res.json()["trang_thai"] == "duyet"

    # Chạy solver — neo ĐÚNG tuần W01 mà ràng buộc trỏ tới. Không truyền tuần
    # sẽ dùng tuần hiện tại theo đồng hồ (khác fixture W01) → nghỉ phép không khớp.
    sol = _run_solver("2026-W01")
    assert sol["ok"] is True

    # Kiểm tra phân công: nv_01 không được xếp vào bất kỳ ca nào ngày T5
    from ca_solver import build_lich_input

    inp = build_lich_input()
    phan = kv_get("phan_cong", {})
    for ca_id, nvs in phan.items():
        if inp.ca_meta.get(ca_id, {}).get("thu") == "T5":
            assert "nv_01" not in nvs, f"nv_01 bị xếp vào ca {ca_id} ngày T5 dù đã duyệt nghỉ!"


def test_duyet_cap_nhat_tkb_wires_into_solver_tkb(monkeypatch: pytest.MonkeyPatch, _du_nhan_vien_xep_lich: None) -> None:
    """Test 3: Duyệt TKB bận sáng T3 nạp vào inp.tkb, solver không xếp ca sáng T3."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    ql = headers(client, "lan")

    item_id = "test_inbox_tkb_02"
    item = {
        "id": item_id,
        "agent": "ag_msg",
        "tom_tat": "Bận học thứ 3 07:00-12:00",
        "trang_thai": "cho_duyet",
        "nguon": "telegram",
        "y_dinh": "cap_nhat_tkb",
        "do_tin_cay": 0.86,
        "nv_id": "nv_02",
        "rang_buoc": {"thu": "T3", "start": "07:00", "end": "12:00", "tuan_id": "2026-W01"},
    }
    kv_set("inbox_rang_buoc", [item])

    res = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet"},
        headers=ql,
    )
    assert res.status_code == 200

    # Ràng buộc trỏ W01 → chạy solver ĐÚNG tuần đó (không truyền tuần = tuần
    # hiện tại theo đồng hồ, khác fixture W01 → ràng buộc không được nạp).
    sol = _run_solver("2026-W01")
    assert sol["ok"] is True

    from ca_solver import build_lich_input

    inp = build_lich_input()
    phan = kv_get("phan_cong", {})
    for ca_id, nvs in phan.items():
        meta = inp.ca_meta.get(ca_id, {})
        if meta.get("thu") == "T3" and meta.get("bat_dau") == "07:00":
            assert "nv_02" not in nvs, f"nv_02 bị xếp vào ca sáng T3 {ca_id} dù bận TKB!"


def test_solver_only_loads_confirmed_tkb_for_target_week(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """TKB W39 không được rò sang lần giải W40."""
    from ca_solver.model import LichInput, SolveResult

    block = ("T4", "12:00", "17:00")
    kv_set(
        "tkb_nv_by_week",
        {
            "2026-W39": {
                "nv_02": {
                    "tuan_iso": "2026-W39",
                    "khoang_ban": [
                        {"thu": block[0], "start": block[1], "end": block[2]}
                    ],
                }
            }
        },
    )
    captured: list[list[tuple[str, str, str]]] = []

    def capture_tkb(data: LichInput, *, time_limit_s: float) -> SolveResult:
        del time_limit_s
        captured.append(list(data.tkb.get("nv_02", [])))
        return SolveResult(ok=False, status="CAPTURED")

    monkeypatch.setattr("ca_api.services.solver_adapter.solve_cpsat", capture_tkb)

    _run_solver("2026-W39")
    _run_solver("2026-W40")

    assert block in captured[0]
    assert block not in captured[1]


def test_duyet_rang_buoc_co_the_tu_dong_xep_du_21_o_ca(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """Duyệt có xác nhận auto phải chạy solver, phủ đủ 21 ô và đưa lịch về chờ duyệt."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    ql = headers(client, "lan")
    item_id = "test_inbox_auto_schedule_21"
    kv_set(
        "inbox_rang_buoc",
        [
            {
                "id": item_id,
                "agent": "ag_msg",
                "tom_tat": "Xin nghỉ T5",
                "trang_thai": "cho_duyet",
                "nguon": "zalo",
                "y_dinh": "xin_nghi",
                "do_tin_cay": 0.9,
                "nv_id": "nv_01",
                "rang_buoc": {"thu": "T5", "tuan_id": "2026-W01"},
            }
        ],
    )
    kv_set(
        "lich_tuan_lifecycle",
        {"tuan_iso": "2026-W01", "trang_thai": "nhap", "nguon": "quan"},
    )

    response = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet", "tu_dong_xep_lich": True},
        headers=ql,
    )

    assert response.status_code == 200, response.text
    solver = response.json()["tu_dong_xep_lich"]
    assert solver["ok"] is True
    assert solver["so_o_ca_da_xep"] == solver["tong_so_o_ca"] == 21
    assert kv_get("lich_tuan_lifecycle", {})["trang_thai"] == "cho_duyet"
    phan_cong = kv_get("phan_cong", {})
    assert len(phan_cong) == 70
    assert all(phan_cong.values())


def test_auto_xep_khong_ghi_de_lich_da_cong_bo(_du_nhan_vien_xep_lich: None) -> None:
    """Lịch đã công bố chỉ ghi nhận ràng buộc cho lượt sau, không bị auto sửa âm thầm."""
    ql = headers(client, "lan")
    item_id = "test_inbox_auto_locked"
    existing_schedule = {"w1_c01": ["nv_01"]}
    kv_set("phan_cong", existing_schedule)
    kv_set(
        "inbox_rang_buoc",
        [
            {
                "id": item_id,
                "agent": "ag_msg",
                "tom_tat": "Xin nghỉ T5",
                "trang_thai": "cho_duyet",
                "nguon": "zalo",
                "y_dinh": "xin_nghi",
                "nv_id": "nv_01",
                "rang_buoc": {"thu": "T5", "tuan_id": "2026-W01"},
            }
        ],
    )
    kv_set(
        "lich_tuan_lifecycle",
        {"tuan_iso": "2026-W01", "trang_thai": "da_cong_bo", "nguon": "quan"},
    )

    response = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet", "tu_dong_xep_lich": True},
        headers=ql,
    )

    assert response.status_code == 200
    solver = response.json()["tu_dong_xep_lich"]
    assert solver["ok"] is False
    assert solver["status"] == "LIFECYCLE_LOCKED"
    assert kv_get("phan_cong", {}) == existing_schedule


def test_auto_xep_bao_khong_kha_thi_va_giu_lich_cu(_du_nhan_vien_xep_lich: None) -> None:
    """Không đủ người thì trả xung đột và tuyệt đối không thay lịch đang có."""
    from ca_api.nhan_vien import list_nhan_vien_ops

    ql = headers(client, "lan")
    staff_ids = [str(item["id"]) for item in list_nhan_vien_ops()]
    pending_id = "test_inbox_auto_infeasible"
    items = [
        {
            "id": pending_id if index == 0 else f"approved_leave_{index}",
            "agent": "ag_msg",
            "tom_tat": f"{nv_id} xin nghỉ T2",
            "trang_thai": "cho_duyet" if index == 0 else "duyet",
            "nguon": "zalo",
            "y_dinh": "xin_nghi",
            "nv_id": nv_id,
            "hieu_luc": None if index == 0 else {
                "loai": "rang_buoc_cho_solver",
                "nv_id": nv_id,
                "thu": "T2",
                "tuan_id": "2026-W01",
            },
            "rang_buoc": {"thu": "T2", "tuan_id": "2026-W01"},
        }
        for index, nv_id in enumerate(staff_ids)
    ]
    existing_schedule = {"w1_c01": [staff_ids[0]]}
    kv_set("phan_cong", existing_schedule)
    kv_set("inbox_rang_buoc", items)
    kv_set(
        "lich_tuan_lifecycle",
        {"tuan_iso": "2026-W01", "trang_thai": "nhap", "nguon": "quan"},
    )

    response = client.post(
        f"/api/v1/inbox/rang-buoc/{pending_id}",
        json={"quyet_dinh": "duyet", "tu_dong_xep_lich": True},
        headers=ql,
    )

    assert response.status_code == 200
    solver = response.json()["tu_dong_xep_lich"]
    assert solver["ok"] is False
    assert "INFEASIBLE" in solver["status"]
    assert solver["danh_sach_xung_dot"]
    assert kv_get("phan_cong", {}) == existing_schedule
    assert kv_get("lich_tuan_lifecycle", {})["trang_thai"] == "nhap"


def test_duyet_doi_ca_requires_ca_id_and_doi_tac() -> None:
    """Test 4: Duyệt đổi ca thiếu ca_id hoặc đối tác bị từ chối 400; có đủ thì mở swap hợp lệ."""
    ql = headers(client, "lan")
    item_id = "test_inbox_doi_ca_03"
    item = {
        "id": item_id,
        "agent": "ag_msg",
        "tom_tat": "Cho em đổi ca",
        "trang_thai": "cho_duyet",
        "nguon": "zalo",
        "y_dinh": "doi_ca",
        "do_tin_cay": 0.60,
        "nv_id": "nv_01",
        "rang_buoc": {},
    }
    kv_set("inbox_rang_buoc", [item])

    # Thử duyệt thiếu thông tin -> lỗi 400
    res_bad = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet"},
        headers=ql,
    )
    assert res_bad.status_code == 400
    assert "doi_ca_can_ca_id_va_doi_tac" in res_bad.json()["detail"]

    # Duyệt đầy đủ
    res_ok = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet", "ca_id": "w1_c01", "doi_tac_nv_id": "nv_02"},
        headers=ql,
    )
    assert res_ok.status_code == 200
    body = res_ok.json()
    assert body["trang_thai"] == "duyet"
    swap_id = body["hieu_luc"]["swap_id"]

    swaps = kv_get("swap", [])
    sw = next(s for s in swaps if s["id"] == swap_id)
    assert sw["ca_id"] == "w1_c01"
    assert sw["b"] == "nv_02"
    assert sw["trang_thai"] == "cho_xac_nhan"


def test_lifecycle_da_dong_to_nhap_with_audit() -> None:
    """Test 5: Mở lại lịch từ da_dong sang nhap bắt buộc có lý do và ghi audit log."""
    chu_quan = headers(client, "hung")
    staff = headers(client, "minh")

    kv_set("lifecycle", {"tuan_iso": "2026-W01", "trang_thai": "da_dong", "nguon": "quan"})

    # Nhân viên không được phép
    r_forbidden = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap", "ly_do": "Mở lại"},
        headers=staff,
    )
    assert r_forbidden.status_code == 403

    # Chủ quán mở lại nhưng thiếu lý do -> 400
    r_no_reason = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap"},
        headers=chu_quan,
    )
    assert r_no_reason.status_code == 400
    assert "can_ly_do_mo_lai_lich" in r_no_reason.json()["detail"]

    # Chủ quán mở lại có lý do hợp lệ -> 200
    r_ok = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap", "ly_do": "Điều chỉnh do nhân viên xin nghỉ gấp"},
        headers=chu_quan,
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["trang_thai"] == "nhap"

    # Kiểm tra audit log
    logs = audit_list()
    reopen_log = next(log for log in logs if log.get("hanh") == "schedule.lifecycle_reopen" and log.get("payload", {}).get("from") == "da_dong" and log.get("payload", {}).get("to") == "nhap")
    assert reopen_log.get("payload", {}).get("ly_do") == "Điều chỉnh do nhân viên xin nghỉ gấp"


def test_solver_ignores_constraints_from_other_weeks(monkeypatch: pytest.MonkeyPatch, _du_nhan_vien_xep_lich: None) -> None:
    """Test 6: Ràng buộc của tuần sau (2026-W02) không được nạp vào solver khi đang giải tuần hiện tại (2026-W01)."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    ql = headers(client, "lan")

    item_id = "test_inbox_tuan_khac_06"
    item = {
        "id": item_id,
        "agent": "ag_msg",
        "tom_tat": "Tuần sau em xin nghỉ T2",
        "trang_thai": "cho_duyet",
        "nguon": "telegram",
        "y_dinh": "xin_nghi",
        "do_tin_cay": 0.86,
        "nv_id": "nv_03",
        "rang_buoc": {"thu": "T2", "tuan_id": "2026-W02"},
    }
    kv_set("inbox_rang_buoc", [item])
    kv_set("lifecycle", {"tuan_iso": "2026-W01", "trang_thai": "nhap", "nguon": "quan"})

    client.post(f"/api/v1/inbox/rang-buoc/{item_id}", json={"quyet_dinh": "duyet"}, headers=ql)

    sol = _run_solver()
    assert sol["ok"] is True


def test_low_confidence_marked_can_xac_minh() -> None:
    """Test 7: Tin nhắn mơ hồ (không có thứ/ngày) được gắn do_tin_cay < 0.7 và can_xac_minh=True."""
    r = classify("Em muốn xin nghỉ một hôm")
    assert r.intent == "xin_nghi"
    assert r.do_tin_cay < 0.7
    assert r.rang_buoc.get("can_xac_minh") is True


def test_deduplicate_identical_inbox_constraints(monkeypatch: pytest.MonkeyPatch, _du_nhan_vien_xep_lich: None) -> None:
    """Test 8: Duyệt 2 tin nhắn trùng lặp cùng xin nghỉ không gây trùng lặp hay lỗi solver."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    ql = headers(client, "lan")

    items = [
        {
            "id": "dup_01",
            "agent": "ag_msg",
            "tom_tat": "Xin nghỉ T6",
            "trang_thai": "cho_duyet",
            "nguon": "zalo",
            "y_dinh": "xin_nghi",
            "do_tin_cay": 0.86,
            "nv_id": "nv_04",
            "rang_buoc": {"thu": "T6", "tuan_id": "2026-W01"},
        },
        {
            "id": "dup_02",
            "agent": "ag_msg",
            "tom_tat": "Xin nghỉ T6 nhắc lại",
            "trang_thai": "cho_duyet",
            "nguon": "telegram",
            "y_dinh": "xin_nghi",
            "do_tin_cay": 0.86,
            "nv_id": "nv_04",
            "rang_buoc": {"thu": "T6", "tuan_id": "2026-W01"},
        },
    ]
    kv_set("inbox_rang_buoc", items)

    client.post("/api/v1/inbox/rang-buoc/dup_01", json={"quyet_dinh": "duyet"}, headers=ql)
    client.post("/api/v1/inbox/rang-buoc/dup_02", json={"quyet_dinh": "duyet"}, headers=ql)

    sol = _run_solver()
    assert sol["ok"] is True


def test_ambiguous_partner_name_requires_explicit_id() -> None:
    """Test 9: Khi có 2 nhân viên trùng tên, hệ thống đánh dấu doi_tac_khong_ro và yêu cầu chọn rõ ID."""
    staff = [
        {"id": "nv_01", "ten": "Nguyễn Lan"},
        {"id": "nv_02", "ten": "Trần Lan"},
    ]
    r = classify("Em muốn đổi ca w1_c01 với Lan", staff=staff)
    assert r.intent == "doi_ca"
    assert r.rang_buoc.get("doi_tac_khong_ro") is True

    ql = headers(client, "lan")
    item_id = "test_ambiguous_09"
    kv_set(
        "inbox_rang_buoc",
        [
            {
                "id": item_id,
                "agent": "ag_msg",
                "tom_tat": "Đổi ca với Lan",
                "trang_thai": "cho_duyet",
                "nguon": "zalo",
                "y_dinh": "doi_ca",
                "do_tin_cay": 0.60,
                "nv_id": "nv_03",
                "doi_tac_khong_ro": True,
                "rang_buoc": {"ca_id": "w1_c01", "doi_tac_khong_ro": True},
            }
        ],
    )

    # Duyệt mà không chọn đối tác rõ -> 400
    res_bad = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet", "ca_id": "w1_c01"},
        headers=ql,
    )
    assert res_bad.status_code == 400
    assert "doi_tac_khong_ro_can_chon_nhan_vien" in res_bad.json()["detail"]

    # Duyệt chỉ định rõ ID -> 200
    res_ok = client.post(
        f"/api/v1/inbox/rang-buoc/{item_id}",
        json={"quyet_dinh": "duyet", "ca_id": "w1_c01", "doi_tac_nv_id": "nv_01"},
        headers=ql,
    )
    assert res_ok.status_code == 200


def test_infeasible_solver_returns_specific_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 10: Khi solver INFEASIBLE do mâu thuẫn ràng buộc, trả về danh sách xung đột cụ thể."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")

    from ca_solver import build_lich_input

    inp = build_lich_input()
    # Tạo ràng buộc nghỉ phép cho TẤT CẢ nhân viên vào thứ 2 (T2)
    inbox_items = []
    for i, nv in enumerate(inp.nhan_vien_ids):
        inbox_items.append(
            {
                "id": f"all_leave_{i}",
                "agent": "ag_msg",
                "tom_tat": f"{nv} xin nghỉ T2",
                "trang_thai": "duyet",
                "nguon": "zalo",
                "y_dinh": "xin_nghi",
                "nv_id": nv,
                "hieu_luc": {
                    "loai": "rang_buoc_cho_solver",
                    "thu": "T2",
                    "tuan_id": "2026-W01",
                },
                "rang_buoc": {"thu": "T2", "tuan_id": "2026-W01"},
            }
        )
    kv_set("inbox_rang_buoc", inbox_items)

    # Ràng buộc trỏ W01 → phải chạy solver ĐÚNG tuần đó để nó nhận ràng buộc
    # và trả INFEASIBLE (không truyền tuần = tuần hiện tại, khác fixture W01).
    sol = _run_solver("2026-W01")
    assert sol["ok"] is False
    assert "INFEASIBLE" in sol["status"]
    assert len(sol["danh_sach_xung_dot"]) > 0
    assert any("T2" in msg for msg in sol["danh_sach_xung_dot"])


def test_swap_rejected_by_partner_not_applied_to_solver() -> None:
    """Test 11: Swap bị đối tác từ chối chuyển sang tu_choi."""
    nv_a = headers(client, "minh")
    # Tạo swap
    item = {
        "id": "sw_test_11",
        "a": "minh",
        "b": "lan",
        "c": "hung",
        "ca_id": "w1_c01",
        "trang_thai": "cho_xac_nhan",
        "dong_y": ["minh"],
    }
    kv_set("swap", [item])

    # Đối tác từ chối
    res = client.post(
        "/api/v1/doi-ca/sw_test_11/tu-choi",
        headers=nv_a,
    )
    assert res.status_code == 200
    assert res.json()["trang_thai"] == "tu_choi"
