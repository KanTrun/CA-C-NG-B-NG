"""FB-POLICY: deterministic moderation for AG-FBPAGE (ADR-002).

Mặc định TỰ XỬ LÝ. Chỉ chuyển người khi khớp đúng danh sách đóng Mục 4
(system prompt nhà hàng). Không mở rộng danh sách đó.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ca_contracts import FbPolicyAction, PolicyDecision

from ca_agents.guardrails import normalize_text

# Ngưỡng FAQ (khi đã qua Mục 4). Không dùng để “an toàn hóa” FAQ thường.
AUTO_THRESHOLD: dict[str, float] = {
    "chao_hoi": 0.90,
    "hoi_gio_dia_chi": 0.85,
    "hoi_menu_gia": 0.85,
}
AUTO_THRESHOLD_COMMENT = 0.85
COMMENT_SAFE_INTENTS = frozenset({
    "chao_hoi", "hoi_gio_dia_chi", "hoi_menu_gia", "hoi_khuyen_mai", "dat_ban",
    "hoi_thanh_toan",
})

LOW_CONFIDENCE_QUEUE = 0.60
REPEAT_ASK_LIMIT = 99  # không còn dùng để né tự xử lý

SLA_MINUTES_PRIORITY_REVIEW = 5
SLA_MINUTES_QUEUE_REVIEW = 10
SLA_MINUTES_COMMENT_QUEUE = 15
SLA_MINUTES_ESCALATE_OWNER = 15

# Không còn intent bắt buộc duyệt — Mục 3 trao toàn quyền trong dữ liệu/ngưỡng.
INTENTS_REQUIRING_APPROVAL: frozenset[str] = frozenset()

INTENT_COMPLAINT = "khieu_nai_gop_y"
INTENT_OTHER = "khac"

# Mục 4.1 — an toàn sức khỏe nghiêm trọng (không dấu, 1 bản)
HEALTH_KEYWORDS = (
    "ngo doc", "dau bung", "di ung", "di vat", "soc phan ve", "say thuoc",
)

# Mục 4.2 — đe dọa pháp lý / truyền thông / cơ quan
LEGAL_KEYWORDS = (
    "bao chi", "co quan chuc nang", "cong an", "so y te", "luat su",
    "van ban phap ly", "toi se kien", "kien quan", "hoa don do",
)

# Mục 4.5 — khách đòi người thật
ASK_HUMAN_KEYWORDS = (
    "gap chu", "gap quan ly", "noi chuyen voi quan ly", "gap nguoi that",
    "can gap nguoi", "chuyen cho quan ly",
)

# Mục 4.6 — giận dữ leo thang
HOSTILE_KEYWORDS = (
    "de doa", "doa giet", "danh chet", "suc vat", "thu dich", "doa danh", "dap quan",
)

# Mục 4.7 — ngoài vận hành nhà hàng
INTERNAL_SCOPE_KEYWORDS = (
    "hop dong", "nhan su noi bo", "luong nhan vien",
)

# Mục 4.3 — chỉ escalate khi tầng gọi set compensation_above_limit
FINANCIAL_KEYWORDS = ("hoan tien", "boi thuong")

# Hợp nhất nhóm chủ quán (health + legal + hỏi chủ) — test/compat
OWNER_ESCALATION_KEYWORDS = HEALTH_KEYWORDS + LEGAL_KEYWORDS + ASK_HUMAN_KEYWORDS

COMPLAINT_HEAVY_KEYWORDS = (
    "tay chay", "1 sao", "review xau", "boc phot", "that vong",
)

OUT_OF_SCOPE_KEYWORDS = (
    "chinh tri", "ton giao", "dang", "doi thu",
)

HOURS_EXCEPTION_KEYWORDS = (
    "dong som", "mo tre", "nghi hom nay", "nghi le", "doi gio mo",
    "thay doi gio", "book kin quan", "thue nguyen quan", "dong cua som",
)


@dataclass(frozen=True)
class PolicyContext:
    """Ngữ cảnh đưa vào decide() — tầng gọi tính các flag, policy không I/O."""

    source: str
    sensitive_post: bool = False
    repeat_ask_count: int = 0
    kb_has_fact: bool = True
    price_above_limit: bool = False
    recent_messages: tuple[str, ...] = ()
    # Default True: chỉ fb_moderation truyền giá trị THẬT từ KV/env. Giữ True để
    # caller cũ (và test) không đột nhiên rơi vào queue vì cờ chưa được truyền.
    reservation_auto_eligible: bool = True
    booking_system_down: bool = False
    compensation_above_limit: bool = False
    # ── Tín hiệu Jev (kế hoạch JEV v2 §4.2) ─────────────────────────────────
    # Jev là cảm biến xác suất, đầu ra là dữ liệu đầu vào không tin cậy cho
    # bảng quyết định tất định này. Mặc định False/0.0 = không leo thang thêm
    # (an toàn khi Jev chưa bật). Nguyên tắc đơn điệu: chỉ thêm, không bớt.
    jev_health_risk: float = 0.0
    jev_legal_threat: float = 0.0
    jev_hostility_score: float = 0.0
    jev_ask_human: float = 0.0
    jev_sarcasm: float = 0.0
    jev_ok: bool = False
    # Jev đã được bật cấu hình NHƯNG đánh giá thất bại (timeout/5xx/429/schema
    # lỗi). Theo kế hoạch §5: Jev lỗi → thoái lui về phía con người (hàng đợi),
    # KHÔNG im lặng fallback về "regex không thấy gì = an toàn" rồi tự trả lời.
    # Mặc định False = Jev tắt hoặc hoạt động bình thường (không kích hoạt).
    jev_failed: bool = False
    # Jev lỗi NHƯNG SensorChain đã dùng RegexSensor thay thế thành công.
    # Khi True: signals trong context đã là regex signals → KHÔNG fail-closed,
    # tiếp tục xử lý bình thường. Chỉ fail-closed khi jev_failed=True AND
    # jev_fallback_used=False (cả hai cảm biến đều thất bại — cực hiếm).
    jev_fallback_used: bool = False
    # KB có chương trình khuyến mãi đang chạy do chủ quán cấu hình (ADR-008:
    # dữ liệu thật mới được phép thông báo; rỗng = quán chưa nhập). Ưu đãi là
    # cam kết marketing — bot TỰ TRẢ LỜI khi có dữ liệu, KHÔNG có → QL duyệt
    # (golden queue_01/05/06: "KM phải QL duyệt"). Default True để layer gọi
    # bằng PolicyContext cũ không đổi hành vi; chỉ nào caller set False mới
    # hạ xuống queue — fail-closed nhưng không phá compat ngược.
    promotions_available: bool = True


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _escalation_text(message_text: str, ctx: PolicyContext) -> str:
    if not ctx.recent_messages:
        return message_text
    return " ".join((*ctx.recent_messages, message_text))


def _queue(
    reason: str,
    intent: str,
    confidence: float,
    role: Literal["quan_ly", "chu_quan"] = "quan_ly",
    sla: int = SLA_MINUTES_QUEUE_REVIEW,
    flagged: tuple[str, ...] = (),
) -> PolicyDecision:
    return PolicyDecision(
        action=FbPolicyAction.QUEUE_REVIEW,
        reason=reason,
        intent=intent,
        confidence=confidence,
        assigned_role=role,
        sla_minutes=sla,
        flagged_reasons=list(flagged),
    )


def _escalate(
    reason: str,
    intent: str,
    confidence: float,
    flagged: tuple[str, ...] = (),
) -> PolicyDecision:
    return PolicyDecision(
        action=FbPolicyAction.ESCALATE_OWNER,
        reason=reason,
        intent=intent,
        confidence=confidence,
        assigned_role="chu_quan",
        sla_minutes=SLA_MINUTES_ESCALATE_OWNER,
        flagged_reasons=list(flagged),
    )


def _priority(
    reason: str,
    intent: str,
    confidence: float,
) -> PolicyDecision:
    return PolicyDecision(
        action=FbPolicyAction.PRIORITY_REVIEW,
        reason=reason,
        intent=intent,
        confidence=confidence,
        assigned_role="quan_ly",
        sla_minutes=SLA_MINUTES_PRIORITY_REVIEW,
    )


def _auto(reason: str, intent: str, confidence: float) -> PolicyDecision:
    return PolicyDecision(
        action=FbPolicyAction.AUTO_SEND,
        reason=reason,
        intent=intent,
        confidence=confidence,
    )


def _ambiguous_flag(intent: str) -> tuple[str, ...]:
    if intent not in (INTENT_COMPLAINT, "yeu_cau_dac_biet"):
        return ("keyword_matched_ambiguous",)
    return ()


def decide(
    intent: str,
    confidence: float,
    message_text: str,
    ctx: PolicyContext,
) -> PolicyDecision:
    """Closed-list Mục 4 trước; mọi thứ khác → auto_send."""
    low = normalize_text(message_text)
    escalation_text = normalize_text(_escalation_text(message_text, ctx))

    # 4.1 An toàn sức khỏe
    if _has_any(escalation_text, HEALTH_KEYWORDS):
        return _escalate("health_safety", intent, confidence, _ambiguous_flag(intent))

    # 4.2 Đe dọa pháp lý / báo chí / cơ quan
    if _has_any(escalation_text, LEGAL_KEYWORDS):
        return _escalate("legal_threat", intent, confidence, _ambiguous_flag(intent))

    # 4.5 Khách đòi người thật
    if _has_any(escalation_text, ASK_HUMAN_KEYWORDS):
        return _escalate("customer_asked_human", intent, confidence, _ambiguous_flag(intent))

    # 4.6 Leo thang thù địch
    if _has_any(escalation_text, HOSTILE_KEYWORDS):
        return _priority("hostile_escalation", intent, confidence)

    # 4.3 Vượt ngưỡng đền bù (flag do tầng gọi tính theo số tiền)
    if _has_any(escalation_text, FINANCIAL_KEYWORDS) and ctx.compensation_above_limit:
        return _escalate("financial_above_limit", intent, confidence)

    # 4.7 Ngoài phạm vi vận hành (hợp đồng, nhân sự)
    if _has_any(escalation_text, INTERNAL_SCOPE_KEYWORDS):
        return _escalate("out_of_scope_internal", intent, confidence, _ambiguous_flag(intent))

    # 4.4 Hệ thống đặt bàn/POS không đọc được
    if intent == "dat_ban" and ctx.booking_system_down:
        return _queue("system_failure", intent, confidence, sla=SLA_MINUTES_QUEUE_REVIEW)

    # Đặt bàn khi chủ quán TẮT cờ đặt bàn tự động → chờ QL duyệt. Lý do rõ ràng
    # để quản lý hiểu vì sao hàng nằm trong hộp thư (trước đây bị hạ xuống queue
    # với reason chung chung `supervisor_downgrade`).
    if intent == "dat_ban" and not ctx.reservation_auto_eligible:
        return _queue("reservation_auto_disabled", intent, confidence)

    # Vượt ngưỡng giá menu cấu hình -> queue duyệt giá
    if intent == "hoi_menu_gia" and ctx.price_above_limit:
        return _queue("fact_not_in_kb_or_price_limit", intent, confidence)

    # Hỏi khuyến mãi: ưu đãi là cam kết marketing. Chỉ auto khi quán CÓ dữ
    # liệu promo do chủ quán nhập; chưa nhập ⇒ KHÔNG tự bịa chương trình
    # (ADR-008), đưa QL duyệt (golden queue_01/05/06).
    if intent == "hoi_khuyen_mai" and not ctx.promotions_available:
        return _queue(
            "promo_requires_approval", intent, confidence,
            flagged=("promo_not_configured",),
        )

    # Ngoài phạm vi xã hội — trả lịch sự, không bịa quan điểm
    if intent == INTENT_OTHER and _has_any(low, OUT_OF_SCOPE_KEYWORDS):
        return PolicyDecision(
            action=FbPolicyAction.BLOCK_POLITE,
            reason="out_of_scope",
            intent=intent,
            confidence=confidence,
        )

    # ── Tín hiệu Jev (kế hoạch JEV v2 §4.2) ─────────────────────────────────
    # Chỉ chạy khi Jev OK (jev_ok=True). Nguyên tắc đơn điệu: Jev chỉ *thêm*
    # leo thang, không bao giờ *gỡ* leo thang do regex đã quyết định ở trên.
    # Ngưỡng sức khỏe/pháp lý thấp (thà báo nhầm còn hơn bỏ sót).
    if ctx.jev_ok:
        if ctx.jev_health_risk >= 0.30 or ctx.jev_legal_threat >= 0.30:
            return _escalate("jev_health_or_legal", intent, confidence, ("jev_signal",))
        if (
            ctx.jev_hostility_score >= 1.5
            or ctx.jev_ask_human >= 0.50
            or ctx.jev_sarcasm >= 0.50
        ):
            return _priority("jev_hostile_or_ask_human", intent, confidence)

    # Jev được bật NHƯNG bị lỗi (timeout/5xx/429/schema) → kiểm tra fallback.
    # Nếu SensorChain đã dùng RegexSensor thay thế (fallback_used=True):
    #   → signals đã là regex signals, jev_ok=False nhưng xử lý bình thường.
    # Nếu KHÔNG có fallback (cả hai thất bại — cực hiếm):
    #   → fail-closed về phía con người (kế hoạch §5 gốc).
    if ctx.jev_failed and not ctx.jev_fallback_used:
        return _queue(
            "jev_failed_fail_closed", intent, confidence,
            role="quan_ly",
            sla=SLA_MINUTES_QUEUE_REVIEW,
            flagged=("jev_sensor_failed",),
        )

    return _auto("autonomous_default", intent, confidence)
