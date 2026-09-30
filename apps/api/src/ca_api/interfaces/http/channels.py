"""Kênh tin (Telegram/Zalo/replay) + Page quán (Facebook replay)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from ca_agents.ag_fbpage import (
    FBMessageInput,
    FBMessageOutput,
    draft_llm_reply,
    process_fb_message,
)
from ca_agents.ag_fbpage import (
    classify_comment_action as classify_comment_pii_action,
)
from ca_agents.ag_fbpage_memory import extract_cskh_golden_pair
from ca_agents.ag_msg import classify
from ca_agents.ag_supervisor import run_nightly_cskh_reflection, supervise_outgoing_response
from ca_agents.customer_memory import (
    extract_customer_preferences,
    merge_customer_profile,
)
from ca_agents.facebook_page import (
    fetch_conversations,
    hide_comment,
    is_within_24h_window,
    page_health,
    publish_page_post,
    reply_to_comment,
    send_messenger_bubbles,
    send_messenger_text,
    upsert_thread_from_messaging,
    verify_fb_webhook_signature,
)
from ca_agents.llm import agent_mode
from ca_agents.messaging import (
    InboundMessage,
    get_port,
    is_xem_lich,
    parse_telegram_update,
    parse_zalo_webhook,
    should_enqueue_constraint,
)
from ca_contracts import (
    AIEvaluation,
    AIEvaluationScores,
    AIFeedbackContent,
    AIFeedbackEvent,
    AIGenerationDraft,
    AIGenerationRecord,
    AIModelVersion,
    FbPolicyAction,
)
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

import ca_api.services.table_reservation_service  # noqa: F401
from ca_api.ai_learning.operations import circuit_breaker_open
from ca_api.ai_learning.repository import AILearningRepository
from ca_api.ai_learning.rollout import select_active_rules
from ca_api.interfaces.http.sprint3 import (
    _known_nv,
    _nv_from_token,
    _phan_cong,
    _require_manager,
    _require_role,
)
from ca_api.persist import (
    audit_add,
    fb_escalation_add,
    fb_review_decide,
    fb_review_finalize_claim,
    fb_review_get,
    fb_review_link_generation,
    fb_review_list,
    fb_review_release_claim,
    fb_review_transition_pending,
    fb_review_update_proposed,
    fb_stats,
    fb_try_claim_scoped_event,
    kenh_bind_code_consume,
    kenh_bind_code_issue,
    kenh_bind_get,
    kenh_bind_list,
    kenh_bind_set,
    kv_get,
    kv_mutate,
    kv_set,
    page_store_map_list,
    resolve_store_id_from_page_id,
)
from ca_api.persist import session as auth_session
from ca_api.services.chat_ws import chat_ws_manager
from ca_api.services.fb_attachment_processor import (
    format_attachment_for_review,
    process_attachment,
)
from ca_api.services.fb_moderation import (
    analyze_comment_sentiment,
    classify_comment_action,
    fb_jev_enabled,
    moderate_fb_message,
    queue_fb_non_text,
)
from ca_api.services.store_public_context import (
    get_active_promotions,
    get_public_menu,
    get_store_profile,
    set_active_promotions,
    set_store_profile,
)

router = APIRouter()
logger = logging.getLogger(__name__)
LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[6]
SEED = ROOT / "data" / "seed" / "sample.json"
PAGE_FIXTURE = ROOT / "data" / "golden" / "page" / "threads_01.json"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(ai: str, hanh: str, payload: dict[str, Any]) -> None:
    audit_add(_now(), ai, hanh, payload)

def _record_fb_feedback(
    *, store_id: str, conversation_id: str, feedback_type: str, original: str = "",
    final: str = "", actor_user_id: str | None = None, actor_role: str = "quan_ly",
    send_status: str = "not_applicable", failure_code: str | None = None, generation_id: str | None = None,
) -> None:
    """Persist feedback only when the source generation is explicitly known."""
    if not generation_id:
        LOG.warning(
            "facebook learning feedback skipped without generation_id: type=%s conversation=%s",
            feedback_type,
            conversation_id,
        )
        return
    try:
        repository = AILearningRepository()
        generation = next(
            (item for item in repository.list("generation", store_id=store_id, limit=200) if item.get("id") == generation_id),
            None,
        )
        if not generation:
            return
        fingerprint = hashlib.sha256(
            f"{generation['id']}:{feedback_type}:{final}:{send_status}".encode()
        ).hexdigest()
        repository.save(AIFeedbackEvent(
            id=f"fb-feedback-{fingerprint[:24]}", store_id=store_id, generation_id=str(generation["id"]),
            channel="facebook", type=cast(Literal["manager_approve", "manager_edit", "manager_reject", "customer_positive", "customer_negative", "customer_followup", "send_success", "send_failure", "manual_rating"], feedback_type),
            original=cast(AIFeedbackContent | None, {"body": original} if original else None),
            final=cast(AIFeedbackContent | None, {"body": final} if final else None),
            edited_fields=cast(list[Literal["subject", "body"]], ["body"] if original and final and original != final else []),
            materially_edited=bool(original and final and original != final), actor_user_id=actor_user_id,
            actor_role=cast(Literal["chu_quan", "quan_ly", "system", "customer"], actor_role), send_status=cast(Literal["not_applicable", "sent", "failed"], send_status), failure_code=failure_code,
            idempotency_key=f"fb-feedback:{fingerprint}", created_at=_now(),
        ))
    except Exception:
        LOG.exception("facebook learning feedback persistence failed")


def _customer_negative_signal(text: str) -> bool:
    """Use a deliberately small, explainable negative-signal vocabulary."""
    normalized = " ".join(text.lower().split())
    return any(term in normalized for term in ("không hài lòng", "that vong", "tệ quá", "quá tệ", "bực mình", "không đúng"))


# ── Bind ──────────────────────────────────────────────────────────────────


class BindIssueOut(BaseModel):
    code: str
    huong_dan: str


@router.post("/api/v1/channels/bind/issue")
def bind_issue(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    nv = _nv_from_token(authorization)
    code = kenh_bind_code_issue(nv)
    return {
        "code": code,
        "huong_dan": (
            f"Ưu tiên Zalo OA — nhắn đúng một dòng: /bind {code}. "
            f"Telegram (nếu có bot): cùng lệnh /bind {code}."
        ),
        "nv_id": nv,
    }


class BindManualBody(BaseModel):
    channel: str = Field(default="telegram", min_length=1, max_length=32)
    external_user_id: str = Field(min_length=1, max_length=128)
    nv_id: str = Field(min_length=1, max_length=64)


@router.post("/api/v1/channels/bind")
def bind_manual(
    body: BindManualBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    if body.channel not in {"telegram", "zalo", "facebook"}:
        raise HTTPException(status_code=422, detail="kenh_khong_hop_le")
    if not _known_nv(body.nv_id):
        raise HTTPException(status_code=404, detail="nhan_vien_khong_ton_tai")
    kenh_bind_set(body.channel, body.external_user_id, body.nv_id)
    _audit(role, "kenh_bind", body.model_dump())
    return {"ok": True, **body.model_dump()}


@router.get("/api/v1/channels/bind")
def bind_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    if s["role"] in {"quan_ly", "chu_quan"}:
        return {"items": kenh_bind_list()}
    return {"items": kenh_bind_list(s["nv_id"])}


# ── Inbound process ───────────────────────────────────────────────────────


def _format_lich(nv_id: str) -> str:
    phan = _phan_cong()
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    meta = {c["id"]: c for c in seed.get("ca_mau_21", [])}
    thu = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
    mine = [cid for cid, nvs in phan.items() if nv_id in nvs]
    if not mine:
        return f"Lịch của bạn ({nv_id}): chưa có ca nào trong tuần này."
    lines = [f"Lịch ca của bạn ({nv_id}):"]
    for cid in mine[:12]:
        m = meta.get(cid, {})
        lines.append(
            f"- {thu.get(int(m.get('ngay_offset', 1)), 'T2')} "
            f"{m.get('bat_dau', '?')}–{m.get('ket_thuc', '?')} "
            f"{m.get('vi_tri', '')} ({cid})"
        )
    return "\n".join(lines)


def _enqueue_inbox(
    *,
    text: str,
    intent: str,
    do_tin_cay: float,
    channel: str,
    nv_id: str,
    external_user_id: str,
    rang_buoc: dict[str, str],
) -> dict[str, Any]:
    item = {
        "id": f"in_ch_{uuid.uuid4().hex[:8]}",
        "agent": "ag_msg",
        "tom_tat": text.strip()[:200],
        "trang_thai": "cho_duyet",
        "nguon": channel,
        "y_dinh": intent,
        "do_tin_cay": do_tin_cay,
        "noi_dung_goc": text,
        "nv_id": nv_id,
        "channel_user_id": external_user_id,
        "rang_buoc": rang_buoc,
        "can_xac_minh": bool(rang_buoc.get("can_xac_minh") or do_tin_cay < 0.7),
        "doi_tac_khong_ro": bool(rang_buoc.get("doi_tac_khong_ro", False)),
        "created_at": _now(),
    }

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.insert(0, item)
        return items

    # Không gọi _seed_inbox trước — tránh ghi đè fixture nếu kv trống trong test
    # khi đã có mục kênh. Seed chỉ khi list rỗng ở GET.
    existing = kv_get("inbox_rang_buoc", None)
    if existing is None:
        kv_set("inbox_rang_buoc", [item])
    else:
        kv_mutate("inbox_rang_buoc", mut, [])

    # AI tự động duyệt/từ chối ngay — trang Hộp thư ràng buộc chỉ còn để xem.
    # Lỗi ở đây không được chặn việc ghi nhận tin nhắn từ kênh.
    try:
        from ca_api.services.inbox_autopilot import auto_process

        auto_process()
    except Exception:
        pass

    return item


def process_inbound(msg: InboundMessage, *, reply_backend: str | None = None) -> dict[str, Any]:
    """Xử lý một tin: bind → xem lịch | classify → inbox.

    Văn phong trả lời: lịch sự, tự nhiên như nhân sự quán, không máy móc.
    """
    port = get_port(reply_backend or msg.channel)
    text = msg.text.strip()
    bind_m = re.match(r"^/bind\s+([a-z0-9]{6,16})$", text, re.I)
    if bind_m:
        nv = kenh_bind_code_consume(bind_m.group(1), msg.channel, msg.external_user_id)
        if not nv:
            sent = port.send(
                msg.external_user_id,
                "Dạ mã kết nối này chưa đúng hoặc đã được dùng rồi ạ. Anh/chị vui lòng lấy mã mới trong mục «Ca của tôi» trên web rồi gửi lại giúp em nhé.",
            )
            return {"ok": False, "ly_do": "bind_code", "message": sent.__dict__}
        sent = port.send(
            msg.external_user_id,
            "Dạ em đã nối kênh thành công rồi ạ. Từ giờ anh/chị có thể nhắn «xem lịch» để biết ca của mình, hoặc nhắn xin nghỉ, đổi ca, báo trễ — em sẽ chuyển thẳng cho quản lý duyệt.",
        )
        return {"ok": True, "hanh": "bind", "nv_id": nv, "message": sent.__dict__}

    nv_id = kenh_bind_get(msg.channel, msg.external_user_id)
    if not nv_id:
        sent = port.send(
            msg.external_user_id,
            "Dạ anh/chị vui lòng kết nối tài khoản quán trước nhé: vào web NHỊP QUÁN, chọn «Ca của tôi», bấm «Lấy mã kết nối» rồi nhắn lại đúng dòng «/bind <mã>» ở đây ạ. Sau đó em hỗ trợ xem lịch và nhận các yêu cầu nghỉ, đổi ca ngay.",
        )
        return {"ok": False, "ly_do": "chua_bind", "message": sent.__dict__}

    if is_xem_lich(text):
        body = _format_lich(nv_id)
        sent = port.send(
            msg.external_user_id,
            f"Dạ đây là lịch ca tuần này của anh/chị ạ:\n{body}\nNếu cần xin nghỉ hay đổi ca, anh/chị cứ nhắn trực tiếp cho em nhé.",
        )
        return {"ok": True, "hanh": "xem_lich", "nv_id": nv_id, "message": sent.__dict__}

    staff_list: list[dict[str, str]] = []
    try:
        from ca_api.persist import list_users
        users = list_users()
        staff_list = [
            {
                "id": u.get("nv_id") or u.get("username", ""),
                "ten": u.get("display_name") or u.get("username", ""),
            }
            for u in users
        ]
    except Exception:
        pass

    # Phải truyền tuần THẬT — giống sprint3 msg_classify. Thiếu base_iso_week
    # thì «tuần sau» luôn ra W02 từ mặc định W01 (bug QA đợt 4).
    try:
        from datetime import UTC, datetime

        iso = datetime.now(UTC).isocalendar()
        base_week = f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        base_week = None
    r = classify(
        text,
        mode=agent_mode(),
        staff=staff_list if staff_list else None,
        base_iso_week=base_week,
    )
    if not should_enqueue_constraint(text, r.intent, r.do_tin_cay):
        sent = port.send(
            msg.external_user_id,
            "Dạ em đã nhận được tin nhắn của anh/chị ạ. Nội dung này chưa phải yêu cầu về ca làm việc, nên tạm chưa cần quản lý duyệt. Nếu anh/chị muốn xin nghỉ, đổi ca, nhận thêm ca, báo đến trễ hay cập nhật lịch học, cứ nhắn rõ giúp em nhé.",
        )
        return {
            "ok": True,
            "hanh": "bo_qua",
            "intent": r.intent,
            "nv_id": nv_id,
            "message": sent.__dict__,
        }
    item = _enqueue_inbox(
        text=text,
        intent=r.intent,
        do_tin_cay=r.do_tin_cay,
        channel=msg.channel,
        nv_id=nv_id,
        external_user_id=msg.external_user_id,
        rang_buoc=dict(r.rang_buoc),
    )
    y_dinh_depngon = {
        "xin_nghi": "xin nghỉ ca",
        "doi_ca": "yêu cầu đổi ca",
        "nhan_ca": "yêu cầu nhận thêm ca",
        "bao_tre": "lời báo đến trễ",
        "cap_nhat_tkb": "cập nhật thời khóa biểu",
    }
    ten_y_dinh = y_dinh_depngon.get(str(r.intent), f"yêu cầu «{r.intent}»")
    sent = port.send(
        msg.external_user_id,
        f"Dạ em đã ghi nhận {ten_y_dinh} của anh/chị và chuyển vào hộp thư duyệt rồi ạ. Quản lý sẽ xem và quyết trong thời gian sớm nhất; quyết định xong em sẽ thông báo lại ngay. Anh/chị cần thêm gì cứ nhắn em nhé.",
    )
    return {"ok": True, "hanh": "enqueue", "item": item, "message": sent.__dict__}


class ReplayBody(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    backend: str = "replay"


@router.get("/api/v1/channels/status")
def channels_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Trạng thái nối kênh thật — UI dùng để hiện 'Chưa nối', không giả lập."""
    caller = auth_session(authorization)
    if not caller:
        raise HTTPException(status_code=401, detail="thieu_token")
    zalo_on = os.environ.get("NHIPQUAN_ZALO_ENABLED", "").strip() in {"1", "true", "yes"}
    zalo_token = bool(os.environ.get("NHIPQUAN_ZALO_OA_ACCESS_TOKEN", "").strip())
    tg_token = bool(os.environ.get("NHIPQUAN_TELEGRAM_BOT_TOKEN", "").strip())
    fb_token = bool(os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip())
    binds = (
        kenh_bind_list()
        if caller["role"] in {"quan_ly", "chu_quan"}
        else kenh_bind_list(caller["nv_id"])
    )
    return {
        "uu_tien": ["zalo", "telegram", "facebook"],
        "agent_mode": agent_mode(),
        "zalo": {
            "enabled_flag": zalo_on,
            "connected": zalo_on and zalo_token,
            "huong_dan": "docs/runbooks/zalo-oa-connect.md",
        },
        "telegram": {
            "connected": tg_token,
            "huong_dan": "docs/runbooks/telegram-bot-connect.md",
        },
        "facebook": {
            "connected": fb_token,
            "huong_dan": "docs/runbooks/facebook-page-connect.md",
        },
        "binds": binds,
    }


