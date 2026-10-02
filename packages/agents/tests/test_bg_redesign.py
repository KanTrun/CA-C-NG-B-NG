# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test offline cho ca_agents.bg_redesign — không gọi mạng thật.

Fixture ``_clear_bg_cache`` (autouse) chặn cả Cloudflare lẫn xoá cache, nên mọi
test ở đây chạy kín dù máy có key Cloudflare thật. Từng test tự patch tiếp
``complete`` (vision bbox + bg prompt) và ``_pollinations_image`` (sinh nền).
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from ca_agents import bg_redesign
from ca_agents.bg_redesign import (
    _background_is_usable,
    _cover_resize,
    _grow_background,
    _premultiplied_resize,
    _subject_alpha,
    _tight_crop,
    build_background_prompt,
    generate_background_redesign,
)
from ca_agents.image_gen import ImageGenResult
from ca_agents.llm import LlmResult
from ca_agents.menu_style import parse_style
from PIL import Image

PROMPT = (
    "fresh iced tea with orange slice on a wooden cafe table, "
    "warm morning light, professional beverage photography"
)


@pytest.fixture(autouse=True)
def _clear_bg_cache(monkeypatch):
    """Cách ly mọi test khỏi mạng và khỏi cache của tiến trình.

    Hai việc, cả hai đều bắt buộc:

    1. **Xoá cache nền** (``_BG_CACHE`` là biến module) để test này không nhận
       ảnh của test trước.
    2. **Chặn Cloudflare**. ``_generate_background`` thử Cloudflare trước rồi mới
       tới Pollinations. Chặn ở ``_cf_ready`` (trả ``None`` = "chưa cấu hình")
       thay vì xoá biến môi trường, vì ``_cf_ready`` có gọi ``ensure_dotenv()`` —
       hàm này NẠP LẠI key từ ``.env`` của máy đang chạy, nên xoá biến là không
       đủ. Chặn thêm ``_cf_image_any_field`` làm lưới an toàn: test nào lỡ bật
       Cloudflare mà quên giả lập provider sẽ đỏ ngay chứ không âm thầm gọi mạng
       thật (nền AI sinh ra làm phép đo tỷ lệ chủ thể sai ngẫu nhiên).
    """
    bg_redesign._BG_CACHE.clear()
    monkeypatch.setattr(bg_redesign, "_cf_ready", lambda: None)
    monkeypatch.setattr(
        bg_redesign,
        "_cf_image_any_field",
        lambda **_: pytest.fail("test gọi mạng Cloudflare thật"),
    )
    yield
    bg_redesign._BG_CACHE.clear()


def _llm_ok(text: str) -> LlmResult:
    return LlmResult(ok=True, text=text, provider="fake", reason="test")


def _fake_bg_bytes(color: tuple[int, int, int] = (20, 30, 40)) -> bytes:
    """Nền giả có gradient + texture nhẹ.

    Không dùng ảnh MỘT MÀU vì ``_background_is_usable`` (đúng thiết kế) từ chối
    nền phẳng — đó là dấu hiệu provider trả ảnh lỗi trong thực tế.
    """
    arr = np.zeros((1024, 1024, 3), dtype=np.float32)
    base = np.array(color, dtype=np.float32)
    # Gradient chéo + vệt bokeh để có độ lệch chuẩn thực tế (std > 6).
    yy, xx = np.mgrid[0:1024, 0:1024]
    ramp = ((xx + yy) / 2046.0)[..., None]
    arr[:] = base * (0.55 + 0.85 * ramp)
    arr += 14.0 * np.sin(xx / 37.0)[..., None]
    arr += 9.0 * np.cos(yy / 53.0)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _synthetic_drink() -> bytes:
    """Nền trắng đồng nhất + 'ly' hình chữ nhật màu nâu đậm ở giữa."""
    img = Image.new("RGB", (300, 400), (250, 250, 250))
    arr = np.asarray(img).copy()
    arr[120:340, 90:210] = (90, 45, 20)  # thân ly
    arr[110:125, 85:215] = (60, 30, 12)  # nắp
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def patch_llm(monkeypatch):
    """complete() → bbox đầy đủ + bg prompt hợp lệ (không gọi mạng)."""

    def fake_complete(*, task: str = "", json_mode: bool = False, **kwargs):
        if task == "vision:bg_redesign_bbox":
            return _llm_ok('{"x1": 0.2, "y1": 0.25, "x2": 0.8, "y2": 0.9}')
        if task == "bg_redesign:prompt":
            return _llm_ok(
                '{"background_prompt_en": "rustic wooden table surface, '
                'soft golden bokeh cafe interior, empty scene"}'
            )
        return _llm_ok("{}")

    monkeypatch.setattr(bg_redesign, "complete", fake_complete)


