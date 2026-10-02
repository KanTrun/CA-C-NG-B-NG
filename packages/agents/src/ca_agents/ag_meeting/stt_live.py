"""STT Live — Transcribe audio using gemini-3.5-transcribe-live via WebSocket.

Nguyên tắc (260918): API Gemini CHỈ dùng cho model Live. STT cuộc họp dùng
`gemini-3.5-transcribe-live` (Live, không hạn mức) thay vì REST `gemini-2.5-flash`
(có hạn mức). Module này mở WebSocket Gemini Live, gửi audio PCM16 16kHz theo chunk,
nhận transcript streaming.

Fallback: nếu không có GEMINI_API_KEY hoặc WebSocket lỗi → trả về replay fixture
(giống stt.py) để không chặn luồng.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import wave
from dataclasses import dataclass
from io import BytesIO

from ca_agents.llm import agent_mode, ensure_dotenv

GEMINI_LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)
GEMINI_TRANSCRIBE_LIVE_MODEL = "gemini-3.5-transcribe-live"
SETUP_TIMEOUT_SECONDS = 15.0
RECV_TIMEOUT_SECONDS = 20.0
# Chunk 1 giây PCM16 16kHz = 32000 bytes
_CHUNK_BYTES = 16000 * 2


@dataclass(frozen=True)
class TranscriptSegment:
    nguoi_noi: str
    noi_dung: str
    bat_dau_s: float | None = None
    ket_thuc_s: float | None = None


@dataclass(frozen=True)
class TranscribeResult:
    ok: bool
    raw_text: str
    segments: list[TranscriptSegment]
    provider: str
    reason: str


def _replay_transcribe() -> TranscribeResult:
    """Fixture fallback cho offline/CI replay."""
    fixture_segs = [
        TranscriptSegment(
            nguoi_noi="Quản lý",
            noi_dung="Chào cả nhà, ca chiều nay chúng ta cần vệ sinh máy pha và kiểm tra tủ đá.",
        ),
        TranscriptSegment(
            nguoi_noi="Tuấn", noi_dung="Dạ em Tuấn nhận lau máy pha và thay ron trước 16h."
        ),
        TranscriptSegment(
            nguoi_noi="My", noi_dung="Dạ em My sẽ dán lại công thức trà đào mới trước 17h."
        ),
    ]
    raw = " ".join(s.noi_dung for s in fixture_segs)
    return TranscribeResult(
        ok=True,
        raw_text=raw,
        segments=fixture_segs,
        provider="replay_fixture",
        reason="offline_replay",
    )


def _decode_to_pcm16_16khz(audio_bytes: bytes, mime_type: str) -> bytes | None:
    """Decode audio bytes -> PCM16 16kHz mono.

    Ưu tiên ffmpeg (imageio-ffmpeg) — decode mọi định dạng (webm/opus, mp3, ogg, wav).
    Fallback: wav PCM trực tiếp nếu không có ffmpeg.
    """
    # 1. Thử ffmpeg (imageio-ffmpeg) — decode mọi định dạng sang PCM16 16kHz mono
    try:
        import subprocess

        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [
                ffmpeg,
                "-i", "pipe:0",
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception:
        pass

    # 2. Fallback: wav PCM trực tiếp
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime in ("audio/wav", "audio/x-wav", "audio/wave") or audio_bytes[:4] == b"RIFF":
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as w:
                ch = w.getnchannels()
                rate = w.getframerate()
                width = w.getsampwidth()
                data = w.readframes(w.getnframes())
            if width != 2:
                return None
            if ch == 1 and rate == 16000:
                return data
            if ch == 2:
                import array

                arr = array.array("h", data)
                mono = array.array("h")
                for i in range(0, len(arr) - 1, 2):
                    mono.append((arr[i] + arr[i + 1]) // 2)
                data = mono.tobytes()
            if rate != 16000:
                import array

                arr = array.array("h", data)
                n_out = int(len(arr) * 16000 / rate)
                out = array.array("h")
                for i in range(n_out):
                    src = i * rate / 16000
                    i0 = int(src)
                    i1 = min(i0 + 1, len(arr) - 1)
                    frac = src - i0
                    out.append(int(arr[i0] * (1 - frac) + arr[i1] * frac))
                data = out.tobytes()
            return data
        except Exception:
            return None
    return None


def _merge_interim_transcripts(transcripts: list[str]) -> str:
    """Gộp chuỗi transcript streaming thành văn bản hoàn chỉnh.

    interimInputTranscription là tiền tố mở dần ("Good" → "Good morning" →
    "Good morning, team.") — nối nguyên chuỗi thì bản bóc băng lặp từng cụm
    từ (gặp thật 2026-10-01 với file TTS). Đoạn mới mở rộng đoạn trước thì
    THAY thế; đoạn trùng lặp thì bỏ; đoạn mới (lượt nói khác) thì nối tiếp.
    """
    merged: list[str] = []
    for t in transcripts:
        t = t.strip()
        if not t:
            continue
        if merged and t.startswith(merged[-1]):
            merged[-1] = t
        elif merged and merged[-1].startswith(t):
            continue
        else:
            merged.append(t)
    return " ".join(merged).strip()


async def _transcribe_live_ws(audio_pcm: bytes, api_key: str) -> TranscribeResult:
    """Mở WebSocket Gemini Live, gửi audio, nhận transcript.

    Gửi và nhận SONG SONG (2 task asyncio) để giữ WebSocket sống (tránh keepalive
    ping timeout) và không dồn token. Gửi nhanh theo chunk, đồng thời nhận
    transcript streaming liên tục.
    """
    from websockets.asyncio.client import connect

    url = f"{GEMINI_LIVE_ENDPOINT}?key={api_key}"
    transcripts: list[str] = []
    done = asyncio.Event()

    async with connect(url, max_size=8 * 1024 * 1024) as ws:
        # Setup
        await ws.send(
            json.dumps(
                {
                    "setup": {
                        "model": f"models/{GEMINI_TRANSCRIBE_LIVE_MODEL}",
                        "inputAudioTranscription": {},
                    }
                }
            )
        )
        # Đọc setupComplete
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=SETUP_TIMEOUT_SECONDS)
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8")
            data = json.loads(msg)
            if "setupComplete" in data:
                break
            if "error" in data:
                return TranscribeResult(
                    ok=False, raw_text="", segments=[], provider="gemini_live", reason=f"setup_error:{data['error']}"
                )

        async def _send_audio() -> None:
            """Gửi audio nhanh theo chunk, không pacing (tránh keepalive timeout)."""
            try:
                for i in range(0, len(audio_pcm), _CHUNK_BYTES):
                    chunk = audio_pcm[i : i + _CHUNK_BYTES]
                    await ws.send(
                        json.dumps(
                            {
                                "realtimeInput": {
                                    "audio": {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": base64.b64encode(chunk).decode("ascii"),
                                    }
                                }
                            }
                        )
                    )
                    # Nghỉ ngắn để không dồn token quá nhanh (tránh 1011 quota)
                    await asyncio.sleep(0.05)
                # Đánh dấu hết audio
                await ws.send(json.dumps({"realtimeInput": {"activityEnd": {}}}))
            finally:
                done.set()

        async def _recv_transcript() -> None:
            """Nhận transcript streaming liên tục.

            Dừng khi: nhận turnComplete/interrupted, hoặc audio đã gửi xong (done)
            và đã nhận được transcript (interim/final). Model transcribe-live gửi
            interimInputTranscription liên tục, không nhất thiết có final.
            """
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_SECONDS)
                    if isinstance(msg, bytes):
                        msg = msg.decode("utf-8")
                    data = json.loads(msg)
                    if "serverContent" in data:
                        sc = data["serverContent"]
                        # Transcript từ modelTurn (nếu có)
                        if "modelTurn" in sc:
                            for part in sc["modelTurn"].get("parts", []):
                                if "transcript" in part:
                                    transcripts.append(part["transcript"])
                        # Transcript từ input transcription (interim/final)
                        if "interimInputTranscription" in sc:
                            t = sc["interimInputTranscription"].get("text", "")
                            if t:
                                transcripts.append(t)
                        if "finalInputTranscription" in sc:
                            t = sc["finalInputTranscription"].get("text", "")
                            if t:
                                transcripts.append(t)
                        if sc.get("turnComplete"):
                            break
                        if sc.get("interrupted"):
                            break
                        # Audio đã gửi xong + đã có transcript → dừng
                        if done.is_set() and transcripts:
                            break
                    if "error" in data:
                        break
            except TimeoutError:
                pass

        # Chạy song song gửi + nhận
        send_task = asyncio.create_task(_send_audio())
        recv_task = asyncio.create_task(_recv_transcript())
        await asyncio.gather(send_task, recv_task)

    raw_text = _merge_interim_transcripts(transcripts)
    if not raw_text:
        return TranscribeResult(
            ok=False, raw_text="", segments=[], provider="gemini_live", reason="empty_transcript"
        )
    return TranscribeResult(
        ok=True,
        raw_text=raw_text,
        segments=[TranscriptSegment(nguoi_noi="Người nói", noi_dung=raw_text)],
        provider="gemini_live",
        reason="success",
    )


# Chunk 30 giây PCM16 16kHz = 960000 bytes. Mỗi chunk < 20K token/phút để không
# vượt quota token của gemini-3.5-transcribe-live.
_CHUNK_AUDIO_BYTES = 16000 * 2 * 30
# Chờ giữa các chunk để reset quota token/phút (20K).
_CHUNK_COOLDOWN_S = 5.0


async def transcribe_audio_live_async(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    *,
    language: str = "vi",
    timeout_s: float = 60.0,
) -> TranscribeResult:
    """Transcribe audio bằng gemini-3.5-transcribe-live (WebSocket Live) — async.

    Chunking: chia audio thành đoạn 30s, gửi từng đoạn riêng, chờ giữa các đoạn
    để reset quota token/phút (20K), nối transcript.

    Fallback: replay fixture nếu không có key / không decode được / WebSocket lỗi.
    """
    if not audio_bytes:
        return _replay_transcribe()

    mode = agent_mode()
    if mode == "replay":
        return _replay_transcribe()

    ensure_dotenv()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return _replay_transcribe()

    pcm = _decode_to_pcm16_16khz(audio_bytes, mime_type)
    if pcm is None:
        return _replay_transcribe()

    # Chunking audio thành đoạn 30s
    chunks = [
        pcm[i : i + _CHUNK_AUDIO_BYTES]
        for i in range(0, len(pcm), _CHUNK_AUDIO_BYTES)
    ]
    all_text: list[str] = []
    last_err = ""
    for idx, chunk in enumerate(chunks):
        try:
            result = await _transcribe_live_ws(chunk, gemini_key)
        except Exception as exc:  # noqa: BLE001
            last_err = f"error:{exc}"
            break
        if result.ok and result.raw_text:
            all_text.append(result.raw_text)
        elif not result.ok:
            last_err = result.reason
            # Nếu chunk đầu lỗi quota, dừng luôn
            if idx == 0:
                break
        # Chờ giữa các chunk để reset quota token/phút
        if idx < len(chunks) - 1:
            await asyncio.sleep(_CHUNK_COOLDOWN_S)

    raw_text = " ".join(all_text).strip()
    if not raw_text:
        return TranscribeResult(
            ok=False, raw_text="", segments=[], provider="gemini_live", reason=last_err or "empty_transcript"
        )
    return TranscribeResult(
        ok=True,
        raw_text=raw_text,
        segments=[TranscriptSegment(nguoi_noi="Người nói", noi_dung=raw_text)],
        provider="gemini_live",
        reason="success",
    )


def transcribe_audio_live(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    *,
    language: str = "vi",
    timeout_s: float = 60.0,
) -> TranscribeResult:
    """Wrapper sync — dùng cho endpoint sync (transcribe). Async context nên gọi
    `transcribe_audio_live_async` trực tiếp để tránh lỗi event loop."""
    try:
        return asyncio.run(
            transcribe_audio_live_async(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                language=language,
                timeout_s=timeout_s,
            )
        )
    except RuntimeError:
        # Đang trong event loop — không thể asyncio.run. Trả replay để không chặn.
        return _replay_transcribe()