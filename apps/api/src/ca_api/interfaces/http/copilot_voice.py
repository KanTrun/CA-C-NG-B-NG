"""Authenticated server-to-server WebSocket proxy for AG-COPILOT voice."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ca_agents.ag_copilot import run_copilot
from ca_agents.ag_copilot.voice_session import (
    GeminiLiveSession,
    VerifiedVoiceContext,
    VoiceSessionUnavailable,
)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ca_api.context_providers import ngay_hom_nay_vn
from ca_api.persist import (
    audit_add,
    copilot_audit_add,
    copilot_draft_save,
)
from ca_api.persist import session as auth_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["copilot-voice"])

AUTH_TIMEOUT_SECONDS = 5.0
VOICE_IDLE_TIMEOUT_SECONDS = float(os.environ.get("VOICE_IDLE_TIMEOUT_SECONDS", "60.0"))
VOICE_SESSION_MAX_SECONDS = float(os.environ.get("VOICE_SESSION_MAX_SECONDS", "300.0"))
MAX_TEXT_LENGTH = 2000
MAX_AUDIO_CHUNK_BYTES = 65536  # 64 KB per PCM chunk
MAX_MESSAGES_PER_SECOND = 25.0

@dataclass
class _ActiveVoiceSession:
    websocket: WebSocket
    stop_event: asyncio.Event
    loop: asyncio.AbstractEventLoop

_ACTIVE_VOICE_SESSIONS: dict[str, _ActiveVoiceSession] = {}
_ACTIVE_SESSIONS_LOCK = threading.Lock()



class TokenBucket:
    """Token-bucket rate limiter per WebSocket connection."""

    def __init__(self, rate: float = 25.0, capacity: float = 40.0) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class ActivityTracker:
    """Track last user audio/text activity for idle timeout watchdog."""

    def __init__(self) -> None:
        self.last_activity = time.monotonic()

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity


def _verified_context(token: str) -> VerifiedVoiceContext | None:
    session = auth_session(f"Bearer {token}") or auth_session(token)
    if not session:
        return None
    user_id = str(session.get("nv_id") or "").strip()
    role = str(session.get("role") or "")
    if not user_id or role not in {"chu_quan", "quan_ly", "nhan_vien"}:
        return None
    return VerifiedVoiceContext(
        user_id=user_id,
        user_role=role,
        store_id=str(session.get("store_id") or "quan_01"),
    )


async def _authenticate(websocket: WebSocket) -> VerifiedVoiceContext | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        message = json.loads(raw)
    except (TimeoutError, WebSocketDisconnect, json.JSONDecodeError, RuntimeError, Exception):
        return None
    if not isinstance(message, dict):
        return None
    if message.get("event") != "auth" or not message.get("token"):
        return None
    return _verified_context(str(message["token"]).strip())


async def _receive_client(
    websocket: WebSocket,
    live: GeminiLiveSession,
    tracker: ActivityTracker,
    limiter: TokenBucket,
) -> None:
    consecutive_oversize = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return

        if not limiter.allow():
            continue

        audio = message.get("bytes")
        if audio is not None:
            if audio:
                if len(audio) > MAX_AUDIO_CHUNK_BYTES:
                    consecutive_oversize += 1
                    if consecutive_oversize >= 3:
                        await websocket.close(code=4003, reason="rate_limited")
                        return
                    continue
                consecutive_oversize = 0
                tracker.touch()
                await live.send_audio(audio)
            continue

        raw = message.get("text")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        event = payload.get("event")
        if event == "stop":
            return
        if event == "text":
            text = str(payload.get("text") or "").strip()
            if text:
                tracker.touch()
                await live.send_text(text[:MAX_TEXT_LENGTH])
        elif event == "interrupt":
            tracker.touch()
            await websocket.send_json({"event": "voice:interrupted"})
        elif event == "activity_start":
            tracker.touch()
            await live.send_activity_start()
        elif event == "activity_end":
            tracker.touch()
            await live.send_activity_end()


_PIPELINE_TOOL_NAME = "run_copilot_pipeline"


def _as_dict(value: Any) -> dict[str, Any]:
    """Ép về dict — upstream có thể gửi sai kiểu (str/list/None).

    Đây là dữ liệu từ mạng: gọi `.get()` thẳng lên giá trị sai kiểu sẽ ném
    `AttributeError` và giết luôn phiên voice, nên mọi truy cập phải qua đây.
    """
    return value if isinstance(value, dict) else {}


def _iter_function_calls(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Gom mọi functionCall trong một server message của Gemini Live.

    Live API (`BidiGenerateContentServerMessage`) gửi yêu cầu gọi hàm ở field
    **top-level** `toolCall.functionCalls`. Bản trước chỉ đọc
    `serverContent.modelTurn.parts[].functionCall` — shape này KHÔNG tồn tại
    trong Live API — nên mọi lượt model gọi `run_copilot_pipeline` đều bị bỏ
    qua: pipeline nghiệp vụ không chạy, không có `toolResponse` trả về Gemini,
    và trợ lý đành trả lời là không truy cập được dữ liệu (voice hỏng trong khi
    chat text vẫn trả lời bình thường). Nhánh `modelTurn.parts[]` được giữ làm
    dự phòng để không vỡ nếu upstream đổi định dạng giữa các bản preview.
    """
    tool_call = _as_dict(event.get("toolCall")) or _as_dict(event.get("tool_call"))
    raw_calls = tool_call.get("functionCalls") or tool_call.get("function_calls") or []
    if not isinstance(raw_calls, list):
        raw_calls = []
    calls = [c for c in raw_calls if isinstance(c, dict)]
    if calls:
        return calls

    server_content = _as_dict(event.get("serverContent"))
    model_turn = _as_dict(server_content.get("modelTurn"))
    parts = model_turn.get("parts") or []
    if not isinstance(parts, list):
        return calls
    for part in parts:
        if not isinstance(part, dict):
            continue
        fn = part.get("functionCall") or part.get("function_call")
        if isinstance(fn, dict):
            calls.append(fn)
    return calls


