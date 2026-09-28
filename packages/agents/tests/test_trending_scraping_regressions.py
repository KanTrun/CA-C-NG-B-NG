# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test hồi quy cho chuỗi cào trending — bám BẰNG CHỨNG response THẬT.

Bối cảnh (nghiên cứu 2026-09-24, `plans/260923-nghien-cuu-cao-du-lieu-trending/`):
    Các nguồn bên thứ ba hỏng vì code đọc sai/thiếu tham số, nhưng test cũ
    **mock toàn bộ hàm nguồn** nên không bao giờ chạm shape response thật.

Nguyên tắc của file này: mọi fixture là **copy nguyên văn (đã lược bớt) payload
THẬT** thu được khi probe live, để nếu bên thứ ba đổi schema thì test fail ngay
tại tầng parse thay vì âm thầm trả rỗng trên production.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import patch

import pytest
from ca_agents.ag_trend import _fetch_tikwm_comments, _fetch_tikwm_feed, parse_tikwm_feed
from ca_agents.sources.gtrends_serpapi_source import fetch_fnb_trends_serpapi
from ca_agents.sources.gtrends_trending_now_source import (
    fetch_trending_now_serpapi,
    parse_trending_now_payload,
)

# ── B1: TikWM feed ────────────────────────────────────────────────────────────
# Payload THẬT (probe 2026-09-24). `data` là LIST PHẲNG — không bọc "videos".
# Đây chính là điểm code cũ hiểu sai khiến hàm luôn trả [].
_TIKWM_FEED_REAL: dict[str, Any] = {
    "code": 0,
    "msg": "success",
    "processed_time": 5.7802,
    "data": [
        {
            "video_id": "7682025351832194322",
            "region": "VN",
            "title": "Cắt nem cho Minh Quang😚 #thuybunfood",
            "play_count": 666097,
            "digg_count": 27277,
            "comment_count": 208,
            "author": {"unique_id": "thuybunfood", "nickname": "Thủy Bun Food"},
        },
        {
            "video_id": "7682025351832194323",
            "region": "VN",
            "title": "Tiền điện chắc cũng sốc luôn #tintuc",
            "play_count": 621188,
            "digg_count": 6665,
            "comment_count": 91,
            "author": {"unique_id": "360tramhonghot", "nickname": "360 Trăm Hóng Hot"},
        },
    ],
}


def test_parse_tikwm_feed_reads_flat_list_data() -> None:
    """`data` dạng LIST PHẲNG phải đọc được (bug cũ: chỉ đọc `data['videos']`)."""
    videos = parse_tikwm_feed(_TIKWM_FEED_REAL)
    assert len(videos) == 2
    assert videos[0]["video_id"] == "7682025351832194322"
    assert videos[0]["author"]["unique_id"] == "thuybunfood"


def test_parse_tikwm_feed_supports_legacy_videos_wrapper() -> None:
    """Biến thể cũ bọc trong `{"videos": [...]}` vẫn phải hoạt động."""
    payload = {"code": 0, "data": {"videos": _TIKWM_FEED_REAL["data"]}}
    assert len(parse_tikwm_feed(payload)) == 2


def test_parse_tikwm_feed_rejects_error_code() -> None:
    """`code != 0` (rate limit) → trả [] thay vì dùng dữ liệu rác (ADR-008)."""
    assert parse_tikwm_feed({"code": -1, "msg": "Free Api Limit: 1 request/second."}) == []
    assert parse_tikwm_feed({"code": -1, "msg": "'url' is required."}) == []


def test_parse_tikwm_feed_tolerates_garbage() -> None:
    """Payload hỏng đủ kiểu không được làm vỡ parser."""
    assert parse_tikwm_feed(None) == []
    assert parse_tikwm_feed("not-a-dict") == []
    assert parse_tikwm_feed({"code": 0, "data": "unexpected"}) == []
    assert parse_tikwm_feed({"code": 0, "data": [1, "x", {"video_id": "ok"}]}) == [
        {"video_id": "ok"}
    ]


def test_fetch_tikwm_feed_falls_back_to_second_host() -> None:
    """Host đầu fail (timeout/HTTP 531) → phải thử host thứ hai trước khi bỏ."""
    attempts: list[str] = []

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    def _fake_urlopen(req: Any, timeout: int = 0, context: Any = None) -> _Resp:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        attempts.append(url)
        if "//tikwm.com" in url:
            raise urllib.error.HTTPError(url, 531, "<none>", {}, None)  # type: ignore[arg-type]
        return _Resp(json.dumps(_TIKWM_FEED_REAL).encode("utf-8"))

    with patch("ca_agents.ag_trend.urllib.request.urlopen", side_effect=_fake_urlopen):
        videos = _fetch_tikwm_feed()

    assert len(videos) == 2, "host dự phòng phải cứu được request"
    assert len(attempts) == 2, "phải thử lần lượt cả 2 host"


