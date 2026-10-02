"""Sinh ảnh thật từ prompt — Cloudflare Workers AI + Gemini image + Pollinations.

Fail-closed: trả về lỗi rõ ràng khi provider không có key hoặc không trả ảnh.
Không bịa ảnh, không trả placeholder.

Về ĐỘ TRỄ (vấn đề "gen ảnh lâu"): provider cộng đồng có model nặng (flux) chạy
15–40 giây/ảnh, và retry khi 429/500 có thể nhân thời gian lên nhiều lần. Ở đây
áp ba biện pháp: (1) mỗi lần gọi có NGÂN SÁCH THỜI GIAN tổng — hết ngân sách thì
dừng chứ không cộng dồn từng timeout; (2) đọc thân response có GIỚI HẠN byte —
ảnh lỗi khổng lồ không kéo dài thời gian; (3) khi model chính fail thì thử model
nhẹ hơn (turbo) trước khi bỏ cuộc.

Vì sao KHÔNG còn NVIDIA: ``ai.api.nvidia.com/v1/genai`` không nhận ảnh người dùng
(chỉ ``example_id`` do NVIDIA cấp) nên không làm được image-to-image ở tầng
provider; nó cũng chỉ là text-to-image thay thế được — Cloudflare Workers AI làm
cả hai việc với MIỄN PHÍ theo ngày. Bỏ NVIDIA thì hết hẳn một điểm hỏng
(key hết hạn, model bị gỡ) mà không mất tính năng nào: Cloudflare nhận thẳng
``width``/``height`` (đã kiểm chứng 768×1344 và 896×1120) nên mọi tỷ lệ khung
vẫn giữ nguyên.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from ca_agents.llm import _KEY_ENV, ensure_dotenv

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_UA = "nhip-quan/0.1 (https://github.com/KanTrun/Crew-Operations)"

# Trần seed dùng chung cho mọi provider (2^31-1) — vượt mức này một số backend
# tràn số nguyên 32 bit và trả ảnh không tái lập được.
_MAX_SEED = 2_147_483_647

# Model sinh ảnh của Gemini (free tier có thể không cấp quota).
_IMAGE_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-preview",
)

# Pollinations Gen — key `sk_...` HOẶC `pk_...`, lấy free (đăng nhập GitHub) tại
# https://enter.pollinations.ai/keys. Cần cho image-to-image; không cần cho
# text-to-image qua endpoint cũ ``image.pollinations.ai``.
_POLLINATIONS_KEY_ENV = "POLLINATIONS_API_KEY"

# ── Cloudflare Workers AI ───────────────────────────────────────────────────
# Miễn phí 10.000 neurons/NGÀY (reset 00:00 UTC), KHÔNG cần thẻ tín dụng.
# `flux-2-klein-4b` giá ~105 neurons cho ảnh 1024×1024 → khoảng 80–95 ảnh/ngày.
#
# Vì sao đây là provider TỐT NHẤT tìm được: model `flux-2-klein-4b`
# hợp nhất sinh ảnh VÀ sửa ảnh trong một model, nhận ảnh qua `multipart`, không
# giới hạn theo tháng như HuggingFace ($0.10/tháng) và không cần key chờ duyệt.
#
# Key gồm HAI phần (khác mọi provider trên): Account ID + API token. Token chỉ có
# quyền `Workers AI - Read/Edit` — không phải API key toàn tài khoản Cloudflare.
_CF_ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
_CF_TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
_CF_BASE = "https://api.cloudflare.com/client/v4/accounts"
# Model theo thứ tự ưu tiên. Cả hai đều nhận ảnh vào (image editing):
# - ``flux-2-klein-4b``: nhanh, hợp nhất generate + edit → mặc định.
# - ``flux-2-dev``: chất lượng cao hơn, hỗ trợ nhiều ảnh tham chiếu.
_CF_MODELS = (
    "@cf/black-forest-labs/flux-2-klein-4b",
    "@cf/black-forest-labs/flux-2-dev",
)
# Tên trường chứa ảnh tham chiếu, thử lần lượt. Tài liệu Cloudflare không nêu
# tên nên phải dò: quy ước mới cho model nhiều ảnh là ``input_image_0``; bản cũ
# dùng ``image``.
_CF_IMAGE_FIELDS = ("input_image_0", "image")

# Pollinations: text-to-image miễn phí, không cần key.
_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
# Endpoint Gen (mới) — có `/v1/images/edits` nhận ẢNH người dùng (image-to-image).
# KHÁC endpoint cũ ở trên: bản cũ chỉ text-to-image và không nhận ảnh tham chiếu.
# Cần ``POLLINATIONS_API_KEY`` (lấy free tại https://enter.pollinations.ai/keys —
# đăng nhập GitHub, kèm Pollen miễn phí từ Quests).
_POLLINATIONS_GEN_BASE = "https://gen.pollinations.ai"
# Model image-EDITING của Pollinations theo thứ tự ưu tiên. Đây là các model nhận
# ảnh vào và trả ảnh đã sửa — khác hẳn ``_POLLINATIONS_FALLBACK_MODELS`` (chỉ text).
_POLLINATIONS_EDIT_MODELS = (
    "black-forest-labs/flux.1-kontext-pro",
    "black-forest-labs/flux.1-kontext-max",
)
# Model text-to-image theo thứ tự ưu tiên khi model chính thất bại. "turbo"
# nhẹ hơn "flux" đáng kể (khoảng 3–8 giây so với 15–40 giây) — dùng làm phương
# án hai để người dùng không phải chờ lâu khi model nặng quá tải.
_POLLINATIONS_FALLBACK_MODELS = ("turbo",)
# Ảnh trả về lớn hơn mức này bị coi là bất thường (ảnh 4096px PNG ~ 20MB).
_MAX_IMAGE_BYTES = 24_000_000

# Tỷ lệ khung → kích thước pixel cho provider text-to-image.
# Cloudflare nhận thẳng ``width``/``height`` (đã kiểm chứng 1024×1024, 896×1120,
# 768×1344 → ảnh ra ĐÚNG kích thước yêu cầu), nên một bảng dùng chung cho mọi
# provider còn lại.
ASPECT_DIMS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:5": (896, 1120),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}


@dataclass(frozen=True)
class ImageGenResult:
    """Kết quả sinh ảnh."""

    ok: bool
    image_bytes: bytes = b""
    image_mime: str = "image/png"
    provider: str = ""
    model: str = ""
    error: str = ""
    text: str = ""


def image_edit_available() -> tuple[bool, str]:
    """Chế độ "AI sửa ảnh thật" có chạy được không, kèm lý do nếu không.

    Hai provider khiến chế độ này CHẮC CHẮN chạy, theo thứ tự chất lượng/chi phí:
      1. **Cloudflare Workers AI** — miễn phí 10.000 neurons/ngày (≈80–95 ảnh).
      2. **Pollinations Gen** — miễn phí, lấy key nhanh (đăng nhập GitHub).

    Cố ý KHÔNG tính GEMINI_API_KEY: model ảnh Gemini trên free tier trả 429
    (``docs/THIRD_PARTY.md``: limit=0), nên bật chế độ này vì nó là mời người
    dùng chọn một nút mà mọi lượt bấm đều hỏng. ``edit_image`` vẫn thử Gemini ở
    cuối chuỗi như cứu cánh cho ai có quota trả phí — chỉ không dùng làm cổng.

    Hàm chỉ đọc biến môi trường, KHÔNG gọi mạng, nên UI gọi được lúc mở form.
    """
    if _cf_ready() is not None:
        return True, ""
    ensure_dotenv()
    if os.environ.get(_POLLINATIONS_KEY_ENV, "").strip():
        return True, ""
    return False, (
        "Chưa có khoá để AI sửa ảnh thật. Cách nhanh nhất: tạo tài khoản Cloudflare "
        "(miễn phí, không cần thẻ) tại https://dash.cloudflare.com → Workers AI → "
        "“Use REST API” → copy Account ID và API token, rồi dán vào "
        "CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN trong .env (được ≈80 ảnh/ngày). "
        "Trong lúc chờ, dùng chế độ “Giữ nguyên sản phẩm, AI chỉ vẽ nền” — chế độ "
        "này chạy được ngay."
    )


def _gemini_image(
    *,
    token: str,
    model: str,
    prompt: str,
    timeout_s: float,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
) -> ImageGenResult:
    """Gọi Gemini generateContent và lấy phần ảnh trả về."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: list[dict[str, object]] = []
    if image_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image_mime or "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
    parts.append({"text": prompt})
    payload: dict[str, object] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", _UA)
    req.add_header("x-goog-api-key", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:240]
        return ImageGenResult(ok=False, provider="gemini", model=model, error=f"http_{exc.code}:{detail}")
    except urllib.error.URLError as exc:
        return ImageGenResult(ok=False, provider="gemini", model=model, error=f"net:{exc.reason}")
    except TimeoutError:
        return ImageGenResult(ok=False, provider="gemini", model=model, error="timeout")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ImageGenResult(ok=False, provider="gemini", model=model, error="bad_json_response")

    candidates = data.get("candidates") or []
    if not candidates:
        return ImageGenResult(ok=False, provider="gemini", model=model, error="missing_candidates")
    out_parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text_chunks: list[str] = []
    for part in out_parts:
        inline = part.get("inline_data") or part.get("inlineData")
        if isinstance(inline, dict) and inline.get("data"):
            mime = str(inline.get("mime_type") or inline.get("mimeType") or "image/png")
            try:
                blob = base64.b64decode(str(inline["data"]))
            except (ValueError, TypeError):
                continue
            if blob:
                return ImageGenResult(
                    ok=True,
                    image_bytes=blob,
                    image_mime=mime,
                    provider="gemini",
                    model=model,
                    text="".join(text_chunks),
                )
        if part.get("text"):
            text_chunks.append(str(part["text"]))
    return ImageGenResult(
        ok=False,
        provider="gemini",
        model=model,
        error="no_image_in_response",
        text="".join(text_chunks),
    )


