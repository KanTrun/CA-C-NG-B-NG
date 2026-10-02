# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests cho module sinh ảnh quảng cáo (ca_agents.image_gen).

Không gọi mạng thật: urllib.request.urlopen được monkeypatch trong mọi test
(phòng test_no_network chặn socket.connect ở chế độ replay).
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from ca_agents import image_gen
from ca_agents.image_gen import ImageGenResult, edit_image, generate_image

_FAKE_JPEG = b"\xff\xd8\xff" + b"fake-jpeg-bytes"
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"


class _FakeResponse:
    """Context manager tối giản thay cho đối tượng response của urlopen.

    ``read`` nhận tham số kích thước như ``http.client.HTTPResponse.read(amt)``
    thật — ``_read_limited`` luôn gọi kèm giới hạn byte nên fake không có tham số
    sẽ làm test đỏ vì lý do không liên quan tới hành vi cần kiểm.
    """

    def __init__(self, body: bytes, content_type: str = "image/jpeg") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self, amt: int | None = None) -> bytes:
        return self._body if amt is None else self._body[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _http_error(url: str, code: int, detail: str = "boom") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, detail, hdrs=None, fp=io.BytesIO(detail.encode()))  # type: ignore[arg-type]


def _gemini_ok_body(blob: bytes = _FAKE_PNG) -> bytes:
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(blob).decode()}}
                    ]
                }
            }
        ]
    }
    return json.dumps(payload).encode()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mọi test đều chạy với env sạch, không phụ thuộc .env của developer.

    Xoá HẾT biến của mọi provider ảnh: để lọt một biến vào là test gọi mạng thật
    (hoặc phụ thuộc key trên máy người chạy, kết quả tuỳ máy). Test nào cần
    provider cụ thể thì tự ``monkeypatch.setenv`` lại.
    """
    monkeypatch.setattr(image_gen, "ensure_dotenv", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("POLLINATIONS_MODEL", raising=False)
    monkeypatch.delenv("POLLINATIONS_API_KEY", raising=False)
    monkeypatch.delenv("POLLINATIONS_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_IMAGE_MODEL", raising=False)


def _cf_ok_body(blob: bytes = _FAKE_JPEG) -> bytes:
    """Response thật của Workers AI: ảnh nằm ở ``result.image`` (base64)."""
    return json.dumps(
        {"success": True, "result": {"image": base64.b64encode(blob).decode()}}
    ).encode()


def _cf_configure(monkeypatch: pytest.MonkeyPatch, token: str = "cf-token") -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", token)


def test_empty_prompt_fails_closed() -> None:
    res = generate_image("   ")
    assert res.ok is False
    assert res.error == "empty_prompt"
    assert res.image_bytes == b""


def test_no_key_at_all_goes_straight_to_pollinations(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        return _FakeResponse(_FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("a cold coffee poster")

    assert res.ok is True
    assert res.provider == "pollinations"
    assert res.image_bytes == _FAKE_JPEG
    assert res.image_mime == "image/jpeg"
    assert len(calls) == 1
    assert "image.pollinations.ai" in calls[0]


# ── Cloudflare Workers AI: provider sinh ảnh CHÍNH ─────────────────────


def test_cloudflare_used_first_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Có Account ID + token thì Cloudflare là provider đầu tiên."""
    _cf_configure(monkeypatch)
    calls: list[str] = []
    bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        calls.append(req.full_url)
        bodies.append(req.data)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("iced peach tea", aspect_ratio="1:1", seed=5)

    assert res.ok is True
    assert res.provider == "cloudflare"
    assert res.model == image_gen._CF_MODELS[0]
    assert res.image_bytes == _FAKE_JPEG
    assert res.image_mime == "image/jpeg"
    assert len(calls) == 1
    assert "/accounts/acc-123/ai/run/" in calls[0]
    # Token đi ở header, KHÔNG được lọt vào body.
    assert b"cf-token" not in bodies[0]
    assert b"Bearer" not in bodies[0]


