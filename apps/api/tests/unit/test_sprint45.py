# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from ca_agents.ag_rule import RuleDraft
from ca_api.interfaces.http import sprint45
from ca_api.interfaces.http.main import app
from ca_api.persist import da_diem_danh, kv_get, kv_set
from ca_api.services.scheduling_service import run_authoritative_schedule
from ca_playbook import record_sua
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_successful_week_resolves_claimed_shifts_without_touching_other_weeks() -> None:
    from ca_api.persist import (
        open_shift_create,
        open_shift_list,
        open_shift_resolve_for_week,
        shift_application_claim_first,
    )

    shift = open_shift_create(
        store_id="quan_01", schedule_run_id="claim-regression", tuan_iso="2026-W44",
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    open_shift_create(
        store_id="quan_01", schedule_run_id="other-week", tuan_iso="2026-W45",
        ca_id="w1_c01", deadline_at="2026-11-08T00:00:00Z",
    )
    assert shift_application_claim_first(
        open_shift_id=shift["id"], store_id="quan_01", nv_id="nv_01",
    ) is not None
    assert shift_application_claim_first(
        open_shift_id=shift["id"], store_id="quan_01", nv_id="nv_02",
    ) is None
    assert open_shift_list("quan_01", tuan_iso="2026-W44", status="claimed")[0]["claimed_by"] == "nv_01"
    assert open_shift_resolve_for_week("quan_01", "2026-W44") == 1
    assert open_shift_list("quan_01", tuan_iso="2026-W44", status="claimed") == []
    assert len(open_shift_list("quan_01", tuan_iso="2026-W45")) == 1


def _hom_nay() -> str:
    return datetime.now(timezone(timedelta(hours=7))).date().isoformat()


def _seed_three_sua() -> None:
    for i in range(3):
        record_sua(
            loai="nhan_ca",
            truoc={"ca_id": "w1_c10", "nv": []},
            sau={"ca_id": "w1_c10", "nv": [f"nv_{i + 10:02d}"]},
            ai="lan",
            now_iso=f"2026-01-0{i + 1}T08:00:00Z",
        )


def _seed_three_nha_ca() -> None:
    """Ba lần nhả ca — ``sau`` không còn ai nên không suy ra được số người."""
    for i in range(3):
        record_sua(
            loai="nha_ca",
            truoc={"ca_id": "w1_c11", "nv": [f"nv_{i + 10:02d}"]},
            sau={"ca_id": "w1_c11", "nv": []},
            ai="lan",
            now_iso=f"2026-01-0{i + 1}T09:00:00Z",
        )


def test_lifecycle_and_audit(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    ql = headers(client, "lan")
    chu = headers(client, "hung")
    # Đúng chuỗi: may_sinh → nhap → dang_giai (solver) → cho_duyet → da_cong_bo.
    client.post("/api/v1/lich/lifecycle", json={"to": "nhap"}, headers=ql)
    r = client.post("/api/v1/lich/lifecycle", json={"to": "dang_giai"}, headers=ql)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trang_thai"] == "cho_duyet"
    assert body.get("solver", {}).get("status")
    approved = client.post("/api/v1/lich/lifecycle", json={"to": "da_duyet"}, headers=ql)
    assert approved.status_code == 200, approved.text
    assert approved.json()["trang_thai"] == "da_cong_bo"
    ics = client.get("/api/v1/lich/ics", headers=ql).json()
    assert "BEGIN:VCALENDAR" in ics["ics"]
    assert client.get("/api/v1/audit", headers=ql).status_code == 200
    log = client.get("/api/v1/audit", headers=chu).json()["items"]
    assert log
    assert log[0]["id"] >= log[-1]["id"]
    assert isinstance(log[0]["payload"], dict)
    assert log[0]["payload"]["to"] in {"dang_giai", "cho_duyet", "da_cong_bo"}


def test_published_schedule_reopen_requires_reason(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    week = "2026-W44"
    ql = headers(client, "lan")
    run = run_authoritative_schedule(
        store_id="quan_01", tuan_iso=week, actor_id="lan", idempotency_key="test-reopen-w44",
    )
    assert run["status"] == "computed", run
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "cho_duyet"}})
    approved = client.post(
        "/api/v1/lich/lifecycle", json={"to": "da_duyet", "tuan_iso": week}, headers=ql,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["trang_thai"] == "da_cong_bo"

    missing_reason = client.post(
        "/api/v1/lich/lifecycle", json={"to": "nhap", "tuan_iso": week}, headers=ql,
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["detail"] == "can_ly_do_mo_lai_lich"

    reopened = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap", "tuan_iso": week, "ly_do": "Nhân viên báo bận đột xuất"},
        headers=ql,
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["trang_thai"] == "nhap"

    from ca_api.persist import availability_confirmation_upsert
    availability_confirmation_upsert(
        item_id="changed-after-reopen",
        store_id="quan_01",
        nv_id="nv_03",
        tuan_iso=week,
        availability={"T2": ["Sáng"]},
        status="da_xac_nhan",
        source="test",
    )
    rerun = client.post(
        "/api/v1/lich/lifecycle", json={"to": "dang_giai", "tuan_iso": week}, headers=ql,
    )
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["trang_thai"] in {"cho_duyet", "nhap"}


def test_only_owner_can_reopen_closed_schedule() -> None:
    week = "2026-W44"
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "da_dong"}})
    manager = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap", "tuan_iso": week, "ly_do": "Cần sửa lịch"},
        headers=headers(client, "lan"),
    )
    assert manager.status_code == 403

    owner = client.post(
        "/api/v1/lich/lifecycle",
        json={"to": "nhap", "tuan_iso": week, "ly_do": "Cần sửa lịch"},
        headers=headers(client, "hung"),
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["trang_thai"] == "nhap"


def test_publish_creates_exact_week_notification_and_ack(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    week = "2026-W44"
    ql = headers(client, "lan")
    run = run_authoritative_schedule(
        store_id="quan_01", tuan_iso=week, actor_id="lan", idempotency_key="test-publish-w44",
    )
    assert run["status"] == "computed", run
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "da_duyet"}})

    published = client.patch(
        "/api/v1/lich-tuan/lifecycle",
        json={"tuan_iso": week, "trang_thai": "da_cong_bo"},
        headers=ql,
    )
    assert published.status_code == 200, published.text

    notifications = client.get("/api/v1/lich/thong-bao", headers=headers(client, "minh"))
    assert notifications.status_code == 200, notifications.text
    items = [item for item in notifications.json()["notifications"] if item["tuan_iso"] == week]
    assert len(items) == 1
    # `minh` là nhân viên (nhan_vien) → nhận link xem lịch CỦA MÌNH (/toi).
    # Quản lý/chủ quán nhận /lich-tuan (xem toàn quán) — xem
    # test_publish_notification_role_based_links trong test_schedule_consistency.py.
    assert items[0]["url"] == f"/toi?tuan={week}"

    acked = client.post(f"/api/v1/lich/thong-bao/{items[0]['id']}/ack", headers=headers(client, "minh"))
    assert acked.status_code == 200 and acked.json()["ok"] is True
    assert client.get("/api/v1/lich/thong-bao?unread_only=true", headers=headers(client, "minh")).json()["notifications"] == []


