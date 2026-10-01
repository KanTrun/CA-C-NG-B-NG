"""Dựng prompt sinh ảnh menu — TẤT ĐỊNH, không gọi LLM.

Vì sao bỏ bước LLM: luồng cũ chạy vision-LLM trên ảnh ly nước để "đoán" ra prompt
— tốn 3–10 giây và một lượt gọi mạng cho MỖI ảnh, và khi provider LLM lỗi thì cả
tính năng đứng (fail-closed nhưng người dùng không có ảnh). Prompt ở đây được lắp
từ dữ liệu có cấu trúc (tên món + phong cách) nên bấm là ra ngay, và cùng món +
cùng phong cách luôn cho cùng prompt — ảnh trong menu đồng bộ mà không cần AI.

Tên món tiếng Việt được dịch sang tiếng Anh bằng từ điển cụm (khớp cụm DÀI trước)
vì model sinh ảnh hiểu tiếng Anh tốt hơn hẳn. Từ không có trong từ điển được giữ
nguyên thay vì bỏ đi — mất thông tin còn tệ hơn là để model tự diễn giải.
"""

from __future__ import annotations

import re
import unicodedata

from ca_agents.menu_style import LENSES, LIGHTINGS, PALETTES, SCENES, MenuStyle

# Từ điển cụm Việt → Anh. Khoá PHẢI là chữ thường, không dấu câu.
# Khớp theo cụm dài nhất trước, nên "trà đào cam sả" thắng "trà đào".
_GLOSSARY: dict[str, str] = {
    # ── Trà ──
    "trà đào cam sả": "peach orange lemongrass tea",
    "trà hoa đậu biếc": "butterfly pea flower tea",
    "trà hoa cúc": "chamomile tea",
    "trà mãng cầu": "soursop tea",
    "trà đào": "peach tea",
    "trà vải": "lychee tea",
    "trà chanh": "lemon tea",
    "trà tắc": "kumquat tea",
    "trà xanh": "green tea",
    "trà sen": "lotus tea",
    "trà gừng": "ginger tea",
    "trà bưởi": "pomelo tea",
    "trà dâu": "strawberry tea",
    "trà xoài": "mango tea",
    "trà cam": "orange tea",
    "trà lài": "jasmine tea",
    "trà nhài": "jasmine tea",
    "trà ô long": "oolong tea",
    "trà olong": "oolong tea",
    "hồng trà": "black tea",
    "trà sữa trân châu": "milk tea with tapioca pearls",
    "trà sữa": "milk tea",
    "trà": "tea",
    # ── Cà phê ──
    "cà phê sữa đá": "iced milk coffee",
    "cà phê muối": "salted coffee",
    "cà phê dừa": "coconut coffee",
    "cà phê trứng": "egg coffee",
    "cà phê kem": "cream coffee",
    "cà phê đen": "black coffee",
    "cà phê sữa": "milk coffee",
    "cà phê đá": "iced coffee",
    "cà phê nóng": "hot coffee",
    "bạc xỉu": "Vietnamese milk coffee",
    "cafe": "coffee",
    "cà phê": "coffee",
    "ca cao": "cocoa",
    "socola": "chocolate",
    "sô cô la": "chocolate",
    "matcha": "matcha",
    "espresso": "espresso",
    "cappuccino": "cappuccino",
    "latte": "latte",
    "americano": "americano",
    "mocha": "mocha",
    "macchiato": "macchiato",
    # ── Nước ép / sinh tố ──
    "nước ép dưa hấu": "watermelon juice",
    "nước ép cà rốt": "carrot juice",
    "nước ép thơm": "pineapple juice",
    "nước ép dứa": "pineapple juice",
    "nước ép táo": "apple juice",
    "nước ép cam": "orange juice",
    "nước ép": "juice",
    "sinh tố việt quất": "blueberry smoothie",
    "sinh tố chuối": "banana smoothie",
    "sinh tố dâu": "strawberry smoothie",
    "sinh tố xoài": "mango smoothie",
    "sinh tố bơ": "avocado smoothie",
    "sinh tố": "smoothie",
    "nước cam": "orange juice",
    "nước chanh": "lemonade",
    "nước dừa": "coconut water",
    "nước mía": "sugarcane juice",
    "nước suối": "mineral water",
    "đá xay": "blended iced drink",
    "sữa chua": "yogurt",
    # ── Trái cây / nguyên liệu ──
    "dưa hấu": "watermelon",
    "chanh dây": "passion fruit",
    "việt quất": "blueberry",
    "mãng cầu": "soursop",
    "cà rốt": "carrot",
    "trân châu": "tapioca pearls",
    "hạt chia": "chia seeds",
    "hạnh nhân": "almonds",
    "óc chó": "walnuts",
    "yến mạch": "oats",
    "mật ong": "honey",
    "phô mai": "cheese",
    "kem phô mai": "cheese foam",
    "khoai môn": "taro",
    "khoai lang": "sweet potato",
    "bạc hà": "mint",
    "cam": "orange",
    "chanh": "lemon",
    "đào": "peach",
    "xoài": "mango",
    "dâu": "strawberry",
    "nho": "grape",
    "táo": "apple",
    "chuối": "banana",
    "bơ": "avocado",
    "dừa": "coconut",
    "ổi": "guava",
    "bưởi": "pomelo",
    "vải": "lychee",
    "tắc": "kumquat",
    "sả": "lemongrass",
    "gừng": "ginger",
    "quế": "cinnamon",
    "sen": "lotus",
    "sữa": "milk",
    "kem": "ice cream",
    "thạch": "jelly",
    "pudding": "pudding",
    # ── Món ăn kèm (menu quán có thể có) ──
    "bánh mì": "Vietnamese baguette sandwich",
    "bánh ngọt": "pastry cake",
    "bánh flan": "creme caramel flan",
    "bánh": "cake",
    "croissant": "croissant",
    "cookie": "cookie",
    # ── Trạng thái / cách phục vụ ──
    "đá": "iced",
    "nóng": "hot",
    "lạnh": "cold",
    "ít đá": "lightly iced",
    "không đá": "no ice",
    "nhiều đá": "extra iced",
    "đặc biệt": "signature",
    "truyền thống": "traditional",
    "thủ công": "handcrafted",
    "tươi": "fresh",
    # ── Bao bì đựng chất lỏng ──
    # Nhóm này cần cho luồng ảnh quảng cáo từ ẢNH THẬT: prompt phải gọi đúng
    # loại bao bì (chai/lọ/hộp/túi) để model không vẽ lại sản phẩm thành ly.
    # Xếp cụm dài TRƯỚC cụm ngắn trong cùng nhóm để "chai thủy tinh" thắng "chai".
    "chai thủy tinh": "glass bottle",
    "chai nhựa": "plastic bottle",
    "hộp giấy": "carton box",
    "túi zip": "zipper pouch",
    "lon nước": "drink can",
    "chai": "bottle",
    "lọ": "jar",
    "hũ": "jar",
    "bình": "jug",
    "ca": "pitcher",
    "hộp": "box",
    "túi": "pouch",
    "gói": "pack",
    "ly": "glass",
    "cốc": "glass",
    "tách": "cup",
    "lon": "can",
    "thùng": "crate",
}