def test_cloudflare_sends_width_height_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kích thước + seed phải đi trong multipart, nếu không mọi tỷ lệ ra ảnh vuông.

    Cloudflare là provider duy nhất nhận thẳng ``width``/``height`` (đã kiểm
    chứng 896×1120 và 768×1344 trả đúng kích thước) nên đây là chỗ giữ tỷ lệ khung.
    """
    _cf_configure(monkeypatch)
    bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        bodies.append(req.data)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_image("poster", aspect_ratio="4:5", seed=11)

    assert len(bodies) == 1
    body = bodies[0]
    assert b'name="width"' in body and b"896" in body
    assert b'name="height"' in body and b"1120" in body
    assert b'name="seed"' in body and b"11" in body
    assert b'name="prompt"' in body


def test_cloudflare_aspect_ratio_9_16_dims(monkeypatch: pytest.MonkeyPatch) -> None:
    """9:16 phải ra 768×1344 (đã kiểm chứng Cloudflare chấp nhận)."""
    _cf_configure(monkeypatch)
    bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        bodies.append(req.data)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_image("poster", aspect_ratio="9:16")

    assert b"768" in bodies[0] and b"1344" in bodies[0]


def test_cloudflare_env_model_tried_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _cf_configure(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-dev")
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.model == "@cf/black-forest-labs/flux-2-dev"
    assert len(seen) == 1
    assert seen[0].endswith("@cf/black-forest-labs/flux-2-dev")


def test_cloudflare_404_falls_back_to_next_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model đầu không tồn tại (Cloudflare gỡ model) → thử model kế tiếp."""
    _cf_configure(monkeypatch)
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        if len(seen) == 1:
            raise _http_error(req.full_url, 404, "no such model")
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.model == image_gen._CF_MODELS[1]
    assert len(seen) == 2