def _extract_pipeline_calls(event: dict[str, Any]) -> list[tuple[str, str]]:
    """Trả [(call_id, message)] cho mọi lượt model gọi tool pipeline.

    Giữ nguyên `call_id` kể cả khi rỗng để hàm gọi tự quyết định (Live API luôn
    kèm id, nhưng thiếu id thì không thể gửi `toolResponse` hợp lệ).
    """
    result: list[tuple[str, str]] = []
    for fn in _iter_function_calls(event):
        if fn.get("name") != _PIPELINE_TOOL_NAME:
            continue
        args = _as_dict(fn.get("args"))
        message = str(args.get("message") or "").strip()
        result.append((str(fn.get("id") or "").strip(), message))
    return result


def _cancelled_call_ids(event: dict[str, Any]) -> set[str]:
    """Id các tool call đã bị server huỷ — không được trả lời nữa."""
    cancellation = _as_dict(event.get("toolCallCancellation")) or _as_dict(
        event.get("tool_call_cancellation")
    )
    ids = cancellation.get("ids")
    if not isinstance(ids, list):
        return set()
    return {str(call_id) for call_id in ids if call_id}


async def _serve_pipeline_call(
    websocket: WebSocket,
    live: GeminiLiveSession,
    context: VerifiedVoiceContext,
    call_id: str,
    message: str,
) -> None:
    """Chạy pipeline nghiệp vụ cho MỘT tool call rồi trả kết quả về Gemini + client."""
    if not call_id:
        # Live API luôn kèm id; thiếu id thì không thể gửi toolResponse hợp lệ.
        logger.warning("voice tool call thieu id; bo qua (khong the tra toolResponse)")
        return
    if not message:
        # Vẫn phải trả lời, nếu không Gemini sẽ treo lượt chờ toolResponse.
        await live.send_function_response(
            call_id,
            "Dạ em chưa nghe rõ yêu cầu. Anh/chị nói lại giúp em nhé.",
        )
        return

    try:
        # run_copilot() có thể gọi LLM (chậm) trong live mode → chạy trong
        # thread executor để không block event loop của WebSocket.
        response = await asyncio.to_thread(
            run_copilot,
            message,
            {
                "store_id": context.store_id,
                "user_id": context.user_id,
                "user_role": context.user_role,
                "active_date": ngay_hom_nay_vn(),
                "channel": "voice",
            },
        )
    except Exception:
        # Ghi log: nuốt lỗi im lặng từng khiến sự cố voice không có dấu vết nào.
        logger.exception("voice: run_copilot that bai cho call_id=%s", call_id)
        response = None

    if response is None:
        await live.send_function_response(
            call_id,
            "Dạ em gặp lỗi khi xử lý yêu cầu. Anh/chị thử lại hoặc dùng chat text nhé.",
        )
        return

    proposal = (
        response.action_proposal.model_dump()
        if response.action_proposal is not None
        else None
    )
    # Lưu draft + audit như chat thường để client bấm "Duyệt & Gửi"
    # không bị 404 action_proposal_not_found.
    if response.action_proposal is not None:
        try:
            copilot_draft_save(response.action_proposal.model_dump())
            copilot_audit_add(
                action_id=response.action_proposal.action_id,
                actor_user_id=context.user_id,
                store_id=context.store_id,
                intent=response.action_proposal.intent.value,
                decision="propose",
                payload_diff=response.action_proposal.payload_diff,
                channel="voice",
                latency_ms=0,
                agent_name="ag_copilot",
                controller_user_id=context.user_id,
            )
        except Exception:
            pass
    await live.send_function_response(call_id, response.reply_text, proposal)
    await websocket.send_json(
        {
            "event": "voice:proposal",
            "data": {
                "reply_text": response.reply_text,
                "intent": (
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                ),
                "action_proposal": proposal,
                "citations": response.citations or [],
                "agent_mode": response.agent_mode,
            },
        }
    )


