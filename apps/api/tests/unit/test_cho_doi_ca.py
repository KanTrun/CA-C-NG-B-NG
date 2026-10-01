# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Chợ đổi ca — phạm vi đọc và đo rủi ro kẹt ca.

Người dùng phàn nàn: "bấm người cần đổi ca (nó cho 1 loạt người để chọn) — rủi ro
ở đây là gì, họ có bị kẹt ở ca nào không sao mà biết được, rồi đổi ca ở tuần nào
cũng không hiển thị".

Hai lỗi gốc được chốt ở đây:
  1. `GET /cho-doi-ca` trả NGUYÊN `kv_get("swap", [])` cho mọi vai — nhân viên
     đọc được toàn bộ phiếu của quán. Lọc ở client KHÔNG phải là bảo vệ.
  2. Không có phép ĐO nào nói người nhận có bị kẹt ca hay không, và phiếu không
     mang tuần nên không biết nó thuộc tuần nào.
"""

from __future__ import annotations

from ca_api.interfaces.http.main import app
from ca_api.persist import kv_get, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def _tuan_cong_bo(week: str, phan: dict[str, list[str]] | None = None) -> None:
    kv_set("lich_tuan_lifecycle", {"tuan_iso": week, "trang_thai": "da_cong_bo"})
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "da_cong_bo"}})
    if phan is not None:
        kv_set("phan_cong", phan)
        kv_set("phan_cong_by_week", {week: phan})


def test_swap_list_chi_tra_phieu_lien_quan_toi() -> None:
    """Nhân viên CHỈ thấy phiếu mình là người nhường/nhận hoặc phiếu mở cho mọi người.

    Đây là rò dữ liệu thật ở bản cũ: `kv_get("swap", [])` trả hết.
    """
    week = "2026-W31"
    _tuan_cong_bo(week)
    kv_set(
        "swap",
        [
            {"id": "sw_cua_toi", "a": "nv_03", "b": "nv_02", "ca_id": "w1_c01",
             "trang_thai": "cho_xac_nhan", "tuan_id": week},
            {"id": "sw_cong_khai", "a": "nv_01", "b": "all", "ca_id": "w1_c02",
             "trang_thai": "cho_xac_nhan", "tuan_id": week},
            {"id": "sw_nguoi_khac", "a": "nv_02", "b": "nv_01", "ca_id": "w1_c03",
             "trang_thai": "cho_xac_nhan", "tuan_id": week},
        ],
    )
    try:
        body = client.get("/api/v1/cho-doi-ca", headers=headers(client, "minh")).json()
        ids = {it["id"] for it in body["items"]}
        assert "sw_cua_toi" in ids
        assert "sw_cong_khai" in ids
        # Phiếu của hai người KHÁC không được lộ ra cho nhân viên này.
        assert "sw_nguoi_khac" not in ids
        assert body["toi_la_quan_ly"] is False
    finally:
        kv_set("swap", [])


def test_swap_list_quan_ly_thay_tat_ca_va_co_co_duyet() -> None:
    """Quản lý thấy hết phiếu và có cờ `toi_la_quan_ly` để UI hiện nút duyệt."""
    week = "2026-W32"
    _tuan_cong_bo(week)
    kv_set(
        "swap",
        [
            {"id": "sw_a", "a": "nv_02", "b": "nv_01", "ca_id": "w1_c01",
             "trang_thai": "cho_xac_nhan", "tuan_id": week},
            {"id": "sw_b", "a": "nv_01", "b": "nv_02", "ca_id": "w1_c02",
             "trang_thai": "cho_xac_nhan", "tuan_id": week},
        ],
    )
    try:
        body = client.get("/api/v1/cho-doi-ca", headers=headers(client, "lan")).json()
        assert body["toi_la_quan_ly"] is True
        assert len(body["items"]) == 2
    finally:
        kv_set("swap", [])


def test_swap_mang_tuan_va_do_rui_ro() -> None:
    """Mỗi phiếu phải kèm `tuan_id` (bản cũ UI không đọc) và khối `rui_ro`."""
    week = "2026-W33"
    _tuan_cong_bo(week, {"w1_c01": ["nv_01"], "w1_c02": []})
    kv_set(
        "swap",
        [{"id": "sw_r", "a": "nv_01", "b": "nv_02", "ca_id": "w1_c01",
          "trang_thai": "cho_xac_nhan", "tuan_id": week}],
    )
    try:
        items = client.get("/api/v1/cho-doi-ca", headers=headers(client, "lan")).json()["items"]
        it = next(x for x in items if x["id"] == "sw_r")
        rr = it["rui_ro"]
        assert rr["tuan_id"] == week
        assert rr["ca_id"] == "w1_c01"
        # Người nhường có thật trong ca → không bị chặn vì lý do đó.
        assert rr["nguoi_nhuong_dang_trong_ca"] is True
        assert rr["ly_do_chan"] == ""
        assert rr["co_the_nhan"] is True
    finally:
        kv_set("swap", [])


def test_rui_ro_bao_khi_nguoi_nhan_dang_co_ca_trung_gio() -> None:
    """Người nhận đã có ca khác trùng giờ → phải CHỈ RÕ ca nào, không chỉ nói 'không được'.

    Đây chính là câu hỏi "họ có bị kẹt ở ca nào không, sao mà biết được".
    """
    week = "2026-W34"
    # nv_02 đang trực w1_c02 cùng thứ với w1_c01 (đều T2 trong seed).
    _tuan_cong_bo(week, {"w1_c01": ["nv_01"], "w1_c02": ["nv_02"]})
    kv_set(
        "swap",
        [{"id": "sw_k", "a": "nv_01", "b": "nv_02", "ca_id": "w1_c01",
          "trang_thai": "cho_xac_nhan", "tuan_id": week}],
    )
    try:
        items = client.get("/api/v1/cho-doi-ca", headers=headers(client, "lan")).json()["items"]
        rr = next(x for x in items if x["id"] == "sw_k")["rui_ro"]
        assert rr["co_the_nhan"] is False
        assert rr["ly_do_chan"] == "nguoi_nhan_dang_co_ca_trung_gio"
        assert [c["ca_id"] for c in rr["nguoi_nhan_dang_trung"]] == ["w1_c02"]
        assert rr["nguoi_nhan_dang_trung"][0]["gio"]
    finally:
        kv_set("swap", [])


def test_rui_ro_bao_khi_nguoi_nhuong_khong_trong_ca() -> None:
    """Phiếu nhường ca mà người nhường KHÔNG trực ca đó → phiếu không thực hiện được."""
    week = "2026-W35"
    _tuan_cong_bo(week, {"w1_c01": ["nv_03"]})
    kv_set(
        "swap",
        [{"id": "sw_x", "a": "nv_01", "b": "nv_02", "ca_id": "w1_c01",
          "trang_thai": "cho_xac_nhan", "tuan_id": week}],
    )
    try:
        items = client.get("/api/v1/cho-doi-ca", headers=headers(client, "lan")).json()["items"]
        rr = next(x for x in items if x["id"] == "sw_x")["rui_ro"]
        assert rr["nguoi_nhuong_dang_trong_ca"] is False
        assert rr["co_the_nhan"] is False
        assert rr["ly_do_chan"] == "ca_khong_trong_phan_cong_cua_nguoi_nhuong"
    finally:
        kv_set("swap", [])


def test_swap_list_can_token() -> None:
    """Chưa đăng nhập thì 401, không trả dữ liệu phiếu."""
    r = client.get("/api/v1/cho-doi-ca")
    assert r.status_code == 401


def test_swap_open_chan_khi_nguoi_nhuong_khong_giu_ca() -> None:
    """Không được mở phiếu nhả ca mình KHÔNG giữ — phiếu rác, duyệt mới lộ."""
    week = "2026-W36"
    _tuan_cong_bo(week, {"w1_c01": ["nv_01"]})
    try:
        r = client.post(
            "/api/v1/cho-doi-ca",
            json={"a": "nv_03", "b": "nv_02", "ca_id": "w1_c01"},
            headers=headers(client, "minh"),
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "nguoi_nhuong_khong_trong_ca"
    finally:
        kv_set("swap", [])


def test_swap_open_gan_dung_tuan_duoc_chon() -> None:
    """Phiếu mở khi đang xem tuần khác phải gắn đúng tuần đó, không rơi nhầm."""
    cur, target = "2026-W37", "2026-W38"
    kv_set("lich_tuan_lifecycle", {"tuan_iso": cur, "trang_thai": "da_cong_bo"})
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {
            cur: {"tuan_iso": cur, "trang_thai": "da_cong_bo"},
            target: {"tuan_iso": target, "trang_thai": "da_cong_bo"},
        },
    )
    kv_set("phan_cong", {"w1_c01": ["nv_03"]})
    kv_set("phan_cong_by_week", {target: {"w1_c01": ["nv_03"]}})
    try:
        r = client.post(
            "/api/v1/cho-doi-ca",
            json={"a": "nv_03", "b": "nv_02", "ca_id": "w1_c01", "tuan": target},
            headers=headers(client, "minh"),
        )
        assert r.status_code == 200, r.text
        assert r.json()["tuan_id"] == target
    finally:
        kv_set("swap", [])


def test_swap_dong_y_duyet_duoc_o_tuan_da_duyet() -> None:
    """Tuần `da_duyet` cũng là chốt — đồng ý + duyệt chạy như tuần công bố."""
    week = "2026-W39"
    ca_id = "w1_c01"
    kv_set("lich_tuan_lifecycle", {"tuan_iso": week, "trang_thai": "da_duyet"})
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {week: {"tuan_iso": week, "trang_thai": "da_duyet"}},
    )
    kv_set("phan_cong", {ca_id: ["nv_01"]})
    kv_set("phan_cong_by_week", {week: {ca_id: ["nv_01"]}})
    try:
        opened = client.post(
            "/api/v1/cho-doi-ca",
            json={"a": "nv_01", "b": "nv_03", "ca_id": ca_id},
            headers=headers(client, "lan"),
        )
        assert opened.status_code == 200, opened.text
        swap_id = opened.json()["id"]
        blocked = client.post(
            f"/api/v1/cho-doi-ca/{swap_id}/dong-y", headers=headers(client, "minh")
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "doi_ca_can_quan_ly_duyet"
        client.post(f"/api/v1/cho-doi-ca/{swap_id}/dong-y", headers=headers(client, "lan"))
        duyet = client.post(
            f"/api/v1/cho-doi-ca/{swap_id}/duyet", headers=headers(client, "lan")
        )
        assert duyet.status_code == 200, duyet.text
        assert kv_get("phan_cong_by_week", {})[week][ca_id] == ["nv_03"]
    finally:
        kv_set("swap", [])
