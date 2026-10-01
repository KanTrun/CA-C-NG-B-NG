# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test offline cho ca_agents.menu_style — phong cách thiết kế (brand kit).

Điều quan trọng được kiểm ở đây: prompt sinh từ phong cách là TẤT ĐỊNH (cùng
phong cách → cùng prompt, để 10 ly của quán ra một phong cách) và TUYỆT ĐỐI
không chứa từ chỉ đồ uống ở phần mô tả (để model không vẽ thêm ly vào nền).
"""

from __future__ import annotations

from ca_agents.menu_style import (
    DEFAULT_STYLE_SLUG,
    LENSES,
    LIGHTINGS,
    PALETTES,
    PRESET_STYLES,
    SCENES,
    MenuStyle,
    default_styles,
    find_style,
    normalize_slug,
    parse_style,
    style_options,
)


class TestNormalizeSlug:
    def test_basic(self):
        assert normalize_slug("Nhịp Quán cổ điển") == "nhip_quan_co_dien"

    def test_keeps_valid_slug(self):
        assert normalize_slug("moody_quan_dem") == "moody_quan_dem"

    def test_collapses_separators(self):
        assert normalize_slug("a__b___c") == "a_b_c"

    def test_rejects_empty(self):
        assert normalize_slug("") is None
        assert normalize_slug("   ") is None
        assert normalize_slug("!!!") is None

    def test_rejects_too_long(self):
        assert normalize_slug("x" * 80) is None

    def test_strips_leading_separators(self):
        assert normalize_slug("__abc") == "abc"


class TestParseStyle:
    def _valid(self) -> dict[str, str]:
        return {
            "slug": "nhip_quan_classic",
            "ten": "Nhịp Quán cổ điển",
            "mo_ta": "ấm và gần gũi",
            "scene": "cafe_wood",
            "lighting": "golden_hour",
            "palette": "warm_wood",
            "lens": "shallow_85mm",
        }

    def test_valid(self):
        style = parse_style(self._valid())
        assert style is not None
        assert style.slug == "nhip_quan_classic"
        assert style.ten == "Nhịp Quán cổ điển"

    def test_rejects_not_a_dict(self):
        assert parse_style(None) is None  # type: ignore[arg-type]
        assert parse_style("cafe_wood") is None  # type: ignore[arg-type]
        assert parse_style([]) is None  # type: ignore[arg-type]

    def test_rejects_unknown_scene(self):
        bad = {**self._valid(), "scene": "banana_grove"}
        assert parse_style(bad) is None

    def test_rejects_unknown_lighting(self):
        assert parse_style({**self._valid(), "lighting": "candle"}) is None

    def test_rejects_unknown_palette(self):
        assert parse_style({**self._valid(), "palette": "rainbow"}) is None

    def test_rejects_unknown_lens(self):
        assert parse_style({**self._valid(), "lens": "fisheye"}) is None

    def test_rejects_bad_slug(self):
        assert parse_style({**self._valid(), "slug": ""}) is None

    def test_ten_defaults_to_slug_when_missing(self):
        raw = self._valid()
        raw.pop("ten")
        style = parse_style(raw)
        assert style is not None
        assert style.ten == "nhip_quan_classic"


class TestPrompt:
    def _style(self, **overrides: str) -> MenuStyle:
        style = parse_style(
            {
                "slug": "nhip_quan_classic",
                "ten": "Nhịp Quán cổ điển",
                "mo_ta": "",
                "scene": "cafe_wood",
                "lighting": "golden_hour",
                "palette": "warm_wood",
                "lens": "shallow_85mm",
                **overrides,
            }
        )
        assert style is not None
        return style

    def test_deterministic(self):
        """Cùng phong cách → cùng prompt; đây là điều làm menu đồng bộ."""
        style = self._style()
        assert style.to_prompt() == style.to_prompt()

    def test_different_styles_differ(self):
        assert self._style().to_prompt() != self._style(scene="marble_bar").to_prompt()

    def test_contains_scene_light_palette_lens(self):
        prompt = self._style().to_prompt()
        assert "wooden cafe table" in prompt
        assert "golden hour" in prompt
        assert "honey" in prompt
        assert "85mm" in prompt

    def test_never_mentions_drinks(self):
        """Mô tả nền không được gợi ý đồ uống, nếu không model vẽ thêm ly."""
        banned = ("drink", "beverage", "glass", "cup", "bottle", "mug", "straw", "coffee", "tea")
        for style in default_styles():
            positive = style.to_prompt().split("absolutely no")[0].lower()
            for word in banned:
                assert word not in positive, f"{style.slug} chứa '{word}'"

    def test_has_negation_tail(self):
        prompt = self._style().to_prompt().lower()
        assert "no drink" in prompt
        assert "no text" in prompt
        assert "background scene only" in prompt

    def test_extra_is_inserted(self):
        prompt = self._style().to_prompt(extra="soft rain on the window")
        assert "soft rain on the window" in prompt

    def test_extra_is_truncated(self):
        prompt = self._style().to_prompt(extra="x" * 2000)
        assert len(prompt) < 1400

    def test_blank_extra_ignored(self):
        assert self._style().to_prompt(extra="   ") == self._style().to_prompt()


class TestPromptAd:
    """Prompt phong cách cho ảnh GIỮ sản phẩm — tuyệt đối không chứa "no drink"."""

    def _style(self):
        from ca_agents.menu_style import parse_style

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
        return style

    def test_khong_co_dieu_khoan_cam_do_uong(self):
        prompt = self._style().to_prompt_ad().lower()
        assert "no drink" not in prompt
        assert "no beverage" not in prompt
        assert "absolutely no" not in prompt

    def test_van_giu_boi_canh(self):
        prompt = self._style().to_prompt_ad()
        assert "wooden cafe table" in prompt
        assert "golden hour" in prompt
        assert "85mm" in prompt

    def test_deterministic(self):
        assert self._style().to_prompt_ad() == self._style().to_prompt_ad()


class TestCatalog:
    def test_all_presets_are_valid(self):
        """Mọi preset phải parse được — preset hỏng làm dropdown UI trống."""
        for item in PRESET_STYLES:
            assert parse_style(item) is not None, item.get("slug")

    def test_preset_slugs_unique(self):
        slugs = [str(item["slug"]) for item in PRESET_STYLES]
        assert len(slugs) == len(set(slugs))

    def test_default_styles_not_empty(self):
        assert len(default_styles()) >= 3

    def test_default_slug_present(self):
        assert find_style(default_styles(), DEFAULT_STYLE_SLUG) is not None

    def test_style_options_expose_every_key(self):
        options = style_options()
        assert set(options) == {"scene", "lighting", "palette", "lens"}
        assert set(options["scene"]) == set(SCENES)
        assert set(options["lighting"]) == set(LIGHTINGS)
        assert set(options["palette"]) == set(PALETTES)
        assert set(options["lens"]) == set(LENSES)

    def test_style_options_returns_copy(self):
        """Sửa dict trả về không được ảnh hưởng bảng gốc."""
        options = style_options()
        options["scene"].clear()
        assert len(SCENES) > 0


class TestFindStyle:
    def test_finds_by_slug(self):
        styles = default_styles()
        assert find_style(styles, DEFAULT_STYLE_SLUG) is not None

    def test_normalizes_input(self):
        styles = default_styles()
        assert find_style(styles, "Moody Quán Đêm") is not None

    def test_returns_none_when_missing(self):
        assert find_style(default_styles(), "khong_ton_tai") is None

    def test_returns_none_for_empty(self):
        assert find_style(default_styles(), "") is None
        assert find_style(default_styles(), "  ") is None