def test_fetch_tikwm_feed_raises_when_all_hosts_fail() -> None:
    """Tất cả host fail → raise để caller ghi nhận (không nuốt lỗi im lặng)."""
    with patch(
        "ca_agents.ag_trend.urllib.request.urlopen",
        side_effect=TimeoutError("read operation timed out"),
    ):
        with pytest.raises(TimeoutError):
            _fetch_tikwm_feed()


def test_fetch_tikwm_comments_parses_real_shape() -> None:
    """Comment thật: `data.comments[].user.unique_id` + `digg_count`."""
    real = {
        "code": 0,
        "msg": "success",
        "data": {
            "comments": [
                {
                    "text": "Ngon quá",
                    "digg_count": 12,
                    "user": {"unique_id": "khach_a"},
                },
                {"text": "", "user": {"unique_id": "empty"}},
            ]
        },
    }

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(real).encode("utf-8")

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    import ca_agents.ag_trend as agt

    agt._last_comment_fetch_ts = 0.0  # không chờ nhịp trong test
    with patch("ca_agents.ag_trend.urllib.request.urlopen", return_value=_Resp()):
        comments = _fetch_tikwm_comments("https://www.tiktok.com/@a/video/1")

    assert comments == ['@khach_a: "Ngon quá" (❤️ 12 tim)']


def test_fetch_tikwm_comments_returns_empty_on_rate_limit() -> None:
    """Rate limit 1 req/s → KHÔNG bịa comment, trả [] (ADR-008)."""
    rate_limited = {"code": -1, "msg": "Free Api Limit: 1 request/second."}

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(rate_limited).encode("utf-8")

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    import ca_agents.ag_trend as agt

    agt._last_comment_fetch_ts = 0.0
    with patch("ca_agents.ag_trend.urllib.request.urlopen", return_value=_Resp()):
        assert _fetch_tikwm_comments("https://www.tiktok.com/@a/video/1") == []


# ── B2: SerpApi Google Trends theo từ khóa ────────────────────────────────────
_RELATED_QUERIES_PAYLOAD: dict[str, Any] = {
    "search_metadata": {"status": "Success"},
    "related_queries": {
        "rising": [
            {"query": "trà sữa viên viên hà nội", "value": "+600%", "extracted_value": 600},
            {"query": "trà sữa tam hảo", "value": "+300%", "extracted_value": 300},
        ],
        "top": [{"query": "trà sữa trân châu", "value": "100", "extracted_value": 100}],
    },
}

# Payload khi KHÔNG truyền data_type — SerpApi trả TIMESERIES, thiếu related_queries.
_TIMESERIES_ONLY_PAYLOAD: dict[str, Any] = {
    "search_metadata": {"status": "Success"},
    "interest_over_time": {"timeline_data": [{"date": "23/09", "values": [{"extracted_value": 70}]}]},
}


def test_fetch_fnb_trends_sends_related_queries_data_type() -> None:
    """BẮT BUỘC gửi `data_type=RELATED_QUERIES`.

    Không có tham số này, SerpApi trả TIMESERIES → payload thiếu
    `related_queries` → hàm trả [] dù API 'thành công' (bug đã xác minh live).
    """
    with patch(
        "ca_agents.sources.gtrends_serpapi_source.search_serpapi",
        return_value=_RELATED_QUERIES_PAYLOAD,
    ) as mock_search:
        items = fetch_fnb_trends_serpapi("trà sữa", geo="VN")

    assert len(items) == 2, "phải parse được rising queries"
    params = mock_search.call_args.args[1]
    assert params["data_type"] == "RELATED_QUERIES"


def test_fetch_fnb_trends_empty_when_timeseries_payload() -> None:
    """Payload TIMESERIES (thiếu related_queries) → rỗng, KHÔNG bịa item."""
    with patch(
        "ca_agents.sources.gtrends_serpapi_source.search_serpapi",
        return_value=_TIMESERIES_ONLY_PAYLOAD,
    ):
        assert fetch_fnb_trends_serpapi("trà sữa", geo="VN") == []


