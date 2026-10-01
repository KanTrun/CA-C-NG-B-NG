"""HTTP router — Khung "AI phân tích" dùng chung cho các trang AI & tự động hoá.

Các trang Đề xuất thông minh / Hệ thống tự giải thích / Thử nghiệm an toàn /
Cẩm nang quán / Học từ phản hồi / Bộ kỹ năng AI / Hỏi quy trình / Hộp thư
ràng buộc trước đây chỉ hiện danh sách dữ liệu tất định (không LLM) — nhìn
như "chữ + nền" không có AI thật. Router này KHÔNG thay thuật toán tất định
(predict/explain/twin vẫn giữ ADR-008: tất định, không LLM), mà thêm một lớp
tường thuật bằng lời tự nhiên phía trên dữ liệu đó, dùng chung LLM cascade của
Copilot (`ca_agents.llm.complete`).

Endpoints:
- POST /api/v1/ai/insight — tóm tắt + khuyến nghị cho một trang cụ thể
- POST /api/v1/ai/insight/ask — hỏi đáp tự do dựa trên cùng ngữ cảnh trang đó

Khi không có provider LLM nào sẵn sàng (replay/CI), trả về tóm tắt tất định
dựng từ chính ngữ cảnh — không bịa số liệu, có nhãn rõ "không qua AI".
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Annotated, Any

from ca_agents.llm import complete, parse_json_object
from ca_playbook import list_luat
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _require_role
from ca_api.persist import kv_get, kv_set

router = APIRouter(tags=["ai_insight"])

_CACHE_TTL_S = 600.0  # 10 phút — tránh gọi LLM lại khi dữ liệu trang chưa đổi.

_PAGE_TITLES: dict[str, str] = {
    "de-xuat-thong-minh": "Đề xuất thông minh",
    "giai-thich": "Hệ thống tự giải thích",
    "thu-nghiem-an-toan": "Thử nghiệm an toàn (Digital Twin)",
    "cam-nang": "Cẩm nang quán",
    "ai-learning": "Học từ phản hồi",
    "skills": "Bộ kỹ năng AI",
    "sop": "Hỏi quy trình",
    "inbox": "Hộp thư ràng buộc",
}


def _safe_list(key: str, limit: int = 20) -> list[dict[str, Any]]:
    try:
        value = kv_get(key, [])
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)][:limit]
        if isinstance(value, dict):
            items = value.get("items")
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)][:limit]
        return []
    except Exception:
        return []


def _cam_nang_luat() -> list[dict[str, Any]]:
    """Luật cẩm nang từ nguồn THẬT (``list_luat``).

    Trước đây hai chỗ này đọc ``kv_get("cam_nang")`` — nhưng không route nào
    ghi vào khoá đó (``cam_nang.json`` mới là nơi lưu, qua ``save_luat``), nên
    ngữ cảnh luôn rỗng và panel tường thuật chỉ đọc được dữ liệu rác. Đọc thẳng
    ``list_luat()`` để AI thấy đúng luật đang có hiệu lực / đang chờ chốt.
    """
    try:
        return [x for x in list_luat() if isinstance(x, dict)]
    except Exception:
        return []


def _gather_context(page: str) -> dict[str, Any]:
    """Ngữ cảnh tất định đọc từ kv cho một trang — KHÔNG suy diễn, chỉ gom lại
    những gì đã có sẵn trên trang đó để LLM tường thuật lại bằng lời."""
    if page == "de-xuat-thong-minh":
        return {
            "mau_thanh_cong": _safe_list("ops_predict_patterns", 15),
            "luat_de_xuat": _safe_list("ops_predict_rules", 15),
        }
    if page == "giai-thich":
        return {"chuoi_nhan_qua": _safe_list("ops_explain_chains", 10)}
    if page == "thu-nghiem-an-toan":
        return {"kich_ban_da_chay": _safe_list("ops_twin_scenarios", 10)}
    if page == "cam-nang":
        return {"luat": _cam_nang_luat()[:20]}
    if page == "inbox":
        items = _safe_list("inbox_rang_buoc", 25)
        return {
            "cho_duyet": [x for x in items if x.get("trang_thai") == "cho_duyet"][:15],
            "da_xu_ly": [x for x in items if x.get("trang_thai") in {"duyet", "tu_choi"}][:10],
        }
    if page == "ai-learning":
        return {
            "de_xuat_luat": _safe_list("ops_predict_rules", 10),
            "chuoi_nhan_qua": _safe_list("ops_explain_chains", 10),
        }
    if page == "skills":
        return {}
    if page == "sop":
        return {
            "luat_dang_hieu_luc": [
                x for x in _cam_nang_luat() if x.get("trang_thai") == "hieu_luc"
            ][:20]
        }
    return {}


def _fingerprint(page: str, context: dict[str, Any]) -> str:
    raw = json.dumps({"page": page, "context": context}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _fallback_insight(page: str, context: dict[str, Any]) -> dict[str, Any]:
    """Tóm tắt tất định khi không có provider LLM nào sẵn sàng (replay/CI) —
    đếm số liệu thật từ `context`, không suy diễn nội dung."""
    counts = {k: len(v) for k, v in context.items() if isinstance(v, list)}
    diem_chinh = [f"{k.replace('_', ' ')}: {n} mục" for k, n in counts.items() if n]
    if not diem_chinh:
        diem_chinh = ["Chưa có dữ liệu nào để tóm tắt trên trang này."]
    return {
        "tom_tat": f"Tóm tắt tất định (chưa nối được AI) cho trang {_PAGE_TITLES.get(page, page)}.",
        "diem_chinh": diem_chinh,
        "khuyen_nghi": [],
        "canh_bao": [],
        "ai_generated": False,
    }


class InsightBody(BaseModel):
    page: str = Field(min_length=1, max_length=64)


class AskBody(BaseModel):
    page: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=1000)


_SYSTEM_PROMPT = (
    "Ban la tro ly van hanh quan ca phe 'Nhip Quan', noi tieng Viet tu nhien, ngan gon, "
    "khong dung thuat ngu ky thuat (khong noi JSON, snake_case, ma noi bo). "
    "Chi dua tren du lieu duoc cung cap trong phan NGU CANH, khong bia so lieu hay su kien khong co. "
    "Neu ngu canh rong, hay noi ro chua co du lieu de phan tich."
)


@router.post("/api/v1/ai/insight")
def ai_insight(
    body: InsightBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    page = body.page.strip()
    context = _gather_context(page)
    fp = _fingerprint(page, context)

    cache_key = f"ai_insight_cache:{page}"
    cached = kv_get(cache_key, None)
    if isinstance(cached, dict) and cached.get("fp") == fp and (time.time() - float(cached.get("at") or 0)) < _CACHE_TTL_S:
        return {"ok": True, "insight": cached.get("insight"), "cached": True}

    title = _PAGE_TITLES.get(page, page)
    user_prompt = (
        f"Trang: {title}.\n"
        f"Du lieu hien co (JSON, tieng Viet co dau da duoc dich nhan): "
        f"{json.dumps(context, ensure_ascii=False, default=str)[:6000]}\n\n"
        "Hay tra ve MOT object JSON dung dinh dang sau, khong them chu nao ngoai JSON:\n"
        '{"tom_tat": "1-2 cau tom tat tinh trang trang nay",'
        ' "diem_chinh": ["toi da 4 y ngan, moi y la mot cau"],'
        ' "khuyen_nghi": ["toi da 3 hanh dong nen lam tiep, moi y ngan"],'
        ' "canh_bao": ["chi neu neu du lieu cho thay rui ro ro rang, toi da 2 y, de trong [] neu khong co"]}'
    )

    result = complete(system=_SYSTEM_PROMPT, user=user_prompt, task="ai_insight", json_mode=True)
    if result.ok and result.text:
        parsed = parse_json_object(result.text)
        if parsed and isinstance(parsed.get("tom_tat"), str):
            insight = {
                "tom_tat": parsed.get("tom_tat", ""),
                "diem_chinh": [str(x) for x in (parsed.get("diem_chinh") or [])][:6],
                "khuyen_nghi": [str(x) for x in (parsed.get("khuyen_nghi") or [])][:6],
                "canh_bao": [str(x) for x in (parsed.get("canh_bao") or [])][:4],
                "ai_generated": True,
                "provider": result.provider,
            }
            kv_set(cache_key, {"fp": fp, "at": time.time(), "insight": insight})
            return {"ok": True, "insight": insight, "cached": False}

    insight = _fallback_insight(page, context)
    return {"ok": True, "insight": insight, "cached": False}


@router.post("/api/v1/ai/insight/ask")
def ai_insight_ask(
    body: AskBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    page = body.page.strip()
    context = _gather_context(page)
    title = _PAGE_TITLES.get(page, page)

    user_prompt = (
        f"Trang: {title}.\n"
        f"Du lieu hien co (JSON): {json.dumps(context, ensure_ascii=False, default=str)[:6000]}\n\n"
        f"Cau hoi cua nguoi quan ly: {body.question.strip()}\n"
        "Tra loi ngan gon bang tieng Viet tu nhien, chi dua tren du lieu tren; "
        "neu du lieu khong du de tra loi, noi ro dieu do."
    )
    result = complete(system=_SYSTEM_PROMPT, user=user_prompt, task="ai_insight_ask", json_mode=False)
    if result.ok and result.text.strip():
        return {"ok": True, "answer": result.text.strip(), "ai_generated": True, "provider": result.provider}

    if not context or all(not v for v in context.values()):
        answer = "Chưa có dữ liệu nào trên trang này để trả lời câu hỏi này."
    else:
        answer = "Chưa nối được AI trực tiếp lúc này. Xem các mục đã hiện trên trang để tự đối chiếu, hoặc thử lại sau."
    return {"ok": True, "answer": answer, "ai_generated": False}
