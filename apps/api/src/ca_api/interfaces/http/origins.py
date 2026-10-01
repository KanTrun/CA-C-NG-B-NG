"""Nguồn sự thật duy nhất cho danh sách origin của web PWA.

Vì sao tách riêng: danh sách này được dùng ở HAI nơi khác nhau —

1. `main.py` cấu hình CORS (middleware).
2. `gmail.py` quyết định đích chuyển hướng sau OAuth callback.

Trước đây chỉ `main.py` giữ danh sách, còn callback chuyển hướng bằng đường
dẫn TƯƠNG ĐỐI `/gmail`. Đường dẫn tương đối được trình duyệt ghép với origin
của API (`http://localhost:8000/gmail`) trong khi web nằm ở cổng khác
(`http://localhost:3000`) ⇒ người dùng kết nối xong lại nhận 404 và không bao
giờ thấy thông báo "Đã kết nối Gmail". Gộp danh sách về một chỗ để hai nơi
không thể lệch nhau.
"""

from __future__ import annotations

import os

# Origin dev local — dùng khi `NHIPQUAN_CORS_ORIGINS` bỏ trống.
# Đặt biến đó (danh sách cách nhau bởi dấu phẩy) sẽ THAY THẾ toàn bộ danh sách
# này; xem `.env.example`.
DEFAULT_WEB_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://[::1]:3000",
    "http://[::1]:3001",
    "http://[::1]:3002",
)


def allowed_web_origins() -> list[str]:
    """Danh sách origin được phép, theo `NHIPQUAN_CORS_ORIGINS` nếu có."""
    configured = [
        origin.strip()
        for origin in os.environ.get("NHIPQUAN_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return configured or list(DEFAULT_WEB_ORIGINS)


def resolve_web_base(origin: str | None) -> str:
    """Base URL của web PWA để chuyển hướng trình duyệt về — "" nghĩa là tương đối.

    - `origin` nằm trong danh sách cho phép ⇒ dùng chính origin đó.
    - Ngược lại (thiếu header, hoặc origin lạ) ⇒ trả "" để giữ đường dẫn tương
      đối. Đây là nhánh ĐÚNG cho production sau reverse-proxy: web và API cùng
      một origin nên `/gmail` tương đối trỏ đúng vào Next.js. Trả về origin của
      kẻ tấn công ở đây sẽ biến callback thành open-redirect, nên origin không
      khớp danh sách KHÔNG bao giờ được dùng.
    """
    candidate = (origin or "").strip().rstrip("/")
    if candidate and candidate in allowed_web_origins():
        return candidate
    return ""
