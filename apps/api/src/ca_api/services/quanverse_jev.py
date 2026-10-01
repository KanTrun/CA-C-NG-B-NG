"""Quanverse — JEV judge/rank (System One) + fallback tất định.

Hợp đồng với người dùng:
- JEV KHÔNG tạo dữ kiện. `judge()` từ chối khi evidence `trong`.
- JEV chỉ RANK trong closed-set A–E do Evidence Builder dựng.
- Không key / timeout / lỗi mạng → fallback tất định, provider=`fallback`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

_VERDICTS = ("binh_thuong", "theo_doi", "can_xu_ly", "khan_cap")

_NHAN_VI = {
    "binh_thuong": "Bình thường",
    "theo_doi": "Cần theo dõi",
    "can_xu_ly": "Cần xử lý",
    "khan_cap": "Khẩn cấp",
}


def _fallback_judge(evidence: dict[str, Any]) -> dict[str, Any]:
    state = evidence.get("state") or {}
    coverage = evidence.get("coverage") or {}
    thieu = [k for k, v in coverage.items() if v != "ok"]
    pha = str(state.get("quay_pha_canh_bao") or "binh_thuong")
    treo = int(state.get("viec_treo_mo") or 0)
    ton = list(state.get("ton_duoi_nguong") or [])
    nv = state.get("nhan_vien_truc")

    if pha == "qua_tai" or treo > 0 and pha == "qua_tai":
        verdict, p = "can_xu_ly", 0.91
    elif pha == "qua_tai":
        verdict, p = "can_xu_ly", 0.88
    elif pha == "chu_y" or ton or (isinstance(nv, int) and nv < 3):
        verdict, p = "theo_doi", 0.72
    elif thieu:
        verdict, p = "theo_doi", 0.64
    else:
        verdict, p = "binh_thuong", 0.68

    if treo >= 3 and verdict == "can_xu_ly":
        verdict, p = "khan_cap", 0.86

    return {"verdict": verdict, "p": p, "provider": "fallback"}


def _fallback_rank(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    cands = [c for c in (evidence.get("candidates") or []) if c.get("eligible")]
    if not cands:
        cands = [c for c in (evidence.get("candidates") or []) if c.get("id") == "E"]
    # Thứ tự nghiêm trọng: C (pha) > D (treo) > B (kho) > A (lịch) > E.
    thu_tu = {"C": 0, "D": 1, "B": 2, "A": 3, "E": 4}
    cands = sorted(cands, key=lambda c: thu_tu.get(str(c.get("id")), 9))
    tong = len(cands)
    out = []
    for i, c in enumerate(cands[:3]):
        # Phân phối giảm dần, chuẩn hoá tổng = 1 trong top.
        w = (tong - i) / sum(range(1, tong + 1)) if tong else 1.0
        out.append({"id": str(c.get("id")), "p": round(w, 2)})
    s = sum(x["p"] for x in out) or 1.0
    for x in out:
        x["p"] = round(x["p"] / s, 2)
    return out


def _goi_jev_http(payload: dict[str, Any], timeout_s: float) -> dict[str, Any] | None:
    """Thử gọi JEV API thật. Trả None khi chưa cấu hình hoặc lỗi (để fallback)."""
    key = (os.environ.get("JEV_API_KEY") or "").strip()
    base = (os.environ.get("JEV_BASE_URL") or "https://api.typesafe.ai/v1/jev").strip()
    if not key:
        return None
    try:
        req = urllib.request.Request(
            base,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def judge(evidence: dict[str, Any]) -> dict[str, Any]:
    """JEV judge/rank. KHÔNG gọi khi evidence `trong`."""
    trang_thai = str(evidence.get("trang_thai") or "")
    coverage = evidence.get("coverage") or {}
    if trang_thai == "trong":
        return {
            "goi_jev": False,
            "ly_do": "insufficient",
            "verdict": None,
            "p": None,
            "provider": "none",
            "ranking": [],
            "message": "Chưa đủ dữ liệu — không gọi JEV.",
        }
    state = evidence.get("state") or {}
    eligible = [c.get("id") for c in (evidence.get("candidates") or []) if c.get("eligible")]
    timeout_s = float(os.environ.get("JEV_TIMEOUT_MS", "600")) / 1000.0
    t0 = time.monotonic()
    raw = _goi_jev_http(
        {
            "model": os.environ.get("JEV_MODEL", "jev-latest"),
            "verdict_choice": list(_VERDICTS),
            "rank_choice": eligible or ["E"],
            "state": state,
            "coverage": coverage,
        },
        timeout_s,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    if isinstance(raw, dict) and raw.get("verdict") in _VERDICTS:
        try:
            p = float(raw.get("p", 0.0))
            p = min(0.99, max(0.01, p))
        except (TypeError, ValueError):
            p = 0.6
        ranking = raw.get("ranking") if isinstance(raw.get("ranking"), list) else _fallback_rank(evidence)
        return {
            "goi_jev": True,
            "verdict": raw["verdict"],
            "verdict_label": _NHAN_VI[raw["verdict"]],
            "p": round(p, 2),
            "provider": "jev",
            "latency_ms": latency_ms,
            "ranking": ranking[:3],
            "thieu": [k for k, v in coverage.items() if v != "ok"],
        }
    fb = _fallback_judge(evidence)
    return {
        "goi_jev": True,
        "verdict": fb["verdict"],
        "verdict_label": _NHAN_VI[fb["verdict"]],
        "p": fb["p"],
        "provider": fb["provider"],
        "latency_ms": latency_ms,
        "ranking": _fallback_rank(evidence),
        "thieu": [k for k, v in coverage.items() if v != "ok"],
    }


def nhan_verdict(verdict: str | None) -> str:
    return _NHAN_VI.get(str(verdict or ""), "Chưa đánh giá")


def route_intent(question: str) -> dict[str, Any]:
    """Route intent hỏi-AI về đúng evidence. Keyword tất định (không mạng)."""
    q = (question or "").lower()
    if any(k in q for k in ("pha", "quá tải", "qua tai", "kẹt", "ket", "đơn")):
        return {"intent": "qua_tai", "provider": "fallback"}
    if any(k in q for k in ("nhân sự", "nhan su", "lịch", "lich", "ca ", "điều người")):
        return {"intent": "nhan_su", "provider": "fallback"}
    if any(k in q for k in ("kho", "tồn", "ton", "sữa", "sua", "nguyên liệu")):
        return {"intent": "ton_kho", "provider": "fallback"}
    if any(k in q for k in ("thời tiết", "thoi tiet", "mưa", "mua")):
        return {"intent": "thoi_tiet", "provider": "fallback"}
    return {"intent": "chung", "provider": "fallback"}
