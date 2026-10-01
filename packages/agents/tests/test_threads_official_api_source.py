# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test threads_official_api_source — Threads Official API (graph.threads.net).

Cover:
    - is_configured(): theo env THREADS_ACCESS_TOKEN
    - _get_token: raise ThreadsOfficialApiError khi thiếu token
    - _keyword_search: build URL đúng params (q, fields, search_type, limit, token)
    - scrape_threads_official_api: map response → TrendItem (id, text, permalink,
      username, timestamp, media_type, has_replies)
    - Search hợp lệ nhưng 0 kết quả → trả [] (không raise)
    - Token sai (HTTP 400 OAuthException) → raise → caller rớt tầng
    - Wire vào _scrape_threads_smart: tier 0 chạy trước Google Bridge
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from ca_agents.ag_trend import TrendItem, _scrape_threads_smart
from ca_agents.sources import threads_official_api_source as src
from ca_agents.sources.threads_official_api_source import (
    ThreadsOfficialApiError,
    is_configured,
    scrape_threads_official_api,
)


@pytest.fixture(autouse=True)
def _clean_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
    yield
    # monkeypatch tự undo env


# ── is_configured / _get_token ──


def test_is_configured_false_without_token():
    assert is_configured() is False


def test_is_configured_true_with_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "EAAlxZA...")
    assert is_configured() is True


def test_get_token_raises_when_missing():
    with pytest.raises(ThreadsOfficialApiError, match="THREADS_ACCESS_TOKEN"):
        src._get_token()


# ── _build_search_url ──


def test_build_search_url_contains_params(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    url = src._build_search_url("cà phê", 5, "TOP")
    assert "https://graph.threads.net/v1.0/keyword_search?" in url
    assert "q=c%C3%A0+ph%C3%AA" in url
    assert "search_type=TOP" in url
    assert "limit=5" in url
    assert "access_token=tok123" in url
    assert "fields=" in url


def test_build_search_url_clamps_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    url = src._build_search_url("gen z", 500, "RECENT")
    assert "limit=100" in url  # max 100 theo docs


# ── _keyword_search ──


def test_keyword_search_parses_data(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    payload = {"data": [{"id": "111", "text": "hello"}]}
    with patch.object(src, "_http_get_json", MagicMock(return_value=payload)) as m:
        data = src._keyword_search("hello", 5)
    assert data == [{"id": "111", "text": "hello"}]
    called_url = m.call_args[0][0]
    assert "q=hello" in called_url


def test_keyword_search_raises_on_invalid_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    with patch.object(src, "_http_get_json", MagicMock(return_value={"error": "boom"})):
        with pytest.raises(ThreadsOfficialApiError, match="không hợp lệ"):
            src._keyword_search("hello", 5)


# ── scrape_threads_official_api — map data → TrendItem ──


def _sample_api_response() -> dict:
    return {
        "data": [
            {
                "id": "3456789012345678901",
                "text": "Cà phê muối ở Sài Gòn giờ đắt quá trời 😭 45k một ly",
                "media_type": "TEXT",
                "permalink": "https://www.threads.net/@genz_coffee/post/3456789012345678901",
                "timestamp": "2026-09-10T05:42:03+0000",
                "username": "genz_coffee",
                "has_replies": True,
                "is_quote_post": False,
                "is_reply": False,
            },
            {
                "id": "3456789012345678902",
                "text": "Gen Z giờ làm việc ở quán cafe nhiều hơn ở văn phòng\n#genz #wfh",
                "media_type": "TEXT",
                "permalink": "https://www.threads.net/@wfh_life/post/3456789012345678902",
                "timestamp": "2026-09-10T06:00:00+0000",
                "username": "wfh_life",
                "has_replies": False,
                "is_quote_post": False,
                "is_reply": False,
            },
        ]
    }


def test_scrape_maps_fields_to_trenditem(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    with patch.object(src, "_keyword_search", MagicMock(return_value=_sample_api_response()["data"])):
        items = scrape_threads_official_api(keyword="cà phê", count=5)
    assert len(items) == 2
    first = items[0]
    assert isinstance(first, TrendItem)
    assert first.id == "live_threads_api_3456789012345678901"
    assert "genz_coffee" in first.diem_nhan_dac_biet
    assert first.link_goc == "https://www.threads.net/@genz_coffee/post/3456789012345678901"
    assert first.is_live_scraped is True
    assert "THREADS API" in first.tieu_de
    assert first.trich_doan_noi_dung_that.startswith("Cà phê muối")
    assert first.danh_muc == "am_thuc_fnb"


def test_scrape_dedupes_and_respects_count(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    data = _sample_api_response()["data"]
    # Trùng id 2 lần + count=1
    doubled = data + [data[0]]
    with patch.object(src, "_keyword_search", MagicMock(return_value=doubled)):
        items = scrape_threads_official_api(keyword="cà phê", count=1)
    assert len(items) == 1
    assert items[0].id == "live_threads_api_3456789012345678901"


def test_scrape_empty_results_returns_empty_list(monkeypatch: pytest.MonkeyPatch):
    """Search hợp lệ, 0 kết quả → [] (không raise, không tốn quota)."""
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    with patch.object(src, "_keyword_search", MagicMock(return_value=[])):
        items = scrape_threads_official_api(keyword="xyz", count=5)
    assert items == []


def test_scrape_no_keyword_uses_default_queries(monkeypatch: pytest.MonkeyPatch):
    """Không keyword → 3 query mặc định (cà phê, gen z, quán cafe)."""
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    spy = MagicMock(return_value=[])
    with patch.object(src, "_keyword_search", spy):
        items = scrape_threads_official_api(keyword="", count=5)
    assert items == []
    assert spy.call_count == 3
    qs = [c.kwargs.get("keyword") or c.args[0] if c.args else c.kwargs.get("q") for c in spy.call_args_list]
    # _keyword_search(q, count, search_type) positional
    qs = [c.args[0] for c in spy.call_args_list]
    assert "cà phê" in qs and "gen z" in qs and "quán cafe" in qs


def test_scrape_raises_on_http_error(monkeypatch: pytest.MonkeyPatch):
    """Token sai → HTTP 400 → raise ThreadsOfficialApiError → caller rớt tầng."""
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "invalid_token")
    with patch.object(
        src,
        "_keyword_search",
        MagicMock(side_effect=ThreadsOfficialApiError("HTTP 400: Invalid OAuth 2.0 Access Token")),
    ):
        with pytest.raises(ThreadsOfficialApiError, match="Invalid OAuth"):
            scrape_threads_official_api(keyword="cà phê", count=5)


# ── Wire vào _scrape_threads_smart (ag_trend.py) ──


def test_smart_chain_official_api_first_when_configured(monkeypatch: pytest.MonkeyPatch):
    """Có token → tier 0 Official API chạy TRƯỚC Google Bridge.

    Tắt Camoufox: trong chuỗi `auto` Camoufox đứng trước Bridge, nhưng tier 0
    (Official API) vẫn đứng TRƯỚC Camoufox nên test này vẫn kiểm được thứ tự 0.
    """
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: False)
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    api_items = [MagicMock(spec=TrendItem)]
    api_mock = MagicMock(return_value=api_items)
    bridge_spy = MagicMock(return_value=[])
    monkeypatch.setattr(
        "ca_agents.sources.threads_official_api_source.scrape_threads_official_api",
        api_mock,
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        bridge_spy,
    )

    items = _scrape_threads_smart(keyword="cà phê", count=5, scrape_mode="auto")
    assert items == api_items
    api_mock.assert_called_once()
    bridge_spy.assert_not_called()  # Official API gánh → Bridge không cần chạy


def test_smart_chain_falls_to_bridge_when_api_fails(monkeypatch: pytest.MonkeyPatch):
    """Token sai / API lỗi → rớt tầng về Google Bridge (không crash).

    Tắt Camoufox: nó đứng TRƯỚC Bridge trong chuỗi `auto` (đo thật 2026-09-26)
    nên nếu máy có Camoufox thì test sẽ cào THẬT thay vì chạm Bridge mock.
    """
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: False)
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "expired_token")
    monkeypatch.setattr(
        "ca_agents.sources.threads_official_api_source.scrape_threads_official_api",
        MagicMock(side_effect=ThreadsOfficialApiError("HTTP 400: token expired")),
    )
    bridge_items = [MagicMock(spec=TrendItem)]
    bridge_mock = MagicMock(return_value=bridge_items)
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        bridge_mock,
    )

    items = _scrape_threads_smart(keyword="cà phê", count=5, scrape_mode="auto")
    assert items == bridge_items
    bridge_mock.assert_called_once()