def test_fetch_fnb_trends_include_timeline_makes_second_call() -> None:
    """`include_timeline=True` cần thêm 1 request TIMESERIES (tốn quota thêm)."""
    calls: list[dict[str, Any]] = []

    def _fake(engine: str, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(params))
        if params.get("data_type") == "TIMESERIES":
            return _TIMESERIES_ONLY_PAYLOAD
        return _RELATED_QUERIES_PAYLOAD

    with patch("ca_agents.sources.gtrends_serpapi_source.search_serpapi", side_effect=_fake):
        items = fetch_fnb_trends_serpapi("trà sữa", geo="VN", include_timeline=True)

    assert len(calls) == 2
    assert {c["data_type"] for c in calls} == {"RELATED_QUERIES", "TIMESERIES"}
    assert items, "phải vẫn trả được rising queries"


# ── Nguồn mới: Google Trends Trending Now (bảng xếp hạng cấp quốc gia) ────────
_TRENDING_NOW_REAL: dict[str, Any] = {
    "search_metadata": {"status": "Success"},
    "trending_searches": [
        {
            "query": "trà sữa viên viên hà nội",
            "start_timestamp": 1790245200,
            "active": True,
            "search_volume": 500000,
            "increase_percentage": 1000,
            "categories": [{"id": 22, "name": "Food & Drink"}],
            "trend_breakdown": ["quán trà sữa hà nội", "trà sữa viên viên"],
        },
        {
            "query": "himass",
            "start_timestamp": 1790139600,
            "active": True,
            "search_volume": 20000,
            "increase_percentage": 600,
            "categories": [{"id": 6, "name": "Games"}],
            "trend_breakdown": ["pubg", "krafton"],
        },
    ],
}


def test_parse_trending_now_reads_real_shape() -> None:
    """Fixture copy từ payload THẬT (probe 2026-09-24, geo=VN)."""
    items = parse_trending_now_payload(_TRENDING_NOW_REAL, geo="VN")
    assert len(items) == 2

    fnb = items[0]
    assert fnb.cum_tu_khoa_viral == "trà sữa viên viên hà nội"
    assert fnb.danh_muc == "am_thuc_fnb", "category Food & Drink → am_thuc_fnb"
    assert fnb.vong_doi == "moi_nhu", "+1000% → bùng nổ"
    assert fnb.nguon_goc == "google_vn"
    assert fnb.is_live_scraped is True
    assert "500.000" in fnb.luot_tiep_can
    assert "quán trà sữa hà nội" in fnb.trich_doan_noi_dung_that

    other = items[1]
    assert other.danh_muc != "am_thuc_fnb", "category Games → không phải F&B"


def test_parse_trending_now_tolerates_garbage() -> None:
    assert parse_trending_now_payload({}) == []
    assert parse_trending_now_payload({"trending_searches": "nope"}) == []
    assert parse_trending_now_payload({"trending_searches": [None, {}, {"query": "  "}]}) == []


def test_parse_trending_now_respects_max_items() -> None:
    items = parse_trending_now_payload(_TRENDING_NOW_REAL, geo="VN", max_items=1)
    assert len(items) == 1


def test_fetch_trending_now_uses_dedicated_engine() -> None:
    """Engine riêng `google_trends_trending_now` + TTL ngắn của chính nó."""
    with patch(
        "ca_agents.sources.gtrends_trending_now_source.search_serpapi",
        return_value=_TRENDING_NOW_REAL,
    ) as mock_search:
        items = fetch_trending_now_serpapi(geo="VN", count=1)

    assert len(items) == 1
    engine = mock_search.call_args.args[0]
    assert engine == "google_trends_trending_now"


def test_fetch_trending_now_returns_empty_on_error() -> None:
    """Lỗi/quota → trả [] để chuỗi rớt tầng, KHÔNG ném ra ngoài."""
    from ca_agents.clients.serpapi_client import SerpApiError

    with patch(
        "ca_agents.sources.gtrends_trending_now_source.search_serpapi",
        side_effect=SerpApiError("boom"),
    ):
        assert fetch_trending_now_serpapi(geo="VN") == []


