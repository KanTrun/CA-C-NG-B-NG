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

Ngữ nghĩa CỘNG (additive), không thay thế: origin dev local LUÔN được phép;
`NHIPQUAN_CORS_ORIGINS` chỉ THÊM origin triển khai. Bản thay-thế cũ từng gây
lỗi thật (260930): `.env` máy dev có
`NHIPQUAN_CORS_ORIGINS=https://nhipquan.duckdns.org` là `localhost:3000` bị
chặn, trình duyệt chặn preflight và UI báo "Chưa nối được máy chủ quán" trong
khi API vẫn 200 qua curl — toàn bộ e2e đỏ ở bước đăng nhập. Cộng cũng đúng về
bảo mật ở hệ này: xác thực dùng Bearer token trong header (KHÔNG cookie
phiên), nên CORS không phải ranh giới xác thực. Muốn chặt hơn ở production:
đặt `NHIPQUAN_CORS_DISABLE_DEV=1`.
"""

from __future__ import annotations

import os

# Origin dev local — LUÔN được phép trừ khi `NHIPQUAN_CORS_DISABLE_DEV=1`.
DEV_WEB_ORIGINS: tuple[str, ...] = (
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

# Tên cũ, giữ để không phá import nào đang dùng.
DEFAULT_WEB_ORIGINS: tuple[str, ...] = DEV_WEB_ORIGINS


def _dev_enabled() -> bool:
    """Origin dev có được phép không (opt-out cho production siết chặt)."""
    return os.environ.get("NHIPQUAN_CORS_DISABLE_DEV", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }


def configured_web_origins() -> list[str]:
    """Origin triển khai khai tường minh trong `NHIPQUAN_CORS_ORIGINS`."""
    return [
        origin.strip()
        for origin in os.environ.get("NHIPQUAN_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]


def allowed_web_origins() -> list[str]:
    """Mọi origin được phép: triển khai (nếu có) CỘNG origin dev (trừ khi tắt)."""
    return list(
        dict.fromkeys(
            [*configured_web_origins(), *(_dev_enabled() and list(DEV_WEB_ORIGINS) or [])]
        )
    )


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
