"""Chat REST & WebSocket routes with enterprise-grade security."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc

from ca_api.context_providers import ngay_hom_nay_vn
from ca_api.persist import (
    chat_conversation_create,
    chat_conversation_get,
    chat_conversation_list_for_user,
    chat_conversation_mute,
    chat_get_or_create_direct,
    chat_get_or_create_scheduler_direct,
    chat_message_create,
    chat_message_delete,
    chat_message_edit,
    chat_message_get,
    chat_message_pin,
    chat_message_react,
    chat_messages_list,
    chat_messages_search,
    chat_read_receipts_update,
    kv_mutate,
    user_is_active,
)
from ca_api.persist import (
    session as auth_session,
)
from ca_api.services.chat_ws import (
    chat_ws_manager,
    msg_rate_limiter,
    sanitize_text,
    ws_auth_ip_limiter,
)

router = APIRouter(tags=["chat"])

ROOT = Path(__file__).resolve().parents[6]
UPLOAD_DIR = ROOT / "data" / "uploads" / "chat"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


CHAT_ENABLED = os.environ.get("CHAT_ENABLED", "true").lower() in ("true", "1", "yes")


def _check_chat_enabled() -> None:
    if not CHAT_ENABLED:
        raise HTTPException(status_code=503, detail="he_thong_chat_tam_khoa_bao_tri")


def _require_user(authorization: str | None) -> dict[str, str]:
    _check_chat_enabled()
    sess = auth_session(authorization)
    if not sess:
        raise HTTPException(status_code=401, detail="chua_dang_nhap")
    if not user_is_active(sess["nv_id"]):
        raise HTTPException(status_code=403, detail="tai_khoan_da_vo_hieu_hoa")
    return sess


class CreateConvBody(BaseModel):
    conv_type: str = Field(..., description="'direct' hoặc 'group'")
    display_name: str = ""
    participant_nv_ids: list[str] = []
    target_nv_id: str | None = None
    avatar_url: str = ""


class SendMsgBody(BaseModel):
    content: str = ""
    msg_type: str = "text"
    metadata: dict[str, Any] = {}
    reply_to_id: str | None = None


class EditMsgBody(BaseModel):
    content: str


class ReactBody(BaseModel):
    emoji: str


class MuteBody(BaseModel):
    muted: bool = True


class PinMsgBody(BaseModel):
    pinned: bool = True


class AvailabilityCorrectionBody(BaseModel):
    text: str = Field(..., min_length=3)


# ── WebSocket Endpoint với First-Message Authentication ──────────────────────

@router.websocket("/ws/chat")
async def chat_websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"

    # 1. Kiểm tra rate limit brute-force theo IP
    if await ws_auth_ip_limiter.is_blocked(client_ip):
        await websocket.close(code=4001, reason="ip_blocked")
        return

    # 2. Chờ tin nhắn đầu tiên phải là auth trong vòng 5 giây
    try:
        raw_first = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        first_msg = json.loads(raw_first)
    except TimeoutError:
        await ws_auth_ip_limiter.record_failure(client_ip)
        try:
            await websocket.close(code=4001, reason="auth_timeout")
        except Exception:
            pass
        return
    except WebSocketDisconnect:
        return
    except Exception:
        await ws_auth_ip_limiter.record_failure(client_ip)
        try:
            await websocket.close(code=4001, reason="auth_invalid")
        except Exception:
            pass
        return

    if first_msg.get("event") != "auth" or not first_msg.get("token"):
        await ws_auth_ip_limiter.record_failure(client_ip)
        await websocket.close(code=4001, reason="auth_invalid")
        return

    token = str(first_msg.get("token")).strip()
    sess = auth_session(f"Bearer {token}") or auth_session(token)
    if not sess or not user_is_active(sess["nv_id"]):
        await ws_auth_ip_limiter.record_failure(client_ip)
        await websocket.close(code=4001, reason="auth_invalid")
        return

    # Auth thành công
    await ws_auth_ip_limiter.clear(client_ip)
    nv_id = sess["nv_id"]
    display_name = sess.get("display_name", nv_id)

    # Gửi ACK xác thực cho client
    try:
        await websocket.send_text(
            json.dumps({
                "event": "auth:ack",
                "data": {"nv_id": nv_id, "display_name": display_name, "role": sess.get("role")},
            })
        )
    except (WebSocketDisconnect, RuntimeError):
        return

    # Chỉ add connection vào broadcast group SAU KHI auth thành công
    await chat_ws_manager.connect(nv_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await chat_ws_manager.handle_client_message(nv_id, websocket, data)
    except WebSocketDisconnect:
        await chat_ws_manager.disconnect(nv_id, websocket)
    except Exception:
        await chat_ws_manager.disconnect(nv_id, websocket)


# ── REST Endpoints ───────────────────────────────────────────────────────────

@router.get("/api/v1/chat/conversations")
def list_conversations(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    store_id = sess.get("store_id", "quan_01")
    items = chat_conversation_list_for_user(nv_id, store_id)
    return {"items": items, "unread_total": sum(c.get("unread_count", 0) for c in items)}


@router.post("/api/v1/chat/conversations")
async def create_conversation(
    body: CreateConvBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    store_id = sess.get("store_id", "quan_01")

    if body.conv_type == "direct":
        if not body.target_nv_id:
            raise HTTPException(status_code=422, detail="thieu_target_nv_id")
        conv = chat_get_or_create_direct(store_id, nv_id, body.target_nv_id)
        return conv

    if body.conv_type == "group":
        display_name = sanitize_text(body.display_name) or "Nhóm mới"
        conv = chat_conversation_create(
            store_id=store_id,
            conv_type="group",
            display_name=display_name,
            created_by=nv_id,
            participant_nv_ids=body.participant_nv_ids,
            is_locked=False,
            avatar_url=body.avatar_url,
        )
        await chat_ws_manager.broadcast_to_conversation(
            conv["id"],
            {"event": "conversation:created", "data": conv},
        )
        return conv

    raise HTTPException(status_code=422, detail="loai_hoi_thoai_khong_hop_le")


@router.get("/api/v1/chat/scheduler")
def get_scheduler_conversation(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Get the one private scheduler conversation for the authenticated employee."""
    sess = _require_user(authorization)
    if sess.get("role") not in {"nhan_vien", "quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="vai_tro_khong_hop_le")
    store_id = str(sess.get("store_id") or "quan_01")
    return chat_get_or_create_scheduler_direct(store_id, str(sess["nv_id"]))


@router.get("/api/v1/chat/conversations/{conv_id}")
def get_conversation(
    conv_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    conv = chat_conversation_get(conv_id, sess["nv_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="khong_tim_thay_hoi_thoai")
    members = [str(p.get("nv_id")) for p in conv.get("participants", [])]
    if sess["nv_id"] not in members:
        raise HTTPException(status_code=403, detail="khong_co_quyen")
    return conv


@router.get("/api/v1/chat/conversations/{conv_id}/messages")
def get_messages(
    conv_id: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: str | None = Query(None),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    conv = chat_conversation_get(conv_id, sess["nv_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="khong_tim_thay_hoi_thoai")
    members = [str(p.get("nv_id")) for p in conv.get("participants", [])]
    if sess["nv_id"] not in members:
        raise HTTPException(status_code=403, detail="khong_co_quyen")
    messages = chat_messages_list(conv_id, limit=limit, before_id=before_id)
    return {"items": messages, "limit": limit, "before_id": before_id}


async def _reply_copilot_bg(conv_id: str, prompt: str, sess: dict[str, Any]) -> None:
    try:
        from ca_agents.ag_copilot import run_copilot
        verified_context = {
            "store_id": sess.get("store_id", "quan_01"),
            "user_id": sess.get("nv_id", "system"),
            "user_role": sess.get("role", "nhan_vien"),
            "active_date": ngay_hom_nay_vn(),
            "channel": "chat",
            "recent_messages": [],
        }
        res = run_copilot(prompt, verified_context)
        reply_content = res.reply_text if res else "Tôi đã nhận được yêu cầu."
        meta: dict[str, Any] = {}
        msg_type = "text"
        proposal = getattr(res, "action_proposal", None) if res else None
        if proposal is not None:
            msg_type = "ops_card"
            meta["proposal"] = proposal.model_dump()

        copilot_msg = chat_message_create(
            conv_id=conv_id,
            sender_id="copilot",
            content=reply_content,
            msg_type=msg_type,
            metadata=meta,
        )
        await chat_ws_manager.broadcast_to_conversation(
            conv_id,
            {"event": "message:new", "data": copilot_msg},
        )
    except Exception:
        pass


@router.post("/api/v1/chat/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: SendMsgBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]

    if not await msg_rate_limiter.check_and_record(nv_id):
        raise HTTPException(status_code=429, detail="gui_tin_qua_nhanh_toi_da_30_tin_phut")

    content = sanitize_text(body.content)
    if not content and not body.metadata.get("url"):
        raise HTTPException(status_code=422, detail="tin_nhan_rong")

    try:
        msg = chat_message_create(
            conv_id=conv_id,
            sender_id=nv_id,
            content=content,
            msg_type=body.msg_type,
            metadata=body.metadata,
            reply_to_id=body.reply_to_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    await chat_ws_manager.broadcast_to_conversation(
        conv_id,
        {"event": "message:new", "data": msg},
    )

    c_low = content.lower()
    if "@agent_lich" in c_low or "@lich" in c_low or "@xep_lich" in c_low or ("xếp lịch" in c_low and ("ai" in c_low or "bot" in c_low or "agent" in c_low or "@" in c_low)):
        from ca_api.services.chat_scheduler_agent import handle_scheduling_request
        asyncio.create_task(handle_scheduling_request(conv_id, content, sess))
    elif "@copilot" in c_low:
        prompt = content
        for prefix in ("@copilot", "@Copilot"):
            prompt = prompt.replace(prefix, "")
        asyncio.create_task(_reply_copilot_bg(conv_id, prompt.strip() or "Xin chào", sess))
    elif any(w in c_low for w in ["rảnh", "đăng ký", "bận", "hôm nay", "ngày mai", "tuần sau"]):
        try:
            from ca_api.services.chat_scheduler_agent import submit_availability_confirmation
            draft = submit_availability_confirmation(
                conv_id=conv_id,
                nv_id=nv_id,
                display_name=str(sess.get("display_name") or nv_id),
                text=content,
                store_id=str(sess.get("store_id") or "quan_01"),
            )
            if draft:
                card = chat_message_create(
                    conv_id=conv_id,
                    sender_id="ai_scheduler",
                    content="Mình đã đọc lịch bận bên dưới. Bạn kiểm tra và bấm Đồng ý; nếu sai, bấm Chỗ sai để gửi lại thông tin.",
                    msg_type="ops_card",
                    metadata={
                        "workflow": "availability_confirmation",
                        "workflow_step": 2,
                        "availability_confirmation": draft,
                        "actions": ["confirm", "correct"],
                    },
                )
                await chat_ws_manager.broadcast_to_conversation(conv_id, {"event": "message:new", "data": card})
            else:
                clarification = chat_message_create(
                    conv_id=conv_id,
                    sender_id="ai_scheduler",
                    content="Mình chưa xác định được đủ ngày và khoảng giờ. Bạn ghi rõ, ví dụ: “ngày 22/9 em bận 8h-11h” hoặc “thứ ba tuần sau em rảnh ca tối” nhé.",
                    msg_type="system",
                    metadata={"workflow": "availability_confirmation", "status": "can_bo_sung"},
                )
                await chat_ws_manager.broadcast_to_conversation(conv_id, {"event": "message:new", "data": clarification})
        except (KeyError, ValueError, TypeError):
            clarification = chat_message_create(
                conv_id=conv_id,
                sender_id="ai_scheduler",
                content="Mình chưa đọc chắc chắn lịch bận. Bạn vui lòng ghi lại ngày và giờ bắt đầu-kết thúc để mình xác nhận đúng tuần.",
                msg_type="system",
                metadata={"workflow": "availability_confirmation", "status": "can_bo_sung"},
            )
            await chat_ws_manager.broadcast_to_conversation(conv_id, {"event": "message:new", "data": clarification})

    return msg


@router.post("/api/v1/chat/availability/{confirmation_id}/confirm")
async def confirm_chat_availability(
    confirmation_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    from ca_api.services.chat_scheduler_agent import update_availability_confirmation
    try:
        store_id = str(sess.get("store_id") or "quan_01")
        item = update_availability_confirmation(
            confirmation_id, nv_id=sess["nv_id"], status="da_xac_nhan", store_id=store_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="lich_ban_khong_ton_tai") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="khong_phai_nguoi_gui") from exc
    from ca_api.interfaces.http.sprint45 import _life, _save_life
    from ca_api.services.scheduling_service import run_authoritative_schedule

    week = str(item["tuan_iso"])
    lifecycle = _life(week, store_id=store_id)
    schedule_run = None
    if lifecycle.get("trang_thai") not in {"da_duyet", "da_cong_bo", "da_dong"}:
        schedule_run = run_authoritative_schedule(
            store_id=store_id,
            tuan_iso=week,
            actor_id=str(sess["nv_id"]),
            idempotency_key=f"availability:{confirmation_id}",
        )
        result = schedule_run.get("result") or {}
        lifecycle["tuan_iso"] = week
        lifecycle["schedule_run"] = schedule_run
        lifecycle["solver"] = result
        lifecycle["trang_thai"] = "cho_duyet" if result.get("ok") else "nhap"
        _save_life(lifecycle, store_id=store_id)
    card = chat_message_create(
        conv_id=str(item["conv_id"]), sender_id="ai_scheduler",
        content=(
            "Đã xác nhận lịch bận và xếp lại lịch tuần này."
            if schedule_run else
            "Đã lưu lịch bận. Tuần này đã duyệt hoặc công bố nên hệ thống không tự xếp lại; quản lý phải mở lại có lý do nếu cần điều chỉnh."
        ),
        msg_type="system", metadata={"workflow": "availability_confirmation", "workflow_step": 2, "status": "da_xac_nhan", "confirmation_id": confirmation_id},
    )
    await chat_ws_manager.broadcast_to_conversation(str(item["conv_id"]), {"event": "message:new", "data": card})
    return {"ok": True, "confirmation": item, "schedule_run": schedule_run}


@router.post("/api/v1/chat/availability/{confirmation_id}/correct")
async def correct_chat_availability(
    confirmation_id: str,
    body: AvailabilityCorrectionBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    from ca_api.services.chat_scheduler_agent import update_availability_confirmation
    try:
        item = update_availability_confirmation(
            confirmation_id, nv_id=sess["nv_id"], status="cho_xac_nhan",
            correction=sanitize_text(body.text),
            store_id=str(sess.get("store_id") or "quan_01"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="lich_ban_khong_ton_tai") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="khong_phai_nguoi_gui") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="khong_doc_duoc_lich_ban") from exc
    card = chat_message_create(
        conv_id=str(item["conv_id"]), sender_id="ai_scheduler",
        content="Mình đã cập nhật lại lịch bận. Bạn kiểm tra lần nữa và bấm Đồng ý khi thông tin đúng.",
        msg_type="ops_card", metadata={"workflow": "availability_confirmation", "workflow_step": 2, "availability_confirmation": item, "actions": ["confirm", "correct"]},
    )
    await chat_ws_manager.broadcast_to_conversation(str(item["conv_id"]), {"event": "message:new", "data": card})
    return {"ok": True, "confirmation": item}


@router.post("/api/v1/chat/messages/{message_id}/pin")
async def pin_message(
    message_id: str,
    body: PinMsgBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    msg = chat_message_pin(message_id, sess["nv_id"], pinned=body.pinned)
    if not msg:
        raise HTTPException(status_code=403, detail="khong_the_ghim_tin_nhan")
    await chat_ws_manager.broadcast_to_conversation(
        msg["conversation_id"],
        {"event": "message:updated", "data": msg},
    )
    return msg


@router.patch("/api/v1/chat/messages/{message_id}")
async def edit_message(
    message_id: str,
    body: EditMsgBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    new_content = sanitize_text(body.content)
    if not new_content:
        raise HTTPException(status_code=422, detail="noi_dung_rong")

    msg = chat_message_edit(message_id, nv_id, new_content)
    if not msg:
        raise HTTPException(status_code=403, detail="khong_the_chinh_sua_tin_nhan")

    await chat_ws_manager.broadcast_to_conversation(
        msg["conversation_id"],
        {"event": "message:updated", "data": msg},
    )
    return msg


@router.delete("/api/v1/chat/messages/{message_id}")
async def delete_message(
    message_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    msg = chat_message_delete(message_id, nv_id)
    if not msg:
        raise HTTPException(status_code=403, detail="khong_co_quyen_thu_hoi")

    await chat_ws_manager.broadcast_to_conversation(
        msg["conversation_id"],
        {"event": "message:updated", "data": msg},
    )
    return msg




class TreoFromChatBody(BaseModel):
    ghi_chu: str | None = None


@router.post("/api/v1/chat/messages/{message_id}/treo")
async def treo_from_chat(
    message_id: str,
    body: TreoFromChatBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Biến tin nhắn chat thành việc treo — dùng đúng pipeline kv `treo`.

    Ai cũng treo được từ tin trong hội thoại mình tham gia; quản lý xem ở
    /treo như mọi việc treo khác. Trả bản ghi treo + link về tin gốc.
    """
    import uuid

    sess = _require_user(authorization)
    msg = chat_message_get(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="khong_tim_thay_tin_nhan")
    conv = chat_conversation_get(str(msg.get("conversation_id") or ""))
    members = [str(p.get("nv_id")) for p in (conv or {}).get("participants", [])] if conv else []
    if sess["nv_id"] not in members:
        raise HTTPException(status_code=403, detail="khong_trong_hoi_thoai")

    treo_id = f"treo_{uuid.uuid4().hex[:8]}"

    def mut(hung: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hung.append(
            {
                "id": treo_id,
                "nguon": "chat",
                "chat_message_id": message_id,
                "conversation_id": msg.get("conversation_id"),
                "nv_id": sess["nv_id"],
                "nhan_vien": sess["nv_id"],
                "noi_dung": (body.ghi_chu or str(msg.get("content") or ""))[:200],
                "trang_thai": "dang_cho",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        return hung

    kv_mutate("treo", mut, [])
    treo_item = {
        "id": treo_id,
        "ok": True,
        "noi_dung": (body.ghi_chu or str(msg.get("content") or ""))[:200],
        "link": "/treo",
    }
    await chat_ws_manager.broadcast_to_conversation(
        str(msg.get("conversation_id")),
        {"event": "message:treo", "data": {"message_id": message_id, "treo": treo_item}},
    )
    return treo_item
@router.post("/api/v1/chat/messages/{message_id}/reactions")
async def react_message(
    message_id: str,
    body: ReactBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    msg = chat_message_react(message_id, nv_id, body.emoji)
    if "conversation_id" in msg:
        await chat_ws_manager.broadcast_to_conversation(
            msg["conversation_id"],
            {"event": "message:updated", "data": msg},
        )
    return msg


@router.post("/api/v1/chat/conversations/{conv_id}/read")
async def mark_read(
    conv_id: str,
    message_id: str = Query(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    nv_id = sess["nv_id"]
    receipts = chat_read_receipts_update(conv_id, nv_id, message_id)
    await chat_ws_manager.broadcast_to_conversation(
        conv_id,
        {
            "event": "message:read",
            "data": {"conversation_id": conv_id, "nv_id": nv_id, "message_id": message_id, "receipts": receipts},
        },
    )
    return {"ok": True, "receipts": receipts}


@router.post("/api/v1/chat/conversations/{conv_id}/mute")
def mute_conversation(
    conv_id: str,
    body: MuteBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    chat_conversation_mute(conv_id, sess["nv_id"], body.muted)
    return {"ok": True, "muted": body.muted}


@router.get("/api/v1/chat/search")
def search_messages(
    q: str = Query(..., min_length=1),
    conv_id: str | None = Query(None),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    sess = _require_user(authorization)
    items = chat_messages_search(q, sess["nv_id"], conv_id=conv_id, store_id=sess.get("store_id", "quan_01"))
    return {"items": items, "query": q}


@router.get("/api/v1/chat/online")
def get_online_users(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_user(authorization)
    return {"online_users": chat_ws_manager.get_online_users()}


# ── File Upload với Magic Bytes Validation ───────────────────────────────────

# Magic bytes và phần mở rộng lưu trữ chuẩn cho các định dạng chat hỗ trợ.
MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x1a\x45\xdf\xa3", "audio/webm", ".webm"),
    (b"OggS", "audio/ogg", ".ogg"),
    (b"ID3", "audio/mpeg", ".mp3"),
]


def detect_media_type(header: bytes) -> tuple[str, str] | None:
    """Nhận dạng MIME và phần mở rộng từ nội dung thay vì tên file phía client."""
    if header.startswith(b"RIFF"):
        if header[8:12] == b"WEBP":
            return "image/webp", ".webp"
        if header[8:12] == b"WAVE":
            return "audio/wav", ".wav"
        return None
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "audio/mp4", ".m4a"
    for signature, mime_type, extension in MAGIC_SIGNATURES:
        if header.startswith(signature):
            return mime_type, extension
    return None


def validate_magic_bytes(header: bytes) -> bool:
    """Xác thực định dạng thực tế của file thông qua header bytes."""
    return detect_media_type(header) is not None


@router.post("/api/v1/chat/upload")
async def upload_chat_media(
    file: UploadFile = File(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_user(authorization)

    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="tep_qua_lon_toi_da_15mb")

    detected = detect_media_type(content[:32])
    if detected is None:
        raise HTTPException(status_code=415, detail="dinh_dang_tep_khong_hop_le_hoac_nguy_hiem")

    original_filename = file.filename or "media"
    mime_type, extension = detected

    safe_filename = f"{uuid.uuid4().hex}{extension}"
    dest_path = UPLOAD_DIR / safe_filename
    with open(dest_path, "wb") as f:
        f.write(content)

    return {
        "url": f"/api/v1/chat/uploads/{safe_filename}",
        "filename": sanitize_text(original_filename),
        "size": len(content),
        "mime_type": mime_type,
    }


@router.get("/api/v1/chat/uploads/{filename}")
def serve_chat_media(filename: str) -> FileResponse:
    safe_name = os.path.basename(filename)
    path = UPLOAD_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="khong_tim_thay_tep")
    with path.open("rb") as media_file:
        detected = detect_media_type(media_file.read(32))
    if detected is None:
        raise HTTPException(status_code=415, detail="dinh_dang_tep_khong_hop_le_hoac_nguy_hiem")
    return FileResponse(path, media_type=detected[0])
