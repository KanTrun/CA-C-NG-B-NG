"""WebSocket Connection Manager and PubSub Backend for enterprise chat."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from uuid import uuid4

from fastapi import WebSocket

from ca_api.persist import (
    chat_message_create,
    chat_message_delete,
    chat_message_edit,
    chat_message_react,
    chat_participants_list,
    chat_read_receipts_update,
    user_is_active,
)

logger = logging.getLogger("ca_api.chat_ws")


# ── Protocol & Backends ───────────────────────────────────────────────────────

class PubSubBackend(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        ...

    async def subscribe(
        self, channel: str, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        ...


class InMemoryPubSubBackend:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = (
            defaultdict(list)
        )

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        for cb in list(self._listeners.get(channel, [])):
            try:
                await cb(message)
            except Exception as e:
                logger.error("InMemoryPubSub dispatch error: %s", e)

    async def subscribe(
        self, channel: str, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._listeners[channel].append(callback)


class RedisPubSubBackend:
    """Redis backend — cố định lúc startup, retry vô hạn khi rớt kết nối.

    KHÔNG fallback về in-memory giữa chừng: các instance khác sẽ không nhận
    được broadcast nếu instance này tự chuyển backend, gây mất tin nhắn âm thầm.
    """

    _RETRY_DELAY_S = 2.0

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: Any = None
        self._listeners: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = (
            defaultdict(list)
        )
        self._task: asyncio.Task[None] | None = None
        self._closing = False

    async def _ensure_connected(self) -> None:
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            self._task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        """Subscribe và tự reconnect + re-subscribe khi kết nối rớt."""
        while not self._closing:
            try:
                ps = self._redis.pubsub()
                await ps.subscribe("nhipquan:chat:broadcast")
                logger.info("Redis Pub/Sub connected on %s", self._url)
                async for raw in ps.listen():
                    if raw and raw.get("type") == "message":
                        try:
                            data = json.loads(raw["data"])
                            channel = data.get("channel", "default")
                            payload = data.get("payload", {})
                            for cb in self._listeners.get(channel, []):
                                await cb(payload)
                        except Exception as e:
                            logger.error("Redis Pub/Sub message handling error: %s", e)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.critical(
                    "REDIS PUB/SUB CONNECTION DROPPED — retrying in %.0fs (no silent "
                    "fallback to in-memory): %s",
                    self._RETRY_DELAY_S,
                    exc,
                )
                await asyncio.sleep(self._RETRY_DELAY_S)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self._ensure_connected()
        packet = json.dumps({"channel": channel, "payload": message}, ensure_ascii=False)
        try:
            await self._redis.publish("nhipquan:chat:broadcast", packet)
        except Exception as exc:
            logger.critical("Failed to publish to Redis: %s", exc)
            raise

    async def subscribe(
        self, channel: str, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        await self._ensure_connected()
        self._listeners[channel].append(callback)

    async def aclose(self) -> None:
        """Đóng kết nối Redis sạch sẽ khi process shutdown."""
        self._closing = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None


# Khởi tạo backend cố định lúc startup — không fallback âm thầm giữa chừng
_REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if _REDIS_URL:
    pubsub_backend: PubSubBackend = RedisPubSubBackend(_REDIS_URL)
    logger.info("Using RedisPubSubBackend (REDIS_URL=%s)", _REDIS_URL)
else:
    pubsub_backend = InMemoryPubSubBackend()
    logger.info("Using InMemoryPubSubBackend")


# ── Sanitize & Rate Limiting ─────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")

def sanitize_text(text: str) -> str:
    """Loại bỏ thẻ HTML độc hại và escape ký tự nguy hiểm chống Stored XSS."""
    clean = _TAG_RE.sub("", text)
    return html.escape(clean).strip()


class IPAuthRateLimiter:
    """Giới hạn số lần thử auth sai theo IP: tối đa 5 lần sai trong 10 phút."""
    def __init__(self) -> None:
        self._failed: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _is_exempt(self, ip: str) -> bool:
        if os.environ.get("NHIPQUAN_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
            return True
        return False

    async def is_blocked(self, ip: str) -> bool:
        if self._is_exempt(ip):
            return False
        now = time.time()
        async with self._lock:
            attempts = [t for t in self._failed[ip] if now - t < 600]
            self._failed[ip] = attempts
            return len(attempts) >= 5

    async def record_failure(self, ip: str) -> None:
        if self._is_exempt(ip):
            return
        now = time.time()
        async with self._lock:
            self._failed[ip].append(now)

    async def clear(self, ip: str) -> None:
        async with self._lock:
            self._failed.pop(ip, None)

# Hai bề mặt auth giữ hai bí mật KHÁC nhau nên phải đếm riêng:
#   - login_ip_limiter   : đoán MẬT KHẨU qua POST /api/v1/auth/login
#   - ws_auth_ip_limiter : TOKEN phiên sai/hết hạn qua /ws/chat
# Dùng chung một bộ đếm thì chỉ cần vài token phiên hết hạn (client tự
# reconnect) là cả IP đó bị khóa luôn trang đăng nhập trong 10 phút — người
# dùng thật không vào lại được đúng lúc họ cần đăng nhập lại.
#   - register_ip_limiter: TẠO TÀI KHOẢN qua POST /api/v1/auth/register
# (Bug QA đợt 6 #37: register trước đây không giới hạn → spam tài khoản.)
login_ip_limiter = IPAuthRateLimiter()
ws_auth_ip_limiter = IPAuthRateLimiter()
register_ip_limiter = IPAuthRateLimiter()


class MessageRateLimiter:
    """Giới hạn tốc độ gửi tin nhắn theo nv_id: tối đa 30 tin/phút."""
    def __init__(self) -> None:
        self._sent: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_and_record(self, nv_id: str) -> bool:
        now = time.time()
        async with self._lock:
            history = [t for t in self._sent[nv_id] if now - t < 60]
            if len(history) >= 30:
                self._sent[nv_id] = history
                return False
            history.append(now)
            self._sent[nv_id] = history
            return True

msg_rate_limiter = MessageRateLimiter()


# ── Connection Manager ───────────────────────────────────────────────────────

class ChatConnectionManager:
    _BROADCAST_CHANNEL = "chat:broadcast"

    def __init__(self, backend: PubSubBackend) -> None:
        self._backend = backend
        # nv_id -> set of active WebSockets
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._origin = uuid4().hex
        self._subscribed = False

    async def _ensure_subscribed(self) -> None:
        """Đăng ký callback nhận broadcast từ instance khác (idempotent)."""
        if self._subscribed:
            return
        await self._backend.subscribe(self._BROADCAST_CHANNEL, self._on_remote_message)
        self._subscribed = True

    async def _on_remote_message(self, payload: dict[str, Any]) -> None:
        """Forward broadcast từ instance khác vào local sockets; bỏ echo của chính mình."""
        if payload.get("_origin") == self._origin:
            return
        text = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            all_sockets = [ws for s in self._connections.values() for ws in s]
        for ws in all_sockets:
            try:
                await ws.send_text(text)
            except Exception:
                pass

    async def connect(self, nv_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            is_first = len(self._connections[nv_id]) == 0
            self._connections[nv_id].add(websocket)

        if is_first:
            await self.broadcast_all({"event": "user:online", "data": {"nv_id": nv_id, "online": True}})

    async def disconnect(self, nv_id: str, websocket: WebSocket) -> None:
        is_last = False
        async with self._lock:
            if nv_id in self._connections:
                self._connections[nv_id].discard(websocket)
                if not self._connections[nv_id]:
                    del self._connections[nv_id]
                    is_last = True

        if is_last:
            await self.broadcast_all({"event": "user:offline", "data": {"nv_id": nv_id, "online": False}})

    async def force_disconnect(self, nv_id: str, reason: str = "account_deactivated") -> None:
        """Cắt kết nối toàn bộ socket của nv_id (dùng cho offboarding)."""
        async with self._lock:
            sockets = list(self._connections.pop(nv_id, set()))
        for ws in sockets:
            try:
                await ws.close(code=4001, reason=reason)
            except Exception:
                pass
        await self.broadcast_all({"event": "user:offline", "data": {"nv_id": nv_id, "online": False}})

    def is_online(self, nv_id: str) -> bool:
        return len(self._connections.get(nv_id, set())) > 0

    def get_online_users(self) -> list[str]:
        return [uid for uid, sockets in self._connections.items() if sockets]

    async def send_to_user(self, nv_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._connections.get(nv_id, set()))
        text = json.dumps(payload, ensure_ascii=False)
        for ws in sockets:
            try:
                await ws.send_text(text)
            except Exception:
                pass

    async def broadcast_all(self, payload: dict[str, Any]) -> None:
        """Fan-out qua PubSubBackend: local sockets + cross-instance qua Redis."""
        async with self._lock:
            all_sockets = [ws for s in self._connections.values() for ws in s]
        text = json.dumps(payload, ensure_ascii=False)
        for ws in all_sockets:
            try:
                await ws.send_text(text)
            except Exception:
                pass
        try:
            await self._ensure_subscribed()
            await self._backend.publish(
                self._BROADCAST_CHANNEL, {**payload, "_origin": self._origin}
            )
        except Exception as exc:
            logger.error("Chat Pub/Sub broadcast failed; local delivery completed: %s", exc)

    async def broadcast_to_conversation(
        self, conv_id: str, payload: dict[str, Any], exclude_socket: WebSocket | None = None
    ) -> None:
        participants = chat_participants_list(conv_id)
        # Chỉ gửi cho thành viên đang 'active'
        target_nv_ids = {p["nv_id"] for p in participants if p["status"] == "active"}

        async with self._lock:
            sockets: list[WebSocket] = []
            for nv_id in target_nv_ids:
                if nv_id in self._connections:
                    sockets.extend(self._connections[nv_id])

        text = json.dumps(payload, ensure_ascii=False)
        for ws in sockets:
            if exclude_socket is not None and ws is exclude_socket:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                pass

        # Local delivery keeps a persisted message usable when Redis is down.
        # Pub/Sub is only needed to fan the event out to other API instances.
        try:
            await self._ensure_subscribed()
            await self._backend.publish(
                self._BROADCAST_CHANNEL, {**payload, "_origin": self._origin}
            )
        except Exception as exc:
            logger.error("Chat Pub/Sub broadcast failed; local delivery completed: %s", exc)

    async def handle_client_message(
        self, sender_nv_id: str, websocket: WebSocket, raw_data: str
    ) -> None:
        # Kiểm tra trạng thái tài khoản
        if not user_is_active(sender_nv_id):
            await websocket.close(code=4001, reason="account_deactivated")
            return

        try:
            msg = json.loads(raw_data)
        except Exception:
            return

        event = msg.get("event")
        data = msg.get("data", {})

        if event == "ping":
            await websocket.send_text(json.dumps({"event": "pong"}))
            return

        if event == "message:send":
            # Rate limit
            if not await msg_rate_limiter.check_and_record(sender_nv_id):
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "data": {"code": "rate_limited", "detail": "Bạn đang gửi tin quá nhanh (tối đa 30 tin/phút)", "conversation_id": data.get("conversation_id")}
                }))
                return

            conv_id = data.get("conversation_id")
            raw_content = str(data.get("content", ""))
            content = sanitize_text(raw_content)
            msg_type = data.get("msg_type", "text")
            meta = data.get("metadata", {})
            reply_to_id = data.get("reply_to_id")

            if not conv_id or (not content and not meta.get("url")):
                return

            try:
                new_msg = chat_message_create(
                    conv_id=conv_id,
                    sender_id=sender_nv_id,
                    content=content,
                    msg_type=msg_type,
                    metadata=meta,
                    reply_to_id=reply_to_id,
                )
            except ValueError as val_err:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "data": {"detail": str(val_err), "conversation_id": conv_id},
                }))
                return

            await self.broadcast_to_conversation(conv_id, {"event": "message:new", "data": new_msg})
            return

        if event == "message:typing":
            conv_id = data.get("conversation_id")
            is_typing = bool(data.get("is_typing", True))
            if conv_id:
                await self.broadcast_to_conversation(
                    conv_id,
                    {
                        "event": "message:typing",
                        "data": {
                            "conversation_id": conv_id,
                            "nv_id": sender_nv_id,
                            "is_typing": is_typing,
                        },
                    },
                    exclude_socket=websocket,
                )
            return

        if event == "message:read":
            conv_id = data.get("conversation_id")
            message_id = data.get("message_id")
            if conv_id and message_id:
                receipts = chat_read_receipts_update(conv_id, sender_nv_id, message_id)
                await self.broadcast_to_conversation(
                    conv_id,
                    {
                        "event": "message:read",
                        "data": {
                            "conversation_id": conv_id,
                            "nv_id": sender_nv_id,
                            "message_id": message_id,
                            "receipts": receipts,
                        },
                    },
                )
            return

        if event == "message:react":
            message_id = data.get("message_id")
            conv_id = data.get("conversation_id")
            emoji = data.get("emoji") or data.get("reaction")
            if message_id and emoji and conv_id:
                updated_msg: dict[str, Any] | None = chat_message_react(message_id, sender_nv_id, emoji)
                await self.broadcast_to_conversation(
                    conv_id,
                    {"event": "message:updated", "data": updated_msg},
                )
            return

        if event == "message:edit":
            message_id = data.get("message_id")
            conv_id = data.get("conversation_id")
            raw_new = str(data.get("content", ""))
            clean_new = sanitize_text(raw_new)
            if message_id and conv_id and clean_new:
                updated_msg = chat_message_edit(message_id, sender_nv_id, clean_new)
                if updated_msg:
                    await self.broadcast_to_conversation(
                        conv_id,
                        {"event": "message:updated", "data": updated_msg},
                    )
            return

        if event == "message:delete":
            message_id = data.get("message_id")
            conv_id = data.get("conversation_id")
            if message_id and conv_id:
                deleted_msg = chat_message_delete(message_id, sender_nv_id)
                if deleted_msg:
                    await self.broadcast_to_conversation(
                        conv_id,
                        {"event": "message:updated", "data": deleted_msg},
                    )
            return


chat_ws_manager = ChatConnectionManager(pubsub_backend)


async def notify_ops_changed(
    kind: str,
    week_iso: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Fan out a persisted operational mutation to connected clients."""
    data: dict[str, Any] = {
        "event_id": uuid4().hex,
        "at": datetime.now(UTC).isoformat(),
        "kind": kind,
        "domain": kind.split(":", 1)[0],
    }
    if week_iso:
        data["week_iso"] = week_iso
    if details:
        data.update(details)
    await chat_ws_manager.broadcast_all({"event": "ops:changed", "data": data})