async def _receive_upstream(
    websocket: WebSocket,
    live: GeminiLiveSession,
    context: VerifiedVoiceContext,
) -> None:
    cancelled: set[str] = set()
    while True:
        event = await live.receive()
        await websocket.send_json({"event": "voice:upstream", "data": event})

        cancelled |= _cancelled_call_ids(event)

        # Nối pipeline nghiệp vụ: khi Gemini gọi tool run_copilot_pipeline,
        # chạy run_copilot() (role auth + tool + ActionProposal + audit) rồi
        # trả kết quả về Gemini để đọc thành tiếng + gửi proposal về client.
        for call_id, message in _extract_pipeline_calls(event):
            if call_id and call_id in cancelled:
                continue
            await _serve_pipeline_call(websocket, live, context, call_id, message)


async def _idle_watchdog(websocket: WebSocket, tracker: ActivityTracker) -> None:
    while True:
        await asyncio.sleep(5.0)
        if tracker.idle_seconds() >= VOICE_IDLE_TIMEOUT_SECONDS:
            await websocket.close(code=4005, reason="idle_timeout")
            return


@router.websocket("/api/v1/copilot/voice")
async def copilot_voice_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    context = await _authenticate(websocket)
    if context is None:
        await websocket.close(code=4001, reason="auth_invalid")
        return

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    current_session = _ActiveVoiceSession(
        websocket=websocket, stop_event=stop_event, loop=loop
    )

    # Concurrency limit: close previous active session for this user
    with _ACTIVE_SESSIONS_LOCK:
        old_session = _ACTIVE_VOICE_SESSIONS.get(context.user_id)
        if old_session is not None and old_session.websocket is not websocket:
            def _signal_superseded(s: _ActiveVoiceSession) -> None:
                s.stop_event.set()
                asyncio.create_task(
                    s.websocket.close(code=4002, reason="session_superseded")
                )

            with suppress(Exception):
                old_session.loop.call_soon_threadsafe(_signal_superseded, old_session)
        _ACTIVE_VOICE_SESSIONS[context.user_id] = current_session

    if stop_event.is_set():
        with suppress(Exception):
            await websocket.close(code=4002, reason="session_superseded")
        return

    live = GeminiLiveSession(context)
    start_time = loop.time()
    try:
        audit_add(
            datetime.now(UTC).isoformat(),
            context.user_id,
            "copilot.voice.start",
            {"store_id": context.store_id, "role": context.user_role},
            agent_name="ag_copilot",
            controller_user_id=context.user_id,
        )
    except Exception:
        pass

    close_reason = "normal"
    tracker = ActivityTracker()
    limiter = TokenBucket(rate=MAX_MESSAGES_PER_SECOND, capacity=40.0)

    try:
        await live.open()
        if stop_event.is_set():
            close_reason = "session_superseded"
            return

        await websocket.send_json(
            {
                "event": "voice:ready",
                "data": {
                    "input_format": "pcm_s16le_16000_mono",
                    "output_format": "pcm_s16le_24000_mono",
                    "session_timeout_seconds": int(VOICE_SESSION_MAX_SECONDS),
                    "idle_timeout_seconds": int(VOICE_IDLE_TIMEOUT_SECONDS),
                },
            }
        )
        async with asyncio.timeout(VOICE_SESSION_MAX_SECONDS):
            client_task = asyncio.create_task(
                _receive_client(websocket, live, tracker, limiter)
            )
            upstream_task = asyncio.create_task(
                _receive_upstream(websocket, live, context)
            )
            watchdog_task = asyncio.create_task(_idle_watchdog(websocket, tracker))
            stop_task = asyncio.create_task(stop_event.wait())
            tasks = {client_task, upstream_task, watchdog_task, stop_task}
            try:
                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if not task.cancelled():
                        task.result()
                if stop_event.is_set():
                    close_reason = "session_superseded"
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except VoiceSessionUnavailable as exc:
        close_reason = str(exc)
        await websocket.send_json(
            {
                "event": "voice:error",
                "data": {"code": str(exc), "fallback": "text_chat"},
            }
        )
    except TimeoutError:
        close_reason = "max_duration_reached"
        with suppress(Exception):
            await websocket.send_json(
                {
                    "event": "voice:ended",
                    "data": {"code": "max_duration_reached", "fallback": "text_chat"},
                }
            )
    except (WebSocketDisconnect, json.JSONDecodeError):
        close_reason = "client_disconnected"
    except (asyncio.CancelledError, GeneratorExit):
        close_reason = "session_superseded" if stop_event.is_set() else "cancelled"
    except Exception as exc:
        close_reason = f"upstream_error: {type(exc).__name__}"
        with suppress(Exception):
            await websocket.send_json(
                {
                    "event": "voice:error",
                    "data": {"code": "upstream_unavailable", "fallback": "text_chat"},
                }
            )
    finally:
        duration = loop.time() - start_time
        try:
            audit_add(
                datetime.now(UTC).isoformat(),
                context.user_id,
                "copilot.voice.end",
                {
                    "store_id": context.store_id,
                    "role": context.user_role,
                    "duration_seconds": round(duration, 2),
                    "reason": close_reason,
                },
                agent_name="ag_copilot",
                controller_user_id=context.user_id,
            )
        except Exception:
            pass

        with _ACTIVE_SESSIONS_LOCK:
            if _ACTIVE_VOICE_SESSIONS.get(context.user_id) is current_session:
                _ACTIVE_VOICE_SESSIONS.pop(context.user_id, None)

        await live.close()
        if close_reason == "session_superseded":
            with suppress(Exception):
                await websocket.close(code=4002, reason="session_superseded")
        else:
            with suppress(Exception):
                await websocket.close(code=1000)

