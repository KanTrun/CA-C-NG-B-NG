"""AG-MSG — 6 intents, two-tier (keyword then replay/overlap) + structured constraint extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from ca_agents.llm import complete, parse_json_object

if TYPE_CHECKING:
    from ca_agents.sensors.sensor_chain import SensorChain

INTENTS = (
    "doi_ca",
    "nhan_ca",
    "bao_tre",
    "cap_nhat_tkb",
    "xin_nghi",
    "khac",
)

_TIER1: list[tuple[str, tuple[str, ...]]] = [
    ("doi_ca", ("đổi ca", "doi ca", "đổi với", "doi voi", "swap")),
    ("nhan_ca", ("nhận ca", "nhan ca", "nhận giúp", "làm hộ", "lam ho")),
    ("bao_tre", ("trễ", "tre ", "muộn", "muon", "đến chậm", "den cham")),
    ("cap_nhat_tkb", ("tkb", "thời khoá", "thoi khoa", "học t", "hoc t", "cập nhật học")),
    ("xin_nghi", ("xin nghỉ", "xin nghi", "nghỉ ca", "nghi ca", "không đi làm", "khong di lam")),
]


@dataclass(frozen=True)
class MsgResult:
    intent: str
    tier: int
    do_tin_cay: float
    rang_buoc: dict[str, Any]


def _norm(text: str) -> str:
    return text.lower().strip()


def _extract_thu(t: str) -> str | None:
    patterns: list[tuple[str, str]] = [
        (r"(?:thứ\s*2|thu\s*2|\bt2\b|thứ\s*hai|thu\s*hai)", "T2"),
        (r"(?:thứ\s*3|thu\s*3|\bt3\b|thứ\s*ba|thu\s*ba)", "T3"),
        (r"(?:thứ\s*4|thu\s*4|\bt4\b|thứ\s*tư|thu\s*tu|thứ\s*bốn|thu\s*bon)", "T4"),
        (r"(?:thứ\s*5|thu\s*5|\bt5\b|thứ\s*năm|thu\s*nam)", "T5"),
        (r"(?:thứ\s*6|thu\s*6|\bt6\b|thứ\s*sáu|thu\s*sau)", "T6"),
        (r"(?:thứ\s*7|thu\s*7|\bt7\b|thứ\s*bảy|thu\s*bay)", "T7"),
        (r"(?:chủ\s*nhật|chu\s*nhat|\bcn\b)", "CN"),
    ]
    for pat, code in patterns:
        if re.search(pat, t, re.IGNORECASE):
            return code
    return None


def _extract_tuan(t: str, base_iso_week: str | None = None) -> str:
    m = re.search(r"\b(?:202\d-w(\d{1,2})|w(\d{1,2}))\b", t, re.IGNORECASE)
    if m:
        w_num = int(m.group(1) or m.group(2))
        base_year = (base_iso_week or "2026-W01").split("-W")[0]
        return f"{base_year}-W{w_num:02d}"

    base = base_iso_week or "2026-W01"
    base_m = re.search(r"(\d{4})-W(\d{1,2})", base)
    year = int(base_m.group(1)) if base_m else 2026
    current_w = int(base_m.group(2)) if base_m else 1

    def _next_week(y: int, w: int) -> str:
        """W+1 có xử lý tràn năm (W52/W53 → năm sau, W01).

        Không xử lý tràn sẽ sinh "2026-W53" (không tồn tại) hoặc "2026-W54",
        khiến ràng buộc ghi vào tuần vô nghĩa.
        """
        try:
            last_week = date(y, 12, 28).isocalendar().week
        except ValueError:
            last_week = 52
        if w >= last_week:
            return f"{y + 1}-W01"
        return f"{y}-W{w + 1:02d}"

    if any(k in t for k in ("tuần sau", "tuan sau", "tuần tới", "tuan toi")):
        return _next_week(year, current_w)
    if any(k in t for k in ("tuần này", "tuan nay")):
        return f"{year}-W{current_w:02d}"
    return base


def _extract_hours(t: str) -> tuple[str | None, str | None]:
    # Range: 7h - 11h30, 07:00 - 12:00, 7h đến 12h
    range_m = re.search(
        r"(\d{1,2})(?:[:h](\d{2})?)\s*(?:đến|-|tới)\s*(\d{1,2})(?:[:h](\d{2})?)",
        t,
        re.IGNORECASE,
    )
    if range_m:
        h1 = int(range_m.group(1))
        m1 = int(range_m.group(2) or 0)
        h2 = int(range_m.group(3))
        m2 = int(range_m.group(4) or 0)
        return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"

    if "ca sáng" in t or "ca sang" in t:
        return "07:00", "12:00"
    if "ca chiều" in t or "ca chieu" in t:
        return "12:00", "17:00"
    if "ca tối" in t or "ca toi" in t:
        return "17:00", "22:00"

    # Điểm mốc trễ: đến 9h, trễ tới 9:30
    late_m = re.search(r"(?:đến|tới|den|toi)\s*(\d{1,2})(?:[:h](\d{2})?)", t, re.IGNORECASE)
    if late_m:
        h = int(late_m.group(1))
        m = int(late_m.group(2) or 0)
        return "07:00", f"{h:02d}:{m:02d}"

    return None, None


def _extract_ca_id(t: str) -> str | None:
    m = re.search(r"\b(w\d+_c\d+|c\d+)\b", t, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_partner(
    t: str, staff: list[dict[str, str]] | None = None
) -> tuple[str | None, bool]:
    """Trả về (partner_id, is_ambiguous)."""
    explicit_nv = re.search(r"\b(nv_\d+)\b", t, re.IGNORECASE)
    if explicit_nv:
        return explicit_nv.group(1).lower(), False

    m = re.search(
        r"(?:với|voi|cho|cùng|cung)\s+([a-zA-Z0-9_\u00C0-\u1EF9]+)",
        t,
        re.IGNORECASE,
    )
    if not m:
        return None, False

    name = m.group(1).strip()
    if staff:
        norm_name = name.lower()
        matches = [
            s
            for s in staff
            if norm_name == (s.get("ten") or s.get("display_name") or "").lower()
            or norm_name in (s.get("ten") or s.get("display_name") or "").lower().split()
            or norm_name == s.get("id", "").lower()
            or norm_name == s.get("nv_id", "").lower()
        ]
        if len(matches) > 1:
            return None, True
        if len(matches) == 1:
            return matches[0].get("nv_id") or matches[0].get("id"), False
        return None, True

    return name, False


def classify(
    text: str,
    *,
    mode: str = "replay",
    staff: list[dict[str, str]] | None = None,
    base_iso_week: str | None = None,
) -> MsgResult:
    t = _norm(text)
    matched_intent: str | None = None
    for intent, keys in _TIER1:
        if any(k in t for k in keys):
            matched_intent = intent
            break

    if not matched_intent:
        if mode.strip().lower() == "live":
            result = complete(
                system=(
                    "Phan loai tin nhan nhan vien quan. Tra JSON gom intent la mot trong "
                    f"{list(INTENTS)} va confidence tu 0 den 1. Khong suy dien rang buoc."
                ),
                user=text,
                task="text:ag_msg",
                json_mode=True,
            )
            parsed = parse_json_object(result.text) if result.ok else None
            intent = str((parsed or {}).get("intent") or "")
            confidence = (parsed or {}).get("confidence")
            if intent in INTENTS and intent != "khac" and isinstance(confidence, (int, float)):
                bounded_confidence = max(0.0, min(float(confidence), 1.0))
                return MsgResult(
                    intent=intent,
                    tier=2,
                    do_tin_cay=bounded_confidence,
                    rang_buoc={"nguon": "llm", "can_xac_minh": True},
                )
        return MsgResult(
            intent="khac",
            tier=2,
            do_tin_cay=0.55,
            rang_buoc={"nguon": "tier2_fallback", "can_xac_minh": True},
        )

    thu = _extract_thu(t)
    tuan_id = _extract_tuan(t, base_iso_week)
    start, end = _extract_hours(t)
    ca_id = _extract_ca_id(t)
    partner_id, is_ambiguous = _extract_partner(t, staff)

    rang_buoc: dict[str, Any] = {
        "nguon": "keyword",
        "tuan_id": tuan_id,
    }
    if thu:
        rang_buoc["thu"] = thu
    if start and end:
        rang_buoc["start"] = start
        rang_buoc["end"] = end
    if ca_id:
        rang_buoc["ca_id"] = ca_id
    if partner_id:
        rang_buoc["doi_tac"] = partner_id
    if is_ambiguous:
        rang_buoc["doi_tac_khong_ro"] = True

    _EMERGENCY_KEYS = (
        "gấp", "gap", "khẩn", "khan", "ốm", "om", "sốt", "sot",
        "bệnh", "benh", "cấp cứu", "cap cuu", "tai nạn", "tai nan",
        "nhập viện", "nhap vien", "đột xuất", "dot xuat",
    )
    if any(k in t for k in _EMERGENCY_KEYS):
        rang_buoc["khan_cap"] = True

    can_xac_minh = False
    do_tin_cay = 0.86

    if matched_intent == "xin_nghi":
        if not thu:
            can_xac_minh = True
            do_tin_cay = 0.55
    elif matched_intent in {"cap_nhat_tkb", "bao_tre"}:
        if not thu or not (start and end):
            can_xac_minh = True
            do_tin_cay = 0.55
    elif matched_intent in {"doi_ca", "nhan_ca"}:
        if not ca_id or not partner_id or is_ambiguous:
            can_xac_minh = True
            do_tin_cay = 0.60

    rang_buoc["can_xac_minh"] = can_xac_minh

    return MsgResult(
        intent=matched_intent,
        tier=1,
        do_tin_cay=do_tin_cay,
        rang_buoc=rang_buoc,
    )


def classify_nang_cao(
    text: str,
    sensor_chain: SensorChain | None = None,
    *,
    mode: str = "replay",
    staff: list[dict[str, str]] | None = None,
    base_iso_week: str | None = None,
) -> MsgResult:
    """Phân loại nâng cao: keyword/LLM tier trước, SensorChain bổ sung sau (opt-in).

    Gọi `classify()` để phân loại tất định rồi dùng SensorChain (JEV →
    RegexSensor fallback) để bổ sung vào `rang_buoc`:
    - `khan_cap_thuc_su ≥ 0.60` → set `rang_buoc["khan_cap"] = True`
      ngay cả khi keyword tier-1 chưa bắt được (ngầm hiểu, ngữ cảnh).
    - `co_gang_ghi_de_chi_dan ≥ 0.50` → set `rang_buoc["injection_attempt"] = True`
      để tầng gọi ngăn auto-xử lý tin nhắn này.

    Nguyên tắc đơn điệu: SensorChain chỉ *thêm* flag, không bao giờ xóa flag
    mà tier-1/keyword đã đặt (vd: khan_cap đã True thì vẫn True).
    Khi cả hai cảm biến thất bại → giữ kết quả classify() gốc, ghi vào rang_buoc.

    Args:
        text: Nội dung tin nhắn nhân viên.
        sensor_chain: SensorChain đã khởi tạo. None → tạo mới chỉ Regex.
        mode / staff / base_iso_week: truyền thẳng cho classify().
    """
    base = classify(text, mode=mode, staff=staff, base_iso_week=base_iso_week)

    # Import lazy tránh vòng lặp phụ thuộc.
    from ca_agents.sensors.msg_questions import MSG_QUESTIONS
    from ca_agents.sensors.sensor_chain import SensorChain

    chain = sensor_chain
    if chain is None:
        chain = SensorChain()  # chỉ Regex (JEV chưa bật)

    result = chain.evaluate(text, "msg_classify", MSG_QUESTIONS)

    # Copy rang_buoc để không mutate dict gốc.
    rang_buoc = dict(base.rang_buoc)

    # Cả hai cảm biến thất bại → giữ nguyên, ghi chú.
    if result.both_failed:
        rang_buoc["sensor_chain_failed"] = True
        return MsgResult(
            intent=base.intent,
            tier=base.tier,
            do_tin_cay=base.do_tin_cay,
            rang_buoc=rang_buoc,
        )

    if result.fallback_used:
        rang_buoc["sensor_source"] = result.source

    signals = result.signals
    emergency = signals.get("khan_cap_thuc_su")
    injection = signals.get("co_gang_ghi_de_chi_dan")

    # Khẩn cấp thật sự: bổ sung nếu chưa có (đơn điệu — không gỡ nếu đã True).
    if emergency is not None and float(emergency.value) >= 0.60:
        rang_buoc["khan_cap"] = True  # OR với giá trị cũ nếu đã có

    # Injection: luôn cộng thêm flag (không gỡ nếu đã True).
    if injection is not None and float(injection.value) >= 0.50:
        rang_buoc["injection_attempt"] = True

    return MsgResult(
        intent=base.intent,
        tier=base.tier,
        do_tin_cay=base.do_tin_cay,
        rang_buoc=rang_buoc,
    )