def _pollinations_edit(
    *,
    token: str,
    image_bytes: bytes,
    image_mime: str,
    prompt: str,
    timeout_s: float,
    model: str,
    image_filename: str = "photo.jpg",
) -> ImageGenResult:
    """Sửa ẢNH THẬT qua Pollinations (image-to-image). Ảnh là nguồn, prompt là yêu cầu sửa.

    Dùng ``POST /v1/images/edits`` với ``multipart/form-data`` — API này nhận file
    nhị phân trực tiếp nên không cần upload trung gian lấy URL. Body dựng thủ công
    thay vì dùng thư viện ngoài: repo chỉ phụ thuộc stdlib cho HTTP.
    """
    boundary = "----nhipquan" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def _field(name: str, value: str) -> None:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )

    _field("prompt", prompt[:32000])
    _field("model", model)
    # Ảnh gốc: phần tử quyết định của endpoint này — không có nó là text-to-image.
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
        f'filename="{image_filename}"\r\nContent-Type: {image_mime}\r\n\r\n'.encode()
        + image_bytes
        + b"\r\n"
    )
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)

    req = urllib.request.Request(
        f"{_POLLINATIONS_GEN_BASE}/v1/images/edits", data=body, method="POST"
    )
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _UA)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = _read_limited(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read(600).decode("utf-8", "replace")[:240]
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error=f"http_{exc.code}:{detail}"
        )
    except urllib.error.URLError as exc:
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error=f"net:{exc.reason}"
        )
    except TimeoutError:
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error="timeout"
        )

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error="bad_json_response"
        )
    items = data.get("data") or []
    if not items or not isinstance(items[0], dict):
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error="no_image_in_response"
        )
    first = items[0]

    blob = b""
    b64 = first.get("b64_json")
    if b64:
        try:
            blob = base64.b64decode(str(b64))
        except (ValueError, TypeError):
            return ImageGenResult(
                ok=False, provider="pollinations-edit", model=model, error="bad_base64_image"
            )
    elif first.get("url"):
        # ``response_format`` mặc định là b64_json, nhưng vẫn xử lý URL cho chắc:
        # provider có thể đổi mặc định mà không báo trước.
        try:
            with urllib.request.urlopen(str(first["url"]), timeout=min(timeout_s, 60.0)) as r:  # noqa: S310
                blob = _read_limited(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            # Chỉ bắt lỗi MẠNG. Bắt `Exception` trùm ở đây sẽ che luôn lỗi lập
            # trình (thuộc tính sai, kiểu sai) và biến nó thành "fetch_result_failed"
            # khó lần ra.
            return ImageGenResult(
                ok=False, provider="pollinations-edit", model=model, error="fetch_result_failed"
            )
    if not blob:
        return ImageGenResult(
            ok=False, provider="pollinations-edit", model=model, error="no_image_in_response"
        )
    return ImageGenResult(
        ok=True,
        image_bytes=blob,
        image_mime=_sniff_image_mime(blob),
        provider="pollinations-edit",
        model=model,
    )


def edit_image(
    image_bytes: bytes,
    prompt: str,
    *,
    image_mime: str = "image/jpeg",
    model: str = "",
    timeout_s: float = 180.0,
    image_filename: str = "photo.jpg",
) -> ImageGenResult:
    """Sửa ẢNH THẬT theo prompt (image-to-image) — ảnh là đầu vào, không phải chỉ tham khảo.

    Thứ tự provider: **Cloudflare Workers AI** (miễn phí ~80–95 ảnh/ngày, nhận ảnh
    qua multipart) → Pollinations Gen (miễn phí, cần key) → Gemini image.

    Vì sao KHÔNG có NVIDIA ở đây: ``ai.api.nvidia.com`` chỉ nhận ``example_id`` do
    NVIDIA cấp cho ảnh nội bộ của họ — ảnh người dùng gửi lên bị từ chối
    (``Expected: example_id, got: base64``), kể cả khi tự upload asset lên NVCF
    (S3 trả ``403 SignatureDoesNotMatch``). Cùng lý do đó, NVIDIA cũng không còn
    ở :func:`generate_image` — một provider không làm được image-to-image thì
    không đáng thêm một key nữa phải quản lý. Muốn ghim/đổi model thì đặt
    ``CLOUDFLARE_IMAGE_MODEL`` hoặc ``POLLINATIONS_IMAGE_MODEL`` — không cần sửa code.

    Args:
        image_bytes: Ảnh gốc người dùng tải lên.
        prompt: Yêu cầu sửa bằng tiếng Anh (mô tả ảnh muốn nhận).
        image_mime: MIME của ảnh gốc.
        model: Model image-editing; trống → dùng danh sách mặc định.
        timeout_s: Ngân sách thời gian cho cả lượt gọi.
        image_filename: Tên file trong multipart (một số server cần đuôi đúng loại ảnh).

    Returns:
        ImageGenResult — ok=True kèm ``image_bytes`` là ảnh ĐÃ SỬA.
    """
    ensure_dotenv()
    if not image_bytes:
        return ImageGenResult(ok=False, error="missing_original_image")
    if not prompt.strip():
        return ImageGenResult(ok=False, error="empty_prompt")

    deadline = time.monotonic() + max(10.0, timeout_s)
    last: ImageGenResult | None = None

    # 1. Cloudflare Workers AI — miễn phí theo NGÀY, model hợp nhất generate + edit.
    cf = _cf_ready()
    if cf is not None:
        account, cf_token = cf
        pinned_cf = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "").strip()
        cf_models: list[str] = []
        for name in (pinned_cf, *_CF_MODELS):
            if name and name not in cf_models:
                cf_models.append(name)
        for name in cf_models:
            remaining = deadline - time.monotonic()
            if remaining <= 5.0:
                break
            res = _cf_image_any_field(
                account=account,
                token=cf_token,
                model=name,
                prompt=prompt,
                timeout_s=remaining,
                image_bytes=image_bytes,
                image_mime=image_mime,
                image_filename=image_filename,
            )
            if res.ok:
                return res
            last = res
            err = res.error.lower()
            # Model không tồn tại → thử model kế tiếp; lỗi thật thì nhường provider sau.
            if "http_404" in err or "not found" in err:
                logger.info("cloudflare model %s unavailable, trying next", name)
                continue
            logger.info("cloudflare edit failed (%s)", res.error[:100])
            break

    token = os.environ.get(_POLLINATIONS_KEY_ENV, "").strip()
    if token:
        pinned = os.environ.get("POLLINATIONS_IMAGE_MODEL", "").strip()
        models: list[str] = []
        for name in (pinned, *_POLLINATIONS_EDIT_MODELS):
            if name and name not in models:
                models.append(name)
        for name in models:
            remaining = deadline - time.monotonic()
            if remaining <= 5.0:
                break
            res = _pollinations_edit(
                token=token,
                image_bytes=image_bytes,
                image_mime=image_mime,
                prompt=prompt,
                timeout_s=remaining,
                model=name,
                image_filename=image_filename,
            )
            if res.ok:
                return res
            last = res
            err = res.error.lower()
            # Model không tồn tại → thử model kế tiếp; lỗi thật thì báo luôn.
            if "http_404" in err or "not found" in err:
                logger.info("pollinations edit model %s unavailable, trying next", name)
                continue
            logger.info("pollinations edit failed (%s)", res.error[:80])
            break

    gemini = os.environ.get(_KEY_ENV["gemini"], "").strip()
    if gemini:
        preferred = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
        names: list[str] = []
        for name in (preferred, *_IMAGE_MODELS):
            if name and name not in names:
                names.append(name)
        for name in names:
            remaining = deadline - time.monotonic()
            if remaining <= 5.0:
                break
            res = _gemini_image(
                token=gemini,
                model=name,
                prompt=prompt,
                timeout_s=remaining,
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
            if res.ok:
                return res
            last = res
            err = res.error.lower()
            if "http_404" in err or "not found" in err:
                continue
            break

    if last is None:
        return ImageGenResult(
            ok=False,
            error="thieu_key_sua_anh",
            text=(
                "Cần CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN (miễn phí tại "
                "https://dash.cloudflare.com → Workers AI → “Use REST API”), "
                "hoặc POLLINATIONS_API_KEY (miễn phí tại https://enter.pollinations.ai/keys), "
                "hoặc GEMINI_API_KEY có quota để AI sửa ảnh thật."
            ),
        )
    return last


def _cf_ready() -> tuple[str, str] | None:
    """``(account_id, token)`` khi đã cấu hình Cloudflare; ``None`` khi chưa.

    Cần CẢ HAI biến: account id nằm trong đường dẫn API, token nằm ở header.
    Thiếu một trong hai thì provider không dùng được (khác mọi provider chỉ cần
    một key).
    """
    ensure_dotenv()
    account = os.environ.get(_CF_ACCOUNT_ENV, "").strip()
    token = os.environ.get(_CF_TOKEN_ENV, "").strip()
    if not account or not token:
        return None
    return account, token


def _cf_image(
    *,
    account: str,
    token: str,
    model: str,
    prompt: str,
    timeout_s: float,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    image_filename: str = "photo.jpg",
    image_field: str = "input_image_0",
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
) -> ImageGenResult:
    """Gọi Workers AI bằng ``multipart/form-data`` và lấy ảnh base64 trả về.

    Dùng multipart cho CẢ hai chiều (sinh mới và sửa ảnh): ``flux-2-klein-4b``
    khai báo input là ``multipart`` (bắt buộc) nên gửi JSON sẽ bị từ chối. Không
    có ``image_bytes`` thì đây là text-to-image.

    ``image_field`` là TÊN TRƯỜNG chứa ảnh. Quy ước của Cloudflare cho model
    nhiều ảnh tham chiếu là ``input_image_0``, ``input_image_1``…; bản cũ hơn
    dùng ``image``. Vì tài liệu không nêu tên trường, hàm này nhận tên từ ngoài
    để ``_cf_image_with_fallback_fields`` thử lần lượt.

    ``width``/``height``/``seed`` bỏ trống thì không gửi — model tự chọn kích
    thước (ra 1024×1024). Truyền vào để giữ đúng tỷ lệ khung người dùng chọn
    (đã kiểm chứng 896×1120 và 768×1344 đều được chấp nhận).
    """
    url = f"{_CF_BASE}/{account}/ai/run/{model}"
    boundary = "----nhipquan" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def _field(name: str, value: str) -> None:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )

    _field("prompt", prompt[:2048])
    if width is not None and height is not None:
        _field("width", str(width))
        _field("height", str(height))
    if seed is not None:
        _field("seed", str(seed))
    if image_bytes:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{image_field}"; '
            f'filename="{image_filename}"\r\nContent-Type: {image_mime}\r\n\r\n'.encode()
            + image_bytes
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(url, data=b"".join(chunks), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _UA)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = _read_limited(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read(600).decode("utf-8", "replace")[:300]
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error=f"http_{exc.code}:{detail}"
        )
    except urllib.error.URLError as exc:
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error=f"net:{exc.reason}"
        )
    except TimeoutError:
        return ImageGenResult(ok=False, provider="cloudflare", model=model, error="timeout")

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error="bad_json_response"
        )
    if not data.get("success", True):
        errs = data.get("errors") or []
        codes = ",".join(str(e.get("code") or "") for e in errs if isinstance(e, dict))
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error=f"cf_error:{codes}"
        )
    result = data.get("result") or {}
    b64 = ""
    if isinstance(result, dict):
        b64 = str(result.get("image") or "")
    elif isinstance(result, str):
        # Một số model trả thẳng chuỗi base64 trong ``result``.
        b64 = result
    if not b64:
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error="no_image_in_response"
        )
    try:
        blob = base64.b64decode(b64)
    except (ValueError, TypeError):
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error="bad_base64_image"
        )
    if not blob:
        return ImageGenResult(
            ok=False, provider="cloudflare", model=model, error="no_image_in_response"
        )
    return ImageGenResult(
        ok=True,
        image_bytes=blob,
        image_mime=_sniff_image_mime(blob),
        provider="cloudflare",
        model=model,
    )