@router.post("/api/v1/channels/replay")
def channels_replay(
    body: ReplayBody | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chỉ cho CI/test — không dùng làm dữ liệu quán thật."""
    _require_manager(authorization)
    if os.environ.get("NHIPQUAN_ALLOW_MSG_REPLAY", "").strip() not in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=403,
            detail="replay_tat — bật NHIPQUAN_ALLOW_MSG_REPLAY=1 chỉ khi chạy test",
        )
    b = body or ReplayBody()
    port = get_port("replay")
    results = []
    for i, msg in enumerate(port.receive_iter()):
        if i >= b.limit:
            break
        results.append(process_inbound(msg, reply_backend=b.backend))
    return {"ok": True, "n": len(results), "results": results}


@router.post("/api/v1/channels/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, Any]:
    secret = os.environ.get("NHIPQUAN_TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret:
        got = request.headers.get("x-telegram-bot-api-secret-token", "")
        if got != secret:
            raise HTTPException(status_code=403, detail="webhook_secret")
    payload = await request.json()
    msg = parse_telegram_update(payload if isinstance(payload, dict) else {})
    if not msg:
        return {"ok": True, "ignored": True}
    return process_inbound(msg, reply_backend="telegram")


@router.post("/api/v1/channels/zalo/webhook")
async def zalo_webhook(request: Request) -> dict[str, Any]:
    """Webhook OA Zalo — kênh ưu tiên tại VN. Cần NHIPQUAN_ZALO_ENABLED=1 + token."""
    if os.environ.get("NHIPQUAN_ZALO_ENABLED", "").strip() not in {"1", "true", "yes"}:
        return {"ok": False, "detail": "chua_bat_zalo — xem docs/runbooks/zalo-oa-connect.md"}
    if not os.environ.get("NHIPQUAN_ZALO_OA_ACCESS_TOKEN", "").strip():
        return {"ok": False, "detail": "thieu_zalo_token"}
    payload = await request.json()
    msg = parse_zalo_webhook(payload if isinstance(payload, dict) else {})
    if not msg:
        return {"ok": True, "ignored": True}
    return process_inbound(msg, reply_backend="zalo")


# ── Page quán (Facebook replay) ────────────────────────────────────────────


def _page_store(store_id: str = "quan_01") -> dict[str, Any]:
    """Store trống theo mặc định — không nhồi fixture làm dữ liệu quán.

    Chỉ seed file golden khi `NHIPQUAN_PAGE_SEED_FIXTURE=1` (CI).
    Multi-page: mỗi store có key riêng (page_quan:{store_id}).
    Tương thích ngược: nếu page_quan:{store_id} chưa có nhưng "page_quan" có dữ liệu thì dùng.
    """
    key = f"page_quan:{store_id}"
    stored = kv_get(key, None)
    if stored and isinstance(stored, dict):
        return cast(dict[str, Any], stored)
    legacy = kv_get("page_quan", None)
    if legacy and isinstance(legacy, dict) and (legacy.get("threads") or legacy.get("drafts")):
        # Tương thích ngược: khi store scoped chưa tồn tại mà legacy có dữ liệu,
        # migrate luôn sang key scoped để MỌI thao tác ghi (reply/approve/draft)
        # về sau đi chung 1 key — tránh tình trạng ghi vào key legacy nhưng
        # đọc không thấy (bug mất trả lời).
        kv_set(key, legacy)
        return cast(dict[str, Any], kv_get(key, legacy))
    seed = os.environ.get("NHIPQUAN_PAGE_SEED_FIXTURE", "").strip() in {"1", "true", "yes"}
    if seed and PAGE_FIXTURE.exists():
        data = json.loads(PAGE_FIXTURE.read_text(encoding="utf-8"))
    else:
        data = {"threads": [], "drafts": [], "mode": "disconnected"}
    data.setdefault("mode", "disconnected")
    data.setdefault("threads", [])
    data.setdefault("drafts", [])
    kv_set(key, data)
    return cast(dict[str, Any], data)


def _page_mode() -> str:
    env = os.environ.get("NHIPQUAN_PAGE_MODE", "").strip().lower()
    if env in {"live", "disconnected"}:
        return env
    token = bool(os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip())
    if token:
        return "live"
    return "disconnected"


def _fb_auto_send_enabled() -> bool:
    """Feature flag — delegate về service (single source of truth, §5.5)."""
    from ca_api.services.fb_moderation import fb_auto_send_enabled

    return fb_auto_send_enabled()


@router.get("/api/v1/page/status")
def page_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_manager(authorization)
    mode = _page_mode()
    token = bool(os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip())
    page_id = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    health: dict[str, Any] = {"ok": False, "detail": "chua_goi"}
    if mode == "live" and token and page_id:
        health = page_health()
    connected = mode == "live" and token and bool(health.get("ok"))
    return {
        "mode": mode,
        "connected": connected,
        "has_token": token,
        "page_id": page_id or None,
        "page_name": health.get("page_name") if health.get("ok") else None,
        "graph_ok": bool(health.get("ok")),
        "graph_detail": None if health.get("ok") else health.get("detail"),
        "huong_dan": (
            "Tạo Page Facebook rồi làm theo docs/runbooks/facebook-page-connect.md "
            "— không dùng dữ liệu giả."
        ),
    }


@router.post("/api/v1/page/sync")
def page_sync(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Kéo hội thoại Messenger thật từ Graph vào store Page quán."""
    _require_manager(authorization)
    if _page_mode() != "live" or not os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip():
        raise HTTPException(status_code=400, detail="page_chua_live")
    try:
        threads = fetch_conversations(limit=20)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)[:180]) from e

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        by_id = {t.get("id"): t for t in doc.get("threads", []) if t.get("id")}
        for th in threads:
            by_id[th["id"]] = th
        doc["threads"] = list(by_id.values())
        doc["mode"] = "live"
        return doc

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    return {"ok": True, "n": len(threads), "mode": "live", "store_id": store_id}


