"""AG-COPILOT agent implementation — Two-phase proposal generator & Conversational Assistant."""

from __future__ import annotations

import os
import uuid

try:
    from datetime import UTC, datetime, timedelta
except ImportError:
    from datetime import datetime, timedelta, timezone
    UTC = timezone.utc
# Per-user rate limiter: max 30 requests/60s sliding window.
import collections as _collections
from typing import Any

from ca_contracts import (
    ActionProposal,
    ActionProposalStatus,
    CopilotIntent,
    CopilotResponse,
    copilot_role_can_use_intent,
)

from ca_agents.ag_copilot.intent_parser import (
    OUT_OF_SCOPE,
    parse_intent,
)
from ca_agents.ag_copilot.tool_registry import (
    execute_whitelisted_tool,
)
from ca_agents.ag_supervisor import supervise_outgoing_response

# TTL mặc định cho ActionProposal — configurable qua env var.
# Tăng từ 30 → 120 phút: chủ quán hay bị ngắt giữa chừng nên cần thời gian duyệt dài hơn.
_DEFAULT_TTL_MINUTES: int = max(5, int(os.environ.get("COPILOT_PROPOSAL_TTL_MINUTES", "120")))

_RATE_WINDOWS: dict[str, _collections.deque[float]] = {}
_RATE_LIMIT = 30
_RATE_WINDOW_S = 60.0

# Lỗi tool = "thiếu thông tin, cần hỏi lại" (không phải lỗi hệ thống). Với các
# mã này, câu hỏi làm rõ phải đi thẳng ra cho người dùng, không bọc tiền tố
# "Dạ kết quả tra cứu cho anh/chị" của nhánh intent-đọc.
_CAU_HOI_LAM_RO_ERROR = frozenset({
    "missing_thu", "thieu_ly_do", "thieu_noi_dung", "thieu_thong_tin",
    "thieu_treo_id", "thieu_so_luong", "thieu_swap_id", "thieu_khoang_ban",
})


def _rate_limit_check(user_id: str) -> bool:
    """Return True if rate-limited (should reject)."""
    import os
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CA_AGENT_MODE") == "replay" or os.environ.get("TESTING"):
        return False
    import time as _time
    now = _time.monotonic()
    dq = _RATE_WINDOWS.setdefault(user_id, _collections.deque())
    while dq and dq[0] < now - _RATE_WINDOW_S:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT:
        return True
    dq.append(now)
    return False


def _current_agent_mode() -> str:
    """Chế độ agent hiện tại — 'live' khi có key LLM, 'replay' mặc định."""
    import os

    return os.environ.get("CA_AGENT_MODE", "replay").strip().lower() or "replay"