def test_smart_chain_skips_api_when_not_configured(monkeypatch: pytest.MonkeyPatch):
    """Không token → skip tier 0 hoàn toàn (không import lỗi, không delay).

    Tắt Camoufox: nó đứng TRƯỚC Bridge trong chuỗi `auto` (đo thật 2026-09-26).
    """
    monkeypatch.setattr("ca_agents.clients.camoufox_client.is_available", lambda: False)
    api_spy = MagicMock()
    monkeypatch.setattr(
        "ca_agents.sources.threads_official_api_source.scrape_threads_official_api",
        api_spy,
    )
    bridge_items = [MagicMock(spec=TrendItem)]
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=bridge_items),
    )

    items = _scrape_threads_smart(keyword="cà phê", count=5, scrape_mode="auto")
    assert items == bridge_items
    api_spy.assert_not_called()  # is_configured()=False → skip


def test_smart_chain_direct_only_skips_api(monkeypatch: pytest.MonkeyPatch):
    """mode='direct_only' → KHÔNG gọi Official API (khóa mọi tier API)."""
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok123")
    api_spy = MagicMock()
    monkeypatch.setattr(
        "ca_agents.sources.threads_official_api_source.scrape_threads_official_api",
        api_spy,
    )
    direct_items = [MagicMock(spec=TrendItem)]
    monkeypatch.setattr(
        "ca_agents.sources.threads_google_bridge_source.scrape_threads_google_bridge",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "ca_agents.sources.threads_direct_source.scrape_threads_direct",
        MagicMock(return_value=direct_items),
    )

    items = _scrape_threads_smart(keyword="cà phê", count=5, scrape_mode="direct_only")
    assert items == direct_items
    api_spy.assert_not_called()
