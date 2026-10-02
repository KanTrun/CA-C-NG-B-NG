"""Gemini Live voice session transport for AG-COPILOT."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

GEMINI_LIVE_MODEL = "gemini-3.8-live-extended-thinking"
GEMINI_LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)
SETUP_TIMEOUT_SECONDS = 10.0


class VoiceSessionUnavailable(RuntimeError):
    """Raised when voice cannot start without violating fail-closed policy."""


class LiveConnection(Protocol):
    async def send(self, message: str | bytes) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


Connector = Callable[[str], Awaitable[LiveConnection]]


@dataclass
class VoiceTurnState:
    """Trạng thái lượt trong phiên voice (mutable, để nhét vào context frozen).

    Cần cho multi-turn xin nghỉ: copilot hỏi "lý do xin nghỉ là gì ạ?" rồi NV
    trả lời ở lượt sau. Không giữ `user_turns`/`last_reply` thì lượt trả lời
    không match intent nào và lý do bị bỏ rơi.
    """

    user_turns: list[str] = field(default_factory=list)
    last_reply: str = ""


@dataclass(frozen=True)
class VerifiedVoiceContext:
    user_id: str
    user_role: str
    store_id: str
    turn_state: VoiceTurnState = field(default_factory=VoiceTurnState)


def voice_enabled() -> bool:
    return os.environ.get("GEMINI_LIVE_VOICE_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def build_setup_message(context: VerifiedVoiceContext) -> str:
    """Build the immutable setup frame without exposing identity to the client."""
    system_instruction = (
        "Bạn là AG-COPILOT của NHỊP QUÁN. Chỉ hỗ trợ hỏi đáp, tra cứu và tạo "
        "ActionProposal qua pipeline nghiệp vụ; không tự thực thi mutation. "
        f"Người dùng đã xác thực: {context.user_id}; vai trò: {context.user_role}; "
        f"cơ sở: {context.store_id}. Trả lời tiếng Việt ngắn gọn, rõ ràng. "
        "Khi người dùng yêu cầu tra cứu dữ liệu, xếp lịch, duyệt đổi ca, báo cáo "
        "hao hụt, quy trình SOP, kiểm kê tồn kho, gửi thư, khảo sát vùng — hãy gọi "
        "tool run_copilot_pipeline với toàn bộ câu hỏi của người dùng. Không tự bịa "
        "dữ liệu; mọi kết quả phải qua pipeline nghiệp vụ."
    )
    return json.dumps(
        {
            "setup": {
                "model": f"models/{GEMINI_LIVE_MODEL}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    # Model gemini-3.8-live-extended-thinking bắt buộc khai báo
                    # thinkingConfig.thinkingLevel, nếu không WebSocket đóng với
                    # lỗi "Thinking level must be specified for this model".
                    "thinkingConfig": {"thinkingLevel": "LOW"},
                },
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "tools": [
                    {
                        "functionDeclarations": [
                            {
                                "name": "run_copilot_pipeline",
                                "description": (
                                    "Chạy pipeline nghiệp vụ AG-COPILOT: nhận diện intent, "
                                    "kiểm tra quyền theo vai trò, tra cứu dữ liệu thật qua "
                                    "tool whitelisted, tạo ActionProposal (two-phase approval). "
                                    "Trả về câu trả lời tiếng Việt + đề xuất (nếu có)."
                                ),
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "Toàn bộ câu hỏi/yêu cầu của người dùng.",
                                        }
                                    },
                                    "required": ["message"],
                                },
                            }
                        ]
                    }
                ],
                "realtimeInputConfig": {
                    "automaticActivityDetection": {
                        "startOfSpeechSensitivity": "START_SENSITIVITY_LOW",
                        "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                        "prefixPaddingMs": 300,
                        "silenceDurationMs": 800,
                    }
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
            }
        },
        ensure_ascii=False,
    )


async def _default_connector(url: str) -> LiveConnection:
    try:
        from websockets.asyncio.client import connect
    except ImportError as exc:
        raise VoiceSessionUnavailable("gemini_live_transport_unavailable") from exc
    return await connect(url, max_size=4 * 1024 * 1024)


class GeminiLiveSession:
    """One authenticated server-to-server Gemini Live connection."""

    def __init__(
        self,
        context: VerifiedVoiceContext,
        *,
        connector: Connector | None = None,
    ) -> None:
        self.context = context
        self._connector = connector or _default_connector
        self._connection: LiveConnection | None = None

    async def open(self) -> None:
        if os.environ.get("CA_AGENT_MODE", "replay").strip().lower() != "live":
            raise VoiceSessionUnavailable("gemini_live_disabled_in_replay")
        if not voice_enabled():
            raise VoiceSessionUnavailable("gemini_live_voice_disabled")
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise VoiceSessionUnavailable("gemini_live_api_key_missing")

        self._connection = await self._connector(f"{GEMINI_LIVE_ENDPOINT}?key={api_key}")
        await self._connection.send(build_setup_message(self.context))
        try:
            message = await asyncio.wait_for(
                self._connection.recv(), timeout=SETUP_TIMEOUT_SECONDS
            )
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            setup_response = json.loads(message)
        except (TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            await self.close()
            raise VoiceSessionUnavailable("gemini_live_setup_failed") from exc
        if not isinstance(setup_response, dict) or "setupComplete" not in setup_response:
            await self.close()
            raise VoiceSessionUnavailable("gemini_live_setup_failed")

    async def send_audio(self, pcm16_16khz: bytes) -> None:
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")

        await self._connection.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "audio": {
                            "mimeType": "audio/pcm;rate=16000",
                            "data": base64.b64encode(pcm16_16khz).decode("ascii"),
                        }
                    }
                }
            )
        )

    async def send_text(self, text: str) -> None:
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")
        await self._connection.send(
            json.dumps(
                {
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": text}]}],
                        "turnComplete": True,
                    }
                },
                ensure_ascii=False,
            )
        )

    async def send_activity_start(self) -> None:
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")
        await self._connection.send(
            json.dumps({"realtimeInput": {"activityStart": {}}})
        )

    async def send_activity_end(self) -> None:
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")
        await self._connection.send(
            json.dumps({"realtimeInput": {"activityEnd": {}}})
        )

    async def send_function_response(
        self, call_id: str, reply_text: str, proposal: dict[str, Any] | None = None
    ) -> None:
        """Return the pipeline result to Gemini Live so it can speak the reply.

        The reply_text is spoken by the model; the proposal (if any) is carried
        in the function response so the client can render an ActionProposalCard.
        """
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")
        await self._connection.send(
            json.dumps(
                {
                    "toolResponse": {
                        "functionResponses": [
                            {
                                "id": call_id,
                                "name": "run_copilot_pipeline",
                                "response": {
                                    "reply_text": reply_text,
                                    "action_proposal": proposal,
                                },
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            )
        )

    async def receive(self) -> dict[str, Any]:
        if self._connection is None:
            raise VoiceSessionUnavailable("gemini_live_session_not_open")
        message = await self._connection.recv()
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        data = json.loads(message)
        return data if isinstance(data, dict) else {"error": "invalid_upstream_event"}

    async def close(self) -> None:
        if self._connection is not None:
            connection, self._connection = self._connection, None
            await connection.close()