def test_cloudflare_failure_falls_back_to_gemini_then_pollinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloudflare lỗi thật (5xx) → nhường Gemini rồi Pollinations, không bỏ cuộc.

    Một provider lỗi không được làm cả tính năng đứng: còn hai nguồn khác.
    """
    _cf_configure(monkeypatch)
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url
        calls.append(url)
        if "api.cloudflare.com" in url:
            raise _http_error(url, 503, "upstream down")
        return _FakeResponse(_FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "pollinations"
    assert any("api.cloudflare.com" in u for u in calls)
    assert any("image.pollinations.ai" in u for u in calls)


def test_both_cloudflare_models_404_falls_back_to_pollinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mọi model Cloudflare đều 404 → nhường provider khác thay vì báo lỗi cho quán."""
    _cf_configure(monkeypatch)
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url
        calls.append(url)
        if "api.cloudflare.com" in url:
            raise _http_error(url, 404, "no such model")
        return _FakeResponse(_FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "pollinations"
    assert sum("api.cloudflare.com" in u for u in calls) == len(image_gen._CF_MODELS)


def test_cloudflare_no_image_in_response_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """21200: ``success:true`` nhưng không có ảnh → nhường provider sau."""
    _cf_configure(monkeypatch)

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        if "api.cloudflare.com" in req.full_url:
            return _FakeResponse(
                json.dumps({"success": True, "result": {}}).encode(), "application/json"
            )
        return _FakeResponse(_FAKE_JPEG, "image/jpeg")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "pollinations"


def test_sniffs_jpeg_mime_from_magic_bytes() -> None:
    assert image_gen._sniff_image_mime(_FAKE_JPEG) == "image/jpeg"
    assert image_gen._sniff_image_mime(_FAKE_PNG) == "image/png"


def test_aspect_ratio_maps_to_pollinations_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_image("poster", aspect_ratio="9:16")

    assert "width=768" in seen[0]
    assert "height=1344" in seen[0]


def test_unknown_aspect_ratio_falls_back_to_square(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_image("poster", aspect_ratio="3:2")

    assert "width=1024" in seen[0]
    assert "height=1024" in seen[0]


def test_gemini_success_returns_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResponse(_gemini_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "gemini"
    assert res.model == image_gen._IMAGE_MODELS[0]
    assert res.image_bytes == _FAKE_PNG
    assert res.image_mime == "image/png"


def test_gemini_429_falls_back_to_pollinations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        if "generativelanguage" in url:
            raise _http_error(url, 429, "quota limit: 0")
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "pollinations"
    # Chỉ gọi Gemini đúng 1 lần (429 → break, không thử model kế tiếp).
    assert sum("generativelanguage" in u for u in calls) == 1


def test_gemini_404_tries_next_model_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    gemini_models: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url
        gemini_models.append(url.split("/models/")[1].split(":")[0])
        if len(gemini_models) == 1:
            raise _http_error(url, 404, "not found")
        return _FakeResponse(_gemini_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert res.provider == "gemini"
    assert gemini_models == list(image_gen._IMAGE_MODELS[:2])


def test_gemini_env_model_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "custom-image-model")
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url.split("/models/")[1].split(":")[0])
        return _FakeResponse(_gemini_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is True
    assert seen[0] == "custom-image-model"


def test_gemini_response_without_image_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    text_only = json.dumps({"candidates": [{"content": {"parts": [{"text": "sorry"}]}}]}).encode()

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "generativelanguage" in url:
            return _FakeResponse(text_only, "application/json")
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    # no_image_in_response không phải 404 → dừng vòng Gemini, rơi xuống Pollinations.
    assert res.ok is True
    assert res.provider == "pollinations"


def test_pollinations_retries_on_500_and_increments_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        if len(seen) < 3:
            raise _http_error(req.full_url, 500, "temporarily unavailable")
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster", seed=100)

    assert res.ok is True
    assert res.provider == "pollinations"
    assert len(seen) == 3
    assert "seed=100" in seen[0]
    assert "seed=101" in seen[1]
    assert "seed=102" in seen[2]


def test_pollinations_all_attempts_fail_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        raise _http_error(req.full_url, 503, "down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is False
    assert res.provider == "pollinations"
    assert res.error.startswith("http_503")
    assert res.image_bytes == b""


def test_pollinations_non_image_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResponse(b"<html>error gateway</html>", "text/html")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = generate_image("poster")

    assert res.ok is False
    assert res.error == "no_image_in_response"


def test_pollinations_uses_env_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_MODEL", "turbo")
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        return _FakeResponse(_FAKE_JPEG)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_image("poster")

    assert "model=turbo" in seen[0]


def test_gemini_http_error_details_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        raise _http_error(url, 400, "bad config")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = image_gen._gemini_image(token="t", model="x", prompt="p", timeout_s=1.0)
    assert res.ok is False
    assert res.error.startswith("http_400")


def test_image_gen_result_is_frozen() -> None:
    res = ImageGenResult(ok=False, error="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.ok = True  # type: ignore[misc]


# ── edit_image: AI sửa ẢNH THẬT (image-to-image) ────────────────────────────


def _edit_ok_body(blob: bytes = _FAKE_JPEG) -> bytes:
    """Response của `/v1/images/edits` (OpenAI Images-compatible)."""
    return json.dumps(
        {"created": 1, "data": [{"b64_json": base64.b64encode(blob).decode()}]}
    ).encode()


def test_edit_image_requires_original() -> None:
    """Thiếu ảnh gốc → lỗi rõ ràng, KHÔNG âm thầm chuyển sang text-to-image."""
    res = edit_image(b"", "make it a poster")
    assert res.ok is False
    assert res.error == "missing_original_image"


def test_edit_image_requires_prompt() -> None:
    res = edit_image(_FAKE_JPEG, "   ")
    assert res.ok is False
    assert res.error == "empty_prompt"


def test_edit_image_needs_a_key() -> None:
    """Không key nào → lỗi kèm hướng dẫn lấy key, không bịa ảnh."""
    res = edit_image(_FAKE_JPEG, "make it a poster")
    assert res.ok is False
    assert res.error == "thieu_key_sua_anh"
    assert "enter.pollinations.ai/keys" in res.text


def test_edit_image_pollinations_used_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        calls.append(req.full_url)
        return _FakeResponse(_edit_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "professional cafe ad")

    assert res.ok is True
    assert res.provider == "pollinations-edit"
    assert res.model == image_gen._POLLINATIONS_EDIT_MODELS[0]
    assert res.image_bytes == _FAKE_JPEG
    assert res.image_mime == "image/jpeg"
    assert len(calls) == 1
    assert "/v1/images/edits" in calls[0]


def test_edit_image_sends_multipart_with_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Body PHẢI chứa ảnh nhị phân — thiếu nó là text-to-image, mất ý nghĩa i2i."""
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    sent: list[Any] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        sent.append(req)
        return _FakeResponse(_edit_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    edit_image(_FAKE_JPEG, "professional cafe ad", image_filename="mon_tra.jpg")

    req = sent[0]
    ctype = req.get_header("Content-type")
    assert ctype is not None and ctype.startswith("multipart/form-data; boundary=")
    body = req.data
    assert isinstance(body, bytes)
    # Ảnh gốc nằm nguyên trong body, kèm tên field và tên file.
    assert _FAKE_JPEG in body
    assert b'name="image"' in body
    assert b"mon_tra.jpg" in body
    assert b'name="prompt"' in body
    assert b'name="model"' in body


def test_edit_image_env_model_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    monkeypatch.setenv("POLLINATIONS_IMAGE_MODEL", "black-forest-labs/flux.1-kontext-max")
    body_seen: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        body_seen.append(req.data)
        return _FakeResponse(_edit_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.model == "black-forest-labs/flux.1-kontext-max"
    assert b"black-forest-labs/flux.1-kontext-max" in body_seen[0]


def test_edit_image_404_tries_next_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    seen: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.data)
        if len(seen) == 1:
            raise _http_error(req.full_url, 404, "not found")
        return _FakeResponse(_edit_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.model == image_gen._POLLINATIONS_EDIT_MODELS[1]
    assert len(seen) == 2


def test_edit_image_falls_back_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pollinations lỗi thật → thử Gemini (cũng nhận base64 ảnh gốc)."""
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        url = req.full_url
        seen.append(url)
        if "gen.pollinations.ai" in url:
            raise _http_error(url, 500, "upstream down")
        return _FakeResponse(_gemini_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.provider == "gemini"
    assert any("generativelanguage" in u for u in seen)


def test_edit_image_url_response_is_downloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """`response_format=url` cũng phải chạy: tải ảnh về thay vì bỏ cuộc."""
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    first = json.dumps({"created": 1, "data": [{"url": "https://cdn.example/a.jpg"}]}).encode()
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        # Lần tải ảnh được gọi bằng URL CHUỖI (không phải Request) — khác lần gọi
        # API, nên phải xử lý cả hai dạng.
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        if url.startswith("https://cdn.example/"):
            return _FakeResponse(_FAKE_JPEG, "image/jpeg")
        return _FakeResponse(first, "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.image_bytes == _FAKE_JPEG
    assert any(u.startswith("https://cdn.example/") for u in calls)


def test_edit_image_no_image_in_response_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResponse(json.dumps({"created": 1, "data": []}).encode(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is False
    assert res.error == "no_image_in_response"


def test_edit_image_bad_json_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResponse(b"<html>gateway</html>", "text/html")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is False
    assert res.error == "bad_json_response"


# ── Cloudflare Workers AI: provider sửa ảnh MIỄN PHÍ chính ──────────────────


def test_cf_ready_needs_both_account_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Thiếu MỘT trong hai là không dùng được — khác mọi provider chỉ cần 1 key.

    Account id nằm trong đường dẫn URL, token nằm ở header; chỉ có token thì
    không dựng nổi request, nên phải trả None chứ không ghép chuỗi rỗng.
    """
    assert image_gen._cf_ready() is None
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-123")
    assert image_gen._cf_ready() is None
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    assert image_gen._cf_ready() is None
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-123")
    assert image_gen._cf_ready() == ("acc-123", "cf-token")


def test_cf_ready_ignores_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dán key kèm khoảng trắng (lỗi thường gặp) vẫn phải nhận."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "  acc-123  ")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", " cf-token ")
    assert image_gen._cf_ready() == ("acc-123", "cf-token")


def test_edit_image_cloudflare_used_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Có Cloudflare → dùng NGAY, không đụng tới provider sau."""
    _cf_configure(monkeypatch)
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")  # cám dỗ fallback
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        calls.append(req.full_url)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "professional cafe ad")

    assert res.ok is True
    assert res.provider == "cloudflare"
    assert res.model == image_gen._CF_MODELS[0]
    assert res.image_bytes == _FAKE_JPEG
    assert res.image_mime == "image/jpeg"
    assert len(calls) == 1
    assert "/accounts/acc-123/ai/run/" in calls[0]


def test_edit_image_cloudflare_sends_photo_in_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ảnh gốc PHẢI đi trong body — thiếu nó là text-to-image, mất ý nghĩa i2i."""
    _cf_configure(monkeypatch)
    sent: list[Any] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        sent.append(req)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    edit_image(_FAKE_JPEG, "ad", image_filename="tra-bi-dao.jpg")

    req = sent[0]
    ctype = req.get_header("Content-type")
    assert ctype is not None and ctype.startswith("multipart/form-data; boundary=")
    body = req.data
    assert isinstance(body, bytes)
    # Cloudflare khai báo input kiểu multipart cho flux-2 → phải là multipart,
    # không phải JSON base64.
    assert _FAKE_JPEG in body
    assert b'name="input_image_0"' in body
    assert b"tra-bi-dao.jpg" in body
    assert b'name="prompt"' in body
    # Token đi ở header, KHÔNG được lọt vào body.
    assert req.get_header("Authorization") == "Bearer cf-token"
    assert b"cf-token" not in body


def test_edit_image_cloudflare_env_model_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    _cf_configure(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-dev")
    urls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        urls.append(req.full_url)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.model == "@cf/black-forest-labs/flux-2-dev"
    assert len(urls) == 1
    assert urls[0].endswith("@cf/black-forest-labs/flux-2-dev")


def test_edit_image_cloudflare_retries_other_field_on_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tài liệu Cloudflare không nêu tên trường → 400 thì thử tên khác rồi mới bỏ.

    Sai tên trường là lỗi cấu hình phổ biến nhất khi tích hợp Workers AI; bỏ cuộc
    ngay sẽ khiến chế độ sửa ảnh hỏng dù mọi thứ khác đúng.
    """
    _cf_configure(monkeypatch)
    bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        bodies.append(req.data)
        if b'name="input_image_0"' in req.data:
            raise _http_error(req.full_url, 400, '{"errors":[{"code":5006}]}')
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert len(bodies) == 2
    assert b'name="input_image_0"' in bodies[0]
    assert b'name="image"' in bodies[1]


def test_edit_image_cloudflare_no_field_retry_on_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 (token sai) thì đổi tên trường cũng vô ích → không tốn thêm lượt gọi."""
    _cf_configure(monkeypatch, token="cf-sai")
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        calls.append(req.full_url)
        raise _http_error(req.full_url, 401, "invalid token")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is False
    assert res.provider == "cloudflare"
    # Đúng MỘT lượt: không thử tên trường khác, không thử model khác — lỗi quyền
    # thì mọi biến thể đều hỏng, gọi thêm chỉ làm người dùng chờ vô ích.
    assert len(calls) == 1


def test_edit_image_cloudflare_404_tries_next_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model bị gỡ → tự chuyển model kế tiếp, không cần sửa code."""
    _cf_configure(monkeypatch)
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        if len(seen) == 1:
            raise _http_error(req.full_url, 404, "no such model")
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.model == image_gen._CF_MODELS[1]
    assert len(seen) == 2


def test_edit_image_cloudflare_success_false_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """``success:false`` kèm HTTP 200 là bình thường ở Workers AI — phải đọc."""
    _cf_configure(monkeypatch)

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        body = json.dumps(
            {"success": False, "errors": [{"code": 3036, "message": "quota exceeded"}]}
        ).encode()
        return _FakeResponse(body, "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is False
    assert res.error.startswith("cf_error")
    assert "3036" in res.error


def test_edit_image_cloudflare_no_image_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _cf_configure(monkeypatch)

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResponse(json.dumps({"success": True, "result": {}}).encode(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is False
    assert res.error == "no_image_in_response"


def test_edit_image_cloudflare_result_as_plain_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vài model trả ``result`` là chuỗi base64 trực tiếp, không bọc trong dict."""
    _cf_configure(monkeypatch)

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        body = json.dumps(
            {"success": True, "result": base64.b64encode(_FAKE_PNG).decode()}
        ).encode()
        return _FakeResponse(body, "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.image_bytes == _FAKE_PNG
    assert res.image_mime == "image/png"


def test_edit_image_cloudflare_failure_falls_back_to_pollinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloudflare chết (500) → hết lượt gọi phải nhường Pollinations, không bỏ cuộc.

    Hai nguồn free độc lập nhau: Cloudflare hết neurons/ngày là chuyện bình
    thường, lúc đó ảnh vẫn phải ra.
    """
    _cf_configure(monkeypatch)
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        seen.append(req.full_url)
        if "api.cloudflare.com" in req.full_url:
            raise _http_error(req.full_url, 500, "internal")
        return _FakeResponse(_edit_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = edit_image(_FAKE_JPEG, "ad")

    assert res.ok is True
    assert res.provider == "pollinations-edit"
    assert any("api.cloudflare.com" in u for u in seen)
    assert any("gen.pollinations.ai" in u for u in seen)


def test_edit_image_cloudflare_text_only_when_no_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Không có ảnh gốc thì ``_cf_image_any_field`` không gắn trường ảnh."""
    _cf_configure(monkeypatch)
    bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        bodies.append(req.data)
        return _FakeResponse(_cf_ok_body(), "application/json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = image_gen._cf_image_any_field(
        account="acc-123", token="cf-token", model=image_gen._CF_MODELS[0],
        prompt="a cup of tea", timeout_s=30.0,
    )

    assert res.ok is True
    assert b'name="input_image_0"' not in bodies[0]
    assert b'name="prompt"' in bodies[0]


def test_edit_image_needs_a_key_message_mentions_cloudflare() -> None:
    """Thiếu hết khoá → hướng dẫn phải nêu Cloudflare (nguồn free dễ lấy nhất)."""
    res = edit_image(_FAKE_JPEG, "ad")
    assert res.error == "thieu_key_sua_anh"
    assert "CLOUDFLARE_ACCOUNT_ID" in res.text


# ── image_edit_available: UI biết TRƯỚC chế độ nào chạy được ────────────────


def test_image_edit_unavailable_without_any_key() -> None:
    """Không khoá nào → chế độ sửa ảnh không chạy được, kèm cách khắc phục."""
    ok, reason = image_gen.image_edit_available()
    assert ok is False
    # Lý do phải chỉ RÕ nơi lấy khoá (Cloudflare — free, không cần thẻ) và các
    # chế độ thay thế, nếu không người dùng mới không biết làm gì tiếp.
    assert "CLOUDFLARE_ACCOUNT_ID" in reason
    assert "dash.cloudflare.com" in reason
    assert "Giữ nguyên sản phẩm" in reason


def test_image_edit_unavailable_with_only_gemini_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHỈ có Gemini KHÔNG đủ để bật chế độ sửa ảnh.

    Model ảnh Gemini trên free tier trả 429 (`THIRD_PARTY.md`: limit=0) — coi là
    khả dụng sẽ mời người dùng chọn chế độ mà mọi lượt bấm đều hỏng.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    ok, reason = image_gen.image_edit_available()
    assert ok is False
    assert "CLOUDFLARE_ACCOUNT_ID" in reason
    # Lý do phải gợi ý chế độ chạy được ngay để người dùng không bị chặn việc.
    # Nhãn chế độ phải khớp UI hiện tại (chạy cho mọi bao bì, không riêng ly).
    assert "Giữ nguyên sản phẩm" in reason


def test_image_edit_available_with_pollinations_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    ok, reason = image_gen.image_edit_available()
    assert ok is True
    assert reason == ""


def test_image_edit_available_ignores_whitespace_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Khoá toàn khoảng trắng (dán lỗi) không được coi là có khoá."""
    monkeypatch.setenv("POLLINATIONS_API_KEY", "   ")
    ok, _ = image_gen.image_edit_available()
    assert ok is False


def test_image_edit_available_does_not_need_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chỉ đọc env — không gọi mạng, nên UI gọi được lúc mở form."""

    def no_network(*_a, **_kw):  # noqa: ANN002, ANN003
        raise AssertionError("image_edit_available KHÔNG được gọi mạng")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
    ok, _ = image_gen.image_edit_available()
    assert ok is True
