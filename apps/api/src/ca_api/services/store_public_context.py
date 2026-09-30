"""Public Context Provider for Customer-Facing Bots & Interfaces.

Provides sanitized, public-safe DTOs for Menu, Store Profile, and Active Promotions.
Strictly isolates all internal store data (BOM quantities, raw material cost, user accounts, shifts).
"""

from __future__ import annotations

from typing import Any

from ca_api.persist import _conn, init_db, kv_get, kv_set

# ADR-008: profile mặc định PHẢI rỗng — quán chưa cấu hình thì bot trả lời
# "chưa cập nhật" thay vì bịa địa chỉ/hotline/wifi (đã từng rò rỉ ra khách thật).
# Quản lý/chủ quán nhập thông tin thật tại trang /cau-hinh-quan.
DEFAULT_STORE_PROFILE: dict[str, Any] = {
    "ten_quan": "",
    "dia_chi": "",
    # Tỉnh / thành phố — giữ tương thích dữ liệu cũ; thời tiết ưu tiên lat/lon GPS.
    "tinh": "",
    "thanh_pho": "",
    # Toạ độ quán từ GPS trình duyệt (Open-Meteo forecast không cần geocode).
    "lat": None,
    "lon": None,
    "hotline": "",
    "gio_mo_cua": "",
    "wifi_ssid": "",
    "wifi_pass": "",
    "mo_ta": "",
    "chinh_sach_dat_ban": "",
    # Hướng dẫn riêng của chủ quán cho AI agent (giọng văn, quy tắc trả lời,
    # thông tin đặc biụt...) — tự do, không convert, đi thẳng vào prompt.
    "huong_dan_agent": "",
}

# Các trường profile quán được phép ghi qua API — chặn key lạ.
PROFILE_FIELDS = frozenset(DEFAULT_STORE_PROFILE.keys())

DEFAULT_PROMOTIONS: list[dict[str, Any]] = []


def get_public_menu() -> list[dict[str, Any]]:
    """Retrieve active menu items with public details only (ten, gia). BOM and costs are hidden.

    Lọc món fixture (`fx_*`) — dữ liệu mô phỏng KP Const không được phục vụ
    ra khách (trùng món + mâu thuẫn giá với menu thật).
    """
    init_db()
    with _conn() as cx:
        rows = cx.execute(
            "SELECT id, ten, gia FROM menu_mon WHERE an = 0 AND id NOT LIKE 'fx\\_%' ESCAPE '\\'"
            " ORDER BY ten ASC"
        ).fetchall()
    return [
        {"id": str(r[0]), "ten": str(r[1]), "gia": int(r[2]), "gia_formatted": f"{int(r[2]):,}đ"}
        for r in rows
    ]


def get_store_profile() -> dict[str, Any]:
    """Retrieve public store contact, operating hours, and location."""
    res = kv_get("store_profile", DEFAULT_STORE_PROFILE)
    if isinstance(res, dict):
        merged = DEFAULT_STORE_PROFILE.copy()
        merged.update(res)
        return merged
    return DEFAULT_STORE_PROFILE.copy()


def set_store_profile(profile: dict[str, Any]) -> None:
    """Update store profile configuration — chỉ nhận các trường hợp lệ."""
    current = get_store_profile()
    current.update({k: v for k, v in profile.items() if k in PROFILE_FIELDS})
    kv_set("store_profile", current)


def get_active_promotions() -> list[dict[str, Any]]:
    """Retrieve ongoing promotional campaigns — rỗng khi quán chưa cấu hình (ADR-008)."""
    res = kv_get("store_promotions", DEFAULT_PROMOTIONS)
    if isinstance(res, list):
        return [p for p in res if isinstance(p, dict)]
    return []


def set_active_promotions(promotions: list[dict[str, Any]]) -> None:
    """Update active promotional campaigns."""
    kv_set("store_promotions", promotions)


def format_public_context_for_prompt() -> str:
    """Assemble formatted summary string for prompt context injection."""
    profile = get_store_profile()
    menu = get_public_menu()
    promos = get_active_promotions()

    menu_lines = [f"- {item['ten']}: {item['gia_formatted']}" for item in menu]
    promo_lines = [
        f"- {p['tieu_de']}: {p['chi_tiet']} (Hiệu lực: {p.get('hieu_luc', 'Đang áp dụng')})"
        for p in promos
    ]

    def _f(label: str, value: Any) -> str:
        """Trường rỗng → không dựng dòng giả; bot tự nói 'chưa cập nhật'."""
        s = str(value or "").strip()
        return f"{label}: {s}" if s else f"{label}: (chưa cập nhật)"

    huong_dan = str(profile.get("huong_dan_agent") or "").strip()
    huong_dan_block = (
        f"\n\n=== HƯỚNG DẪN RIÊNG CỦA CHỦ QUÁN CHO BẠN (BẮT BUỘC TUÂN THỦ) ===\n{huong_dan}"
        if huong_dan
        else ""
    )

    return f"""=== THÔNG TIN QUÁN (CÔNG KHAI) ===
{_f("Tên quán", profile.get("ten_quan"))}
{_f("Địa chỉ", profile.get("dia_chi"))}
{_f("Hotline", profile.get("hotline"))}
{_f("Giờ mở cửa", profile.get("gio_mo_cua"))}
{_f("Wifi", profile.get("wifi_ssid"))}
{_f("Chính sách đặt bàn", profile.get("chinh_sach_dat_ban"))}

=== MENU ĐỒ UỐNG HIỆN HÀNH ===
{chr(10).join(menu_lines) if menu_lines else "Đang cập nhật"}

=== CHƯƠNG TRÌNH KHUYẾN MÃI ===
{chr(10).join(promo_lines) if promo_lines else "Hiện chưa có khuyến mãi mới"}{huong_dan_block}
"""
