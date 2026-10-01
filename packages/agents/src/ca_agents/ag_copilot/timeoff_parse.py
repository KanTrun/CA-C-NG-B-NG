"""Nguồn DUY NHẤT cho phần parse xin nghỉ / báo bận (PROPOSE_TIME_OFF).

Trước đây cùng một logic nằm ở hai nơi (`intent_parser.py` và `tool_registry.py`),
lệch nhau theo thời gian: `_parse_ca_range` copy-paste 2 bản, `_parse_thu` vs
`_parse_thu_tu_tin` cũng vậy. Hệ quả là cùng một câu NV nói có thể ra 2 kết quả
khác nhau tuỳ vào chỗ gọi. Module này gom về một chỗ; `intent_parser` và
`tool_registry` đều import từ đây.

Không import `intent_parser`/`tool_registry` để tránh vòng lặp import.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any

# Khung giờ chuẩn của ca — NGUỒN DUY NHẤT. Phải khớp `_busy_to_availability`
# (solver/sprint3.py): đây là điểm phân biệt "bận 1 ca" với "bận cả ngày".
CA_RANGE: dict[str, tuple[str, str]] = {
    "sang": ("06:30", "12:00"),
    "chieu": ("12:00", "17:30"),
    "toi": ("17:30", "22:30"),
}

# Ngày trong tuần — dạng dài khớp bằng substring an toàn (không bị ambiguity).
_THU_DAI: dict[str, str] = {
    "thứ 2": "T2", "thứ hai": "T2", "thu 2": "T2", "thu hai": "T2",
    "thứ 3": "T3", "thứ ba": "T3", "thu 3": "T3", "thu ba": "T3",
    "thứ 4": "T4", "thứ tư": "T4", "thu 4": "T4", "thu tu": "T4",
    "thứ 5": "T5", "thứ năm": "T5", "thu 5": "T5", "thu nam": "T5",
    "thứ 6": "T6", "thứ sáu": "T6", "thu 6": "T6", "thu sau": "T6",
    "thứ 7": "T7", "thứ bảy": "T7", "thu 7": "T7", "thu bay": "T7",
    "chủ nhật": "CN", "chu nhat": "CN",
}

# Viết tắt ngắn (t2..t7) dùng regex word-boundary để tránh false positive.
# Cố ý KHÔNG có 'cn': quá mơ hồ (viết tắt 'công nhân', 'chi nhánh'...).
_THU_ABBREV: tuple[tuple[str, str], ...] = (
    (r"\bt2\b", "T2"), (r"\bt3\b", "T3"), (r"\bt4\b", "T4"),
    (r"\bt5\b", "T5"), (r"\bt6\b", "T6"), (r"\bt7\b", "T7"),
)
_THU_ABBREV_COMPILED = tuple(
    (re.compile(pat, re.IGNORECASE), val) for pat, val in _THU_ABBREV
)

_THU_TU_THEO_THAU = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


def chuan_hoa(text: Any) -> str:
    """Gộp khoảng trắng + hạ chữ thường, bỏ dấu câu treo ở hai đầu."""
    t = " ".join(str(text or "").lower().split())
    return t.strip(" \t\r\n,.;:-–—!?\"'“”‘’()")


def _bo_dau_tieng_viet(text: str) -> str:
    """Bỏ dấu thanh/dấu phụ để so khớp ổn định giữa có/không dấu.

    Dùng NFD + loại combining marks, KHÔNG bảng tra tay: bảng tay dễ sót chữ và
    sót là hỏng im lặng — đã từng sót "ô" khiến "Tôi bận thứ 5" không khớp "toi"
    nên câu có dấu bị giữ nguyên toàn văn thay vì bị loại hết.
    "đ" và "ô" là chữ cơ sơn, NFD không tách được nên bổ sung tay.
    """
    s = text.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", s).replace("ô", "o").replace("Ô", "O")


def parse_thu(text: str) -> str:
    """Trích thứ trong tuần (T2..CN) từ câu tiếng Việt. Rỗng nếu không nêu."""
    t = " ".join(str(text or "").lower().split())
    for cu, thu in _THU_DAI.items():
        if cu in t:
            return thu
    for pat, thu in _THU_ABBREV_COMPILED:
        if pat.search(t):
            return thu
    return ""


def parse_ca_range(text: str) -> tuple[str, str] | None:
    """Trích khung giờ nghỉ (start, end); None nếu chỉ nêu thứ (bận cả ngày)."""
    t = " ".join(str(text or "").lower().split())
    range_m = re.search(
        r"(\d{1,2})(?:[:h](\d{2})?)\s*(?:đến|-|tới|toi|den)\s*(\d{1,2})(?:[:h](\d{2})?)",
        t,
        re.IGNORECASE,
    )
    if range_m:
        h1, m1 = int(range_m.group(1)), int(range_m.group(2) or 0)
        h2, m2 = int(range_m.group(3)), int(range_m.group(4) or 0)
        return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"
    if "ca sáng" in t or "ca sang" in t or "buổi sáng" in t or "buoi sang" in t:
        return CA_RANGE["sang"]
    if "ca chiều" in t or "ca chieu" in t or "buổi chiều" in t or "buoi chieu" in t:
        return CA_RANGE["chieu"]
    if "ca tối" in t or "ca toi" in t or "buổi tối" in t or "buoi toi" in t:
        return CA_RANGE["toi"]
    return None


# ── Ngày tương đối ("hôm nay", "ngày mai") ──────────────────────────────────
# `_parse_thu` cố ý chỉ nhận "thứ X": cụm "nay"/"mai" quá mơ hồ để suy thứ.
# Ở đây ta xử lý riêng: chỉ khi câu nói rõ NGÀY TƯƠNG ĐỐI mới suy ra thứ từ
# `active_date` (ngày theo giờ quán do API gửi xuống).
# Tất cả CHỈ liệt kê dạng không dấu: đầu vào đã qua `_bo_dau_tieng_viet` nên
# "hôm nay"→"hom nay", "ngày mai"→"ngay mai" đã được phủ tự động.
_NGAY_TUONG_DOI: tuple[tuple[str, int], ...] = (
    ("hom nay", 0), ("ngay nay", 0), ("nay", 0), ("bay gio", 0), ("luon", 0),
    ("ngay mai", 1), ("sang mai", 1), ("ngay sau", 1),
    ("ngay kia", 2),
)


def parse_thu_tuong_doi(text: str, active_date: Any) -> str:
    """Suy thứ trong tuần từ ngày tương đối. Rỗng nếu câu không nêu ngày đó.

    Bổ sung cho `parse_thu`: "xin nghỉ buổi chiều nay" không có "thứ X" nên
    `parse_thu` trả rỗng → trước đây đơn bị bỏ rơi. Nay suy từ `active_date`.

    So khớp theo TỪ ĐỦC BIỆT (\\b) chứ không phải `in` thuần: cụm "nay" xuất
    hiện trong rất nhiều từ dính ("hoàn thành", "khuấy", "nay mai") — `in` sẽ
    khớp nhầm và gán sai thứ.
    """
    if not isinstance(active_date, date):
        return ""
    t = _bo_dau_tieng_viet(" ".join(str(text or "").lower().split()))
    for cu, delta in _NGAY_TUONG_DOI:
        if re.search(rf"\b{re.escape(cu)}\b", t):
            return _thu_tu_ngay(active_date + timedelta(days=delta))
    return ""


def _thu_tu_ngay(d: date) -> str:
    """T2..CN từ `date` (isoweekday: 1=Thứ 2 … 7=Chủ nhật)."""
    return _THU_TU_THEO_THAU[min(7, max(1, d.isoweekday())) - 1]


# ── Trích lý do nghỉ ─────────────────────────────────────────────────────────
# NV nói tự nhiên, lý do nằm lẫn với cụm mở đầu ("em xin nghỉ"), ngày
# ("thứ 5"), và ca ("buổi chiều"). Trước đây dùng `re.sub` chồng nên lý do thật
# bị token thời gian chôn ("sang thu 3 vi con ong" → ly_do sai), hoặc khi câu
# không có lý do thì tự điền "bận" — tức là bịa. Nay dùng phép loại token
# theo thứ tự, và KHÔNG bao giờ tự bịa: thiếu lý do thì trả "" để lớp trên hỏi lại.

# Mệnh đề nối báo lý do. Cố ý KHÔNG có "do": "do" nằm trong nhiều cụm không
# phải nối ("do anh giao", "cô do vậy") — để phần từ cuối (dưới đây) xử lý.
_MOI_DAU_LY_DO = ("vi", "boi", "nen")
_MOI_DAU_2_TU = (("tai", "vi"), ("o", "vi"))

# Cụm nhiều từ bị loại khi đứng đầu (dài trước, ngắn sau để thứ tự khớp đúng).
_CUM_NOISE_DAU: tuple[tuple[str, ...], ...] = (
    ("xin", "nghi", "ca"), ("khong", "di", "lam"), ("khong", "di", "duoc"),
    ("khong", "thanh", "cong"), ("khong", "ranh"), ("khong", "lam", "duoc"),
    ("muon", "nghi"), ("cho", "em"), ("cho", "toi"), ("cho", "anh"), ("cho", "chi"),
    ("xin", "nghi"), ("nghi", "ca"), ("nghi", "mot", "buoi"), ("tai", "vi"),
    ("ca", "sang"), ("ca", "chieu"), ("ca", "toi"),
    ("buoi", "sang"), ("buoi", "chieu"), ("buoi", "toi"),
    ("hom", "nay"), ("ngay", "nay"), ("ngay", "mai"), ("ngay", "kia"),
    ("hom", "qua"), ("hom", "kia"), ("cuoi", "tuan"), ("sang", "mai"),    ("chu", "nhat"), ("thu", "hai"), ("thu", "ba"), ("thu", "tu"),
    ("thu", "nam"), ("thu", "sau"), ("thu", "bay"),
)

# Từ đơn bị loại khi đứng đầu. KHÔNG có "con" ("con ốm" là lý do) và
# KHÔNG có "sang/chieu/toi" đứng lẻ (xử lý bằng điều kiện thứ trong câu).
_TU_NOISE_DAU = frozenset({
    # đại từ / xưng ("ban" là "bạn"/"bận" — cùng dạng không dấu)
    "toi", "em", "minh", "anh", "chi", "ban",
    # mệnh đề nối
    "vi", "boi", "nen", "do",
    # động từ xin nghỉ
    "xin", "nghi",
    # ca / buổi (chỉ khi đi kèm ngày — xem _la_noise_dau)
    "buoi", "ca", "mot", "hai", "1", "2",
    # ngày
    "thu", "ngay", "hom", "nay", "mai",
    # lịch sự
    "nhe", "nha", "nho", "a", "oi",
    "vui", "long", "thoi", "luon", "duoc", "ranh",
})

_DAI_TU = frozenset({"toi", "em", "minh", "anh", "chi", "ban"})
_BUOI_TRONG_NGAY = frozenset({"sang", "chieu", "toi"})
_TEN_THU = frozenset({"hai", "ba", "tu", "nam", "sau", "bay", "nhat"})
_HAU_TO_LICH_SU = frozenset({
    "nhe", "nha", "nho", "a", "oi", "thoi",
})

# "thứ 5", "thu nam", "t3" — nhận diện để biết câu có nêu ngày không.
_RE_CO_NGAY = re.compile(
    r"\b(?:th[uứ]\s*(?:\d|[a-zà-ỹ]+)|t[2-7]|ch[uủ]\s*nh[aậ]t)\b|"
    r"\b(?:hom|ngay)\s*(?:nay|mai|kia|qua)\b",
    re.IGNORECASE,
)

# Động từ xin nghỉ: dùng để phát hiện "mệnh đề nối tìm thấy nhầm".
_CUM_DONG_TU_NGHI = ("xin nghi", "nghi ca", "khong di lam", "khong di duoc")


def _co_dong_tu_nghi(text: str) -> bool:
    t = _bo_dau_tieng_viet(text.lower())
    return any(cum in t for cum in _CUM_DONG_TU_NGHI)


def _la_noise_dau(toks: list[str], i: int) -> int:
    """Số token nhiễu bắt đầu tại `i` (0 = không phải nhiễu).

    `toks` đã bỏ dấu. Trả về ĐỘ DÀI khớp (không phải bool) vì cụm nhiều từ
    ("xin nghi", "ca sang") phải ăn trọn vẹn — nếu chỉ ăn từng từ thì "di lam"
    còn sót lại và bị tính nhầm là lý do.
    """
    tok = toks[i]
    for n in (3, 2):
        if tuple(toks[i:i + n]) in _CUM_NOISE_DAU:
            return n
    if tok in _TU_NOISE_DAU:
        # "thứ 5" / "thứ năm": ăn luôn con số/từ chỉ ngày đứng sau "thứ".
        if tok == "thu" and i + 1 < len(toks) and (
            re.fullmatch(r"[2-7]", toks[i + 1]) or toks[i + 1] in _TEN_THU
        ):
            return 2
        # Số từ chỉ là nhiễu khi đi cùng "buổi": "1 buổi chiều".
        if tok in ("mot", "hai", "1", "2") and i + 1 < len(toks):
            return 2 if toks[i + 1] in ("buoi", "buổi") else 0
        # Đại từ chỉ là nhiễu khi nó mở đầu lệnh, tức kẹp theo là nhiễu nữa
        # ("em xin nghỉ" → bỏ "em"). Nếu sau nó là mệnh đề thật
        # ("em đi khám bệnh") thì giữ nguyên để lý do không bị cụt.
        if tok in _DAI_TU and i + 1 < len(toks):
            return 1 if _la_noise_dau(toks, i + 1) else 0
        return 1
    # "sáng/chiều/tối" đứng lẻ chỉ là nhiễu khi câu còn nhắc tới ngày; nếu
    # không thì rất có thể là từ trong lý do ("sáng mai tôi mệt").
    if tok in _BUOI_TRONG_NGAY and _RE_CO_NGAY.search(" ".join(toks[i + 1:])):
        return 1
    return 0


def _lo_dau(text: str) -> str:
    """Bỏ dần các token mở đầu cho tới khi gặp phần đầu tiên KHÔNG phải nhiễu.

    Giữ NGUYÊN dấu của phần còn lại: dấu tiếng Việt là thông tin, không phải
    nhiễu — nhân viên và quản lý đọc lý do này.
    """
    goc = str(text or "").split()
    if not goc:
        return ""
    # Hạ chữ + bỏ dấu CHỈ để so khớp; phần trả về giữ nguyên `goc` (có dấu,
    # phân biệt hoa thường như người dùng gõ).
    toks = [_bo_dau_tieng_viet(t.lower()) for t in goc]
    i = 0
    while i < len(toks):
        n = _la_noise_dau(toks, i)
        if not n:
            break
        i += n
    return " ".join(goc[i:]).strip(" ,.;:-–—!?")


def _sau_moi_dau(text: str) -> str:
    """Phần sau mệnh đề nối đầu tiên ("vì/vi/bởi/nên"). Rỗng nếu không có."""
    goc = str(text or "").split()
    if not goc:
        return ""
    toks = [_bo_dau_tieng_viet(t.lower()) for t in goc]
    for i, tok in enumerate(toks):
        j = -1
        if tok in _MOI_DAU_LY_DO:
            j = i + 1
        elif i + 1 < len(toks) and (tok, toks[i + 1]) in _MOI_DAU_2_TU:
            j = i + 2
        if j < 0:
            continue
        du = " ".join(goc[j:]).strip(" ,.;:-–—!?")
        if not du:
            return ""
        if _co_dong_tu_nghi(du):
            # Mệnh đề nối tìm thấy nhầm: câu dạng "vì con ốm em xin nghỉ
            # thứ 5" — lý do nằm TRƯỚC động từ xin nghỉ, không phải sau.
            head = du[:_vi_tri_dong_tu_nghi(du)]
            return _bo_dai_tu_cuoi(head).strip(" ,.;:-–—!?") if head else ""
        return du
    return ""


def _bo_dai_tu_cuoi(text: str) -> str:
    """Bỏ đại từ rơi ở CUỐI ("vì con ốm em xin nghỉ" → "con ốm")."""
    goc = str(text or "").split()
    while len(goc) > 1 and _bo_dau_tieng_viet(goc[-1].lower()) in _DAI_TU:
        goc.pop()
    return " ".join(goc)


def _vi_tri_dong_tu_nghi(text: str) -> int:
    """Vị trí đầu tiên của động từ xin nghỉ trong `text` (len(text) nếu không có)."""
    t = _bo_dau_tieng_viet(text.lower())
    vi_tri = [t.find(cum) for cum in _CUM_DONG_TU_NGHI if cum in t]
    return min(vi_tri) if vi_tri else len(text)


def _danh_sach_doan(text: str) -> list[str]:
    """Các đoạn ngăn bởi dấu phẩy/giấu hai chấm, đảo từ cuối về đầu."""
    parts = [p.strip() for p in re.split(r"[,;:]", text) if p.strip()]
    return list(reversed(parts))


def trich_ly_do(text: str) -> str:
    """Trích LÝ DO nghỉ khỏi câu NV nói. Trả `""` nếu câu không nêu lý do.

    Thứ tự ưu tiên (mỗi bước đều phải cho ra kết quả KHÔNG RỖNG mới dừng):

    1. Đoạn sau dấu phẩy/`:`, lấy từ đoạn cuối có nội dung về trước — tránh
       bỏ sót lý do nằm trước dấu phẩy ("..., nha, em đi khám bệnh").
    2. Phần sau mệnh đề nối ("vì/vi/bởi/nên") — nơi lý do hay nằm nhất.
    3. Còn lại của câu sau khi loại cụm mở đầu + thứ + ca ("xin nghỉ 1 buổi
       chiều thứ 6 nha" → rỗng ⇒ để lớp trên hỏi lại, KHÔNG tự điền "bận").
    """
    raw = " ".join(str(text or "").split()).strip(" \t\r\n")
    if not raw:
        return ""

    for doan in _danh_sach_doan(raw):
        for ung in (_sau_moi_dau(doan), _lo_dau(doan)):
            if ung:
                return _chuan_hoa_ket_qua(ung)

    for doan in [raw, *_danh_sach_doan(raw)]:
        ung = _sau_moi_dau(doan)
        if ung:
            return _chuan_hoa_ket_qua(ung)

    ket = _lo_dau(raw)
    return _chuan_hoa_ket_qua(ket) if ket else ""


def _chuan_hoa_ket_qua(ly_do: str) -> str:
    """Dọn lịch sự cuối câu và giới hạn độ dài (giữ nguyên dấu)."""
    goc = str(ly_do or "").split()
    while goc and _bo_dau_tieng_viet(goc[-1].lower().strip(" ,.;:-–—!?")) in _HAU_TO_LICH_SU:
        goc.pop()
    return " ".join(goc).strip(" ,.;:-–—!?\"'“”‘’()")[:200]