@pytest.fixture
def patch_pollinations(monkeypatch):
    """Chặn MẠNG ở provider sinh nền thứ hai (Cloudflare đã chặn ở fixture chung).

    ``_generate_background`` thử Cloudflare trước rồi mới tới Pollinations.
    Fixture autouse ``_clear_bg_cache`` ép Cloudflare trả ``None`` nên luồng rơi
    thẳng xuống Pollinations giả dưới đây; test nào cần Cloudflare thật thì patch
    lại sau fixture.
    """
    calls: list[dict] = []

    def fake_pollinations(*, prompt: str, width: int, height: int, seed, timeout_s, attempts=3):
        calls.append({"prompt": prompt, "width": width, "height": height, "seed": seed})
        return ImageGenResult(
            ok=True,
            image_bytes=_fake_bg_bytes(),
            image_mime="image/jpeg",
            provider="pollinations",
            model="flux",
        )

    monkeypatch.setattr(bg_redesign, "_pollinations_image", fake_pollinations)
    return calls


class TestGuards:
    def test_missing_original(self):
        res = generate_background_redesign(b"", PROMPT)
        assert not res.ok
        assert res.error == "missing_original_image"

    def test_empty_prompt(self, patch_llm):
        res = generate_background_redesign(_synthetic_drink(), "   ")
        assert not res.ok
        assert res.error == "empty_prompt"

    def test_invalid_image(self, patch_llm):
        res = generate_background_redesign(b"not an image at all", PROMPT)
        assert not res.ok
        assert res.error == "invalid_original_image"

    def test_too_small(self, patch_llm):
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (200, 100, 50)).save(buf, format="PNG")
        res = generate_background_redesign(buf.getvalue(), PROMPT)
        assert not res.ok
        assert res.error == "original_too_small"


class TestSegmentation:
    def test_grow_background_finds_white_border(self):
        arr = np.asarray(Image.open(io.BytesIO(_synthetic_drink())), dtype=np.float32)
        h, w = arr.shape[:2]
        seed = np.zeros((h, w), dtype=bool)
        seed[:3, :] = seed[-3:, :] = seed[:, :3] = seed[:, -3:] = True
        bg = _grow_background(arr, seed, 28.0)
        # Vùng nền phải chiếm đa số và KHÔNG ăn vào thân ly màu nâu.
        assert bg.mean() > 0.6
        assert not bg[200, 150]

    def test_subject_alpha_covers_drink(self):
        img = Image.open(io.BytesIO(_synthetic_drink()))
        alpha = _subject_alpha(img, None)
        assert alpha is not None
        # Tâm ly phải thuộc chủ thể, góc ảnh phải là nền.
        assert alpha[230, 150] > 0.9
        assert alpha[5, 5] < 0.1

    def test_uniform_image_fails_closed(self, patch_llm, patch_pollinations):
        """Ảnh một màu → không tách chủ thể tin cậy → segment_failed, không bịa ảnh.

        Nền và vision chạy SONG SONG nên request nền có thể đã được gửi trước khi
        biết tách chủ thể thất bại; điều bắt buộc là KHÔNG trả ảnh, và có thoát
        sớm (không chờ hết thời gian tải nền).
        """
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (120, 120, 120)).save(buf, format="PNG")
        res = generate_background_redesign(buf.getvalue(), PROMPT)
        assert not res.ok
        assert res.error == "segment_failed"
        # Câu hướng dẫn phải khớp NHÃN của chế độ trên UI ("giữ nguyên sản phẩm"),
        # không phải tên cũ ("giữ nguyên ly nước") — chế độ này chạy cho mọi bao bì
        # đựng chất lỏng (chai/lọ/bình/hộp/túi), không riêng ly.
        assert "giữ nguyên sản phẩm" in res.text
        # Thoát sớm: tối đa 1 request nền (không retry seed thứ hai).
        assert len(patch_pollinations) <= 1

    def test_tight_crop_shrinks(self):
        img = Image.open(io.BytesIO(_synthetic_drink())).convert("RGBA")
        alpha = _subject_alpha(img.convert("RGB"), None)
        assert alpha is not None
        cropped, crop_alpha = _tight_crop(img, alpha)
        assert cropped.size[0] < img.size[0]
        assert cropped.size[1] < img.size[1]
        assert crop_alpha.shape[:2] == (cropped.size[1], cropped.size[0])