def _compute_hash(data: Any) -> str:
    import hashlib
    import json
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _generate_conversational_reply(
    message: str,
    user_role: str,
    user_id: str,
    store_id: str,
    context: dict[str, Any],
) -> str:
    """Tạo câu trả lời thông minh cho các câu hội thoại / chào hỏi / hỏi đáp ngoài thao tác tool."""
    lower = message.lower().strip()

    # 1. Thử gọi LLM khi ở chế độ live hoặc có LLM provider khả dụng
    mode = _current_agent_mode()
    if mode == "live":
        try:
            from ca_agents.llm import complete, provider_status
            st = provider_status()
            if any(st.values()):
                role_label = {
                    "chu_quan": "Chủ quán",
                    "quan_ly": "Quản lý",
                    "nhan_vien": "Nhân viên",
                }.get(user_role, "Nhân viên")

                system = (
                    "Bạn là AG-COPILOT — trợ lý điều hành ảo thông minh của chuỗi quán cà phê Nhịp Quán.\n"
                    f"Người dùng đang trò chuyện có vai trò: {role_label} (tài khoản: {user_id}, cơ sở: {store_id}).\n"
                    "Phong cách giao tiếp:\n"
                    "- Tiếng Việt chuẩn mực, thân thiện, tự nhiên, xưng 'em', gọi 'anh/chị'.\n"
                    "- Trả lời đúng trọng tâm câu hỏi của người dùng (chào hỏi, cảm ơn, hỏi thăm, giải thích, tư vấn vận hành quán cà phê, kiến thức đồ uống).\n"
                    "- Ngắn gọn, súc tích (khoảng 2-4 câu), không dài dòng.\n"
                    "- Hiểu rõ nghiệp vụ quán: xếp lịch ca, đổi ca, bản tin sáng, quy trình SOP, kiểm kho, hao hụt... Nếu người dùng muốn làm các việc này, hãy giải thích và hướng dẫn họ câu lệnh cụ thể.\n"
                    "- Không tự ý bịa số liệu hay nói rằng mình đã tự ý thay đổi dữ liệu trong hệ thống khi người dùng chỉ đang trò chuyện."
                )
                llm_res = complete(
                    system=system,
                    user=message,
                    task="text:copilot_chat",
                    timeout_s=15.0,
                    json_mode=False,
                )
                if llm_res.ok and llm_res.text.strip():
                    return llm_res.text.strip()
        except (ImportError, OSError, ValueError):
            pass

    # 2. Phản hồi đàm thoại thông minh theo quy tắc (fallback khi replay hoặc LLM bận)
    import re
    if re.search(r"\b(chào|xin chào|hello|hi|hey|alo)\b", lower):
        return (
            "Dạ em chào anh/chị! Chúc anh/chị một ca làm việc vui vẻ và hiệu quả. "
            "Anh/chị cần em hỗ trợ gì cho quán hôm nay không ạ?"
        )
    if re.search(r"\b(cảm ơn|cam on|thank|thanks|tks)\b", lower):
        return (
            "Dạ không có chi ạ! Rất vui được hỗ trợ anh/chị. "
            "Nếu cần hỗ trợ thêm việc gì trong ca, anh/chị cứ nhắn em nhé!"
        )
    if re.search(r"\b(bạn là ai|em là ai|mày là ai|bạn tên gì|ten gi|giới thiệu)\b", lower):
        return (
            "Dạ em là AG-COPILOT — trợ lý điều hành ảo của Nhịp Quán. "
            "Em hỗ trợ anh/chị quản lý lịch ca, theo dõi bàn giao, quy trình SOP, tồn kho và các nghiệp vụ vận hành quán ạ."
        )
    if re.search(r"\b(làm được gì|giúp gì|chức năng|năng lực|ho tro gi)\b", lower):
        if user_role == "nhan_vien":
            return (
                "Dạ với vai trò nhân viên, em có thể hỗ trợ anh/chị: xem bản tin ca, "
                "tra cứu quy trình (SOP), xem lịch làm việc của mình, và gửi yêu cầu đổi ca/báo bận ạ."
            )
        return (
            "Dạ em hỗ trợ anh/chị toàn diện việc điều hành: xếp lịch tuần (solver), "
            "duyệt đổi ca, tóm tắt bản tin sáng, tra cứu quy trình, báo cáo hao hụt, kiểm kho và đề xuất luật mới ạ."
        )

    # 3. Fallback mặc định theo vai trò
    if user_role == "nhan_vien":
        return (
            "Dạ em có thể hỗ trợ anh/chị: xem bản tin ca, tra cứu quy trình (SOP) "
            "và báo cáo hao hụt trong ca. Anh/chị cần em làm gì ạ?"
        )
    return (
        "Dạ em có thể hỗ trợ anh/chị: xếp lịch tuần, duyệt đổi ca, bản tin sáng, tra cứu quy trình, "
        "báo cáo hao hụt, đề xuất luật mới và kiểm tra tồn kho. Anh/chị cần em làm gì ạ?"
    )


