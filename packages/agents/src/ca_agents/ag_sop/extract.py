"""AG-SOP — answer only from phiếu YAML + approved laws. Else chưa có."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ca_agents.ag_sop.ops import (
    SopOpsContext,
    ac_question_without_source,
    default_ops_context,
    filter_luat_for_sop,
    topic_blocked,
)
from ca_agents.llm import agent_mode, complete, parse_json_object

_SOP_SYSTEM = """Bạn là trợ lý cẩm nang NHỊP QUÁN.
Chỉ trả lời từ NGỮ CẢNH được cung cấp (bước phiếu + luật hiệu lực + ngữ cảnh ca).
Trả JSON: {"cau_tra_loi": "...", "trich_dan": ["phieu:ma", "luat:id"], "chua_co": false}
Câu trả lời gồm: (1) tóm tắt ngắn, (2) việc cần làm ngay, (3) ngưỡng/điều kiện nếu có.
Nếu ngữ cảnh không đủ hoặc câu hỏi khác chủ đề nguồn: {"cau_tra_loi": "Chưa có trong cẩm nang của quán, hãy hỏi quản lý.", "trich_dan": [], "chua_co": true}
Mỗi trich_dan phải trỏ tới mã có trong ngữ cảnh. Cấm bịa quy trình."""

_STOP = frozenset(
    {
        "mấy",
        "giờ",
        "phải",
        "là",
        "được",
        "gì",
        "như",
        "thế",
        "nào",
        "khi",
        "cho",
        "trong",
        "và",
        "có",
        "không",
        "bao",
        "nhiêu",
        "làm",
        "sao",
        "một",
        "các",
        "theo",
        "của",
        "về",
        "với",
        "từ",
        "đến",
        "hay",
        "hoặc",
        "này",
        "đó",
        "để",
        "ra",
        "vào",
        "trên",
        "dưới",
        "đã",
        "sẽ",
        "cần",
        "nên",
        "thì",
        "mà",
        "bị",
        "hướng",
        "dẫn",
        "giúp",
        "tôi",
        "biết",
    }
)

_PHRASES = (
    "tủ lạnh",
    "tủ đông",
    "máy pha",
    "vệ sinh",
    "kiểm kê",
    "bàn giao",
    "đóng quán",
)


@dataclass
class SopAnswer:
    cau_tra_loi: str
    trich_dan: list[str]
    chua_co: bool
    mode: str = "keyword"
    provider: str = ""
    do_tin: float = 0.0
    canh_bao: str = ""
    viec_lam: str = ""
    phieu_ma: str = ""
    phieu_buoc_ma: str = ""
    ngu_canh: dict[str, str] = field(default_factory=dict)


def _words(text: str) -> list[str]:
    return re.findall(
        r"[\wàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]+",
        text.lower(),
    )


def _question_tokens(question: str) -> list[str]:
    return [w for w in _words(question) if len(w) >= 2 and w not in _STOP]


def _unmatched_ratio(q_tokens: list[str], blob_words: set[str]) -> float:
    long_tokens = [t for t in q_tokens if len(t) >= 3]
    if not long_tokens:
        return 0.0
    unmatched = sum(1 for t in long_tokens if t not in blob_words)
    return unmatched / len(long_tokens)


def _score_blob(question: str, q_tokens: list[str], blob: str) -> float:
    if topic_blocked(question, blob) or ac_question_without_source(question, blob):
        return 0.0
    if not q_tokens:
        return 0.0
    blob_words = set(_words(blob))
    q_lower = question.lower()
    token_hits = sum(1 for t in q_tokens if t in blob_words)
    ratio = token_hits / len(q_tokens)
    phrase_bonus = sum(0.25 for p in _PHRASES if p in q_lower and p in blob.lower())
    orphan_penalty = _unmatched_ratio(q_tokens, blob_words) * 0.5
    score = max(0.0, ratio + phrase_bonus - orphan_penalty)
    if phrase_bonus >= 0.5 and ratio >= 0.3:
        score = max(score, 0.62)
    if _unmatched_ratio(q_tokens, blob_words) >= 0.5:
        score *= 0.55
    return score


def _format_buoc_answer(b: dict[str, Any]) -> tuple[str, str, str, str]:
    ten = str(b.get("ten") or "")
    phieu_ten = str(b.get("phieu_ten") or b.get("phieu") or "quy trình")
    phieu_ma = str(b.get("phieu") or "")
    buoc_ma = str(b.get("ma") or "")
    ng = b.get("nguong") or {}
    lines = [f"Tóm tắt: {ten}."]
    viec = f"Việc làm: mở phiếu «{phieu_ten}» và hoàn thành bước «{ten}» (trang /phieu)."
    if ng and ng.get("min") is not None and ng.get("max") is not None:
        lines.append(f"Ngưỡng: {ng.get('min')}–{ng.get('max')}°C — nếu lệch, báo quản lý ngay.")
    lines.append(viec)
    return "\n".join(lines), viec, phieu_ma, buoc_ma


def _format_law_answer(law: dict[str, Any], ctx: SopOpsContext) -> tuple[str, str]:
    cau = str(law.get("cau") or "")
    cond = law.get("tham_so_loi") or law.get("dieu_kien") or {}
    extra = ""
    if isinstance(cond, dict):
        thu_c = str(cond.get("thu") or "")
        khung_c = str(cond.get("khung") or "")
        if thu_c and khung_c:
            extra = f" (áp dụng {thu_c} ca {khung_c})"
        elif thu_c:
            extra = f" (áp dụng {thu_c})"
        elif khung_c:
            extra = f" (áp dụng ca {khung_c})"
    tom_tat = f"Tóm tắt: {cau}{extra}."
    viec = "Việc làm: tuân thủ luật trên trong ca hiện tại; nếu không chắc, hỏi quản lý."
    return f"{tom_tat}\n{viec}", viec


def _chua_co_answer(
    *,
    ctx: SopOpsContext,
    reason: str = "",
) -> SopAnswer:
    msg = "Chưa có trong cẩm nang của quán, hãy hỏi quản lý."
    if reason:
        msg = f"{reason} {msg}"
    return SopAnswer(
        cau_tra_loi=msg,
        trich_dan=[],
        chua_co=True,
        mode="keyword",
        provider="",
        do_tin=0.0,
        ngu_canh=ctx.as_dict(),
    )


def _build_context(
    buoc: list[dict[str, Any]],
    luat: list[dict[str, Any]],
    ctx: SopOpsContext,
) -> tuple[str, set[str]]:
    valid: set[str] = set()
    lines: list[str] = [
        "=== Ngữ cảnh ca ===",
        f"ngay={ctx.ngay} thu={ctx.thu} khung={ctx.khung}",
        "=== Bước phiếu ===",
    ]
    for b in buoc:
        ma = str(b.get("ma") or "")
        ten = str(b.get("ten") or "")
        phieu = str(b.get("phieu_ten") or b.get("phieu") or "")
        if ma:
            valid.add(f"phieu:{ma}")
        ng = b.get("nguong") or {}
        extra = f" ngưỡng {ng.get('min')}–{ng.get('max')}" if ng else ""
        prefix = f"[{phieu}] " if phieu else ""
        lines.append(f"- phieu:{ma} | {prefix}{ten}{extra}")
    lines.append("=== Luật hiệu lực (đã lọc theo ca) ===")
    for law in luat:
        if law.get("trang_thai") != "hieu_luc":
            continue
        lid = str(law.get("id") or "")
        cau = str(law.get("cau") or "")
        if lid:
            valid.add(f"luat:{lid}")
        lines.append(f"- luat:{lid} | {cau}")
    return "\n".join(lines), valid


def _answer_keyword(
    question: str,
    *,
    buoc: list[dict[str, Any]],
    luat: list[dict[str, Any]],
    ctx: SopOpsContext,
) -> SopAnswer:
    q_tokens = _question_tokens(question)
    q_lower = question.lower()
    if any(p in q_lower for p in ("máy lạnh", "may lanh", "điều hòa", "dieu hoa")):
        if not any(
            ac_question_without_source(question, f"{b.get('ma')} {b.get('ten')}") is False
            and not topic_blocked(question, f"{b.get('ma')} {b.get('ten')}")
            for b in buoc
        ) and not any(
            not topic_blocked(question, str(law.get("cau") or ""))
            and not ac_question_without_source(question, str(law.get("cau") or ""))
            for law in luat
        ):
            return _chua_co_answer(
                ctx=ctx,
                reason="Cẩm nang chưa có quy trình máy lạnh/điều hòa.",
            )

    best_buoc: tuple[float, dict[str, Any]] | None = None
    best_law: tuple[float, dict[str, Any]] | None = None

    for b in buoc:
        ma = str(b.get("ma") or "")
        ten = str(b.get("ten") or "")
        blob = f"{ma} {ten}"
        score = _score_blob(question, q_tokens, blob)
        if score < 0.45:
            continue
        blob_words = set(_words(blob))
        if _unmatched_ratio(q_tokens, blob_words) >= 0.5 and score < 0.85:
            continue
        if best_buoc is None or score > best_buoc[0]:
            best_buoc = (score, b)

    for law in luat:
        if law.get("trang_thai") != "hieu_luc":
            continue
        cau = str(law.get("cau") or "")
        lid = str(law.get("id") or "")
        blob = f"{lid} {cau}"
        score = _score_blob(question, q_tokens, blob)
        if score < 0.45:
            continue
        blob_words = set(_words(blob))
        if _unmatched_ratio(q_tokens, blob_words) >= 0.5 and score < 0.85:
            continue
        if best_law is None or score > best_law[0]:
            best_law = (score, law)

    if best_buoc is None and best_law is None:
        return _chua_co_answer(ctx=ctx)

    picks: list[tuple[float, str, str, str, str, str]] = []
    if best_buoc:
        score, b = best_buoc
        cau, viec, phieu_ma, buoc_ma = _format_buoc_answer(b)
        picks.append((score, cau, viec, f"phieu:{b.get('ma')}", phieu_ma, buoc_ma))
    if best_law:
        score, law = best_law
        cau, viec = _format_law_answer(law, ctx)
        picks.append((score, cau, viec, f"luat:{law.get('id')}", "", ""))
    picks.sort(key=lambda x: x[0], reverse=True)
    top_score, top_cau, top_viec, top_cite, phieu_ma, buoc_ma = picks[0]
    trich_dan = [c for _, _, _, c, _, _ in picks[:2]]
    seen: list[str] = []
    for c in trich_dan:
        if c not in seen:
            seen.append(c)
    orphan = 0.0
    if best_buoc:
        b = best_buoc[1]
        orphan = _unmatched_ratio(q_tokens, set(_words(f"{b.get('ma')} {b.get('ten')}")))
    canh_bao = ""
    do_tin = round(min(0.9, top_score), 2)
    if orphan >= 0.25:
        canh_bao = "Câu hỏi có thể không khớp hoàn toàn chủ đề nguồn — hãy đọc kỹ trước khi làm."
        do_tin = round(min(do_tin, 0.55), 2)
    return SopAnswer(
        cau_tra_loi=top_cau,
        trich_dan=seen,
        chua_co=False,
        mode="keyword",
        provider="",
        do_tin=do_tin,
        canh_bao=canh_bao,
        viec_lam=top_viec,
        phieu_ma=phieu_ma,
        phieu_buoc_ma=buoc_ma,
        ngu_canh=ctx.as_dict(),
    )


def _answer_live(
    question: str,
    *,
    buoc: list[dict[str, Any]],
    luat: list[dict[str, Any]],
    ctx: SopOpsContext,
) -> SopAnswer | None:
    ctx_text, valid = _build_context(buoc, luat, ctx)
    user = json.dumps(
        {"cau_hoi": question, "ngu_canh": ctx_text, "ca": ctx.as_dict()},
        ensure_ascii=False,
    )
    res = complete(system=_SOP_SYSTEM, user=user, task="ag_sop", json_mode=True)
    if not res.ok:
        return None
    data = parse_json_object(res.text)
    if not data:
        return None
    chua_co = bool(data.get("chua_co"))
    trich = [str(x) for x in (data.get("trich_dan") or []) if str(x)]
    if chua_co:
        return SopAnswer(
            cau_tra_loi=str(
                data.get("cau_tra_loi") or "Chưa có trong cẩm nang của quán, hãy hỏi quản lý."
            ),
            trich_dan=[],
            chua_co=True,
            mode="live",
            provider=res.provider,
            do_tin=0.0,
            ngu_canh=ctx.as_dict(),
        )
    if not trich or not all(t in valid for t in trich):
        return None
    cau = str(data.get("cau_tra_loi") or "").strip()
    if not cau:
        return None
    phieu_ma = ""
    buoc_ma = ""
    for t in trich:
        if t.startswith("phieu:"):
            buoc_ma = t.split(":", 1)[1]
            for b in buoc:
                if str(b.get("ma")) == buoc_ma:
                    phieu_ma = str(b.get("phieu") or "")
                    break
    return SopAnswer(
        cau_tra_loi=cau,
        trich_dan=trich,
        chua_co=False,
        mode="live",
        provider=res.provider,
        do_tin=0.85,
        viec_lam="Xem phiếu quy trình tại /phieu nếu cần thực hiện bước.",
        phieu_ma=phieu_ma,
        phieu_buoc_ma=buoc_ma,
        ngu_canh=ctx.as_dict(),
    )


def answer(
    question: str,
    *,
    buoc: list[dict[str, Any]],
    luat: list[dict[str, Any]],
    ops_context: SopOpsContext | None = None,
    mode: str | None = None,
) -> SopAnswer:
    ctx = ops_context or default_ops_context()
    scoped_luat = filter_luat_for_sop(luat, ctx, question=question)
    resolved = (mode or agent_mode() or "replay").strip().lower()
    if resolved == "live":
        live = _answer_live(question, buoc=buoc, luat=scoped_luat, ctx=ctx)
        if live:
            return live
    kw = _answer_keyword(question, buoc=buoc, luat=scoped_luat, ctx=ctx)
    if resolved == "live" and not kw.chua_co:
        kw.mode = "keyword"
    return kw