class TestHappyPath:
    def test_composite_ok_and_png(self, patch_llm, patch_pollinations):
        raw = _synthetic_drink()
        res = generate_background_redesign(raw, PROMPT, original_mime="image/png", seed=5)
        assert res.ok, res.error
        assert res.provider == "local-composite"
        assert res.image_mime == "image/png"
        assert res.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        out = Image.open(io.BytesIO(res.image_bytes))
        assert out.size == (1024, 1024)
        assert len(patch_pollinations) == 1
        call = patch_pollinations[0]
        assert call["seed"] == 5
        # Prompt nền phải được phủ định "no drink" và không chứa từ mô tả ly.
        assert "no drink" in call["prompt"]
        assert "iced tea" not in call["prompt"]

    def test_aspect_ratio_dims(self, patch_llm, patch_pollinations):
        generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png", aspect_ratio="9:16"
        )
        call = patch_pollinations[0]
        assert (call["width"], call["height"]) == (768, 1344)

    def test_model_reports_real_bg_provider(self, patch_llm, patch_pollinations):
        """``model`` phải nói provider THẬT đã sinh nền, không phải nhãn cứng.

        Trước đây ghi cứng ``"pollinations-bg+pillow"``, nên khi Cloudflare (hoặc
        nguồn khác) sinh nền thì người vận hành vẫn tưởng Pollinations làm — dẫn
        tới sửa sai cấu hình khi ảnh nền ra xấu.
        """
        res = generate_background_redesign(_synthetic_drink(), PROMPT, original_mime="image/png")
        assert res.ok, res.error
        assert res.model == "pollinations-bg+pillow"

    def test_model_reports_cloudflare_when_cloudflare_used(self, patch_llm, monkeypatch):
        """Cloudflare sinh nền → ``model`` phải ghi ``cloudflare-bg+pillow``."""

        def fake_cf(*, prompt, timeout_s, seed, width, height):
            return ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="cloudflare",
                model="@cf/black-forest-labs/flux-2-klein-4b",
            )

        monkeypatch.setattr(bg_redesign, "_cloudflare_background", fake_cf)
        res = generate_background_redesign(_synthetic_drink(), PROMPT, original_mime="image/png")
        assert res.ok, res.error
        assert res.model == "cloudflare-bg+pillow"

    def test_drink_pixels_preserved(self, patch_llm, patch_pollinations):
        """Lõi ly phải giữ ĐÚNG màu gốc (không qua model), nền mới nằm ngoài ly."""
        raw = _synthetic_drink()
        res = generate_background_redesign(raw, PROMPT, original_mime="image/png")
        assert res.ok, res.error
        out = np.asarray(Image.open(io.BytesIO(res.image_bytes)).convert("RGB"))
        # Thân ly nâu (90,45,20): còn hàng nghìn pixel đúng màu, dung sai ±6.
        drink = (
            (np.abs(out[:, :, 0].astype(int) - 90) <= 6)
            & (np.abs(out[:, :, 1].astype(int) - 45) <= 6)
            & (np.abs(out[:, :, 2].astype(int) - 20) <= 6)
        )
        assert drink.sum() > 3000
        # Góc ảnh là nền mới (gradient xanh đậm 20/30/40 phủ lên nền gốc trắng):
        # ảnh gốc có nền TRẮNG, nên nếu còn pixel trắng đục ở góc thì nền cũ chưa
        # được thay. Cho phép ám sáng nhẹ từ vignette/hào quang.
        corner = out[:120, :120].reshape(-1, 3).astype(float)
        assert corner.mean(axis=0).max() < 150

    def test_background_provider_error_passthrough(self, patch_llm, monkeypatch):
        def fail_pollinations(**kwargs):
            return ImageGenResult(ok=False, provider="pollinations", error="http_503")

        monkeypatch.setattr(bg_redesign, "_pollinations_image", fail_pollinations)
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png"
        )
        assert not res.ok
        assert res.error == "http_503"
        assert res.provider == "pollinations"
        # Thông báo cho người dùng phải nói rõ nền không dùng được + gợi ý bấm lại.
        assert "Tạo lại ảnh khác" in res.text

    def test_llm_outage_still_works(self, monkeypatch, patch_pollinations):
        """Vision/LLM lỗi → bbox prior bỏ qua, bg prompt dùng fallback, vẫn có ảnh."""

        def fake_complete(*, task: str = "", **kwargs):
            return LlmResult(ok=False, text="", provider="replay", reason="no_provider")

        monkeypatch.setattr(bg_redesign, "complete", fake_complete)
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png"
        )
        assert res.ok, res.error
        assert "cozy" in patch_pollinations[0]["prompt"].lower() or "cafe" in patch_pollinations[0]["prompt"].lower()

    def test_flat_background_rejected_then_retried(self, patch_llm, monkeypatch):
        """Nền một màu (ảnh lỗi) bị từ chối; lần thử lại với seed khác cho ảnh tốt."""
        calls: list[int | None] = []

        def fake_pollinations(*, prompt, width, height, seed, timeout_s, attempts=3):
            calls.append(seed)
            if len(calls) == 1:
                buf = io.BytesIO()
                Image.new("RGB", (512, 512), (128, 128, 128)).save(buf, format="JPEG")
                return ImageGenResult(
                    ok=True,
                    image_bytes=buf.getvalue(),
                    image_mime="image/jpeg",
                    provider="pollinations",
                    model="flux",
                )
            return ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="pollinations",
                model="flux",
            )

        monkeypatch.setattr(bg_redesign, "_pollinations_image", fake_pollinations)
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png", seed=100
        )
        assert res.ok, res.error
        # Lần thử lại phải dùng seed KHÁC để không nhận đúng ảnh lỗi từ cache.
        assert len(calls) == 2
        assert calls[0] != calls[1]


