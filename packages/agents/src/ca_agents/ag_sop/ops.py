"""Ngữ cảnh vận hành và guard chủ đề cho AG-SOP."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_VN = ZoneInfo("Asia/Ho_Chi_Minh")
_THU = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


@dataclass
class SopOpsContext:
    ngay: str
    thu: str
    khung: str

    def as_dict(self) -> dict[str, str]:
        return {"ngay": self.ngay, "thu": self.thu, "khung": self.khung}


def default_ops_context(*, now: datetime | None = None) -> SopOpsContext:
    dt = now or datetime.now(_VN)
    thu = _THU[dt.weekday()]
    h = dt.hour
    khung = "sang" if h < 11 else "chieu" if h < 17 else "toi"
    return SopOpsContext(ngay=dt.date().isoformat(), thu=thu, khung=khung)


def ops_context_from_dict(raw: dict[str, Any] | None) -> SopOpsContext | None:
    if not raw:
        return None
    thu = str(raw.get("thu") or "").strip()
    khung = str(raw.get("khung") or "").strip()
    ngay = str(raw.get("ngay") or "").strip()
    if not thu and not khung:
        return None
    base = default_ops_context()
    return SopOpsContext(
        ngay=ngay or base.ngay,
        thu=thu or base.thu,
        khung=khung or base.khung,
    )


def _law_cond(law: dict[str, Any]) -> dict[str, Any]:
    cond = law.get("tham_so_loi") or law.get("dieu_kien") or {}
    return cond if isinstance(cond, dict) else {}


def law_has_temporal_cond(law: dict[str, Any]) -> bool:
    cond = _law_cond(law)
    return any(cond.get(k) for k in ("thu", "khung", "vi_tri"))


def law_matches_ops(law: dict[str, Any], ctx: SopOpsContext) -> bool:
    cond = _law_cond(law)
    if cond.get("thu") and str(cond["thu"]) != ctx.thu:
        return False
    if cond.get("khung") and str(cond["khung"]) != ctx.khung:
        return False
    return True


def filter_luat_for_sop(
    luat: list[dict[str, Any]],
    ctx: SopOpsContext,
    *,
    question: str = "",
) -> list[dict[str, Any]]:
    """Luật không điều kiện thời gian + luật khớp ca/ngày hiện tại.

    ``question``: nếu câu hỏi tự nêu đích danh thứ/khung giờ (vd "Thứ Bảy ca
    chiều…") mà luật khớp phần nêu đó thì vẫn trả lời, dù ngữ cảnh ca hiện tại
    khác — người hỏi đang hỏi về thời điểm khác, không phải ca đang chạy.
    """
    hint_thu, hint_khung = question_time_hint(question) if question else (None, None)
    out: list[dict[str, Any]] = []
    for law in luat:
        if law.get("trang_thai") != "hieu_luc":
            continue
        if not law_has_temporal_cond(law) or law_matches_ops(law, ctx):
            out.append(law)
        elif question and law_matches_hint(law, hint_thu, hint_khung):
            out.append(law)
    return out


_THU_HINTS: tuple[tuple[str, str], ...] = (
    ("chủ nhật", "CN"),
    ("chu nhat", "CN"),
    ("thứ bảy", "T7"),
    ("thu bay", "T7"),
    ("thứ 7", "T7"),
    ("thứ sáu", "T6"),
    ("thu sau", "T6"),
    ("thứ 6", "T6"),
    ("thứ năm", "T5"),
    ("thu nam", "T5"),
    ("thứ 5", "T5"),
    ("thứ tư", "T4"),
    ("thu tu", "T4"),
    ("thứ 4", "T4"),
    ("thứ ba", "T3"),
    ("thu ba", "T3"),
    ("thứ 3", "T3"),
    ("thứ hai", "T2"),
    ("thu hai", "T2"),
    ("thứ 2", "T2"),
)

_KHUNG_HINTS: tuple[tuple[str, str], ...] = (
    ("ca sáng", "sang"),
    ("buổi sáng", "sang"),
    ("sáng nay", "sang"),
    ("ca chiều", "chieu"),
    ("buổi chiều", "chieu"),
    ("chiều nay", "chieu"),
    ("ca tối", "toi"),
    ("buổi tối", "toi"),
    ("tối nay", "toi"),
)


def question_time_hint(question: str) -> tuple[str | None, str | None]:
    """Đọc thứ + khung giờ mà câu hỏi nêu đích danh, nếu có."""
    q = question.lower()
    thu = next((m for p, m in _THU_HINTS if p in q), None)
    if thu is None:
        m = re.search(r"\bt[\- ]?([2-7])\b", q)
        if m:
            thu = f"T{m.group(1)}"
        elif re.search(r"\bcn\b", q):
            thu = "CN"
    khung = next((k for p, k in _KHUNG_HINTS if p in q), None)
    return thu, khung


def law_matches_hint(law: dict[str, Any], thu: str | None, khung: str | None) -> bool:
    """Luật khớp phần thời gian câu hỏi nêu — cond nào nêu thì phải đúng."""
    cond = _law_cond(law)
    if cond.get("thu") and str(cond["thu"]) != (thu or ""):
        return False
    if cond.get("khung") and str(cond["khung"]) != (khung or ""):
        return False
    return True


def topic_blocked(question: str, blob: str) -> bool:
    """Chặn nhầm chủ đề (máy lạnh/điều hòa ≠ tủ lạnh)."""
    q = question.lower()
    b = blob.lower()
    ac_q = any(p in q for p in ("máy lạnh", "may lanh", "điều hòa", "dieu hoa"))
    fridge_b = "tủ lạnh" in b or "tu lanh" in b or "nhiet_do_tu_lanh" in b
    if ac_q and fridge_b and not any(p in b for p in ("máy lạnh", "may lanh", "điều hòa", "dieu hoa")):
        return True
    fridge_q = "tủ lạnh" in q or "tu lanh" in q
    ac_b = any(p in b for p in ("máy lạnh", "may lanh", "điều hòa"))
    if fridge_q and ac_b and "tủ lạnh" not in b and "tu lanh" not in b:
        return True
    return False


def ac_question_without_source(question: str, blob: str) -> bool:
    q = question.lower()
    if not any(p in q for p in ("máy lạnh", "may lanh", "điều hòa", "dieu hoa")):
        return False
    b = blob.lower()
    return not any(p in b for p in ("máy lạnh", "may lanh", "điều hòa", "dieu hoa"))


@dataclass
class SopAnswerExtras:
    canh_bao: str = ""
    viec_lam: str = ""
    phieu_ma: str = ""
    phieu_buoc_ma: str = ""
    ngu_canh: dict[str, str] = field(default_factory=dict)
