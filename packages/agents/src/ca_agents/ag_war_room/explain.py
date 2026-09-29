"""War Room — tầng GIẢI THÍCH bằng LLM (không đụng số liệu).

Nguyên tắc (giữ đúng thiết kế fail-closed của War Room):

- **Số liệu do engine tất định tính** (`orchestrator.py`) — tầng này KHÔNG bao
  giờ sinh hay sửa số. Nó chỉ diễn đạt LẠI các con số đã có thành lời.
- Gọi LLM CHỈ khi `CA_AGENT_MODE=live`. Replay/không key → rơi về bản tất định.
- **Cổng chống bịa**: mọi con số trong câu trả lời phải xuất hiện trong dữ kiện;
  nếu LLM thêm số lạ hoặc khẳng định tuyệt đối → bỏ câu trả lời LLM, giữ bản tất
  định (giống `ag_quanverse.assistant`).

Vì sao cần: các panel War Room trước đây chỉ hiện số khô + một câu `risk` cố
định, nên bấm "Đề xuất" gần như không thấy gì xảy ra. Tầng này đưa ra lời giải
thích ĐỌC ĐƯỢC cho từng phương án, bám đúng số của engine.
"""

from __future__ import annotations

import re
from typing import Any

from ca_agents.llm import agent_mode, complete

_SYSTEM_PROMPT = (
    "Bạn là trợ lý vận hành quán cà phê. Bạn CHỈ được diễn giải các con số và sự "
    "kiện trong phần DỮ KIỆN. TUYỆT ĐỐI không bịa thêm số, không thêm sự kiện "
    "ngoài dữ kiện, không dùng lời khẳng định tuyệt đối (chắc chắn 100%, luôn "
    "luôn…). Trả lời tiếng Việt, 2–4 câu, nói rõ phương án này đánh đổi điều gì."
)

_ABSOLUTE_HINTS = ("chắc chắn 100%", "luôn luôn", "không bao giờ sai", "đảm bảo 100%")


def _numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d[\d.,]*", text or "")}


def _fact_numbers(options: list[dict[str, Any]]) -> set[str]:
    """Tập hợp mọi con số có trong dữ kiện để chặn LLM bịa số."""
    allowed: set[str] = set()
    for opt in options:
        for bucket in ("outputs", "load", "fairness_impact"):
            val = opt.get(bucket)
            if isinstance(val, dict):
                for v in val.values():
                    allowed |= _numbers_in(str(v))
            elif val is not None:
                allowed |= _numbers_in(str(val))
        for key in ("estimated_cost", "estimated_revenue"):
            if opt.get(key) is not None:
                allowed |= _numbers_in(str(opt[key]))
    return allowed


def audit_explanation(text: str, allowed: set[str]) -> list[str]:
    """Trả danh sách vi phạm: số lạ hoặc khẳng định tuyệt đối."""
    problems: list[str] = []
    low = (text or "").lower()
    for hint in _ABSOLUTE_HINTS:
        if hint in low:
            problems.append(f"khẳng định tuyệt đối: {hint}")
    for number in _numbers_in(text):
        if number not in allowed:
            problems.append(f"số không có trong dữ kiện: {number}")
    return problems


def _deterministic_reason(option: dict[str, Any]) -> str:
    """Lời giải thích tất định từ chính dữ kiện (lưới an toàn, dùng ở replay)."""
    parts: list[str] = []
    risk = str(option.get("risk") or "").strip()
    if risk:
        parts.append(risk)
    delta = (option.get("fairness_impact") or {}).get("delta") if isinstance(option.get("fairness_impact"), dict) else None
    if delta is not None:
        parts.append(f"Lệch công bằng: {delta}.")
    viol = option.get("constraint_violations") or []
    if viol:
        parts.append(f"Vi phạm ràng buộc: {len(viol)}.")
    return " ".join(parts) if parts else "Chưa có mô hình tất định cho phương án này."


def explain_option(option: dict[str, Any], *, all_options: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Trả ``{"reason": str, "provider": str, "unsupported": [...]}``.

    `reason` là lời giải thích ĐỌC ĐƯỢC cho một phương án. Số trong đó bám đúng
    dữ kiện; ở replay là bản tất định.
    """
    allowed = _fact_numbers(all_options or [option])
    fallback = _deterministic_reason(option)
    provider = "replay"
    reason = fallback
    unsupported: list[str] = []

    facts = {
        "phuong_an": option.get("scenario_id"),
        "outputs": option.get("outputs"),
        "fairness": option.get("fairness_impact"),
        "rui_ro": option.get("risk"),
        "vi_pham": option.get("constraint_violations"),
    }
    if agent_mode() == "live" and facts.get("outputs"):
        result = complete(
            system=_SYSTEM_PROMPT,
            user=f"DỮ KIỆN (JSON):\n{facts}\n\nHãy giải thích phương án này đánh đổi điều gì.",
            task="text:war_room_explain",
            json_mode=False,
        )
        if result.ok and result.text.strip():
            violations = audit_explanation(result.text, allowed)
            if violations:
                unsupported = violations
                provider = f"replay:chan_{result.provider}"
            else:
                reason = result.text.strip()
                provider = result.provider
        else:
            provider = f"replay:khong_co_{result.provider or 'llm'}"

    return {"reason": reason, "provider": provider, "unsupported": unsupported}