# Từ mô tả đặc tính đặt lên ĐẦU cụm tiếng Anh cho tự nhiên ("iced milk coffee"
# thay vì "milk coffee iced").
_FRONT_WORDS = frozenset({"iced", "hot", "cold", "fresh", "extra iced", "lightly iced"})

# Đuôi chất lượng cho ảnh HOÀN CHỈNH (có đồ uống trong khung). Cố ý khác
# ``menu_style._QUALITY_SUFFIX``: bản đó dành cho ảnh NỀN trống nên có điều khoản
# "no drink, no beverage" — dùng nhầm vào đây sẽ xoá luôn món khỏi ảnh.
_QUALITY = (
    "professional commercial food photography, appetizing and fresh, sharp focus, "
    "clean uncluttered composition, high dynamic range, subtle film grain, "
    "no text, no watermark, no logo, no people, no hands"
)

# Gợi ý bố cục theo tỷ lệ khung — giúp model không cắt cụt ly ở khung dọc.
_COMPOSITION: dict[str, str] = {
    "1:1": "centered square composition",
    "4:5": "vertical composition with generous negative space above",
    "9:16": "tall vertical composition suitable for stories and reels",
    "16:9": "wide horizontal composition with room beside the subject",
}


def _normalize(text: str) -> str:
    """Chuẩn hoá tên món: thường hoá, bỏ dấu câu, gộp khoảng trắng.

    ``\\w`` trong Python 3 khớp cả chữ có dấu tiếng Việt nên "trà đào" được giữ
    nguyên thay vì bị cắt thành "tr  o".
    """
    lowered = text.strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def known_phrase(phrase: str) -> str | None:
    """Tra một cụm ĐÃ chuẩn hoá trong từ điển; None khi không có.

    Dùng cho nơi cần tra từng cụm một (dịch ý kiến người dùng) thay vì chạy cả
    câu qua :func:`translate_mon_ten` — chạy cả câu sẽ để cụm từ vắt qua ranh
    giới hai ý khớp nhầm.
    """
    return _GLOSSARY.get(phrase.strip().lower())


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt (NFD rồi lọc dấu kết hợp; "đ" xử lý riêng)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").replace("đ", "d")


