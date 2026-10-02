"""
AG-FBPAGE: Frontdesk Orchestrator for Customer Service Squad.

Orchestrates the Specialized Agent Squad:
- AG-FRONTDESK: Welcome, triage, operating hours, address, wifi.
- AG-BARISTA: Beverage consultation, taste profiling, natural pairings.
- AG-CONCIERGE: Complaint de-escalation (HEAR) and table reservations.
- AG-SUPERVISOR: Pre-flight safety gate against hallucinated promises and data leaks.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from ca_agents.ag_barista import consult_beverage
from ca_agents.ag_concierge import handle_complaint, handle_reservation
from ca_agents.ag_fbpage_memory import format_golden_cskh_prompt
from ca_agents.ag_supervisor import supervise_outgoing_response
from ca_agents.customer_memory import format_customer_greeting_context
from ca_agents.guardrails import check_input_guardrail
from ca_agents.llm import agent_mode, complete
from ca_agents.prompts.ag_fbpage.system_prompt import (
    build_fb_comment_system_prompt,
    build_fb_system_prompt,
)

CONFIDENCE_THRESHOLD_DEFAULT = 0.82

CUSTOMER_INTENTS = (
    "hoi_menu_gia",
    "hoi_gio_dia_chi",
    "hoi_khuyen_mai",
    "dat_ban",
    "hoi_thanh_toan",
    "khieu_nai_gop_y",
    "chao_hoi",
    "khac",
)

_COMPLAINT_WORDS = (
    "thất vọng",
    "that vong",
    "dở",
    "do ",
    "nguội",
    "nguoi",
    "chậm",
    "cham",
    "thái độ",
    "thai do",
    "phản ánh",
    "phan anh",
    "góp ý",
    "gop y",
    "khiếu nại",
    "khieu nai",
    "tệ",
    "te ",
    "đau bụng",
    "dau bung",
    "bực",
    "buc",
    "tẩy chay",
    "khó chịu",
    "kho chiu",
    "đợi",
    "doi ",
    "tính nhầm",
    "tinh nham",
    "sai đơn",
    "sai don",
)

_BOOKING_WORDS = (
    "đặt bàn",
    "dat ban",
    "giữ chỗ",
    "giu cho",
    "giữ bàn",
    "giu ban",
    "đặt chỗ",
    "dat cho",
    "book bàn",
    "book ban",
    "bàn 10 người",
    "bàn mấy người",
    "reserve",
    "booking",
    "đặt trước",
    "dat truoc",
    "ghép bàn",
    "tiệc",
    "tiec",
    "đặt tiệc",
    "còn bàn",
    "con ban",
    "hủy bàn",
    "huy ban",
    "hủy lịch",
    "huy lich",
    "có bàn",
    "co ban",
    "bàn trống",
    "ban trong",
    "lấy bàn",
    "lay ban",
    "có chỗ không",
    "co cho khong",
    "còn chỗ không",
    "con cho khong",
    "còn bàn không",
    "con ban khong",
    "có bàn không",
    "co ban khong",
    "bàn còn trống",
    "ban con trong",
    "còn trống",
    "con trong",
    "có chỗ",
    "co cho",
    "chỗ ngồi",
    "cho ngoi",
    "còn chỗ",
    "con cho",
)

_PAYMENT_WORDS = (
    "số tài khoản",
    "so tai khoan",
    "stk",
    "tài khoản",
    "tai khoan",
    "chuyển khoản",
    "chuyen khoan",
    "chuyển tiền",
    "chuyen tien",
    "đặt cọc",
    "dat coc",
    "cọc bàn",
    "coc ban",
    "cọc",
    "thanh toán",
    "thanh toan",
    "mã qr",
    "ma qr",
    "qr",
    "momo",
    "zalopay",
    "vnpay",
    "quẹt thẻ",
    "quet the",
    "cà thẻ",
    "trả trước",
    "tra truoc",
)

_PROMO_WORDS = (
    "khuyến mãi",
    "khuyen mai",
    "ưu đãi",
    "uu dai",
    "giảm giá",
    "giam gia",
    "voucher",
    "combo",
    "discount",
    "sale",
    "chương trình",
    "chuong trinh",
)

_INFO_WORDS = (
    "mở cửa",
    "mo cua",
    "mấy giờ",
    "may gio",
    "đóng cửa",
    "dong cua",
    "ở đâu",
    "o dau",
    "địa chỉ",
    "dia chi",
    "vị trí",
    "vi tri",
    "tìm đường",
    "tim duong",
    "quán ở",
    "quan o",
    "wifi",
    "pass wifi",
)

_CONSULT_WORDS = (
    "tư vấn",
    "tu van",
    "món gì ngon",
    "mon gi ngon",
    "chưa biết chọn gì",
    "không uống được",
    "khong uong duoc",
    "say cà phê",
    "say ca phe",
    "ít ngọt",
    "it ngọt",
    "bán chạy",
    "signature",
    "gợi ý",
    "goi y",
)

_MENU_WORDS = (
    "menu",
    "thực đơn",
    "thuc don",
    "giá",
    "gia",
    "bao nhiêu",
    "bao nhieu",
    "món gì",
    "mon gi",
    "uống gì",
    "uong gi",
    "cà phê",
    "ca phe",
    "cafe",
    "bạc xỉu",
    "bac xiu",
    "trà đào",
    "tra dao",
    "sinh tố",
    "nước ép",
)

_GREETING_WORDS = (
    "chào",
    "chao",
    "hi",
    "hello",
    "alo",
    "quán ơi",
    "quan oi",
    "ad ơi",
    "ad oi",
    "shop ơi",
)


@dataclass(frozen=True)
class FBMessageInput:
    """Standardized Facebook message input."""

    psid: str
    text: str
    message_id: str
    timestamp: float
    sender_name: str | None = None


@dataclass(frozen=True)
class FBMessageOutput:
    """Result of processing a Facebook message."""

    action: str
    response: str | None
    intent: str
    confidence: float
    emotion: str = "neutral"
    suggested_reply: str | None = None
    delegated_agent: str = "AG-FRONTDESK"
    reason: str | None = None
    error: str | None = None
    reservation_state: dict[str, Any] | None = None


def _norm(text: str) -> str:
    return text.lower().strip()


def _missing_verified_context(
    intent: str, emotion: str, context: dict[str, Any] | None
) -> str | None:
    """Return the public fact set required before a response may be auto-sent."""
    ctx = context or {}
    # `hoi_thanh_toan` KHÔNG bao giờ queue: thiếu dữ liệu thì reply trung thực
    # kèm hotline, không bịa STK (ADR-008). Giữ ở đây để mọi caller rõ ý định.
    if intent == "hoi_thanh_toan":
        return None
    if intent == "hoi_gio_dia_chi":
        profile = ctx.get("profile")
        if not isinstance(profile, dict) or not any(
            str(profile.get(field) or "").strip() for field in ("gio_mo_cua", "dia_chi", "hotline")
        ):
            return "profile"
    if intent == "hoi_khuyen_mai" and not isinstance(ctx.get("promotions"), list):
        return "promotions"
    if intent == "hoi_menu_gia":
        menu = ctx.get("menu")
        if not isinstance(menu, list) or not menu:
            return "menu"
    if emotion == "hesitant":
        menu = ctx.get("menu")
        if not isinstance(menu, list) or not menu:
            return "barista_review"
    return None


def _has_keyword(text: str, keyword: str) -> bool:
    if len(keyword.strip()) <= 3:
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None
    return keyword in text


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_has_keyword(text, keyword) for keyword in keywords)


_PHONE_REGEX = re.compile(r"(?:(?:\+84)|0)[35789]\d{8}")
_BOOKING_PATTERN_REGEX = re.compile(
    r"\b(?:bàn\s+(?:cho\s+)?\d+\s*(?:người|khách|chỗ|bạn|ng)|nhóm\s+\d+\s*(?:người|khách|bạn)|(?:đặt|giữ|book)\s+(?:1|một|cái)?\s*bàn)\b",
    re.IGNORECASE,
)

_CONFIRM_CANCEL_WORDS = (
    "đúng",
    "dung",
    "ok",
    "chốt",
    "chot",
    "xác nhận",
    "xac nhan",
    "hủy",
    "huy",
    "chuẩn",
    "chuan",
)

_NUMBER_WORDS = (
    "một",
    "mot",
    "hai",
    "ba",
    "bốn",
    "bon",
    "năm",
    "nam",
    "sáu",
    "sau",
    "bảy",
    "bay",
    "tám",
    "tam",
    "chín",
    "chin",
    "mười",
    "muoi",
)

_PARTY_WORDS = ("người", "nguoi", "nhóm", "nhom")


def _has_booking_details(t: str) -> bool:
    """True khi `t` đã chứa dữ liệu đặt bàn cụ thể (SĐT/giờ/số khách/xác nhận).

    Dùng để phân biệt "cho em xin số tài khoản để đặt bàn" (chưa có chi tiết →
    `hoi_thanh_toan`) với tin đặt bàn đang có dữ liệu (giữ `dat_ban`).
    """
    low_clean = t.replace(" ", "").replace(".", "").replace("-", "")
    if bool(_PHONE_REGEX.search(low_clean)):
        return True
    if bool(re.search(r"\d{1,2}\s*(h|:|giờ|g)", t)):
        return True
    if bool(re.search(r"\d+\s*(người|ng|khách|bạn|chỗ|pax)", t)):
        return True
    if any(k in t for k in _NUMBER_WORDS) and any(k in t for k in _PARTY_WORDS):
        return True
    # _has_any_keyword áp word-boundary cho từ ngắn ("ok"/"huy") để "bàn" trong
    # "đặt bàn" không bị nhầm là từ xác nhận.
    return _has_any_keyword(t, _CONFIRM_CANCEL_WORDS)


def detect_customer_psychology(
    text: str,
    reservation_state: dict[str, Any] | None = None,
) -> tuple[str, str, float]:
    """
    Analyze customer emotion and intent.
    Returns (emotion, intent, confidence).
    """
    t = _norm(text)

    # 1. Complaint (AG-CONCIERGE)
    if _has_any_keyword(t, _COMPLAINT_WORDS):
        return "complaining", "khieu_nai_gop_y", 0.95

    # 2. Table Booking (AG-CONCIERGE) — phân nhánh payment khi xin STK để đặt bàn
    if _has_any_keyword(t, _BOOKING_WORDS) or bool(_BOOKING_PATTERN_REGEX.search(t)):
        if _has_any_keyword(t, _PAYMENT_WORDS) and not _has_booking_details(t):
            return "inquiring", "hoi_thanh_toan", 0.90
        return "booking", "dat_ban", 0.92

    # 2b. Multi-turn continuation for ongoing table reservation
    res_step = (reservation_state or {}).get("dialog_step")
    if res_step in ("EXTRACTING", "CONFIRMING"):
        is_asking_menu = _has_any_keyword(t, _MENU_WORDS) or _has_any_keyword(t, _CONSULT_WORDS)
        if not is_asking_menu:
            low_clean = t.replace(" ", "").replace(".", "").replace("-", "")
            has_phone = bool(_PHONE_REGEX.search(low_clean))
            is_confirm = any(k in t for k in ("đúng", "dung", "ok", "chốt", "chot", "xác nhận", "xac nhan", "chuẩn", "chuan"))
            is_cancel = any(k in t for k in ("hủy", "huy", "không đến", "khong den", "bận", "ban"))
            has_time_or_date = bool(re.search(r"\d{1,2}\s*(?:h|:|giờ|g|pm|am)", t) or any(k in t for k in ("mai", "hôm nay", "tối", "trưa", "chiều", "rưỡi")))
            has_size = bool(re.search(r"\d+\s*(?:người|ng|khách|bạn|chỗ|pax)", t) or any(k in t for k in ("một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười")))
            if is_confirm or is_cancel or has_phone or has_time_or_date or has_size or len(t.split()) <= 5:
                return "booking", "dat_ban", 0.95

    # 3. Beverage Consultation (AG-BARISTA)
    if _has_any_keyword(t, _CONSULT_WORDS):
        return "hesitant", "hoi_menu_gia", 0.90

    # 4. Hỏi thanh toán / STK / cọc bàn — đặt SAU continuation 2b nên phiên đặt
    # bàn đang mở vẫn được tôn trọng; chỉ khi 2b không match mới rơi xuống đây.
    # _has_any_keyword xử lý word-boundary cho từ ngắn "qr"/"stk".
    if _has_any_keyword(t, _PAYMENT_WORDS):
        return "inquiring", "hoi_thanh_toan", 0.90

    # 5. Promotions (AG-FRONTDESK)
    if _has_any_keyword(t, _PROMO_WORDS):
        return "inquiring", "hoi_khuyen_mai", 0.88

    # 6. Operating Hours & Address (AG-FRONTDESK)
    if _has_any_keyword(t, _INFO_WORDS):
        return "rushed" if len(t) < 25 else "inquiring", "hoi_gio_dia_chi", 0.90

    # 7. Menu & Pricing (AG-FRONTDESK / BARISTA)
    if _has_any_keyword(t, _MENU_WORDS):
        return "inquiring", "hoi_menu_gia", 0.88

    # 8. Greeting (AG-FRONTDESK)
    # 0.92 ≥ AUTO_THRESHOLD chao_hoi (0.90) — trước đây 0.85 khiến mọi "hi/xin chào"
    # rơi xuống hộp thư QL dù đây là FAQ an toàn.
    if _has_any_keyword(t, _GREETING_WORDS):
        return "friendly", "chao_hoi", 0.92

    return "neutral", "khac", 0.50
_ADDRESS_KEYWORDS = (
    "dia chi", "địa chỉ", "nha o", "nhà ở", "so nha", "số nhà",
    "giao den", "giao đến", "ship den", "ship đến", "giao qua", "ship qua",
)


def classify_comment_action(text: str) -> dict[str, Any]:
    """Phân loại hành vi xử lý bình luận công khai theo Mục 3 của System Prompt:

    - Mục 3b: Chứa SĐT / địa chỉ riêng -> tự động ẩn ngay + trả lời công khai chuyển DM.
    - Mục 3b: Phàn nàn thông thường -> 1 câu xin lỗi ngắn công khai + chuyển DM xử lý chi tiết.
    - Mục 3b: Đặt bàn / đặt tiệc theo nhu cầu riêng -> chuyển DM tư vấn chu đáo.
    - Mục 3a: Thắc mắc chung / khen ngợi -> trả lời công khai trực tiếp.
    """
    cleaned = text.replace(" ", "").replace(".", "").replace("-", "")
    has_phone = bool(_PHONE_REGEX.search(cleaned))
    low = _norm(text)
    has_address = any(k in low for k in _ADDRESS_KEYWORDS)

    # 1. Chứa thông tin cá nhân (SĐT / địa chỉ) -> ẩn ngay tránh đối thủ cướp khách + chuyển DM
    if has_phone or has_address:
        return {
            "category": "hide_and_dm",
            "should_hide": True,
            "reply_public": "Dạ Nhịp Quán đã nhắn tin riêng hỗ trợ anh/chị rồi ạ! Mình kiểm tra hộp thư chờ giúp quán nhé ạ. ❤️",
            "reason": "customer_pii_protected",
        }

    # 2. Phàn nàn thông thường -> xin lỗi ngắn 1 câu, không đàm phán bồi thường công khai -> chuyển DM
    if _has_any_keyword(low, _COMPLAINT_WORDS):
        return {
            "category": "complaint_to_dm",
            "should_hide": False,
            "reply_public": "Dạ Nhịp Quán thật sự xin lỗi mình vì trải nghiệm chưa trọn vẹn ạ! Quán đã chủ động gửi tin nhắn riêng để hỗ trợ giải quyết ngay cho mình, anh/chị kiểm tra hộp thư giúp em nhé ạ.",
            "reason": "complaint_moved_to_dm",
        }

    # 3. Đặt bàn / đặt tiệc / hỏi giá riêng -> chuyển DM
    if _has_any_keyword(low, _BOOKING_WORDS):
        return {
            "category": "booking_to_dm",
            "should_hide": False,
            "reply_public": "Dạ Nhịp Quán rất vui được đón tiếp nhóm mình ạ! Em đã gửi tin nhắn riêng để lấy thông tin giữ bàn chu đáo, anh/chị check tin nhắn giúp em nha! 🎉",
            "reason": "booking_moved_to_dm",
        }

    # 4. Trả lời công khai trực tiếp (FAQ / menu / giờ mở cửa / khen ngợi)
    return {
        "category": "public_reply",
        "should_hide": False,
        "reply_public": None,
        "reason": "standard_public_inquiry",
    }


def build_human_response(
    intent: str,
    emotion: str,
    text: str,
    context: dict[str, Any] | None = None,
    customer_profile: dict[str, Any] | None = None,
    golden_examples: list[dict[str, Any]] | None = None,
) -> tuple[str, bool, str]:
    """
    Route task to specialized agent squad and generate response.
    Returns (reply_text, requires_human_approval, agent_name).
    """
    ctx = context or {}
    customer = customer_profile if isinstance(customer_profile, dict) else {}
    profile_raw = ctx.get("profile")
    profile: dict[str, Any] = profile_raw if isinstance(profile_raw, dict) else {}
    menu_raw = ctx.get("menu")
    menu: list[Any] = menu_raw if isinstance(menu_raw, list) else []
    promos_raw = ctx.get("promotions")
    promos: list[Any] = promos_raw if isinstance(promos_raw, list) else []

    # Ưu tiên áp dụng bài học mẫu Quản lý đã dạy nếu trùng ý định
    if golden_examples and intent in (
        "chao_hoi",
        "hoi_gio_dia_chi",
        "hoi_khuyen_mai",
        "hoi_menu_gia",
    ):
        for g in golden_examples:
            if g.get("intent") == intent and g.get("manager_reply"):
                return g["manager_reply"], False, "AG-FRONTDESK"

    # Case A: AG-CONCIERGE (Complaint)
    if intent == "khieu_nai_gop_y" or emotion == "complaining":
        ticket = handle_complaint(text)
        return ticket.suggested_reply, ticket.requires_human_approval, "AG-CONCIERGE"

    # Case B0: hỏi thanh toán / STK / cọc bàn — TRƯỚC Case B để câu
    # "cho em xin số tài khoản để đặt bàn" không bị state-machine nuốt mất.
    # Dữ liệu lấy 100% từ profile chủ quán cấu hình; thiếu thì nói thật + hotline,
    # KHÔNG bịa (ADR-008). Cố tình tránh cụm "tài khoản ngân hàng cá nhân" vì
    # trùng _FORBIDDEN_REGEX của supervisor.
    if intent == "hoi_thanh_toan":
        ngan_hang = str(profile.get("ngan_hang") or "").strip()
        stk = str(profile.get("stk_ngan_hang") or "").strip()
        chu_tk = str(profile.get("chu_tai_khoan") or "").strip()
        hotline = str(profile.get("hotline") or "").strip()
        chinh_sach = str(profile.get("chinh_sach_dat_ban") or "").strip()
        if not ngan_hang and not stk:
            if hotline:
                reply = (
                    "Dạ hiện quán chưa cập nhật thông tin chuyển khoản trên hệ thống ạ. "
                    f"Anh/chị liên hệ Hotline {hotline} để được hỗ trợ xác nhận nhé ạ!"
                )
            else:
                reply = (
                    "Dạ hiện quán chưa cập nhật thông tin chuyển khoản trên hệ thống ạ. "
                    "Anh/chị để lại SĐT, em xác nhận lại trong 10 phút ạ!"
                )
            return reply, False, "AG-FRONTDESK"
        parts = ["Dạ em gửi mình thông tin chuyển khoản để đặt bàn/giữ chỗ ạ:"]
        if ngan_hang and stk:
            parts.append(f"Thông tin chuyển khoản: Ngân hàng {ngan_hang} — Số tài khoản: {stk}")
        elif stk:
            parts.append(f"Thông tin chuyển khoản: Số tài khoản: {stk}")
        else:
            parts.append(f"Thông tin chuyển khoản: Ngân hàng {ngan_hang}")
        line = "\n".join(parts)
        if chu_tk:
            line += f" (Chủ tài khoản: {chu_tk})"
        if chinh_sach:
            line += f"\nChính sách đặt bàn: {chinh_sach}"
        return line, False, "AG-FRONTDESK"

    # Case B: AG-CONCIERGE (Booking)
    if intent == "dat_ban" or emotion == "booking":
        ticket = handle_reservation(
            text,
            store_name=str(profile.get("ten_quan") or "quán"),
            psid=str(customer.get("psid") or ""),
            session_state=customer.get("reservation_state"),
        )
        if isinstance(customer_profile, dict):
            customer_profile["reservation_state"] = ticket.extracted_data
        reply_b = ticket.suggested_reply
        # Tin đặt bàn CÓ kèm từ khóa thanh toán ("dat bàn 2 người, STK?") → gộp
        # thêm STK + chính sách vào reply đặt bàn. Làm ở đây vì đã có sẵn profile
        # mà không phải đụng state-machine của handle_reservation.
        if _has_any_keyword(_norm(text), _PAYMENT_WORDS):
            ngan_hang_b = str(profile.get("ngan_hang") or "").strip()
            stk_b = str(profile.get("stk_ngan_hang") or "").strip()
            if ngan_hang_b and stk_b:
                pay_block = (
                    f"Thông tin chuyển khoản: Ngân hàng {ngan_hang_b} — Số tài khoản: {stk_b}"
                )
                chu_b = str(profile.get("chu_tai_khoan") or "").strip()
                if chu_b:
                    pay_block += f" (Chủ tài khoản: {chu_b})"
                chinh_b = str(profile.get("chinh_sach_dat_ban") or "").strip()
                if chinh_b:
                    pay_block += f"\nChính sách đặt bàn: {chinh_b}"
                reply_b = f"{pay_block}\n\n{reply_b}"
        return reply_b, ticket.requires_human_approval, "AG-CONCIERGE"

    # Case C: AG-BARISTA (Taste consultation)
    if emotion == "hesitant" or any(
        k in _norm(text) for k in ("tư vấn", "không uống được", "say cà phê", "ít ngọt")
    ):
        reply, _ = consult_beverage(text, menu)
        return reply, False, "AG-BARISTA"

    # Case D: AG-FRONTDESK (Greeting, Info, Menu list, Promo)
    if intent == "chao_hoi":
        cust_name = customer.get("ten_khach")
        favs = customer.get("favorite_drinks", [])
        if cust_name and customer.get("is_vip_or_regular") and favs:
            return (
                f"Dạ Nhịp Quán chào anh/chị {cust_name} ạ! Hôm nay mình vẫn dùng món quen {favs[0]} đúng không ạ?",
                False,
                "AG-FRONTDESK",
            )
        if cust_name:
            return (
                f"Dạ Nhịp Quán chào anh/chị {cust_name} ạ! Em có thể gửi mình xem menu hoặc tư vấn đồ uống hôm nay nha!",
                False,
                "AG-FRONTDESK",
            )
        return (
            "Dạ Nhịp Quán xin chào mình ạ! Em có thể gửi mình xem menu hoặc tư vấn đồ uống hôm nay nha!",
            False,
            "AG-FRONTDESK",
        )

    if intent == "hoi_gio_dia_chi":
        # Chỉ ghép field có dữ liệu — không bao giờ để "None" lọt vào tin nhắn
        # khách (lỗ hổng văn bản khi profile thiếu field, review 2026-09-04).
        lines = []
        if profile.get("gio_mo_cua"):
            lines.append(f"Dạ {profile.get('ten_quan') or 'quán'} mở cửa từ {profile['gio_mo_cua']} ạ.")
        if profile.get("dia_chi"):
            lines.append(f"📍 Địa chỉ: {profile['dia_chi']}")
        if profile.get("hotline"):
            lines.append(f"📞 Hotline: {profile['hotline']}")
        if profile.get("wifi_ssid"):
            wifi_line = f"📶 Wifi: {profile['wifi_ssid']}"
            if profile.get("wifi_pass"):
                wifi_line += f" (Mật khẩu: {profile['wifi_pass']})"
            lines.append(wifi_line)
        if lines:
            lines.append("Mời mình ghé quán trải nghiệm không gian và thưởng thức cà phê nhé ạ!")
        else:
            lines.append(
                "Dạ hiện em chưa có thông tin giờ/địa chỉ trên hệ thống. "
                "Anh/chị để lại SĐT, em xác nhận lại trong 10 phút ạ!"
            )
        reply = "\n".join(lines)
        return reply, False, "AG-FRONTDESK"

    if intent == "hoi_menu_gia":
        items_str = "\n".join(
            [
                f"• {m['ten']}: {m.get('gia_formatted', str(m.get('gia', '')) + 'đ')}"
                for m in menu[:6]
            ]
        )
        reply = (
            f"Dạ em gửi mình menu nổi bật của quán nha:\n{items_str}\n\n"
            "Quán có đầy đủ cà phê truyền thống, trà trái cây và bánh ngọt. "
            "Mình muốn thử món nào cứ nhắn em tư vấn kỹ hơn nha!"
        )
        return reply, False, "AG-FRONTDESK"

    if intent == "hoi_khuyen_mai":
        if promos:
            promos_str = "\n".join([f"🎉 {p['tieu_de']}: {p['chi_tiet']}" for p in promos])
            reply = f"Dạ hôm nay quán đang có chương trình ưu đãi nè mình ơi:\n{promos_str}\n\nMời mình ghé quán nhận ưu đãi nha!"
        else:
            reply = "Dạ hiện tại quán đang phục vụ menu tiêu chuẩn với giá cực kỳ yêu thương mỗi ngày. Mời mình ghé quán thưởng thức nhé ạ!"
        return reply, False, "AG-FRONTDESK"

    reply = (
        "Dạ em nhận tin rồi ạ! Mình cần xem menu, giờ mở cửa, đặt bàn hay tư vấn món — "
        "cứ nhắn em xử lý ngay giúp mình nha."
    )
    return reply, False, "AG-FRONTDESK"


def build_public_context_summary(
    profile: dict[str, Any] | None,
    menu: list[Any] | None,
    promos: list[Any] | None,
) -> str:
    """Tóm tắt MỌI trường công khai của quán cho prompt LLM — hàm thuần, không I/O.

    Trước đây `draft_llm_reply` tự dựng `ctx_summary` thiếu STK/ngân hàng/chính
    sách đặt bàn/fanpage → LLM không có dữ liệu để trả lời câu hỏi thanh toán.
    Tách ra đây để test được trực tiếp và để FB pipeline dùng chung một nguồn.
    Trường trống → "(chưa cập nhật)" (không nhồi chuỗi rỗng/None vào prompt).
    """
    prof: dict[str, Any] = profile if isinstance(profile, dict) else {}
    menu_list: list[Any] = menu if isinstance(menu, list) else []
    promo_list: list[Any] = promos if isinstance(promos, list) else []

    def _pf(key: str) -> str:
        v = str(prof.get(key) or "").strip()
        return v if v else "(chưa cập nhật)"

    menu_items = [
        f"{m.get('ten', '')} ({m.get('gia_formatted') or (str(m.get('gia', '')) + 'đ')})"
        for m in menu_list
        if isinstance(m, dict) and m.get("ten")
    ]
    menu_str = ", ".join(menu_items) if menu_items else "Đang cập nhật"
    promo_str = ", ".join(
        str(p.get("tieu_de", ""))
        for p in promo_list
        if isinstance(p, dict) and p.get("tieu_de")
    ) or "Chưa có"

    wifi_ssid = str(prof.get("wifi_ssid") or "").strip()
    wifi_pass = str(prof.get("wifi_pass") or "").strip()
    wifi_str = "(chưa cập nhật)"
    if wifi_ssid:
        wifi_str = wifi_ssid + (f" (Pass: {wifi_pass})" if wifi_pass else "")

    # Gom ngân hàng/STK/chủ tài khoản thành một dòng — cùng cách diễn đạt với
    # reply template để LLM không tự bịa thêm chi tiết.
    ngan_hang = str(prof.get("ngan_hang") or "").strip()
    stk = str(prof.get("stk_ngan_hang") or "").strip()
    chu_tk = str(prof.get("chu_tai_khoan") or "").strip()
    if ngan_hang and stk:
        bank_str = f"Ngân hàng {ngan_hang} — Số tài khoản: {stk}"
    elif stk:
        bank_str = f"Số tài khoản: {stk}"
    elif ngan_hang:
        bank_str = f"Ngân hàng {ngan_hang}"
    else:
        bank_str = "(chưa cập nhật)"
    if bank_str != "(chưa cập nhật)" and chu_tk:
        bank_str += f" (Chủ tài khoản: {chu_tk})"

    dia_chi_ct = str(prof.get("dia_chi_chi_tiet") or "").strip() or "(chưa cập nhật)"
    maps_url = str(prof.get("google_maps_url") or "").strip() or "(chưa cập nhật)"

    ctx_summary = (
        f"Tên quán: {_pf('ten_quan')}\n"
        f"Slogan: {_pf('slogan')}\n"
        f"Địa chỉ: {_pf('dia_chi')}\n"
        f"Địa chỉ chi tiết: {dia_chi_ct}\n"
        f"Google Maps: {maps_url}\n"
        f"Giờ mở cửa: {_pf('gio_mo_cua')}\n"
        f"Giờ mở cửa chi tiết: {_pf('gio_mo_cua_chi_tiet')}\n"
        f"Hotline: {_pf('hotline')}\n"
        f"Hotline phụ: {_pf('hotline_phu')}\n"
        f"Email: {_pf('email')}\n"
        f"Website: {_pf('website')}\n"
        f"Fanpage: {_pf('fanpage_url')}\n"
        f"Khoảng giá: {_pf('khoang_gia')}\n"
        f"Tiện ích: {_pf('tien_ich')}\n"
        f"Wifi: {wifi_str}\n"
        f"Thông tin chuyển khoản: {bank_str}\n"
        f"Mô tả: {_pf('mo_ta')}\n"
        f"Chính sách đặt bàn: {_pf('chinh_sach_dat_ban')}\n"
        f"Menu & Giá: {menu_str}\n"
        f"Khuyến mãi: {promo_str}"
    )
    huong_dan = str(prof.get("huong_dan_agent") or "").strip()
    if huong_dan:
        ctx_summary += (
            "\n\nHƯỚNG DẪN RIÊNG CỦA CHỦ QUÁN (bắt buộc tuân thủ, ưu tiên cao nhất "
            "sau yêu cầu pháp luật/an toàn):\n" + huong_dan
        )
    return ctx_summary


async def draft_llm_reply(
    *,
    text: str,
    public_context: dict[str, Any] | None = None,
    customer_profile: dict[str, Any] | None = None,
    golden_examples: list[dict[str, Any]] | None = None,
    active_rules: list[dict[str, Any]] | None = None,
    is_comment: bool = False,
) -> str | None:
    """Sinh bản nháp trả lời bằng LLM (live mode) — dùng cho cả messenger & comment.

    Trả về None nếu LLM lỗi/timeout/empty — caller fallback về template.
    Bản nháp LUÔN qua supervise_outgoing_response trước khi dùng.
    """
    if agent_mode() != "live":
        return None
    try:
        profile = (public_context or {}).get("profile", {})
        menu = (public_context or {}).get("menu", [])
        promos = (public_context or {}).get("promotions", [])
        ctx_summary = build_public_context_summary(
            profile if isinstance(profile, dict) else {},
            menu if isinstance(menu, list) else [],
            promos if isinstance(promos, list) else [],
        )
        sys_prompt = (
            build_fb_comment_system_prompt(ctx_summary)
            if is_comment
            else build_fb_system_prompt(ctx_summary)
        )

        extra_instructions = []
        if customer_profile:
            cust_ctx = format_customer_greeting_context(customer_profile)
            if cust_ctx:
                extra_instructions.append(cust_ctx)
        if golden_examples:
            gold_ctx = format_golden_cskh_prompt(golden_examples)
            if gold_ctx:
                extra_instructions.append(gold_ctx)
        rule_texts = [str((rule.get("rule") or {}).get("text") or "").strip() for rule in active_rules or []]
        if rule_texts:
            extra_instructions.append("QUY TẮC ĐÃ ĐƯỢC CHỦ QUÁN DUYỆT:\n" + "\n".join(f"- {text}" for text in rule_texts if text))

        if extra_instructions:
            sys_prompt += "\n\n" + "\n\n".join(extra_instructions)

        llm_res = await asyncio.wait_for(
            asyncio.to_thread(
                complete,
                system=sys_prompt,
                user=text,
                task="text",
                json_mode=False,
                timeout_s=3.0,
            ),
            timeout=3.5,
        )
        if llm_res.ok and llm_res.text.strip():
            return llm_res.text.strip()
        return None
    except Exception:
        return None


async def process_fb_message(
    input_msg: FBMessageInput,
    *,
    confidence_threshold: float = CONFIDENCE_THRESHOLD_DEFAULT,
    auto_respond_enabled: bool = True,
    public_context: dict[str, Any] | None = None,
    customer_profile: dict[str, Any] | None = None,
    golden_examples: list[dict[str, Any]] | None = None,
    active_rules: list[dict[str, Any]] | None = None,
) -> FBMessageOutput:
    """
    Process a customer message through the 4-Agent Squad Architecture.
    """
    # 1. Guardrail filter
    guard = check_input_guardrail(input_msg.text)
    if not guard.is_safe:
        return FBMessageOutput(
            action="auto_respond" if auto_respond_enabled else "queue_to_inbox",
            response="Dạ em không thể hỗ trợ yêu cầu này được ạ. Mình cần em tư vấn thêm món gì trong menu không ạ?",
            intent="blocked_injection",
            confidence=1.0,
            emotion="suspicious",
            delegated_agent="AG-SUPERVISOR",
            reason=f"Guardrail triggered: {guard.reason}",
        )

    # 2. Emotion & Intent Detection
    cust_prof = dict(customer_profile or {})
    if input_msg.psid and not cust_prof.get("psid"):
        cust_prof["psid"] = input_msg.psid

    current_res_state = cust_prof.get("reservation_state")
    emotion, intent, confidence = detect_customer_psychology(
        guard.sanitized_text, reservation_state=current_res_state
    )

    # 3. Squad Routing (Frontdesk, Barista, Concierge)
    missing_context = _missing_verified_context(intent, emotion, public_context)
    reply_text, requires_approval, agent_name = build_human_response(
        intent,
        emotion,
        guard.sanitized_text,
        public_context,
        customer_profile=cust_prof,
        golden_examples=golden_examples,
    )
    # Thiếu dữ liệu: vẫn tự trả lời trung thực — không đẩy duyệt (Mục 5).
    if missing_context and "hiện chưa có thông tin" not in (reply_text or "").lower():
        reply_text = (
            "Dạ hiện em chưa có đủ thông tin này trên hệ thống. "
            "Anh/chị để lại SĐT, em xác nhận lại trong 10 phút — hoặc mình hỏi menu/đặt bàn em hỗ trợ ngay ạ!"
        )
        requires_approval = False

    # 4. Live LLM execution if enabled
    # Sinh bản nháp LLM cho mọi intent NGOẠI TRỪ dat_ban (để bảo vệ state machine & DB booking)
    llm_drafted = False
    if agent_mode() == "live" and auto_respond_enabled and intent != "dat_ban":
        llm_draft = await draft_llm_reply(
            text=guard.sanitized_text,
            public_context=public_context,
            customer_profile=cust_prof,
            golden_examples=golden_examples,
            active_rules=active_rules,
        )
        if llm_draft:
            reply_text = llm_draft
            llm_drafted = True

    # 5. AG-SUPERVISOR Pre-flight Safety Gate
    # `chinh_sach_dat_ban` do chủ quán nhập là dữ liệu thật có người chịu trách
    # nhiệm (ADR-008) → bot chép nguyên văn không phải "hứa hẹn bịa đặt".
    _prof_gate = (public_context or {}).get("profile")
    _owner_policy = (
        str(_prof_gate.get("chinh_sach_dat_ban") or "").strip()
        if isinstance(_prof_gate, dict)
        else ""
    )
    sup_check = supervise_outgoing_response(
        guard.sanitized_text, reply_text, owner_policy=_owner_policy
    )
    reply_text = sup_check.sanitized_response
    if not sup_check.is_approved:
        requires_approval = True

    updated_res_state = cust_prof.get("reservation_state")

    # 6. Action decision — tự gửi trừ khi supervisor/an toàn bắt buộc duyệt.
    if not requires_approval and auto_respond_enabled:
        return FBMessageOutput(
            action="auto_respond",
            response=reply_text,
            intent=intent,
            confidence=confidence,
            emotion=emotion,
            delegated_agent=agent_name,
            suggested_reply=reply_text,
            reason=f"Approved by AG-SUPERVISOR ({agent_name})",
            reservation_state=updated_res_state,
        )
    else:
        return FBMessageOutput(
            action="queue_to_inbox",
            response=None,
            intent=intent,
            confidence=confidence,
            emotion=emotion,
            delegated_agent=agent_name,
            suggested_reply=reply_text,
            reason=(
                f"missing_verified_context:{missing_context}"
                if missing_context
                else ("llm_draft_for_manager_review" if llm_drafted else "Queued for manager approval")
            ),
            reservation_state=updated_res_state,
        )


def parse_fb_webhook_message(entry: dict[str, Any]) -> FBMessageInput | None:
    """Parse incoming Facebook webhook entry to FBMessageInput."""
    try:
        messaging_list = entry.get("messaging") or []
        if not messaging_list:
            return None
        messaging = messaging_list[0]
        message = messaging.get("message", {})
        sender_id = (messaging.get("sender") or {}).get("id")

        if not sender_id or not message.get("text"):
            return None

        return FBMessageInput(
            psid=str(sender_id),
            text=str(message["text"]).strip(),
            message_id=str(message.get("mid", "")),
            timestamp=float(messaging.get("timestamp", 0)),
            sender_name=None,
        )
    except (KeyError, TypeError, IndexError, ValueError):
        return None


def classify_customer_intent(
    text: str, reservation_state: dict[str, Any] | None = None
) -> tuple[str, float]:
    """Helper alias for intent classification."""
    _, intent, conf = detect_customer_psychology(text, reservation_state=reservation_state)
    return intent, conf


def build_response_for_intent(
    intent: str, text: str, context: dict[str, Any] | None = None
) -> tuple[str, bool]:
    """Helper alias for response generation."""
    reply, req, _ = build_human_response(intent, "neutral", text, context)
    return reply, req


__all__ = [
    "FBMessageInput",
    "FBMessageOutput",
    "process_fb_message",
    "parse_fb_webhook_message",
    "detect_customer_psychology",
    "classify_customer_intent",
    "build_human_response",
    "build_response_for_intent",
    "build_public_context_summary",
    "_missing_verified_context",
    "CONFIDENCE_THRESHOLD_DEFAULT",
    "CUSTOMER_INTENTS",
]
