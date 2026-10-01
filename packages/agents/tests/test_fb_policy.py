# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Unit tests for fb_policy — every branch of the moderation matrix (plan §3.2).

Deterministic: no LLM, no I/O, no system clock (ADR-002).
Priority order is asserted explicitly: escalate_owner > priority_review > queue > auto.
"""

from __future__ import annotations

import pytest
from ca_agents.fb_policy import (
    COMMENT_SAFE_INTENTS,
    PolicyContext,
    decide,
)
from ca_contracts import FbPolicyAction


def ctx(**overrides: object) -> PolicyContext:
    base: dict[str, object] = {
        "source": "messenger",
        "sensitive_post": False,
        "repeat_ask_count": 0,
        "kb_has_fact": True,
        "price_above_limit": False,
        "recent_messages": (),
    }
    base.update(overrides)
    return PolicyContext(**base)  # type: ignore[arg-type]


# ── 1. Trao toàn quyền xử lý (Mục 3) ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("intent", "conf"),
    [
        ("chao_hoi", 0.90),
        ("hoi_gio_dia_chi", 0.85),
        ("hoi_menu_gia", 0.85),
        ("hoi_khuyen_mai", 0.80),
        ("dat_ban", 0.70),
        ("tu_van_mon", 0.75),
        ("yeu_cau_dac_biet", 0.80),
    ],
)
def test_autonomous_default_intents_auto_send(intent: str, conf: float) -> None:
    """Mọi intent hợp lệ thông thường đều tự xử lý trước (Mục 3) → auto_send."""
    d = decide(intent, conf, "xin chào quán ơi", ctx())
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


def test_dat_ban_large_group_auto_send() -> None:
    """Mục 3: Đặt bàn mọi số lượng khách miễn còn chỗ trống trong hệ thống."""
    d = decide("dat_ban", 0.95, "đặt bàn 20 người tiệc sinh nhật tối nay", ctx())
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


def test_complaint_light_auto_send() -> None:
    """Mục 3: Phàn nàn thông thường (chờ lâu, phục vụ chậm) → tự xử lý tặng ưu đãi <= 200k."""
    d = decide("khieu_nai_gop_y", 0.90, "hôm nay phục vụ hơi chậm quá ạ", ctx())
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


def test_fact_not_in_kb_still_auto_send() -> None:
    """Mục 2 & 5: Thiếu dữ liệu → trả lời thẳng thắn và hẹn 10 phút, vẫn tính là tự xử lý."""
    d = decide("hoi_gio_dia_chi", 0.95, "quán mở cửa mấy giờ", ctx(kb_has_fact=False))
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


def test_price_above_cap_queue() -> None:
    d = decide("hoi_menu_gia", 0.95, "combo tiệc giá bao nhiêu", ctx(price_above_limit=True))
    assert d.action == FbPolicyAction.QUEUE_REVIEW
    assert d.reason == "fact_not_in_kb_or_price_limit"


def test_price_cap_not_applied_to_other_intents() -> None:
    d = decide("chao_hoi", 0.95, "chào quán", ctx(price_above_limit=True))
    assert d.action == FbPolicyAction.AUTO_SEND


def test_repeat_ask_loop_still_auto_send() -> None:
    """Không dùng repeat ask để né tự xử lý."""
    d = decide("chao_hoi", 0.95, "hello", ctx(repeat_ask_count=3))
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


# ── 2. Danh sách bất khả kháng (Mục 4 — 7 trường hợp đóng) ────────────────────


# 4.1 An toàn sức khỏe nghiêm trọng
@pytest.mark.parametrize(
    "text",
    [
        "uống nước hôm qua về bị ngộ độc phải nhập viện",
        "món này có dị vật nguy hiểm bên trong",
        "khách bị dị ứng nặng sốc phản vệ",
        "uống xong đau bụng dữ dội",
    ],
)
def test_mục_4_1_health_safety_escalates(text: str) -> None:
    d = decide("khieu_nai_gop_y", 0.95, text, ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "health_safety"
    assert d.assigned_role == "chu_quan"
    assert d.sla_minutes == 15


# 4.2 Đe dọa pháp lý / báo chí / cơ quan chức năng / văn bản pháp lý
@pytest.mark.parametrize(
    "text",
    [
        "tôi sẽ kiện quán ra tòa",
        "tôi sẽ báo công an và sở y tế vào kiểm tra",
        "liên hệ báo chí để phản ánh vụ này",
        "cho xin hóa đơn đỏ công ty",
        "yêu cầu cung cấp văn bản pháp lý",
    ],
)
def test_mục_4_2_legal_threat_escalates(text: str) -> None:
    d = decide("chao_hoi", 0.90, text, ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "legal_threat"
    assert d.assigned_role == "chu_quan"
    assert d.sla_minutes == 15


# 4.3 Vượt ngưỡng tài chính (> 500.000đ)
def test_mục_4_3_financial_above_limit_escalates() -> None:
    d = decide(
        "khieu_nai_gop_y",
        0.90,
        "yêu cầu hoàn tiền đơn hàng này",
        ctx(compensation_above_limit=True),
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "financial_above_limit"
    assert d.assigned_role == "chu_quan"
    assert d.sla_minutes == 15


def test_mục_4_3_financial_within_limit_auto_send() -> None:
    d = decide(
        "khieu_nai_gop_y",
        0.90,
        "yêu cầu hoàn tiền đơn 100k",
        ctx(compensation_above_limit=False),
    )
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


# 4.4 Sự cố hệ thống đặt bàn / POS
def test_mục_4_4_system_failure_queues() -> None:
    d = decide("dat_ban", 0.95, "đặt bàn tối nay", ctx(booking_system_down=True))
    assert d.action == FbPolicyAction.QUEUE_REVIEW
    assert d.reason == "system_failure"
    assert d.assigned_role == "quan_ly"
    assert d.sla_minutes == 10


# 4.5 Khách chủ động đòi gặp người thật
@pytest.mark.parametrize(
    "text",
    [
        "muốn gặp chủ quán trực tiếp",
        "cho tôi nói chuyện với quản lý",
        "tôi cần gặp người thật",
        "chuyển cho quản lý đi",
    ],
)
def test_mục_4_5_customer_asked_human_escalates(text: str) -> None:
    d = decide("chao_hoi", 0.90, text, ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "customer_asked_human"
    assert d.assigned_role == "chu_quan"
    assert d.sla_minutes == 15


# 4.6 Khách giận dữ leo thang rõ rệt (đe dọa, thù địch)
@pytest.mark.parametrize(
    "text",
    [
        "tao sẽ đến đập quán",
        "đe dọa hành hung nhân viên",
        "đồ súc vật làm ăn lừa đảo",
    ],
)
def test_mục_4_6_hostile_escalation_priority(text: str) -> None:
    d = decide("khieu_nai_gop_y", 0.90, text, ctx())
    assert d.action == FbPolicyAction.PRIORITY_REVIEW
    assert d.reason == "hostile_escalation"
    assert d.assigned_role == "quan_ly"
    assert d.sla_minutes == 5


# 4.7 Ngoài phạm vi vận hành quán (hợp đồng đối tác, nhân sự nội bộ)
@pytest.mark.parametrize(
    "text",
    [
        "tôi muốn trao đổi về hợp đồng đối tác đầu tư",
        "cho hỏi chính sách nhân sự nội bộ và lương nhân viên quán thế nào",
    ],
)
def test_mục_4_7_internal_scope_escalates(text: str) -> None:
    d = decide("chao_hoi", 0.90, text, ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "out_of_scope_internal"
    assert d.assigned_role == "chu_quan"
    assert d.sla_minutes == 15


# Ngoài phạm vi xã hội (chính trị, tôn giáo) → chặn lịch sự
def test_out_of_scope_block_polite() -> None:
    d = decide("khac", 0.80, "quán ủng hộ chính trị đảng nào", ctx())
    assert d.action == FbPolicyAction.BLOCK_POLITE
    assert d.reason == "out_of_scope"


# ── 3. Evasion-resistance & Ngữ cảnh hội thoại ────────────────────────────────


def test_owner_escalation_from_recent_messages() -> None:
    """Keyword xuất hiện ở tin nhắn liền kề trong thread (plan §6.2d)."""
    d = decide(
        "khac",
        0.70,
        "hôm qua uống ở quán",
        ctx(recent_messages=("nước bị ngộ độc trong người quá",)),
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "health_safety"


@pytest.mark.parametrize(
    "text",
    [
        "b.á.o  ch í nào đến phỏng vấn",        # chèn dấu chấm + khoảng trắng
        "baoo chi phỏng vấn quán",               # gõ dính
        "CHO XIN HÓA ĐƠN ĐỎ",                    # uppercase
        "hóa đơn đỏ  ạ",                         # double space
        "muốn gặp chủ  quán",                    # double space between words
    ],
)
def test_keyword_match_survives_evasion_and_case(text: str) -> None:
    d = decide("chao_hoi", 0.90, text, ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER, f"evaded: {text}"


def test_no_accents_duplicate_keyword_list() -> None:
    """Các keyword an toàn phải là chuỗi không dấu, ascii chuẩn."""
    from ca_agents.fb_policy import OWNER_ESCALATION_KEYWORDS

    for kw in OWNER_ESCALATION_KEYWORDS:
        assert kw == kw.lower()
        assert kw.isascii(), f"keyword should be non-accented ascii: {kw}"


def test_ambiguous_keyword_match_flagged() -> None:
    """Keyword khớp nhưng intent là chào hỏi → vẫn escalate và gắn flag giám sát."""
    d = decide("chao_hoi", 0.90, "cho quán lên báo chí quảng bá đi ạ", ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert "keyword_matched_ambiguous" in d.flagged_reasons


def test_unambiguous_escalation_not_flagged_ambiguous() -> None:
    d = decide("khieu_nai_gop_y", 0.85, "bị ngộ độc quá", ctx())
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert "keyword_matched_ambiguous" not in d.flagged_reasons


# ── 10. Determinism & purity (ADR-002) ───────────────────────────────────────


def test_decide_is_pure_and_deterministic() -> None:
    """Same inputs → identical decision objects, no I/O, no clock."""
    a = decide("hoi_gio_dia_chi", 0.90, "quán mở mấy giờ", ctx())
    b = decide("hoi_gio_dia_chi", 0.90, "quán mở mấy giờ", ctx())
    assert a == b


def test_policy_context_defaults_immutable() -> None:
    from dataclasses import FrozenInstanceError

    c = ctx()
    with pytest.raises(FrozenInstanceError):
        c.source = "comment"  # type: ignore[misc]


def test_decision_contract_roundtrip() -> None:
    """PolicyDecision (from ca_contracts) validates per schema §3.4."""
    from ca_contracts import PolicyDecision as ContractDecision

    d = decide("chao_hoi", 0.95, "hi quán", ctx())
    contract = ContractDecision(
        action=d.action,
        reason=d.reason,
        intent=d.intent,
        confidence=d.confidence,
        assigned_role=d.assigned_role,
        sla_minutes=d.sla_minutes,
        flagged_reasons=list(d.flagged_reasons),
    )
    assert contract.action == "auto_send"
    assert 0.0 <= contract.confidence <= 1.0


# ── 11. Tín hiệu Jev (kế hoạch JEV v2 §4.2) ─────────────────────────────────


def test_jev_disabled_no_escalation() -> None:
    """Jev chưa bật (jev_ok=False) → không leo thang thêm, giữ auto."""
    d = decide("chao_hoi", 0.90, "hi quán", ctx())
    assert d.action == FbPolicyAction.AUTO_SEND


def test_jev_health_risk_escalates_owner() -> None:
    """Jev báo nguy cơ sức khỏe cao → ESCALATE_OWNER (ngưỡng thấp)."""
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=True, jev_health_risk=0.35),
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "jev_health_or_legal"


def test_jev_legal_threat_escalates_owner() -> None:
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=True, jev_legal_threat=0.40),
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER


def test_jev_hostile_escalates_priority() -> None:
    """Jev báo gay gắt cao → PRIORITY_REVIEW (Quản lý)."""
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=True, jev_hostility_score=2.0),
    )
    assert d.action == FbPolicyAction.PRIORITY_REVIEW
    assert d.reason == "jev_hostile_or_ask_human"


def test_jev_ask_human_escalates_priority() -> None:
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=True, jev_ask_human=0.6),
    )
    assert d.action == FbPolicyAction.PRIORITY_REVIEW


def test_jev_low_signal_no_escalation() -> None:
    """Jev OK nhưng tín hiệu thấp → không leo thang, giữ auto."""
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=True, jev_health_risk=0.05, jev_hostility_score=0.0),
    )
    assert d.action == FbPolicyAction.AUTO_SEND


def test_jev_monotone_regex_still_wins() -> None:
    """Regex trúng sức khỏe → ESCALATE_OWNER, bất kể Jev nói gì (đơn điệu)."""
    d = decide(
        "chao_hoi",
        0.90,
        "cả nhà tôi đau bụng",
        ctx(jev_ok=True, jev_health_risk=0.0),  # Jev nói không nguy hiểm
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "health_safety"


# ── 12. Jev lỗi → fail-closed về hàng đợi (kế hoạch §5) ────────────────────


def test_jev_failed_queues_not_auto() -> None:
    """Jev bật nhưng LỖI → QUEUE_REVIEW (người duyệt), KHÔNG im lặng tự trả lời."""
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=False, jev_failed=True),
    )
    assert d.action == FbPolicyAction.QUEUE_REVIEW
    assert "jev_sensor_failed" in d.flagged_reasons


def test_jev_off_not_failed_keeps_auto() -> None:
    """Jev TẮT (chưa cấu hình) → không coi là lỗi, giữ auto (hành vi cũ)."""
    d = decide(
        "chao_hoi",
        0.90,
        "hi quán",
        ctx(jev_ok=False, jev_failed=False),
    )
    assert d.action == FbPolicyAction.AUTO_SEND


def test_jev_failed_regex_still_wins() -> None:
    """Jev lỗi nhưng regex trúng sức khỏe → vẫn ESCALATE_OWNER (đơn điệu)."""
    d = decide(
        "chao_hoi",
        0.90,
        "cả nhà tôi đau bụng",
        ctx(jev_ok=False, jev_failed=True),
    )
    assert d.action == FbPolicyAction.ESCALATE_OWNER
    assert d.reason == "health_safety"

# ── Nhiem vu B/C: dat_ban khi tat auto-reservation + intent hoi_thanh_toan ──────


def test_dat_ban_auto_reservation_disabled_queues():
    """Cờ tự động đặt bàn TẮT → queue với lý do tường minh, không lặng lẽ."""
    d = decide(
        "dat_ban",
        0.92,
        "đặt bàn 4 người tối nay",
        ctx(reservation_auto_eligible=False),
    )
    assert d.action == FbPolicyAction.QUEUE_REVIEW
    assert d.reason == "reservation_auto_disabled"


def test_dat_ban_auto_reservation_enabled_still_auto():
    """Cờ BẬT → giữ hành vi cũ (state-machine tự chạy), không đẩy duyệt."""
    d = decide(
        "dat_ban",
        0.92,
        "đặt bàn 4 người tối nay",
        ctx(reservation_auto_eligible=True),
    )
    assert d.action == FbPolicyAction.AUTO_SEND


def test_hoi_thanh_toan_auto_send():
    """Hỏi STK/thanh toán (đã cấu hình qua profile) → tự trả lời, không cần duyệt."""
    d = decide(
        "hoi_thanh_toan",
        0.90,
        "cho em xin số tài khoản để đặt bàn",
        ctx(),
    )
    assert d.action == FbPolicyAction.AUTO_SEND
    assert d.reason == "autonomous_default"


def test_hoi_thanh_toan_comment_safe_intent():
    """Intent thanh toán nằm trong COMMENT_SAFE_INTENTS — comment an toàn được auto."""
    assert "hoi_thanh_toan" in COMMENT_SAFE_INTENTS

