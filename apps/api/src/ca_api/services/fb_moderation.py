"""FB moderation service — cầu nối webhook ↔ policy engine ↔ review queue.

Tầng API duy nhất được ghi DB (agent không ghi DB — ADR-002). Mọi tin nhắn
Messenger inbound đi qua đây trước khi được trả lời tự động hay đẩy queue.

Luồng (kế hoạch §3.3 + bản vá §6.2):
    L0 idempotency/echo  — ở webhook handler (channels.py)
    L1 input guardrail   (ca_agents.guardrails)
    L2 rate limit        (ca_agents.fb_rate_limiter) + blacklist DB
    L3 intent classify   (ag_fbpage.detect_customer_psychology — deterministic)
    L4 policy decide     (ca_agents.fb_policy)  ← tất định, không LLM
    L5 supervisor        (ca_agents.ag_supervisor) — hạ auto → queue nếu flag
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import timedelta
from typing import Any

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc

from ca_agents.ag_fbpage import build_human_response, detect_customer_psychology
from ca_agents.ag_supervisor import supervise_outgoing_response
from ca_agents.fb_policy import (
    AUTO_THRESHOLD_COMMENT,
    COMMENT_SAFE_INTENTS,
    FINANCIAL_KEYWORDS,
    PolicyContext,
    decide,
)
from ca_agents.fb_rate_limiter import SlidingWindowRateLimiter
from ca_agents.guardrails import check_input_guardrail, normalize_text
from ca_agents.sensors.fb_questions import (
    FB_QUESTIONS,
    INJECTION_QUESTIONS,
    anonymize_state,
)
from ca_agents.sensors.jev_sensor import JevSensor
from ca_agents.sensors.regex_sensor import RegexSensor
from ca_agents.sensors.sensor_chain import SensorChain
from ca_contracts import FbPolicyAction, PolicyDecision

from ca_api.persist import (
    audit_add,
    fb_blacklist_bump,
    fb_blacklist_check,
    fb_escalation_add,
    fb_review_insert,
    kv_get,
    kv_set,
)

_RATE_LIMITER = SlidingWindowRateLimiter()
_FB_POLICY_KV = "fb_policy_runtime"

# SensorChain — JEV làm cảm biến chính; RegexSensor làm fallback tự động khi JEV lỗi.
# Tắt mặc định (JEV chưa được bật). Bật bằng JEV_ENABLED=true + JEV_API_KEY.
_JEV_SENSOR: JevSensor | None = None
_SENSOR_CHAIN: SensorChain | None = None


def _get_sensor_chain() -> SensorChain:
    """Trả SensorChain singleton (lazy). Luôn có RegexSensor; JEV tùy cấu hình.

    Kiểm tra kill-switch runtime mỗi lần gọi: nếu Chủ quán tắt JEV qua
    `/page/fb-policy` → chain tự động dùng None (chỉ Regex).
    """
    global _JEV_SENSOR, _SENSOR_CHAIN

    # Kill-switch runtime tắt JEV → xóa sensor cache ngay.
    if _JEV_SENSOR is not None and not fb_jev_enabled():
        _JEV_SENSOR = None
        _SENSOR_CHAIN = None

    # Khởi tạo JEV lazy nếu chưa có và đang được bật.
    if _JEV_SENSOR is None and fb_jev_enabled():
        candidate = JevSensor()
        if candidate.enabled and candidate.api_key:
            _JEV_SENSOR = candidate
            _SENSOR_CHAIN = None  # force rebuild chain với sensor mới

    # Xây chain (hoặc dùng lại nếu đã có).
    if _SENSOR_CHAIN is None:
        _SENSOR_CHAIN = SensorChain(
            jev_sensor=_JEV_SENSOR,
            regex_sensor=RegexSensor(),
        )

    return _SENSOR_CHAIN


def _jev_flags(
    text: str, name_map: dict[str, str] | None = None
) -> PolicyContext:
    """Đánh giá qua SensorChain (JEV → RegexSensor fallback) và trả PolicyContext.

    Khi JEV tắt/lỗi → RegexSensor tự động thay thế (đơn điệu, không im lặng):
    - JEV TẮT (chưa cấu hình key): source="regex", jev_ok=False, jev_failed=False.
    - JEV BẬT nhưng LỖI: source="regex_fallback", jev_failed=True,
      jev_fallback_used=True → decide() KHÔNG fail-closed (đã có Regex thay thế).
    - Cả hai thất bại (cực hiếm): jev_failed=True, jev_fallback_used=False
      → decide() fail-closed về phía con người.
    """
    chain = _get_sensor_chain()
    # Ẩn danh hóa trước khi gửi cho bên thứ ba (§6).
    anon_text = anonymize_state({"noi_dung_khach": text}, name_map).get(
        "noi_dung_khach", text
    )
    result = chain.evaluate(anon_text, "fb_page", FB_QUESTIONS)

    # Ghi audit theo source (ADR-007: không ghi nội dung thô).
    if result.source == "both" or result.source == "jev":
        audit_add(
            _now_iso(), "fb_jev_sensor", "jev_success", {
                "ok": True,
                "source": result.source,
                "signals": {name: s.value for name, s in result.signals.items()},
            },
            actor_type="system", agent_name="ag_fbpage",
        )
    elif result.source == "regex_fallback":
        audit_add(
            _now_iso(), "fb_jev_sensor", "jev_fallback_regex", {
                "ok": False,
                "source": "regex_fallback",
                "signals": {name: s.value for name, s in result.signals.items()},
            },
            actor_type="system", agent_name="ag_fbpage",
        )
    elif result.both_failed:
        audit_add(
            _now_iso(), "fb_jev_sensor", "jev_failed", {
                "ok": False,
                "source": "none",
            },
            actor_type="system", agent_name="ag_fbpage",
        )

    signals = result.signals
    health = signals.get("nguy_co_suc_khoe")
    legal = signals.get("de_doa_phap_ly_truyen_thong")
    hostility = signals.get("muc_gay_gat")
    ask_human = signals.get("doi_gap_nguoi_that")
    sarcasm = signals.get("co_ve_mia_mai")

    return PolicyContext(
        source=result.source,
        jev_ok=result.jev_ok,
        jev_failed=result.jev_failed,
        jev_fallback_used=result.fallback_used,
        jev_health_risk=float(health.value) if health is not None else 0.0,
        jev_legal_threat=float(legal.value) if legal is not None else 0.0,
        jev_hostility_score=float(hostility.value) if hostility is not None else 0.0,
        jev_ask_human=float(ask_human.value) if ask_human is not None else 0.0,
        jev_sarcasm=float(sarcasm.value) if sarcasm is not None else 0.0,
    )


def _check_jev_injection(psid: str, text: str) -> bool:
    """Kiểm tra injection/jailbreak qua SensorChain (kế hoạch §4.3).

    Fail-closed an toàn cho injection: cả JEV lẫn Regex đều tắt/lỗi → False
    (KHÔNG chặn vô tội vạ). RegexSensor KHÔNG có signal injection nên khi JEV
    lỗi → trả False (không thể bổ trợ). Regex L1 trong guardrails là lưới chính.
    """
    # Injection check: chỉ gọi JEV (không merge với Regex vì Regex không có
    # signal injection — tránh false positive từ chain merge).
    jev = _JEV_SENSOR
    if jev is None:
        return False
    state = anonymize_state({"noi_dung_khach": text})
    r = jev.evaluate(state, "injection_scan", INJECTION_QUESTIONS)
    if not r.ok:
        # JEV lỗi → injection check fallback = False (không chặn vô tội vạ).
        return False
    signals = r.signals
    override = float(signals["co_gang_ghi_de_chi_dan"].value)
    ask_internal = float(signals["hoi_du_lieu_noi_bo"].value)
    blocked = override >= 0.5 or ask_internal >= 0.5
    if blocked:
        _audit_block(psid, text, "jev_injection", "jev_flag")
    return blocked


_POSITIVE_KEYWORDS = (
    "cảm ơn",
    "hài lòng",
    "tuyệt vời",
    "tốt quá",
    "rất tốt",
    "ưng ý",
)
_NEGATIVE_KEYWORDS = (
    "không hài lòng",
    "thất vọng",
    "tệ quá",
    "quá tệ",
    "bực mình",
    "không đúng",
    "lừa đảo",
)
_COMMENT_ACTION_KEYWORDS = {
    "hide": ("spam", "quảng cáo", "link lạ"),
    "escalate": ("khiếu nại", "bồi thường", "lừa đảo", "luật sư"),
}


def analyze_comment_sentiment(text: str, sensor_chain: SensorChain | None = None) -> str:
    """Classify public-comment sentiment with deterministic vocabulary + SensorChain fallback."""
    normalized = normalize_text(text)
    if any(keyword in normalized for keyword in _NEGATIVE_KEYWORDS):
        return "negative"
    if sensor_chain is not None:
        res = sensor_chain.evaluate(text, "comment_sentiment", FB_QUESTIONS)
        sigs = res.signals
        hostility = sigs.get("muc_gay_gat")
        sarcasm = sigs.get("co_ve_mia_mai")
        if (hostility and float(hostility.value) >= 1.5) or (sarcasm and float(sarcasm.value) >= 0.50):
            return "negative"
    if any(keyword in normalized for keyword in _POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def classify_comment_action(
    text: str,
    sentiment: str,
    post_is_sensitive: bool = False,
    sensor_chain: SensorChain | None = None,
) -> tuple[str, list[str]]:
    """Return a review hint; the policy engine remains authoritative."""
    normalized = normalize_text(text)
    reasons: list[str] = []
    if any(keyword in normalized for keyword in _COMMENT_ACTION_KEYWORDS["hide"]):
        reasons.append("spam_or_advertising")
        return "hide", reasons
    if sentiment == "negative":
        reasons.append("negative_sentiment")
    if post_is_sensitive:
        reasons.append("sensitive_post")
    if any(keyword in normalized for keyword in _COMMENT_ACTION_KEYWORDS["escalate"]):
        reasons.append("escalation_keyword")

    if sensor_chain is not None:
        res = sensor_chain.evaluate(text, "comment_classify", FB_QUESTIONS)
        sigs = res.signals
        health = sigs.get("nguy_co_suc_khoe")
        legal = sigs.get("de_doa_phap_ly_truyen_thong")
        hostility = sigs.get("muc_gay_gat")
        sarcasm = sigs.get("co_ve_mia_mai")
        if health and float(health.value) >= 0.30:
            reasons.append("sensor_health_risk")
        if legal and float(legal.value) >= 0.30:
            reasons.append("sensor_legal_threat")
        if hostility and float(hostility.value) >= 1.5:
            reasons.append("sensor_high_hostility")
        if sarcasm and float(sarcasm.value) >= 0.50:
            reasons.append("sensor_sarcasm")

    return ("escalate" if reasons else "reply"), reasons


def _policy_runtime() -> dict[str, Any]:
    raw = kv_get(_FB_POLICY_KV, {})
    return raw if isinstance(raw, dict) else {}


def fb_auto_send_enabled() -> bool:
    """Feature flag — kế hoạch §5.5. Mặc định BẬT; Chủ quán tắt qua nút/env.

    KV (Chủ quán bật/tắt trên hộp thư) thắng env, để không mất sau restart
    Docker khi compose vẫn để NHIPQUAN_FB_AUTO_SEND cũ. Khi OFF, nhánh
    auto_send được ghi 'pending' — không bao giờ ghi 'auto_sent' khi chưa
    gửi thật. Tắt tường minh bằng NHIPQUAN_FB_AUTO_SEND=0 hoặc nút Chủ quán.
    """
    stored = _policy_runtime()
    if "auto_send_enabled" in stored:
        return bool(stored["auto_send_enabled"])
    env = os.environ.get("NHIPQUAN_FB_AUTO_SEND", "1").strip().lower()
    return env not in {"0", "false", "no", "off", ""}


def fb_jev_enabled() -> bool:
    """Kill-switch runtime cho Jev (kế hoạch §5 / review mục còn lại).

    KV (`jev_enabled`) thắng env — Chủ quán tắt nhanh qua API/hộp thư mà KHÔNG
    cần deploy, khi phát hiện Jev hoạt động sai / lộ dữ liệu. Mặc định BẬT
    (thiếu env = bật); tắt tường minh bằng JEV_ENABLED=0. Khi tắt → JevSensor
    không được tạo → fail-closed an toàn. Bật nhưng thiếu JEV_API_KEY thì
    JevSensor tự fail-closed (không gọi mạng) — xem JevSensor.
    """
    stored = _policy_runtime()
    if "jev_enabled" in stored:
        return bool(stored["jev_enabled"])
    return os.environ.get("JEV_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off", "",
    )


def fb_auto_price_cap_vnd() -> int:
    stored = _policy_runtime()
    if stored.get("auto_price_cap_vnd") is not None:
        try:
            return int(stored["auto_price_cap_vnd"])
        except (TypeError, ValueError):
            pass
    return int(os.environ.get("NHIPQUAN_FB_AUTO_PRICE_CAP_VND", "100000"))


def fb_compensation_cap_vnd() -> int:
    stored = _policy_runtime()
    if stored.get("compensation_cap_vnd") is not None:
        try:
            return int(stored["compensation_cap_vnd"])
        except (TypeError, ValueError):
            pass
    return int(os.environ.get("NHIPQUAN_FB_COMPENSATION_CAP_VND", "500000"))


def _compensation_above_cap(text: str) -> bool:
    low = normalize_text(text)
    if not any(k in low for k in FINANCIAL_KEYWORDS):
        return False
    if "trieu" in low:
        return True
    cap = fb_compensation_cap_vnd()
    for tok in re.sub(r"[^\d]", " ", text).split():
        if tok.isdigit() and int(tok) > cap:
            return True
    return False


def set_fb_policy_runtime(
    auto_send_enabled: bool | None = None,
    auto_price_cap_vnd: int | None = None,
    jev_enabled: bool | None = None,
) -> dict[str, Any]:
    """Ghi chính sách runtime (KV + env process) — Chủ quán chỉnh không restart."""
    cur = dict(_policy_runtime())
    global _JEV_SENSOR, _SENSOR_CHAIN
    if auto_send_enabled is not None:
        cur["auto_send_enabled"] = bool(auto_send_enabled)
        os.environ["NHIPQUAN_FB_AUTO_SEND"] = "1" if auto_send_enabled else "0"
    if auto_price_cap_vnd is not None:
        cur["auto_price_cap_vnd"] = int(auto_price_cap_vnd)
        os.environ["NHIPQUAN_FB_AUTO_PRICE_CAP_VND"] = str(int(auto_price_cap_vnd))
    if jev_enabled is not None:
        # Kill-switch runtime: tắt Jev ngay không cần deploy (kế hoạch §5).
        cur["jev_enabled"] = bool(jev_enabled)
        os.environ["JEV_ENABLED"] = "1" if jev_enabled else "0"
        # Reset cả sensor lẫn chain để lần gọi sau tạo/ko tạo đúng trạng thái.
        _JEV_SENSOR = None
        _SENSOR_CHAIN = None
    kv_set(_FB_POLICY_KV, cur)
    return cur


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sla_expiry(sla_minutes: int | None) -> str | None:
    if not sla_minutes:
        return None
    return (datetime.now(UTC) + timedelta(minutes=sla_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _event_time_iso(timestamp: float) -> str | None:
    if timestamp <= 0:
        return None
    seconds = timestamp / 1000 if timestamp > 1e11 else timestamp
    try:
        return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError):
        return None


def queue_fb_non_text(
    *,
    psid: str,
    event_id: str,
    description: str,
    attachment_type: str | None = None,
    attachment_url: str | None = None,
    store_id: str | None = None,
) -> int:
    """Đưa attachment/postback vào hàng duyệt mà không suy đoán ý định."""
    review_id = fb_review_insert(
        {
            "source": "messenger",
            "external_thread_id": f"fb_{psid}",
            "external_psid": psid,
            "message_text": description,
            "detected_intent": "khac",
            "confidence": 1.0,
            "policy_action": FbPolicyAction.QUEUE_REVIEW.value,
            "assigned_role": "quan_ly",
            "proposed_response": None,
            "flagged_reasons": ["non_text_event"],
            "trace_id": event_id or uuid.uuid4().hex[:12],
            "created_at": _now_iso(),
            "expires_at": _sla_expiry(10),
            "store_id": store_id,
            "attachment_type": attachment_type,
            "attachment_url": attachment_url,
        }
    )
    audit_add(
        _now_iso(),
        "fb_policy_engine",
        FbPolicyAction.QUEUE_REVIEW.value,
        {"psid": psid, "reason": "non_text_event", "review_id": review_id},
        actor_type="system",
        agent_name="ag_fbpage",
    )
    return review_id


def _menu_price_above_cap(menu: list[dict[str, Any]], text: str) -> bool:
    low = text.lower()
    for m in menu:
        ten = str(m.get("ten") or "").lower()
        if ten and ten in low:
            try:
                return int(m.get("gia") or 0) > fb_auto_price_cap_vnd()
            except (TypeError, ValueError):
                return False
    return False


def _kb_has_fact(public_context: dict[str, Any] | None, text: str) -> bool:
    ctx = public_context or {}
    profile = ctx.get("profile") or {}
    menu = ctx.get("menu") or []
    low = text.lower()
    if any(k in low for k in ("mấy giờ", "may gio", "giờ mở", "gio mo", "đóng cửa", "dong cua")):
        return bool(str(profile.get("gio_mo_cua") or "").strip())
    if any(k in low for k in ("ở đâu", "o dau", "địa chỉ", "dia chi", "vị trí", "vi tri")):
        return bool(str(profile.get("dia_chi") or "").strip())
    if "wifi" in low:
        return bool(str(profile.get("wifi_ssid") or "").strip())
    if any(k in low for k in ("giá", "gia", "tiền", "tien", "menu", "bao nhiêu", "bao nhieu")):
        return bool(menu)
    return bool(menu) or bool(profile)


def moderate_fb_message(
    *,
    psid: str,
    text: str,
    message_id: str,
    timestamp: float,
    public_context: dict[str, Any] | None = None,
    repeat_ask_count: int = 0,
    source: str = "messenger",
    post_id: str | None = None,
    post_is_sensitive: bool = False,
    external_user_name: str | None = None,
    store_id: str | None = None,
) -> dict[str, Any]:
    """Xử lý 1 tin Messenger qua 5 lớp cổng; ghi queue khi cần con người.

    Trả về dict: action, review_id, response (chỉ khi auto_send), reason,
    flagged_reasons, intent, confidence.
    """
    # L1 — Input guardrail
    guard = check_input_guardrail(text)
    if not guard.is_safe:
        _audit_block(psid, text, "injection", guard.reason or "unsafe")
        return {
            "action": FbPolicyAction.BLOCK_SILENT.value,
            "review_id": None,
            "response": None,
            "reason": guard.reason,
            "flagged_reasons": [],
        }

    # L2 — blacklist DB + rate limit in-memory
    if fb_blacklist_check(psid):
        return {
            "action": FbPolicyAction.BLOCK_SILENT.value,
            "review_id": None,
            "response": None,
            "reason": "psid_blacklisted",
            "flagged_reasons": [],
        }
    verdict = _RATE_LIMITER.check(psid)
    if not verdict.allowed:
        if verdict.blacklisted:
            blocked_until = (datetime.now(UTC) + timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            fb_blacklist_bump(
                psid, strikes=3, blocked_until=blocked_until,
                reason=verdict.reason or "rate_limit",
            )
        _audit_block(psid, text, "rate_limit", verdict.reason or "")
        return {
            "action": FbPolicyAction.BLOCK_SILENT.value,
            "review_id": None,
            "response": None,
            "reason": verdict.reason,
            "flagged_reasons": [],
        }

    # L3 — Intent classify (deterministic)
    _, intent, confidence = detect_customer_psychology(guard.sanitized_text)

    # L3.5 — Lọc injection/jailbreak bằng Jev (kế hoạch §4.3) — bổ trợ regex L1,
    # chỉ TĂNG leo thang (đơn điệu). Jev tắt/lỗi → bỏ qua, không cấp quyền gì.
    _jev_injection_blocked = _check_jev_injection(psid, guard.sanitized_text)
    if _jev_injection_blocked:
        return {
            "action": FbPolicyAction.BLOCK_SILENT.value,
            "review_id": None,
            "response": None,
            "reason": "jev_injection_detected",
            "flagged_reasons": ["jev_injection"],
        }

    # L4 — Policy decide (tất định)
    res_eligible = False
    if intent == "dat_ban":
        try:
            from ca_api.services.table_reservation_service import (
                auto_reservation_enabled,
                check_anti_abuse,
            )

            if auto_reservation_enabled():
                allowed, _ = check_anti_abuse(store_id="quan_01", psid=psid)
                res_eligible = allowed
            else:
                res_eligible = False
        except Exception:
            res_eligible = False

    # L3.5 — Đánh giá Jev một lần (fail-closed nếu tắt/lỗi) — đơn điệu, chỉ
    # thêm leo thang. Ẩn danh hóa state trước khi gửi bên thứ ba (§6).
    jctx = _jev_flags(guard.sanitized_text, {"minh": "NV_01", "lan": "NV_02"})

    ctx = PolicyContext(
        source=source,
        sensitive_post=post_is_sensitive,
        repeat_ask_count=repeat_ask_count,
        kb_has_fact=_kb_has_fact(public_context, guard.sanitized_text),
        price_above_limit=_menu_price_above_cap(
            (public_context or {}).get("menu") or [], guard.sanitized_text
        ),
        reservation_auto_eligible=res_eligible,
        booking_system_down=False,
        compensation_above_limit=_compensation_above_cap(guard.sanitized_text),
        # ADR-008: promo do chủ quán nhập mới được thông báo; danh sách rỗng
        # nghĩa là quán chưa cấu hình → câu hỏi khuyến mãi phải QL duyệt.
        promotions_available=bool((public_context or {}).get("promotions")),
        jev_ok=jctx.jev_ok,
        jev_failed=jctx.jev_failed,
        jev_health_risk=jctx.jev_health_risk,
        jev_legal_threat=jctx.jev_legal_threat,
        jev_hostility_score=jctx.jev_hostility_score,
        jev_ask_human=jctx.jev_ask_human,
        jev_sarcasm=jctx.jev_sarcasm,
    )
    decision = decide(intent, confidence, guard.sanitized_text, ctx)
    flagged = list(decision.flagged_reasons)

    # Comment công khai: chỉ auto-send khi intent an toàn + confidence cao
    # (COMMENT_SAFE_INTENTS + AUTO_THRESHOLD_COMMENT). Ngoài ra hạ xuống queue
    # cho QL duyệt tay (ADR-008) — không để action auto_send lọt ra ngoài.
    if source == "comment" and decision.action == FbPolicyAction.AUTO_SEND:
        if not (intent in COMMENT_SAFE_INTENTS and confidence >= AUTO_THRESHOLD_COMMENT):
            decision = PolicyDecision(
                action=FbPolicyAction.QUEUE_REVIEW,
                reason="comment_not_safe_auto",
                intent=intent,
                confidence=confidence,
                assigned_role="quan_ly",
                sla_minutes=15,
                flagged_reasons=flagged + ["comment_requires_manager"],
            )
            flagged = decision.flagged_reasons

    # L5 — Supervisor gate cho nhánh auto; hạ xuống queue nếu flag
    response: str | None = None
    if decision.action == FbPolicyAction.AUTO_SEND:
        reply, requires_approval, _agent = build_human_response(
            intent, "neutral", guard.sanitized_text, public_context,
            customer_profile={"psid": psid},
        )
        sup = supervise_outgoing_response(guard.sanitized_text, reply)
        if not sup.is_approved or requires_approval:
            decision = PolicyDecision(
                action=FbPolicyAction.QUEUE_REVIEW,
                reason="supervisor_downgrade",
                intent=intent,
                confidence=confidence,
                assigned_role="quan_ly",
                sla_minutes=10,
                flagged_reasons=flagged + [sup.flagged_reason or "supervisor"],
            )
            flagged = decision.flagged_reasons
        else:
            response = sup.sanitized_response

    # Nếu rơi vào hàng đợi duyệt nhưng chưa có câu gợi ý, sinh bản nháp cho Quản lý
    if not response and decision.action in (
        FbPolicyAction.QUEUE_REVIEW,
        FbPolicyAction.PRIORITY_REVIEW,
    ):
        try:
            suggested_draft, _, _ = build_human_response(
                intent, "neutral", guard.sanitized_text, public_context,
                customer_profile={"psid": psid},
            )
            response = suggested_draft
        except Exception:
            pass

    # Ghi review queue cho mọi thứ cần con người nhìn
    review_id: int | None = None
    if decision.action in (
        FbPolicyAction.QUEUE_REVIEW,
        FbPolicyAction.PRIORITY_REVIEW,
        FbPolicyAction.ESCALATE_OWNER,
    ):
        review_id = fb_review_insert(
            {
                "store_id": store_id or "quan_01",
                "source": source,
                "external_thread_id": message_id if source == "comment" else f"fb_{psid}",
                "external_psid": psid,
                "external_user_name": external_user_name,
                "post_id": post_id,
                "post_is_sensitive": post_is_sensitive,
                "message_text": guard.sanitized_text,
                "detected_intent": intent,
                "confidence": confidence,
                "policy_action": decision.action.value,
                "assigned_role": decision.assigned_role,
                "proposed_response": response or decision.reason,
                "flagged_reasons": flagged,
                "trace_id": uuid.uuid4().hex[:12],
                "created_at": _now_iso(),
                "event_at": _event_time_iso(timestamp),
                "expires_at": _sla_expiry(decision.sla_minutes),
            }
        )
        if decision.action == FbPolicyAction.ESCALATE_OWNER:
            fb_escalation_add(
                review_id,
                escalated_to="chu_quan",
                reason=decision.reason,
                notified_channel="in_app",
            )
    elif decision.action == FbPolicyAction.AUTO_SEND:
        # Comment công khai an toàn: LUÔN claim để tự trả lời, bất kể cờ
        # auto-send (quyết định của Chủ quán: mặc kệ env/KV, comment an toàn
        # phải được trả lời ngay). Cờ chỉ giữ cho Messenger.
        # Comment không an toàn đã bị hạ QUEUE_REVIEW ở trên.
        if source == "comment" or fb_auto_send_enabled():
            # Claim giao tin; webhook chỉ đánh dấu auto_sent sau khi Graph xác nhận.
            review_id = fb_review_insert(
                {
                    "store_id": store_id or "quan_01",
                    "source": source,
                    "external_thread_id": message_id if source == "comment" else f"fb_{psid}",
                    "external_psid": psid,
                    "external_user_name": external_user_name,
                    "post_id": post_id,
                    "post_is_sensitive": post_is_sensitive,
                    "message_text": guard.sanitized_text,
                    "detected_intent": intent,
                    "confidence": confidence,
                    "policy_action": decision.action.value,
                    "assigned_role": None,
                    "proposed_response": response,
                    "flagged_reasons": flagged,
                    "status": "approved",
                    "final_response": response,
                    "trace_id": uuid.uuid4().hex[:12],
                    "created_at": _now_iso(),
                    "event_at": _event_time_iso(timestamp),
                    "expires_at": None,
                }
            )
        else:
            # Flag OFF + Messenger: auto-able nhưng chưa được phép gửi →
            # pending cho QL duyệt tay (ADR-008: người quyết). KHÔNG ghi
            # auto_sent. Nhánh comment không bao giờ vào đây (luôn claim ở trên).
            review_id = fb_review_insert(
                {
                    "source": source,
                    "external_thread_id": message_id if source == "comment" else f"fb_{psid}",
                    "external_psid": psid,
                    "external_user_name": external_user_name,
                    "post_id": post_id,
                    "post_is_sensitive": post_is_sensitive,
                    "message_text": guard.sanitized_text,
                    "detected_intent": intent,
                    "confidence": confidence,
                    "policy_action": decision.action.value,
                    "assigned_role": "quan_ly",
                    "proposed_response": response,
                    "flagged_reasons": flagged + ["auto_blocked_by_flag"],
                    "status": "pending",
                    "trace_id": uuid.uuid4().hex[:12],
                    "created_at": _now_iso(),
                    "event_at": _event_time_iso(timestamp),
                    "expires_at": _sla_expiry(10),
                }
            )

    audit_add(
        _now_iso(),
        "fb_policy_engine",
        decision.action.value,
        {
            "psid": psid, "intent": intent, "confidence": confidence,
            "reason": decision.reason, "review_id": review_id,
        },
        actor_type="system",
        agent_name="ag_fbpage",
    )
    return {
        "action": decision.action.value,
        "review_id": review_id,
        "response": response,
        "intent": intent,
        "confidence": confidence,
        "reason": decision.reason,
        "flagged_reasons": flagged,
        "source": source,
    }


def _audit_block(psid: str, text: str, loai: str, reason: str) -> None:
    audit_add(_now_iso(), "fb_moderation_block", loai, {
        "psid": psid, "reason": reason, "text_len": len(text),
    }, actor_type="system", agent_name="ag_fbpage")
