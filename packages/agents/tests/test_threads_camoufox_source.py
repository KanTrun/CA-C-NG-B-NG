# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test threads_camoufox_source — không mở browser thật (CA_AGENT_MODE=replay).

Cover theo PR 3 §IV:
    - extract_threads_items bằng fixture HTML tĩnh (không mock Playwright)
    - Tái dùng _detect_category/_assess_trend_lifecycle từ threads_direct_source
    - _is_login_wall: URL redirect + HTML chỉ có nút login
    - fetch_threads_page: chờ selector + trả content (mock page object)
    - Cache TTL: hit trong TTL, miss sau khi expire, key gồm keyword+region
    - scrape_threads_camoufox lifecycle: mock scrape_page, login-wall raise
    - Chuỗi _scrape_threads_smart: skip tier khi unavailable, mode browser gọi first
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ca_agents.ag_trend import TrendItem, _scrape_threads_smart
from ca_agents.sources import threads_camoufox_source as src
from ca_agents.sources.threads_camoufox_source import (
    extract_threads_items,
    fetch_threads_page,
    scrape_threads_camoufox,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "threads_search_sample.html"


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset cache TTL trước mỗi test (env override được)."""
    src._reset_cache()
    yield
    src._reset_cache()


# ── extract_threads_items — hàm THUẦN với fixture HTML tĩnh ──


def test_extract_items_from_fixture():
    """Fixture 3 post → 3 TrendItem với stats parse đúng + category từ helper chung."""
    html = _FIXTURE.read_text(encoding="utf-8")
    items = extract_threads_items(
        html, keyword="matcha", count=12, nguon_goc="threads_vn", now_str="10:00:00 15/09/2026"
    )

    assert len(items) == 3
    first = items[0]
    assert isinstance(first, TrendItem)
    assert first.is_live_scraped is True
    # Post đầu: 2.4K likes, 185 replies → "đang đỉnh cao" (likes >= 1000)
    assert "2,400 tim" in first.diem_nhan_dac_biet
    assert "185 phản hồi" in first.diem_nhan_dac_biet
    assert first.vong_doi == "dang_dinh"
    # Link post từ href
    assert first.link_goc == "https://www.threads.net/@saigon_coffee_guide/post/Cx1a2b3c4d5"
    # Category từ _detect_category (matcha → am_thuc_fnb)
    assert first.danh_muc == "am_thuc_fnb"


def test_extract_items_respects_count_limit():
    """count=2 → chỉ 2 item dù fixture có 3."""
    html = _FIXTURE.read_text(encoding="utf-8")
    items = extract_threads_items(
        html, keyword="matcha", count=2, nguon_goc="threads_vn", now_str="10:00:00 15/09/2026"
    )
    assert len(items) == 2


def test_extract_items_empty_html():
    """HTML rỗng / không selector → list rỗng, không raise."""
    assert extract_threads_items("", "kw", 5, "threads_vn", "now") == []
    assert extract_threads_items("<div>nothing here</div>", "kw", 5, "threads_vn", "now") == []


def test_extract_items_skips_block_without_text():
    """Khối post rỗng (text < 30 ký tự) → skip, không crash."""
    html = '<div data-e2e="search-result-post"><a href="/@x/post/1">ok</a></div>'
    items = extract_threads_items(html, "kw", 5, "threads_vn", "now")
    assert items == []


def test_extract_reuses_lifecycle_helper():
    """Post ít tương tác (likes < 1000) → 'moi_nhu' từ _assess_trend_lifecycle."""
    html = (
        '<a href="/@user/post/Ab1"></a>'
        '<div>user</div><div>3 giờ</div>'
        '<div>Cà phê quán mới mở đẹp lung linh ghé ngay kẻo lỡ</div>'
        '<div>150</div><div>12</div>'
    )
    items = extract_threads_items(html, "cafe", 5, "threads_vn", "now")
    assert len(items) == 1
    assert items[0].vong_doi == "moi_nhu"


def test_map_post_rejects_short_body_and_no_stats():
    """Bài rỗng nội dung hoặc không có tương tác → skip (không phải trend)."""
    assert src._map_post(
        {"username": "a", "body": "ngắn", "stats_raw": ["1"], "aria_labels": []},
        0, "kw", "threads_vn", "now",
    ) is None
    assert src._map_post(
        {"username": "a", "body": "nội dung đủ dài để vượt ngưỡng 15 ký tự",
         "stats_raw": [], "aria_labels": []},
        0, "kw", "threads_vn", "now",
    ) is None


def test_map_post_parses_real_shape():
    """Payload THẬT từ JS extract → TrendItem đầy đủ trường."""
    raw = {
        "username": "sonqthao",
        "post_id": "DddL7rjmtPp",
        "url": "https://www.threads.net/@sonqthao/post/DddL7rjmtPp",
        "time_text": "2 giờ",
        "body": "Thu đến nhất định phải ngồi quán này... Quán đúng gu tui thật sự",
        "stats_raw": ["6,9K", "99", "496", "4,4K"],
        "aria_labels": ["Thích", "Bình luận", "Đăng lại"],
    }
    item = src._map_post(raw, 0, "cà phê", "threads_vn", "now")
    assert item is not None
    assert item.link_goc == "https://www.threads.net/@sonqthao/post/DddL7rjmtPp"
    # "6,9K" kiểu Việt (dấu phẩy thập phân) → 6900
    assert "6,900 tim" in item.luot_tiep_can
    assert "496 đăng lại" in item.luot_tiep_can
    assert "@sonqthao" in item.diem_nhan_dac_biet
    assert item.is_live_scraped is True


# ── _is_login_wall (plan §3.4) ──


def test_login_wall_detected_by_url():
    """URL redirect về /login → login-wall."""
    assert src._is_login_wall("<html>whatever</html>", "https://www.threads.net/login") is True
    assert src._is_login_wall(
        "x", "https://www.threads.com/login/?next=https%3A%2F%2Fwww.threads.com%2Fexplore"
    ) is True


def test_nav_login_link_is_NOT_wall():
    """⚠️ BÀI HỌC 2026-09-26: `a[href*='/login']` LUÔN có trong nav bar.

    Trang search render đầy đủ 6–19 bài VẪN có link "Đăng nhập" ở nav. Dùng nav
    link để suy ra login-wall là FALSE POSITIVE — chính là nguyên nhân tier
    Threads báo "login-wall" oan rồi rớt tầng dù cào được bài.
    """
    html = '<html><nav><a href="/login">Đăng nhập</a></nav><a href="/@u/post/1">bài</a></html>'
    assert src._is_login_wall(html, "https://www.threads.net/search?q=cafe") is False


def test_no_login_wall_when_posts_present():
    """Trang có post thật + URL search → KHÔNG phải login-wall."""
    html = _FIXTURE.read_text(encoding="utf-8")
    assert src._is_login_wall(html, "https://www.threads.net/search?q=cafe") is False


# ── fetch_threads_page — mock page object (không Playwright thật) ──


def test_fetch_threads_page_returns_content_when_posts_found():
    """fetch chờ CÓ BÀI (poll đếm link post) rồi trả content — KHÔNG goto.

    ĐO THẬT 2026-09-26: bỏ `wait_for_selector` (trang render chậm, chờ selector
    cứng dễ chụp HTML quá sớm → 0–2 bài). Nay poll `a[href*='/post/']` tối đa 20s.
    """
    page = MagicMock()
    page.content.return_value = "<html>fake</html>"
    page.eval_on_selector_all.return_value = 5  # có 5 link post
    page.wait_for_timeout.return_value = None

    html = fetch_threads_page(page, "cafe", scroll_rounds=0)
    assert html == "<html>fake</html>"
    page.goto.assert_not_called()  # goto do scrape_page lo
    # Đã đếm link post ít nhất 1 lần
    assert page.eval_on_selector_all.called


def test_fetch_threads_page_raises_when_no_posts():
    """Trang render nhưng 0 link post sau khi chờ → CamoufoxUnavailable."""
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    page = MagicMock()
    page.eval_on_selector_all.return_value = 0
    page.url = "https://www.threads.net/search?q=cafe"  # KHÔNG redirect /login
    page.wait_for_timeout.return_value = None

    with pytest.raises(CamoufoxUnavailable, match="không có bài viết nào"):
        fetch_threads_page(page, "cafe", scroll_rounds=0)


def test_fetch_threads_page_raises_login_wall_when_redirected():
    """0 post + URL redirect về /login → CamoufoxUnavailable nói rõ login-wall."""
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    page = MagicMock()
    page.eval_on_selector_all.return_value = 0
    page.url = "https://www.threads.com/login/?next=https%3A%2F%2Fwww.threads.com%2Fexplore"
    page.wait_for_timeout.return_value = None

    with pytest.raises(CamoufoxUnavailable, match="redirect về trang đăng nhập"):
        fetch_threads_page(page, "cafe", scroll_rounds=0)


# ── Cache TTL (§3.3-bis) ──


def test_cache_hit_within_ttl(monkeypatch: pytest.MonkeyPatch):
    """Trong TTL → scrape_page KHÔNG được gọi (dùng cache)."""
    cached_item = MagicMock(spec=TrendItem)
    src._cache_put("threads:matcha|threads_vn", [cached_item])

    scrape_mock = MagicMock()
    monkeypatch.setattr(src, "scrape_page", scrape_mock)

    items = scrape_threads_camoufox(keyword="matcha", count=5, nguon_goc="threads_vn")
    assert items == [cached_item]
    scrape_mock.assert_not_called()


def _fake_posts() -> list[dict]:
    """Payload THẬT từ JS extract (2 bài đủ nội dung + stats)."""
    return [
        {
            "username": "saigon_coffee_guide",
            "post_id": "Cx1a2b3c4d5",
            "url": "https://www.threads.net/@saigon_coffee_guide/post/Cx1a2b3c4d5",
            "time_text": "2 giờ",
            "body": "Cơn sốt matcha nguyên bản đậm vị đang áp đảo các loại trà ngọt gắt.",
            "stats_raw": ["2.4K", "185"],
            "aria_labels": ["Thích", "Bình luận"],
        },
        {
            "username": "genz_overthinking",
            "post_id": "Cx9y8z7w6v5",
            "url": "https://www.threads.net/@genz_overthinking/post/Cx9y8z7w6v5",
            "time_text": "5 giờ",
            "body": "Đi làm quán cafe ca tối đúng là bài test sức bền tâm lý ghê.",
            "stats_raw": ["1.8K", "94"],
            "aria_labels": ["Thích"],
        },
    ]


def _fake_scrape_page_factory(posts: list[dict]):  # type: ignore[no-untyped-def]
    """Trả hàm `scrape_page` giả: chạy extractor với page đã mock sẵn."""

    def _fake(url: str, extractor, **kwargs: object) -> object:
        page = MagicMock()
        page.wait_for_selector.return_value = None
        page.eval_on_selector_all.return_value = len(posts)
        page.query_selector.return_value = None
        page.evaluate.return_value = posts
        return extractor(page)

    return _fake


def test_cache_miss_after_ttl(monkeypatch: pytest.MonkeyPatch):
    """Hết TTL → cache miss → gọi scrape_page thật."""
    src._cache_put("threads:matcha|threads_vn", [MagicMock(spec=TrendItem)])
    # Ép cache cũ hơn TTL
    stale = time.monotonic() - 10_000
    src._cache["threads:matcha|threads_vn"] = (stale, [MagicMock(spec=TrendItem)])

    posts = _fake_posts()

    def fake_scrape_page(url: str, extractor, **kwargs: object) -> list[dict]:
        page = MagicMock()
        page.wait_for_selector.return_value = None
        page.eval_on_selector_all.return_value = len(posts)
        page.query_selector.return_value = None
        page.evaluate.return_value = posts
        return extractor(page)

    monkeypatch.setattr(src, "scrape_page", fake_scrape_page)

    items = scrape_threads_camoufox(keyword="matcha", count=3, nguon_goc="threads_vn")
    assert len(items) == 2
    assert all(isinstance(i, TrendItem) for i in items)


def test_cache_key_separates_from_tiktok(monkeypatch: pytest.MonkeyPatch):
    """Key threads: prefix riêng — không đụng cache TikTok cùng keyword."""
    from ca_agents.sources import tiktok_camoufox_source as tt_src

    tt_src._cache_put("matcha|tiktok_vn", [MagicMock(spec=TrendItem)])

    posts = _fake_posts()

    def fake_scrape_page(url: str, extractor, **kwargs: object) -> list[dict]:
        page = MagicMock()
        page.wait_for_selector.return_value = None
        page.eval_on_selector_all.return_value = len(posts)
        page.query_selector.return_value = None
        page.evaluate.return_value = posts
        return extractor(page)

    monkeypatch.setattr(src, "scrape_page", fake_scrape_page)
    items = scrape_threads_camoufox(keyword="matcha", count=3, nguon_goc="threads_vn")
    assert items, "threads cache trống → phải gọi thật và có item"


# ── scrape_threads_camoufox lifecycle — mock scrape_page ──


def test_scrape_calls_extract_and_logs(monkeypatch: pytest.MonkeyPatch):
    """scrape_page chạy extractor → items, URL goto đúng search URL."""
    posts = _fake_posts()
    captured: dict[str, str] = {}

    def fake_scrape_page(url: str, extractor, **kwargs: object) -> list[dict]:
        captured["url"] = url
        page = MagicMock()
        page.wait_for_selector.return_value = None
        page.eval_on_selector_all.return_value = len(posts)
        page.query_selector.return_value = None
        page.evaluate.return_value = posts
        return extractor(page)

    monkeypatch.setattr(src, "scrape_page", fake_scrape_page)

    items = scrape_threads_camoufox(keyword="matcha", count=3, nguon_goc="threads_vn")
    assert len(items) == 2
    assert all(isinstance(i, TrendItem) for i in items)
    assert "https://www.threads.net/search?q=matcha" in captured["url"]
    assert "serp_type=default" in captured["url"]
    # Link là bài thật (không phải search URL)
    assert all("/post/" in i.link_goc for i in items)


def test_scrape_propagates_camoufox_unavailable(monkeypatch: pytest.MonkeyPatch):
    """scrape_page raise CamoufoxUnavailable → propagate thẳng cho caller rớt tầng."""
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    monkeypatch.setattr(src, "scrape_page", MagicMock(side_effect=CamoufoxUnavailable("chưa cài")))
    with pytest.raises(CamoufoxUnavailable):
        scrape_threads_camoufox(keyword="matcha", count=3)


def test_login_wall_raises_unavailable(monkeypatch: pytest.MonkeyPatch):
    """URL redirect /login → CamoufoxUnavailable, rớt tầng NGAY (plan §3.4)."""
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    def fake_scrape_page(url: str, extractor, **kwargs: object) -> object:
        page = MagicMock()
        page.eval_on_selector_all.return_value = 0  # 0 post
        page.url = "https://www.threads.com/login/?next=https%3A%2F%2Fwww.threads.com%2Fexplore"
        page.wait_for_timeout.return_value = None
        return extractor(page)

    monkeypatch.setattr(src, "scrape_page", fake_scrape_page)

    with pytest.raises(CamoufoxUnavailable, match="redirect về trang đăng nhập"):
        scrape_threads_camoufox(keyword="matcha", count=3)


# ── Wire vào _scrape_threads_smart (ag_trend.py) ──


def test_smart_chain_skips_camoufox_when_unavailable(monkeypatch: pytest.MonkeyPatch):
    """is_available()=False → tier Camoufox bị skip, chuỗi cũ vẫn chạy."""
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: False)
    bridge_items = [MagicMock(spec=TrendItem)]
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=bridge_items),
    )
    camoufox_spy = MagicMock()
    monkeypatch.setattr(
        "ca_agents.sources.threads_camoufox_source.scrape_threads_camoufox",
        camoufox_spy,
    )

    items = _scrape_threads_smart(keyword="matcha", count=5, scrape_mode="auto")
    assert items == bridge_items
    camoufox_spy.assert_not_called()  # unavailable → skip tier


def test_smart_chain_uses_camoufox_after_direct_fail(monkeypatch: pytest.MonkeyPatch):
    """Bridge + Direct fail (rỗng) + Camoufox available → Camoufox tier, KHÔNG tới Apify."""
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: True)
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_direct_source.scrape_threads_direct",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_camoufox_source.scrape_page",
        _fake_scrape_page_factory(_fake_posts()),
    )
    apify_spy = MagicMock()
    monkeypatch.setattr("ca_agents.sources.threads_apify_source.scrape_threads_apify", apify_spy)

    items = _scrape_threads_smart(keyword="matcha", count=3, scrape_mode="auto")
    assert len(items) == 2
    apify_spy.assert_not_called()  # Camoufox gánh được → không tốn CU Apify


def test_smart_chain_browser_mode_camoufox_first(monkeypatch: pytest.MonkeyPatch):
    """mode='browser' → Camoufox FIRST, Bridge/Direct chỉ là backup."""
    monkeypatch.setattr(
        "ca_agents.sources.threads_camoufox_source.scrape_page",
        _fake_scrape_page_factory(_fake_posts()),
    )
    bridge_spy = MagicMock(return_value=[])
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        bridge_spy,
    )

    items = _scrape_threads_smart(keyword="matcha", count=3, scrape_mode="browser")
    assert len(items) == 2
    # Camoufox gánh → Bridge backup KHÔNG được gọi
    bridge_spy.assert_not_called()


def test_smart_chain_browser_mode_falls_back_to_bridge(monkeypatch: pytest.MonkeyPatch):
    """mode='browser' + Camoufox fail → rớt tầng về Bridge (không crash)."""
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    monkeypatch.setattr(
        "ca_agents.sources.threads_camoufox_source.scrape_page",
        MagicMock(side_effect=CamoufoxUnavailable("chưa cài")),
    )
    bridge_items = [MagicMock(spec=TrendItem)]
    bridge_mock = MagicMock(return_value=bridge_items)
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        bridge_mock,
    )

    items = _scrape_threads_smart(keyword="matcha", count=5, scrape_mode="browser")
    assert items == bridge_items
    bridge_mock.assert_called_once()


def test_smart_chain_direct_only_never_uses_camoufox(monkeypatch: pytest.MonkeyPatch):
    """mode='direct_only' → KHÔNG gọi Camoufox tier (khóa cả browser lẫn Apify)."""
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: True)
    direct_items = [MagicMock(spec=TrendItem)]
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_direct_source.scrape_threads_direct",
        MagicMock(return_value=direct_items),
    )
    camoufox_spy = MagicMock()
    monkeypatch.setattr(
        "ca_agents.sources.threads_camoufox_source.scrape_threads_camoufox",
        camoufox_spy,
    )

    items = _scrape_threads_smart(keyword="matcha", count=5, scrape_mode="direct_only")
    assert items == direct_items
    camoufox_spy.assert_not_called()


# ── No-hardcoded-fallback (plan §3.4 — fix fake-data tier-blocking) ──


def test_google_bridge_returns_empty_when_rss_empty(monkeypatch: pytest.MonkeyPatch):
    """Google News RSS rỗng → trả [] (KHÔNG curated hardcode giả mạo data thật)."""
    from ca_agents.sources import threads_google_bridge_source as bridge_src

    monkeypatch.setattr(
        bridge_src,
        "parse_google_rss_xml",
        MagicMock(return_value=[]),
    )
    items = bridge_src.scrape_threads_google_bridge(keyword="cà phê", count=5)
    assert items == []
    # Không item nào được gắn is_live_scraped=True từ data giả
    assert all(not getattr(it, "is_live_scraped", False) for it in items)


def test_direct_jina_returns_empty_when_fetch_fails(monkeypatch: pytest.MonkeyPatch):
    """Jina 403/fail → trả [] để chuỗi rớt tầng Camoufox/Apify (KHÔNG curated_hot_threads)."""
    from ca_agents.sources import threads_direct_source as direct_src

    monkeypatch.setattr(
        "urllib.request.urlopen",
        MagicMock(side_effect=RuntimeError("HTTP Error 403: Forbidden")),
    )
    items = direct_src.scrape_threads_direct(keyword="cà phê", count=5)
    assert items == []


def test_smart_chain_all_tiers_empty_falls_to_rss(monkeypatch: pytest.MonkeyPatch):
    """Bridge + Direct + Camoufox + Apify đều rỗng → tầng cuối RSS Kênh14 (data thật)."""
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_direct_source.scrape_threads_direct",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.clients.camoufox_client.is_available",
        lambda: False,
    )
    rss_items = [MagicMock(spec=TrendItem)]
    monkeypatch.setattr(
        "ca_agents.ag_trend._scrape_genz_media_vn",
        MagicMock(return_value=rss_items),
    )

    items = _scrape_threads_smart(keyword="cà phê", count=5, scrape_mode="auto")
    assert items == rss_items  # rớt tầng tới RSS thật, không phải []


def test_smart_chain_returns_empty_when_all_real_sources_fail(monkeypatch: pytest.MonkeyPatch):
    """Mọi tầng thật fail (kể cả RSS) → trả [] trung thực, KHÔNG giả mạo data."""
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_direct_source.scrape_threads_direct",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.clients.camoufox_client.is_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "ca_agents.ag_trend._scrape_genz_media_vn",
        MagicMock(return_value=[]),
    )

    items = _scrape_threads_smart(keyword="xyz-khong-ton-tai", count=5, scrape_mode="auto")
    assert items == []  # trung thực: không data giả lấp đầy
