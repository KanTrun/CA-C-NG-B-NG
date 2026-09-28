"""AG-COPILOT HTTP endpoints — Conversational dispatch, two-phase confirmation, VF gates & audit."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Iterator
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, ParamSpec, TypeVar

try:
    from datetime import UTC, datetime, timedelta
except ImportError:
    from datetime import datetime, timedelta, timezone
    UTC = timezone.utc

from ca_agents.ag_copilot import run_copilot
from ca_agents.ag_copilot.tool_registry import build_live_snapshot
from ca_contracts import (
    CAPABILITY_REGISTRY,
    COPILOT_ROLE_INTENT_MATRIX,
    CopilotIntent,
    CopilotResponse,
    capabilities_for_role,
    copilot_intents_allowed_for_role,
)
from ca_gates import compute_snapshot_hash, validate_scope, validate_stale
from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ca_api.context_providers import ngay_hom_nay_vn
from ca_api.persist import (
    copilot_audit_add,
    copilot_audit_list,
    copilot_commit_internal_execution,
    copilot_draft_compare_and_set_status,
    copilot_draft_get,
    copilot_draft_save,
    copilot_draft_update_status,
    copilot_execution_complete,
    copilot_execution_fail,
    copilot_execution_rearm_internal,
    copilot_execution_reserve,
    kv_get,
    kv_mutate,
)
from ca_api.persist import session as auth_session

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

_ROOT = Path(__file__).resolve().parents[6]
UPLOAD_DIR = _ROOT / "data" / "uploads" / "copilot"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Magic bytes và phần mở rộng cho các định dạng tệp đính kèm Copilot hỗ trợ
MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF-", "application/pdf", ".pdf"),
]


def detect_media_type(header: bytes) -> tuple[str, str] | None:
    """Nhận dạng MIME và phần mở rộng từ header bytes."""
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp", ".webp"
    for signature, mime_type, extension in MAGIC_SIGNATURES:
        if header.startswith(signature):
            return mime_type, extension
    return None


def _life_tuan_hien_tai() -> str:
    """Tuần ISO hiện tại của lifecycle lịch — dùng khi đề xuất không kèm tuần."""
    life = kv_get("lich_tuan_lifecycle", {}) or {}
    return str(life.get("tuan_iso") or "2026-W36")

_RATE_LIMIT_STORE: dict[str, list[float]] = {}


def _get_verified_user(authorization: str | None) -> dict[str, str]:
    """Extract authenticated session; fallback to default test user if auth not enforced in replay."""
    sess = auth_session(authorization)
    if sess:
        return {
            "username": sess["username"],
            "user_id": sess["nv_id"],
            "role": sess["role"],
            "store_id": sess["store_id"],
        }
    # For open endpoints with optional auth, check header or assign unauthenticated
    return {
        "username": "guest",
        "user_id": "nv_guest",
        "role": "nhan_vien",
        "store_id": "quan_01",
    }


def _require_user(authorization: str | None) -> dict[str, str]:
    """Validate user — raise 401 when token missing. For write-like endpoints.

    Giữ `_get_verified_user` cho endpoint đọc (Telegram/Zalo webhook có thể không
    có token user). Endpoint GHI dữ liệu (execute-action, amend) phải xác thực.
    """
    sess = auth_session(authorization)
    if not sess:
        raise HTTPException(status_code=401, detail="thieu_token_hoac_session_het_han")
    return {
        "username": sess["username"],
        "user_id": sess["nv_id"],
        "role": sess["role"],
        "store_id": sess["store_id"],
    }


def _check_rate_limit(user_id: str, max_per_min: int = 30) -> None:
    now = time.time()
    times = [t for t in _RATE_LIMIT_STORE.get(user_id, []) if now - t < 60]
    if len(times) >= max_per_min:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded:too_many_requests")
    times.append(now)
    _RATE_LIMIT_STORE[user_id] = times


# ── Request / Response Models ────────────────────────────────────────────────

class MessageRequestBody(BaseModel):
    message: str = Field(default="", max_length=2000)
    store_id: str = "quan_01"
    channel: str = "web"
    recent_messages: list[str] = Field(default_factory=list, max_length=3)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ExecuteActionBody(BaseModel):
    action_id: str
    decision: str = Field(pattern="^(approve|reject)$")
    idempotency_key: str = Field(default_factory=lambda: uuid.uuid4().hex)
    reason: str | None = None
    correction_diff: dict[str, Any] | None = None


class AmendActionBody(BaseModel):
    reason: str = Field(min_length=3)
    correction_diff: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: uuid.uuid4().hex)


class _NoCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _MailCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


class _HangingTaskCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noi_dung: str | None = Field(default=None, min_length=1, max_length=200)


class _TaskCompleteCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treo_id: str | None = Field(default=None, min_length=6, max_length=40)


class _ConsumptionCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hang: str | None = Field(default=None, min_length=1, max_length=60)
    so_luong: float | None = Field(default=None, gt=0)
    don_vi: str | None = Field(default=None, min_length=1, max_length=20)


class _MenuUpdateCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ten_mon: str | None = Field(default=None, min_length=1, max_length=60)
    gia: int | None = Field(default=None, gt=0)
    an: bool | None = None


class _OrderTransitionCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    don_id: str | None = Field(default=None, min_length=4, max_length=40)
    trang_thai: str | None = Field(default=None, pattern="^(cho_pha|dang_pha|xong|huy)$")
    ly_do_huy: str | None = Field(default=None, max_length=200)


class _PinCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ca_id: str | None = Field(default=None, min_length=3, max_length=40)
    nv_id: str | None = Field(default=None, min_length=3, max_length=40)
    pinned: bool | None = None


class _TkbConfirmCorrections(BaseModel):
    """PROPOSE_TKB_CONFIRM — chỉ cho sửa nv_id (khoảng bận phải qua đề xuất mới)."""

    model_config = ConfigDict(extra="forbid")

    nv_id: str | None = Field(default=None, min_length=3, max_length=40)


class _SwapConsentCorrections(BaseModel):
    """PROPOSE_SWAP_CONSENT — swap_id/người đồng ý không sửa được sau đề xuất."""

    model_config = ConfigDict(extra="forbid")


class _HandoverCorrections(BaseModel):
    """PROPOSE_HANDOVER — cho sửa nội dung bàn giao trước khi duyệt."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=3, max_length=2000)


class _PageDraftCorrections(BaseModel):
    """PROPOSE_PAGE_DRAFT — cho sửa nội dung bài đăng trước khi duyệt."""

    model_config = ConfigDict(extra="forbid")

    noi_dung: str | None = Field(default=None, min_length=3, max_length=5000)
    topic: str | None = Field(default=None, max_length=200)
    tone: str | None = Field(default=None, max_length=50)


_CORRECTION_MODELS: dict[str, type[BaseModel]] = {
    "SEND_MAIL": _MailCorrections,
    "PROPOSE_HANGING_TASK": _HangingTaskCorrections,
    "PROPOSE_TASK_COMPLETE": _TaskCompleteCorrections,
    "PROPOSE_CONSUMPTION_RECORD": _ConsumptionCorrections,
    "PROPOSE_MENU_UPDATE": _MenuUpdateCorrections,
    "PROPOSE_ORDER_TRANSITION": _OrderTransitionCorrections,
    "PROPOSE_PIN": _PinCorrections,
    "PROPOSE_PAGE_SYNC": _NoCorrections,
    "PROPOSE_PAGE_DRAFT": _PageDraftCorrections,
    # PR10 còn lại (R2_CONFIRM)
    "PROPOSE_TKB_CONFIRM": _TkbConfirmCorrections,
    "PROPOSE_SWAP_CONSENT": _SwapConsentCorrections,
    "PROPOSE_HANDOVER": _HandoverCorrections,
}


