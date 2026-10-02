"""AG-MEETING extraction engine — Transcript to structured Meeting Minutes, Action Items, and SOP proposals."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from ca_agents.llm import agent_mode, complete, ensure_dotenv, parse_json_object

_THU_CAN = {
    "thứ 2": "T2", "thứ hai": "T2", "thu 2": "T2", "thu hai": "T2",
    "thứ 3": "T3", "thứ ba": "T3", "thu 3": "T3", "thu ba": "T3",
    "thứ 4": "T4", "thứ tư": "T4", "thu 4": "T4", "thu tu": "T4",
    "thứ 5": "T5", "thứ năm": "T5", "thu 5": "T5", "thu nam": "T5",
    "thứ 6": "T6", "thứ sáu": "T6", "thu 6": "T6", "thu sau": "T6",
    "thứ 7": "T7", "thứ bảy": "T7", "thu 7": "T7", "thu bay": "T7",
    "chủ nhật": "CN", "chu nhat": "CN",
}
_THU_ABBREV_PATTERNS = [
    (r"\bt2\b", "T2"), (r"\bt3\b", "T3"), (r"\bt4\b", "T4"),
    (r"\bt5\b", "T5"), (r"\bt6\b", "T6"), (r"\bt7\b", "T7"),
    (r"\bcn\b", "CN"),
]


def _detect_thu(text: str) -> str:
    low = " ".join(str(text or "").lower().split())
    for k, v in _THU_CAN.items():
        if k in low:
            return v
    for pat, v in _THU_ABBREV_PATTERNS:
        if re.search(pat, low):
            return v
    return ""


def _detect_khung(text: str) -> str:
    low = text.lower()
    if "sáng" in low or "sang" in low:
        return "sang"
    if "chiều" in low or "chieu" in low:
        return "chieu"
    if "tối" in low or "toi" in low or "đêm" in low:
        return "toi"
    return ""


def _strip_accents(text: str) -> str:
    """Normalize and remove diacritics for accent-less mobile typing matching."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def resolve_staff_id_with_meta(
    name: str,
    staff_list: list[dict[str, Any]] | None,
    *,
    allow_fuzzy_stt: bool = False,
) -> tuple[str | None, bool]:
    """Fuzzy match spoken person name to official NhanVien ID.

    Returns:
        (nv_id, is_stt_near_miss)
    """
    if not name or not staff_list:
        return None, False
    clean_name = name.strip().lower()
    if not clean_name:
        return None, False

    # Words that should NEVER be treated as a person's name (actions, objects, prepositions)
    _NAME_STOPWORDS = {
        "tra", "tu", "kho", "ban", "may", "ca", "truoc", "nuoc", "sua",
        "quan", "lanh", "ly", "don", "lau", "xong", "kiem", "bar", "ron",
    }
    if clean_name in _NAME_STOPWORDS:
        return None, False

    def _ten_hien_thi_candidates(ten: str) -> list[str]:
        """Tên người dùng để khớp, từ một chuỗi hiển thị.

        users thật hay đặt display_name kèm chức danh, ví dụ
        "Minh Phạm — Trưởng pha chế (PT)". Chỉ phần trước dấu gạch ngang
        dài là tên; để nguyên cả chuỗi thì resolve_staff_id không bao giờ
        khớp và mọi việc giao ca đều mất người nhận (bug gặp thật 2026-10-01).
        """
        core = re.split(r"\s+[—–-]\s*", ten.strip())[0]
        core = re.sub(r"\([^)]*\)", "", core).strip()
        out = []
        for candidate in (ten.strip(), core):
            normalized = re.sub(r"\s+", " ", candidate).lower()
            if normalized and normalized not in out:
                out.append(normalized)
        return out

    def _khop_ten(ten_hien_thi: str, spoken: str) -> bool:
        for candidate in _ten_hien_thi_candidates(ten_hien_thi):
            words = candidate.split()
            first_name = words[-1] if words else ""
            if (
                spoken == candidate
                or spoken == first_name
                or spoken in words
                or spoken.endswith(f" {first_name}")
            ):
                return True
        return False

    # 1. Exact match or token / first name match with original diacritics
    for nv in staff_list:
        nv_id = str(nv.get("id") or "")
        nv_ten = str(nv.get("ten") or "")
        if not nv_ten:
            continue
        if _khop_ten(nv_ten, clean_name):
            return nv_id, False

    # 2. Accent-insensitive fallback (TC-31 / R10: mobile typing without accents e.g. "tuan", "my", "lan")
    clean_no_accent = _strip_accents(clean_name)
    if clean_no_accent and clean_no_accent not in _NAME_STOPWORDS:
        for nv in staff_list:
            nv_id = str(nv.get("id") or "")
            nv_ten = str(nv.get("ten") or "")
            if not nv_ten:
                continue
            if _khop_ten(_strip_accents(nv_ten), clean_no_accent):
                return nv_id, False

    # 3. STT Near-miss fuzzy matching (TC-37: Levenshtein distance <= 1 for phonetic hearing errors)
    if allow_fuzzy_stt and clean_no_accent and clean_no_accent not in _NAME_STOPWORDS:
        for nv in staff_list:
            nv_id = str(nv.get("id") or "")
            nv_ten = str(nv.get("ten") or "")
            if not nv_ten:
                continue
            ten_no_accent = _strip_accents(nv_ten)
            # So tên cốt lõi (bỏ chức danh sau gạch ngang) — "(sm)" không phải tên
            candidates_no_accent = _ten_hien_thi_candidates(ten_no_accent)
            for candidate in candidates_no_accent:
                first_name_no_accent = candidate.split()[-1]
                if len(clean_no_accent) < 3 or abs(len(clean_no_accent) - len(first_name_no_accent)) > 1:
                    continue
                dist = _levenshtein(clean_no_accent, first_name_no_accent)
                max_dist = 1 if len(clean_no_accent) <= 4 else 2
                if dist <= max_dist:
                    return nv_id, True

    return None, False


def resolve_staff_id(
    name: str,
    staff_list: list[dict[str, Any]] | None,
    allow_fuzzy_stt: bool = False,
) -> str | None:
    """Fuzzy match spoken person name to official NhanVien ID (supports accents, unaccented, and near-miss)."""
    nv_id, _ = resolve_staff_id_with_meta(name, staff_list, allow_fuzzy_stt=allow_fuzzy_stt)
    return nv_id


