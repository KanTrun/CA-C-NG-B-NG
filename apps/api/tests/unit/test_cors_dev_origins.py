"""Gate: CORS phải cho phép origin dev local NGAY CẢ KHI có `NHIPQUAN_CORS_ORIGINS`.

Bảo vệ lỗi thật đã vấp (260930): `.env` máy dev có
`NHIPQUAN_CORS_ORIGINS=https://nhipquan.duckdns.org`, và bản cũ hiểu biến đó là
"thay toàn bộ danh sách" → `http://localhost:3000` bị chặn → **mọi e2e đỏ ở
`loginAs`** với timeout `waitForURL` (trông như lỗi điều hướng, thực ra là
preflight CORS thất bại).

Vì sao test bằng CÁCH ĐỌC BIẾN Ở MODULE không đủ: `_cors_origins` được tính một
lần lúc import `main.py`, nên muốn thử với env khác phải import lại module. Ở đây
kiểm trực tiếp danh sách đã tính — đó chính là thứ `CORSMiddleware` nhận — và
kiểm thêm nhánh opt-out bằng cách chạy lại biểu thức với env mô phỏng.
"""

from __future__ import annotations

from ca_api.interfaces.http import main as main_mod


def test_dev_origins_luon_duoc_phep() -> None:
    """Mọi origin dev local phải nằm trong danh sách CORS đang hiệu lực."""
    for origin in main_mod._DEV_CORS_ORIGINS:
        assert origin in main_mod._cors_origins, (
            f"origin dev {origin} bị loại khỏi CORS — e2e và dev local sẽ không "
            f"đăng nhập được (preflight thất bại)"
        )


def test_cors_origins_them_chu_khong_thay_the() -> None:
    """`NHIPQUAN_CORS_ORIGINS` phải THÊM origin, không thay thế danh sách dev.

    Bất biến: origin triển khai (nếu được cấu hình) và origin dev cùng tồn tại.
    """
    for origin in main_mod._configured_cors:
        assert origin in main_mod._cors_origins, (
            f"origin triển khai {origin} không có trong CORS"
        )
    # Nếu máy này có cấu hình origin triển khai, origin dev vẫn phải còn.
    if main_mod._configured_cors:
        assert "http://localhost:3000" in main_mod._cors_origins, (
            "có NHIPQUAN_CORS_ORIGINS nhưng origin dev bị mất → đã quay lại hành vi "
            "'thay thế' (bug cũ)"
        )


def test_preflight_cho_origin_dev_thanh_cong() -> None:
    """Preflight OPTIONS từ origin dev phải trả `access-control-allow-origin`.

    Đây là phép kiểm END-TO-END của chính triệu chứng đã vấp: trình duyệt gửi
    OPTIONS trước, và nếu response thiếu header này thì fetch bị chặn — dù API
    vẫn trả 200 nếu gọi bằng curl.
    """
    from fastapi.testclient import TestClient

    client = TestClient(main_mod.app)
    for origin in ("http://localhost:3000", "http://127.0.0.1:3001"):
        r = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        allow = r.headers.get("access-control-allow-origin")
        assert allow == origin, (
            f"preflight từ {origin} không được cho phép (allow-origin={allow!r}) — "
            f"trình duyệt sẽ chặn đăng nhập"
        )