def _cf_image_any_field(
    *,
    account: str,
    token: str,
    model: str,
    prompt: str,
    timeout_s: float,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    image_filename: str = "photo.jpg",
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
) -> ImageGenResult:
    """Thử lần lượt các tên trường ảnh cho tới khi Cloudflare chấp nhận.

    Tài liệu Cloudflare KHÔNG nêu tên trường cho ảnh tham chiếu, nên cứng một tên
    là rủi ro (sai tên → lỗi 400 dù mọi thứ khác đúng). Lần thử chỉ tốn một lượt
    validation rẻ, không tính neurons khi bị từ chối.

    Không có ``image_bytes`` thì chỉ có MỘT lượt gọi (không có tên trường nào để
    dò) — đây là đường text-to-image.
    """
    if not image_bytes:
        return _cf_image(
            account=account,
            token=token,
            model=model,
            prompt=prompt,
            timeout_s=timeout_s,
            width=width,
            height=height,
            seed=seed,
        )
    last: ImageGenResult | None = None
    for field in _CF_IMAGE_FIELDS:
        res = _cf_image(
            account=account,
            token=token,
            model=model,
            prompt=prompt,
            timeout_s=timeout_s,
            image_bytes=image_bytes,
            image_mime=image_mime,
            image_filename=image_filename,
            image_field=field,
            width=width,
            height=height,
            seed=seed,
        )
        if res.ok:
            logger.info("cloudflare accepted image field %r", field)
            return res
        last = res
        # Chỉ thử tên khác khi lỗi là "sai/thiếu trường" (400/422). Lỗi khác
        # (401 hết quyền, 429 hết hạn mức) thì đổi tên trường cũng vô ích.
        err = res.error.lower()
        if not ("http_400" in err or "http_422" in err):
            return res
    return last or ImageGenResult(
        ok=False, provider="cloudflare", error="no_image_in_response"
    )