class TestCloudflareBackground:
    """Cloudflare là provider sinh nền ĐẦU TIÊN (rẻ, hạn mức rõ ràng)."""

    def test_cloudflare_used_before_pollinations(self, patch_llm, monkeypatch):
        """Có key Cloudflare → dùng ngay, không đụng Pollinations."""
        cf_calls: list[dict] = []

        def fake_cf(*, prompt, timeout_s, seed, width, height):
            cf_calls.append(
                {"prompt": prompt, "seed": seed, "width": width, "height": height}
            )
            return ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="cloudflare",
                model="@cf/black-forest-labs/flux-2-klein-4b",
            )

        monkeypatch.setattr(bg_redesign, "_cloudflare_background", fake_cf)
        pollinations_calls: list[dict] = []

        def fake_pollinations(**kwargs):
            pollinations_calls.append(kwargs)
            raise AssertionError("Pollinations không được gọi khi Cloudflare đã chạy")

        monkeypatch.setattr(bg_redesign, "_pollinations_image", fake_pollinations)
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png"
        )

        assert res.ok, res.error
        assert len(cf_calls) == 1
        assert not pollinations_calls
        # Kích thước nền phải khớp khung đích để ``_cover_resize`` crop đúng.
        assert cf_calls[0]["width"] > 0 and cf_calls[0]["height"] > 0
    def test_cloudflare_failure_falls_back_to_pollinations(
        self, patch_llm, patch_pollinations, monkeypatch
    ):
        """Cloudflare lỗi thật (hết neurons/ngày) → Pollinations vẫn phải ra ảnh.

        Hai nguồn độc lập: hết hạn mức Cloudflare là chuyện bình thường mỗi ngày.
        """

        def fake_cf(**kwargs):
            return ImageGenResult(
                ok=False,
                provider="cloudflare",
                error="http_429:quota exceeded",
            )

        monkeypatch.setattr(bg_redesign, "_cloudflare_background", fake_cf)
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png"
        )

        assert res.ok, res.error
        assert len(patch_pollinations) >= 1

    def test_cloudflare_absent_falls_back_to_pollinations(
        self, patch_llm, patch_pollinations
    ):
        """Không cấu hình Cloudflare (fixture trả None) → Pollinations làm việc."""
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png"
        )
        assert res.ok, res.error
        assert len(patch_pollinations) == 1

    def test_cloudflare_background_sends_dims_and_seed(self, monkeypatch):
        """``_cloudflare_background`` truyền đủ kích thước + seed xuống provider.

        Thiếu width/height thì Cloudflare trả ảnh vuông 1024×1024, và
        ``_cover_resize`` phải crop mạnh — mất chi tiết nền ở khung dọc.
        """
        monkeypatch.setattr(bg_redesign, "_cf_ready", lambda: ("acc-123", "cf-token"))
        seen: list[dict] = []

        def fake_cf_image_any_field(**kwargs):
            seen.append(kwargs)
            return ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="cloudflare",
                model=kwargs["model"],
            )

        monkeypatch.setattr(bg_redesign, "_cf_image_any_field", fake_cf_image_any_field)
        res = bg_redesign._cloudflare_background(
            prompt="wooden table", timeout_s=30.0, seed=7, width=896, height=1120
        )

        assert res is not None and res.ok
        assert seen[0]["width"] == 896
        assert seen[0]["height"] == 1120
        assert seen[0]["seed"] == 7
        assert seen[0]["account"] == "acc-123"
        assert seen[0]["token"] == "cf-token"

    def test_cloudflare_background_without_key_returns_none(self):
        """Chưa cấu hình → None (không phải lỗi), để luồng thử Pollinations.

        Fixture autouse đã ép ``_cf_ready`` trả None — đúng trạng thái "chưa có
        key" mà test này cần kiểm chứng.
        """
        res = bg_redesign._cloudflare_background(
            prompt="wooden table", timeout_s=30.0, seed=None, width=1024, height=1024
        )
        assert res is None

    def test_cloudflare_env_model_pinned(self, monkeypatch):
        """``CLOUDFLARE_IMAGE_MODEL`` cho phép ghim model cho cả nền."""
        monkeypatch.setattr(bg_redesign, "_cf_ready", lambda: ("acc-123", "cf-token"))
        monkeypatch.setenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-dev")
        seen: list[str] = []

        def fake_cf_image_any_field(**kwargs):
            seen.append(kwargs["model"])
            return ImageGenResult(
                ok=True, image_bytes=_fake_bg_bytes(), image_mime="image/jpeg",
                provider="cloudflare", model=kwargs["model"],
            )

        monkeypatch.setattr(bg_redesign, "_cf_image_any_field", fake_cf_image_any_field)
        bg_redesign._cloudflare_background(
            prompt="wooden table", timeout_s=30.0, seed=None, width=1024, height=1024
        )

        assert seen[0] == "@cf/black-forest-labs/flux-2-dev"

    def test_cloudflare_background_default_model_is_klein(self, monkeypatch):
        """Mặc định dùng ``klein-4b`` (rẻ) chứ không phải ``dev`` (đắt)."""
        monkeypatch.setattr(bg_redesign, "_cf_ready", lambda: ("acc-123", "cf-token"))
        monkeypatch.delenv("CLOUDFLARE_IMAGE_MODEL", raising=False)
        seen: list[str] = []

        def fake_cf_image_any_field(**kwargs):
            seen.append(kwargs["model"])
            return ImageGenResult(
                ok=True, image_bytes=_fake_bg_bytes(), image_mime="image/jpeg",
                provider="cloudflare", model=kwargs["model"],
            )

        monkeypatch.setattr(bg_redesign, "_cf_image_any_field", fake_cf_image_any_field)
        bg_redesign._cloudflare_background(
            prompt="wooden table", timeout_s=30.0, seed=None, width=1024, height=1024
        )

        assert seen[0] == bg_redesign._CF_BG_MODEL
        assert "klein" in seen[0]

    def test_cloudflare_background_skips_when_no_time_budget(self, monkeypatch):
        """Ngân sách thời gian quá nhỏ → bỏ qua Cloudflare thay vì gọi rồi timeout."""
        monkeypatch.setattr(bg_redesign, "_cf_ready", lambda: ("acc-123", "cf-token"))

        def boom(**kwargs):
            raise AssertionError("không được gọi mạng khi ngân sách đã cạn")

        monkeypatch.setattr(bg_redesign, "_cf_image_any_field", boom)
        res = bg_redesign._cloudflare_background(
            prompt="wooden table", timeout_s=2.0, seed=None, width=1024, height=1024
        )
        assert res is None