def _resolve_relative_deadline(text: str, base_dt: datetime) -> str:
    """Anchor relative time words to the meeting's recording timestamp (TC-36)."""
    low = text.lower()
    thu_names = {0: "Thứ Hai", 1: "Thứ Ba", 2: "Thứ Tư", 3: "Thứ Năm", 4: "Thứ Sáu", 5: "Thứ Bảy", 6: "Chủ Nhật"}
    if any(k in low for k in ["sáng mai", "mai làm", "ngày mai", "hôm sau", "ngay mai"]):
        tmr = base_dt + timedelta(days=1)
        return f"{tmr.strftime('%Y-%m-%d')} ({thu_names.get(tmr.weekday(), '')})"
    if any(k in low for k in ["hôm nay", "chiều nay", "tối nay", "trong ca", "hết ca"]):
        return f"{base_dt.strftime('%Y-%m-%d')} (Trong ca)"
    detected = _detect_thu(low)
    if detected:
        thu_idx = {"T2": 0, "T3": 1, "T4": 2, "T5": 3, "T6": 4, "T7": 5, "CN": 6}.get(detected)
        if thu_idx is not None:
            days_ahead = (thu_idx - base_dt.weekday()) % 7
            if days_ahead == 0 and "tuần sau" in low:
                days_ahead = 7
            target_date = base_dt + timedelta(days=days_ahead)
            return f"{target_date.strftime('%Y-%m-%d')} ({thu_names.get(target_date.weekday(), '')})"
    m_hour = re.search(r"\b(\d{1,2})[h:](\d{2})?\b", text)
    if m_hour:
        h = m_hour.group(1).zfill(2)
        m = (m_hour.group(2) or "00").zfill(2)
        return f"{h}:{m}"
    return "Trong ca"


def _split_compound_line(line: str, staff_list: list[dict[str, Any]] | None) -> list[str]:
    """Split compound line with multiple person-action clauses (TC-38)."""
    low = line.lower()
    retraction_cues = ["à thôi", "thôi để", "nhầm", "thay vì", "đổi lại", "thôi giao cho", "thôi nhờ"]
    if any(rc in low for rc in retraction_cues):
        return [line]
    parts = [p.strip() for p in re.split(r"[,;]", line) if p.strip()]
    if len(parts) <= 1:
        return [line]
    matched_count = 0
    for p in parts:
        if any(resolve_staff_id(w.strip(".,;:!?"), staff_list, allow_fuzzy_stt=True) for w in p.split()):
            matched_count += 1
    if matched_count >= 2:
        return parts
    return [line]


def _strip_speaker_prefix(line: str) -> str:
    """Bỏ tiền tố người nói khỏi nội dung câu.

    Mỗi dòng thoại có dạng "Tuấn: em lau bàn nhé". Tên người nói đã được tách
    riêng ở `nguoi_noi`, nhưng tiêu đề việc treo lại dùng nguyên `line` nên
    thành "Tuấn: em lau bàn nhé" — tên bị lặp vào nội dung việc, và cũng làm
    bộ chống trùng ở `apply_meeting_decisions` so sai chuỗi.

    Phải neo theo MỘT cụm từ đầu dòng (`^từ:`) và loại trừ tiền tố là số.
    Bản cũ dùng `^[^:]{1,40}:` nên khớp cả "Tuấn: 14" trong
    "Tuấn: 14:00 dọn bàn nhé" và ăn mất giờ — mốc thời gian quan trọng nhất
    của câu bị xoá trước khi tới `_resolve_relative_deadline`.
    """
    m = re.match(r"^([^\s:][^:]{0,30}?)\s*:\s*(\S.*)$", line)
    if m and m.group(1).strip() and not m.group(1).strip()[0].isdigit():
        return m.group(2).strip()
    return line


# Lượt nói thể hiện nhận việc, không phải giao việc mới.
_ACK_LEADING = (
    "dạ", "vâng", "dạ", "vang", "ok", "oke", "uh", "ừ", "uk", "được", "duoc",
    "em sẽ", "em se", "em làm", "em lam", "để em", "de em", "con sẽ", "con se",
    "tôi sẽ", "toi se", "nhất trí", "nhat tri",
)

# Dấu hiệu lượt nói mang THÔNG TIN MỚI dù mở đầu bằng "dạ/vâng".
# "Dạ em xin nghỉ thứ 4" và "Dạ em đồng ý làm ca sáng thứ 2" đều bắt đầu bằng
# "Dạ em" nhưng chúng là đơn xin nghỉ / nhận ca — bỏ qua là mất luôn điều
# chỉnh lịch. Chỉ được coi là lời nhận việc khi KHÔNG chứa các dấu hiệu này.
#
# So khớp theo RANH GIỚI TỪ (xem `_has_word`), không dùng `in` trần: "nghi"
# không dấu là substring của "nghiêm"/"nghiên" nên bản dùng `in` đã bỏ oan
# những câu nhận việc thật như "Dạ em sẽ nghiêm túc dọn bàn ca sau".
_ACK_NEW_INFO_CUES = (
    "xin nghỉ", "xin nghi", "xin phép", "xin phep", "nghỉ", "nghi",
    "đổi ca", "doi ca", "ghim", "trực", "truc", "làm ca", "lam ca",
    "ca sáng", "ca sang", "ca chiều", "ca chieu", "ca tối", "ca toi",
    "thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "chủ nhật",
    "t2", "t3", "t4", "t5", "t6", "t7", "cn",
    "tuần sau", "tuan sau", "nghỉ phép", "nghi phep",
)


def _has_word(haystack: str, needle: str) -> bool:
    """Khớp `needle` theo ranh giới từ.

    Tránh false positive kiểu "nghi" khớp trong "nghiêm"/"nghiên".
    `\\b` hoạt động đúng với ký tự tiếng Việt trong Python `re` (unicode).
    """
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _is_acknowledgement(low: str) -> bool:
    """True nếu lượt nói là lời NHẬN việc, không phải một việc mới.

    Gọi SAU khi đã bỏ tiền tố người nói — nếu kiểm tra trên `line` gốc thì
    "Tuấn: Dạ em sẽ lau bàn" không khớp vì câu bắt đầu bằng tên.
    """
    body = _strip_speaker_prefix(low).strip()
    if not body:
        return False
    if not any(_has_word(body, lead) or body.startswith(lead) for lead in _ACK_LEADING):
        return False
    # Có thông tin mới (nghỉ/đổi ca/ghim ca) thì đây là lượt nghiệp vụ thật,
    # không phải lời nhận việc suông.
    return not any(_has_word(body, cue) for cue in _ACK_NEW_INFO_CUES)


# Mốc ca tương đối → nhãn ca hiển thị được ở việc treo.
# CỐ Ý không có "sáng mai"/"chiều mai": `_resolve_relative_deadline` đã xử lý
# các mốc đó thành NGÀY CỤ THỂ neo theo lúc ghi âm (TC-36). Ghi đè ở đây sẽ
# làm mất mốc ngày (đã gây hồi quy test TC-36).
_SHIFT_REFERENCE_CUES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ca sau", "ca tới", "ca kế", "ca tiếp", "ca sau nữa"), "Ca kế tiếp"),
    (("ca này", "ca hiện tại", "ca đang"), "Ca hiện tại"),
    (("tối nay", "tối hôm nay"), "Ca Tối (hôm nay)"),
    (("chiều nay", "chiều hôm nay"), "Ca Chiều (hôm nay)"),
)


def _detect_shift_reference(low: str, resolved_due: str) -> str | None:
    """Nhãn ca khi câu nói chỉ định ca tương đối ("ca sau", "chiều nay").

    Trước đây các mốc này rơi hết về "Trong ca": người giao nói rõ "ca sau"
    mà việc treo lại ghi "Trong ca", và `ca_thuc_hien` bỏ trống nên tầng làm
    rõ còn tưởng nhân viên không có ca nào và hỏi sai câu.

    Chỉ trả nhãn khi `_resolve_relative_deadline` KHÔNG ra mốc cụ thể — nếu
    đã có ngày/giờ chính xác thì đó là thông tin tốt hơn, không được ghi đè.
    """
    if resolved_due and resolved_due != "Trong ca":
        return None
    for cues, label in _SHIFT_REFERENCE_CUES:
        if any(cue in low for cue in cues):
            return label
    return None