_Params = ParamSpec("_Params")
_Result = TypeVar("_Result")


def _recover_execution_failure(  # noqa: UP047 - keep Python 3.10 compatibility until CI is 3.12-only
    endpoint: Callable[_Params, _Result],
) -> Callable[_Params, _Result]:
    @wraps(endpoint)
    def wrapped(*args: _Params.args, **kwargs: _Params.kwargs) -> _Result:
        try:
            return endpoint(*args, **kwargs)
        except Exception as exc:
            body = kwargs.get("body")
            if isinstance(body, ExecuteActionBody) and copilot_draft_compare_and_set_status(
                body.action_id,
                "executing",
                "execution_failed",
            ):
                draft = copilot_draft_get(body.action_id)
                if draft:
                    copilot_execution_fail(
                        draft["store_id"],
                        body.action_id,
                        body.idempotency_key,
                        type(exc).__name__,
                    )
                    copilot_audit_add(
                        action_id=body.action_id,
                        actor_user_id="system",
                        store_id=draft["store_id"],
                        intent=draft["intent"],
                        decision="execution_failed",
                        payload_diff={"error_type": type(exc).__name__},
                        channel="web",
                        agent_name="ag_copilot",
                        controller_user_id=None,
                    )
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(status_code=500, detail="action_execution_failed") from exc
            raise

    return wrapped


def _current_snapshot_data(
    draft: dict[str, Any], payload: dict[str, Any] | None = None,
) -> Any:
    stored_payload = draft.get("payload_diff") or {}
    effective_payload = payload or stored_payload
    if (
        stored_payload.get("snapshot_version") == "live-v1"
    ):
        return build_live_snapshot(draft["intent"], draft["store_id"], effective_payload)
    if draft["intent"] == "INVENTORY_RESTOCK_CHECK":
        return [item for item in (kv_get("tieu_thu", []) or []) if isinstance(item, dict)]
    return payload


def _validate_correction_diff(intent: str, correction_diff: dict[str, Any] | None) -> dict[str, Any]:
    if not correction_diff:
        return {}
    model = _CORRECTION_MODELS.get(intent, _NoCorrections)
    try:
        return model.model_validate(correction_diff).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid_correction_diff") from exc
def _record_copilot_response(
    response: CopilotResponse,
    *,
    user: dict[str, str],
    message: str,
    channel: str,
    latency_ms: int,
) -> None:
    """Persist every proposal before exposing it to an approval-capable client."""
    if response.intent == CopilotIntent.OUT_OF_SCOPE and "vượt phạm vi vai trò" in response.reply_text:
        copilot_audit_add(
            action_id="n/a",
            actor_user_id=user["user_id"],
            store_id=user["store_id"],
            intent="role_blocked",
            decision="role_blocked",
            payload_diff={"message": message[:200]},
            channel=channel,
            latency_ms=latency_ms,
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )

    if response.action_proposal:
        prop_dict = response.action_proposal.model_dump()
        copilot_draft_save(prop_dict)
        copilot_audit_add(
            action_id=response.action_proposal.action_id,
            actor_user_id=user["user_id"],
            store_id=user["store_id"],
            intent=response.action_proposal.intent.value,
            decision="propose",
            payload_diff=response.action_proposal.payload_diff,
            channel=channel,
            latency_ms=latency_ms,
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )


# ── 0. File Upload & Serve ───────────────────────────────────────────────────