def test_inbox_ten_decisions() -> None:
    ql = headers(client, "lan")
    items = client.get("/api/v1/inbox/rang-buoc", headers=ql).json()["items"]
    assert len(items) >= 10
    for it in items[:10]:
        d = "duyet" if it["id"].endswith(("1", "2", "3", "4", "5")) else "tu_choi"
        rr = client.post(
            f"/api/v1/inbox/rang-buoc/{it['id']}",
            json={"quyet_dinh": d},
            headers=ql,
        )
        assert rr.status_code == 200, rr.text


def test_inbox_msg_does_not_break_rang_buoc() -> None:
    ql = headers(client, "lan")
    client.post("/api/v1/inbox", json={"tom_tat": "tin nhắn"}, headers=ql)
    items = client.get("/api/v1/inbox/rang-buoc", headers=ql).json()["items"]
    assert len(items) >= 10
    assert all("id" in it for it in items)


def test_conflict_never_picks() -> None:
    body = client.get("/api/v1/vf/conflict").json()
    assert body["conflict"] is True
    assert body["khong_tu_chon"] is True


def test_handover_sbar() -> None:
    nv = headers(client, "minh")
    text = (
        "Tình hình: hết đá\nBối cảnh: ca sáng\n"
        "Đánh giá: khách đông\nĐề nghị: mua đá\nTreo: máy pha kêu"
    )
    r = client.post("/api/v1/handover", json={"text": text, "alt_claim": "ổn"}, headers=nv)
    assert r.status_code == 200
    assert "hết đá" in r.json()["tinh_hinh"]


def test_handover_phat_hien_lech_so_giua_ca() -> None:
    """Bug #3 (QA 2026-09-26): hai ca khai két lệch nhau phải được nêu ra.

    Cổng VF-NUM mở rộng: `co_lech_so=true` + liệt kê các mức tiền khác nhau cho
    cùng chủ đề; KHÔNG tự chọn bên nào (ADR-008).
    """
    nv = headers(client, "lan")
    text = (
        "Ca sáng: két còn 2.350.000đ, còn 3 bàn chưa dọn.\n"
        "Ca chiều: két còn 2.300.000đ, máy pha cần vệ sinh."
    )
    r = client.post("/api/v1/handover", json={"text": text}, headers=nv)
    assert r.status_code == 200
    body = r.json()
    assert body["co_lech_so"] is True
    conflicts = body["vf_number_conflict"]
    assert len(conflicts) == 1
    assert conflicts[0]["chu_de"] == "ket"
    assert conflicts[0]["gia_tri"] == [2300000, 2350000]