class TestBackgroundValidation:
    """`_background_is_usable` — chốt chặn ảnh lỗi thay vì ghép ảnh hỏng."""

    def _bg(self, arr: np.ndarray) -> Image.Image:
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")

    @staticmethod
    def _structured(mean: float, amplitude: float = 45.0, size: int = 256) -> np.ndarray:
        """Nền có cấu trúc TẦN SỐ THẤP (gradient + bokeh) quanh màu ``mean``.

        Không dùng nhiễu hạt mịn: ``_background_is_usable`` hạ ảnh về 96×96 trước
        khi đo, nên nhiễu hạt bị triệt tiêu — đúng ý đồ thiết kế, vì nền AI thật
        luôn có cấu trúc lớn (mép bàn, vệt sáng, bokeh), còn nhiễu hạt chỉ là
        artifact nén ảnh chứ không phải "nền có nội dung".
        """
        yy, xx = np.mgrid[0:size, 0:size]
        ramp = ((xx + yy) / (2.0 * (size - 1)) - 0.5) * 2.0  # -1..1
        arr = np.full((size, size, 3), mean, dtype=np.float32)
        arr += (ramp * amplitude)[..., None]
        arr += (np.sin(xx / 9.0) * amplitude * 0.35)[..., None]
        return arr

    def test_flat_background_rejected(self):
        flat = np.full((256, 256, 3), 128.0)
        ok, reason = _background_is_usable(self._bg(flat), np.array([20.0, 30.0, 40.0]))
        assert not ok
        assert reason == "flat_background"

    def test_full_black_rejected(self):
        black = np.full((256, 256, 3), 2.0)
        ok, _ = _background_is_usable(self._bg(black), np.array([20.0, 30.0, 40.0]))
        assert not ok

    def test_full_white_rejected(self):
        white = np.full((256, 256, 3), 253.0)
        ok, _ = _background_is_usable(self._bg(white), np.array([20.0, 30.0, 40.0]))
        assert not ok

    def test_background_same_as_original_rejected(self):
        """Nền model trả lại gần trùng nền cũ → coi như không đổi được nền."""
        arr = self._structured(200.0)
        ok, reason = _background_is_usable(self._bg(arr), np.array([200.0, 200.0, 200.0]))
        assert not ok
        assert reason == "background_unchanged"

    def test_textured_different_background_accepted(self):
        arr = self._structured(90.0)
        ok, reason = _background_is_usable(self._bg(arr), np.array([200.0, 200.0, 200.0]))
        assert ok, reason

    def test_similar_but_valid_background_accepted(self):
        """Nền có cấu trúc, màu hơi lệch nền cũ → vẫn nhận.

        Ngưỡng phải đủ thấp để KHÔNG chặn oan trường hợp hợp lệ: chụp trên nền
        sáng rồi đổi sang studio sáng khác vẫn là kết quả người dùng muốn.
        """
        arr = self._structured(214.0)
        ok, reason = _background_is_usable(self._bg(arr), np.array([200.0, 200.0, 200.0]))
        assert ok, reason