def _sniff_image_mime(blob: bytes) -> str:
    """MIME từ magic bytes — không tin header vì provider không phải lúc nào cũng gửi kèm."""
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _pollinations_image(
    *,
    prompt: str,
    timeout_s: float,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    attempts: int = 3,
) -> ImageGenResult:
    """Sinh ảnh qua Pollinations (text-to-image, miễn phí, không cần key).

    Retry khi gặp 429/500 vì endpoint cộng đồng hay bị rate-limit tạm thời, NHƯNG
    tổng thời gian bị chặn bởi ``timeout_s``: hết ngân sách thì dừng ngay, thay
    vì cộng dồn ``attempts × timeout`` (đó là nguyên nhân chính của "gen ảnh lâu"
    — 3 lần × 90 giây = 270 giây cho một lần bấm).
    """
    encoded = urllib.parse.quote(prompt[:1500])
    primary = os.environ.get("POLLINATIONS_MODEL", "flux").strip() or "flux"
    # Chỉ thử model dự phòng khi người dùng CHƯA ghim model tường minh: nếu họ đã
    # chọn model, đổi model sau lưng họ sẽ ra ảnh khác phong cách.
    pinned = bool(os.environ.get("POLLINATIONS_MODEL", "").strip())
    models = [primary] if pinned else [primary, *_POLLINATIONS_FALLBACK_MODELS]

    deadline = time.monotonic() + max(5.0, timeout_s)
    last: ImageGenResult | None = None
    for model in models:
        remaining = deadline - time.monotonic()
        if remaining <= 3.0:
            break
        last = _pollinations_try(
            encoded=encoded,
            model=model,
            width=width,
            height=height,
            seed=seed,
            timeout_s=remaining,
            attempts=attempts,
            deadline=deadline,
        )
        if last.ok:
            return last
    return last or ImageGenResult(ok=False, provider="pollinations", error="no_image_in_response")