@router.post("/api/v1/page/sync-multi")
def page_sync_multi(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Kéo hội thoại Messenger từ nhiều Page (multi-page support)."""
    _require_manager(authorization)
    if _page_mode() != "live" or not os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip():
        raise HTTPException(status_code=400, detail="page_chua_live")

    mappings = page_store_map_list()
    if not mappings:
        raise HTTPException(status_code=400, detail="no_page_mappings")

    results: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        page_id = str(mapping.get("page_id") or "")
        store_id = str(mapping.get("store_id") or "quan_01")
        if not page_id:
            continue
        try:
            # Note: fetch_conversations uses the default page token from env
            # For multi-page, we'd need page-specific tokens
            threads = fetch_conversations(limit=20)
            results[page_id] = {"ok": True, "n": len(threads), "store_id": store_id}
        except RuntimeError as e:
            results[page_id] = {"ok": False, "error": str(e)[:180]}

    return {"ok": True, "results": results}


def _safe_float(value: Any) -> float:
    """Ép kiểu an toàn cho trường số trong webhook công khai (payload có thể rác)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fb_debounce_delay() -> float:
    """Thời gian debounce gom tin nhắn dồn dập từ khách (giây).

    Mặc định 3.5s khi live (theo genz-texting-agent skill).
    Trong test tự động (pytest), nếu không chỉ định NHIPQUAN_FB_DEBOUNCE_SECONDS,
    sẽ là 0.0s để pipeline webhook chạy tức thì đồng bộ.
    """
    env_val = os.environ.get("NHIPQUAN_FB_DEBOUNCE_SECONDS", "").strip()
    if env_val:
        try:
            return max(0.0, float(env_val))
        except ValueError:
            pass
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("PYTEST_VERSION"):
        return 0.0
    if os.environ.get("CA_AGENT_MODE", "").strip().lower() == "live":
        return 3.5
    return 0.0


class FBDebounceManager:
    """Debounce buffer gom nhiều tin nhắn ngắn gửi liên tiếp từ 1 khách hàng trước khi gọi AI."""

    def __init__(self) -> None:
        self._buffers: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._timers: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def push(
        self,
        *,
        store_id: str,
        sender: str,
        mid: str,
        text: str,
        ts: float,
        page_id: str,
        public_ctx: dict[str, Any] | None,
        callback: Any,
        delay_seconds: float = 3.5,
    ) -> None:
        key = (store_id, sender)
        async with self._lock:
            if key not in self._buffers:
                self._buffers[key] = []
            self._buffers[key].append({"mid": mid, "text": text, "ts": ts})

            existing_timer = self._timers.get(key)
            if existing_timer and not existing_timer.done():
                existing_timer.cancel()

            async def _worker() -> None:
                try:
                    await asyncio.sleep(delay_seconds)
                    async with self._lock:
                        messages = self._buffers.pop(key, [])
                        self._timers.pop(key, None)
                    if not messages:
                        return
                    combined_text = "\n".join(m["text"] for m in messages if m.get("text"))
                    latest_mid = messages[-1]["mid"]
                    latest_ts = messages[-1]["ts"]
                    await callback(
                        store_id=store_id,
                        page_id=page_id,
                        sender=sender,
                        text=combined_text,
                        mid=latest_mid,
                        ts=latest_ts,
                        public_ctx=public_ctx,
                    )
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    LOG.exception("Lỗi trong fb debounce worker: %s", err)

            self._timers[key] = asyncio.create_task(_worker())


_FB_DEBOUNCE_MANAGER = FBDebounceManager()


async def _execute_fb_pipeline(
    *,
    store_id: str,
    page_id: str,
    sender: str,
    text: str,
    mid: str,
    ts: float,
    public_ctx: dict[str, Any] | None,
) -> bool:
    moderation = moderate_fb_message(
        psid=sender,
        text=text,
        message_id=mid,
        timestamp=ts,
        public_context=public_ctx,
        store_id=store_id,
    )
    action = moderation.get("action", "")
    if action in {"block_silent", "block_polite"}:
        return False

    input_msg = FBMessageInput(psid=sender, text=text, message_id=mid, timestamp=ts)

    cust_prof = kv_get(f"customer_profile:{store_id}:{sender}", {})
    res_session = kv_get(f"reservation_session:{store_id}:{sender}", {})
    if isinstance(res_session, dict) and res_session:
        last_ts = _safe_float(res_session.get("updated_ts", 0))
        if last_ts > 0 and ts - last_ts > 1800:
            res_session = {}
            kv_set(f"reservation_session:{store_id}:{sender}", {})

    if isinstance(cust_prof, dict):
        cust_prof["psid"] = sender
        if res_session:
            cust_prof["reservation_state"] = res_session

    goldens = kv_get(f"cskh_golden_memory:{store_id}", [])
    learning_repository = AILearningRepository()
    active_rules, rollout_bucket = select_active_rules(
        learning_repository.active_rules(store_id=store_id, channel="facebook"),
        store_id=store_id,
        identity=sender,
    )

    prior_thread = next(
        (thread for thread in _page_store(store_id).get("threads", []) if thread.get("psid") == sender),
        None,
    )
    prior_generation_id = str((prior_thread or {}).get("ai_generation_id") or "")
    if prior_generation_id:
        _record_fb_feedback(
            store_id=store_id, conversation_id=sender, feedback_type="customer_followup",
            final=text, actor_role="customer", generation_id=prior_generation_id,
        )
        if _customer_negative_signal(text):
            _record_fb_feedback(
                store_id=store_id, conversation_id=sender, feedback_type="customer_negative",
                final=text, actor_role="customer", generation_id=prior_generation_id,
            )

    out: FBMessageOutput = await process_fb_message(
        input_msg,
        auto_respond_enabled=True,
        public_context=public_ctx,
        customer_profile=cust_prof if cust_prof else None,
        golden_examples=goldens if goldens else None,
        active_rules=active_rules,
    )

    if circuit_breaker_open(store_id=store_id, channel="facebook") or action in {"queue_review", "priority_review", "escalate_owner"}:
        out = FBMessageOutput(
            action="queue_to_inbox",
            response=None,
            intent=out.intent,
            confidence=out.confidence,
            emotion=out.emotion,
            suggested_reply=out.suggested_reply or moderation.get("response"),
            delegated_agent=out.delegated_agent,
            reason="ai_circuit_breaker_open" if circuit_breaker_open(store_id=store_id, channel="facebook") else f"fb_policy:{moderation.get('reason')}",
            reservation_state=out.reservation_state,
        )
    elif action == "auto_send" and out.action == "auto_respond" and _fb_auto_send_enabled():
        out = FBMessageOutput(
            action="auto_respond",
            response=out.response,
            intent=out.intent,
            confidence=out.confidence,
            emotion=out.emotion,
            suggested_reply=out.suggested_reply,
            delegated_agent=out.delegated_agent,
            reason=f"fb_policy_auto:{moderation.get('reason')}",
            reservation_state=out.reservation_state,
        )
    else:
        out = FBMessageOutput(
            action="queue_to_inbox",
            response=None,
            intent=out.intent,
            confidence=out.confidence,
            emotion=out.emotion,
            suggested_reply=out.suggested_reply or moderation.get("response"),
            delegated_agent=out.delegated_agent,
            reason="fb_policy_auto_guarded",
            reservation_state=out.reservation_state,
        )

    fingerprint = hashlib.sha256(f"{store_id}:{page_id}:{mid}:{out.action}:{out.suggested_reply or out.response or ''}".encode()).hexdigest()
    policy_action = "auto_send" if out.action == "auto_respond" else "queue_review"
    generation_id = f"facebook-{fingerprint[:24]}"
    learning_repository.save(AIGenerationRecord(
        id=generation_id, store_id=store_id, channel="facebook",
        conversation_id=sender, request_kind="facebook_message", external_event_hash=hashlib.sha256(mid.encode()).hexdigest(),
        draft=cast(AIGenerationDraft, {"body": out.suggested_reply or out.response or "Đã chuyển quản lý xử lý."}), context_snapshot_hash=fingerprint,
        agent_version="ag-fbpage", prompt_version="fb-messenger-v1",
        rule_version=",".join(str(rule.get("id")) for rule in active_rules) or "none",
        rollout_bucket=cast(Literal["control", "canary_10", "canary_50", "active_100"], rollout_bucket), model=cast(AIModelVersion, {"provider": agent_mode(), "model_id": "ag-fbpage", "temperature": 0, "tool_context_hash": fingerprint}),
        policy_action=cast(FbPolicyAction, policy_action), idempotency_key=f"generation:{fingerprint}", created_at=datetime.now(UTC).isoformat(),
    ))
    if moderation.get("review_id"):
        fb_review_link_generation(int(moderation["review_id"]), generation_id=generation_id)
    learning_repository.save(AIEvaluation(
        id=f"facebook-evaluation-{fingerprint[:20]}", store_id=store_id, generation_id=f"facebook-{fingerprint[:24]}", channel="facebook",
        scores=cast(AIEvaluationScores, {"accuracy": out.confidence, "safety": 1.0}), aggregate_score=out.confidence,
        passed=out.action == "auto_respond", action=cast(FbPolicyAction, policy_action),
        flags=[] if out.action == "auto_respond" else ["manager_review_required"], threshold_version="facebook-policy-v1",
        calibration_version="deterministic-v1", sample_count=0, evaluation_window="per_messenger_event",
        evaluator="ag-fbpage-policy", idempotency_key=f"evaluation:{fingerprint}", created_at=datetime.now(UTC).isoformat(),
    ))

    new_prefs = extract_customer_preferences([text])
    if new_prefs.get("ten_khach") or new_prefs.get("favorite_drinks") or new_prefs.get("special_notes"):
        def mut_prof(cur: dict[str, Any] | None, _p: dict[str, Any] = new_prefs) -> dict[str, Any]:
            return merge_customer_profile(cur, _p)

        cust_prof = kv_mutate(f"customer_profile:{store_id}:{sender}", mut_prof, {})

    if out.reservation_state is not None:
        step = out.reservation_state.get("dialog_step")
        if step in ("CONFIRMED", "CANCELLED") or out.reservation_state.get("status") == "confirmed":
            kv_set(f"reservation_session:{store_id}:{sender}", {})
            if isinstance(cust_prof, dict):
                cust_prof["reservation_state"] = None
        else:
            new_res_state = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in dict(out.reservation_state).items()
            }
            new_res_state["updated_ts"] = ts
            kv_set(f"reservation_session:{store_id}:{sender}", new_res_state)
            if isinstance(cust_prof, dict):
                cust_prof["reservation_state"] = new_res_state

    th = upsert_thread_from_messaging(sender, text, mid)
    th["ai_generation_id"] = generation_id
    th["intent"] = out.intent
    th["confidence"] = out.confidence
    th["suggested_reply"] = out.suggested_reply
    th["pending_approval"] = out.action == "queue_to_inbox"
    th["last_message_ts"] = ts
    th["is_within_24h"] = is_within_24h_window(ts)
    th["customer_profile"] = cust_prof

    if out.action == "auto_respond" and out.response:
        bot_reply = {
            "id": f"bot_{uuid.uuid4().hex[:6]}",
            "text": out.response,
            "by": "Chatbot (Tự động)",
            "at": _now(),
            "mock": False,
        }
        delivered = _page_mode() != "live"
        if _page_mode() == "live":
            try:
                await send_messenger_bubbles(sender, out.response, send_fn=send_messenger_text)
                delivered = True
            except Exception:
                delivered = False
        review_id = moderation.get("review_id")
        if review_id is not None:
            if delivered:
                fb_review_finalize_claim(
                    int(review_id),
                    status="auto_sent",
                    decided_by="fb_auto",
                    final_response=out.response,
                )
            else:
                fb_review_release_claim(int(review_id))
        if delivered:
            th.setdefault("replies", []).append(bot_reply)

    def mut(doc: dict[str, Any], thread: dict[str, Any] = th) -> dict[str, Any]:
        threads = doc.setdefault("threads", [])
        existing = next((t for t in threads if t.get("id") == thread["id"]), None)
        if existing:
            existing["tom_tat"] = thread["tom_tat"]
            existing.setdefault("replies", []).extend(thread.get("replies") or [])
            existing["psid"] = thread.get("psid")
            existing["intent"] = thread.get("intent")
            existing["confidence"] = thread.get("confidence")
            existing["suggested_reply"] = thread.get("suggested_reply")
            existing["pending_approval"] = thread.get("pending_approval")
            existing["last_message_ts"] = thread.get("last_message_ts")
            existing["is_within_24h"] = thread.get("is_within_24h")
            existing["ai_generation_id"] = thread.get("ai_generation_id")
            existing["customer_profile"] = thread.get("customer_profile")
        else:
            threads.insert(0, thread)
        doc["mode"] = "live"
        return doc

    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    return True