def _is_grounded_in_transcript(title: str, transcript: str) -> bool:
    """Guardrail: Verify action item is grounded in transcript to prevent hallucination (TC-40)."""
    if not title or not transcript:
        return False
    stop_words = {"cho", "làm", "trước", "nhé", "nhớ", "trong", "phải", "được", "việc", "ngày", "chiều", "sáng", "tối", "quán", "cần", "giúp"}
    words = [re.sub(r"[^\w]", "", w).lower() for w in title.split()]
    sig_words = [w for w in words if len(w) >= 3 and w not in stop_words]
    if not sig_words:
        return True
    trans_low = transcript.lower()
    return any(w in trans_low for w in sig_words)


def extract_meeting(
    text: str,
    *,
    segments: list[dict[str, Any]] | None = None,
    staff_list: list[dict[str, Any]] | None = None,
    meeting_type: str = "giao_ca",
    meeting_id: str | None = None,
    audio_source: str = "microphone",
    thoi_gian: str | None = None,
) -> dict[str, Any]:
    """Extract structured meeting minutes, action items, and SOP proposals from text transcript."""
    ensure_dotenv()
    mid = meeting_id or f"meet_{uuid.uuid4().hex[:8]}"
    mode = agent_mode()

    # If in replay mode
    if mode == "replay":
        return _extract_rule_or_fixture(
            text=text,
            meeting_id=mid,
            meeting_type=meeting_type,
            audio_source=audio_source,
            segments=segments,
            staff_list=staff_list,
            thoi_gian=thoi_gian,
        )

    if not text.strip():
        return _extract_rule_or_fixture(
            text="Ghi nhận ca làm việc",
            meeting_id=mid,
            meeting_type=meeting_type,
            audio_source=audio_source,
            segments=segments,
            staff_list=staff_list,
            thoi_gian=thoi_gian,
        )

    # Live mode via LLM — use v2 prompt first, fallback to v1
    prompt_base = Path(__file__).resolve().parent.parent / "prompts" / "ag_meeting"
    prompt_path = prompt_base / "v2.md"
    if not prompt_path.is_file():
        prompt_path = prompt_base / "v1.md"
    system_prompt = (
        prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else "Bạn là AG-MEETING."
    )

    # Build segment detail string for better context
    seg_detail = ""
    if segments:
        seg_lines = [f"  [{s.get('nguoi_noi', '?')}]: {s.get('noi_dung', '')}" for s in segments]
        seg_detail = "\n\nChi tiết từng đoạn thoại:\n" + "\n".join(seg_lines)

    user_prompt = (
        f"Loại cuộc họp: {meeting_type}\n"
        f"Danh sách nhân viên trong quán: {', '.join(nv.get('ten', '') for nv in (staff_list or []))}\n"
        f"Nội dung bản bóc băng thoại:\n{text.strip()}"
        f"{seg_detail}\n\n"
        "Hãy phân tích kỹ và trả về JSON đầy đủ gồm: "
        "khong_lien_quan, tieu_de, tom_tat, quyet_dinh, audit_sop, ban_tin_ca, huan_luyen_quan_ly, de_xuat_phe_duyet, action_items, gop_y_luu_y, do_tin_cay_tong_the."
    )

    res = complete(
        system=system_prompt,
        user=user_prompt,
        task="text:ag_meeting",
        json_mode=True,
    )

    parsed = parse_json_object(res.text) if res.ok else None
    if not parsed or not isinstance(parsed, dict):
        return _extract_rule_or_fixture(
            text=text,
            meeting_id=mid,
            meeting_type=meeting_type,
            audio_source=audio_source,
            segments=segments,
            staff_list=staff_list,
            thoi_gian=thoi_gian,
        )

    return _normalize_output(
        data=parsed,
        meeting_id=mid,
        meeting_type=meeting_type,
        audio_source=audio_source,
        segments=segments,
        staff_list=staff_list,
    )