def run_copilot(
    message: str,
    context: dict[str, Any] | None = None,
    *,
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> CopilotResponse:
    """Main AG-COPILOT entrypoint."""
    ctx = context or {}
    store_id = str(ctx.get("store_id") or "quan_01")
    user_id = str(ctx.get("user_id") or "nv_01")

    # Rate limit per-user (fail-open: lỗi rate limiter không chặn request).
    try:
        if _rate_limit_check(user_id):
            return CopilotResponse(
                reply_text="Dạ anh/chị gửi tin nhắn hơi nhanh, em xử lý không kịp. Anh/chị chờ vài giây rồi nhắn lại giúp em nhé!",
                intent=CopilotIntent.OUT_OF_SCOPE,
                confidence=0.99,
                action_proposal=None,
                direct_answer=None,
                agent_mode=_current_agent_mode(),
            )
    except Exception:
        pass

    # Fail-closed: role thiếu/lạ → nhan_vien (đặc quyền thấp nhất).
    raw_role = str(ctx.get("user_role") or "").strip()
    user_role = raw_role if raw_role in ("chu_quan", "quan_ly", "nhan_vien") else "nhan_vien"

    # 1. Parse Intent & Security Filter
    parsed = parse_intent(message, ctx)

    # 1.0 Role-based intent authorization (VF-SCOPE pre-check, fail-closed).
    # Chặn TRƯỚC khi chạy tool để AI của role thấp không bao giờ thực thi
    # intent vượt quyền, kể cả khi LLM parse đúng intent đó.
    if parsed.intent != OUT_OF_SCOPE and not copilot_role_can_use_intent(
        user_role, parsed.intent
    ):
        reply = (
            "Dạ lỗi này vượt phạm vi vai trò của anh/chị. "
            "Việc này chỉ quản lý hoặc chủ quán mới có thể yêu cầu em thực hiện ạ. "
            "Anh/chị có thể nhờ quản lý duyệt giúp, hoặc hỏi em các việc trong phạm vi ca của mình."
        )
        return CopilotResponse(
            reply_text=reply,
            intent=CopilotIntent.OUT_OF_SCOPE,
            confidence=0.99,
            action_proposal=None,
            direct_answer=reply,
            agent_mode=_current_agent_mode(),
        )

    # 1.1 Check Prompt Injection / Bypass Approval attempts
    if parsed.security_flag == "bypass_approval_rejected":
        reply = (
            "Dạ em không thể bỏ qua bước duyệt được ạ, đây là quy định an toàn bắt buộc của hệ thống. "
            "Em vẫn có thể tạo bản nháp để anh/chị xem trước khi duyệt — anh/chị có muốn em thực hiện không ạ?"
        )
        return CopilotResponse(
            reply_text=reply,
            intent=CopilotIntent.OUT_OF_SCOPE,
            confidence=0.99,
            action_proposal=None,
            direct_answer=reply,
            agent_mode=_current_agent_mode(),
        )

    # 1.2 Low-confidence clarification
    if parsed.clarification_needed and parsed.clarification_question:
        return CopilotResponse(
            reply_text=parsed.clarification_question,
            intent=getattr(CopilotIntent, parsed.intent, CopilotIntent.OUT_OF_SCOPE),
            confidence=parsed.confidence,
            action_proposal=None,
            direct_answer=None,
            agent_mode=_current_agent_mode(),
            clarification_kind=parsed.clarification_kind,
        )

    # 1.3 Out of scope / Conversational QA
    if parsed.intent == OUT_OF_SCOPE:
        reply = _generate_conversational_reply(
            message,
            user_role=user_role,
            user_id=user_id,
            store_id=store_id,
            context=ctx,
        )
        return CopilotResponse(
            reply_text=reply,
            intent=CopilotIntent.OUT_OF_SCOPE,
            confidence=parsed.confidence,
            action_proposal=None,
            direct_answer=reply,
            agent_mode=_current_agent_mode(),
        )

    # 2. Execute Whitelisted Tool
    # PR10 còn lại: tool cần biết người gọi (ownership TKB, participant consent)
    # nên truyền user_id/user_role — các tool cũ nhận qua **kwargs, không ảnh hưởng.
    tool_res = execute_whitelisted_tool(
        parsed.intent,
        {**parsed.params, "store_id": store_id, "user_id": user_id, "user_role": user_role},
    )

    # 2.1 Tool fail-closed vì thiếu thông tin → hỏi lại, KHÔNG bọc trong
    # "Dạ kết quả tra cứu cho anh/chị". Câu đó dành cho intent ĐỌC; với yêu
    # cầu hành động nó đọc như copilot lạc đề, và "Anh/chị cho em biết ngày
    # nào bận ạ" bị chôn sau tiền tố sai làm NV không biết phải trả lời gì.
    if not tool_res.success and tool_res.error in _CAU_HOI_LAM_RO_ERROR:
        return CopilotResponse(
            reply_text=tool_res.summary,
            intent=getattr(CopilotIntent, parsed.intent, CopilotIntent.OUT_OF_SCOPE),
            confidence=parsed.confidence,
            action_proposal=None,
            direct_answer=tool_res.summary,
            agent_mode=_current_agent_mode(),
        )

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_iso = (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot_data = tool_res.source_snapshot if tool_res.source_snapshot is not None else tool_res.data
    snapshot_hash = _compute_hash(snapshot_data)

    action_prop: ActionProposal | None = None
    direct_answer: str | None = None

    if tool_res.requires_confirmation:
        action_id = f"act_{uuid.uuid4().hex[:8]}"
        explanation = tool_res.explanation
        from ca_agents.runtime import SkillLoader
        matched_skill_id = SkillLoader().match_intent_to_skill(message)
        if matched_skill_id:
            explanation = f"{explanation} [Đã kiểm định qua Kỹ năng: {matched_skill_id}]"

        action_prop = ActionProposal(
            action_id=action_id,
            intent=getattr(CopilotIntent, parsed.intent),
            status=ActionProposalStatus.ready_for_approval if tool_res.success else ActionProposalStatus.draft,
            summary=tool_res.summary,
            explanation=explanation,
            payload_diff=tool_res.data,
            requires_confirmation=True,
            store_id=store_id,
            created_by=user_id,
            confidence=parsed.confidence,
            data_snapshot_hash=snapshot_hash,
            created_at=now_iso,
            expires_at=expires_iso,
        )

        if parsed.intent == "SEND_MAIL":
            reply = (
                f"Dạ em đã nhờ Agent Soạn Mail (AG-MAILWRITER) soạn xong: {tool_res.summary}. "
                "Anh/chị xem qua nội dung bên dưới, có thể bấm 'Duyệt & Gửi', chỉnh sửa hoặc bảo em sửa lại nhé!"
            )
        elif not tool_res.success:
            # BUG4 fix: tool thất bại nhưng requires_confirmation=True → proposal ở trạng thái draft
            # Không nói "Đã hoàn thành" vì sẽ misleading người dùng.
            reply = (
                f"Dạ em chưa tạo được đề xuất hoàn chỉnh: {tool_res.summary} "
                "Anh/chị xem thông tin bên dưới và có thể yêu cầu lại hoặc nhờ quản lý kiểm tra nhé!"
            )
        else:
            reply = f"Dạ em đã hoàn thành bước chuẩn bị: {tool_res.summary} Anh/chị xem qua và bấm duyệt để áp dụng nhé!"
    else:
        direct_answer = tool_res.summary
        reply = f"Dạ kết quả tra cứu cho anh/chị: {tool_res.summary}"

    # 3. Supervise outgoing response for safety & leaks
    sup_res = supervise_outgoing_response(message, reply)
    final_reply = sup_res.sanitized_response

    # Fail-closed: Nếu supervisor phát hiện vi phạm an toàn, hạ cấp action_proposal
    confidence = parsed.confidence
    if not sup_res.is_approved:
        confidence = 0.0
        direct_answer = None
        if action_prop is not None:
            action_prop = ActionProposal(
                action_id=action_prop.action_id,
                intent=action_prop.intent,
                status=ActionProposalStatus.draft,
                summary=f"[BỊ CHẶN BỞI AG-SUPERVISOR: {sup_res.flagged_reason}] {action_prop.summary}",
                explanation=f"Đề xuất bị chặn do phát hiện rủi ro an toàn ({sup_res.flagged_reason}). Quản lý cần kiểm tra thủ công.",
                payload_diff=action_prop.payload_diff,
                requires_confirmation=True,
                store_id=action_prop.store_id,
                created_by=action_prop.created_by,
                confidence=0.0,
                data_snapshot_hash=action_prop.data_snapshot_hash,
                created_at=action_prop.created_at,
                expires_at=action_prop.expires_at,
            )

    # Citations: lấy từ tool data nếu có (QUERY_SOP / survey).
    citations = list(tool_res.data.get("citations", []) or []) if isinstance(tool_res.data, dict) else []

    return CopilotResponse(
        reply_text=final_reply,
        intent=getattr(CopilotIntent, parsed.intent, CopilotIntent.OUT_OF_SCOPE),
        confidence=confidence,
        action_proposal=action_prop,
        direct_answer=direct_answer,
        citations=citations,
        agent_mode=_current_agent_mode(),
    )