class TestGeometry:
    """Không bóp méo tỷ lệ + không lem màu nền cũ vào rìa ly."""

    def test_cover_resize_keeps_aspect(self):
        """Cắt theo cover: hình VUÔNG trong ảnh gốc vẫn vuông trong khung thuôn.

        Đây là phép đo trực tiếp của lỗi "biến dạng": ``resize`` thẳng một ảnh
        400×400 vào khung 200×400 sẽ nén ngang 50% → hình vuông thành chữ nhật
        dọc. Cover crop giữ scale đồng nhất nên tỷ lệ không đổi.
        """
        arr = np.zeros((400, 400, 3), dtype=np.uint8)
        arr[150:250, 150:250] = 255  # khối vuông 100×100 ở giữa
        img = Image.fromarray(arr, mode="RGB")
        out = _cover_resize(img, 200, 400)
        assert out.size == (200, 400)
        out_arr = np.asarray(out)
        ys, xs = np.nonzero(out_arr[:, :, 0] > 200)
        assert ys.size > 0
        width = xs.max() - xs.min() + 1
        height = ys.max() - ys.min() + 1
        assert abs(width - height) <= 2

    def test_cover_resize_crops_instead_of_stretching(self):
        """Khung hẹp hơn ảnh gốc → CẮT hai bên, không kéo giãn chiều rộng."""
        arr = np.zeros((400, 400, 3), dtype=np.uint8)
        arr[:, 100:140] = 255  # sọc dọc rộng 40px, còn 1/3 ngoài khung nhìn
        out = _cover_resize(Image.fromarray(arr, mode="RGB"), 200, 400)
        out_arr = np.asarray(out)
        stripe = np.nonzero(out_arr[200, :, 0] > 200)[0]
        # Sọc giữ nguyên độ rộng (scale = 1.0, chỉ crop), KHÔNG co còn 20px như
        # khi resize thẳng về 200×400.
        assert 38 <= stripe.size <= 42

    def test_premultiplied_resize_avoids_dark_fringe(self):
        """Rìa trong suốt không được kéo màu RGB của pixel trong suốt vào."""
        arr = np.zeros((100, 100, 4), dtype=np.uint8)
        # Nửa trái: đỏ đặc. Nửa phải: ĐEN nhưng alpha=0 (màu nền cũ ngoài mask).
        arr[:, :50] = (255, 0, 0, 255)
        arr[:, 50:] = (0, 0, 0, 0)
        out = np.asarray(_premultiplied_resize(Image.fromarray(arr, mode="RGBA"), (50, 50)))
        # Cột sát biên (đã ở nửa trong suốt nhưng gần vùng đỏ) phải giữ tông ĐỎ,
        # không bị tối đi vì trộn với đen của pixel alpha=0.
        edge = out[:, 24]
        opaque = edge[edge[:, 3] > 10]
        assert opaque.size > 0
        assert opaque[:, 0].mean() > 150
        assert opaque[:, 2].mean() < 60

    def test_subject_not_distorted_in_output(self, patch_llm, monkeypatch):
        """Ly hình chữ nhật dọc phải giữ tỷ lệ rộng/cao trong ảnh ra (sai số 6%)."""
        raw = _synthetic_drink()  # thân ly 120×220 px trong ảnh 300×400
        src = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB")).astype(np.int16)
        mask = (
            (np.abs(src[:, :, 0] - 90) <= 6)
            & (np.abs(src[:, :, 1] - 45) <= 6)
            & (np.abs(src[:, :, 2] - 20) <= 6)
        )
        ys, xs = np.nonzero(mask)
        src_ratio = (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)

        monkeypatch.setattr(
            bg_redesign,
            "_pollinations_image",
            lambda **kwargs: ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="pollinations",
                model="flux",
            ),
        )

        res = generate_background_redesign(raw, PROMPT, original_mime="image/png")
        assert res.ok, res.error
        out = np.asarray(Image.open(io.BytesIO(res.image_bytes)).convert("RGB")).astype(np.int16)
        out_mask = (
            (np.abs(out[:, :, 0] - 90) <= 8)
            & (np.abs(out[:, :, 1] - 45) <= 8)
            & (np.abs(out[:, :, 2] - 20) <= 8)
        )
        ys2, xs2 = np.nonzero(out_mask)
        assert ys2.size > 0
        out_ratio = (xs2.max() - xs2.min() + 1) / (ys2.max() - ys2.min() + 1)
        assert abs(out_ratio - src_ratio) / src_ratio < 0.06


