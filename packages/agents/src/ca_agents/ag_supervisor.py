"""
AG-SUPERVISOR: Safety Gate & Quality Assurance Supervisor Agent for Nhịp Quán.

Specialized in:
- Pre-flight Gate: Intercepting hallucinations, unauthorized financial commitments (fake discounts), data leaks, and robot phrases.
- Post-flight Audit: Analyzing daily conversations, evaluating customer satisfaction (CSAT), and generating management summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ca_agents.guardrails import normalize_text

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone

    UTC = timezone.utc


@dataclass(frozen=True)
class SupervisionResult:
    is_approved: bool
    sanitized_response: str
    flagged_reason: str | None = None


# Patterns that are forbidden for customer-facing bot to output
_FORBIDDEN_PROMISES = [
    r"giảm\s*(giá\s*)?(50%|70%|100%|nửa\s*giá|\d{2,3}%)",
    r"miễn\s*phí\s*(toàn\s*bộ|hết|mọi\s*thứ)?",
    r"đền\s*bù\s*(tiền|triệu)",
    r"chuyển\s*khoản\s*trả\s*lại",
    r"tặng\s*voucher\s*\d{3,}",
]

_LEAK_PATTERNS = [
    r"mật\s*khẩu\s*của\s*(quản\s*lý|chủ\s*quán|hệ\s*thống)?",
    r"giá\s*vốn\s*của\s*món",
    r"công\s*thức\s*bí\s*mật",
    r"doanh\s*thu\s*ngày",
    r"tài\s*khoản\s*ngân\s*hàng\s*cá\s*nhân",
    # Mở rộng theo kế hoạch chatbot moderation §3.6
    r"lương\s*(nhân\s*viên|nv)",
    r"(số|so)\s*điện\s*thoại\s*(nội\s*bộ|chủ\s*quán|quản\s*lý)",
    r"chi\s*phí\s*(nguyên\s*liệu|vốn|mặt\s*bằng)",
    r"(mật\s*khẩu|mat\s*khau)\s*(wifi)?\s*(quản\s*lý|admin|root)",
]

_ROBOT_PHRASES = [
    r"tôi\s*là\s*(mô\s*hình\s*ngôn\s*ngữ|trợ\s*lý\s*ảo|ai|bot)",
    r"theo\s*cơ\s*sở\s*dữ\s*liệu",
    r"tôi\s*không\s*có\s*cảm\s*xúc",
]

_ROBOT_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"tôi\s*là\s*(mô\s*hình\s*ngôn\s*ngữ(\s*ai)?|trợ\s*lý\s*ảo|ai|bot)", re.IGNORECASE), "em"),
    (re.compile(r"theo\s*cơ\s*sở\s*dữ\s*liệu(\s*của\s*quán)?", re.IGNORECASE), "theo thông tin quán"),
    (re.compile(r"tôi\s*không\s*có\s*cảm\s*xúc", re.IGNORECASE), "em luôn sẵn sàng lắng nghe"),
    (re.compile(r"\btôi\s+có\s+thể\b", re.IGNORECASE), "em có thể"),
)

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"quên\s+(hết\s+)?(chỉ\s*dẫn|hướng\s*dẫn|quy\s*định|luật)",
    r"tiết\s*lộ\s*(system\s*prompt|lời\s*nhắc\s*hệ\s*thống|chỉ\s*thị\s*gốc)",
    r"đóng\s*vai\s*(dan|hacker|quản\s*trị\s*viên\s*tối\s*cao)",
]

_FORBIDDEN_REGEX = re.compile("|".join(_FORBIDDEN_PROMISES), re.IGNORECASE)
_LEAK_REGEX = re.compile("|".join(_LEAK_PATTERNS), re.IGNORECASE)
_ROBOT_REGEX = re.compile("|".join(_ROBOT_PHRASES), re.IGNORECASE)
_INJECTION_REGEX = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def clean_robotic_phrasing(text: str) -> tuple[str, bool]:
    """Clean robotic AI jargon and raw markdown asterisks while preserving natural Vietnamese phrasing."""
    cleaned = text
    modified = False
    for rx, repl in _ROBOT_REPLACEMENTS:
        if rx.search(cleaned):
            cleaned = rx.sub(repl, cleaned)
            modified = True

    # Clean markdown bold/italic asterisks (e.g. **tên món** -> tên món)
    if "**" in cleaned:
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        modified = True
    if re.search(r"(?<!\*)\*([^*\n]+)\*(?!\*)", cleaned):
        cleaned = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", cleaned)
        modified = True

    # Normalize markdown list bullets (* or -) to clean dots (•)
    if re.search(r"(?m)^\s*[\*\-]\s+", cleaned):
        cleaned = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", cleaned)
        modified = True

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, modified


def _owner_policy_allows(response: str, owner_policy: str | None) -> bool:
    """Cụm hứa tài chính có nằm trong CHÍNH SÁCH chủ quán tự cấu hình không?

    ADR-008: `chinh_sach_dat_ban` do chủ quán nhập là dữ liệu thật có người chịu
    trách nhiệm → bot chép nguyên văn chính sách đó không phải "hứa hẹn bịa đặt".
    So khớp bỏ dấu/hoa thường để chịu được cách gõ khác nhau.
    """
    if not owner_policy or not str(owner_policy).strip():
        return False
    m = _FORBIDDEN_REGEX.search(response or "")
    if not m:
        return False
    frag = normalize_text(m.group(0))
    return bool(frag) and frag in normalize_text(str(owner_policy))


def supervise_outgoing_response(
    customer_query: str,
    proposed_response: str,
    *,
    owner_policy: str | None = None,
) -> SupervisionResult:
    """
    Pre-flight safety check on AI-generated response before sending to customer or management.

    `owner_policy`: chính sách chủ quán đã cấu hình (vd `chinh_sach_dat_ban`) —
    cụm hứa tài chính trùng nguyên văn chính sách này được cho qua (ADR-008).
    """
    if not proposed_response or not proposed_response.strip():
        return SupervisionResult(
            is_approved=False,
            sanitized_response="Dạ em đã nhận được tin nhắn và sẽ phản hồi mình ngay ạ!",
            flagged_reason="empty_response",
        )

    # 0. Check prompt injection / jailbreak attempts in customer_query
    if customer_query and _INJECTION_REGEX.search(customer_query):
        return SupervisionResult(
            is_approved=False,
            sanitized_response="Dạ em chỉ hỗ trợ các thông tin về dịch vụ, menu và hoạt động của quán thôi ạ!",
            flagged_reason="prompt_injection_in_query",
        )

    # 1. Check for unauthorized financial promises or compensations
    if _FORBIDDEN_REGEX.search(proposed_response) and not _owner_policy_allows(
        proposed_response, owner_policy
    ):
        return SupervisionResult(
            is_approved=False,
            sanitized_response="Dạ em đã ghi nhận yêu cầu của mình và sẽ báo Quản lý quán liên hệ hỗ trợ trực tiếp cho mình nha!",
            flagged_reason="unauthorized_financial_promise",
        )

    # 2. Check for data leaks
    if _LEAK_REGEX.search(proposed_response):
        # Tránh false-positive khi bot từ chối hợp lệ hoặc nêu rõ chính sách không dùng tài khoản cá nhân
        is_safe_denial = bool(re.search(
            r"không\s*(nhận|dùng|sử\s*dụng|chuyển|chia\s*sẻ|cung\s*cấp).{0,30}tài\s*khoản\s*ngân\s*hàng\s*cá\s*nhân",
            proposed_response,
            re.IGNORECASE,
        ))
        if not is_safe_denial:
            return SupervisionResult(
                is_approved=False,
                sanitized_response="Dạ thông tin này thuộc nội bộ quán nên em không thể chia sẻ được ạ. Mình cần em hỗ trợ thêm gì về Menu không ạ?",
                flagged_reason="data_leak_detected",
            )

    # 3. Clean any robotic phrasing with contextual replacement
    cleaned_resp, was_cleaned = clean_robotic_phrasing(proposed_response)
    if was_cleaned or _ROBOT_REGEX.search(proposed_response):
        if _ROBOT_REGEX.search(cleaned_resp):
            cleaned_resp = _ROBOT_REGEX.sub("em", cleaned_resp)
        return SupervisionResult(
            is_approved=True,
            sanitized_response=cleaned_resp,
            flagged_reason="robotic_phrasing_cleaned",
        )

    return SupervisionResult(
        is_approved=True,
        sanitized_response=proposed_response,
        flagged_reason=None,
    )


# HEAR bắt buộc cho draft khiếu nại (kế hoạch §3.6): xin lỗi → ghi nhận → hỏi SĐT
# → cam kết Quản lý gọi lại. Thiếu bước nào thì báo rõ để tầng API hạ xuống queue.
_HEAR_STEPS: tuple[tuple[str, str], ...] = (
    ("xin_loi", r"xin\s*lỗi|xin\s*loi"),
    ("so_dien_thoai", r"số\s*điện\s*thoại|sđt|so\s*dien\s*thoai"),
    ("quan_ly", r"quản\s*lý|quan\s*ly"),
)

_HEAR_REGEXES = tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _HEAR_STEPS)


def check_hear_structure(response: str) -> tuple[bool, tuple[str, ...]]:
    """Return (ok, missing_steps). Used by API layer: complaint draft missing
    a HEAR step is downgraded to queue_review, never auto-sent."""
    missing = tuple(name for name, rx in _HEAR_REGEXES if not rx.search(response or ""))
    return (len(missing) == 0, missing)


def audit_conversations_summary(threads: list[dict[str, Any]]) -> dict[str, Any]:
    """Post-flight audit: Analyze conversation logs to compute quality metrics for management."""
    total = len(threads)
    if total == 0:
        return {
            "total_conversations": 0,
            "auto_replied_count": 0,
            "pending_approval_count": 0,
            "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
            "summary_text": "Hôm nay chưa có cuộc hội thoại nào từ khách hàng.",
        }

    auto_replied = 0
    pending_approval = 0
    complaints = 0
    reservations = 0
    positive_count = 0
    neutral_count = 0
    negative_count = 0

    for th in threads:
        if th.get("pending_approval"):
            pending_approval += 1
        else:
            auto_replied += 1

        intent = str(th.get("intent", ""))
        sent = str(th.get("sentiment") or "").lower()
        if intent == "khieu_nai_gop_y" or sent == "negative":
            complaints += 1 if intent == "khieu_nai_gop_y" else 0
            negative_count += 1
        elif intent == "dat_ban" or sent == "positive":
            reservations += 1 if intent == "dat_ban" else 0
            positive_count += 1
        else:
            neutral_count += 1

    summary_text = (
        f"Tổng cộng {total} cuộc hội thoại: {auto_replied} cuộc trả lời tự động, "
        f"{pending_approval} cuộc cần quản lý duyệt ({reservations} đặt bàn, {complaints} phản ánh)."
    )

    return {
        "total_conversations": total,
        "auto_replied_count": auto_replied,
        "pending_approval_count": pending_approval,
        "reservations_count": reservations,
        "complaints_count": complaints,
        "sentiment_breakdown": {
            "positive": positive_count,
            "neutral": neutral_count,
            "negative": negative_count,
        },
        "summary_text": summary_text,
    }


def run_nightly_cskh_reflection(
    threads: list[dict[str, Any]],
    store_id: str = "quan_01",
) -> dict[str, Any]:
    """Tự phê bình & đánh giá chất lượng CSKH hàng đêm (Nightly Reflection Agent).

    Phân tích toàn bộ hội thoại trong ngày:
    1. Chấm điểm CSAT dự đoán (1-10) và tỷ lệ tuân thủ quy chuẩn H.E.A.R.
    2. Phát hiện lỗ hổng tri thức (Unresolved Inquiries / Knowledge Gaps).
    3. Tự động sinh Đề xuất Cẩm nang (Playbook Rule Proposals) để gửi chủ quán duyệt.
    """
    total = len(threads)
    if total == 0:
        return {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "store_id": store_id,
            "total_conversations": 0,
            "csat_score": 10.0,
            "hear_compliance_rate": 100.0,
            "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
            "unresolved_inquiries": [],
            "learning_recommendations": ["Hôm nay không phát sinh hội thoại khách hàng nào cần rút kinh nghiệm."],
            "playbook_rule_proposals": [],
            "summary_text": "Hôm nay không có hội thoại phát sinh.",
        }

    positive_count = 0
    neutral_count = 0
    negative_count = 0
    complaints = 0
    hear_passed = 0

    # Danh mục các lỗ hổng tri thức thường gặp để gom cụm
    topic_patterns = [
        ("bai_do_xe", r"đậu\s*xe|đỗ\s*xe|bãi\s*xe|ô\s*tô|xe\s*hơi", "Chỗ đậu xe ô tô & bãi giữ xe"),
        ("ban_hat_cafe", r"mua\s*hạt|bán\s*hạt|hạt\s*cà\s*phê|pha\s*phin", "Bán hạt cà phê đóng gói mang về"),
        ("to_chuc_su_kien", r"sinh\s*nhật|sự\s*kiện|thuê\s*quán|bao\s*quán|họp\s*nhóm", "Chính sách thuê không gian & tổ chức sự kiện"),
        ("xuat_hoa_don", r"hóa\s*đơn\s*đỏ|vat|hóa\s*đơn\s*công\s*ty", "Xuất hóa đơn VAT cho doanh nghiệp"),
        ("thu_cung_pet", r"thú\s*cưng|chó|mèo|pet", "Chính sách tiếp đón thú cưng (Pet-friendly)"),
        ("giao_hang_ship", r"ship|giao\s*hàng|đặt\s*mang\s*về|shopee\s*food|grab", "Chính sách giao hàng & đối tác giao vận"),
        ("chinh_sach_tich_diem", r"tích\s*điểm|thành\s*viên|ưu\s*đãi\s*sinh\s*nhật|thẻ\s*thành\s*viên", "Chính sách thành viên & tích điểm"),
    ]
    unresolved_map: dict[str, dict[str, Any]] = {}

    for th in threads:
        # Lấy nội dung tin nhắn của khách
        msgs = th.get("messages") or []
        cust_texts = [m.get("text", "") for m in msgs if m.get("from_customer")]
        combined_cust = " ".join(cust_texts).lower()

        # Lấy câu phản hồi của bot/quán
        replies = th.get("replies") or []
        last_reply = replies[-1].get("text", "") if replies else str(th.get("suggested_reply") or "")

        # 1. Phân loại cảm xúc & CSAT
        is_complaint = th.get("intent") == "khieu_nai_gop_y" or any(
            k in combined_cust for k in ("thất vọng", "dở", "tệ", "chậm", "thái độ", "đau bụng", "bực")
        )

        if is_complaint:
            complaints += 1
            negative_count += 1
            # Đánh giá chuẩn HEAR
            ok_hear, _ = check_hear_structure(last_reply)
            if ok_hear:
                hear_passed += 1
        elif any(k in combined_cust for k in ("cảm ơn", "cam on", "tuyệt", "ngon", "ok", "dạ vâng")):
            positive_count += 1
        else:
            neutral_count += 1

        # 2. Quét lỗ hổng tri thức (chưa biết thông tin / trả lời chung chung)
        is_fallback_reply = any(
            k in last_reply.lower() for k in ("chưa có thông tin", "hỏi lại quản lý", "đợi em một xíu", "kiểm tra lại")
        )
        for slug, pattern, title in topic_patterns:
            if re.search(pattern, combined_cust, re.IGNORECASE):
                if is_fallback_reply or th.get("pending_approval"):
                    entry = unresolved_map.setdefault(slug, {
                        "slug": slug,
                        "title": title,
                        "count": 0,
                        "sample_questions": [],
                    })
                    entry["count"] += 1
                    # Tìm câu hỏi thực tế của khách hàng khớp với pattern thay vì luôn lấy câu đầu tiên
                    matching_texts = [
                        t.strip() for t in cust_texts if re.search(pattern, t, re.IGNORECASE) and t.strip()
                    ]
                    if not matching_texts and cust_texts:
                        matching_texts = [cust_texts[-1].strip()]
                    for q in matching_texts:
                        if len(entry["sample_questions"]) < 3 and q not in entry["sample_questions"]:
                            entry["sample_questions"].append(q)

    # 3. Tính điểm CSAT & Tỷ lệ HEAR
    hear_rate = (hear_passed / complaints * 100.0) if complaints > 0 else 100.0
    # Công thức CSAT dự đoán: (Positive * 10 + Neutral * 8 + Negative * (4 nếu đủ HEAR, 2 nếu thiếu HEAR)) / Total
    total_score = (
        positive_count * 10.0
        + neutral_count * 8.0
        + (hear_passed * 5.0 + (complaints - hear_passed) * 2.0)
    )
    csat_score = round(min(10.0, max(1.0, total_score / total)), 1)

    # 4. Tạo các đề xuất Cẩm nang quán (Playbook Rule Proposals)
    proposals = []
    recommendations = []

    if complaints > 0 and hear_rate < 100.0:
        recommendations.append(
            f"Phát hiện {complaints - hear_passed} ca khiếu nại chưa áp dụng đủ 3 bước H.E.A.R (Xin lỗi - Lấy SĐT - Quản lý gọi lại). Cần kiểm soát chặt câu từ trước khi gửi."
        )
    elif complaints > 0 and hear_rate == 100.0:
        recommendations.append(
            f"Tất cả {complaints} ca khiếu nại trong ngày đều được xử lý chuẩn mực theo quy trình H.E.A.R."
        )

    for slug, item in unresolved_map.items():
        count = item["count"]
        title = item["title"]
        recommendations.append(
            f"Có {count} khách hỏi về \"{title}\" nhưng quán chưa có câu trả lời tự động chuẩn xác."
        )
        proposals.append({
            "proposal_id": f"prop_{slug}_{datetime.now(UTC).strftime('%Y%m%d')}",
            "title": f"Bổ sung quy định: {title}",
            "topic": title,
            "frequency": count,
            "sample_questions": item["sample_questions"],
            "suggested_rule": f"Khi khách hỏi về {title.lower()}, giải thích rõ chính sách của quán và hỗ trợ chu đáo.",
            "status": "cho_chu_duyet",
        })

    if not recommendations:
        recommendations.append("Đội ngũ CSKH và bot hôm nay hoạt động xuất sắc, không ghi nhận bất thường.")

    summary_text = (
        f"Đánh giá CSAT: {csat_score}/10.0 | Tỷ lệ tuân thủ HEAR: {hear_rate:.0f}%. "
        f"Ghi nhận {len(proposals)} chủ đề khách quan tâm cần cập nhật vào Cẩm nang quán."
    )

    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "store_id": store_id,
        "total_conversations": total,
        "csat_score": csat_score,
        "hear_compliance_rate": round(hear_rate, 1),
        "sentiment_breakdown": {
            "positive": positive_count,
            "neutral": neutral_count,
            "negative": negative_count,
        },
        "unresolved_inquiries": list(unresolved_map.values()),
        "learning_recommendations": recommendations,
        "playbook_rule_proposals": proposals,
        "summary_text": summary_text,
    }


# ── Incoming Query Supervision (SensorChain: JEV + RegexSensor fallback) ────

@dataclass(frozen=True)
class IncomingSupervisionResult:
    """Kết quả kiểm tra query đầu vào qua SensorChain.

    `is_safe=False` → tầng gọi phải chặn hoặc leo thang, không tự trả lời.
    `fallback_used=True` → JEV lỗi nhưng RegexSensor đã thay thế (vẫn có giá trị).
    `source` → "jev" | "regex" | "regex_fallback" | "both" | "none" (cực hiếm).
    """

    is_safe: bool
    flagged_reason: str | None = None
    source: str = "none"
    fallback_used: bool = False


def supervise_incoming_query(
    text: str,
    sensor_chain: Any | None = None,
) -> IncomingSupervisionResult:
    """Kiểm tra query khách/nhân viên qua SensorChain trước khi xử lý.

    Dùng SensorChain (JEV ưu tiên → RegexSensor fallback) để phát hiện:
    - Rủi ro sức khỏe (nguy_co_suc_khoe ≥ 0.30)
    - Prompt injection / jailbreak (co_gang_ghi_de_chi_dan ≥ 0.50)
    - Đe dọa pháp lý (de_doa_phap_ly_truyen_thong ≥ 0.30)

    Nguyên tắc đơn điệu: chỉ *thêm* leo thang, không bao giờ *gỡ* leo thang.
    Nếu SensorChain trả `both_failed=True` (cực hiếm) → fail-safe, coi là
    không an toàn (là_safe=False) để tránh tự xử lý khi không có signal nào.

    Args:
        text: Nội dung cần kiểm tra (chưa ẩn danh hóa — hàm này không gửi mạng).
        sensor_chain: SensorChain đã khởi tạo. Nếu None → tạo mới chỉ Regex.
    """
    # Import lazy để tránh circular (ag_supervisor không phụ thuộc sensors khi chưa cần).
    from ca_agents.sensors.fb_questions import FB_QUESTIONS
    from ca_agents.sensors.sensor_chain import SensorChain

    chain = sensor_chain
    if chain is None:
        chain = SensorChain()  # chỉ Regex (JEV chưa bật)

    result = chain.evaluate(text, "supervisor_incoming", FB_QUESTIONS)

    # Cả hai thất bại → fail-safe: không tự xử lý.
    if result.both_failed:
        return IncomingSupervisionResult(
            is_safe=False,
            flagged_reason="sensor_chain_failed",
            source="none",
            fallback_used=True,
        )

    signals = result.signals
    health = signals.get("nguy_co_suc_khoe")
    legal = signals.get("de_doa_phap_ly_truyen_thong")
    injection = signals.get("co_gang_ghi_de_chi_dan")

    # Ngưỡng thấp cho health/legal (thà báo nhầm còn hơn bỏ sót).
    if health is not None and float(health.value) >= 0.30:
        return IncomingSupervisionResult(
            is_safe=False,
            flagged_reason="health_risk_detected",
            source=result.source,
            fallback_used=result.fallback_used,
        )
    if legal is not None and float(legal.value) >= 0.30:
        return IncomingSupervisionResult(
            is_safe=False,
            flagged_reason="legal_threat_detected",
            source=result.source,
            fallback_used=result.fallback_used,
        )
    # Injection: ngưỡng 0.50 (bảo thủ hơn để tránh false positive).
    if injection is not None and float(injection.value) >= 0.50:
        return IncomingSupervisionResult(
            is_safe=False,
            flagged_reason="injection_attempt_detected",
            source=result.source,
            fallback_used=result.fallback_used,
        )

    return IncomingSupervisionResult(
        is_safe=True,
        flagged_reason=f"sensor_ok_source={result.source}" if result.fallback_used else None,
        source=result.source,
        fallback_used=result.fallback_used,
    )


__all__ = [
    "SupervisionResult",
    "IncomingSupervisionResult",
    "supervise_outgoing_response",
    "supervise_incoming_query",
    "check_hear_structure",
    "audit_conversations_summary",
    "run_nightly_cskh_reflection",
]