# Bảng tra KHÔNG DẤU suy ra từ :data:`_GLOSSARY` — người dùng gõ nhanh hay bỏ
# dấu ("tra dao", "sua da"). Suy ra tự động thay vì viết tay để mỗi mục mới
# thêm vào từ điển có dấu tự động có bản không dấu, không phải nhớ thêm thủ công.
_GLOSSARY_KHONG_DAU: dict[str, str] = {}
for _cum, _dich in _GLOSSARY.items():
    _GLOSSARY_KHONG_DAU.setdefault(_bo_dau(_cum), _dich)


def known_phrase_khong_dau(phrase: str) -> str | None:
    """Tra từ điển ở dạng KHÔNG DẤU — lớp hai khi :func:`known_phrase` trượt.

    Chỉ dùng sau khi đã thử bản có dấu: bản có dấu là dạng người dùng gõ đúng,
    còn bản này là lưới bắt các trường hợp bỏ dấu.
    """
    return _GLOSSARY_KHONG_DAU.get(_bo_dau(phrase.strip()))


def translate_mon_ten(mon_ten: str) -> str:
    """Dịch tên món sang cụm tiếng Anh; từ lạ được giữ nguyên.

    Khớp cụm DÀI trước để "trà đào cam sả" ra một cụm đúng thay vì bị cắt thành
    "peach tea orange lemongrass".
    """
    tokens = _normalize(mon_ten).split()
    if not tokens:
        return ""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        matched = False
        # Thử cụm 4 → 1 từ; cụm dài nhất thắng. Thử bản CÓ DẤU trước rồi mới tới
        # bản không dấu — người gõ đúng dấu phải được ưu tiên.
        for span in range(min(4, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + span])
            dich = known_phrase(phrase) or known_phrase_khong_dau(phrase)
            if dich is not None:
                out.append(dich)
                i += span
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    # Đưa từ chỉ trạng thái lên đầu ("iced", "hot"…).
    front = [w for w in out if w in _FRONT_WORDS]
    rest = [w for w in out if w not in _FRONT_WORDS]
    return " ".join([*front, *rest]).strip()


def _fallback_style() -> MenuStyle:
    """Phong cách dùng khi quán chưa chọn gì — preset đầu tiên của bộ mặc định."""
    from ca_agents.menu_style import default_styles

    styles = default_styles()
    return styles[0]


def build_menu_prompt(
    mon_ten: str,
    *,
    mo_ta: str = "",
    style: MenuStyle | None = None,
    aspect_ratio: str = "1:1",
) -> str:
    """Dựng prompt sinh ảnh tiếng Anh từ tên món + phong cách (không gọi LLM).

    Args:
        mon_ten: Tên món như hiển thị trên menu (tiếng Việt vẫn được).
        mo_ta: Mô tả thêm của người dùng (tuỳ chọn) — nối vào đầu prompt.
        style: Phong cách thiết kế; None → dùng preset mặc định.
        aspect_ratio: Tỷ lệ khung, dùng để thêm gợi ý bố cục.

    Returns:
        Prompt tiếng Anh hoàn chỉnh. Chuỗi rỗng khi ``mon_ten`` trống — endpoint
        phải từ chối trường hợp đó thay vì sinh ảnh từ prompt rỗng.
    """
    subject = translate_mon_ten(mon_ten)
    if not subject:
        return ""
    chosen = style if style is not None else _fallback_style()
    parts = [f"professional food photography of a freshly made {subject}"]
    # Mô tả của người dùng cũng đi qua từ điển: họ gõ tiếng Việt ("thêm đá và
    # hạt cà phê") mà prompt phải là tiếng Anh để model hiểu đúng. Từ không có
    # trong từ điển vẫn được giữ nguyên — model đọc được tốt hơn là bỏ mất ý.
    extra = translate_mon_ten(mo_ta) if mo_ta.strip() else ""
    if extra:
        parts.append(extra[:300])
    parts.append(SCENES[chosen.scene])
    parts.append(LIGHTINGS[chosen.lighting])
    parts.append(f"color palette of {PALETTES[chosen.palette]}")
    parts.append(LENSES[chosen.lens])
    composition = _COMPOSITION.get(aspect_ratio)
    if composition:
        parts.append(composition)
    parts.append(_QUALITY)
    return ", ".join(parts)