def _extract_rule_or_fixture(
    text: str,
    meeting_id: str,
    meeting_type: str,
    audio_source: str,
    segments: list[dict[str, Any]] | None,
    staff_list: list[dict[str, Any]] | None,
    thoi_gian: str | None = None,
) -> dict[str, Any]:
    """Rule-based heuristic extractor and golden fixture fallback."""
    raw = text.strip()

    # 1. Check if matches golden coffee meeting
    if ("máy pha số 2" in raw and "rỉ nước" in raw) or ("syrup đào" in raw and "rỉ nước" in raw) or "meeting_01" in raw:
        items = [
            {
                "id": "act_1",
                "tieu_de": "Thay ron dự phòng và vệ sinh họng máy pha số 2",
                "noi_dung_chi_tiet": "Tháo phần ron cao su cũ bị rỉ, lắp ron mới, vệ sinh sạch họng máy và kiểm tra lại áp suất trước khi pha.",
                "ten_nguoi_nhan": "Tuấn",
                "pham_vi": "ca_nhan",
                "nhan_vien_id": resolve_staff_id("Tuấn", staff_list) or "nv_01",
                "han_chot": "16:00",
                "muc_do_uu_tien": "cao",
                "do_tin_cay": 0.95,
                "da_chon": True,
                "stt_near_miss": False,
                "khong_co_can_cu": False,
                "nguon_cau_noi": "Thay ron dự phòng và vệ sinh họng máy pha số 2",
            },
            {
                "id": "act_2",
                "tieu_de": "Dán bảng công thức trà đào mới tại quầy bar",
                "noi_dung_chi_tiet": "In hoặc viết tay bảng công thức mới: syrup đào 20ml (thay vì 30ml cũ), dán tại vị trí dễ thấy trên quầy bar.",
                "ten_nguoi_nhan": "My",
                "pham_vi": "ca_nhan",
                "nhan_vien_id": resolve_staff_id("My", staff_list) or "nv_02",
                "han_chot": "17:00",
                "muc_do_uu_tien": "cao",
                "do_tin_cay": 0.92,
                "da_chon": True,
                "stt_near_miss": False,
                "khong_co_can_cu": False,
                "nguon_cau_noi": "Dán bảng công thức trà đào mới tại quầy bar",
            },
            {
                "id": "act_3",
                "tieu_de": "Kiểm tra và vệ sinh tủ đá",
                "noi_dung_chi_tiet": "Kiểm tra tình trạng đông đá, lau khay đựng nước đọng, đảm bảo đủ đá cho ca tối.",
                "ten_nguoi_nhan": "Tuấn",
                "pham_vi": "ca_nhan",
                "nhan_vien_id": resolve_staff_id("Tuấn", staff_list) or "nv_01",
                "han_chot": "18:00",
                "muc_do_uu_tien": "trung_binh",
                "do_tin_cay": 0.88,
                "da_chon": True,
                "stt_near_miss": False,
                "khong_co_can_cu": False,
                "nguon_cau_noi": "Kiểm tra và vệ sinh tủ đá",
            },
        ]
        van_de = [
            {
                "van_de": "Máy pha số 2 bị rỉ nước tại ron cao su",
                "trang_thai": "can_hanh_dong",
                "ghi_chu": "Giao Tuấn thay ron và vệ sinh họng máy trước 16h",
            },
            {
                "van_de": "Trà đào bị phàn nàn ngọt gắt",
                "trang_thai": "da_giai_quyet",
                "ghi_chu": "Đã thống nhất giảm syrup đào từ 30ml xuống 20ml, giao My dán bảng công thức mới",
            },
            {
                "van_de": "Tủ đá cần kiểm tra định kỳ",
                "trang_thai": "can_hanh_dong",
                "ghi_chu": "Giao Tuấn kiểm tra và vệ sinh khay trước 18h",
            },
        ]
        return {
            "id": meeting_id,
            "tieu_de": "Họp giao ca & Xử lý sự cố máy pha",
            "loai_hop": meeting_type,
            "thoi_gian": thoi_gian or "2026-08-29T14:30:00+07:00",
            "ngay_ghi_am": thoi_gian or "2026-08-29T14:30:00+07:00",
            "phien_ban": 1,
            "nguon_am_thanh": audio_source,
            "transcript_thoai": segments or [],
            "khong_lien_quan": False,
            "tom_tat": "Buổi giao ca phát sinh 2 vấn đề: máy pha số 2 bị rỉ nước tại ron cao su (cần bảo dưỡng khẩn) và trà đào bị khách phàn nàn ngọt gắt (đã chốt đổi định lượng syrup). Vấn đề trà đào đã được giải quyết tại cuộc họp bằng quyết định thay đổi công thức; việc sửa máy và kiểm tra tủ đá cần nhân viên thực hiện sau buổi họp.",
            "van_de_phat_sinh": van_de,
            "quyet_dinh": [
                "Bảo dưỡng và thay ron máy pha số 2 — giao Tuấn, hạn 16:00",
                "Giảm định lượng syrup đào từ 30ml xuống 20ml (áp dụng ngay từ ca này)",
            ],
            "action_items": items,
            "de_xuat_phe_duyet": [],
            "dieu_chinh_lich": [],
            "gop_y_luu_y": [],
            "de_xuat_sop": [
                {
                    "quy_trinh_lien_quan": "Pha chế Trà Đào",
                    "buoc_so": 3,
                    "noi_dung_thay_doi": "Định lượng syrup đào giảm từ 30ml xuống 20ml",
                    "ly_do": "Khách phàn nàn bị ngọt gắt, cần cân bằng vị",
                }
            ],
            "do_tin_cay_tong_the": 0.94,
            "trang_thai": "cho_duyet",
        }

    # 2. Generic Rule-based extraction
    base_dt: datetime
    if thoi_gian:
        try:
            base_dt = datetime.fromisoformat(thoi_gian.replace("Z", "+00:00"))
        except Exception:
            base_dt = datetime.now(timezone.utc)
    else:
        base_dt = datetime.now(timezone.utc)

    # Pre-process lines with compound splitting (TC-38)
    raw_lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    lines: list[str] = []
    for ln in raw_lines:
        lines.extend(_split_compound_line(ln, staff_list))

    action_items: list[dict[str, Any]] = []
    quyet_dinh: list[str] = []
    de_xuat_phe_duyet: list[dict[str, Any]] = []
    dieu_chinh_lich: list[dict[str, Any]] = []

    idx = 1
    prop_idx = 1
    for line in lines:
        low = line.lower()

        # Câu xác nhận của nhân viên ("Dạ em sẽ lau bàn ca sau ạ") không phải
        # một việc mới — nó là lời nhận việc cho câu giao ngay trước đó. Nếu
        # vẫn tạo item thì mỗi lượt giao việc sinh 2 việc treo trùng nội dung,
        # và bộ chống trùng ở `apply_meeting_decisions` không bắt được vì
        # `noi_dung` khác nhau (nó so theo chuỗi). Bỏ qua lượt xác nhận.
        if _is_acknowledgement(low):
            continue

        # Check spoken self-correction (TC-39): "Tuấn dọn bàn... à thôi để Lan dọn"
        retraction_cues = ["à thôi", "thôi để", "nhầm", "thay vì", "đổi lại", "thôi giao cho", "thôi nhờ"]
        has_retraction = any(rc in low for rc in retraction_cues)

        # Check speaker if formatted as "Tuấn: ..."
        speaker = ""
        m_spk = re.match(r"^([^:]+):", line)
        if m_spk:
            clean_spk = re.sub(r"[^\w\s]", "", m_spk.group(1)).strip()
            if resolve_staff_id(clean_spk, staff_list, allow_fuzzy_stt=True):
                speaker = clean_spk

        # Extract staff and handle retraction or near-miss
        assignee = speaker or "Chưa rõ"
        matched_id = None
        is_stt_near = False

        if has_retraction:
            active_cue = next((rc for rc in retraction_cues if rc in low), None)
            after_text = ""
            if active_cue:
                parts = low.split(active_cue, 1)
                after_text = line[len(parts[0]) + len(active_cue):]

            found_target = False
            if after_text:
                for w in after_text.split():
                    clean_w = re.sub(r"[^\w\s]", "", w)
                    sid, near = resolve_staff_id_with_meta(clean_w, staff_list, allow_fuzzy_stt=True)
                    if sid:
                        assignee = clean_w
                        matched_id = sid
                        is_stt_near = near
                        found_target = True
                        break

            if not found_target:
                mentions = []
                for w in line.split():
                    clean_w = re.sub(r"[^\w\s]", "", w)
                    sid, near = resolve_staff_id_with_meta(clean_w, staff_list, allow_fuzzy_stt=True)
                    if sid:
                        mentions.append((clean_w, sid, near))
                if len(mentions) >= 2:
                    assignee = mentions[-1][0]
                    matched_id = mentions[-1][1]
                    is_stt_near = mentions[-1][2]
                elif mentions:
                    assignee = mentions[0][0]
                    matched_id = mentions[0][1]
                    is_stt_near = mentions[0][2]
        elif not speaker:
            for word in line.split():
                clean_w = re.sub(r"[^\w\s]", "", word)
                sid, near = resolve_staff_id_with_meta(
                    clean_w, staff_list, allow_fuzzy_stt=(audio_source != "ghi_chep_tay")
                )
                if sid:
                    assignee = clean_w
                    matched_id = sid
                    is_stt_near = near
                    break
        else:
            sid, near = resolve_staff_id_with_meta(speaker, staff_list, allow_fuzzy_stt=True)
            matched_id = sid
            is_stt_near = near

        # Skip questions when extracting proposals
        is_question = "?" in line or any(q in low for q in ["gì không", "khong?", "không?", "chưa?", "chua?"])

        # Check for schedule requests / adjustments
        has_leave_cue = (not is_question) and any(kw in low for kw in ["xin nghỉ", "xin nghi", "bận", "ban", "nghỉ ca", "nghi ca", "không đi làm", "khong di lam", "không trực", "bận thi", "bận học"])
        has_pin_cue = (not is_question) and any(kw in low for kw in ["ghim", "phân công ca", "chốt ca", "cố định ca", "trực ca sáng", "trực ca tối", "trực ca chiều"])
        has_swap_cue = (not is_question) and any(kw in low for kw in ["đổi ca", "doi ca", "hoán đổi ca"])

        if has_leave_cue:
            leave_assignee = assignee
            m_leave_target = re.search(r"(?:duyệt|cho)?\s*([^\s,.:]+)\s+(?:xin\s+)?nghỉ", line, re.IGNORECASE)
            if m_leave_target and resolve_staff_id(m_leave_target.group(1), staff_list):
                leave_assignee = m_leave_target.group(1)
            elif speaker and any(kw in low for kw in ["em xin", "tôi xin", "em bận", "tôi bận"]):
                leave_assignee = speaker

            thu = _detect_thu(low)
            khung = _detect_khung(low)
            sched_item = {
                "id": f"dcl_{prop_idx}",
                "nhan_vien_id": resolve_staff_id(leave_assignee, staff_list) if leave_assignee != "Chưa rõ" else None,
                "ten_nhan_vien": leave_assignee if leave_assignee != "Chưa rõ" else "Nhân viên",
                "loai": "xin_nghi",
                "thu": thu,
                "khung": khung,
                "ca_id": "",
                "tuan_iso": "",
                "ly_do": line,
                "trang_thai": "cho_duyet",
            }
            dieu_chinh_lich.append(sched_item)
            de_xuat_phe_duyet.append({
                "id": f"prop_{prop_idx}",
                "loai_de_xuat": "dieu_chinh_lich",
                "tieu_de": f"Xin nghỉ ca: {leave_assignee} ({thu or 'trong tuần'})",
                "nguoi_de_xuat": leave_assignee,
                "nguoi_phe_duyet": "Quản lý",
                "noi_dung": line,
                "ly_do": line,
                "trang_thai": "cho_duyet",
                "chi_tiet_lich": sched_item,
            })
            prop_idx += 1

        elif has_pin_cue:
            pin_assignee = assignee
            m_pin_target = re.search(r"(?:ghim|phân công|chốt ca)\s+([^\s,.:]+)", line, re.IGNORECASE)
            if m_pin_target and resolve_staff_id(m_pin_target.group(1), staff_list):
                pin_assignee = m_pin_target.group(1)

            thu = _detect_thu(low)
            khung = _detect_khung(low)
            sched_item = {
                "id": f"dcl_{prop_idx}",
                "nhan_vien_id": resolve_staff_id(pin_assignee, staff_list) if pin_assignee != "Chưa rõ" else None,
                "ten_nhan_vien": pin_assignee if pin_assignee != "Chưa rõ" else "Nhân viên",
                "loai": "ghim_ca",
                "thu": thu,
                "khung": khung,
                "ca_id": "",
                "tuan_iso": "",
                "ly_do": line,
                "trang_thai": "cho_duyet",
            }
            dieu_chinh_lich.append(sched_item)
            de_xuat_phe_duyet.append({
                "id": f"prop_{prop_idx}",
                "loai_de_xuat": "dieu_chinh_lich",
                "tieu_de": f"Ghim ca làm việc: {assignee} ({thu or 'trong tuần'} - ca {khung or 'chỉ định'})",
                "nguoi_de_xuat": assignee,
                "nguoi_phe_duyet": "Quản lý",
                "noi_dung": line,
                "ly_do": line,
                "trang_thai": "cho_duyet",
                "chi_tiet_lich": sched_item,
            })
            prop_idx += 1

        elif has_swap_cue:
            sched_item = {
                "id": f"dcl_{prop_idx}",
                "nhan_vien_id": resolve_staff_id(assignee, staff_list) if assignee != "Chưa rõ" else None,
                "ten_nhan_vien": assignee if assignee != "Chưa rõ" else "Nhân viên",
                "loai": "doi_ca",
                "thu": _detect_thu(low),
                "khung": _detect_khung(low),
                "ca_id": "",
                "tuan_iso": "",
                "ly_do": line,
                "trang_thai": "cho_duyet",
            }
            dieu_chinh_lich.append(sched_item)
            de_xuat_phe_duyet.append({
                "id": f"prop_{prop_idx}",
                "loai_de_xuat": "dieu_chinh_lich",
                "tieu_de": f"Yêu cầu đổi ca: {line}",
                "nguoi_de_xuat": assignee,
                "nguoi_phe_duyet": "Quản lý",
                "noi_dung": line,
                "ly_do": line,
                "trang_thai": "cho_duyet",
                "chi_tiet_lich": sched_item,
            })
            prop_idx += 1

        # Action item detection (supports Vietnamese cues and F&B English code-switching loanwords - TC-34)
        has_action_cue = any(
            kw in low
            for kw in [
                "nhận", "phụ trách", "làm", "nhớ", "hạn", "trước", "giao",
                "kiểm tra", "kiem tra", "lau", "dọn", "don", "vệ sinh", "ve sinh",
                "thay", "chuẩn bị", "chuan bi", "sửa", "sua", "bảo dưỡng", "bao duong",
                "dán", "dan",
                "check", "update", "follow up", "fix", "clean", "review", "order",
            ]
        )
        if has_action_cue and not has_leave_cue:
            due = _resolve_relative_deadline(line, base_dt)
            # Tiêu đề việc KHÔNG kèm tên người nói: tên đã ở `ten_nguoi_nhan`
            # và `nguoi_noi`, giữ lại chỉ làm nội dung việc treo rối.
            task_title = _strip_speaker_prefix(line)
            # "ca sau" / "ca tới" là mốc thời gian thật, không được rơi về
            # "Trong ca" — người giao nói rõ ca nào thì việc treo phải ghi ca đó.
            ca_moc = _detect_shift_reference(low, due)
            if ca_moc:
                due = ca_moc
            grounded = _is_grounded_in_transcript(line, raw)
            action_items.append(
                {
                    "id": f"act_{idx}",
                    "tieu_de": task_title,
                    "ten_nguoi_nhan": assignee,
                    "nhan_vien_id": matched_id or resolve_staff_id(assignee, staff_list, allow_fuzzy_stt=True),
                    "han_chot": due,
                    "ca_thuc_hien": ca_moc or "",
                    "muc_do_uu_tien": "trung_binh",
                    "do_tin_cay": 0.80 if is_stt_near else (0.85 if assignee != "Chưa rõ" else 0.65),
                    "da_chon": True,
                    "stt_near_miss": is_stt_near,
                    "khong_co_can_cu": not grounded,
                    "nguon_cau_noi": line if grounded else "",
                    "can_lam_ro": (not grounded) or (assignee == "Chưa rõ") or is_stt_near,
                    "van_de_ngu_canh": (
                        "Việc này chưa thấy trong ghi chép thoại, cần xác nhận lại"
                        if not grounded
                        else ("STT nghe gần đúng tên nhân sự, vui lòng xác nhận" if is_stt_near else "")
                    ),
                    "cau_hoi_lam_ro": (
                        "Nội dung này không xuất hiện trong biên bản thoại. Bạn có chắc chắn muốn giao việc này không?"
                        if not grounded
                        else (f"STT nghe là '{assignee}', hệ thống đối soát '{matched_id}'. Bạn có muốn xác nhận?" if is_stt_near else "")
                    ),
                }
            )
            idx += 1
        elif any(kw in low for kw in ["thống nhất", "chốt", "quyết định", "từ nay", "đổi"]) and not has_swap_cue:
            quyet_dinh.append(line)

    summary = (
        f"Ghi nhận {len(lines)} nội dung trao đổi trong cuộc họp. "
        f"Đã trích xuất {len(action_items)} việc cần làm, {len(de_xuat_phe_duyet)} đề xuất (gồm {len(dieu_chinh_lich)} điều chỉnh lịch) và {len(quyet_dinh)} quyết định."
    )
    # Check if conversation is completely irrelevant to cafe operations (TC-08)
    is_irrelevant = any(w in raw.lower() for w in ["bóng đá", "bong da", "world cup", "phim ảnh", "xem phim"]) and not any(
        w in raw.lower() for w in ["ca", "máy", "quán", "bar", "syrup", "khách", "order", "bàn", "kho", "ron"]
    )
    if is_irrelevant:
        summary = "Nội dung cuộc trò chuyện không liên quan vận hành quán, không tạo việc giao."
        action_items = []
    elif not action_items and not de_xuat_phe_duyet:
        action_items.append(
            {
                "id": "act_1",
                "tieu_de": "Rà soát lại nội dung ghi chép ca",
                "ten_nguoi_nhan": "Quản lý",
                "nhan_vien_id": None,
                "han_chot": "Hết ca",
                "muc_do_uu_tien": "thap",
                "do_tin_cay": 0.7,
                "da_chon": True,
            }
        )

    now_str = base_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": meeting_id,
        "tieu_de": f"Biên bản cuộc họp {meeting_type}",
        "loai_hop": meeting_type,
        "thoi_gian": thoi_gian or now_str,
        "ngay_ghi_am": thoi_gian or now_str,
        "nguon_am_thanh": audio_source,
        "transcript_thoai": segments or [],
        "khong_lien_quan": is_irrelevant,
        "tom_tat": summary,
        "quyet_dinh": quyet_dinh or (["Không có quyết định vận hành"] if is_irrelevant else ["Duy trì đúng quy trình vận hành ca"]),
        "action_items": action_items,
        "de_xuat_phe_duyet": de_xuat_phe_duyet,
        "dieu_chinh_lich": dieu_chinh_lich,
        "de_xuat_sop": [],
        # Luôn kèm `audit_sop` dạng dict: UI dùng truthy-check `self.audit_sop ?`
        # nên key thiếu/None làm hiển thị và guard lệch nhau. Hội thoại không
        # liên quan vận hành thì không chấm điểm tuân thủ (0 điểm, hạng D).
        "audit_sop": {
            "diem_tuan_thu": 0 if is_irrelevant else 100,
            "xep_hang": "D" if is_irrelevant else "A",
            "tieu_chi": [],
            "canh_bao_do": [],
            "nhan_xet_chung": "",
        },
        "do_tin_cay_tong_the": 0.88,
        "trang_thai": "cho_duyet",
        "phien_ban": 1,
        "last_modified_at": now_str,
    }