def _pollinations_try(
    *,
    encoded: str,
    model: str,
    width: int,
    height: int,
    seed: int | None,
    timeout_s: float,
    attempts: int,
    deadline: float,
) -> ImageGenResult:
    """Một model Pollinations, tối đa ``attempts`` lần, tôn trọng ``deadline``."""
    last: ImageGenResult | None = None
    for attempt in range(max(1, attempts)):
        remaining = deadline - time.monotonic()
        if remaining <= 3.0:
            break
        params = {
            "width": str(width),
            "height": str(height),
            "nologo": "true",
            "model": model,
        }
        if seed is not None:
            # Đổi seed mỗi lần retry để tránh cache lỗi.
            params["seed"] = str(seed + attempt)
        url = f"{_POLLINATIONS_BASE}/{encoded}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", _UA)
        try:
            with urllib.request.urlopen(req, timeout=min(remaining, timeout_s)) as resp:  # noqa: S310
                blob = _read_limited(resp)
                mime = resp.headers.get("Content-Type") or "image/jpeg"
        except urllib.error.HTTPError as exc:
            detail = exc.read(600).decode("utf-8", "replace")[:240]
            last = ImageGenResult(
                ok=False, provider="pollinations", model=model, error=f"http_{exc.code}:{detail}"
            )
            if exc.code in (429, 500, 502, 503, 504):
                continue
            return last
        except urllib.error.URLError as exc:
            last = ImageGenResult(
                ok=False, provider="pollinations", model=model, error=f"net:{exc.reason}"
            )
            continue
        except TimeoutError:
            last = ImageGenResult(ok=False, provider="pollinations", model=model, error="timeout")
            continue
        if not blob or not mime.startswith("image/"):
            last = ImageGenResult(
                ok=False, provider="pollinations", model=model, error="no_image_in_response"
            )
            continue
        return ImageGenResult(
            ok=True,
            image_bytes=blob,
            image_mime=mime.split(";")[0].strip(),
            provider="pollinations",
            model=model,
        )
    return last or ImageGenResult(
        ok=False, provider="pollinations", model=model, error="no_image_in_response"
    )


