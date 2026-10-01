"""Phong cách thiết kế (brand kit) cho ảnh quảng cáo menu — lưu & tái dùng.

Vấn đề: mỗi lần tạo ảnh, prompt nền được viết lại từ đầu → 10 ly nước của cùng
một quán ra 10 phong cách khác nhau, nhìn như 10 quán khác nhau.

Giải pháp: một *phong cách* là dữ liệu có cấu trúc (không phải prompt tự do) gồm
scene/lighting/palette/lens/mood, kèm một ``slug`` ngắn để hiển thị trong UI.
Phong cách được dịch thành prompt nền **tất định** — cùng phong cách + cùng món
→ cùng prompt, nên ảnh trong menu đồng bộ mà không cần gọi LLM.

Fail-closed: phong cách hỏng/thiếu trường → ``None``; không tự bịa giá trị.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Slug dùng làm khoá lưu: chữ thường, số, gạch dưới.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

# Bảng màu hợp lệ — giới hạn để UI và prompt không lệch nhau.
PALETTES: dict[str, str] = {
    "warm_wood": "warm honey and dark walnut browns, soft cream highlights",
    "sage_green": "muted sage green and natural linen, soft daylight whites",
    "terracotta": "terracotta clay and burnt sienna, sun-baked warm neutrals",
    "monochrome_ink": "near-black charcoal and warm off-white, minimal high contrast",
    "pastel_dawn": "soft blush pink and pale peach, airy pastel highlights",
    "deep_emerald": "deep emerald green and brushed brass, moody jewel tones",
}

# Bối cảnh nền hợp lệ — mô tả SCENE, tuyệt đối không nhắc tới đồ uống.
SCENES: dict[str, str] = {
    "cafe_wood": "a rustic wooden cafe table surface in the foreground",
    "marble_bar": "a polished marble countertop with subtle grey veining",
    "linen_cloth": "a natural wrinkled linen tablecloth surface",
    "concrete_loft": "a smooth polished concrete surface in a bright loft",
    "outdoor_garden": "a weathered garden table with soft green foliage behind",
    "studio_paper": "a seamless studio paper backdrop curving into the surface",
}

# Ánh sáng hợp lệ.
LIGHTINGS: dict[str, str] = {
    "golden_hour": "warm golden hour side light with soft long shadows",
    "window_soft": "soft diffused daylight from a large window",
    "moody_low_key": "moody low-key lighting with a single warm rim light",
    "bright_high_key": "bright even high-key studio lighting with minimal shadow",
    "neon_evening": "cool neon evening light with warm cove accents",
}

# Ống kính / bố cục hợp lệ.
LENSES: dict[str, str] = {
    "shallow_85mm": "85mm lens, very shallow depth of field, creamy background bokeh",
    "tight_50mm": "50mm lens, natural perspective, moderate depth of field",
    "wide_35mm": "35mm lens, wider scene context, gentle foreground depth",
    "macro_detail": "macro-style close framing, razor-sharp focal plane, heavy bokeh",
}

# Hậu tố chất lượng dùng chung — kỹ thuật nhiếp ảnh, không đổi phong cách.
# Cố ý KHÔNG dùng chữ "beverage"/"drink" ở đây: từ chỉ đồ uống trong prompt là
# thứ khiến model vẽ thêm một ly nữa vào nền.
_QUALITY_SUFFIX = (
    "professional commercial food photography, sharp focus, clean composition, "
    "high dynamic range, subtle film grain, no text, no watermark"
)

# Từ khoá cấm trong ảnh nền (model hay vẽ thêm ly khi prompt nhắc "beverage").
_NEGATION = (
    "absolutely no drink, no beverage, no glass, no cup, no bottle, no mug, "
    "no straw, no spoon, no topping, no food, no hands, no people, no text, "
    "no logo, empty surface, nothing on the table, background scene only"
)

# Phong cách mặc định — dùng khi quán chưa tạo phong cách nào.
DEFAULT_STYLE_SLUG = "nhip_quan_classic"

# Bộ preset dựng sẵn để UI đổ vào dropdown ngay lần đầu.
PRESET_STYLES: tuple[dict[str, str], ...] = (
    {
        "slug": DEFAULT_STYLE_SLUG,
        "ten": "Nhịp Quán cổ điển",
        "mo_ta": "Gỗ tối + nắng vàng, ấm và gần gũi — mặc định của quán.",
        "scene": "cafe_wood",
        "lighting": "golden_hour",
        "palette": "warm_wood",
        "lens": "shallow_85mm",
    },
    {
        "slug": "toi_gian_sang",
        "ten": "Tối giản sáng",
        "mo_ta": "Nền sáng sạch, ít chi tiết — hợp ảnh menu in và app giao hàng.",
        "scene": "studio_paper",
        "lighting": "bright_high_key",
        "palette": "monochrome_ink",
        "lens": "tight_50mm",
    },
    {
        "slug": "moody_quan_dem",
        "ten": "Quán đêm moody",
        "mo_ta": "Tối, tương phản mạnh, ánh viền ấm — hợp teaser buổi tối.",
        "scene": "concrete_loft",
        "lighting": "moody_low_key",
        "palette": "deep_emerald",
        "lens": "shallow_85mm",
    },
    {
        "slug": "vuon_xanh",
        "ten": "Vườn xanh",
        "mo_ta": "Ngoài trời, lá xanh, nắng dịu — hợp trà trái cây và nước ép.",
        "scene": "outdoor_garden",
        "lighting": "window_soft",
        "palette": "sage_green",
        "lens": "wide_35mm",
    },
    {
        "slug": "dep_sang_trong",
        "ten": "Đẹp sang trọng",
        "mo_ta": "Đá marble + đồng thau — hợp món signature giá cao.",
        "scene": "marble_bar",
        "lighting": "window_soft",
        "palette": "terracotta",
        "lens": "tight_50mm",
    },
)


@dataclass(frozen=True)
class MenuStyle:
    """Một phong cách thiết kế có cấu trúc — mọi trường phải thuộc bảng hợp lệ."""

    slug: str
    ten: str
    mo_ta: str
    scene: str
    lighting: str
    palette: str
    lens: str

    def to_prompt(self, *, extra: str = "") -> str:
        """Dịch phong cách thành prompt nền tiếng Anh — tất định, không LLM.

        ``extra``: yêu cầu riêng của người dùng đã được viết lại thành mô tả nền
        (đã qua LLM hoặc do người dùng nhập) — nối vào trước phần kỹ thuật.

        Bản này dành cho ảnh NỀN TRỐNG (không có sản phẩm trong khung) nên kèm
        điều khoản "no drink…" — KHÔNG dùng cho prompt quảng cáo giữ sản phẩm
        (xem :meth:`to_prompt_ad`).
        """
        parts = [
            f"empty cafe background scene: {SCENES[self.scene]}",
            LIGHTINGS[self.lighting],
            f"color palette of {PALETTES[self.palette]}",
            LENSES[self.lens],
        ]
        if extra.strip():
            parts.insert(1, extra.strip()[:600])
        parts.append(_QUALITY_SUFFIX)
        return ", ".join(parts) + ", " + _NEGATION

    def to_prompt_ad(self, *, extra: str = "") -> str:
        """Mô tả phong cách cho prompt ẢNH QUẢNG CÁO giữ sản phẩm.

        Khác :meth:`to_prompt`: KHÔNG có tiền tố "empty background scene" và
        KHÔNG có điều khoản "no drink, no beverage…" — hai thứ đó bảo model
        xoá sản phẩm khỏi ảnh (đã gây lỗi gửi ảnh matcha latte mà ra ảnh bánh).
        Chỉ tả bối cảnh/ánh sáng/palette/ống kính quanh sản phẩm.
        """
        parts = [
            f"cafe setting with {SCENES[self.scene]} as the backdrop",
            LIGHTINGS[self.lighting],
            f"color palette of {PALETTES[self.palette]}",
            LENSES[self.lens],
        ]
        if extra.strip():
            parts.insert(1, extra.strip()[:600])
        parts.append(_QUALITY_SUFFIX)
        return ", ".join(parts)

    def to_dict(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "ten": self.ten,
            "mo_ta": self.mo_ta,
            "scene": self.scene,
            "lighting": self.lighting,
            "palette": self.palette,
            "lens": self.lens,
        }


def style_options() -> dict[str, dict[str, str]]:
    """Bảng giá trị hợp lệ cho UI (scene/lighting/palette/lens) — 1 nguồn sự thật."""
    return {
        "scene": dict(SCENES),
        "lighting": dict(LIGHTINGS),
        "palette": dict(PALETTES),
        "lens": dict(LENSES),
    }


def normalize_slug(raw: str) -> str | None:
    """Chuẩn hoá tên phong cách thành slug hợp lệ; None nếu không dùng được.

    Bỏ dấu tiếng Việt trước khi lọc: "Moody Quán Đêm" → ``moody_quan_dem``. Không
    bỏ dấu thì tên có dấu bị lọc thành chuỗi rỗng và người dùng nhận lỗi 422 khó
    hiểu dù họ nhập tên hợp lệ.
    """
    # NFD tách dấu khỏi nguyên âm; "đ" không tách được nên xử lý riêng.
    decomposed = unicodedata.normalize("NFD", raw.strip().lower())
    ascii_ish = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    ascii_ish = ascii_ish.replace("đ", "d")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_ish).strip("_")
    slug = re.sub(r"_{2,}", "_", slug)
    # Từ chối khi QUÁ DÀI thay vì cắt ngắn: cắt ngắn có thể sinh slug trùng nhau
    # (hai tên khác nhau ra cùng 48 ký tự đầu) và âm thầm ghi đè phong cách.
    if len(slug) > 48:
        return None
    if not slug or not _SLUG.fullmatch(slug):
        return None
    return slug


def parse_style(data: Any) -> MenuStyle | None:
    """Dựng ``MenuStyle`` từ dict đã lưu/hiển thị. None nếu thiếu/sai trường.

    Fail-closed: giá trị nằm ngoài bảng hợp lệ bị từ chối thay vì âm thầm
    thay bằng mặc định — nếu không, ảnh ra sẽ khác phong cách người dùng chọn.
    """
    if not isinstance(data, dict):
        return None
    slug = normalize_slug(str(data.get("slug") or ""))
    if not slug:
        return None
    scene = str(data.get("scene") or "")
    lighting = str(data.get("lighting") or "")
    palette = str(data.get("palette") or "")
    lens = str(data.get("lens") or "")
    if scene not in SCENES or lighting not in LIGHTINGS:
        return None
    if palette not in PALETTES or lens not in LENSES:
        return None
    return MenuStyle(
        slug=slug,
        ten=str(data.get("ten") or slug).strip()[:60] or slug,
        mo_ta=str(data.get("mo_ta") or "").strip()[:200],
        scene=scene,
        lighting=lighting,
        palette=palette,
        lens=lens,
    )


def default_styles() -> list[MenuStyle]:
    """Preset dựng sẵn — dùng khi store chưa có phong cách nào."""
    out: list[MenuStyle] = []
    for item in PRESET_STYLES:
        parsed = parse_style(item)
        if parsed is not None:
            out.append(parsed)
    return out


def find_style(styles: list[MenuStyle], slug: str) -> MenuStyle | None:
    """Tìm phong cách theo slug (đã chuẩn hoá); None nếu không có."""
    target = normalize_slug(slug)
    if not target:
        return None
    for style in styles:
        if style.slug == target:
            return style
    return None