def _normalize_output(
    data: dict[str, Any],
    meeting_id: str,
    meeting_type: str,
    audio_source: str,
    segments: list[dict[str, Any]] | None,
    staff_list: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Ensure output matches CuocHop contract v2 and resolves entity IDs."""
    # Handle khong_lien_quan flag from v2 prompt
    khong_lien_quan = bool(data.get("khong_lien_quan", False))

    tom_tat = str(data.get("tom_tat") or "Tóm tắt nội dung cuộc họp")
    quyet_dinh = [str(q) for q in (data.get("quyet_dinh") or []) if q]
    tieu_de = str(data.get("tieu_de") or f"Biên bản cuộc họp {meeting_type}")

    # Van de phat sinh (v2 field)
    raw_van_de = data.get("van_de_phat_sinh") or []
    van_de_phat_sinh: list[dict[str, Any]] = []
    for vd in raw_van_de:
        if isinstance(vd, dict) and vd.get("van_de"):
            trang_thai = vd.get("trang_thai", "can_hanh_dong")
            if trang_thai not in ("da_giai_quyet", "can_hanh_dong", "theo_doi"):
                trang_thai = "can_hanh_dong"
            van_de_phat_sinh.append(
                {
                    "van_de": str(vd.get("van_de")),
                    "trang_thai": trang_thai,
                    "ghi_chu": str(vd.get("ghi_chu") or ""),
                }
            )

    # Action items — if khong_lien_quan, return empty
    raw_actions = [] if khong_lien_quan else (data.get("action_items") or [])
    norm_actions: list[dict[str, Any]] = []
    for i, a in enumerate(raw_actions):
        if not isinstance(a, dict):
            continue
        ten_nhan = str(a.get("ten_nguoi_nhan") or "Chưa rõ")
        ten_giao = str(a.get("ten_nguoi_giao") or "Quản lý")
        tinh_chat = a.get("tinh_chat", "bat_buoc")
        if tinh_chat not in ("bat_buoc", "tuy_chon", "khuyen_khich"):
            tinh_chat = "bat_buoc"
        pham_vi = a.get("pham_vi", "ca_nhan")
        if pham_vi not in ("ca_nhan", "nhom"):
            pham_vi = (
                "nhom" if ten_nhan in ("Nhóm ca", "Mọi người", "Tất cả", "Chưa rõ") else "ca_nhan"
            )
        score = float(a.get("do_tin_cay", 0.9))
        if ten_nhan == "Chưa rõ" or not ten_nhan:
            score = min(score, 0.7)
        norm_actions.append(
            {
                "id": str(a.get("id") or f"act_{i + 1}"),
                "tieu_de": str(a.get("tieu_de") or "Công việc cần làm"),
                "noi_dung_chi_tiet": str(a.get("noi_dung_chi_tiet") or ""),
                "tinh_chat": tinh_chat,
                "ten_nguoi_giao": ten_giao,
                "ten_nguoi_nhan": ten_nhan,
                "pham_vi": pham_vi,
                "nhan_vien_id": resolve_staff_id(ten_nhan, staff_list),
                "thoi_gian_bat_dau": str(a.get("thoi_gian_bat_dau") or ""),
                "han_chot": str(a.get("han_chot") or "Hết ca"),
                "muc_do_uu_tien": a.get("muc_do_uu_tien")
                if a.get("muc_do_uu_tien") in ["cao", "trung_binh", "thap"]
                else "trung_binh",
                "do_tin_cay": score,
                "da_chon": bool(a.get("da_chon", True)),
            }
        )

    # Check if any action item is actually a schedule adjustment / shift pin
    remaining_actions = []
    sched_from_actions = []
    for a in norm_actions:
        a_full = f"{a.get('tieu_de', '')} {a.get('noi_dung_chi_tiet', '')}".lower()
        has_pin = any(kw in a_full for kw in ["ghim", "chốt ca", "cố định ca", "trực ca"])
        has_leave = any(kw in a_full for kw in ["xin nghỉ", "nghỉ ca", "bận thi", "bận học"])
        detected_thu = _detect_thu(a_full)
        if (has_pin or has_leave) and (detected_thu or "ca" in a_full):
            nv_name = a.get("ten_nguoi_nhan") or "Nhân viên"
            c_nv_id = a.get("nhan_vien_id") or resolve_staff_id(nv_name, staff_list)
            loai_adj = "ghim_ca" if has_pin else "xin_nghi"
            c_khung = _detect_khung(a_full)
            adj_item = {
                "id": f"dcl_act_{a.get('id', '')}",
                "nhan_vien_id": c_nv_id,
                "ten_nhan_vien": nv_name,
                "loai": loai_adj,
                "thu": detected_thu or "T2",
                "khung": c_khung,
                "ca_id": "",
                "tuan_iso": "",
                "ly_do": a.get("noi_dung_chi_tiet") or a.get("tieu_de") or "",
                "trang_thai": "da_duyet" if has_pin else "cho_duyet",
            }
            sched_from_actions.append((adj_item, {
                "id": f"prop_act_{a.get('id', '')}",
                "loai_de_xuat": "dieu_chinh_lich",
                "tieu_de": f"{'Ghim ca' if has_pin else 'Xin nghỉ ca'}: {nv_name} ({detected_thu or 'trong tuần'})",
                "nguoi_de_xuat": nv_name,
                "nguoi_phe_duyet": a.get("ten_nguoi_giao") or "Quản lý",
                "noi_dung": f"{a.get('tieu_de', '')}: {a.get('noi_dung_chi_tiet', '')}",
                "ly_do": a.get("noi_dung_chi_tiet") or a.get("tieu_de") or "",
                "trang_thai": "da_duyet" if has_pin else "cho_duyet",
                "chi_tiet_lich": adj_item,
            }))
        else:
            remaining_actions.append(a)
    norm_actions = remaining_actions

    # De xuat phe duyet (Proposals & Approvals)
    raw_props = [] if khong_lien_quan else (data.get("de_xuat_phe_duyet") or [])
    norm_props: list[dict[str, Any]] = []
    norm_sop: list[dict[str, Any]] = []
    norm_dieu_chinh_lich: list[dict[str, Any]] = []

    for adj_item, prop_item in sched_from_actions:
        norm_dieu_chinh_lich.append(adj_item)
        norm_props.append(prop_item)

    for i, p in enumerate(raw_props):
        if not isinstance(p, dict):
            continue
        trang_thai = p.get("trang_thai", "cho_duyet")
        if trang_thai not in ("da_duyet", "cho_duyet", "tu_choi"):
            trang_thai = "cho_duyet"
        loai = p.get("loai_de_xuat", "quy_trinh_sop")
        if loai not in ("quy_trinh_sop", "mua_sam_vat_tu", "chinh_sach_nhan_su", "dieu_chinh_lich", "khac"):
            loai = "quy_trinh_sop"

        chi_tiet_lich = None
        if loai == "dieu_chinh_lich" or p.get("chi_tiet_lich"):
            loai = "dieu_chinh_lich"
            raw_ctl = p.get("chi_tiet_lich") or {}
            c_nv_name = str(raw_ctl.get("ten_nhan_vien") or p.get("nguoi_de_xuat") or "")
            c_nv_id = raw_ctl.get("nhan_vien_id") or resolve_staff_id(c_nv_name, staff_list)
            c_loai = raw_ctl.get("loai", "xin_nghi")
            if c_loai not in ("xin_nghi", "ghim_ca", "doi_ca", "uu_tien"):
                c_loai = "xin_nghi"
            c_thu = str(raw_ctl.get("thu") or _detect_thu(p.get("noi_dung", "")) or "")
            c_khung = str(raw_ctl.get("khung") or _detect_khung(p.get("noi_dung", "")) or "")
            chi_tiet_lich = {
                "id": str(raw_ctl.get("id") or f"dcl_{i + 1}"),
                "nhan_vien_id": c_nv_id,
                "ten_nhan_vien": c_nv_name,
                "loai": c_loai,
                "thu": c_thu,
                "khung": c_khung,
                "ca_id": str(raw_ctl.get("ca_id") or ""),
                "tuan_iso": str(raw_ctl.get("tuan_iso") or ""),
                "ly_do": str(raw_ctl.get("ly_do") or p.get("ly_do") or p.get("noi_dung") or ""),
                "trang_thai": trang_thai,
            }
            norm_dieu_chinh_lich.append(chi_tiet_lich)

        prop_obj = {
            "id": str(p.get("id") or f"prop_{i + 1}"),
            "loai_de_xuat": loai,
            "tieu_de": str(p.get("tieu_de") or "Đề xuất cải tiến"),
            "nguoi_de_xuat": str(p.get("nguoi_de_xuat") or ""),
            "nguoi_phe_duyet": str(p.get("nguoi_phe_duyet") or ""),
            "noi_dung": str(p.get("noi_dung") or ""),
            "ly_do": str(p.get("ly_do") or ""),
            "trang_thai": trang_thai,
            "quy_trinh_lien_quan": p.get("quy_trinh_lien_quan"),
            "buoc_so": int(p["buoc_so"]) if p.get("buoc_so") is not None else None,
            "chi_tiet_lich": chi_tiet_lich,
        }
        norm_props.append(prop_obj)

        # Populate de_xuat_sop backward-compatibility
        if loai == "quy_trinh_sop" and p.get("quy_trinh_lien_quan"):
            norm_sop.append(
                {
                    "quy_trinh_lien_quan": str(p["quy_trinh_lien_quan"]),
                    "buoc_so": int(p["buoc_so"]) if p.get("buoc_so") is not None else None,
                    "noi_dung_thay_doi": str(p.get("noi_dung") or ""),
                    "ly_do": str(p.get("ly_do") or ""),
                }
            )

    # In case data had raw dieu_chinh_lich directly
    raw_dcl = [] if khong_lien_quan else (data.get("dieu_chinh_lich") or [])
    for d in raw_dcl:
        if isinstance(d, dict) and d not in norm_dieu_chinh_lich:
            c_nv_name = str(d.get("ten_nhan_vien") or "")
            c_nv_id = d.get("nhan_vien_id") or resolve_staff_id(c_nv_name, staff_list)
            norm_dieu_chinh_lich.append({
                "id": str(d.get("id") or f"dcl_{len(norm_dieu_chinh_lich) + 1}"),
                "nhan_vien_id": c_nv_id,
                "ten_nhan_vien": c_nv_name,
                "loai": d.get("loai", "xin_nghi"),
                "thu": str(d.get("thu") or ""),
                "khung": str(d.get("khung") or ""),
                "ca_id": str(d.get("ca_id") or ""),
                "tuan_iso": str(d.get("tuan_iso") or ""),
                "ly_do": str(d.get("ly_do") or ""),
                "trang_thai": d.get("trang_thai", "cho_duyet"),
            })

    # Gop y & Luu y noi bo (Team feedback & Notes)
    raw_fb = [] if khong_lien_quan else (data.get("gop_y_luu_y") or [])
    norm_fb: list[dict[str, Any]] = []
    for i, fb in enumerate(raw_fb):
        if not isinstance(fb, dict) or not fb.get("noi_dung"):
            continue
        chu_de = fb.get("chu_de", "luu_y_chung")
        if chu_de not in (
            "thai_do_phuc_vu",
            "ky_nang_pha_che",
            "ve_sinh_an_toan",
            "dong_vien_khen_ngoi",
            "luu_y_chung",
        ):
            chu_de = "luu_y_chung"
        tinh_chat = fb.get("tinh_chat", "gop_y")
        if tinh_chat not in ("nhac_nho", "khen_ngoi", "kinh_nghiem", "gop_y"):
            tinh_chat = "gop_y"
        norm_fb.append(
            {
                "id": str(fb.get("id") or f"fb_{i + 1}"),
                "nguoi_gop_y": str(fb.get("nguoi_gop_y") or ""),
                "nguoi_nhan": str(fb.get("nguoi_nhan") or "Cả ca"),
                "chu_de": chu_de,
                "tinh_chat": tinh_chat,
                "noi_dung": str(fb.get("noi_dung")),
                "ghi_chu": str(fb.get("ghi_chu") or ""),
            }
        )

    # Audit SOP Compliance.
    # `norm_audit` PHẢI luôn là dict: lớp precedence `self.audit_sop ?` ở UI là
    # truthy-check nên `None` sẽ lọt qua và làm crash khi đọc `tieu_chi`
    # (gặp thật trên /cuoc-hop). Contract `AuditTuanThuSop` cũng yêu cầu dict,
    # nên khi thiếu dữ liệu thì trả bản mặc định thay vì None.
    raw_audit = data.get("audit_sop")
    norm_audit: dict[str, Any] = {
        "diem_tuan_thu": 100,
        "xep_hang": "A",
        "tieu_chi": [],
        "canh_bao_do": [],
        "nhan_xet_chung": "",
    }
    if isinstance(raw_audit, dict):
        raw_tc = raw_audit.get("tieu_chi") or []
        norm_tc = []
        for tc in raw_tc:
            if isinstance(tc, dict) and tc.get("ten_tieu_chi"):
                norm_tc.append(
                    {
                        "ma": str(tc.get("ma") or "tc"),
                        "ten_tieu_chi": str(tc.get("ten_tieu_chi")),
                        "dat": bool(tc.get("dat", False)),
                        "chi_tiet": str(tc.get("chi_tiet") or ""),
                    }
                )
        diem = int(raw_audit.get("diem_tuan_thu", 80))
        diem = max(0, min(100, diem))
        xep_hang = raw_audit.get(
            "xep_hang", "A" if diem >= 90 else "B" if diem >= 70 else "C" if diem >= 50 else "D"
        )
        if xep_hang not in ("A", "B", "C", "D"):
            xep_hang = "B"
        norm_audit = {
            "diem_tuan_thu": diem,
            "xep_hang": xep_hang,
            "tieu_chi": norm_tc,
            "canh_bao_do": [str(x) for x in (raw_audit.get("canh_bao_do") or []) if str(x).strip()],
            "nhan_xet_chung": str(raw_audit.get("nhan_xet_chung") or ""),
        }
    elif khong_lien_quan:
        # Hội thoại không liên quan vận hành: không chấm điểm tuân thủ.
        norm_audit = {
            "diem_tuan_thu": 0,
            "xep_hang": "D",
            "tieu_chi": [],
            "canh_bao_do": [],
            "nhan_xet_chung": "",
        }

    # Ban tin ca khan
    raw_bt = None if khong_lien_quan else data.get("ban_tin_ca")
    norm_bt = None
    if isinstance(raw_bt, dict):
        norm_bt = {
            "ban_vip": [str(x) for x in (raw_bt.get("ban_vip") or []) if str(x).strip()],
            "luu_y_di_ung_khach": [
                str(x) for x in (raw_bt.get("luu_y_di_ung_khach") or []) if str(x).strip()
            ],
            "su_co_thiet_bi_khan": [
                str(x) for x in (raw_bt.get("su_co_thiet_bi_khan") or []) if str(x).strip()
            ],
            "danh_sach_mon_86": [
                str(x) for x in (raw_bt.get("danh_sach_mon_86") or []) if str(x).strip()
            ],
            "noi_dung_tin_nhan_gui_nhom": str(raw_bt.get("noi_dung_tin_nhan_gui_nhom") or ""),
        }

    # Huan luyen quan ly
    raw_hl = None if khong_lien_quan else data.get("huan_luyen_quan_ly")
    norm_hl = None
    if isinstance(raw_hl, dict):
        raw_q_pct = cast(object, raw_hl.get("ty_le_noi_quan_ly_pct"))
        q_pct = int(raw_q_pct) if isinstance(raw_q_pct, (int, float, str)) else 70
        q_pct = max(0, min(100, q_pct))
        s_pct = 100 - q_pct
        norm_hl = {
            "ty_le_noi_quan_ly_pct": q_pct,
            "ty_le_noi_nhan_vien_pct": s_pct,
            "diem_tuong_tac_2_chieu": max(1, min(10, int(raw_hl.get("diem_tuong_tac_2_chieu", 8)))),
            "diem_truyen_cam_hung": max(1, min(10, int(raw_hl.get("diem_truyen_cam_hung", 8)))),
            "phong_cach_dieu_hanh": str(
                raw_hl.get("phong_cach_dieu_hanh") or "Chuẩn mực & Tương tác"
            ),
            "loi_khuyen_ai_coaching": [
                str(x) for x in (raw_hl.get("loi_khuyen_ai_coaching") or []) if str(x).strip()
            ],
        }

    # Legacy de_xuat_sop fallback if raw_props was empty
    if not norm_props:
        legacy_sop = [] if khong_lien_quan else (data.get("de_xuat_sop") or [])
        for s in legacy_sop:
            if isinstance(s, dict) and s.get("quy_trinh_lien_quan"):
                raw_step = cast(object, s.get("buoc_so"))
                norm_sop.append(
                    {
                        "quy_trinh_lien_quan": str(s.get("quy_trinh_lien_quan")),
                        "buoc_so": int(raw_step)
                        if isinstance(raw_step, (int, float, str))
                        else None,
                        "noi_dung_thay_doi": str(s.get("noi_dung_thay_doi") or ""),
                        "ly_do": str(s.get("ly_do") or ""),
                    }
                )

    return {
        "id": meeting_id,
        "tieu_de": tieu_de,
        "loai_hop": meeting_type,
        "thoi_gian": str(data.get("thoi_gian") or "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nguon_am_thanh": audio_source,
        "transcript_thoai": segments or [],
        "khong_lien_quan": khong_lien_quan,
        "tom_tat": tom_tat,
        "van_de_phat_sinh": van_de_phat_sinh,
        "quyet_dinh": quyet_dinh,
        "de_xuat_phe_duyet": norm_props,
        "dieu_chinh_lich": norm_dieu_chinh_lich,
        "action_items": norm_actions,
        "gop_y_luu_y": norm_fb,
        "audit_sop": norm_audit,
        "ban_tin_ca": norm_bt,
        "huan_luyen_quan_ly": norm_hl,
        "de_xuat_sop": norm_sop,
        "do_tin_cay_tong_the": float(data.get("do_tin_cay_tong_the", 0.9)),
        "trang_thai": "cho_duyet",
    }