def test_handover_khong_bao_lech_khi_so_giong() -> None:
    nv = headers(client, "lan")
    text = "Ca sáng: két còn 2.350.000đ.\nCa chiều: két còn 2.350.000đ."
    body = client.post("/api/v1/handover", json={"text": text}, headers=nv).json()
    assert body["co_lech_so"] is False
    assert body["vf_number_conflict"] == []


def test_cong_bang_chi_tra_nv_co_that() -> None:
    """Bug QA đợt 4: /cong-bang tra số dư cho nv_20..nv_25 (mã trong seed
    fixture) dù DB chỉ có 19 người. Kết quả phải chỉ gồm NV đang xếp lịch.
    """
    cq = headers(client, "hung")  # /nguoi đòi quyền chu_quan
    body = client.get("/api/v1/cong-bang", headers=cq).json()
    so_du = body["so_du"]
    items = client.get("/api/v1/nguoi", headers=cq).json()["items"]
    nv_that = {u["nv_id"] for u in items if u["role"] != "ai_assistant"}
    la = set(so_du.keys())
    assert la <= nv_that, f"số dư có mã không tồn tại: {sorted(la - nv_that)}"
    assert not any(k.startswith("nv_2") for k in la), f"còn mã ngoài DB: {sorted(la)}"


def test_cam_nang_eight_steps_den_cho_chu_quan() -> None:
    """Chạy 8 bước trên lần sửa thật: luật suy tất định phải qua VF và chờ chủ quán.

    Không có ``bi_loai`` ở đường này là đúng: suy luật tất định
    (``derive_rule_from_edits``) chỉ sinh câu và ``dieu_kien`` hợp hợp đồng nên
    cổng VF-RULE không có gì để loại. Ví dụ luật bị loại cho demo nằm ở fixture
    ``luat_cam_nang`` (xem test_seed_van_hanh), không do API bịa ra.
    """
    _seed_three_sua()
    ql = headers(client, "lan")
    chu = headers(client, "hung")
    r = client.post("/api/v1/cam-nang/chay-8-buoc", headers=ql)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cho_chot"]["trang_thai"] == "cho_chu_quan"
    assert body["cho_chot"]["buoc"] == 6
    assert body["cho_chot"]["cau"].strip()
    assert body["bi_loai"] is None
    assert body["so_luat_that_quan"] >= 1
    assert [x["mau"] for x in body["ung_vien"]] == ["nhan_ca"]
    assert client.post(
        "/api/v1/cam-nang/duyet", json={"id": body["cho_chot"]["id"], "ok": True}, headers=ql
    ).status_code == 403
    final = client.post(
        "/api/v1/cam-nang/duyet", json={"id": body["cho_chot"]["id"], "ok": True}, headers=chu
    )
    assert final.status_code == 200, final.text
    assert final.json()["trang_thai"] == "hieu_luc"
    cards = client.get("/api/v1/cam-nang", headers=ql).json()["items"]
    assert any(x.get("trang_thai") == "hieu_luc" for x in cards)


