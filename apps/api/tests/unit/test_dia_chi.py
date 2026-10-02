# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Unit tests cho API danh mục địa chỉ Việt Nam (/api/v1/geo/...) và các trường thông tin quán mở rộng."""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from fastapi.testclient import TestClient

from unit.auth_util import headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_dia_chi_chan_nguoi_chua_dang_nhap(client: TestClient) -> None:
    """Các endpoint địa lý yêu cầu đăng nhập."""
    assert client.get("/api/v1/geo/provinces").status_code == 401
    assert client.get("/api/v1/geo/wards/79").status_code == 401


def test_lay_danh_sach_tinh_thanh(client: TestClient) -> None:
    """Trả về danh sách các tỉnh thành với đầy đủ mã và tên."""
    ql = headers(client, "lan")
    r = client.get("/api/v1/geo/provinces", headers=ql)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    # Bản sau sáp nhập 07/2025 (Nghị quyết 202/2025/QH15): đúng 34 đơn vị cấp tỉnh.
    # Số 63 nghĩa là đang trỏ nhầm sang bản v1 cũ của provinces.open-api.vn.
    assert len(items) == 34
    codes = [p["code"] for p in items]
    names = [p["name"] for p in items]
    # TP HCM và Hà Nội phải có trong danh sách
    assert 79 in codes or any("Hồ Chí Minh" in n for n in names)
    assert 1 in codes or any("Hà Nội" in n for n in names)
    # Các đơn vị đã sáp nhập không còn tồn tại ở cấp tỉnh
    assert not any("Bình Dương" in n for n in names)
    assert not any("Long An" in n for n in names)


def test_lay_phuong_xa_theo_tinh(client: TestClient) -> None:
    """Cấp quận/huyện đã bỏ — phường/xã lấy thẳng theo mã tỉnh (chính quyền 2 cấp)."""
    ql = headers(client, "lan")

    # Endpoint cấp quận/huyện không còn nữa
    assert client.get("/api/v1/geo/districts/79", headers=ql).status_code == 404

    r = client.get("/api/v1/geo/wards/79", headers=ql)
    assert r.status_code == 200, r.text
    wards = r.json()
    assert isinstance(wards, list)
    assert len(wards) > 100
    assert all(w["province_code"] == 79 for w in wards)
    # Chứng minh là dữ liệu SAU sáp nhập: TP.HCM gộp Bình Dương nên có phường Thủ Dầu Một,
    # và không còn "Quận 1" kiểu cũ.
    assert any("Thủ Dầu Một" in w["name"] for w in wards)
    assert not any(w["name"] == "Quận 1" for w in wards)


def test_store_profile_luu_thong_tin_dia_chi_va_tien_ich_mo_rong(client: TestClient) -> None:
    """Quản lý lưu hồ sơ quán đầy đủ (địa chỉ chuẩn hóa, thanh toán, tiện ích, email)."""
    ql = headers(client, "lan")
    payload = {
        "ten_quan": "Nhịp Quán Specialty Coffee",
        "slogan": "Cà phê mộc, không gian làm việc tĩnh lặng",
        "dia_chi_chi_tiet": "45 Nguyễn Huệ",
        "phuong_xa": "Phường Bến Thành",
        "phuong_xa_code": "26743",
        # Cấp quận/huyện hết hiệu lực từ 07/2025 — trường cũ giữ lại để không phá
        # dữ liệu/nhà gọi cũ, hồ sơ mới để trống.
        "quan_huyen": "",
        "quan_huyen_code": "",
        "tinh": "Thành phố Hồ Chí Minh",
        "tinh_code": "79",
        "dia_chi": "45 Nguyễn Huệ, Phường Bến Thành, Thành phố Hồ Chí Minh",
        "hotline": "0901234567",
        "hotline_phu": "0909888999",
        "email": "contact@nhipquan.vn",
        "fanpage_url": "https://facebook.com/nhipquancoffee",
        "website": "https://nhipquan.vn",
        "gio_mo_cua": "07:00 - 22:30",
        "khoang_gia": "35.000đ - 75.000đ",
        "tien_ich": "Máy lạnh, Wifi mạnh, Chỗ đỗ ô tô, Ổ cắm laptop",
        "ngan_hang": "Vietcombank",
        "stk_ngan_hang": "0071001234567",
        "chu_tai_khoan": "TRAN VAN HUNG",
        "wifi_ssid": "NhipQuan_Guest",
        "wifi_pass": "nhipquan2026",
    }
    r = client.put("/api/v1/store/profile", json=payload, headers=ql)
    assert r.status_code == 200, r.text

    got = client.get("/api/v1/store/profile", headers=ql).json()
    assert got["slogan"] == "Cà phê mộc, không gian làm việc tĩnh lặng"
    assert got["email"] == "contact@nhipquan.vn"
    assert got["ngan_hang"] == "Vietcombank"
    assert got["stk_ngan_hang"] == "0071001234567"
    assert got["chu_tai_khoan"] == "TRAN VAN HUNG"
    assert got["phuong_xa"] == "Phường Bến Thành"
    assert got["quan_huyen"] == ""

    from ca_api.services.store_public_context import format_public_context_for_prompt

    prompt_text = format_public_context_for_prompt()
    assert "Slogan: Cà phê mộc" in prompt_text
    assert "Email: contact@nhipquan.vn" in prompt_text
    assert "Vietcombank - STK: 0071001234567" in prompt_text
    assert "Tiện ích quán: Máy lạnh" in prompt_text


def test_store_profile_chan_email_va_hotline_sai(client: TestClient) -> None:
    """Validate chặn email và hotline phụ không hợp lệ."""
    ql = headers(client, "lan")
    # Email sai định dạng
    r1 = client.put("/api/v1/store/profile", json={"email": "invalid_email"}, headers=ql)
    assert r1.status_code == 422

    # Hotline phụ chứa chữ
    r2 = client.put("/api/v1/store/profile", json={"hotline_phu": "so_dien_thoai_chu"}, headers=ql)
    assert r2.status_code == 422


def test_geocode_address_api(client: TestClient) -> None:
    """Kiểm tra tra cứu toạ độ từ địa chỉ quán qua /api/v1/geo/geocode."""
    assert client.get("/api/v1/geo/geocode?address=Hồ+Chí+Minh").status_code == 401

    ql = headers(client, "lan")
    r = client.get("/api/v1/geo/geocode?address=Hồ+Chí+Minh", headers=ql)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["found"] is True
    assert data["lat"] is not None
    assert data["lon"] is not None

    # Địa chỉ rỗng không tìm thấy
    r_empty = client.get("/api/v1/geo/geocode?address=dia_chi_khong_ton_tai_xyz123456789", headers=ql)
    assert r_empty.status_code == 200
    assert r_empty.json()["found"] is False