@router.api_route("/api/v1/channels/facebook/webhook", methods=["GET", "POST"])
async def facebook_webhook(request: Request) -> Any:
    """Meta webhook: GET verify challenge; POST Messenger events → AG-FBPAGE processing."""
    if request.method == "GET":
        mode = request.query_params.get("hub.mode", "")
        token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")
        expected = os.environ.get("NHIPQUAN_FB_WEBHOOK_VERIFY", "").strip()
        if mode == "subscribe" and expected and token == expected and challenge:
            return Response(content=challenge, media_type="text/plain")
        raise HTTPException(status_code=403, detail="verify_fail")

    body_bytes = await request.body()
    sig_header = request.headers.get("x-hub-signature-256", "")
    if not verify_fb_webhook_signature(body_bytes, sig_header):
        # APP_SECRET thiếu là cấu hình phổ biến nhất: chặn 100% webhook thật
        # (fail-closed an toàn) nhưng cần log rõ để vận hành nhận ra ngay.
        if not os.environ.get("NHIPQUAN_FB_APP_SECRET", "").strip():
            LOG.warning(
                "FB webhook rejected: NHIPQUAN_FB_APP_SECRET is EMPTY — "
                "add it to .env (Meta App Dashboard → App Settings → Basic → App Secret) "
                "then restart the stack, otherwise ALL real Meta events get 403."
            )
        raise HTTPException(status_code=403, detail="invalid_signature")

    if _page_mode() != "live" or not os.environ.get("NHIPQUAN_FB_PAGE_TOKEN", "").strip():
        return {"ok": False, "detail": "page_chua_live"}

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        return {"ok": True, "ignored": True}

    if not isinstance(payload, dict):
        return {"ok": True, "ignored": True}

    public_ctx = {
        "profile": get_store_profile(),
        "menu": get_public_menu(),
        "promotions": get_active_promotions(),
    }

    n = 0
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    entries = payload.get("entry") or []
    if not isinstance(entries, list):
        # Payload công khai có thể dị dạng — bỏ qua thay vì 500 (Meta sẽ retry).
        return {"ok": True, "ignored": True}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # L0a — chỉ nhận entry đúng Page cấu hình (kế hoạch §6.3.5); thiếu id → cho qua (tương thích ngược)
        if page_id_cfg and entry.get("id") and str(entry.get("id")) != page_id_cfg:
            continue
        messaging = entry.get("messaging") or []
        if not isinstance(messaging, list):
            continue
        for ev in messaging:
            if not isinstance(ev, dict):
                continue
            sender_raw = ev.get("sender")
            sender = str((sender_raw or {}).get("id") or "") if isinstance(sender_raw, dict) else ""
            msg = ev.get("message") or {}
            if not isinstance(msg, dict):
                continue
            # L0b — lọc echo: tin do chính Page/bot gửi → tránh vòng lặp (§6.2a)
            if msg.get("is_echo"):
                continue
            text = str(msg.get("text") or "").strip()
            postback = ev.get("postback") or {}
            if not isinstance(postback, dict):
                postback = {}
            attachments = msg.get("attachments") or []
            if not isinstance(attachments, list):
                attachments = []
            if not sender:
                continue

            if not text and (attachments or postback):
                attachment_url = None
                attachment_type = ""
                if postback:
                    title = str(postback.get("title") or "lựa chọn nhanh").strip()
                    text = f"[Khách chọn: {title}]"
                    event_id = str(postback.get("mid") or f"postback:{sender}:{ev.get('timestamp')}:{postback.get('payload')}")
                else:
                    first = attachments[0] if attachments else {}
                    if not isinstance(first, dict):
                        first = {}
                    attachment_type = str(first.get("type") or "tệp")
                    attachment_url = str(first.get("payload", {}).get("url") or "") or None
                    attachment_labels = {"image": "ảnh", "audio": "âm thanh", "video": "video", "file": "tệp"}
                    text = f"[Khách gửi {attachment_labels.get(attachment_type, 'tệp đính kèm')}]"
                    event_id = str(msg.get("mid") or f"attachment:{sender}:{ev.get('timestamp')}")
                page_id = str(entry.get("id") or page_id_cfg).strip()
                store_id = resolve_store_id_from_page_id(page_id)
                if not fb_try_claim_scoped_event(
                    store_id=store_id,
                    page_id=page_id,
                    event_type="messaging",
                    external_event_id=event_id,
                ):
                    continue

                # Process attachment content if available
                if attachment_url:
                    try:
                        att_info = await process_attachment(first)
                        description, flagged_reasons = format_attachment_for_review(att_info)
                        queue_fb_non_text(
                            psid=sender,
                            event_id=event_id,
                            description=description if not att_info.error else text,
                            attachment_type=attachment_type,
                            attachment_url=attachment_url,
                            store_id=store_id
                        )
                    except Exception as e:
                        logger.warning("Attachment processing failed, falling back to basic queue: %s", e)
                        queue_fb_non_text(
                            psid=sender,
                            event_id=event_id,
                            description=text,
                            attachment_type=attachment_type,
                            attachment_url=attachment_url,
                            store_id=store_id
                        )
                else:
                    queue_fb_non_text(
                        psid=sender,
                        event_id=event_id,
                        description=text,
                        attachment_type=attachment_type,
                        attachment_url=attachment_url,
                        store_id=store_id
                    )
                n += 1
                continue

            # read / delivery và message không có nội dung → bỏ qua, không classify
            if not text:
                continue

            mid = str(msg.get("mid") or "").strip()
            # L0c — idempotency chống webhook retry (§6.2b)
            # Không dùng timestamp fallback: event thiếu ID không được vào pipeline.
            page_id = str(entry.get("id") or page_id_cfg).strip()
            if not mid or not page_id:
                continue
            store_id = resolve_store_id_from_page_id(page_id)
            if not fb_try_claim_scoped_event(
                store_id=store_id,
                page_id=page_id,
                event_type="messaging",
                external_event_id=mid,
            ):
                continue
            ts = _safe_float(ev.get("timestamp"))

            debounce_sec = _fb_debounce_delay()
            if debounce_sec > 0:
                await _FB_DEBOUNCE_MANAGER.push(
                    store_id=store_id,
                    page_id=page_id,
                    sender=sender,
                    mid=mid,
                    text=text,
                    ts=ts,
                    public_ctx=public_ctx,
                    callback=_execute_fb_pipeline,
                    delay_seconds=debounce_sec,
                )
                n += 1
            else:
                ok = await _execute_fb_pipeline(
                    store_id=store_id,
                    page_id=page_id,
                    sender=sender,
                    text=text,
                    mid=mid,
                    ts=ts,
                    public_ctx=public_ctx,
                )
                if ok:
                    n += 1

        changes = entry.get("changes") or []
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            if change.get("field") != "feed" or value.get("item") != "comment":
                continue
            if value.get("verb") != "add" or value.get("is_hidden"):
                continue
            author = value.get("from") or {}
            if not isinstance(author, dict):
                continue
            sender = str(author.get("id") or "")
            comment_id = str(value.get("comment_id") or "")
            text = str(value.get("message") or "").strip()
            if not sender or sender == page_id_cfg or not comment_id or not text:
                continue
            page_id = str(entry.get("id") or page_id_cfg).strip()
            store_id = resolve_store_id_from_page_id(page_id)
            if not fb_try_claim_scoped_event(
                store_id=store_id,
                page_id=page_id,
                event_type="comment",
                external_event_id=comment_id,
            ):
                continue

            # Determine if post is sensitive (default False since webhook doesn't provide this)
            post_is_sensitive = False

            # Analyze sentiment and classify action for comment
            sentiment = analyze_comment_sentiment(text)
            comment_action, flagged_reasons = classify_comment_action(text, sentiment, post_is_sensitive)

            moderation = moderate_fb_message(
                psid=sender,
                text=text,
                message_id=comment_id,
                timestamp=_safe_float(value.get("created_time")),
                public_context=public_ctx,
                source="comment",
                post_id=str(value.get("post_id") or "") or None,
                external_user_name=str(author.get("name") or "") or None,
                post_is_sensitive=post_is_sensitive,
                store_id=store_id,
            )

            # Add sentiment and comment action to moderation result
            moderation["sentiment"] = sentiment
            moderation["comment_action"] = comment_action
            moderation["flagged_reasons"] = list(set((moderation.get("flagged_reasons") or []) + flagged_reasons))

            # Mục 3b: comment chứa SĐT/địa chỉ riêng → ẩn ngay (bảo vệ PII,
            # không để lộ cho đối thủ) + trả lời công khai chuyển DM. Ẩn là
            # toàn quyền, không cần duyệt (Mục 6). Không auto-send nội dung
            # nhạy cảm.
            pii_action = classify_comment_pii_action(text)
            if pii_action.get("should_hide"):
                try:
                    hide_comment(comment_id)
                except Exception:
                    pass
                if moderation.get("action") not in {"block_silent", "block_polite"}:
                    public_reply = pii_action.get("reply_public")
                    if public_reply:
                        try:
                            reply_to_comment(comment_id, public_reply)
                        except Exception:
                            pass
                    review_id = moderation.get("review_id")
                    if review_id is not None:
                        final_resp = public_reply or "Đã ẩn comment chứa thông tin cá nhân."
                        fb_review_decide(
                            int(review_id), status="auto_sent", decided_by="fb_auto",
                            final_response=final_resp,
                        )
                n += 1
                continue

            if moderation.get("action") not in {"block_silent", "block_polite"}:
                # Comment công khai.
                # - Nếu policy cho auto_send (intent an toàn + confidence cao,
                #   COMMENT_SAFE_INTENTS + AUTO_THRESHOLD_COMMENT) VÀ cờ
                #   auto_send bật: gửi trả lời công khai ngay, không cần QL
                #   duyệt. Ưu tiên LLM draft thông minh, fallback về response
                #   template đã qua supervisor.
                # - Ngược lại: sinh LLM draft cho QL duyệt tay (ADR-008).
                if (
                    moderation.get("action") == "auto_send"
                    and moderation.get("response")
                    and _fb_auto_send_enabled()
                ):
                    final_text = str(moderation["response"]).strip()
                    if agent_mode() == "live":
                        try:
                            comment_draft = await draft_llm_reply(
                                text=text,
                                public_context=public_ctx,
                                is_comment=True,
                            )
                            if comment_draft:
                                sup = supervise_outgoing_response(text, comment_draft)
                                if sup.is_approved and sup.sanitized_response.strip():
                                    final_text = sup.sanitized_response.strip()
                        except Exception:
                            pass
                    delivered = _page_mode() != "live"
                    if _page_mode() == "live":
                        try:
                            reply_to_comment(comment_id, final_text)
                            delivered = True
                        except Exception:
                            delivered = False
                    review_id = moderation.get("review_id")
                    if review_id is not None:
                        if delivered:
                            fb_review_finalize_claim(
                                int(review_id),
                                status="auto_sent",
                                decided_by="fb_auto",
                                final_response=final_text,
                            )
                        else:
                            fb_review_release_claim(int(review_id))
                elif agent_mode() == "live" and "review_id" in moderation and moderation.get("review_id"):
                    try:
                        comment_draft = await draft_llm_reply(
                            text=text,
                            public_context=public_ctx,
                            is_comment=True,
                        )
                        if comment_draft:
                            sup = supervise_outgoing_response(text, comment_draft)
                            if sup.is_approved and sup.sanitized_response.strip():
                                fb_review_update_proposed(
                                    int(moderation["review_id"]),
                                    proposed_response=sup.sanitized_response.strip(),
                                )
                    except Exception:
                        pass
                n += 1
    return {"ok": True, "n": n}


