# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Gate UI web — `useToasts()` phải đi kèm `<Toasts>`.

Lỗi thật đã xảy ra (260920, trang `/page-quan/dat-ban`): hook `useToasts()` được
gọi và `push()` được dùng ở 5 chỗ, nhưng component `<Toasts>` không hề được
render. Hệ quả: mọi thông báo thành công/lỗi im lặng hoàn toàn — nhân viên bấm
"Vào bàn"/"Hủy" xong không biết thao tác có ăn hay không. Cùng lỗi có ở
`/page-quan`, `/inbox`, `/page-quan/fb-inbox`.

Không có TypeScript nào bắt được lỗi này: `push` là hàm hợp lệ, chỉ là kết quả
của nó không được vẽ ra. Vì vậy phải kiểm bằng phân tích tĩnh trên mã nguồn.

Gate này quét mọi file `.tsx` trong `apps/web/src`:
- Có gọi `useToasts()`  ⇒ phải có `<Toasts ... />`.
- Có `<Toasts>` ⇒ phải có `useToasts()` (tránh render với biến không tồn tại).

Ngoại lệ có lý do nằm trong `MIEN_TRU`.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parents[3] / "web" / "src"

# File cố ý không theo cặp gọi-render, kèm lý do.
MIEN_TRU: dict[str, str] = {
    # `kit.tsx` là nơi ĐỊNH NGHĨA hook và component, không phải nơi dùng.
    "ui/kit.tsx": "định nghĩa useToasts/Toasts",
}

_RE_GOI_HOOK = re.compile(r"\buseToasts\s*\(")
_RE_RENDER = re.compile(r"<Toasts\b")


def _cac_file_tsx() -> list[Path]:
    return sorted(WEB_SRC.rglob("*.tsx"))


def test_web_src_ton_tai() -> None:
    """Chốt an toàn: nếu đường dẫn sai thì gate sẽ quét 0 file và báo sạch GIẢ."""
    assert WEB_SRC.is_dir(), f"không thấy thư mục mã nguồn web: {WEB_SRC}"
    assert _cac_file_tsx(), "không tìm thấy file .tsx nào — gate sẽ báo sạch giả"


def test_use_toasts_luon_di_kem_render_toasts() -> None:
    """Gọi `useToasts()` mà không render `<Toasts>` = thông báo bị nuốt."""
    vi_pham: list[str] = []
    for path in _cac_file_tsx():
        rel = path.relative_to(WEB_SRC).as_posix()
        if rel in MIEN_TRU:
            continue
        text = path.read_text(encoding="utf-8")
        co_goi = bool(_RE_GOI_HOOK.search(text))
        co_render = bool(_RE_RENDER.search(text))
        if co_goi and not co_render:
            vi_pham.append(f"{rel}: gọi useToasts() nhưng thiếu <Toasts ... />")
        if co_render and not co_goi:
            vi_pham.append(f"{rel}: render <Toasts> nhưng không gọi useToasts()")
    assert not vi_pham, "Thông báo bị nuốt (thêm <Toasts> hoặc khai báo MIEN_TRU):\n" + "\n".join(
        vi_pham
    )


# ── Gate 2: trạng thái quầy không được suy từ "hôm nay có ca" ────────────────

_RE_SET_CHECKED_IN_TU_HOM_NAY = re.compile(r"setCheckedIn\s*\(\s*homNay\s*\)")


def test_quay_khong_suy_ra_da_diem_danh_tu_co_ca() -> None:
    """`/quay`: \"hôm nay có ca\" KHÁC \"đã điểm danh\" — không được gộp làm một.

    Lỗi thật đã xảy ra (260928, QA đợt 5): `load()` gặp 403 `chua_diem_danh`
    rồi gọi `setCheckedIn(homNay)` — biến `homNay` chỉ nghĩa là *có ca hôm nay*.
    Hệ quả: UI hiện \"Ca đang mở\", đổi nhãn ca thành \"bạn đang trong ca này\",
    và **bật** nút \"Gửi sang pha chế\" — nhưng mọi lệnh ghi vẫn 403 vì cổng API
    (`_require_dang_ca`) đòi đúng `da_diem_danh`. Nhân viên có ca nhưng chưa
    điểm danh thấy một cái quầy trông như đang mở mà bấm gì cũng hỏng, và
    KHÔNG có cảnh báo nào chỉ đường đi điểm danh.

    TypeScript không bắt được: `homNay` là `boolean` hợp lệ, `checkedIn` cũng
    vậy — chỉ có ý NGHĨA sai. Phải kiểm bằng phân tích tĩnh.
    """
    path = WEB_SRC / "app" / "quay" / "page.tsx"
    assert path.is_file(), f"không thấy trang quầy: {path}"
    text = path.read_text(encoding="utf-8")
    vi_pham = _RE_SET_CHECKED_IN_TU_HOM_NAY.findall(text)
    assert not vi_pham, (
        "app/quay/page.tsx: `setCheckedIn(homNay)` gộp 'có ca' thành 'đã điểm danh' "
        "→ UI báo quầy đã mở trong khi API vẫn 403. Dùng biến riêng cho 'có ca' "
        "(vd `setCoCaHomNay`) và giữ `checkedIn=false` khi gặp 403."
    )


def test_quay_bat_buoc_diem_danh_truoc_khi_gui_don() -> None:
    """Nút gửi đơn phải phụ thuộc `checkedIn`, không phải 'có ca'."""
    path = WEB_SRC / "app" / "quay" / "page.tsx"
    text = path.read_text(encoding="utf-8")
    assert re.search(r"disabled=\{!checkedIn", text), (
        "app/quay/page.tsx: nút 'Gửi sang pha chế' phải `disabled={!checkedIn ...}` "
        "— nếu chỉ dựa vào giỏ hàng thì người chưa điểm danh bấm được rồi ăn 403."
    )


def test_quay_co_loi_di_diem_danh_khi_chua_mo() -> None:
    """Chưa mở quầy ⇒ phải có lối đi điểm danh ngay trên trang."""
    path = WEB_SRC / "app" / "quay" / "page.tsx"
    text = path.read_text(encoding="utf-8")
    assert 'apiSend("/api/v1/diem-danh")' in text, (
        "app/quay/page.tsx: phải có nút gọi `POST /api/v1/diem-danh` để nhân viên "
        "mở quầy ngay tại chỗ, thay vì chỉ báo khóa mà không chỉ đường."
    )