@router.post("/upload")
async def copilot_upload(
    file: UploadFile = File(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Upload tệp đính kèm (ảnh TKB, phiếu, tài liệu) cho AG-COPILOT."""
    user = _get_verified_user(authorization)
    _check_rate_limit(user["user_id"])

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="tep_qua_lon_toi_da_10mb")

    detected = detect_media_type(content[:32])
    if detected is None:
        raise HTTPException(status_code=415, detail="dinh_dang_tep_khong_hop_le_hoac_nguy_hiem")

    original_filename = file.filename or "attachment"
    mime_type, extension = detected

    upload_id = f"up_{uuid.uuid4().hex[:12]}"
    safe_filename = f"{upload_id}{extension}"
    dest_path = UPLOAD_DIR / safe_filename
    dest_path.write_bytes(content)

    return {
        "url": f"/api/v1/copilot/uploads/{safe_filename}",
        "filename": original_filename[:120],
        "size": len(content),
        "mime_type": mime_type,
        "upload_id": upload_id,
        "local_path": str(dest_path),
    }


@router.get("/uploads/{filename}")
def serve_copilot_media(filename: str) -> FileResponse:
    """Serve tệp đính kèm đã tải lên cho AG-COPILOT."""
    safe_name = os.path.basename(filename)
    path = UPLOAD_DIR / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="khong_tim_thay_tep")
    with path.open("rb") as media_file:
        detected = detect_media_type(media_file.read(32))
    if detected is None:
        raise HTTPException(status_code=415, detail="dinh_dang_tep_khong_hop_le_hoac_nguy_hiem")
    return FileResponse(path, media_type=detected[0])


# ── 1. POST /api/v1/copilot/message ──────────────────────────────────────────

@router.post("/message", response_model=CopilotResponse)
def copilot_message(
    body: MessageRequestBody,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_telegram_secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> CopilotResponse:
    """Send natural language instruction to AG-COPILOT."""
    t0 = time.time()

    if not body.message.strip() and not body.attachments:
        raise HTTPException(status_code=422, detail="tin_nhan_hoac_tep_dinh_kem_khong_duoc_de_trong")

    # Webhook signature verification for Telegram if channel is telegram
    if body.channel == "telegram":
        expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if expected_secret and x_telegram_secret != expected_secret:
            raise HTTPException(status_code=401, detail="invalid_telegram_webhook_secret")

    user = _get_verified_user(authorization)
    _check_rate_limit(user["user_id"])

    effective_message = body.message.strip()
    if not effective_message and body.attachments:
        effective_message = "Đã gửi tệp đính kèm"

    # Enforce verified identity from server session
    # `active_date` phải theo giờ QUÁN (UTC+7), không phải UTC: sau 17:00 giờ VN
    # thì UTC đã sang ngày mới → agent tưởng "hôm nay" là hôm sau (bug QA đợt 4).
    verified_context = {
        "store_id": user["store_id"],
        "user_id": user["user_id"],
        "user_role": user["role"],
        "active_date": ngay_hom_nay_vn(),
        "channel": body.channel,
        "recent_messages": body.recent_messages,
        "attachments": body.attachments,
    }

    # Run AG-COPILOT
    response = run_copilot(effective_message, verified_context)
    latency_ms = int((time.time() - t0) * 1000)

    _record_copilot_response(
        response,
        user=user,
        message=effective_message,
        channel=body.channel,
        latency_ms=latency_ms,
    )

    return response


# ── 1b. POST /api/v1/copilot/message/stream (SSE) ────────────────────────────

@router.post("/message/stream")
def copilot_message_stream(
    body: MessageRequestBody,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """SSE streaming: `status` ngay → `meta` → `delta` từng phần → `done`.

    Vì sao phải đẩy `status` TRƯỚC `run_copilot`: bản cũ chạy `run_copilot()` xong
    HẾT rồi mới bắt đầu "stream" (`_chunk_text` 4 ký tự/lần). Nghĩa là byte đầu
    tiên chỉ ra sau khi đã xong 6 lượt đọc DB + (chế độ live) cả lượt gọi LLM —
    người dùng ngồi nhìn màn hình trống rồi chữ hiện ra một loạt. Đó không phải
    streaming, chỉ là văn bản đã hoàn tất được cắt nhỏ.

    Nay: `status` ra ngay trong ~ms đầu, phần text vẫn đi theo `delta`. Không hứa
    streaming token của LLM (chế độ replay không có LLM để stream) — chỉ bảo đảm
    phản hồi ĐẦU TIÊN tới ngay, và giữ nguyên hình dạng sự kiện cho client cũ.
    """
    t0 = time.time()
    user = _get_verified_user(authorization)
    _check_rate_limit(user["user_id"])
    if not body.message.strip() and not body.attachments:
        raise HTTPException(status_code=422, detail="tin_nhan_hoac_tep_dinh_kem_khong_duoc_de_trong")

    effective_message = body.message.strip()
    if not effective_message and body.attachments:
        effective_message = "Đã gửi tệp đính kèm"

    verified_context = {
        "store_id": user["store_id"],
        "user_id": user["user_id"],
        "user_role": user["role"],
        # Ngày theo giờ VN (UTC+7), không phải UTC — nếu dùng UTC thì sau 17:00
        # giờ VN agent nhận "ngày mai" (bug QA đợt 4: lệch ngày với /message).
        "active_date": ngay_hom_nay_vn(),
        "channel": body.channel,
        "recent_messages": body.recent_messages,
        "attachments": body.attachments,
    }

    def _sse(ev: str, payload: dict[str, Any]) -> str:
        return f"event: {ev}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _gen() -> Iterator[str]:
        # BƯỚC 0 — ra ngay. Client tắt được trạng thái "đang chờ" và biết máy đã nhận.
        yield _sse("status", {"stage": "dang_tra_cuu", "message": "Đang tra cứu dữ liệu…"})

        # 1. Copilot tất định (intent/tool/proposal). Chậm nhất ở đây, nhưng client
        #    đã có `status` để hiển thị nên không còn khoảng lặng.
        response = run_copilot(effective_message, verified_context)
        _record_copilot_response(
            response,
            user=user,
            message=effective_message,
            channel=body.channel,
            latency_ms=int((time.time() - t0) * 1000),
        )

        # 1b. Lưu draft khi có ActionProposal — /message/stream trước đây bỏ sót bước
        # này nên bấm "Duyệt & Gửi" ở UI bị 404 action_proposal_not_found.
        if response.action_proposal:
            copilot_draft_save(response.action_proposal.model_dump())
            copilot_audit_add(
                action_id=response.action_proposal.action_id,
                actor_user_id=user["user_id"],
                store_id=user["store_id"],
                intent=response.action_proposal.intent.value,
                decision="propose",
                payload_diff=response.action_proposal.payload_diff,
                channel=body.channel,
                latency_ms=0,
                agent_name="ag_copilot",
                controller_user_id=user["user_id"],
            )

        # 2. Meta: intent + confidence + action_proposal (client biết trước khi đọc chữ).
        meta = {
            "intent": response.intent.value if hasattr(response.intent, "value") else str(response.intent),
            "confidence": response.confidence,
            "action_proposal": (
                response.action_proposal.model_dump() if response.action_proposal else None
            ),
            "citations": list(getattr(response, "citations", []) or []),
            "direct_answer": getattr(response, "direct_answer", None),
            "agent_mode": getattr(response, "agent_mode", "replay"),
        }
        yield _sse("meta", meta)

        # 3. Text: stream từng phần, chia theo TỪ để không cắt giữa chữ.
        reply_text = response.reply_text or ""
        for chunk in _chunk_text_worlds(reply_text):
            yield _sse("delta", {"text": chunk})
        yield _sse("done", {"ok": True})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chunk_text(text: str, size: int = 4) -> list[str]:
    """Chia chuỗi thành các cụm nhỏ (SSE delta). Giữ nguyên khoảng trắng."""
    chars = list(text)
    return ["".join(chars[i : i + size]) for i in range(0, len(chars), size)]


def _chunk_text_worlds(text: str, per_chunk: int = 3) -> list[str]:
    """Chia theo TỪ (giữ khoảng trắng) — không cắt giữa một từ.

    Vì sao đổi khỏi `_chunk_text` (4 ký tự): cắt theo ký tự làm từ bị vỡ ("nhâ" /
    "n viên"), và với chữ tiếng Việt có dấu thì vỡ ngay giữa tổ hợp dấu. Cắt theo
    từ tốn thêm vài byte JSON mỗi sự kiện nhưng đọc được ngay cả khi mạng chậm.
    """
    if not text:
        return []
    words = text.split(" ")
    out: list[str] = []
    for i in range(0, len(words), per_chunk):
        piece = " ".join(words[i : i + per_chunk])
        if i + per_chunk < len(words):
            piece += " "
        out.append(piece)
    return out


# ── 2. POST /api/v1/copilot/execute-action ───────────────────────────────────

@router.post("/execute-action")
@_recover_execution_failure
def copilot_execute_action(
    body: ExecuteActionBody,
    background_tasks: BackgroundTasks,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Confirm/Approve or Reject an ActionProposal with VF-SCOPE, VF-STALE and Idempotency."""
    t0 = time.time()
    user = _require_user(authorization)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Fetch draft from DB
    draft = copilot_draft_get(body.action_id)
    if not draft:
        raise HTTPException(status_code=404, detail="action_proposal_not_found")

    # 2. VF-SCOPE: Multi-tenant and role check. Scope must precede replay so a
    # caller cannot use an executed action ID to discover another action.
    scope_res = validate_scope(
        caller_store_id=user["store_id"],
        target_store_id=draft["store_id"],
        caller_role=user["role"],
        intent=draft["intent"],
        action_created_by=draft["created_by"],
        caller_user_id=user["user_id"],
    )
    if not scope_res.passed:
        copilot_audit_add(
            action_id=body.action_id,
            actor_user_id=user["user_id"],
            store_id=user["store_id"],
            intent=draft["intent"],
            decision="authz_blocked",
            payload_diff={"reason": scope_res.reason},
            channel="web",
            latency_ms=int((time.time() - t0) * 1000),
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )
        raise HTTPException(status_code=403, detail=f"scope_blocked:{scope_res.reason}")

    correction_diff = (
        _validate_correction_diff(draft["intent"], body.correction_diff)
        if body.decision == "approve"
        else {}
    )
    request_hash = compute_snapshot_hash(
        {
            "action_id": body.action_id,
            "decision": body.decision,
            "reason": body.reason,
            "correction_diff": correction_diff,
        }
    )

    # 3. Durable replay is valid only for the same authorized request and key.
    if draft["status"] == "executed" and body.decision == "approve":
        receipt_status, outcome = copilot_execution_reserve(
            user["store_id"],
            body.action_id,
            body.idempotency_key,
            request_hash,
        )
        if receipt_status == "replay" and outcome:
            return outcome
        raise HTTPException(status_code=409, detail="idempotency_conflict")

    # Failed internal transactions can retry only after their DB transaction
    # rolled back; external mail failures remain terminal until reconciled.
    if draft["status"] == "execution_failed" and draft["intent"] in {
        "SCHEDULE_SOLVE", "APPROVE_SHIFT_SWAP", "INVENTORY_RESTOCK_CHECK",
        "PROPOSE_HANGING_TASK", "PROPOSE_TASK_COMPLETE", "PROPOSE_CONSUMPTION_RECORD",
        "PROPOSE_MENU_UPDATE", "PROPOSE_ORDER_TRANSITION", "PROPOSE_PIN",
        "PROPOSE_TKB_CONFIRM", "PROPOSE_SWAP_CONSENT", "PROPOSE_HANDOVER",
        "PROPOSE_PAGE_DRAFT", "RUN_CATCHMENT_SURVEY",
    } and body.decision == "approve":
        if not copilot_execution_rearm_internal(
            user["store_id"], body.action_id, body.idempotency_key, request_hash
        ):
            raise HTTPException(status_code=409, detail="action_retry_not_safe")
        draft = copilot_draft_get(body.action_id) or draft

    # 4. Only a proposal explicitly ready for approval may be decided.
    if draft["status"] not in {"ready_for_approval", "amendment_ready"}:
        raise HTTPException(
            status_code=409,
            detail=f"invalid_action_status:{draft['status']}",
        )

    # 5. Check expiration and fail closed on malformed timestamps.
    if draft["expires_at"]:
        try:
            exp_dt = datetime.fromisoformat(draft["expires_at"].replace("Z", "+00:00"))
            is_expired = datetime.now(UTC) > exp_dt
        except (AttributeError, TypeError, ValueError):
            copilot_audit_add(
                action_id=body.action_id,
                actor_user_id=user["user_id"],
                store_id=user["store_id"],
                intent=draft["intent"],
                decision="invalid_expiry",
                channel="web",
                latency_ms=int((time.time() - t0) * 1000),
                agent_name="ag_copilot",
                controller_user_id=user["user_id"],
            )
            raise HTTPException(status_code=400, detail="invalid_action_expiry") from None
        if is_expired:
            copilot_draft_update_status(body.action_id, "expired")
            copilot_audit_add(
                action_id=body.action_id,
                actor_user_id=user["user_id"],
                store_id=user["store_id"],
                intent=draft["intent"],
                decision="expired",
                channel="web",
                latency_ms=int((time.time() - t0) * 1000),
                agent_name="ag_copilot",
                controller_user_id=user["user_id"],
            )
            raise HTTPException(status_code=400, detail="action_proposal_expired")

    # 6. Handle REJECT
    if body.decision == "reject":
        if not copilot_draft_compare_and_set_status(
            body.action_id,
            "ready_for_approval",
            "rejected",
        ):
            raise HTTPException(status_code=409, detail="action_decision_conflict")
        copilot_audit_add(
            action_id=body.action_id,
            actor_user_id=user["user_id"],
            store_id=user["store_id"],
            intent=draft["intent"],
            decision="reject",
            payload_diff={"reason": body.reason},
            channel="web",
            latency_ms=int((time.time() - t0) * 1000),
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )
        return {
            "ok": True,
            "action_id": body.action_id,
            "status": "rejected",
            "message": "Action proposal rejected.",
        }

    receipt_status, outcome = copilot_execution_reserve(
        user["store_id"],
        body.action_id,
        body.idempotency_key,
        request_hash,
    )
    if receipt_status == "replay" and outcome:
        return outcome
    if receipt_status == "pending":
        raise HTTPException(status_code=409, detail="action_execution_in_progress")
    if receipt_status != "reserved":
        raise HTTPException(status_code=409, detail="idempotency_conflict")

    # 7. VF-STALE Check on APPROVE
    # Compute current data state snapshot
    effective_diff = dict(draft["payload_diff"])
    if draft["intent"] != "SEND_MAIL":
        effective_diff.update(correction_diff)
    current_snapshot_data = _current_snapshot_data(draft, effective_diff)
    current_hash = compute_snapshot_hash(current_snapshot_data)
    stale_res = validate_stale(
        draft_snapshot_hash=draft["data_snapshot_hash"],
        current_snapshot_hash=current_hash,
    )
    if not stale_res.passed:
        if not copilot_draft_compare_and_set_status(
            body.action_id,
            "ready_for_approval",
            "stale_rejected",
        ):
            raise HTTPException(status_code=409, detail="action_decision_conflict")
        copilot_audit_add(
            action_id=body.action_id,
            actor_user_id=user["user_id"],
            store_id=user["store_id"],
            intent=draft["intent"],
            decision="stale_rejected",
            payload_diff={"reason": stale_res.reason},
            channel="web",
            latency_ms=int((time.time() - t0) * 1000),
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )
        copilot_execution_fail(
            user["store_id"],
            body.action_id,
            body.idempotency_key,
            "stale_rejected",
        )
        raise HTTPException(status_code=409, detail=f"stale_rejected:{stale_res.reason}")

    # 8. Claim execution before any side effect. Only one concurrent request
    # can transition the proposal and enter an executor.
    claimed = copilot_draft_compare_and_set_status(
        body.action_id, draft["status"], "executing"
    ) if draft["status"] in {"ready_for_approval", "amendment_ready"} else False
    if not claimed:
        raise HTTPException(status_code=409, detail="action_execution_conflict")

    # 9. Apply Action Execution
    intent = draft["intent"]
    diff = draft["payload_diff"]
    orig_body = str(diff.get("body", ""))

    if correction_diff:
        diff.update(correction_diff)
        if intent == "SEND_MAIL":
            new_body = str(diff.get("body", ""))
            if orig_body and new_body and orig_body != new_body:
                from ca_agents.ag_mailwriter import extract_style_preferences

                prefs = extract_style_preferences(orig_body, new_body)
                if prefs:
                    store_key = f"mail_style_memory:{user['store_id']}"

                    def mut_style(cur: dict[str, Any] | None) -> dict[str, Any]:
                        style = dict(cur or {})
                        if prefs.get("greeting_style"):
                            style["greeting_style"] = prefs["greeting_style"]
                        if prefs.get("signoff_name"):
                            style["signoff_name"] = prefs["signoff_name"]
                        if prefs.get("brevity"):
                            style["brevity"] = prefs["brevity"]
                        samples = list(style.get("samples") or [])
                        samples.append({
                            "subject": str(diff.get("subject", "")),
                            "body": new_body,
                        })
                        style["samples"] = samples[-5:]
                        return style

                    kv_mutate(store_key, mut_style, {})

    internal_mutations: dict[str, tuple[Callable[[Any], Any], Any]] = {}
    if intent == "SCHEDULE_SOLVE":
        tuan_ap_dung = diff.get("tuan_iso") or diff.get("tuan") or _life_tuan_hien_tai()
        phan_cong_moi = diff.get("phan_cong", {})
        # Ghi đúng nơi /roster đọc: file lich_tuan.json (nguồn GET /api/v1/lich-tuan)
        # + kv phan_cong (nguồn /toi, đổi ca, công bằng) + lifecycle trạng thái mới.
        try:
            _env_out = os.environ.get("NHIPQUAN_LICH_TUAN_OUT")
            _lich_out = Path(_env_out) if _env_out else _ROOT / "data" / "out" / "lich_tuan.json"
            _lich_out.parent.mkdir(parents=True, exist_ok=True)
            payload_file = {
                "nguon": "quan",
                "adr": "ADR-012",
                "tuan_iso": tuan_ap_dung,
                "status": str(diff.get("status") or "OPTIMAL"),
                "ok": bool(diff.get("ok", True)),
                "elapsed_s": diff.get("elapsed_s"),
                "objective": diff.get("objective"),
                "violations": diff.get("violations", []),
                "phan_cong": phan_cong_moi,
                "debt_after": diff.get("debt_after", {}),
                "luat_ap_dung": diff.get("luat_ap_dung", []),
                "danh_sach_xung_dot": [],
            }
            _lich_out.write_text(
                json.dumps(payload_file, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # File system read-only (vài môi trường Docker) — kv vẫn là nguồn dự phòng.

        def mut_life(cur: dict[str, Any]) -> dict[str, Any]:
            life = dict(cur or {})
            # Giữ chuỗi duyệt chuẩn: đề xuất đã được quản lý duyệt ở bước
            # execute-action → trạng thái sau ghi là da_duyet (không nhảy
            # thẳng da_cong_bo bỏ bước công bố cho NV trên /roster).
            life["trang_thai"] = "da_duyet"
            life["tuan_iso"] = tuan_ap_dung
            life["cap_nhat_luc"] = now_iso
            life["cap_nhat_boi"] = "copilot_duyet"
            life["nguon"] = "copilot"
            return life

        def mut_roster_status(cur: dict[str, Any]) -> dict[str, Any]:
            st = dict(cur or {})
            week_st = dict(st.get(tuan_ap_dung) or {})
            # Quản lý đã duyệt lịch trên Copilot -> tự động xác nhận giữ ca cho tất cả nhân sự có ca
            for _cid, nvs in phan_cong_moi.items():
                if isinstance(nvs, list):
                    for nid in nvs:
                        week_st[str(nid)] = "xac_nhan"
            st[tuan_ap_dung] = week_st
            return st

        internal_mutations = {
            "phan_cong": (lambda _current: phan_cong_moi, {}),
            "lich_tuan": (lambda _current: phan_cong_moi, {}),
            "lich_tuan_status": (lambda _current: "da_duyet", ""),
            "lich_tuan_lifecycle": (mut_life, {}),
            "roster_nv_status": (mut_roster_status, {}),
        }

        try:
            from ca_api.services.chat_ws import notify_ops_changed
            background_tasks.add_task(notify_ops_changed, "roster:lifecycle", tuan_ap_dung)
            background_tasks.add_task(notify_ops_changed, "roster:nv-status", tuan_ap_dung)
        except Exception:
            pass
    elif intent == "APPROVE_SHIFT_SWAP":
        swap_id = diff.get("swap_id")
        # UI + tool hiện dùng KV "swap" (swap-market 3 nhánh, khóa "id").
        def mut_swap(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            for it in items:
                if it.get("id") == swap_id or it.get("swap_id") == swap_id:
                    it["trang_thai"] = "da_duyet"
                    it["duyet_ai"] = user["user_id"]
                    it["duyet_luc"] = now_iso
            return items
        internal_mutations["swap"] = (mut_swap, [])
        # Cũ (legacy) vẫn dùng khóa "shift_swaps" + "swap_id".
        def mut_legacy(swaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
            for sw in swaps:
                if sw.get("swap_id") == swap_id:
                    sw["trang_thai"] = "da_duyet"
            return swaps
        internal_mutations["shift_swaps"] = (mut_legacy, [])
        # Cập nhật phân công thật: hoán đổi người trong ca trên lịch tuần.
        ca_id = diff.get("ca_id")
        tu_nv, nhan_nv = diff.get("tu_nv"), diff.get("nhan_nv")
        if ca_id and tu_nv and nhan_nv:
            def mut_phan_cong(phan_cong: dict[str, Any]) -> dict[str, Any]:
                for ca, nvs in phan_cong.items():
                    if ca == ca_id and isinstance(nvs, list):
                        for i, nv in enumerate(nvs):
                            if nv == tu_nv:
                                nvs[i] = nhan_nv
                return phan_cong
            internal_mutations["phan_cong"] = (mut_phan_cong, {})
    elif intent == "CREATE_RULE_PROPOSAL":
        # Ghi luật thật vào cẩm nang sống (cam_nang.json) ở trạng thái de_xuat.
        de_xuat = diff.get("de_xuat")
        if isinstance(de_xuat, dict):
            try:
                from ca_playbook.vong_doi import list_luat, save_luat
                luat = list(list_luat() or [])
                luat.append(de_xuat)
                save_luat(luat)
            except Exception:
                # Fallback sang KV nếu playbook chưa khả dụng.
                def mut_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
                    rules.append(de_xuat)
                    return rules
                internal_mutations["rules"] = (mut_rules, [])
        else:
            def mut_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
                rules.append(diff)
                return rules
            internal_mutations["rules"] = (mut_rules, [])
    elif intent == "INVENTORY_RESTOCK_CHECK":
        # Tool trả data.canh_bao (danh sách mặt hàng dưới ngưỡng).
        items = diff.get("canh_bao") or diff.get("items") or []
        def mut_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
            orders.append({"order_id": f"ord_{uuid.uuid4().hex[:6]}", "items": items, "created_at": now_iso})
            return orders
        internal_mutations["restock_orders"] = (mut_orders, [])
    elif intent == "PROPOSE_TIME_OFF":
        # Cùng key/schema với inbox duyệt của AG-MSG (xin_nghi) — quản lý duyệt
        # ở /inbox, hiệu lực nạp vào lượt xếp lịch tới qua _run_solver.
        #
        # PHÂN BIỆT MỨC: nêu ca (start/end) → chỉ chặn đúng khung giờ đó
        # (y_dinh="cap_nhat_tkb"); chỉ nêu thứ → bận cả ngày (y_dinh="xin_nghi").
        # Trước đây luôn ghi 07:00–22:00 + xin_nghi nên "bận ca sáng" xoá cả ngày.
        _start = str(diff.get("start") or "").strip()
        _end = str(diff.get("end") or "").strip()
        _co_khung = bool(_start and _end)
        _y_dinh = "cap_nhat_tkb" if _co_khung else "xin_nghi"
        _muc_chu = (
            f"ca {_start}–{_end} {diff.get('thu')}"
            if _co_khung
            else f"cả ngày {diff.get('thu')}"
        )
        _rang_buoc: dict[str, Any] = {"thu": str(diff.get("thu") or "")}
        if _co_khung:
            _rang_buoc["start"] = _start
            _rang_buoc["end"] = _end

        def mut_inbox(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            items.append({
                "id": f"in_to_{uuid.uuid4().hex[:6]}",
                "agent": "ag_copilot",
                "nv_id": str(diff.get("nv_id") or user["user_id"]),
                "y_dinh": _y_dinh,
                "tom_tat": f"Copilot ghi nhận: bận {_muc_chu} ({diff.get('ly_do')})",
                "trang_thai": "cho_duyet",
                "do_tin_cay": 0.92,
                "nguon": "copilot",
                "rang_buoc": _rang_buoc,
                "hieu_luc": None,
                "created_at": now_iso,
            })
            return items
        internal_mutations["inbox_rang_buoc"] = (mut_inbox, [])
    elif intent == "PROPOSE_HANGING_TASK":
        # Cùng key/schema với route web /api/v1/phieu/{id}/treo (PR10 self-service).
        def mut_treo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            items.append({
                "id": f"treo_{uuid.uuid4().hex[:8]}",
                "nv_id": user["user_id"],
                "nhan_vien": user["user_id"],
                "noi_dung": str(diff.get("noi_dung") or ""),
                "trang_thai": "dang_cho",
                "created_at": now_iso,
                "copilot_created": True,
            })
            return items
        internal_mutations["treo"] = (mut_treo, [])
    elif intent == "PROPOSE_TASK_COMPLETE":
        # Cùng key/schema với route web PATCH /api/v1/viec-treo/{treo_id}.
        treo_id = str(diff.get("treo_id") or "")
        def mut_treo_done(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            for it in items:
                if isinstance(it, dict) and it.get("id") == treo_id:
                    it["trang_thai"] = "xong"
                    it["xong_luc"] = now_iso
                    it["xong_boi"] = user["user_id"]
            return items
        internal_mutations["treo"] = (mut_treo_done, [])
    elif intent == "PROPOSE_CONSUMPTION_RECORD":
        # Cùng key/schema với route web POST /api/v1/tieu-thu.
        def mut_tieu_thu(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            rows.append({
                "id": f"tt_{uuid.uuid4().hex[:8]}",
                "hang": str(diff.get("hang") or ""),
                "so_luong": float(diff.get("so_luong") or 0),
                "don_vi": str(diff.get("don_vi") or "khay"),
                "duoi_nguong": float(diff.get("so_luong") or 0) < 2,
                "ai": user["user_id"],
                "luc": now_iso,
                "copilot_created": True,
            })
            return rows
        internal_mutations["tieu_thu"] = (mut_tieu_thu, [])
    elif intent == "PROPOSE_MENU_UPDATE":
        # Cùng bảng menu_mon với route web /menu (PR11 admin).
        hanh_dong = str(diff.get("hanh_dong") or "")
        ten_mon = str(diff.get("ten_mon") or "")
        if hanh_dong == "them":
            def mut_menu_them(mons: dict[str, Any]) -> dict[str, Any]:
                # menu_mon là bảng domain, không phải KV — ghi qua KV mirror
                # "menu_copilot_pending" để route web áp dụng sau khi duyệt.
                pending = list(mons.get("them") or [])
                pending.append({
                    "id": f"mon_{uuid.uuid4().hex[:8]}",
                    "ten": ten_mon,
                    "gia": int(diff.get("gia") or 0),
                    "an": False,
                    "created_at": now_iso,
                })
                mons["them"] = pending
                return mons
            internal_mutations["menu_copilot_pending"] = (mut_menu_them, {})
        else:
            mon_id = str(diff.get("mon_id") or "")
            def mut_menu_sua(mons: dict[str, Any]) -> dict[str, Any]:
                updates = list(mons.get("sua") or [])
                updates.append({
                    "mon_id": mon_id,
                    "hanh_dong": hanh_dong,
                    "gia": diff.get("gia"),
                    "an": diff.get("an"),
                    "created_at": now_iso,
                })
                mons["sua"] = updates
                return mons
            internal_mutations["menu_copilot_pending"] = (mut_menu_sua, {})
    elif intent == "PROPOSE_PIN":
        # Cùng KV "pins" (key "ca_id|nv_id") với route web pin lịch.
        ca_id = str(diff.get("ca_id") or "")
        nv_pin = str(diff.get("nv_id") or "")
        pinned = bool(diff.get("pinned"))
        def mut_pins(pins: dict[str, Any]) -> dict[str, Any]:
            pins[f"{ca_id}|{nv_pin}"] = pinned
            return pins
        internal_mutations["pins"] = (mut_pins, {})
    elif intent == "PROPOSE_TKB_CONFIRM":
        # Cùng key/schema với route web POST /api/v1/tkb/confirm (sprint3.py):
        # tkb_nv_by_week[tuan_iso][nv] = {khoang_ban, source_id, ...}.
        nv_tkb = str(diff.get("nv_id") or user["user_id"])
        tuan_iso = str(diff.get("tuan_iso") or "").strip()
        if not tuan_iso:
            raise RuntimeError("thieu_tuan_iso")
        khoang = [
            {"thu": str(k.get("thu") or ""), "start": str(k.get("start") or ""), "end": str(k.get("end") or "")}
            for k in (diff.get("khoang_ban") or []) if isinstance(k, dict)
        ]
        if not khoang:
            raise RuntimeError("khoang_rong")
        # Ownership gate giống route web: non-manager chỉ xác nhận TKB của mình.
        if user["role"] not in {"quan_ly", "chu_quan"} and nv_tkb != user["user_id"]:
            raise RuntimeError("chi_gan_tkb_cua_minh")

        def mut_tkb_by_week(tkb_by_week: dict[str, Any]) -> dict[str, Any]:
            week_doc = tkb_by_week.setdefault(tuan_iso, {})
            if not isinstance(week_doc, dict):
                week_doc = {}
                tkb_by_week[tuan_iso] = week_doc
            week_doc[nv_tkb] = {
                "tuan_iso": tuan_iso,
                "khoang_ban": khoang,
                "source_id": str(diff.get("source_id") or "copilot"),
                "upload_id": str(diff.get("upload_id") or ""),
                "xac_nhan_boi": user["user_id"],
                "vai": user["role"],
            }
            return tkb_by_week

        internal_mutations["tkb_nv_by_week"] = (mut_tkb_by_week, {})
        # Ghi nhận lần sửa giống route web (record_sua loai="tkb_xac_nhan").
        try:
            from ca_playbook.sua import record_sua

            record_sua(
                loai="tkb_xac_nhan",
                truoc={},
                sau={"nv_id": nv_tkb, "tuan_iso": tuan_iso, "khoang_ban": khoang},
                ai=user["user_id"],
                now_iso=now_iso,
            )
        except Exception:
            pass  # Playbook file có thể read-only (Docker) — KV vẫn là nguồn thật.
    elif intent == "PROPOSE_SWAP_CONSENT":
        # Mirror route web POST /api/v1/cho-doi-ca/{swap_id}/dong-y (sprint45.py):
        # chỉ append nv của người duyệt; trang_thai "dong_y" khi {a, b} đều đồng ý.
        swap_id = str(diff.get("swap_id") or "")
        nv_dong_y = str(diff.get("nv_id") or user["user_id"])

        def mut_swap_consent(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            target = next(
                (s for s in items if isinstance(s, dict) and (
                    str(s.get("id") or "") == swap_id or str(s.get("swap_id") or "") == swap_id
                )),
                None,
            )
            if not target:
                raise RuntimeError("swap_khong_tim_thay")
            parties = {
                str(target.get("a") or ""),
                str(target.get("b") or ""),
                str(target.get("c") or ""),
            } - {""}
            if nv_dong_y not in parties and user["role"] not in {"quan_ly", "chu_quan"}:
                raise RuntimeError("khong_phai_nguoi_tham_gia")
            agreed = set(target.get("dong_y") or [])
            agreed.add(nv_dong_y)
            target["dong_y"] = sorted(agreed)
            if {str(target.get("a") or ""), str(target.get("b") or "")} <= agreed:
                target["trang_thai"] = "dong_y"
            return items

        internal_mutations["swap"] = (mut_swap_consent, [])
    elif intent == "PROPOSE_HANDOVER":
        # Mirror route web POST /api/v1/handover (sprint45.py): trích SBAR qua
        # ag_handover (chỉ API layer được import cross-agent) + append history.
        ho_text = str(diff.get("text") or "")
        if not ho_text.strip():
            raise RuntimeError("missing_handover_text")
        from ca_agents.ag_handover import extract as extract_handover

        h = extract_handover(ho_text)
        ho_fields = h.__dict__
        try:
            from ca_gates.vf_num import validate_num

            nums = validate_num(ho_text, {"2", "3", "8", "15"})
            ho_fields["vf_num"] = nums.__dict__
        except Exception:
            pass  # VF số chỉ là kiểm định thêm — không chặn bàn giao.
        ho_entry = {
            "id": f"ho_{uuid.uuid4().hex[:8]}",
            "luc": now_iso,
            "ai": user["user_id"],
            **ho_fields,
        }

        def mut_handover(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            rows.append(ho_entry)
            return rows[-50:]

        internal_mutations["handover_history"] = (mut_handover, [])
    elif intent == "PROPOSE_PAGE_SYNC":
        # Cùng logic Graph fetch với route /api/v1/page/sync (PR12). Nếu Graph
        # lỗi, action rơi vào execution_failed với reason — không side effect.
        from ca_agents.facebook_page import fetch_conversations

        try:
            threads = fetch_conversations(limit=20)
        except RuntimeError as exc:
            raise RuntimeError(f"page_sync_failed:{str(exc)[:120]}") from exc

        def mut_page(doc: dict[str, Any]) -> dict[str, Any]:
            by_id = {t.get("id"): t for t in doc.get("threads", []) if t.get("id")}
            for th in threads:
                by_id[th["id"]] = th
            doc["threads"] = list(by_id.values())
            doc["mode"] = "live"
            return doc

        kv_mutate("page_quan", mut_page, {})
        diff["so_hoi_thoai"] = len(threads)
    elif intent == "PROPOSE_PAGE_DRAFT":
        noi_dung = str(diff.get("noi_dung") or "")
        topic = str(diff.get("topic") or "")
        tone = str(diff.get("tone") or "than thien")
        from ca_api.interfaces.http.channels import _now, _page_mode
        draft_item: dict[str, Any] = {
            "id": f"pd_{uuid.uuid4().hex[:8]}",
            "noi_dung": noi_dung,
            "trang_thai": "da_dang" if _page_mode() == "live" else "da_dang_mock",
            "by": f"AI Copilot ({user['role']})",
            "nguoi_tao": f"{user['user_id']} ({user['role']})",
            "at": _now(),
            "ngay_tao": _now(),
            "topic": topic,
            "tone": tone,
        }
        graph_post_id: str | None = None
        if _page_mode() == "live":
            from ca_agents.facebook_page import publish_page_post
            try:
                pub = publish_page_post(noi_dung)
                graph_post_id = str(pub.get("id") or "") or None
                draft_item["graph_post_id"] = graph_post_id
            except Exception as exc:
                raise RuntimeError(f"facebook_publish_failed:{str(exc)[:120]}") from exc

        def mut_page(doc: dict[str, Any]) -> dict[str, Any]:
            doc.setdefault("drafts", []).insert(0, draft_item)
            return doc

        kv_mutate("page_quan", mut_page, {})
        diff["draft_id"] = draft_item["id"]
        diff["graph_post_id"] = graph_post_id
        diff["trang_thai"] = draft_item["trang_thai"]
    elif intent == "SEND_MAIL":
        to_emails = diff.get("to_emails") or []
        subject = diff.get("subject") or ""
        body_text = diff.get("body") or ""
        from ca_api.interfaces.http.mail import execute_supervised_mail

        mail_result = execute_supervised_mail(
            store_id=user["store_id"], actor_user_id=user["user_id"], actor_role=user["role"],
            to_emails=to_emails, subject=subject, body=body_text,
            html_body=diff.get("html_body"), attachments=diff.get("attachments"),
            original_subject=str(draft["payload_diff"].get("subject") or subject),
            original_body=orig_body, ops_context=diff.get("ops_context"),
            prompt_version="copilot-mail-v1", rule_version=str(diff.get("rule_version") or "none"),
            rollout_bucket=str(diff.get("rollout_bucket") or "control"),
            idempotency_key=body.idempotency_key,
        )
        diff["mail_result"] = mail_result
        if not mail_result.get("ok"):
            raise RuntimeError(f"mail_delivery_failed:{mail_result.get('reason') or 'unknown'}")
    elif intent == "RUN_CATCHMENT_SURVEY":
        # 1. Server-side role check (defense-in-depth): chỉ quan_ly/chu_quan
        if user["role"] not in {"quan_ly", "chu_quan"}:
            raise HTTPException(status_code=403, detail="forbidden: survey requires manager role")

        # 2. Tạo SurveyJob qua SurveyOrchestrator
        from ca_agents.ag_pricing.job_manager import get_job_store
        from ca_agents.ag_pricing.orchestrator_v2 import SurveyOrchestrator
        from ca_contracts.catchment_survey_v2 import (
            CatchmentSurveyRequest,
            ChannelMode,
            RadiusProfile,
        )

        cat_kw = str(diff.get("category_keyword") or "cà phê")
        radius_val = float(diff.get("radius_km") or 3.0)
        mode_val = str(diff.get("channel_mode") or "hybrid")

        req_v2 = CatchmentSurveyRequest(
            latitude=10.7769,
            longitude=106.7009,
            core_category=cat_kw,
            channel_mode=ChannelMode(mode_val) if mode_val in [m.value for m in ChannelMode] else ChannelMode.HYBRID,
            radius_profile=RadiusProfile(
                dine_in_km=min(3.0, radius_val),
                delivery_km=min(10.0, radius_val),
            ),
            idempotency_key=body.idempotency_key,
        )

        orch = SurveyOrchestrator(job_store=get_job_store())
        job = orch.create_job(req_v2)
        job.meta["store_id"] = user["store_id"]

        background_tasks.add_task(orch.execute_job, job.job_id)

        diff["job_id"] = job.job_id
        diff["status"] = job.status.value
        diff["link"] = f"/khao-sat-gia?job_id={job.job_id}"

    _RESULT_LINK: dict[str, str] = {
        "SCHEDULE_SOLVE": "/roster",
        "APPROVE_SHIFT_SWAP": "/doi-ca",
        "CREATE_RULE_PROPOSAL": "/cam-nang",
        "INVENTORY_RESTOCK_CHECK": "/tieu-thu",
        "GENERATE_DAILY_BRIEF": "/hom-nay",
        "QUERY_SOP": "/sop",
        "ANALYZE_WASTE": "/hao-phi",
        "SEND_MAIL": "/vet",
        # PR10 còn lại (R2_CONFIRM)
        "PROPOSE_TKB_CONFIRM": "/inbox",
        "PROPOSE_SWAP_CONSENT": "/doi-ca",
        "PROPOSE_HANDOVER": "/handover",
        "PROPOSE_TIME_OFF": "/inbox",
        "PROPOSE_HANGING_TASK": "/treo",
        "PROPOSE_PAGE_SYNC": "/page-quan",
        "PROPOSE_PAGE_DRAFT": "/page-quan",
        "RUN_CATCHMENT_SURVEY": "/khao-sat-gia",
        "QUERY_AUDIT": "/vet",
    }
    outcome = {
        "ok": True,
        "action_id": body.action_id,
        "status": "executed",
        "message": "Đã phê duyệt và thực thi hành động thành công!",
        "result_link": _RESULT_LINK.get(intent),
        "payload_diff": diff,
    }
    if intent == "PROPOSE_ORDER_TRANSITION":
        # Đơn quầy là bảng domain (không phải KV) — ghi cùng bảng don_quay mà
        # route web /quay đang đọc, giữ nguyên state machine; lỗi ghi sẽ đánh
        # dấu action thất bại (không partial commit vì đây là write duy nhất).
        from ca_api.persist import don_get, don_update

        don = don_get(str(diff.get("don_id") or ""))
        if not don:
            raise RuntimeError("don_not_found")
        prev_status = str(don.get("trang_thai") or "")
        don["trang_thai"] = str(diff.get("trang_thai") or "")
        if don["trang_thai"] == "huy":
            don["ly_do_huy"] = str(diff.get("ly_do_huy") or "")
        don_update(don)
        diff["trang_thai_truoc"] = prev_status
    if internal_mutations:
        copilot_commit_internal_execution(
            store_id=user["store_id"], action_id=body.action_id,
            idempotency_key=body.idempotency_key, intent=draft["intent"],
            actor_user_id=user["user_id"], payload_diff=diff, outcome=outcome,
            kv_mutations=internal_mutations, channel="web",
            latency_ms=int((time.time() - t0) * 1000),
        )
    else:
        copilot_draft_update_status(body.action_id, "executed", executed_at=now_iso)
        copilot_audit_add(
            action_id=body.action_id, actor_user_id=user["user_id"],
            store_id=user["store_id"], intent=draft["intent"], decision="approve",
            payload_diff=diff, channel="web",
            latency_ms=int((time.time() - t0) * 1000),
            agent_name="ag_copilot",
            controller_user_id=user["user_id"],
        )
        copilot_execution_complete(
            user["store_id"], body.action_id, body.idempotency_key, outcome,
        )
    return outcome


# ── 3. POST /api/v1/copilot/action/{action_id}/amend ─────────────────────────

@router.post("/action/{action_id}/amend")
def copilot_amend_action(
    action_id: str,
    body: AmendActionBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Amend / Correct an already executed action within the amendment time window (15 mins)."""
    t0 = time.time()
    user = _require_user(authorization)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    draft = copilot_draft_get(action_id)
    if not draft:
        raise HTTPException(status_code=404, detail="action_not_found")

    scope_res = validate_scope(
        caller_store_id=user["store_id"], target_store_id=draft["store_id"],
        caller_role=user["role"], intent=draft["intent"],
        action_created_by=draft["created_by"], caller_user_id=user["user_id"],
    )
    if not scope_res.passed:
        raise HTTPException(status_code=404, detail="action_not_found")

    if draft["status"] != "executed":
        raise HTTPException(status_code=400, detail="only_executed_actions_can_be_amended")

    if draft["intent"] != "SEND_MAIL":
        raise HTTPException(status_code=422, detail="amendment_not_supported_for_intent")

    # Check 15-minute amendment window
    if draft["executed_at"]:
        try:
            exec_dt = datetime.fromisoformat(draft["executed_at"].replace("Z", "+00:00"))
            if (datetime.now(UTC) - exec_dt).total_seconds() > 900:  # 15 mins
                raise HTTPException(status_code=400, detail="amendment_window_expired")
        except HTTPException:
            raise
        except Exception:
            pass

    correction_diff = _validate_correction_diff(draft["intent"], body.correction_diff)
    amended_payload = dict(draft.get("payload_diff") or {})
    amended_payload.update(correction_diff)
    expires_at = (datetime.now(UTC) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_action_id = f"amend_{uuid.uuid4().hex[:8]}"
    new_draft = {
        "action_id": new_action_id,
        "intent": draft["intent"],
        "status": "amendment_ready",
        "store_id": draft["store_id"],
        "created_by": user["user_id"],
        "confidence": 1.0,
        "summary": f"Đính chính cho hành động {action_id}: {body.reason}",
        "explanation": f"Yêu cầu đính chính từ {user['username']}: {body.reason}",
        "payload_diff": amended_payload,
        "requires_confirmation": True,
        "data_snapshot_hash": compute_snapshot_hash(
            build_live_snapshot("SEND_MAIL", draft["store_id"], amended_payload)
        ),
        "expires_at": expires_at,
        "created_at": now_iso,
        "executed_at": None,
        "amended_from": action_id,
        "amended_by": user["user_id"],
    }
    copilot_draft_save(new_draft)

    # Log audit
    copilot_audit_add(
        action_id=new_action_id,
        actor_user_id=user["user_id"],
        store_id=user["store_id"],
        intent=draft["intent"],
        decision="amend_proposed",
        payload_diff={"amended_from": action_id, "reason": body.reason, "diff": correction_diff},
        channel="web",
        latency_ms=int((time.time() - t0) * 1000),
        agent_name="ag_copilot",
        controller_user_id=user["user_id"],
    )

    return {
        "ok": True,
        "new_action_id": new_action_id,
        "amended_from": action_id,
        "status": "amendment_ready",
        "message": f"Đã tạo đề xuất đính chính cho hành động {action_id}; cần duyệt lại.",
    }


# ── 4. GET /api/v1/copilot/action/{action_id} ────────────────────────────────

@router.get("/action/{action_id}")
def copilot_get_action(
    action_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Get ActionProposal details within the authenticated tenant scope."""
    user = _require_user(authorization)
    draft = copilot_draft_get(action_id)
    if not draft:
        raise HTTPException(status_code=404, detail="action_not_found")
    scope_res = validate_scope(
        caller_store_id=user["store_id"], target_store_id=draft["store_id"],
        caller_role=user["role"], intent=draft["intent"],
        action_created_by=draft["created_by"], caller_user_id=user["user_id"],
    )
    if not scope_res.passed:
        raise HTTPException(status_code=404, detail="action_not_found")
    return draft


# ── 5. GET /api/v1/copilot/audit ─────────────────────────────────────────────

@router.get("/audit")
def copilot_get_audit(
    store_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    """Get audit log for the authenticated manager/owner tenant only."""
    user = _require_user(authorization)
    if user["role"] not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="insufficient_role:audit_manager_only")
    # Query parameters never override the tenant carried by the session.
    return copilot_audit_list(user["store_id"], limit=limit)


# ── 6. GET /api/v1/copilot/permissions ───────────────────────────────────────

@router.get("/permissions")
def copilot_get_permissions(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Minh bạch quyền: role hiện tại được (và không được) dùng intent nào."""
    user = _get_verified_user(authorization)
    role = user["role"]
    allowed = sorted(copilot_intents_allowed_for_role(role))
    all_intents = sorted(
        str(i.value) if hasattr(i, "value") else str(i)
        for i in CopilotIntent
        if i != CopilotIntent.OUT_OF_SCOPE
    )
    return {
        "role": role,
        "allowed_intents": allowed,
        "denied_intents": sorted(set(all_intents) - set(allowed)),
        "matrix": {
            r: sorted(v) for r, v in COPILOT_ROLE_INTENT_MATRIX.items()
        },
    }


# ── 7. GET /api/v1/copilot/capabilities ─────────────────────────────────────

@router.get("/capabilities")
def copilot_get_capabilities(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Catalog capability theo role (PR9): UI/agent chỉ quảng bá chức năng
    user thật sự có quyền. R4_MANUAL_ONLY không bao giờ được thực thi qua chat —
    chỉ trả deep-link để người có quyền thao tác trực tiếp."""
    user = _require_user(authorization)
    caps = capabilities_for_role(user["role"])
    return {
        "role": user["role"],
        "store_id": user["store_id"],
        "capabilities": [
            {
                "intent": c.intent,
                "label": c.label,
                "domain": c.domain,
                "risk_tier": c.risk_tier,
                "deep_link": c.deep_link,
                "manual_only_reason": c.manual_only_reason,
            }
            for c in caps
        ],
    }


# ── 8. POST /api/v1/copilot/navigate ────────────────────────────────────────

class NavigateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=100)


@router.post("/navigate")
def copilot_navigate(
    body: NavigateBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """NAVIGATE_TO_FEATURE: trả deep-link hợp lệ từ registry (không tự xây URL).

    Fail-closed: target không có trong registry -> 404, không trả URL tùy ý.
    R4_MANUAL_ONLY vẫn trả deep-link kèm lý do vì sao agent không tự làm.
    """
    user = _require_user(authorization)
    raw = body.target.strip()
    upper = raw.upper()
    # 1. Match theo capability intent (GET_SCHEDULE, PAYMENT, ...).
    chosen = next(
        (c for c in CAPABILITY_REGISTRY if c.intent.upper() == upper), None
    )
    # 2. Match theo path web (/menu -> capability có deep_link đó).
    if chosen is None:
        chosen = next(
            (c for c in CAPABILITY_REGISTRY if c.deep_link and c.deep_link == raw),
            None,
        )
    if chosen is None:
        raise HTTPException(status_code=404, detail="navigate_target_not_found")
    # R4_MANUAL_ONLY vẫn được navigate: chỉ trả deep-link + lý do, không thực thi.
    # Các tier khác kiểm tra bằng catalog theo role (fail-closed).
    if chosen.risk_tier != "R4_MANUAL_ONLY":
        allowed = any(
            c.intent == chosen.intent
            for c in capabilities_for_role(user["role"])
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="navigate_insufficient_role")
    return {
        "ok": True,
        "intent": chosen.intent,
        "label": chosen.label,
        "deep_link": chosen.deep_link,
        "risk_tier": chosen.risk_tier,
        "manual_only_reason": chosen.manual_only_reason,
        "message": (
            f"Đây là thao tác agent không thể tự thực hiện ({chosen.manual_only_reason}). "
            f"Anh/chị thao tác trực tiếp tại {chosen.deep_link} nhé!"
            if chosen.manual_only_reason
            else f"Mở màn hình {chosen.label} tại {chosen.deep_link}."
        ),
    }
