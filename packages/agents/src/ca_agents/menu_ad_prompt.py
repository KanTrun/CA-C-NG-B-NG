"""Prompt ảnh quảng cáo từ ẢNH THẬT — lắp theo quy trình 4 bước, tất định.

Khác gì :mod:`ca_agents.menu_prompt`
------------------------------------
``menu_prompt`` mô tả MÓN bằng lời ("trà đào" → "peach tea") nên model **vẽ lại**
sản phẩm từ đầu — hợp cho chế độ "AI vẽ mới", nhưng mỗi lần ra một dáng ly khác.

Module này làm việc của luồng "úp ảnh thật → AI dàn dựng lại": ảnh gốc là **nguồn
sự thật duy nhất** về sản phẩm, prompt chỉ được mô tả **bối cảnh/ánh sáng/phong
cách**, và luôn kèm ràng buộc bảo toàn sản phẩm (hình dáng, nhãn, chữ, logo, màu
bao bì, nắp). Nhờ vậy ảnh quảng cáo ra đúng là chai/lọ của quán, không phải một
sản phẩm na ná do model tự nghĩ ra.

Bốn bước của quy trình, ánh xạ vào hàm
--------------------------------------
| Bước | Việc | Ở đây |
|---|---|---|
| 1 | Kiểm ảnh có phải sản phẩm đựng chất lỏng | :func:`validate_product_image` |
| 2 | Thu ý kiến người dùng, ghi vào ``user_feedback_history`` | :func:`append_feedback` |
| 3 | Lắp prompt = template gốc + ý kiến đã thu | :func:`build_ad_prompt` |
| 4 | Lặp chỉnh sửa (ý kiến mới đè ý kiến mâu thuẫn cũ) | :func:`build_ad_prompt` (lần gọi sau) |

Bước 2 và 4 dùng **cùng một hàm**: lịch sử ý kiến là một danh sách, mỗi lần người
dùng góp ý thì nối thêm rồi lắp lại prompt. Không có nhánh "chỉnh sửa" riêng —
nếu có, hai nhánh sẽ lệch nhau theo thời gian.

Không gọi LLM để viết prompt
----------------------------
Đúng nguyên tắc đã chốt ở ``plans/260922-cai-tien-tao-anh-quang-cao-menu.md`` §6.1:
prompt lắp từ dữ liệu có cấu trúc nên **bấm là ra ngay**, và cùng đầu vào luôn cho
cùng prompt. Bước 1 CÓ gọi AI thị giác (đó là đọc ảnh, không phải viết prompt) —
xem :func:`validate_product_image`.

Từ điển dịch dùng chung: :func:`ca_agents.menu_prompt.translate_mon_ten` — ý kiến
người dùng gõ tiếng Việt ("đổi nền sang màu xanh") vẫn phải thành tiếng Anh để
model hiểu đúng.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from ca_agents.llm import complete
from ca_agents.menu_prompt import (
    known_phrase,
    known_phrase_khong_dau,
    translate_mon_ten,
)

logger = logging.getLogger(__name__)

# ── TEMPLATE GỐC ────────────────────────────────────────────────────────────
# Áp cho MỌI loại bao bì đựng chất lỏng (chai/lọ/bình/hộp/túi/ly), KHÔNG đặc
# trưng riêng cho một sản phẩm nào. Giữ nguyên cấu trúc ba phần:
#   1. mở bài — ảnh chụp sản phẩm chuyên nghiệp, chính diện, căn giữa;
#   2. ràng buộc bảo toàn sản phẩm — tuyệt đối không đổi hình dáng/nhãn/chữ/logo/màu/nắp;
#   3. chỗ chèn ý kiến người dùng (bối cảnh, ánh sáng, phong cách, tâm trạng).
# Đổi bất kỳ câu nào ở đây là đổi kết quả của MỌI ảnh quảng cáo đã tạo.
_TEMPLATE_OPEN = (
    "A professional product photograph of a {container} placed front-facing and centered "
    "in the frame. Preserve the exact original shape, label design, text, logo, color, "
    "cap/lid, material, and liquid color of the product — do not alter, distort, "
    "redesign, or reinterpret any physical feature of the product itself. The product "
    "must remain fully recognizable and identical to the source image. Only the "
    "environment, background, lighting, and mood may be changed as described below."
)

# Bao bì mặc định khi không suy được loại cụ thể từ tên món. Cố ý trung tính —
# đoán bừa "chai" cho một ly trà sữa sẽ khiến model vẽ sai dạng sản phẩm.
_CONTAINER_MAC_DINH = "liquid product container"

# Mô tả bao bì theo TỪ KHOÁ ĐÃ DỊCH sang tiếng Anh — :func:`loai_bao_bi` tra trên
# đầu ra của ``translate_mon_ten``, không phải trên tên tiếng Việt. Khoá tiếng
# Việt giữ lại làm lớp hai cho trường hợp từ lạ không có trong từ điển dịch.
# Khớp theo cụm DÀI trước, nên "glass bottle" thắng "glass".
_BAO_BI: dict[str, str] = {
    "glass bottle": "glass bottle",
    "plastic bottle": "plastic bottle",
    "carton box": "carton box",
    "zipper pouch": "zipper pouch",
    "drink can": "drink can",
    "bottle": "bottle",
    "jar": "jar",
    "jug": "jug",
    "pitcher": "pitcher",
    "pouch": "pouch",
    "pack": "pack",
    "box": "box",
    "crate": "crate",
    "can": "can",
    "glass": "glass",
    "cup": "cup",
    # Lớp hai — tên tiếng Việt khi từ điển dịch không nhận ra từ đó.
    "chai thủy tinh": "glass bottle",
    "chai": "bottle",
    "lọ": "jar",
    "hũ": "jar",
    "bình": "jug",
    "hộp": "box",
    "túi": "pouch",
    "lon": "can",
    "ly": "glass",
    "cốc": "glass",
    "tách": "cup",
}

# ── RÀNG BUỘC BẮT BUỘC ─────────────────────────────────────────────────────
# Bốn ràng buộc của quy trình, KHÔNG BAO GIỜ BỎ, kể cả ở lần chỉnh sửa thứ N.
# Viết thành hằng số để test khẳng định được từng điều khoản còn nguyên vẹn, và
# để không ai vô tình xoá khi sửa phần lắp prompt bên dưới.
_RANG_BUOC = (
    "The product stays front-facing and centered — same orientation as the source image.",
    "Do not change the shape, label, text, logo, packaging color, liquid color, or cap/lid.",
    "Environment, lighting, style, mood, camera angle, surface and surrounding props may change.",
    "No people, no hands, and no extra text or logo overlaid on the product.",
)

_KET = (
    "High resolution, realistic, commercial product photography quality, sharp focus on "
    "the product, clean composition."
)

# Từ khoá cấm trong phần ý kiến người dùng: model đọc được là sẽ vẽ lại sản phẩm
# hoặc thêm người. Người dùng gõ tiếng Việt lẫn tiếng Anh đều phải chặn.
#
# Đây là chốt an toàn ở tầng PROMPT, không phải thay thế cho quyền của người
# dùng: ai muốn ảnh khác kiểu thì sửa ô prompt ở UI (ô đó là văn bản tự do, có
# nhãn nói rõ "sửa được"), còn phần "mô tả thêm" thì phải nằm trong khuôn khổ
# giữ nguyên sản phẩm — nếu không, cả luồng mất ý nghĩa.

# Ánh xạ cụm tiếng Việt → tiếng Anh cho ý kiến người dùng. Chỉ chứa từ CHỈ BỐI
# CẢNH/ÁNH SÁNG/PHONG CÁCH — không chứa danh từ sản phẩm (xem ``_TU_KHOA_CAM``).
_GLOSSARY_BOI_CANH: dict[str, str] = {
    # bối cảnh
    "nền trắng": "plain white background",
    "nền đen": "black background",
    "nền xanh": "green background",
    "nền hồng": "pink background",
    "nền gỗ": "wooden table background",
    "nền biển": "seaside background",
    "nền cát": "sand background",
    "nền đá": "stone surface background",
    "nền studio": "studio background",
    "nền tối": "dark background",
    "nền sáng": "bright background",
    "nền mây": "soft cloudy sky background",
    "nền hoa": "flower background",
    "bàn gỗ": "wooden table surface",
    "mặt bàn": "table surface",
    "trên bàn": "on the table",
    "mặt đá": "marble surface",
    "quầy bar": "bar counter surface",
    "ngoài trời": "outdoor setting",
    "trong nhà": "indoor setting",
    "công viên": "park setting",
    "quán cà phê": "cafe interior setting",
    "phòng studio": "photo studio setting",
    "bãi biển": "beach setting",
    "vườn": "garden setting",
    # ánh sáng / tâm trạng
    "ánh sáng tự nhiên": "natural daylight",
    "ánh nắng": "sunlight",
    "nắng vàng": "warm golden light",
    "nắng sớm": "soft morning light",
    "hoàng hôn": "golden hour sunset light",
    "buổi sáng": "morning light",
    "buổi trưa": "midday light",
    "buổi chiều": "afternoon light",
    "buổi tối": "evening ambience",
    "ban đêm": "night ambience",
    "ánh nến": "candlelight",
    "đèn neon": "neon lighting",
    "studio sáng": "bright studio lighting",
    "sáng hơn": "brighter, higher exposure",
    "tối hơn": "darker, moodier exposure",
    "ấm hơn": "warmer color temperature",
    "lạnh hơn": "cooler color temperature",
    "tương phản mạnh": "strong contrast",
    "nổi bật": "eye-catching, standout",
    "rực rỡ": "vivid and colorful",
    "mềm mại": "soft gentle mood",
    "tươi sáng": "fresh bright mood",
    "sang trọng": "luxurious premium mood",
    "tối giản": "minimalist mood",
    "ấm cúng": "cozy warm mood",
    "mát mẻ": "cool refreshing mood",
    "mùa hè": "summer feel",
    "mùa đông": "winter feel",
    "tết": "Vietnamese lunar new year feel",
    # bố cục / máy ảnh
    "chụp gần": "closer framing",
    "chụp xa": "wider framing",
    "xóa phông": "shallow depth of field with creamy bokeh",
    "góc cao": "slightly high camera angle",
    "góc thấp": "slightly low camera angle",
    "nhìn thẳng": "straight-on camera angle",
    # vật trang trí
    "bỏ vật trang trí": "no props, clean empty surface",
    "bỏ bớt vật trang trí": "fewer props, cleaner surface",
    "thêm hoa": "a few flowers beside the product",
    "thêm đá": "a few ice cubes beside the product",
    "thêm lá": "a few fresh leaves beside the product",
    "lát chanh": "lemon slices beside the product",
    "lát cam": "orange slices beside the product",
    "lát": "slices",
    "thêm trái cây": "fresh fruit slices beside the product",
    "thêm vải": "a linen cloth beside the product",
    "thêm cà phê hạt": "scattered coffee beans beside the product",
    "thêm nến": "a candle beside the product",
    "thêm sách": "a book beside the product",
    "thêm cây": "a small plant beside the product",
    # hình khối chung — cụm cụ thể đứng TRƯỚC để "màu xanh dương" không bị
    # "màu xanh" ăn mất phần "dương".
    "màu xanh dương": "blue tones",
    "màu xanh biển": "blue tones",
    "màu xanh ngọc": "emerald green tones",
    "màu xanh lá": "green tones",
    "màu xanh mint": "mint green tones",
    "màu xanh": "green tones",
    "màu vàng": "yellow tones",
    "màu nâu": "brown tones",
    "màu hồng": "pink tones",
    "màu đỏ": "red tones",
    "màu tím": "purple tones",
    "màu cam": "orange tones",
    "màu xám": "grey tones",
    "màu be": "beige tones",
    "màu trắng": "white tones",
    "màu đen": "black tones",
}

# Từ nối / trợ từ tiếng Việt và tiếng Anh: bỏ khi KHÔNG khớp cụm nào trong từ
# điển. Không bỏ thì "làm sáng hơn" ra "làm brighter, higher exposure" — model
# vẫn hiểu nhưng prompt lẫn tiếng Việt, và những từ này không mang thông tin gì
# thêm (đã nằm trong cụm đích: "sáng hơn" → "brighter, higher exposure").
#
# Cụm dài được tra TRƯỚC nên từ nối chỉ bị bỏ khi đứng lẻ: "thêm hoa" khớp cụm
# và ra "a few flowers…", còn "thêm" trơ trọi mới bị bỏ.
_TU_NOI = frozenset(
    {
        "làm",
        "cho",
        "hãy",
        "muốn",
        "giúp",
        "thì",
        "hơi",
        "một",
        "chút",
        "thêm",
        "bớt",
        "bỏ",
        "đổi",
        "hơn",
        "sang",
        "thành",
        "về",
        "và",
        "của",
        "ở",
        "trên",
        "dưới",
        "phía",
        "the",
        "a",
        "an",
        "it",
        "please",
        "make",
        "bit",
        "slightly",
        "more",
        "less",
    }
)

# Cụm mà người dùng viết mà nếu đưa vào prompt sẽ phá ràng buộc bảo toàn sản phẩm
# (model sẽ THAY sản phẩm) hoặc vi phạm "không thêm người". Bị lọc khỏi phần ý
# kiến; phần còn lại của câu vẫn được giữ nên người dùng không mất trắng yêu cầu.
#
# So khớp theo RANH GIỚI TỪ (không phải chuỗi con) — xem :func:`_co_tu_khoa_cam`.
# Cố ý KHÔNG có các mục mơ hồ sau vì chúng chặn oan yêu cầu hợp lệ:
#   * "mẫu" — cùng dạng không dấu với "màu" ("màu xanh" bị chặn nhầm);
#   * "lật" — cùng dạng không dấu với "lát" ("lát chanh" bị chặn nhầm).
# Thay bằng cụm dài hơn, không thể trùng.
_TU_KHOA_CAM = (
    # đổi chính sản phẩm
    "thay chai",
    "thay ly",
    "thay lọ",
    "thay nhãn",
    "đổi nhãn",
    "đổi chai",
    "đổi màu nước",
    "đổi logo",
    "thêm chữ",
    "thêm logo",
    "viết tên",
    "lật ngược",
    "lật chai",
    "dựng đứng",
    "nghiêng",
    "quay ngang",
    "nhìn nghiêng",
    "đổ nước",
    "đổ ra",
    # thêm người
    "người",
    "nhân viên",
    "khách",
    "bàn tay",
    "tay cầm",
    # tiếng Anh (người dùng có thể gõ thẳng)
    "replace the bottle",
    "replace the label",
    "change the label",
    "redesign",
    "add text",
    "add logo",
    "person",
    "people",
    "human",
    "hand",
    "hands",
    "model holding",
    "side view",
    "rotate",
    "tilt",
    "upside down",
)

# Trần số từ cho một cụm tra từ điển. Phải đủ dài cho các cụm tự nhiên của
# người dùng ("bỏ bớt vật trang trí" = 5 từ, "ánh sáng tự nhiên" = 4 từ);
# ngắn hơn thì cụm dài không bao giờ khớp và từ lẻ lọt vào prompt.
_MAX_SPAN_CUM = 5

# Trần độ dài phần ý kiến trong prompt. Prompt dài quá thì model bỏ qua phần đầu
# (chỗ có ràng buộc bảo toàn sản phẩm) — mất ràng buộc là mất cả tính năng.
_MAX_Y_KIEN = 700
# Trần số ý kiến giữ lại. Người dùng bấm chỉnh 20 lần thì prompt vẫn phải gọn.
_MAX_Y_KIEN_LICH_SU = 12


@dataclass(frozen=True)
class AdPromptResult:
    """Prompt quảng cáo dựng từ ảnh thật + lịch sử ý kiến.

    ``prompt_en`` là chuỗi duy nhất được gửi sang model sinh ảnh.
    ``bo_qua`` liệt kê cụm ý kiến đã bị LỌC vì phá ràng buộc — UI hiện lại cho
    người dùng biết yêu cầu nào không áp dụng được và vì sao, thay vì âm thầm bỏ.
    """

    ok: bool
    prompt_en: str = ""
    prompt_vi: str = ""
    container: str = ""
    error: str = ""
    bo_qua: tuple[str, ...] = field(default_factory=tuple)


def _normalize(text: str) -> str:
    """Chuẩn hoá: thường hoá, bỏ dấu câu, gộp khoảng trắng (giữ dấu tiếng Việt)."""
    lowered = text.strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt — dùng để so khớp từ khoá cấm khi người dùng gõ không dấu."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").replace("đ", "d")


# Bảng tra KHÔNG DẤU, suy ra từ :data:`_GLOSSARY_BOI_CANH`.
#
# Vì sao cần: người dùng gõ nhanh rất hay bỏ dấu ("doi nen sang mau xanh").
# Không chuẩn hoá thì mọi câu không dấu trượt từ điển và lọt nguyên xi tiếng
# Việt vào prompt gửi model. Suy ra TỰ ĐỘNG thay vì viết tay: viết tay thì mỗi
# lần thêm mục vào từ điển có dấu là phải nhớ thêm mục không dấu tương ứng, và
# quên một cái là một lỗ thầm lặng.
#
# Cụm có dấu trùng không dấu (vd "vườn" và "vuon" cùng ra "vuon") đều map về
# cùng bản dịch nên ghi đè nhau vô hại.
_GLOSSARY_KHONG_DAU: dict[str, str] = {}
for _cum, _dich in _GLOSSARY_BOI_CANH.items():
    _GLOSSARY_KHONG_DAU.setdefault(_bo_dau(_cum), _dich)
# Từ nối cũng phải tra được ở dạng không dấu: người dùng gõ "doi nen sang mau
# xanh" thì "doi" phải bị bỏ như "đổi".
_TU_NOI_KHONG_DAU = frozenset(_bo_dau(t) for t in _TU_NOI)
# Từ khoá cấm cũng phải tra được ở dạng không dấu — người dùng bỏ dấu là cách
# vô tình lách qua bộ lọc dễ nhất.
_TU_KHOA_CAM_KHONG_DAU = tuple(_bo_dau(t) for t in _TU_KHOA_CAM)


def _co_tu_khoa_cam(menh_de: str) -> bool:
    """Mệnh đề có chứa cụm bị cấm không — so khớp theo RANH GIỚI TỪ.

    Khớp chuỗi con gây chặn oan: "mẫu" nằm trong "màu" (bỏ dấu thì "màu xanh"
    thành "mau xanh" và chứa "mau"), "đổ" nằm trong "đổi" ("đổi nền" thành
    "doi nen" và chứa "do"). Người dùng yêu cầu "màu xanh" mà bị báo là đòi thêm
    người — lỗi tệ hơn cả việc không lọc gì.
    """
    khong_dau = _bo_dau(menh_de)
    for tu in _TU_KHOA_CAM_KHONG_DAU:
        # Cụm nhiều từ: \b ở đầu và cuối vẫn đúng vì khoảng trắng là ranh giới.
        if re.search(rf"\b{re.escape(tu)}\b", khong_dau):
            return True
    return False


def loai_bao_bi(mon_ten: str) -> str:
    """Suy mô tả bao bì từ tên món; mặc định trung tính khi không nhận ra.

    Chỉ dùng để prompt gọi đúng LOẠI bao bì ("a glass bottle" thay vì "a glass").
    Không ảnh hưởng gì tới việc giữ nguyên sản phẩm — ảnh gốc mới là nguồn.
    """
    tokens = translate_mon_ten(mon_ten).lower().split()
    if not tokens:
        return _CONTAINER_MAC_DINH
    for span in range(min(3, len(tokens)), 0, -1):
        for start in range(len(tokens) - span + 1):
            phrase = " ".join(tokens[start : start + span])
            if phrase in _BAO_BI:
                return _BAO_BI[phrase]
    return _CONTAINER_MAC_DINH


def _dich_y_kien(text: str) -> str:
    """Dịch ý kiến người dùng sang tiếng Anh; từ lạ được giữ nguyên.

    Một vòng lặp khớp cụm dài trước, thử BỐN lớp tra theo thứ tự (người gõ đúng
    dấu luôn được ưu tiên, bản không dấu chỉ là lưới bắt):

    1. :data:`_GLOSSARY_BOI_CANH` — bối cảnh/ánh sáng/phong cách, có dấu;
    2. chính từ điển đó ở dạng không dấu;
    3. :func:`ca_agents.menu_prompt.known_phrase` — từ điển món ăn/đồ uống dùng
       chung, để "đá", "bạc hà", "trân châu" cũng ra tiếng Anh;
    4. lớp 3 ở dạng không dấu.

    Tra THEO CỤM chứ không dịch cả câu một lượt: dịch cả câu sẽ để cụm từ vắt
    qua ranh giới hai ý ("nền xanh làm sáng") khớp nhầm thành một cụm khác.
    """
    normalized = _normalize(text)
    if not normalized:
        return ""
    tokens = normalized.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        matched = False
        # Thử cụm 5 → 1 từ; cụm dài nhất thắng. Trần 5 (không phải 4) vì từ điển
        # bối cảnh có cụm 5 từ như "bỏ bớt vật trang trí" — cắt ở 4 thì cụm đó
        # không bao giờ khớp và các từ lẻ ("vật", "trang", "trí") lọt vào prompt.
        for span in range(min(_MAX_SPAN_CUM, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + span])
            # Thứ tự tra quyết định chất lượng: bối cảnh có dấu → bối cảnh không
            # dấu → từ điển món có dấu → từ điển món không dấu. Người gõ đúng dấu
            # luôn được ưu tiên; bản không dấu chỉ là lưới bắt khi họ bỏ dấu.
            dich_cum = (
                _GLOSSARY_BOI_CANH.get(phrase)
                or _GLOSSARY_KHONG_DAU.get(_bo_dau(phrase))
                or known_phrase(phrase)
                or known_phrase_khong_dau(phrase)
            )
            if dich_cum is None:
                continue
            out.append(dich_cum)
            i += span
            matched = True
            break
        if not matched:
            # Từ nối đứng lẻ: bỏ hẳn thay vì để lẫn tiếng Việt vào prompt.
            token = tokens[i]
            if token not in _TU_NOI and _bo_dau(token) not in _TU_NOI_KHONG_DAU:
                out.append(token)
            i += 1
    return " ".join(out)


def loc_y_kien(text: str) -> tuple[str, tuple[str, ...]]:
    """Tách cụm vi phạm ràng buộc ra khỏi ý kiến người dùng.

    Trả ``(ý_kiến_đã_lọc, các_cụm_bị_bỏ)``. So khớp trên bản BỎ DẤU để người dùng
    gõ "them nguoi" hay "thêm người" đều bị chặn như nhau — chặn theo dấu thì chỉ
    cần gõ thiếu dấu là lách qua được.
    """
    # Cắt mệnh đề trên văn bản GỐC (còn dấu câu): mỗi mệnh đề được kiểm riêng để
    # "nền xanh, thêm người" giữ được "nền xanh" thay vì bỏ cả câu.
    menh_de_goc = [m.strip() for m in re.split(r"[.;,\n]+|\s+(?:và|and|with)\s+", text, flags=re.IGNORECASE)]
    bo_qua: list[str] = []
    giu: list[str] = []
    for menh_de in menh_de_goc:
        normalized = _normalize(menh_de)
        if not normalized:
            continue
        if _co_tu_khoa_cam(normalized):
            bo_qua.append(normalized)
        else:
            giu.append(normalized)

    if not giu:
        return "", tuple(bo_qua)

    dich = ", ".join(filter(None, (_dich_y_kien(m) for m in giu)))
    return dich[:_MAX_Y_KIEN], tuple(bo_qua)


def append_feedback(history: list[str], moi: str) -> list[str]:
    """Nối một ý kiến mới vào ``user_feedback_history`` (bất biến, giữ thứ tự).

    Giữ cả ý kiến cũ thay vì ghi đè: người dùng nói "nền biển" rồi sau đó "làm
    sáng hơn" — hai ý kiến không mâu thuẫn, phải cùng có mặt trong prompt. Việc
    ưu tiên ý kiến mới khi MÂU THUẪN do chính prompt giải quyết: model sinh ảnh
    luôn nghe mệnh đề đứng sau khi hai mệnh đề xung đột, nên phần "Ghi chú mới
    nhất" ở cuối prompt là chốt chặn (xem :func:`build_ad_prompt`).

    Danh sách bị cắt còn :data:`_MAX_Y_KIEN_LICH_SU` phần tử, bỏ phần CŨ nhất.
    """
    cleaned = moi.strip()
    if cleaned:
        history = [*history, cleaned]
    return history[-_MAX_Y_KIEN_LICH_SU:]


def build_ad_prompt(
    mon_ten: str,
    *,
    feedback_history: list[str] | None = None,
    style_prompt: str = "",
) -> AdPromptResult:
    """Lắp prompt quảng cáo hoàn chỉnh theo cấu trúc template gốc (Bước 3).

    Args:
        mon_ten: Tên món — dùng để gọi đúng LOẠI bao bì trong prompt.
        feedback_history: Toàn bộ ý kiến người dùng đã ghi nhận (Bước 2 + Bước 4).
        style_prompt: Mô tả phong cách của quán (từ :class:`ca_agents.menu_style.MenuStyle`),
            đã là tiếng Anh. Nối vào phần bối cảnh.

    Returns:
        AdPromptResult — ``ok=False`` kèm ``error`` khi tên món trống (fail-closed,
        không bao giờ sinh ảnh từ prompt rỗng).
    """
    ten = mon_ten.strip()
    if not ten:
        return AdPromptResult(ok=False, error="thieu_ten_mon")

    container = loai_bao_bi(ten)
    parts = [_TEMPLATE_OPEN.format(container=container)]

    bo_qua: list[str] = []
    dich: list[str] = []
    for y_kien in feedback_history or []:
        text, skipped = loc_y_kien(y_kien)
        if text:
            dich.append(text)
        bo_qua.extend(skipped)

    if style_prompt.strip():
        dich.append(style_prompt.strip()[:400])
    if dich:
        parts.append(" ".join(dich))

    parts.append(" ".join(_RANG_BUOC))
    # Ý kiến mâu thuẫn: model ưu tiên mệnh đề đứng SAU, nên nhắc lại ý kiến MỚI
    # NHẤT ngay trước phần kết. Nhờ vậy "đổi nền biển" rồi "nền trắng studio" ra
    # nền trắng (yêu cầu mới thắng) mà không phải xoá lịch sử — xoá lịch sử thì
    # mất luôn các ý kiến cũ không liên quan (ánh sáng, góc chụp…).
    if dich:
        parts.append(f"Latest instruction to prioritize: {dich[-1]}.")

    parts.append(_KET)

    prompt_vi = f"Ảnh quảng cáo cho {ten}"
    if dich:
        prompt_vi += f" — theo {len(dich)} yêu cầu của bạn"
    return AdPromptResult(
        ok=True,
        prompt_en=" ".join(parts),
        prompt_vi=prompt_vi,
        container=container,
        bo_qua=tuple(bo_qua),
    )


# ── BƯỚC 1 — kiểm ảnh đầu vào ──────────────────────────────────────────────

_SYSTEM_KIEM_ANH = """You inspect a photo a cafe owner uploaded for a product advertisement.