def test_cam_nang_bao_luat_bi_vf_rule_loai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bản nháp của agent vi phạm VF-RULE thì bị loại và được báo ra, không lọt."""
    _seed_three_sua()
    xau = RuleDraft(
        cau="nv_03 lười không xếp cuối tuần",
        loai="ghep_ky_nang",
        dieu_kien={"thu": "T7"},
        bang_chung=["0", "1", "2"],
        do_tin_cay=0.75,
    )
    monkeypatch.setattr(sprint45, "propose_rule", lambda *a, **k: xau)

    ql = headers(client, "lan")
    r = client.post("/api/v1/cam-nang/chay-8-buoc", headers=ql)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cho_chot"] is None
    assert body["bi_loai"]["trang_thai"] == "loai"
    assert body["bi_loai"]["vf_rule"] == "luat_ve_nguoi"
    assert body["ung_vien"][0]["vf_rule"] == "luat_ve_nguoi"
    cards = client.get("/api/v1/cam-nang", headers=ql).json()["items"]
    assert any(x.get("trang_thai") == "loai" for x in cards)


def test_cam_nang_bao_khong_du_tin_hieu_khi_thieu_tin_hieu() -> None:
    """Ba lần nhả ca làm trống ca: không có tín hiệu số người nên không suy được luật.

    Đường này phải báo ``khong_du_tin_hieu`` chứ không được dựng một câu luật
    bịa để lấp chỗ trống.
    """
    _seed_three_nha_ca()
    ql = headers(client, "lan")
    r = client.post("/api/v1/cam-nang/chay-8-buoc", headers=ql)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cho_chot"] is None
    assert body["bi_loai"] is None
    assert body["ung_vien"] == [
        {"mau": "nha_ca", "trang_thai": "khong_du_tin_hieu", "buoc": 3, "id": None}
    ]
    assert client.get("/api/v1/cam-nang", headers=ql).json()["items"] == []


def test_cam_nang_requires_real_edits() -> None:
    ql = headers(client, "lan")
    r = client.post("/api/v1/cam-nang/chay-8-buoc", headers=ql)
    assert r.status_code == 409


def test_sop_twenty_with_citation_or_unknown() -> None:
    ql = headers(client, "lan")
    r = client.get("/api/v1/sop/golden", headers=ql).json()
    assert r["n"] == 20
    assert r["moi_cau_co_nguon_hoac_chua_co"] is True
    assert r["co_cau_chua_co"] is True


def test_qr_one_shot() -> None:
    ql = headers(client, "lan")
    nv = headers(client, "minh")
    tok = client.post("/api/v1/qr", json={"nv_id": "nv_03"}, headers=ql).json()["token"]
    assert client.post(f"/api/v1/qr/{tok}", headers=nv).status_code == 200
    assert client.post(f"/api/v1/qr/{tok}", headers=nv).status_code == 409


def test_swap_uses_requester_and_any_recipient() -> None:
    nv = headers(client, "minh")
    r = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_03", "b": "all", "ca_id": "w1_c01"},
        headers=nv,
    )
    assert r.status_code == 200
    assert r.json()["trang_thai"] == "cho_xac_nhan"
    assert "c" not in r.json()


def test_fairness_scoped_to_self_for_nv() -> None:
    nv = headers(client, "minh")
    r = client.get("/api/v1/cong-bang", headers=nv).json()
    assert r["khong_xep_hang_ten"] is True
    assert "cuoi_tuan" in r["axes"]
    assert set(r["so_du"].keys()) == {"nv_03"}
    assert r["nv_id"] == "nv_03"


def test_qr_can_only_be_used_by_target_employee() -> None:
    manager = headers(client, "lan")
    other = headers(client, "hung")
    target = headers(client, "minh")
    token = client.post("/api/v1/qr", json={"nv_id": "nv_03", "ca_id": "w1_c01"}, headers=manager).json()["token"]
    assert client.post(f"/api/v1/qr/{token}", headers=other).status_code == 403
    assert client.post(f"/api/v1/qr/{token}", headers=target).status_code == 200
    assert "nv_03" in kv_get("diem_danh", {}).get(_hom_nay(), [])


def test_qr_diem_danh_chi_hieu_luc_trong_ngay() -> None:
    """Điểm danh scoped theo ngày — ngày khác không tính, phải quét lại."""
    kv_set("diem_danh", {"2000-01-01": ["nv_03"]})
    assert da_diem_danh("nv_03") is False
    # Bản cũ dạng list vẫn đọc được (tương thích ngược)
    kv_set("diem_danh", ["nv_03"])
    assert da_diem_danh("nv_03") is True


def test_qr_write_path_tuong_thich_nguoc_du_lieu_list_cu() -> None:
    """QR check-in ghi cùng KV `diem_danh` — bản cũ dạng list phải migrate, không 500.

    Regression cùng lớp lỗi với /api/v1/diem-danh: `dd_mut()` gọi `.get()` trên
    list → AttributeError → 500, nhân viên không quét QR vào ca được.
    """
    kv_set("diem_danh", ["nv_09"])
    manager = headers(client, "lan")
    target = headers(client, "minh")
    token = client.post("/api/v1/qr", json={"nv_id": "nv_03", "ca_id": "w1_c01"}, headers=manager).json()["token"]

    r = client.post(f"/api/v1/qr/{token}", headers=target)

    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    luu = kv_get("diem_danh", {})
    assert isinstance(luu, dict)
    assert set(luu[_hom_nay()]) == {"nv_09", "nv_03"}


def test_diem_danh_nang_cap_kv_list_cu_thanh_dict() -> None:
    """Ghi điểm danh lên kv dạng list cũ phải nâng cấp, không được 500.

    Bên đọc (`diem_danh_hom_nay`) chấp nhận cả list lẫn dict, nên DB seed từ
    trước còn giữ dạng list. Nếu bên ghi chỉ biết dict thì nó ném
    AttributeError và endpoint trả 500 — nhân viên không điểm danh được nên
    phiếu không mở nổi.
    """
    kv_set("diem_danh", ["nv_03", "fx_nv_an"])

    r = client.post("/api/v1/diem-danh", headers=headers(client, "lan"))
    assert r.status_code == 200
    assert r.json()["nv_id"] == "nv_01"

    luu = kv_get("diem_danh", {})
    assert isinstance(luu, dict), "kv phải được nâng cấp sang dạng theo ngày"
    danh_sach = luu[_hom_nay()]
    # Người cũ giữ nguyên, người mới được thêm vào đúng ngày hôm nay.
    assert "nv_03" in danh_sach
    assert "fx_nv_an" in danh_sach
    assert "nv_01" in danh_sach
    assert da_diem_danh("nv_01") is True

    # Gọi lại không được nhân bản phần tử.
    client.post("/api/v1/diem-danh", headers=headers(client, "lan"))
    assert kv_get("diem_danh", {})[_hom_nay()].count("nv_01") == 1


def test_swap_requires_valid_shift_and_staff_participation() -> None:
    staff = headers(client, "minh")
    outsider = {"a": "nv_01", "b": "all", "ca_id": "w1_c01"}
    assert client.post("/api/v1/cho-doi-ca", json=outsider, headers=staff).status_code == 403
    invalid = {"a": "nv_03", "b": "missing", "ca_id": "missing"}
    assert client.post("/api/v1/cho-doi-ca", json=invalid, headers=staff).status_code == 422


def test_ops_pickers_for_staff() -> None:
    nv = headers(client, "minh")
    r = client.get("/api/v1/ops/pickers", headers=nv)
    assert r.status_code == 200
    body = r.json()
    assert {person["id"] for person in body["nhan_vien"]} >= {"nv_01", "nv_02", "nv_03"}
    assert "nv_04" not in {person["id"] for person in body["nhan_vien"]}
    assert len(body["ca"]) >= 3
    assert body["me_nv_id"] == "nv_03"


def test_swap_consent_by_any_recipient() -> None:
    """Phiếu mở cho MỌI NGƯỜI: ai bấm đồng ý cũng thành người nhận.

    Phải dựng tuần đã công bố trước: đổi ca ở tuần chưa công bố bị chặn
    (`lich_chua_cong_bo`) vì đó là sửa bản nháp quản lý còn đang xếp.
    """
    kv_set("lich_tuan_lifecycle", {"tuan_iso": "2026-W01", "trang_thai": "da_cong_bo"})
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {"2026-W01": {"tuan_iso": "2026-W01", "trang_thai": "da_cong_bo"}},
    )
    opened = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_03", "b": "all", "ca_id": "w1_c01"},
        headers=headers(client, "minh"),
    ).json()
    swap_id = opened["id"]
    done = client.post(f"/api/v1/cho-doi-ca/{swap_id}/dong-y", headers=headers(client, "hung")).json()
    assert done["trang_thai"] == "dong_y"
    assert done["dong_y"] == ["nv_02"]


def test_swap_dong_y_doi_quan_ly_duyet_khi_tuan_da_cong_bo() -> None:
    """Tuần đã công bố: NHÂN VIÊN đồng ý không tự áp phân công — phải qua `/duyet`.

    Lưu ý `hung` là `chu_quan` nên được đi thẳng; muốn kiểm cổng thì phải dùng
    một tài khoản NHÂN VIÊN làm người nhận.
    """
    ca_id = "w1_c01"
    kv_set("phan_cong", {ca_id: ["nv_01"]})
    kv_set("phan_cong_by_week", {"2026-W01": {ca_id: ["nv_01"]}})
    kv_set("lich_tuan_lifecycle", {"tuan_iso": "2026-W01", "trang_thai": "da_cong_bo"})
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {"2026-W01": {"tuan_iso": "2026-W01", "trang_thai": "da_cong_bo"}},
    )

    # `lan`=nv_01 (quản lý) mở phiếu nhường ca cho `minh`=nv_03 (nhân viên).
    opened = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_01", "b": "nv_03", "ca_id": ca_id},
        headers=headers(client, "lan"),
    ).json()
    swap_id = opened["id"]

    # Nhân viên là người nhận bấm đồng ý → bị chặn, chưa đụng phân công.
    blocked = client.post(f"/api/v1/cho-doi-ca/{swap_id}/dong-y", headers=headers(client, "minh"))
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "doi_ca_can_quan_ly_duyet"
    assert kv_get("phan_cong", {})[ca_id] == ["nv_01"], "chưa duyệt thì không được đổi"

    # Quản lý đồng ý (đủ hai bên) rồi duyệt → lúc đó mới áp phân công.
    client.post(f"/api/v1/cho-doi-ca/{swap_id}/dong-y", headers=headers(client, "lan"))
    duyet = client.post(f"/api/v1/cho-doi-ca/{swap_id}/duyet", headers=headers(client, "lan"))
    assert duyet.status_code == 200, duyet.text
    assert kv_get("phan_cong", {})[ca_id] == ["nv_03"]


def test_swap_chan_khi_tuan_chua_cong_bo() -> None:
    """Tuần còn nháp thì không đổi ca được, dù hai bên đều đồng ý."""
    week = "2026-W19"
    ca_id = "w1_c01"
    kv_set("phan_cong", {ca_id: ["nv_03"]})
    kv_set("phan_cong_by_week", {week: {ca_id: ["nv_03"]}})
    kv_set("lich_tuan_lifecycle", {"tuan_iso": week, "trang_thai": "nhap"})
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "nhap"}})

    opened = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_03", "b": "nv_02", "ca_id": ca_id},
        headers=headers(client, "minh"),
    ).json()
    blocked = client.post(f"/api/v1/cho-doi-ca/{opened['id']}/dong-y", headers=headers(client, "hung"))
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "lich_chua_cong_bo"


def test_swap_tu_choi_idor_protection() -> None:
    # Đăng ký một nhân viên mới không liên quan đến ca đổi
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": "nv_ngoai_cuoc", "password": "password123", "display_name": "Người Ngoài Cuộc"},
    ).json()
    headers_outsider = {"Authorization": f"Bearer {reg['token']}"}

    opened = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_03", "b": "nv_02", "c": "nv_01", "ca_id": "w1_c01"},
        headers=headers(client, "minh"),
    ).json()
    swap_id = opened["id"]

    # Nhân viên ngoài cuộc không có quyền từ chối yêu cầu đổi ca của người khác
    res_reject = client.post(f"/api/v1/cho-doi-ca/{swap_id}/tu-choi", headers=headers_outsider)
    assert res_reject.status_code == 403
    assert res_reject.json()["detail"] == "khong_phai_nguoi_tham_gia"

    # Người trong cuộc (Minh - nv_03) có quyền từ chối
    res_ok = client.post(f"/api/v1/cho-doi-ca/{swap_id}/tu-choi", headers=headers(client, "minh"))
    assert res_ok.status_code == 200
    assert res_ok.json()["trang_thai"] == "tu_choi"


def test_lich_ics_event_fields_rfc5545() -> None:
    ql = headers(client, "lan")
    from ca_api.persist import kv_mutate
    kv_mutate("phan_cong", lambda _: {"w1_c01": ["nv_01", "nv_02"]}, {})
    ics = client.get("/api/v1/lich/ics", headers=ql).json()
    assert "BEGIN:VCALENDAR" in ics["ics"]
    assert "BEGIN:VEVENT" in ics["ics"]
    assert "DTSTART;TZID=Asia/Ho_Chi_Minh:" in ics["ics"]
    assert "DTEND;TZID=Asia/Ho_Chi_Minh:" in ics["ics"]
    assert "DTSTAMP:" in ics["ics"]
    assert "END:VEVENT" in ics["ics"]



def test_hom_nay_preview_fields() -> None:
    ql = headers(client, "lan")
    body = client.get("/api/v1/hom-nay", headers=ql).json()
    assert "treo_preview" in body
    assert "treo_theo_trang_thai" in body
    assert "sua_gan_day" in body
    assert "ton_tom_tat" in body
    assert "hao_hut" in body, "bảng Hôm nay phải nối được sang mặt hao hụt"


def test_hom_nay_hao_hut_khop_voi_trang_hao_phi() -> None:
    """Bảng Hôm nay và trang Hao phí phải ra CÙNG số.

    Cả hai gọi `ag_waste.tinh_tu_nguon`; test này chốt rằng không ai lỡ tay tính
    riêng ở một trong hai chỗ. Hai đường tự tính là hai cơ hội để lệch số.
    """
    from ca_agents.ag_waste import ngay_hom_nay
    from ca_api.persist import kv_mutate

    hom_nay = ngay_hom_nay()

    def nap_kk(rows: list[dict]) -> list[dict]:
        rows.append(
            {
                "id": "kk_hom_nay_check",
                "ngay": hom_nay,
                "muc": [{"mat_hang": "sua_tuoi", "dau_ca": 25, "nhap_trong_ca": 8, "cuoi_ca": 26, "hao_hut_ghi": 0}],
            }
        )
        return rows

    kv_mutate("kiem_ke", nap_kk, [])

    ql = headers(client, "lan")
    hom_nay_body = client.get("/api/v1/hom-nay", headers=ql).json()
    hao_phi_body = client.get("/api/v1/hao-hut?ky=hom_nay", headers=ql).json()

    hh = hom_nay_body["hao_hut"]
    assert hh["co_du_lieu"] is True
    assert hh["tong_dong"] == hao_phi_body["tong_dong"]
    assert hh["so_thieu_du_lieu"] == hao_phi_body["so_thieu_du_lieu"]
    assert hh["so_nghiem_trong"] == hao_phi_body["so_nghiem_trong"]
    assert hh["so_canh_bao"] == hao_phi_body["so_canh_bao"]


def test_hom_nay_hao_hut_khong_bia_so_khi_rong() -> None:
    """Không có dữ liệu ⇒ `co_du_lieu` false, KHÔNG trả số 0 như thể đã đo."""
    ql = headers(client, "lan")
    body = client.get("/api/v1/hom-nay", headers=ql).json()
    hh = body["hao_hut"]
    assert hh["co_du_lieu"] is False
    assert hh.get("tong_dong", 0) == 0


def test_hom_nay_khong_sap_khi_hao_hut_loi(monkeypatch) -> None:
    """Lỗi ở phần hao hụt KHÔNG được làm sập bảng Hôm nay.

    Đây là trang mở đầu sau đăng nhập — hỏng nó là hỏng cả ca làm việc. Phần hao
    hụt phải tự hạ xuống chứ không kéo cả payload theo.
    """
    from ca_api.interfaces.http import sprint45

    def no(*_a, **_k):
        raise RuntimeError("nguon hao hut hong")

    monkeypatch.setattr(sprint45, "_hao_hut_hom_nay", no)
    ql = headers(client, "lan")
    r = client.get("/api/v1/hom-nay", headers=ql)
    assert r.status_code == 200, r.text
    hh = r.json()["hao_hut"]
    assert hh["co_du_lieu"] is False
    assert hh.get("ly_do") == "khong_doc_duoc"


def test_hom_nay_so_treo_chi_tinh_viec_dang_mo() -> None:
    """so_treo chỉ đếm việc treo chưa xong — việc đã xong không còn là việc treo."""
    from ca_api.persist import kv_set

    kv_set(
        "treo",
        [
            {"id": "t_mo_1", "noi_dung": "việc đang chờ", "trang_thai": "dang_cho"},
            {"id": "t_mo_2", "noi_dung": "việc quá hạn", "trang_thai": "qua_han"},
            {"id": "t_xong_1", "noi_dung": "việc đã xong", "trang_thai": "xong"},
            {"id": "t_xong_2", "noi_dung": "việc đã xong khác", "trang_thai": "xong"},
        ],
    )
    ql = headers(client, "lan")
    body = client.get("/api/v1/hom-nay", headers=ql).json()
    assert body["so_treo"] == 2
    # Preview chỉ liệt kê việc đang mở, không kéo việc đã xong lên.
    ids = [p["id"] for p in body["treo_preview"]]
    assert "t_xong_1" not in ids
    assert "t_xong_2" not in ids
    # Breakdown chỉ gom các trạng thái đang mở.
    breakdown = {b["trang_thai"]: b["so_luong"] for b in body["treo_theo_trang_thai"]}
    assert "xong" not in breakdown
    assert breakdown["dang_cho"] == 1
    assert breakdown["qua_han"] == 1


def test_handover_history_list() -> None:
    nv = headers(client, "minh")
    client.post(
        "/api/v1/handover",
        json={"text": "Tình hình: test\nBối cảnh: a\nĐánh giá: b\nĐề nghị: c"},
        headers=nv,
    )
    items = client.get("/api/v1/handover", headers=nv).json()["items"]
    assert len(items) >= 1


def test_publication_guard_blocks_claimed_shifts(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    """Cannot publish when claimed shifts exist."""
    from ca_api.persist import open_shift_create, shift_application_claim_first
    from ca_api.services.scheduling_service import run_authoritative_schedule
    
    week = "2026-W44"
    ql = headers(client, "lan")
    
    # Create a valid schedule run
    run = run_authoritative_schedule(
        store_id="quan_01", tuan_iso=week, actor_id="lan", idempotency_key="pub-guard-test",
    )
    assert run["status"] == "computed"
    
    # Create and claim an open shift
    shift = open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    shift_application_claim_first(
        open_shift_id=shift["id"], store_id="quan_01", nv_id="nv_03",
    )
    
    # Set lifecycle to da_duyet
    from ca_api.persist import kv_set
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "da_duyet"}})
    
    # Attempt to publish should fail
    r = client.patch(
        "/api/v1/lich-tuan/lifecycle",
        json={"tuan_iso": week, "trang_thai": "da_cong_bo"},
        headers=ql,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "schedule_has_open_shifts"


def test_manager_sees_claimed_shifts_employee_does_not(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    """Manager sees both open and claimed shifts; employee sees only open."""
    from ca_api.persist import open_shift_create, shift_application_claim_first
    
    week = "2026-W44"
    ql = headers(client, "lan")
    nv = headers(client, "minh")
    
    # Create two open shifts
    shift1 = open_shift_create(
        store_id="quan_01", schedule_run_id="vis-test-1", tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    # Ca thứ 2 chỉ để tạo dữ liệu cho test đếm (không cần giữ id).
    open_shift_create(
        store_id="quan_01", schedule_run_id="vis-test-2", tuan_iso=week,
        ca_id="w1_c02", deadline_at="2026-11-01T00:00:00Z",
    )
    
    # Claim one shift
    shift_application_claim_first(
        open_shift_id=shift1["id"], store_id="quan_01", nv_id="nv_03",
    )
    
    # Manager sees both
    manager_items = client.get(f"/api/v1/open-shifts?tuan_iso={week}", headers=ql).json()["items"]
    assert len(manager_items) == 2
    statuses = {item["status"] for item in manager_items}
    assert statuses == {"open", "claimed"}
    
    # Employee sees only open
    employee_items = client.get(f"/api/v1/open-shifts?tuan_iso={week}", headers=nv).json()["items"]
    assert len(employee_items) == 1
    assert employee_items[0]["status"] == "open"


def test_claim_requires_employee_role(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    """Manager cannot claim shifts."""
    from ca_api.persist import open_shift_create, schedule_run_create
    
    week = "2026-W44"
    ql = headers(client, "lan")
    
    run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={}, fingerprint="fp-role",
        idempotency_key="claim-role-test", created_by="lan", status="needs_gap_resolution",
    )
    shift = open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    
    r = client.post(
        "/api/v1/open-shifts/claim",
        json={"open_shift_id": shift["id"]},
        headers=ql,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "chi_nhan_vien_duoc_nhan_ca"


def test_claim_requires_confirmed_availability(_du_nhan_vien_xep_lich: None) -> None:
    """Employee without confirmed availability cannot claim."""
    from ca_api.persist import open_shift_create, schedule_run_create
    
    week = "2026-W44"
    nv = headers(client, "minh")
    
    run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={}, fingerprint="fp-avail",
        idempotency_key="claim-avail-test", created_by="lan", status="needs_gap_resolution",
    )
    shift = open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    
    r = client.post(
        "/api/v1/open-shifts/claim",
        json={"open_shift_id": shift["id"]},
        headers=nv,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "chua_xac_nhan_kha_dung_dung_tuan"


def test_claim_first_claimant_wins(_du_nhan_vien_xep_lich: None, _xac_nhan_kha_dung_tuan: None) -> None:
    """First claimant wins; second gets 409."""
    from ca_api.persist import open_shift_create, schedule_run_create
    
    week = "2026-W44"
    
    run = schedule_run_create(
        store_id="quan_01", tuan_iso=week, input_snapshot={}, fingerprint="fp-race",
        idempotency_key="claim-race-test", created_by="lan", status="needs_gap_resolution",
    )
    shift = open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso=week,
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )
    
    # Register second employee with unique name
    import uuid
    uname = f"nv_race_{uuid.uuid4().hex[:8]}"
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "matkhautot123", "display_name": "Race"},
    )
    assert reg.status_code == 201, reg.text
    nv2 = {"Authorization": f"Bearer {reg.json()['token']}"}
    
    # Confirm availability for second employee
    from ca_api.persist import availability_confirmation_upsert
    nv2_id = reg.json()["nv_id"]
    availability = {day: ["Sáng", "Chiều", "Tối"] for day in ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]}
    availability_confirmation_upsert(
        item_id=f"test-av-{uname}", store_id="quan_01", nv_id=nv2_id,
        tuan_iso=week, availability=availability, status="da_xac_nhan", source="test",
    )
    
    minh = headers(client, "minh")
    
    # First claim succeeds
    r1 = client.post(
        "/api/v1/open-shifts/claim",
        json={"open_shift_id": shift["id"]},
        headers=minh,
    )
    assert r1.status_code == 200
    
    # Second claim fails — shift no longer appears as open, so 404
    r2 = client.post(
        "/api/v1/open-shifts/claim",
        json={"open_shift_id": shift["id"]},
        headers=nv2,
    )
    assert r2.status_code == 404
    assert r2.json()["detail"] == "open_shift_khong_ton_tai"


def test_claim_rejects_expired_shift_atomically() -> None:
    from ca_api.persist import open_shift_create, schedule_run_create, shift_application_claim_first

    run = schedule_run_create(
        store_id="quan_01", tuan_iso="2026-W44", input_snapshot={}, fingerprint="fp-expired",
        idempotency_key="claim-expired-test", created_by="lan", status="needs_gap_resolution",
    )
    shift = open_shift_create(
        store_id="quan_01", schedule_run_id=str(run["id"]), tuan_iso="2026-W44",
        ca_id="w1_c01", deadline_at="2026-11-01T00:00:00Z",
    )

    claimed = shift_application_claim_first(
        open_shift_id=str(shift["id"]), store_id="quan_01", nv_id="nv_03",
        now="2026-11-01T00:00:01Z",
    )
    assert claimed is None