def _thread_display_name(thread: dict[str, Any]) -> str:
    """Tên hiển thị ưu tiên cho 1 hội thoại Messenger.

    Thứ tự ưu tiên (fallback liên tục để không bao giờ để trống):
      1. `sender_name` đã lưu sẵn (nếu có — sync Graph / test), loại bỏ sentinel "Khách".
      2. `customer_name` — trường tên khách từ fixture/vận hành.
      3. `from` tên khách Graph trả về khi sync (fetch_conversations).
      4. `customer_profile.ten_khach` — AI trích xuất từ tin nhắn (customer_memory).
      5. Mã PSID rút gọn để vẫn phân biệt được ai đang nhắn (tránh "Khách" chung chung).
    """
    raw = thread.get("sender_name") or thread.get("customer_name") or thread.get("from") or ""
    if isinstance(raw, str) and raw.strip() and raw.strip() not in {"Khách", "Khách hàng", "Customer"}:
        return raw.strip()
    prof = thread.get("customer_profile")
    if isinstance(prof, dict):
        ten = prof.get("ten_khach")
        if isinstance(ten, str) and ten.strip():
            return ten.strip()
    psid = str(thread.get("psid") or thread.get("sender_id") or "")
    if psid:
        return f"Khách {psid[-4:]}"
    return "Khách"


