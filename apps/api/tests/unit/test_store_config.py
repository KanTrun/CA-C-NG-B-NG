# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test cấu hình quán (/cau-hinh-quan) — thông tin thật thay dữ liệu mock ảo.

Sau audit 260924 (`apps/api/src/ca_api/services/store_public_context.py` từng
hardcode địa chỉ/hotline/wifi giả), nhóm test này chốt 3 hợp đồng:

1. Mặc định KHÔNG có thông tin bịa — tất cả trường rỗng, prompt ghi
   "(chưa cập nhật)", không còn "123 Đường Cà Phê" hay "0901234567".
2. Quản lý PUT thông tin thật => GET đọc lại đúng + prompt phản ánh đúng, kể cả
   `huong_dan_agent` (hướng dẫn riêng chủ quán cho AI agent).
3. Menu công khai KHÔNG phục vụ món fixture (`fx_*`) ra khách.
4. RBAC: nhân viên không được PUT (403).
"""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from fastapi.testclient import TestClient

from unit.auth_util import headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_profile_mac_dinh_rong_khong_co_du_lieu_bia(client: TestClient) -> None:
    """DB mới (chưa cấu hình) phải trả mọi trường rỗng — không địa chỉ/hotline giả."""
    ql = headers(client, "lan")
    r = client.get("/api/v1/store/profile", headers=ql)
    assert r.status_code == 200, r.text
    p = r.json()
    # Các giá trị giả từng hardcode — phải không còn xuất hiện.
    for key in ("ten_quan", "dia_chi", "tinh", "thanh_pho", "hotline", "gio_mo_cua", "wifi_ssid", "wifi_pass", "huong_dan_agent"):
        assert str(p.get(key) or "").strip() == "", f"{key} phải rỗng khi chưa cấu hình, được {p.get(key)!r}"
    assert "123 Đường Cà Phê" not in str(p)
    assert "0901234567" not in str(p)


def test_profile_chan_nguoi_chua_dang_nhap(client: TestClient) -> None:
    """Bug QA đợt 6 (#38): hồ sơ quán KHÔNG được đọc khi chưa đăng nhập.

    Trước đây `get_profile()` không nhận `authorization` nên trả 200 cho mọi
    người — kể cả `wifi_pass` và `huong_dan_agent` (hướng dẫn nội bộ cho AI).
    """
    assert client.get("/api/v1/store/profile").status_code == 401
    assert client.get("/api/v1/store/profile", headers={"Authorization": "Bearer token_bom"}).status_code == 401
    # Cùng lỗ hổng ở endpoint khuyến mãi.
    assert client.get("/api/v1/store/promotions").status_code == 401


def test_prompt_mac_dinh_noi_chua_cap_nhat(client: TestClient) -> None:
    from ca_api.services.store_public_context import format_public_context_for_prompt

    text = format_public_context_for_prompt()
    assert "(chưa cập nhật)" in text
    assert "123 Đường Cà Phê" not in text
    assert "nhipquan2026" not in text


def test_quan_ly_put_profile_va_doc_lai(client: TestClient) -> None:
    ql = headers(client, "lan")
    payload = {
        "ten_quan": "Cà phê Thật Là Thật",
        "dia_chi": "45 Nguyễn Huệ, Q.1, TP. HCM",
        "hotline": "0987654321",
        "gio_mo_cua": "07:00 - 21:00",
        "huong_dan_agent": "Luôn xưng em, không hứa giảm giá.",
    }
    r = client.put("/api/v1/store/profile", json=payload, headers=ql)
    assert r.status_code == 200, r.text

    got = client.get("/api/v1/store/profile", headers=ql).json()
    assert got["ten_quan"] == "Cà phê Thật Là Thật"
    assert got["dia_chi"] == "45 Nguyễn Huệ, Q.1, TP. HCM"
    assert got["huong_dan_agent"] == "Luôn xưng em, không hứa giảm giá."

    from ca_api.services.store_public_context import format_public_context_for_prompt

    text = format_public_context_for_prompt()
    assert "45 Nguyễn Huệ" in text
    assert "Luôn xưng em" in text  # hướng dẫn lọt vào prompt agent


def test_put_profile_bo_key_la_khong_ghi(client: TestClient) -> None:
    """Key ngoài PROFILE_FIELDS bị lọc — không thể nhồi field lạ vào KV."""
    ql = headers(client, "lan")
    r = client.put(
        "/api/v1/store/profile",
        json={"ten_quan": "Quán A", "admin_password": " hack "},
        headers=ql,
    )
    assert r.status_code == 200, r.text
    got = client.get("/api/v1/store/profile", headers=ql).json()
    assert "admin_password" not in got
    assert got["ten_quan"] == "Quán A"


def test_nhan_vien_khong_doi_duoc_profile(client: TestClient) -> None:
    nv = headers(client, "minh")
    r = client.put(
        "/api/v1/store/profile",
        json={"ten_quan": "Quán bịa"},
        headers=nv,
    )
    assert r.status_code == 403, r.text


def test_public_menu_khong_co_mon_fixture(client: TestClient) -> None:
    """Món seed fixture `fx_*` không được ra menu công khai phục vụ khách."""
    from ca_api.persist import init_db, menu_upsert

    init_db()
    menu_upsert({"id": "fx_mon_test_fake", "ten": "Món fixture", "gia": 1})
    menu_upsert({"id": "mon_that_test", "ten": "Món thật", "gia": 2})

    from ca_api.services.store_public_context import get_public_menu

    items = get_public_menu()
    ids = [i["id"] for i in items]
    ten = [i["ten"] for i in items]
    assert "fx_mon_test_fake" not in ids
    assert "Món fixture" not in ten
    assert all(not i["id"].startswith("fx_") for i in items)