class TestStyle:
    """Phong cách thiết kế → prompt nền tất định, tái dùng cho mọi ly."""

    def test_same_style_same_prompt(self):
        style = parse_style(
            {
                "slug": "nhip_quan_classic",
                "ten": "Nhịp Quán cổ điển",
                "mo_ta": "",
                "scene": "cafe_wood",
                "lighting": "golden_hour",
                "palette": "warm_wood",
                "lens": "shallow_85mm",
            }
        )
        assert style is not None
        first = build_background_prompt("món A", style)
        second = build_background_prompt("món B khác hoàn toàn", style)
        assert first == second
        assert "cafe_wood" not in first  # prompt dùng mô tả, không dùng slug
        assert "wooden cafe table" in first
        assert "no drink" in first

    def test_style_prompt_has_no_drink_words(self):
        style = parse_style(
            {
                "slug": "dep_sang_trong",
                "ten": "Đẹp sang trọng",
                "mo_ta": "",
                "scene": "marble_bar",
                "lighting": "window_soft",
                "palette": "terracotta",
                "lens": "tight_50mm",
            }
        )
        assert style is not None
        prompt = build_background_prompt("iced tea with orange", style)
        # Phần MÔ TẢ (trước hậu tố phủ định) không được nhắc tới đồ uống.
        positive = prompt.split("absolutely no drink")[0].lower()
        for banned in ("iced tea", "orange", "glass", "cup", "bottle", "mug"):
            assert banned not in positive
        # Hậu tố phủ định phải có mặt để model không vẽ thêm ly vào nền.
        assert "no drink" in prompt

    def test_style_avoids_llm_call(self, monkeypatch):
        """Có phong cách → KHÔNG gọi LLM viết lại prompt (tiết kiệm cả chục giây)."""
        calls: list[str] = []

        def fake_complete(*, task: str = "", **kwargs):
            calls.append(task)
            if task == "vision:bg_redesign_bbox":
                return _llm_ok('{"x1": 0.2, "y1": 0.25, "x2": 0.8, "y2": 0.9}')
            return _llm_ok('{"background_prompt_en": "should not be used at all"}')

        monkeypatch.setattr(bg_redesign, "complete", fake_complete)
        monkeypatch.setattr(
            bg_redesign,
            "_pollinations_image",
            lambda **kwargs: ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="pollinations",
                model="flux",
            ),
        )
        style = parse_style(
            {
                "slug": "nhip_quan_classic",
                "ten": "Nhịp Quán cổ điển",
                "mo_ta": "",
                "scene": "cafe_wood",
                "lighting": "golden_hour",
                "palette": "warm_wood",
                "lens": "shallow_85mm",
            }
        )
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png", style=style
        )
        assert res.ok, res.error
        assert "bg_redesign:prompt" not in calls
        assert "style=nhip_quan_classic" in res.text

    def test_style_used_in_output_metadata(self, monkeypatch):
        monkeypatch.setattr(
            bg_redesign,
            "_pollinations_image",
            lambda **kwargs: ImageGenResult(
                ok=True,
                image_bytes=_fake_bg_bytes(),
                image_mime="image/jpeg",
                provider="pollinations",
                model="flux",
            ),
        )
        style = parse_style(
            {
                "slug": "toi_gian_sang",
                "ten": "Tối giản sáng",
                "mo_ta": "",
                "scene": "studio_paper",
                "lighting": "bright_high_key",
                "palette": "monochrome_ink",
                "lens": "tight_50mm",
            }
        )
        res = generate_background_redesign(
            _synthetic_drink(), PROMPT, original_mime="image/png", style=style
        )
        assert res.ok, res.error
        assert "studio paper backdrop" in res.text