def _read_limited(resp: object, limit: int = _MAX_IMAGE_BYTES) -> bytes:
    """Đọc thân response nhưng chặn trên ``limit`` byte.

    Không chặn thì một response lỗi khổng lồ (hoặc stream không bao giờ kết thúc)
    giữ request mở tới hết timeout dù dữ liệu đã vô nghĩa.
    """
    read = getattr(resp, "read", None)
    if not callable(read):
        return b""
    try:
        raw = read(limit + 1)
    except TypeError:
        # Đối tượng read() không nhận tham số kích thước (response giả trong test,
        # một số wrapper). Đọc hết rồi tự cắt.
        raw = read()
    if not isinstance(raw, bytes):
        return b""
    if len(raw) > limit:
        logger.info("pollinations response exceeded %d bytes, truncating", limit)
        return raw[:limit]
    return raw


def generate_image(
    prompt: str,
    *,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
    timeout_s: float = 45.0,
    aspect_ratio: str = "1:1",
    seed: int | None = None,
) -> ImageGenResult:
    """Sinh ảnh từ prompt (tuỳ chọn kèm ảnh gốc để redesign).

    Thứ tự provider: **Cloudflare Workers AI** (miễn phí ~80–95 ảnh/ngày, không
    cần thẻ) → Gemini image (nếu có key + quota) → Pollinations (miễn phí, không
    cần key).

    Cloudflare đứng đầu vì nó là provider DUY NHẤT trong ba vừa miễn phí bền
    vững vừa nhận cả ảnh gốc lẫn ``width``/``height``. NVIDIA đã bỏ hẳn: nó
    không nhận ảnh người dùng nên chỉ làm được một nửa việc mà vẫn là một key
    nữa phải quản lý.

    Args:
        prompt: Prompt tiếng Anh mô tả ảnh cần tạo.
        image_bytes: Ảnh gốc (nếu muốn redesign theo ảnh thật). Cloudflare dùng
            trường này — ảnh gửi kèm trong multipart, không cần upload trung gian.
        image_mime: MIME của ảnh gốc.
        timeout_s: NGÂN SÁCH THỜI GIAN tổng cho cả lượt gọi (không phải timeout
            cho từng request) — hết ngân sách thì dừng, không retry thêm.
        aspect_ratio: "1:1" | "4:5" | "9:16" | "16:9".
        seed: Seed cố định để tái lập kết quả.

    Returns:
        ImageGenResult — ok=True kèm image_bytes khi thành công.
    """
    ensure_dotenv()
    if not prompt.strip():
        return ImageGenResult(ok=False, error="empty_prompt")

    width, height = ASPECT_DIMS.get(aspect_ratio, (1024, 1024))
    deadline = time.monotonic() + max(5.0, timeout_s)

    # Seed: provider cần giá trị cụ thể. Không truyền → sinh ngẫu nhiên để hai
    # lần bấm "tạo ảnh" liên tiếp không ra cùng một ảnh.
    fixed_seed = seed if seed is not None else random.randint(0, _MAX_SEED)
    # ``seed`` cũng phải nằm trong khoảng model chấp nhận (đã thử 3e9 vẫn OK,
    # nhưng giữ dưới 2^31 để an toàn với mọi backend).
    fixed_seed = max(0, min(_MAX_SEED, int(fixed_seed)))

    cf = _cf_ready()
    if cf is not None:
        account, cf_token = cf
        pinned_cf = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "").strip()
        cf_models: list[str] = []
        for name in (pinned_cf, *_CF_MODELS):
            if name and name not in cf_models:
                cf_models.append(name)
        for name in cf_models:
            remaining = deadline - time.monotonic()
            if remaining <= 5.0:
                break
            res = _cf_image_any_field(
                account=account,
                token=cf_token,
                model=name,
                prompt=prompt,
                timeout_s=remaining,
                image_bytes=image_bytes,
                image_mime=image_mime or "image/jpeg",
                width=width,
                height=height,
                seed=fixed_seed,
            )
            if res.ok:
                return res
            # Model không tồn tại → thử model kế tiếp; lỗi thật thì nhường
            # provider sau (Gemini → Pollinations) thay vì bỏ cuộc.
            err = res.error.lower()
            if "http_404" in err or "not found" in err:
                logger.info("cloudflare model %s unavailable, trying next", name)
                continue
            logger.info("cloudflare generate failed (%s), falling back", res.error[:100])
            break

    token = os.environ.get(_KEY_ENV["gemini"], "").strip()
    if token:
        preferred = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
        models: list[str] = []
        for name in (preferred, *_IMAGE_MODELS):
            if name and name not in models:
                models.append(name)
        for model in models:
            remaining = deadline - time.monotonic()
            if remaining <= 5.0:
                break
            res = _gemini_image(
                token=token,
                model=model,
                prompt=prompt,
                timeout_s=remaining,
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
            if res.ok:
                return res
            err = res.error.lower()
            # Model không tồn tại / không hỗ trợ → thử model kế tiếp.
            if "http_404" in err or "not found" in err or "not supported" in err:
                continue
            # 429 (hết quota) / 400 / lỗi khác → rơi xuống Pollinations.
            logger.info("Gemini image unavailable (%s), falling back to pollinations", res.error[:80])
            break

    return _pollinations_image(
        prompt=prompt,
        timeout_s=max(5.0, deadline - time.monotonic()),
        width=width,
        height=height,
        seed=fixed_seed,
    )