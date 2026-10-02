# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from __future__ import annotations

import asyncio
import json

import pytest
from ca_agents.ag_copilot.voice_session import (
    GEMINI_LIVE_MODEL,
    GeminiLiveSession,
    VerifiedVoiceContext,
    VoiceSessionUnavailable,
    build_setup_message,
)


class FakeConnection:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.sent: list[str | bytes] = []
        self.closed = False
        self.response = response or {"setupComplete": {}}

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return json.dumps(self.response)

    async def close(self) -> None:
        self.closed = True


def _context() -> VerifiedVoiceContext:
    return VerifiedVoiceContext(
        user_id="nv_01",
        user_role="quan_ly",
        store_id="quan_01",
    )


def test_replay_mode_never_opens_network(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def connector(url: str) -> FakeConnection:
        calls.append(url)
        return FakeConnection()

    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    monkeypatch.setenv("GEMINI_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def exercise() -> None:
        with pytest.raises(VoiceSessionUnavailable, match="disabled_in_replay"):
            await GeminiLiveSession(_context(), connector=connector).open()

    asyncio.run(exercise())

    assert calls == []


def test_live_session_uses_only_extended_thinking_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    urls: list[str] = []

    async def connector(url: str) -> FakeConnection:
        urls.append(url)
        return connection

    monkeypatch.setenv("CA_AGENT_MODE", "live")
    monkeypatch.setenv("GEMINI_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def exercise() -> None:
        session = GeminiLiveSession(_context(), connector=connector)
        await session.open()

    asyncio.run(exercise())

    assert urls and "test-key" in urls[0]
    setup = json.loads(str(connection.sent[0]))
    assert setup["setup"]["model"] == f"models/{GEMINI_LIVE_MODEL}"
    assert GEMINI_LIVE_MODEL == "gemini-3.8-live-extended-thinking"
    assert "gemini-3.8-live\"" not in str(connection.sent[0])
    vad = setup["setup"]["realtimeInputConfig"]["automaticActivityDetection"]
    assert vad["startOfSpeechSensitivity"] == "START_SENSITIVITY_LOW"
    assert vad["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    assert vad["prefixPaddingMs"] == 300
    assert vad["silenceDurationMs"] == 800


def test_live_session_rejects_missing_setup_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection({"serverContent": {"turnComplete": True}})

    async def connector(_url: str) -> FakeConnection:
        return connection

    monkeypatch.setenv("CA_AGENT_MODE", "live")
    monkeypatch.setenv("GEMINI_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def exercise() -> None:
        with pytest.raises(VoiceSessionUnavailable, match="setup_failed"):
            await GeminiLiveSession(_context(), connector=connector).open()

    asyncio.run(exercise())

    assert connection.closed is True


def test_live_session_forwards_audio_text_and_upstream_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()

    async def connector(_url: str) -> FakeConnection:
        return connection

    monkeypatch.setenv("CA_AGENT_MODE", "live")
    monkeypatch.setenv("GEMINI_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def exercise() -> dict[str, object]:
        session = GeminiLiveSession(_context(), connector=connector)
        await session.open()
        await session.send_audio(b"\x00\x01")
        await session.send_text("Tra cứu ca hôm nay")
        await session.send_activity_start()
        await session.send_activity_end()
        connection.response = {"serverContent": {"turnComplete": True}}
        event = await session.receive()
        await session.close()
        return event

    event = asyncio.run(exercise())
    audio = json.loads(str(connection.sent[1]))
    text = json.loads(str(connection.sent[2]))
    act_start = json.loads(str(connection.sent[3]))
    act_end = json.loads(str(connection.sent[4]))

    assert audio == {
        "realtimeInput": {
            "audio": {"mimeType": "audio/pcm;rate=16000", "data": "AAE="}
        }
    }
    assert text == {
        "clientContent": {
            "turns": [
                {"role": "user", "parts": [{"text": "Tra cứu ca hôm nay"}]}
            ],
            "turnComplete": True,
        }
    }
    assert act_start == {"realtimeInput": {"activityStart": {}}}
    assert act_end == {"realtimeInput": {"activityEnd": {}}}
    assert event == {"serverContent": {"turnComplete": True}}
    assert connection.closed is True


def test_setup_message_buoc_goi_tool_cho_cau_hoi_ca_nhan() -> None:
    """Prompt Live phải buộc gọi tool cho câu hỏi ca/lịch của chính người dùng.

    Không có chỉ dẫn này, Live đáp câu xã giao ("em có thể hỗ trợ...") và người
    dùng tưởng trợ lý không trả lời được — trong khi chat text vẫn chạy pipeline.
    """
    setup = json.loads(build_setup_message(_context()))
    instruction = setup["setup"]["systemInstruction"]["parts"][0]["text"]

    assert "BẮT BUỘC gọi tool run_copilot_pipeline" in instruction
    assert "lịch hôm nay của tôi" in instruction
    assert "hôm nay tôi có ca không" in instruction
    # Không được cho phép model tự bịa kết quả hay từ chối tra cứu.
    assert "không tự suy đoán kết quả" in instruction
    assert "không có thông tin lịch cá nhân" in instruction
    # Danh tính phải do server chèn, client không thấy.
    assert "nv_01" in instruction


def test_setup_message_khai_bao_tool_va_model_dung() -> None:
    """Setup frame phải khai tool pipeline và đúng model extended thinking."""
    setup = json.loads(build_setup_message(_context()))["setup"]

    assert setup["model"] == f"models/{GEMINI_LIVE_MODEL}"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    # Model extended-thinking bắt buộc có thinkingLevel, thiếu là WS đóng.
    assert setup["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "LOW"}
    declarations = setup["tools"][0]["functionDeclarations"]
    assert declarations[0]["name"] == "run_copilot_pipeline"
    assert declarations[0]["parameters"]["required"] == ["message"]