def test_trending_now_classifies_by_category_name() -> None:
    """Phân loại theo TÊN category, KHÔNG theo ID (bảng ID không ổn định).

    Bug đã bắt được live 2026-09-24: `giá xăng dầu hôm nay` bị gán
    `am_thuc_fnb` khi dò theo ID category.
    """
    payload: dict[str, Any] = {
        "trending_searches": [
            {
                "query": "giá xăng dầu hôm nay",
                "search_volume": 10000,
                "increase_percentage": 400,
                "categories": [{"id": 1, "name": "Autos and Vehicles"}],
                "trend_breakdown": ["giá xăng"],
            },
            {
                "query": "món mới quán abc",
                "search_volume": 5000,
                "increase_percentage": 200,
                "categories": [{"id": 999, "name": "Food & Drink"}],
                "trend_breakdown": [],
            },
        ]
    }
    items = parse_trending_now_payload(payload, geo="VN")
    by_query = {i.cum_tu_khoa_viral: i for i in items}
    assert by_query["giá xăng dầu hôm nay"].danh_muc != "am_thuc_fnb"
    assert by_query["món mới quán abc"].danh_muc == "am_thuc_fnb"


# ── Lọc video Việt Nam trong feed TikWM ──────────────────────────────────────
def test_filter_vn_videos_drops_foreign() -> None:
    """`region=VN` của TikWM KHÔNG lọc thật → phải tự lọc, BỎ video nước ngoài.

    Đo live 2026-09-25: tỷ lệ VN chỉ 21–50%, có lần 1/20; phần còn lại là
    MM/TH/PK/US/ID/PH/KR/JP/UG/SG/GB. Hành vi cũ chỉ "ưu tiên VN lên đầu" nên
    video Thái/Myanmar vẫn lọt vào radar TikTok VN.
    """
    from ca_agents.ag_trend import _filter_vn_videos

    videos = [
        {"video_id": "1", "region": "MM"},
        {"video_id": "2", "region": "VN"},
        {"video_id": "3", "region": "TH"},
        {"video_id": "4", "region": "vn"},
        {"video_id": "5", "region": None},
        {"video_id": "6", "region": "US"},
    ]
    kept = _filter_vn_videos(videos)
    assert [v["video_id"] for v in kept] == ["2", "4"], "chỉ giữ VN, bỏ hẳn nước ngoài"


def test_filter_vn_videos_empty_when_no_vn() -> None:
    """Không có video VN (thực tế có lần 0/20) → trả [] để rớt tầng, KHÔNG trả bừa."""
    from ca_agents.ag_trend import _filter_vn_videos

    assert _filter_vn_videos([{"video_id": "1", "region": "MM"}]) == []


def test_fetch_tikwm_feed_vn_accumulates_and_dedupes() -> None:
    """Feed 1 lần không đủ video VN → gọi nhiều lần, khử trùng theo `video_id`."""
    import ca_agents.ag_trend as agt

    # Mỗi lần trả 1 phần VN + rác nước ngoài (mô phỏng đo thật: có lần 0 VN).
    batches = [
        [{"video_id": "a", "region": "MM"}, {"video_id": "b", "region": "VN"}],
        [{"video_id": "c", "region": "VN"}, {"video_id": "b", "region": "VN"}],  # b trùng
        [{"video_id": "d", "region": "VN"}, {"video_id": "e", "region": "TH"}],
    ]
    calls = {"n": 0}

    def _fake_feed() -> list[dict]:
        i = calls["n"]
        calls["n"] += 1
        return batches[min(i, len(batches) - 1)]

    with (
        patch.object(agt, "_fetch_tikwm_feed", side_effect=_fake_feed),
        patch.object(agt.time, "sleep"),
    ):
        videos = agt._fetch_tikwm_feed_vn(attempts=3)

    assert sorted(v["video_id"] for v in videos) == ["b", "c", "d"], (
        "tích luỹ qua nhiều lần, khử trùng, chỉ giữ VN"
    )


def test_fetch_tikwm_feed_vn_raises_when_all_attempts_fail() -> None:
    """Mọi lần gọi đều lỗi → raise lỗi cuối để caller ghi circuit breaker."""
    import ca_agents.ag_trend as agt

    with (
        patch.object(agt, "_fetch_tikwm_feed", side_effect=TimeoutError("down")),
        patch.object(agt.time, "sleep"),
        pytest.raises(TimeoutError),
    ):
        agt._fetch_tikwm_feed_vn(attempts=2)


def test_fetch_tikwm_feed_vn_returns_empty_when_only_foreign() -> None:
    """TikWM trả toàn video nước ngoài → [] (không raise, để rớt tầng sạch)."""
    import ca_agents.ag_trend as agt

    with (
        patch.object(
            agt, "_fetch_tikwm_feed", return_value=[{"video_id": "x", "region": "MM"}]
        ),
        patch.object(agt.time, "sleep"),
    ):
        assert agt._fetch_tikwm_feed_vn(attempts=2) == []
