"""Test lọc tài khoản BOT khỏi danh sách người dùng.

Bug QA đợt 5 (2026-09-27): trang Người dùng `/nguoi` hiện "20 TỔNG TÀI KHOẢN"
và biểu đồ phân bố vai trò có 4 nhóm, dù quán chỉ có 19 người thật.

Nguyên nhân gốc: `persist.list_users()` trả MỌI dòng trong bảng `users`, kể cả
tài khoản bot `ai_scheduler` (vai `ai_assistant`). Bot này được tạo tự động ở
`chat_get_or_create_scheduler_direct` để thoả khoá ngoại
`chat_participants.nv_id → users.nv_id` (migration 0008) — nó KHÔNG phải nhân sự.

Vì sao lọc ở tầng dữ liệu chứ không ở giao diện: `list_users()` được dùng ở 7
nơi (`/nguoi`, `channels` gợi ý người nhận, `AG-MEETING`, provider Copilot,
phép đếm `so_nv`, kiểm tra nhân viên thuộc cửa hàng) — lọc ở UI thì mỗi bề mặt
phải tự nhớ lọc, và bề mặt nào quên sẽ lộ bot.
"""

from __future__ import annotations

from typing import Any

from ca_api import persist


def _tao_bot(store_id: str = "quan_01") -> None:
    """Tạo tài khoản bot đúng như `chat_get_or_create_scheduler_direct` làm."""
    persist.init_db()
    with persist._conn() as cx:
        cx.execute(
            """
            INSERT INTO users(username, password_sha, role, nv_id, display_name, store_id, status)
            VALUES ('ai_scheduler', 'bot_internal', 'ai_assistant', 'ai_scheduler', 'Agent Xếp Lịch', ?, 'active')
            ON CONFLICT(username) DO NOTHING
            """,
            (store_id,),
        )


def test_bot_khong_lot_vao_danh_sach_nguoi() -> None:
    """`list_users()` mặc định KHÔNG trả tài khoản vai `ai_assistant`."""
    _tao_bot()
    ds = persist.list_users()
    vai = {u["role"] for u in ds}
    assert "ai_assistant" not in vai, (
        f"bot `ai_assistant` lọt vào danh sách người: {[u['username'] for u in ds if u['role'] == 'ai_assistant']}"
    )
    assert not any(u["username"] == "ai_scheduler" for u in ds), (
        "`ai_scheduler` không được xuất hiện trong danh sách người"
    )


def test_include_bots_tra_duoc_bot() -> None:
    """Cờ `include_bots=True` giữ đường lui cho nơi thật sự cần bot."""
    _tao_bot()
    ds = persist.list_users(include_bots=True)
    assert any(u["username"] == "ai_scheduler" for u in ds), (
        "include_bots=True phải trả cả tài khoản bot"
    )


def test_loc_theo_store_cung_ap_dung() -> None:
    """Nhánh lọc theo `store_id` phải lọc bot y như nhánh không lọc."""
    _tao_bot("quan_01")
    ds = persist.list_users(store_id="quan_01")
    assert not any(u["role"] == "ai_assistant" for u in ds), (
        "nhánh store_id bỏ sót bộ lọc bot"
    )


def test_nguoi_khong_bi_tinh_vao_so_nhan_vien() -> None:
    """Phép đếm `so_nv` (role == 'nhan_vien') không được thấy bot.

    Bot có vai `ai_assistant` nên tự nó không khớp `nhan_vien`; test này khoá
    hợp đồng rằng bộ lọc không vô tình đổi vai của ai khác.
    """
    _tao_bot()
    so_nv = sum(1 for u in persist.list_users() if u.get("role") == "nhan_vien")
    so_nv_co_bot = sum(
        1 for u in persist.list_users(include_bots=True) if u.get("role") == "nhan_vien"
    )
    assert so_nv == so_nv_co_bot, "bộ lọc bot không được đổi số nhân viên thật"


def test_khong_xoa_du_lieu_bot_trong_db() -> None:
    """Lọc ở TẦNG ĐỌC — bot phải còn nguyên trong DB (khoá ngoại chat cần nó)."""
    _tao_bot()
    persist.list_users()  # gọi hàm lọc
    with persist._conn() as cx:
        row = cx.execute(
            "SELECT username, role FROM users WHERE username='ai_scheduler'"
        ).fetchone()
    assert row is not None, "bộ lọc không được XOÁ bot — chat_participants cần khoá ngoại này"
    assert str(row[1]) == "ai_assistant"


def test_hang_so_vai_bot_khop_voi_nhan_vien_module() -> None:
    """Hai chốt lọc phải dùng cùng một định nghĩa vai bot.

    `persist.VAI_BOT` (danh sách người) và `nhan_vien.VAI_KHONG_XEP_LICH`
    (pool xếp lịch) là hai chốt độc lập; lệch nhau thì bot lọt qua một trong hai.
    """
    from ca_api.nhan_vien import VAI_KHONG_XEP_LICH

    assert persist.VAI_BOT == set(VAI_KHONG_XEP_LICH), (
        f"VAI_BOT={persist.VAI_BOT} lệch VAI_KHONG_XEP_LICH={set(VAI_KHONG_XEP_LICH)}"
    )


def test_list_users_tra_dung_khoa_du_lieu() -> None:
    """Hợp đồng dữ liệu của `list_users` không đổi sau khi thêm bộ lọc."""
    _tao_bot()
    ds = persist.list_users()
    if not ds:
        return
    u: dict[str, Any] = ds[0]
    assert set(u) == {"username", "role", "nv_id", "display_name", "email"}, (
        f"khoá trả về đổi: {sorted(u)}"
    )
