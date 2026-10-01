"""Tiện ích mở trình duyệt Camoufox để người dùng tự đăng nhập Threads an toàn.

Mục đích:
    - Người dùng tự gõ tài khoản và mật khẩu trên máy tính của mình (không chia sẻ cho bất kỳ ai).
    - Session/Cookie sau khi đăng nhập thành công sẽ được lưu trữ cục bộ tại thư mục `./threads_profile`.
    - Các lần cào sau này sẽ tự động tái sử dụng profile này mà không cần đăng nhập lại.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    profile_dir = Path(os.getenv("CA_THREADS_USER_DATA_DIR", "./threads_profile")).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(" CÔNG CỤ THIẾT LẬP PHIÊN ĐĂNG NHẬP THREADS (CAMOUFOX)")
    print("=" * 70)
    print(f">> Thư mục lưu Profile: {profile_dir}")
    print(">> Đang khởi động trình duyệt Camoufox (chế độ có giao diện)...")

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        print("\n[LỖI] Chưa cài đặt thư viện `camoufox`.")
        print("Vui lòng chạy lệnh sau trên Terminal để cài đặt:")
        print("    pip install -U 'camoufox[geoip]'")
        print("    camoufox fetch")
        sys.exit(1)

    try:
        with Camoufox(
            headless=False,
            user_data_dir=str(profile_dir),
            # Camoufox 0.5.x bắt buộc persistent_context=True khi truyền
            # user_data_dir (nếu thiếu → TypeError: unexpected keyword argument).
            persistent_context=True,
            geoip=True,
            humanize=True,
        ) as browser:
            page = browser.new_page() if hasattr(browser, "new_page") else browser
            print("\n>> Đang mở trang đăng nhập Threads (https://www.threads.net/login)...")
            page.goto("https://www.threads.net/login")

            print("\n" + "*" * 65)
            print(" HƯỚNG DẪN:")
            print(" 1. Trên cửa sổ trình duyệt vừa mở ra, bạn tự nhập tài khoản & mật khẩu.")
            print(" 2. Nhập mã xác minh 2FA (nếu có) và tích chọn 'Nhớ trình duyệt này'.")
            print(" 3. Khi đã vào được trang chủ Threads, bạn chỉ cần ĐÓNG CỬA SỔ TRÌNH DUYỆT.")
            print("*" * 65 + "\n")

            # Chờ người dùng đăng nhập và đóng trình duyệt
            try:
                page.wait_for_event("close", timeout=600_000)  # Chờ tối đa 10 phút
            except Exception:
                pass

        print("\n[THÀNH CÔNG] Đã lưu thông tin phiên làm việc vào:", profile_dir)
        print("Bây giờ bạn có thể chạy lệnh test cào dữ liệu:")
        print("    python scripts/threads_test_trending.py\n")

    except Exception as e:
        print(f"\n[LỖI] Quá trình khởi động trình duyệt thất bại: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