def _thread_display_avatar(thread: dict[str, Any]) -> str:
    """Ảnh đại diện người nhắn: ưu tiên URL đã lưu, fallback về URL ổn định theo PSID.

    Messenger Profile API của Meta (POST /{psid}?fields=profile_pic) chỉ gọi được khi
    khách đã tương tác trong 24h — nên với khách cũ chúng ta dùng URL trừu tượng ổn định
    theo PSID để giao diện vẫn có avatar riêng cho từng người.
    """
    existing = thread.get("sender_avatar") or (thread.get("customer_profile") or {}).get("avatar_url")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    psid = str(thread.get("psid") or thread.get("sender_id") or "")
    if not psid:
        return ""
    import hashlib

    digest = hashlib.sha1(psid.encode("utf-8")).hexdigest()  # noqa: S324 — chỉ để tạo màu nền, không dùng cho bảo mật
    return f"https://api.dicebear.com/9.x/initials/svg?seed={digest}&backgroundColor=7c5c3e,8d6e63,bcaaa4,5d4037,6d4c41"


def _enrich_threads_for_display(threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bổ sung trường hiển thị (sender_name, sender_avatar) cho từng hội thoại.

    KHÔNG ghi đè dữ liệu gốc trong store — chỉ làm giàu ở tầng API trả về,
    giữ nguyên fail-closed (không phụ thuộc Graph thời gian thực).
    """
    out: list[dict[str, Any]] = []
    for t in threads:
        display = dict(t)
        display["sender_name"] = _thread_display_name(t)
        avatar = _thread_display_avatar(t)
        if avatar:
            display["sender_avatar"] = avatar
        out.append(display)
    return out


@router.get("/api/v1/page/threads")
def page_threads(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_manager(authorization)
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    doc = _page_store(store_id)
    threads = doc.get("threads", [])
    # Update is_within_24h dynamic flag
    for t in threads:
        t["is_within_24h"] = is_within_24h_window(t.get("last_message_ts"))
    return {
        "items": _enrich_threads_for_display(threads),
        "mode": _page_mode(),
        "nguon": "quan",
        "store_id": store_id,
    }


class PageReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    tag: str | None = None


@router.post("/api/v1/page/threads/{thread_id}/reply")
def page_reply(
    thread_id: str,
    body: PageReplyBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    _require_manager(authorization)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="noi_dung_trong")

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)

    found: dict[str, Any] | None = None

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        nonlocal found
        for th in doc.get("threads", []):
            if th.get("id") == thread_id:
                th["pending_approval"] = False
                replies = th.setdefault("replies", [])
                replies.append(
                    {
                        "id": f"pr_{uuid.uuid4().hex[:6]}",
                        "text": body.text.strip(),
                        "by": s.get("display_name", s["nv_id"]),
                        "at": _now(),
                        "mock": _page_mode() != "live",
                    }
                )
                found = th
                break
        return doc

    # Ghi vào ĐÚNG key mà _page_store đọc (page_quan:{store_id}) — tránh mất
    # tin trả lời vì ghi vào key legacy "page_quan" không ai đọc.
    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    if not found:
        raise HTTPException(status_code=404, detail="thread")
    graph_sent = False
    if _page_mode() == "live":
        psid = str(found.get("psid") or "")
        if psid:
            try:
                tag = body.tag
                if not tag and not is_within_24h_window(found.get("last_message_ts")):
                    tag = "CONFIRMED_EVENT_UPDATE"
                send_messenger_text(psid, body.text.strip(), tag=tag)
                graph_sent = True
            except RuntimeError as e:
                raise HTTPException(status_code=502, detail=str(e)[:180]) from e

    _audit(
        s["nv_id"],
        "page_reply",
        {"thread_id": thread_id, "text": body.text.strip(), "graph_sent": graph_sent, "store_id": store_id},
    )
    return {"ok": True, "thread": found, "mode": _page_mode(), "graph_sent": graph_sent, "store_id": store_id}


class PageThreadApproveBody(BaseModel):
    final_reply: str = Field(min_length=1, max_length=5000)
    tag: str | None = None


@router.post("/api/v1/page/threads/{thread_id}/approve")
def page_thread_approve(
    thread_id: str,
    body: PageThreadApproveBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Quản lý duyệt câu trả lời gợi ý của bot hoặc sửa câu trả lời trước khi gửi."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    _require_manager(authorization)
    if not body.final_reply.strip():
        raise HTTPException(status_code=422, detail="noi_dung_trong")
    found: dict[str, Any] | None = None
    suggested_orig: str = ""

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        nonlocal found, suggested_orig
        for th in doc.get("threads", []):
            if th.get("id") == thread_id:
                suggested_orig = str(th.get("suggested_reply") or "")
                th["pending_approval"] = False
                replies = th.setdefault("replies", [])
                replies.append(
                    {
                        "id": f"pr_{uuid.uuid4().hex[:6]}",
                        "text": body.final_reply.strip(),
                        "by": f"Quản lý {s.get('display_name', s['nv_id'])} (Đã duyệt)",
                        "at": _now(),
                        "mock": _page_mode() != "live",
                    }
                )
                found = th
                break
        return doc

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    # Ghi vào ĐÚNG key _page_store đọc (page_quan:{store_id}) — chống mất trả lời.
    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    if not found:
        raise HTTPException(status_code=404, detail="thread")

    graph_sent = False
    if _page_mode() == "live":
        psid = str(found.get("psid") or "")
        if psid:
            try:
                tag = body.tag
                if not tag and not is_within_24h_window(found.get("last_message_ts")):
                    tag = "CONFIRMED_EVENT_UPDATE"
                send_messenger_text(psid, body.final_reply.strip(), tag=tag)
                graph_sent = True
            except RuntimeError as e:
                raise HTTPException(status_code=502, detail=str(e)[:180]) from e

    # ── Vòng lặp học từ câu sửa của Quản lý (CSKH Golden Memory) ──
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    clean_final = body.final_reply.strip()
    msgs = found.get("messages") or []
    cust_msg = ""
    for m in reversed(msgs):
        if m.get("from_customer"):
            cust_msg = str(m.get("text") or "")
            break

    if cust_msg and suggested_orig and clean_final != suggested_orig:
        pair = extract_cskh_golden_pair(
            customer_msg=cust_msg,
            ai_draft=suggested_orig,
            manager_reply=clean_final,
            intent=str(found.get("intent") or "khac"),
            customer_name=str(found.get("sender_name") or "Khách hàng"),
        )
        if pair:
            def mut_golden(items: list[dict[str, Any]] | None, _p: dict[str, Any] = pair) -> list[dict[str, Any]]:
                lst = [x for x in (items or []) if x.get("customer_msg") != _p["customer_msg"]]
                lst.insert(0, _p)
                return lst[:20]

            kv_mutate(f"cskh_golden_memory:{store_id}", mut_golden, [])

    conversation_id = str(found.get("psid") or found.get("sender_id") or thread_id)
    manager_feedback = "manager_edit" if suggested_orig and clean_final != suggested_orig else "manager_approve"
    _record_fb_feedback(
        store_id=store_id, conversation_id=conversation_id, feedback_type=manager_feedback,
        original=suggested_orig, final=clean_final, actor_user_id=s["nv_id"], actor_role=str(s["role"]),
        generation_id=str(found.get("ai_generation_id") or "") or None,
    )
    _record_fb_feedback(
        store_id=store_id, conversation_id=conversation_id,
        feedback_type="send_success" if graph_sent else "send_failure", final=clean_final,
        actor_user_id=s["nv_id"], actor_role="system",
        send_status="sent" if graph_sent else "failed",
        failure_code=None if graph_sent else "not_sent_or_replay",
        generation_id=str(found.get("ai_generation_id") or "") or None,
    )

    # Cập nhật hồ sơ Khách quen nếu có
    if cust_msg:
        prefs = extract_customer_preferences([cust_msg])
        psid = str(found.get("psid") or found.get("sender_id") or "")
        if psid and (prefs.get("ten_khach") or prefs.get("favorite_drinks") or prefs.get("special_notes")):
            def mut_cust(cur: dict[str, Any] | None) -> dict[str, Any]:
                return merge_customer_profile(cur, prefs)

            kv_mutate(f"customer_profile:{store_id}:{psid}", mut_cust, {})

    # Audit log with diff tracking
    _audit(
        s["nv_id"],
        "page_thread_approve",
        {
            "thread_id": thread_id,
            "suggested": suggested_orig,
            "final": body.final_reply.strip(),
            "diff_detected": suggested_orig.strip() != body.final_reply.strip(),
            "graph_sent": graph_sent,
        },
    )
    return {"ok": True, "thread": found, "graph_sent": graph_sent}


# ── FB moderation inbox (kế hoạch chatbot §3.8) ───────────────────────────


class FbInboxDecideBody(BaseModel):
    quyet_dinh: str = Field(pattern="^(duyet|sua_gui|tu_choi|chuyen_cap)$")
    noi_dung: str | None = None
    ly_do: str | None = None


@router.get("/api/v1/page/fb-inbox")
def fb_inbox_list(
    status: str | None = None,
    assigned_role: str | None = None,
    limit: int = 50,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Danh sách tin FB chờ duyệt. QL không xem hàng gán cho Chủ quán."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = _require_manager(authorization)
    if role == "quan_ly" and assigned_role == "chu_quan":
        raise HTTPException(status_code=403, detail="forbidden")
    visible_role = "quan_ly" if role == "quan_ly" else assigned_role
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    items = fb_review_list(status=status, assigned_role=visible_role, limit=limit, store_id=store_id)
    for it in items:
        it["flagged_reasons"] = json.loads(it.get("flagged_reasons") or "[]")
    return {"items": items, "role": role}


@router.get("/api/v1/page/fb-inbox/stats")
def fb_inbox_stats(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    return fb_stats(store_id)


@router.get("/api/v1/page/fb-inbox/{item_id}")
def fb_inbox_detail(
    item_id: int,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)
    item = fb_review_get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="khong_thay")
    item["flagged_reasons"] = json.loads(item.get("flagged_reasons") or "[]")
    return item


@router.post("/api/v1/page/fb-inbox/{item_id}/decide")
async def fb_inbox_decide(
    item_id: int,
    body: FbInboxDecideBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Duyệt / sửa rồi gửi / từ chối / chuyển cấp. RBAC theo assigned_role."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = _require_manager(authorization)
    item = fb_review_get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="khong_thay")
    if str(item.get("status")) != "pending":
        raise HTTPException(status_code=409, detail="da_quyet_truoc_do")
    # Escalate chủ quán: QL không được duyệt khi chưa được chuyển cấp
    if str(item.get("assigned_role")) == "chu_quan" and role != "chu_quan":
        raise HTTPException(status_code=403, detail="cho_chu_quan_duyet")

    customer_event_at = item.get("event_at") or item.get("created_at")
    if customer_event_at and not is_within_24h_window(str(customer_event_at)):
        fb_review_transition_pending(item_id, status="expired")
        raise HTTPException(status_code=409, detail="qua_cua_so_24h")

    if body.quyet_dinh == "tu_choi":
        updated = fb_review_decide(item_id, status="rejected", decided_by=s["nv_id"])
        if not updated:
            raise HTTPException(status_code=409, detail="da_quyet_truoc_do")
        page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
        store_id = resolve_store_id_from_page_id(page_id_cfg)
        _record_fb_feedback(
            store_id=store_id, conversation_id=str(item.get("external_psid") or item_id),
            feedback_type="manager_reject", original=str(item.get("proposed_response") or ""),
            actor_user_id=s["nv_id"], actor_role=str(s["role"]),
            generation_id=str(item.get("ai_generation_id") or "") or None,
        )
        _audit(s["nv_id"], "fb_inbox_decide", {"id": item_id, "q": "tu_choi"})
        return {"ok": True, "item": updated, "sent": False}

    if body.quyet_dinh == "chuyen_cap":
        fb_escalation_add(
            item_id, escalated_to="chu_quan",
            reason=body.ly_do or "chuyen_cap", notified_channel="in_app",
        )
        _audit(s["nv_id"], "fb_inbox_decide", {"id": item_id, "q": "chuyen_cap", "reason": body.ly_do})
        return {"ok": True, "item": fb_review_get(item_id), "sent": False}

    # duyet / sua_gui — gửi đúng transport theo nguồn đã lưu
    final_text = (body.noi_dung or str(item.get("proposed_response") or "")).strip()
    if not final_text:
        raise HTTPException(status_code=400, detail="thieu_noi_dung")
    psid = str(item.get("external_psid") or "")
    if not fb_review_transition_pending(item_id, status="approved"):
        raise HTTPException(status_code=409, detail="da_quyet_truoc_do")
    graph_sent = False
    if _page_mode() == "live" and psid:
        try:
            if str(item.get("source")) == "comment":
                reply_to_comment(str(item.get("external_thread_id") or ""), final_text)
            else:
                send_messenger_text(psid, final_text)
            graph_sent = True
        except Exception:
            graph_sent = False
    if graph_sent:
        updated = fb_review_finalize_claim(
            item_id,
            status="sent",
            decided_by=s["nv_id"],
            final_response=final_text,
        )
    else:
        fb_review_release_claim(item_id)
        updated = fb_review_get(item_id)
    proposed = str(item.get("proposed_response") or "")
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    _record_fb_feedback(
        store_id=store_id, conversation_id=str(item.get("external_psid") or item_id),
        feedback_type="manager_edit" if proposed and proposed != final_text else "manager_approve",
        original=proposed, final=final_text, actor_user_id=s["nv_id"], actor_role=str(s["role"]),
        generation_id=str(item.get("ai_generation_id") or "") or None,
    )
    _record_fb_feedback(
        store_id=store_id, conversation_id=str(item.get("external_psid") or item_id),
        feedback_type="send_success" if graph_sent else "send_failure", final=final_text,
        actor_user_id=s["nv_id"], actor_role="system", send_status="sent" if graph_sent else "failed",
        failure_code=None if graph_sent else "not_sent_or_replay",
        generation_id=str(item.get("ai_generation_id") or "") or None,
    )
    _audit(
        s["nv_id"],
        "fb_inbox_decide",
        {"id": item_id, "q": body.quyet_dinh, "graph_sent": graph_sent,
         "final_len": len(final_text)},
    )
    # Broadcast real-time update to fb-inbox
    updated = updated or {}
    await chat_ws_manager.broadcast_all({
        "event": "fb_inbox:update",
        "data": {
            "id": item_id,
            "store_id": store_id,
            "status": updated.get("status"),
            "final_response": updated.get("final_response"),
            "decided_by": updated.get("decided_by"),
            "decided_at": updated.get("decided_at"),
            "sent": graph_sent,
        }
    })
    return {"ok": True, "item": updated, "sent": graph_sent}


# ── FB policy runtime config (kế hoạch §5.5 — Chủ quán chỉnh không cần sửa code) ──


class FbPolicyBody(BaseModel):
    auto_send_enabled: bool | None = None
    auto_price_cap_vnd: int | None = None
    jev_enabled: bool | None = None
    note: str | None = None


def _fb_policy_get() -> dict[str, Any]:
    """Đọc config hiện tại (env override lên trước)."""
    return {
        "auto_send_enabled": _fb_auto_send_enabled(),
        "auto_price_cap_vnd": int(
            os.environ.get("NHIPQUAN_FB_AUTO_PRICE_CAP_VND", "100000")
        ),
        "jev_enabled": fb_jev_enabled(),
        "page_mode": _page_mode(),
        "intent_thresholds": {
            "chao_hoi": 0.90,
            "hoi_gio_dia_chi": 0.85,
            "hoi_menu_gia": 0.85,
        },
        "comment_threshold": 0.85,
        "sla_minutes": {
            "priority_review": 5,
            "queue_review": 10,
            "escalate_owner": 15,
            "comment_queue": 15,
        },
    }


@router.get("/api/v1/page/fb-policy")
def fb_policy_get(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chủ quán (và QL) xem policy hiện tại."""
    _require_manager(authorization)
    return _fb_policy_get()


@router.put("/api/v1/page/fb-policy")
def fb_policy_set(
    body: FbPolicyBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chỉ Chủ quán mới được chỉnh `auto_send_enabled` + `auto_price_cap_vnd`.

    Thay đổi ghi audit + cập nhật env process hiện tại (tác dụng cho tới restart
    service; rollback bằng tắt flag qua env file). Ngưỡng intent/SLA cố định
    trong code (quyết định kinh doanh — đổi phải PR mới).
    """
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    if s.get("role") != "chu_quan":
        raise HTTPException(status_code=403, detail="chi_chu_quan")
    changes: dict[str, Any] = {}
    from ca_api.services.fb_moderation import set_fb_policy_runtime

    if body.auto_price_cap_vnd is not None and body.auto_price_cap_vnd < 0:
        raise HTTPException(status_code=400, detail="price_cap_am")
    if (
        body.auto_send_enabled is not None
        or body.auto_price_cap_vnd is not None
        or body.jev_enabled is not None
    ):
        set_fb_policy_runtime(
            auto_send_enabled=body.auto_send_enabled,
            auto_price_cap_vnd=body.auto_price_cap_vnd,
            jev_enabled=body.jev_enabled,
        )
    if body.auto_send_enabled is not None:
        changes["auto_send_enabled"] = body.auto_send_enabled
    if body.auto_price_cap_vnd is not None:
        changes["auto_price_cap_vnd"] = int(body.auto_price_cap_vnd)
    if body.jev_enabled is not None:
        changes["jev_enabled"] = body.jev_enabled
    _audit(
        s["nv_id"],
        "fb_policy_update",
        {"changes": changes, "note": body.note or ""},
    )
    return _fb_policy_get()


class ApplyProposalBody(BaseModel):
    proposal_id: str
    title: str
    suggested_rule: str
    topic: str | None = None


@router.post("/api/v1/page/audit/reflection")
def page_audit_reflection(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tự động kích hoạt Báo cáo Tự phê bình CSKH hàng đêm cho Quán."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    _require_manager(authorization)

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    doc = _page_store(store_id)
    threads = doc.get("threads", [])

    report = run_nightly_cskh_reflection(threads, store_id=store_id)
    kv_set(f"cskh_reflection_reports:{store_id}", report)

    _audit(s["nv_id"], "cskh_nightly_reflection", {"csat": report["csat_score"], "proposals": len(report["playbook_rule_proposals"])})
    return {"ok": True, "report": report}


@router.get("/api/v1/page/audit/reflection/latest")
def get_latest_reflection(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lấy báo cáo tự phê bình CSKH mới nhất."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    report = kv_get(f"cskh_reflection_reports:{store_id}", None)
    if not report:
        doc = _page_store(store_id)
        threads = doc.get("threads", [])
        report = run_nightly_cskh_reflection(threads, store_id=store_id)
        kv_set(f"cskh_reflection_reports:{store_id}", report)
    return {"ok": True, "report": report}


@router.post("/api/v1/page/audit/reflection/apply-proposal")
def apply_reflection_proposal(
    body: ApplyProposalBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chấp thuận đề xuất cẩm nang từ báo cáo tự phê bình để đưa vào quy trình quán."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    _require_manager(authorization)

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    def mut_rules(rules: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        lst = list(rules or [])
        lst.append({
            "id": body.proposal_id,
            "title": body.title,
            "rule": body.suggested_rule,
            "topic": body.topic,
            "created_by": f"AI Reflection ({s.get('display_name', s['nv_id'])})",
            "created_at": _now(),
        })
        return lst

    kv_mutate(f"playbook_rules:{store_id}", mut_rules, [])

    _audit(s["nv_id"], "apply_cskh_proposal", {"proposal_id": body.proposal_id, "title": body.title})
    return {"ok": True, "message": f"Đã bổ sung '{body.title}' vào cẩm nang quán thành công!"}


class StoreProfileBody(BaseModel):
    """Thông tin quán — đi thẳng vào prompt trả lời khách, nên phải chặn dữ liệu rác.

    Bug QA đợt 5: endpoint nhận `dict[str, Any]` trần nên không kiểm gì —
    nhận cả `<script>` trong tên quán, hotline không phải số, và địa chỉ dài
    5.000 ký tự. Ba trường này đều được nhúng vào prompt của bot chăm sóc khách,
    nên rác ở đây thành rác trả lời khách thật.
    """

    ten_quan: str = Field(default="", max_length=120)
    dia_chi: str = Field(default="", max_length=300)
    tinh: str = Field(default="", max_length=80)
    thanh_pho: str = Field(default="", max_length=80)
    hotline: str = Field(default="", max_length=40)
    gio_mo_cua: str = Field(default="", max_length=120)
    wifi_ssid: str = Field(default="", max_length=60)
    wifi_pass: str = Field(default="", max_length=60)
    mo_ta: str = Field(default="", max_length=1000)
    chinh_sach_dat_ban: str = Field(default="", max_length=1000)
    huong_dan_agent: str = Field(default="", max_length=4000)


def _text_sach(value: str) -> str:
    """Bỏ thẻ HTML và ký tự điều khiển khỏi văn bản người dùng nhập.

    Không thay thế escape của React/Pydantic (chuỗi vẫn được escape khi render),
    nhưng chặn rác vô nghĩa đi vào prompt AI và log audit.
    """
    khong_the = re.sub(r"<[^>]*>", "", value)
    return "".join(ch for ch in khong_the if ch == "\n" or ch == "\t" or ord(ch) >= 32).strip()


@router.get("/api/v1/store/profile")
def get_profile(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Hồ sơ quán — CHỈ người đã đăng nhập.

    Bug QA đợt 6 (#38): endpoint trước đây KHÔNG có tham số `authorization` nên
    bất kỳ ai (không token / token sai) đều đọc được toàn bộ hồ sơ — kể cả
    `wifi_pass` và `huong_dan_agent` (hướng dẫn nội bộ cho AI). Đây là dữ liệu
    vận hành, không phải thông tin công khai: khách nhận thông tin qua chatbot
    (`format_public_context_for_prompt`), không qua API này.
    """
    _require_role(authorization)
    return get_store_profile()


@router.put("/api/v1/store/profile")
def update_profile(
    data: StoreProfileBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    sach = {k: _text_sach(v) for k, v in data.model_dump().items()}
    # Hotline: chỉ nhận chữ số và các ký tự ngăn cách thông dụng. Bỏ trống vẫn hợp lệ
    # (quán chưa cấu hình → bot trả "chưa cập nhật", xem ADR-008).
    hotline = sach["hotline"]
    if hotline and not re.fullmatch(r"[0-9+()\-.\s]{6,40}", hotline):
        raise HTTPException(status_code=422, detail="hotline_khong_hop_le")
    set_store_profile(sach)
    _audit(role, "store_profile_update", sach)
    return {"ok": True, "profile": get_store_profile()}


@router.get("/api/v1/store/promotions")
def get_promos(
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    """Khuyến mãi đang chạy — CHỈ người đã đăng nhập (cùng lý do #38)."""
    _require_role(authorization)
    return get_active_promotions()


@router.put("/api/v1/store/promotions")
def update_promos(
    promotions: list[dict[str, Any]],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    set_active_promotions(promotions)
    _audit(role, "store_promotions_update", {"count": len(promotions)})
    return {"ok": True, "promotions": get_active_promotions()}


class PageDraftBody(BaseModel):
    noi_dung: str = Field(min_length=1, max_length=10000)


@router.get("/api/v1/page/drafts")
def page_drafts(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_manager(authorization)
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    return {"items": _page_store(store_id).get("drafts", []), "mode": _page_mode(), "store_id": store_id}


@router.post("/api/v1/page/drafts")
def page_draft_create(
    body: PageDraftBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    if not body.noi_dung.strip():
        raise HTTPException(status_code=422, detail="noi_dung_trong")
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    item = {
        "id": f"pd_{uuid.uuid4().hex[:8]}",
        "noi_dung": body.noi_dung.strip(),
        "trang_thai": "cho_duyet",
        "by": role,
        "nguoi_tao": role,
        "at": _now(),
        "ngay_tao": _now(),
    }

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        doc.setdefault("drafts", []).insert(0, item)
        return doc

    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    return item


class PageDraftAIGenerateBody(BaseModel):
    topic: str
    tone: str = "than thien"


@router.post("/api/v1/page/drafts/ai-generate")
def page_draft_ai_generate(
    body: PageDraftAIGenerateBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic_bat_buoc")

    tone = (body.tone or "than thien").strip()
    noi_dung = ""
    try:
        import sys
        from pathlib import Path
        scripts_dir = str(Path(__file__).resolve().parents[4] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from fb_auto_poster import generate_content
        noi_dung = generate_content(topic, tone)
    except Exception:
        pass

    if not noi_dung.strip():
        try:
            from ca_agents.llm import complete
            sys_p = (
                "Ban la quan ly truyen thong cho quan ca phe 'Nhip Quan'. "
                "Hay viet mot bai dang Facebook tieng Viet 3-4 doan ngan, co emoji sinh dong, "
                "gioi thieu chu de theo yeu cau, ket thuc bang loi moi den quan (CTA), khong dung hashtag."
            )
            user_p = f"Chu de: {topic}. Giong: {tone}."
            res = complete(system=sys_p, user=user_p)
            if res.ok and res.text.strip():
                noi_dung = res.text.strip()
        except Exception:
            pass

    if not noi_dung.strip():
        noi_dung = (
            f"☕ Chào cả nhà! Hôm nay Nhịp Quán có gợi ý mới về '{topic}'. "
            f"Ghé quán thưởng thức cùng không gian yên tĩnh và wifi mạnh nhé! Hẹn gặp bạn hôm nay! ✨"
        )

    item = {
        "id": f"pd_{uuid.uuid4().hex[:8]}",
        "noi_dung": noi_dung,
        "trang_thai": "cho_duyet",
        "by": f"AI ({role})",
        "nguoi_tao": f"AI Copilot ({role})",
        "at": _now(),
        "ngay_tao": _now(),
        "topic": topic,
        "tone": tone,
    }

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        doc.setdefault("drafts", []).insert(0, item)
        return doc

    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    return item


class PageDraftDecideBody(BaseModel):
    quyet_dinh: str  # cho_duyet | duyet | tu_choi


@router.post("/api/v1/page/drafts/{draft_id}")
def page_draft_decide(
    draft_id: str,
    body: PageDraftDecideBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    if body.quyet_dinh not in {"cho_duyet", "duyet", "tu_choi"}:
        raise HTTPException(status_code=400, detail="quyet_dinh")
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    found: dict[str, Any] | None = None

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        nonlocal found
        for d in doc.get("drafts", []):
            if d.get("id") == draft_id:
                d["trang_thai"] = (
                    ("da_dang" if _page_mode() == "live" else "da_dang_mock")
                    if body.quyet_dinh == "duyet"
                    else body.quyet_dinh
                )
                d["quyet_boi"] = role
                d["quyet_luc"] = _now()
                found = d
                break
        return doc

    kv_mutate(f"page_quan:{store_id}", mut, _page_store(store_id))
    if not found:
        raise HTTPException(status_code=404, detail="draft")
    graph_post_id = None
    if body.quyet_dinh == "duyet" and _page_mode() == "live":
        try:
            pub = publish_page_post(str(found.get("noi_dung") or ""))
            graph_post_id = pub.get("id")

            def mark(doc: dict[str, Any]) -> dict[str, Any]:
                for d in doc.get("drafts", []):
                    if d.get("id") == draft_id:
                        d["trang_thai"] = "da_dang"
                        d["graph_post_id"] = graph_post_id
                        break
                return doc

            kv_mutate(f"page_quan:{store_id}", mark, _page_store(store_id))
            found = {**found, "trang_thai": "da_dang", "graph_post_id": graph_post_id}
        except RuntimeError as e:
            if os.environ.get("CA_AGENT_MODE", "").strip().lower() == "replay":
                pass
            else:
                raise HTTPException(status_code=502, detail=str(e)[:180]) from e
    _audit(
        role,
        "page_draft",
        {
            "id": draft_id,
            "q": body.quyet_dinh,
            "graph_post_id": graph_post_id,
        },
    )
    return found


class TreoFromThreadBody(BaseModel):
    thread_id: str
    ghi_chu: str = ""


@router.post("/api/v1/page/treo")
def page_treo(
    body: TreoFromThreadBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Cầu nối ops: thread page → việc treo (không CRM)."""
    _require_manager(authorization)
    page_id_cfg = os.environ.get("NHIPQUAN_FB_PAGE_ID", "").strip()
    store_id = resolve_store_id_from_page_id(page_id_cfg)
    doc = _page_store(store_id)
    th = next((t for t in doc.get("threads", []) if t.get("id") == body.thread_id), None)
    if not th:
        raise HTTPException(status_code=404, detail="thread")
    item = {
        "id": f"tr_pg_{uuid.uuid4().hex[:8]}",
        "mo_ta": body.ghi_chu or f"Từ page: {th.get('tom_tat', th.get('id'))}",
        "trang_thai": "dang_cho",
        "nguon": "page_quan",
        "thread_id": body.thread_id,
        "created_at": _now(),
    }

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.insert(0, item)
        return items

    kv_mutate("treo", mut, [])
    return item
