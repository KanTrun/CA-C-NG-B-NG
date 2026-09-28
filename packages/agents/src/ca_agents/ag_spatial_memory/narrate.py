"""Hồn quán — tầng DIỄN ĐẠT tour bằng LLM (không thêm sự kiện).

Giữ nguyên nguyên tắc grounded của `tour.py`: các bước, anchor và ký ức đã
được chọn TẤT ĐỊNH. Tầng này chỉ viết lại câu chữ cho tự nhiên hơn khi
`CA_AGENT_MODE=live`; replay/không key → giữ nguyên narration tất định.

Cổng chống bịa: câu chữ LLM phải KHÔNG chứa con số lạ và không dùng khẳng định
tuyệt đối; nếu vi phạm → giữ bản tất định (giống `ag_quanverse.assistant`).
"""

from __future__ import annotations

import re
from typing import Any

from ca_agents.llm import agent_mode, complete

_SYSTEM_PROMPT = (
    "Bạn là hướng dẫn viên của quán cà phê. Chỉ được diễn đạt lại ĐÚNG các bước "
    "và ký ức trong DỮ KIỆN. Không bịa thêm chi tiết, không thêm số, không dùng "
    "lời khẳng định tuyệt đối. Tiếng Việt, tự nhiên, mỗi bước một câu."
)

_ABSOLUTE_HINTS = ("chắc chắn 100%", "luôn luôn", "không bao giờ sai")


def _numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d[\d.,]*", text or "")}


def enrich_narration(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trả bản sao `steps` với `narrative` được diễn đạt lại khi live.

    Mọi thứ khác (anchor_id, citation) giữ NGUYÊN — chỉ câu chữ đổi.
    """
    if agent_mode() != "live" or not steps:
        return steps

    facts = [
        {"buoc": i + 1, "anchor": s.get("anchor_id"), "mo_ta": s.get("narrative")}
        for i, s in enumerate(steps)
    ]
    allowed = _numbers_in(str(facts))
    result = complete(
        system=_SYSTEM_PROMPT,
        user=f"DỮ KIỆN (JSON):\n{facts}\n\nViết lại lời dẫn cho từng bước, đánh số rõ.",
        task="text:spatial_tour",
        json_mode=False,
    )
    if not result.ok or not result.text.strip():
        return steps
    text = result.text
    # Chặn số lạ / khẳng định tuyệt đối → giữ bản tất định.
    low = text.lower()
    if any(h in low for h in _ABSOLUTE_HINTS):
        return steps
    if any(n not in allowed for n in _numbers_in(text)):
        return steps

    out = [dict(s) for s in steps]
    # Gắn lời dẫn LLM vào bước CUỐI như đoạn tổng kết (an toàn: không cần khớp
    # từng bước với từng dòng LLM, tránh ghép sai).
    if out:
        out[-1]["narrative"] = f"{out[-1].get('narrative', '')} — {text.strip()}"
        out[-1]["narration_provider"] = result.provider
    return out