Decide two things:
1. does the photo show a LIQUID PRODUCT CONTAINER — a bottle, jar, jug, carton, pouch, can, glass or cup that holds or is meant to hold a drink/liquid?
2. is the container CLEARLY VISIBLE — reasonably sharp, not mostly hidden or cropped away, not a drawing, cartoon, logo or unrelated snapshot?

Be strict: a plate of food, a person, a landscape, a receipt, a blurry unrelated photo, or a drawing must be rejected.
Return JSON only: {"is_liquid_product": true, "clearly_visible": true, "container": "glass bottle", "reason_vi": "..."}
Set both booleans to false when unsure. Keep "reason_vi" under 20 Vietnamese words."""

# Câu trả lời cho người dùng khi ảnh không hợp lệ — nguyên văn theo đặc tả.
THONG_DIEP_ANH_KHONG_HOP_LE = (
    "Ảnh bạn gửi không phải là ảnh sản phẩm dạng nước (chai/lọ/bình chứa chất lỏng). "
    "Vui lòng gửi lại ảnh sản phẩm rõ nét để mình xử lý."
)


@dataclass(frozen=True)
class ProductImageCheck:
    """Kết quả Bước 1.

    ``da_kiem`` phân biệt hai trường hợp có ``ok=True``: ảnh đã được AI thị giác
    xác nhận (``da_kiem=True``) với ảnh chỉ qua được kiểm tra kỹ thuật vì không
    có provider thị giác (``da_kiem=False``). UI phải nói rõ trường hợp thứ hai,
    không được để người dùng tưởng ảnh đã được kiểm nội dung.
    """

    ok: bool
    da_kiem: bool = False
    container: str = ""
    ly_do: str = ""
    error: str = ""


def validate_product_image(
    image_bytes: bytes,
    image_mime: str,
    *,
    timeout_s: float = 30.0,
) -> ProductImageCheck:
    """Bước 1 — ảnh có phải sản phẩm đựng chất lỏng, nhìn rõ không?

    Fail-closed theo hai tầng, có chủ đích:

    * **Ảnh sai định dạng / quá nhỏ** → ``ok=False``. Không có AI nào chữa được
      một file không phải ảnh, và ảnh vài chục pixel thì không có sản phẩm nào
      để dàn dựng lại.
    * **Không gọi được AI thị giác** (chưa cấu hình key, provider lỗi) →
      ``ok=True, da_kiem=False``. Chặn ở đây nghĩa là tính năng chết khi rút mạng,
      trong khi phần lớn giá trị (dàn dựng lại ảnh) vẫn làm được. Người dùng được
      báo rõ là chưa kiểm nội dung ảnh.

    Không bao giờ suy đoán nội dung ảnh bằng số liệu thay cho AI: "ảnh này có
    chai không" không quyết được bằng kích thước hay độ sáng, mà đoán bừa thì
    hoặc chặn oan ảnh đúng, hoặc cho qua ảnh rác.
    """
    suffix_ok = (
        image_bytes[:3] == b"\xff\xd8\xff"
        or image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        or image_bytes[:4] == b"RIFF"
    )
    if not image_bytes or not suffix_ok:
        return ProductImageCheck(
            ok=False,
            error="anh_goc_khong_hop_le",
            ly_do="Tệp gửi lên không phải ảnh (chỉ nhận JPG, PNG, WebP).",
        )

    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as img:
            rong, cao = img.size
    except Exception:  # noqa: BLE001 — PIL ném nhiều loại lỗi khác nhau cho ảnh hỏng
        return ProductImageCheck(
            ok=False,
            error="anh_goc_khong_doc_duoc",
            ly_do="Không mở được ảnh này. Thử lưu lại ảnh rồi gửi lại.",
        )

    # 200px là mức sàn để model sinh ảnh còn thấy được nhãn và logo của sản phẩm.
    if min(rong, cao) < 200:
        return ProductImageCheck(
            ok=False,
            error="anh_goc_qua_nho",
            ly_do="Ảnh quá nhỏ để làm ảnh quảng cáo. Gửi ảnh lớn hơn (cạnh ngắn từ 200px).",
        )

    res = complete(
        system=_SYSTEM_KIEM_ANH,
        user="Check this photo.",
        task="vision:menu_ad_check",
        timeout_s=timeout_s,
        json_mode=True,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )
    if not res.ok:
        # Ảnh đọc được nhưng không kiểm được nội dung — vẫn cho đi tiếp, kèm cờ
        # để UI nói thật với người dùng là chưa kiểm.
        logger.info("product image check skipped (%s)", res.reason)
        return ProductImageCheck(ok=True, da_kiem=False)

    try:
        data = json.loads(res.text)
    except json.JSONDecodeError:
        return ProductImageCheck(ok=True, da_kiem=False)

    la_san_pham = data.get("is_liquid_product") is True
    ro_rang = data.get("clearly_visible") is True
    container = str(data.get("container") or "").strip()[:60]
    ly_do = str(data.get("reason_vi") or "").strip()[:200]
    if not (la_san_pham and ro_rang):
        return ProductImageCheck(
            ok=False,
            da_kiem=True,
            container=container,
            ly_do=ly_do,
            error="anh_khong_phai_san_pham_nuoc",
        )
    return ProductImageCheck(ok=True, da_kiem=True, container=container, ly_do=ly_do)
