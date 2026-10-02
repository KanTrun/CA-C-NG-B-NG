# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from __future__ import annotations

from ca_api.interfaces.http.main import app
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_chu_quan_alone_can_manage_menu_and_people() -> None:
    ql = headers(client, "lan")
    chu = headers(client, "hung")

    assert client.get("/api/v1/nguoi", headers=ql).status_code == 403
    people = client.get("/api/v1/nguoi", headers=chu)
    assert people.status_code == 200
    assert {x["username"] for x in people.json()["items"]} >= {"lan", "minh", "hung"}

    forbidden = client.put(
        "/api/v1/menu/tra_chanh",
        json={"ten": "Trà chanh", "gia": 20000, "bom": {"ly": 1}},
        headers=ql,
    )
    assert forbidden.status_code == 403
    saved = client.put(
        "/api/v1/menu/tra_chanh",
        json={"ten": "Trà chanh", "gia": 20000, "bom": {"ly": 1}},
        headers=chu,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["nguon"] == "quan"

    registered = client.post(
        "/api/v1/auth/register",
        json={"username": "hoa", "password": "matkhau01", "display_name": "Hoa"},
    )
    assert registered.status_code == 201
    promoted = client.post("/api/v1/nguoi/hoa/nang-vai", json={}, headers=chu)
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "quan_ly"
    demoted = client.post("/api/v1/nguoi/hoa/ha-vai", json={}, headers=chu)
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["role"] == "nhan_vien"


def test_pos_requires_checkin_then_ban_pha_la_hang_doi_chung() -> None:
    """Cổng điểm danh giữ nguyên; bàn pha thì là HÀNG ĐỢI CHUNG của cả ca.

    Bản trước khẳng định ngược lại: nhân viên chỉ thấy và chỉ thao tác được đơn
    của chính mình. Điều đó đúng cho "ghi đơn của tôi" nhưng sai cho bàn pha — ca
    bàn giao tiếp nhau, đơn lúc bàn giao vẫn mang `nv_id` của người ghi, nên bàn
    pha trở thành danh sách riêng của từng người và không ai pha nổi đơn dở dang
    của ca trước.
    """
    minh = headers(client, "minh")
    hung = headers(client, "hung")
    body = {"dong": [{"mon_id": "mon_sua", "so_luong": 2}], "thanh_toan": "chua_thu"}

    # Cổng điểm danh không nới: chưa điểm danh thì không ghi được đơn.
    assert client.post("/api/v1/quay/don", json=body, headers=minh).status_code == 403

    assert client.post("/api/v1/diem-danh", headers=minh).status_code == 200
    mine = client.post("/api/v1/quay/don", json=body, headers=minh)
    assert mine.status_code == 201, mine.text
    assert mine.json()["trang_thai"] == "cho_pha"

    assert client.post("/api/v1/diem-danh", headers=hung).status_code == 200
    other = client.post("/api/v1/quay/don", json=body, headers=hung)
    assert other.status_code == 201

    # Hàng đợi chung: người pha thấy đơn của đồng nghiệp.
    listed = client.get("/api/v1/quay/don", headers=minh)
    assert listed.status_code == 200
    ids = [x["id"] for x in listed.json()["items"]]
    assert mine.json()["id"] in ids
    assert other.json()["id"] in ids, "nhân viên không thấy đơn của đồng nghiệp"

    # Và nhận pha được đơn của người khác — trước đây trả 403 ở đây.
    nhan = client.post(
        f"/api/v1/quay/don/{other.json()['id']}/chuyen",
        json={"trang_thai": "dang_pha"},
        headers=minh,
    )
    assert nhan.status_code == 200, nhan.text
    assert nhan.json()["trang_thai"] == "dang_pha"


def test_quay_don_gioi_han_theo_ngay_va_chi_so() -> None:
    """`?tu=` và `?limit=` chặn endpoint trả nguyên bảng `don_quay`."""
    hung = headers(client, "hung")
    assert client.post("/api/v1/diem-danh", headers=hung).status_code == 200
    tao = client.post(
        "/api/v1/quay/don",
        json={"dong": [{"mon_id": "mon_sua", "so_luong": 1}], "thanh_toan": "chua_thu"},
        headers=hung,
    )
    assert tao.status_code == 201, tao.text
    don_id = tao.json()["id"]

    # Mốc ở tương lai: không đơn nào lọc trúng, kể cả đơn vừa tạo.
    r = client.get("/api/v1/quay/don?tu=2999-01-01T00:00:00Z", headers=hung)
    assert r.status_code == 200
    assert don_id not in [x["id"] for x in r.json()["items"]]

    # `limit` là trần cứng, không phải gợi ý.
    r = client.get("/api/v1/quay/don?limit=1", headers=hung)
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 1

    assert client.get("/api/v1/quay/don?limit=0", headers=hung).status_code == 422
    assert client.get("/api/v1/quay/don?limit=9999", headers=hung).status_code == 422


def test_menu_luu_tu_chan_nhom_ngoai_danh_muc() -> None:
    """Mã nhóm ngoài danh mục phải bị chặn lúc ghi, không phải lúc hiển thị.

    UI chỉ vẽ nhóm có trong `NHOM_MON_THU_TU`, nên món mang mã lạ sẽ biến mất
    khỏi quầy mà không một dòng cảnh báo. Chặn ở tầng ghi rẻ hơn nhiều so với
    truy ra món mất.
    """
    chu = headers(client, "hung")
    r = client.put(
        "/api/v1/menu/mon_nhom_la",
        json={"ten": "Món nhóm lạ", "gia": 20000, "nhom": "phan_bo", "bom": {"ly": 1}},
        headers=chu,
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "nhom_khong_hop_le"

    ok = client.put(
        "/api/v1/menu/mon_nhom_hop_le",
        json={"ten": "Món nhóm hợp lệ", "gia": 20000, "nhom": "banh", "bom": {"banh": 1}},
        headers=chu,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["nhom"] == "banh"


def test_complete_order_records_estimated_consumption_and_manager_can_fix_active_order() -> None:
    minh = headers(client, "minh")
    lan = headers(client, "lan")
    assert client.post("/api/v1/diem-danh", headers=minh).status_code == 200
    created = client.post(
        "/api/v1/quay/don",
        json={"dong": [{"mon_id": "mon_sua", "so_luong": 2}], "thanh_toan": "chua_thu"},
        headers=minh,
    )
    assert created.status_code == 201, created.text
    don_id = created.json()["id"]

    assert client.post("/api/v1/diem-danh", headers=lan).status_code == 200
    fixed = client.post(
        f"/api/v1/quay/don/{don_id}/chinh",
        json={"dong": [{"mon_id": "mon_sua", "so_luong": 3}], "thanh_toan": "da_ck"},
        headers=lan,
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["dong"][0]["so_luong"] == 3

    assert client.post(
        f"/api/v1/quay/don/{don_id}/chuyen", json={"trang_thai": "dang_pha"}, headers=minh
    ).status_code == 200
    done = client.post(
        f"/api/v1/quay/don/{don_id}/chuyen", json={"trang_thai": "xong"}, headers=minh
    )
    assert done.status_code == 200, done.text
    assert client.post(
        f"/api/v1/quay/don/{don_id}/chuyen", json={"trang_thai": "xong"}, headers=minh
    ).status_code == 409

    payload = client.get("/api/v1/tieu-thu", headers=minh).json()
    consumption = payload["items"]
    from_order = [x for x in consumption if x.get("don_quay_id") == don_id]
    # Sổ trả MÃ chuẩn + TÊN CÓ DẤU + đúng đơn vị. Mốc cũ `{"cafe_g","sua_ml","ly"}`
    # chính là mã legacy làm `/tieu-thu` hiện "Cà phê / Sua tuoi / đơn vị".
    assert {x["ma"] for x in from_order} == {"ca_phe_hat", "sua_tuoi", "ly"}
    assert {x["hang"] for x in from_order} == {
        "Cà phê hạt",
        "Sữa tươi",
        "Ly / cốc dùng một lần",
    }
    assert {x["don_vi"] for x in from_order} == {"g", "ml", "cái"}
    assert {x["nhom"] for x in from_order} == {"ca_phe"}
    assert all(x["nguon"] == "uoc_luong_tu_quay" for x in from_order)
    # `tong_hop` gộp một dòng cho một nguyên liệu — trang `/tieu-thu` vẽ cái này.
    assert {d["ma"] for d in payload["tong_hop"]} == {"ca_phe_hat", "sua_tuoi", "ly"}
    assert all(d["so_dong"] >= 1 for d in payload["tong_hop"])
    # Mỗi dòng trừ kho phải nối về đúng món đã bán (Cà phê sữa ×3), không chỉ
    # ra mã BOM trơ — sổ tiêu thụ đọc lúc khoá ca cần vết "ai dùng cái gì".
    assert all(x["mon_id"] == "mon_sua" for x in from_order)
    assert all(x["mon_ten"] == "Cà phê sữa" and x["mon_so_luong"] == 3 for x in from_order)

    report = client.get("/api/v1/quay/bao-cao", headers=lan)
    assert report.status_code == 200
    assert report.json()["tong_ly"] == 3
