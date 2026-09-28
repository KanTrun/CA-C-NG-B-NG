# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test trend_discovery_source — Trend Discovery Pipeline (không mở mạng thật).

Bối cảnh: ý tưởng "AI tự phát hiện từ khoá trending mà KHÔNG biết trước".
Chuỗi: query meta-keyword (có tháng) → Google News RSS → extract candidate
→ score → xếp hạng.

Fixture dùng TIÊU ĐỀ THẬT thu được khi đo live 2026-09-26, để nếu báo đổi
cách viết thì test fail ngay thay vì âm thầm mất tín hiệu.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ca_agents.sources import trend_discovery_source as src
from ca_agents.sources.trend_discovery_source import (
    TrendCandidate,
    build_discovery_queries,
    discover_candidates,
    extract_candidates,
    is_list_article,
    is_topic_relevant,
    score_candidate,
)


@pytest.fixture(autouse=True)
def _no_query_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test không ngủ giữa các query (delay chỉ dành cho chạy thật).

    Đồng thời CÔ LẬP env: nếu `.env` thật lọt vào (xem ghi chú repo về
    `ensure_dotenv`) thì ngưỡng có thể đổi → test phụ thuộc thứ tự chạy.
    Xoá mọi biến discovery trước mỗi test để kết quả tất định.
    """
    for name in (
        "TREND_DISCOVERY_MAX_QUERIES",
        "TREND_DISCOVERY_MIN_MENTIONS",
        "TREND_DISCOVERY_MIN_SOURCES",
        "TREND_DISCOVERY_MIN_CONFIDENCE",
        "TREND_DISCOVERY_MAX_FRESHNESS_DAYS",
        "TREND_DISCOVERY_MAX_CANDIDATES",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TREND_DISCOVERY_QUERY_DELAY_S", "0")

# ── build_discovery_queries ──────────────────────────────────────────────────


def test_build_queries_has_month_params() -> None:
    """Query phải chứa THÁNG hiện tại + tháng trước (đo thật: bắt trend mới)."""
    qs = build_discovery_queries(month=9, year=2026)
    blob = " ".join(qs)
    assert "tháng 9" in blob
    assert "tháng 8" in blob  # tháng trước
    assert "2026" in blob


def test_build_queries_handles_january() -> None:
    """Tháng 1 → tháng trước là tháng 12 NĂM NGOÁI (không phải tháng 0)."""
    qs = build_discovery_queries(month=1, year=2026)
    blob = " ".join(qs)
    assert "tháng 12" in blob
    assert "tháng 0" not in blob


def test_build_queries_avoids_exact_quotes_for_fresh() -> None:
    """⚠️ Bài học đo thật: ngoặc kép → Google trả bài CŨ (82–436 ngày).

    Nhóm query quan trọng nhất (có tháng) KHÔNG được dùng `"..."` cụm chính xác,
    nếu không sẽ mất khả năng bắt trend mới.
    """
    qs = build_discovery_queries(month=9, year=2026)
    fresh_queries = [q for q in qs if "tháng" in q]
    assert fresh_queries, "phải có nhóm query theo tháng"
    assert all('"' not in q for q in fresh_queries), (
        "query theo tháng không được có ngoặc kép (làm Google trả bài cũ)"
    )


def test_build_queries_deduped() -> None:
    qs = build_discovery_queries(month=9, year=2026)
    assert len(qs) == len(set(qs))


# ── extract_candidates (hàm THUẦN) ───────────────────────────────────────────


def test_extract_candidates_captures_bakhi() -> None:
    """Bắt được `Bá khí` từ tiêu đề THẬT — đây là ví dụ người dùng nêu."""
    title = '“Bá khí” là gì? Nguồn gốc của meme đang phủ sóng mạng xã hội'
    assert extract_candidates(title, "") == ["Bá khí"]


def test_extract_candidates_from_list_article() -> None:
    """Bài tổng hợp: nhiều cụm trong ngoặc kép → nhiều candidate 1 lượt."""
    title = "Top từ lóng thống trị mạng xã hội"
    desc = 'Gồm "aura farming", "bùa chống flop" và "chữa lành ví tiền".'
    cands = extract_candidates(title, desc)
    assert "aura farming" in cands
    assert "bùa chống flop" in cands
    assert "chữa lành ví tiền" in cands


def test_extract_candidates_from_multiple_quotes_in_title() -> None:
    """Tiêu đề kiểu liệt kê nhiều cụm trong ngoặc kép (THẬT từ MarketingAI)."""
    title = '“8386 mãi đỉnh”, “Vì tinh tú J97”, “Ai sợ thì đi về”: Nhìn lại...'
    cands = extract_candidates(title, "")
    assert "8386 mãi đỉnh" in cands
    assert "Vì tinh tú J97" in cands
    assert "Ai sợ thì đi về" in cands


def test_extract_candidates_rejects_junk() -> None:
    """Rác HTML/RSS + tên báo + mã màu không được thành candidate."""
    junk_values = [
        "target=",
        "#6f6f6f",
        "&gt;",
        "https://example.com",
        "t11&12/2025 - advertising vietnam",
        "doanh số tăng 43%",
        "Brands Vietnam",
    ]
    for junk in junk_values:
        quoted = '"' + junk + '"'
        assert extract_candidates(quoted, "") == [], f"{junk!r} phải bị loại"


def test_extract_candidates_rejects_generic() -> None:
    """Từ chung chung ('hot', 'gen z', 'mạng xã hội') không phải trend."""
    for generic in ("hot", "Gen Z", "mạng xã hội", "trend", "nét", "quà tặng"):
        assert extract_candidates(f'"{generic}"', "") == []


def test_extract_candidates_empty_input() -> None:
    assert extract_candidates("", "") == []
    assert extract_candidates("Không có ngoặc kép nào ở đây", "") == []


def test_extract_candidates_dedupes_case_insensitive() -> None:
    title = '“Bá khí” và “bá khí” là cùng một từ'
    assert extract_candidates(title, "") == ["Bá khí"]


# ── Regression (AUDIT 2026-09-26) — các lỗi bắt được khi rà soát SOTA ────────


def test_extract_candidates_non_str_returns_empty() -> None:
    """Input không phải `str` (None/int) → `[]`, KHÔNG ném `TypeError`.

    AUDIT: trước đây `extract_candidates(123)` ném
    `TypeError: argument of type 'int' is not iterable`.
    """
    assert extract_candidates(123, "") == []  # type: ignore[arg-type]
    assert extract_candidates(None, "") == []  # type: ignore[arg-type]
    # `desc` sai kiểu cũng không được làm chết hàm.
    assert "Bá khí" in extract_candidates('"Bá khí"', 999)  # type: ignore[arg-type]


def test_extract_candidates_strips_curly_quotes() -> None:
    """Nháy CONG (`“ ”`) của báo VN phải bị bóc — không để lọt `“bá khí”`.

    AUDIT: trước đây `'từ lóng: “x”, “y”'` → `['“x”', '“y”']` (giữ nháy).
    """
    cands = extract_candidates('Từ lóng: \u201cbá khí\u201d, \u201caura farming\u201d', "")
    assert cands == ["bá khí", "aura farming"]
    assert all("\u201c" not in c and "\u201d" not in c for c in cands)


def test_extract_candidates_dedupes_whitespace_variants() -> None:
    """`bá   khí` (nhiều dấu cách) và `bá khí` phải gộp làm một.

    AUDIT: trước đây dedup theo `.lower()` thô → lọt trùng.
    """
    title = 'Bá khí là gì'
    desc = 'trend "bá   khí" đang nổi'
    assert extract_candidates(title, desc) == ["bá khí"]


def test_extract_candidates_rejects_too_short() -> None:
    """Cụm 1–2 ký tự (`x`, `y`, `ok`) không phải trend.

    AUDIT: trước đây `len(t) < 3` không bị chặn.
    """
    cands = extract_candidates('List: "x", "y", "ab", "bá khí"', "")
    assert cands == ["bá khí"]


# ── is_list_article / is_topic_relevant ──────────────────────────────────────


def test_is_list_article() -> None:
    assert is_list_article("Top từ lóng thống trị mạng xã hội") is True
    assert is_list_article("Lộ diện 20 Slang lọt top WeYoung") is True
    assert is_list_article("Tuyển tập Social Slang đang hot") is True
    assert is_list_article("Giá xăng tăng mạnh hôm nay") is False


def test_is_topic_relevant() -> None:
    assert is_topic_relevant('“Bá khí” là gì? Nguồn gốc meme') is True
    assert is_topic_relevant("Top từ lóng thống trị mạng xã hội") is True
    assert is_topic_relevant("Giá vàng hôm nay tăng sốc") is False


# ── score_candidate (hàm THUẦN) ──────────────────────────────────────────────


def test_score_prefers_more_sources() -> None:
    """Nhiều nguồn độc lập → điểm cao hơn (tín hiệu mạnh hơn)."""
    one = score_candidate("x", ["A"], ["t1"], freshness_days=1)
    three = score_candidate("x", ["A", "B", "C"], ["t1", "t2", "t3"], freshness_days=1)
    assert three.confidence > one.confidence
    assert three.source_count == 3


def test_score_prefers_fresh() -> None:
    """Bài mới → điểm cao hơn bài cũ (cùng nguồn)."""
    fresh = score_candidate("x", ["A", "B"], ["t"], freshness_days=1)
    old = score_candidate("x", ["A", "B"], ["t"], freshness_days=40)
    assert fresh.confidence > old.confidence


def test_score_list_article_boost() -> None:
    """Xuất hiện trong bài TỔNG HỢP → boost (báo chủ đích tổng hợp)."""
    plain = score_candidate("x", ["A", "B"], ["t1", "t2"], freshness_days=1)
    listed = score_candidate(
        "x", ["A", "B"], ["t1", "t2"], freshness_days=1, list_article_count=2
    )
    assert listed.confidence > plain.confidence
    assert listed.list_article_count == 2


def test_score_fnb_relevance_boost() -> None:
    """Từ khoá liên quan F&B → relevance cao hơn."""
    fnb = score_candidate("cà phê muối", ["A"], ["t"], freshness_days=1)
    other = score_candidate("bóng đá", ["A"], ["t"], freshness_days=1)
    assert fnb.relevance == 1.0
    assert other.relevance == 0.5


def test_score_confidence_bounded() -> None:
    """Điểm phải nằm trong [0, 1] — không vượt thang."""
    c = score_candidate(
        "x", ["A", "B", "C", "D", "E"], [f"t{i}" for i in range(20)],
        freshness_days=0, list_article_count=5,
    )
    assert 0.0 <= c.confidence <= 1.0


def test_candidate_to_dict() -> None:
    c = TrendCandidate(keyword="bá khí", sources=["SOHA"], mention_count=3)
    d = c.to_dict()
    assert d["keyword"] == "bá khí"
    assert d["mention_count"] == 3
    assert d["is_discovered"] is True


# ── discover_candidates (pipeline, mock _fetch_gnews) ────────────────────────


def _fake_gnews(query: str) -> list[dict]:
    """Trả item giả theo query — mô phỏng corpus THẬT."""
    if "câu nói viral" in query:
        return [
            {
                "title": '“Bá khí” là gì? Nguồn gốc của meme đang phủ sóng mạng xã hội',
                "desc": "",
                "source": "lag.vn",
                "date": "Fri, 25 Sep 2026 09:24:00 GMT",
            },
            {
                "title": '“Bá khí” viral khắp TikTok',
                "desc": "",
                "source": "soha.vn",
                "date": "Thu, 24 Sep 2026 08:00:00 GMT",
            },
            {
                "title": 'Giải mã “bá khí” trong giới trẻ',
                "desc": "",
                "source": "kenh14.vn",
                "date": "Wed, 23 Sep 2026 08:00:00 GMT",
            },
        ]
    if "tổng hợp" in query:
        return [
            {
                "title": "Top từ lóng thống trị mạng xã hội",
                "desc": 'Gồm "aura farming", "bùa chống flop".',
                "source": "Advertising Vietnam",
                "date": "Tue, 22 Sep 2026 08:00:00 GMT",
            }
        ]
    return []


def test_discover_ranks_by_confidence() -> None:
    """Pipeline: gộp nhiều query → xếp theo confidence giảm dần."""
    with patch.object(src, "_fetch_gnews", side_effect=_fake_gnews):
        cands = discover_candidates(max_queries=14, min_mentions=1)
    assert cands, "phải tìm được candidate từ corpus giả"
    confs = [c.confidence for c in cands]
    assert confs == sorted(confs, reverse=True), "phải xếp giảm dần"
    kw = {c.keyword for c in cands}
    assert "Bá khí" in kw, "phải bắt được Bá khí (3 nguồn, 3 lần)"


def test_discover_min_mentions_filters() -> None:
    """min_mentions lọc candidate xuất hiện quá ít."""
    with patch.object(src, "_fetch_gnews", side_effect=_fake_gnews):
        all_c = discover_candidates(max_queries=14, min_mentions=1)
        few = discover_candidates(max_queries=14, min_mentions=3)
    assert len(few) <= len(all_c)
    assert all(c.mention_count >= 3 for c in few)


def test_discover_max_freshness_filters_old() -> None:
    """Bài cũ hơn max_freshness_days → loại (đo thật: ngoặc kép → bài 436 ngày)."""
    with patch.object(src, "_fetch_gnews", side_effect=_fake_gnews):
        fresh = discover_candidates(max_queries=14, min_mentions=1, max_freshness_days=45)
        allc = discover_candidates(max_queries=14, min_mentions=1, max_freshness_days=99999)
    assert all(c.freshness_days <= 45 for c in fresh)
    assert len(fresh) <= len(allc)


def test_discover_returns_empty_on_fetch_failure() -> None:
    """_fetch_gnews lỗi → trả [] (rớt tầng), KHÔNG ném ra ngoài."""
    with patch.object(src, "_fetch_gnews", return_value=[]):
        assert discover_candidates(max_queries=3) == []


def test_discover_circuit_breaker_skips() -> None:
    """Circuit breaker mở → bỏ qua fetch, trả [] nhanh."""
    src._CB_GNEWS._open_until = float("inf")
    try:
        with patch.object(src, "_fetch_gnews", wraps=src._fetch_gnews):
            out = discover_candidates(max_queries=2)
        assert out == []
    finally:
        src._CB_GNEWS._open_until = 0.0


# ── Env config + delay (AUDIT 2026-09-26 item E/F) ───────────────────────────


def test_env_config_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env phải điều khiển được ngưỡng (mùa Tết cần siết/nới)."""
    monkeypatch.setenv("TREND_DISCOVERY_MAX_QUERIES", "2")
    monkeypatch.setenv("TREND_DISCOVERY_MIN_MENTIONS", "99")
    seen: list[str] = []

    def _fake(query: str) -> list[dict[str, str]]:
        seen.append(query)
        return [
            {
                "title": '“Bá khí” viral khắp TikTok',
                "desc": "",
                "source": "kenh14.vn",
                "date": "Fri, 25 Sep 2026 09:24:00 GMT",
            }
        ]

    with patch.object(src, "_fetch_gnews", side_effect=_fake):
        out = discover_candidates(month=9, year=2026)
    assert len(seen) == 2, "MAX_QUERIES=2 phải giới hạn còn 2 query"
    assert out == [], "MIN_MENTIONS=99 phải lọc sạch"


def test_explicit_arg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tham số hàm thắng env."""
    monkeypatch.setenv("TREND_DISCOVERY_MAX_QUERIES", "99")
    seen: list[str] = []

    def _fake(query: str) -> list[dict[str, str]]:
        seen.append(query)
        return []

    with patch.object(src, "_fetch_gnews", side_effect=_fake):
        discover_candidates(month=9, year=2026, max_queries=1)
    assert len(seen) == 1


def test_env_config_tolerates_bad_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env rác (`abc`) → rơi về default, KHÔNG ném `ValueError`."""
    monkeypatch.setenv("TREND_DISCOVERY_MAX_QUERIES", "abc")
    monkeypatch.setenv("TREND_DISCOVERY_MAX_FRESHNESS_DAYS", "not-a-number")
    with patch.object(src, "_fetch_gnews", return_value=[]):
        assert discover_candidates(month=9, year=2026) == []


def test_query_delay_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Query thứ 2 trở đi phải nghỉ `delay` giây (lịch sự với nguồn miễn phí)."""
    monkeypatch.setenv("TREND_DISCOVERY_QUERY_DELAY_S", "0.5")
    sleeps: list[float] = []
    monkeypatch.setattr(src.time, "sleep", lambda s: sleeps.append(s))
    with patch.object(src, "_fetch_gnews", return_value=[]):
        discover_candidates(month=9, year=2026, max_queries=3)
    assert sleeps == [0.5, 0.5], "3 query → nghỉ 2 lần (không nghỉ trước query đầu)"


def test_no_sleep_before_first_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """KHÔNG nghỉ trước query đầu — tránh chậm vô ích."""
    sleeps: list[float] = []
    monkeypatch.setattr(src.time, "sleep", lambda s: sleeps.append(s))
    with patch.object(src, "_fetch_gnews", return_value=[]):
        discover_candidates(month=9, year=2026, max_queries=1, query_delay_s=1.0)
    assert sleeps == []


# ── Gộp 2 tầng trend (Trending Now + Discovery) ──────────────────────────────


def _ti(keyword: str):  # type: ignore[no-untyped-def]
    """TrendItem tối thiểu để test hàm gộp."""
    from ca_agents.ag_trend import TrendItem

    return TrendItem(
        id=f"x_{keyword}",
        tieu_de=f"t_{keyword}",
        cum_tu_khoa_viral=keyword,
        nguon_goc="google_vn",
        loai_xu_huong="breaking_vn_24h",
        danh_muc="am_thuc_fnb",
        vong_doi="moi_nhu",
        diem_nhan_dac_biet="",
        nguon_goc_chi_tiet="",
        ngu_canh_su_dung="",
        tam_ly_gioi_tre="",
        toc_do_tang_truong_24h=1.0,
        diem_tiem_nang_viral=1,
        du_bao_thoi_gian="",
    )


def test_merge_layers_keeps_both() -> None:
    """Gộp giữ CẢ HAI tầng — Trending Now (tìm kiếm) + Discovery (slang/meme).

    Regression: trước đây `_scrape_google_trends_vn` `return` ngay sau Trending
    Now → Discovery không bao giờ chạy (đo live: `discovery_` count = 0).
    """
    from ca_agents.ag_trend import _merge_trend_layers

    primary = [_ti("fpt play"), _ti("bão áp thấp nhiệt đới")]
    secondary = [_ti("bá khí"), _ti("thánh meme")]

    merged = _merge_trend_layers(primary, secondary)
    keys = [m.cum_tu_khoa_viral for m in merged]
    assert keys == ["fpt play", "bão áp thấp nhiệt đới", "bá khí", "thánh meme"]
    assert len(merged) == 4


def test_merge_layers_dedupes_case_insensitive() -> None:
    """Trùng cụm (khác hoa/thường) chỉ giữ bản ĐẦU (tầng primary thắng)."""
    from ca_agents.ag_trend import _merge_trend_layers

    primary = [_ti("Bá Khí")]
    secondary = [_ti("bá khí"), _ti("thánh meme")]

    merged = _merge_trend_layers(primary, secondary)
    assert [m.cum_tu_khoa_viral for m in merged] == ["Bá Khí", "thánh meme"]


def test_merge_layers_skips_empty_keyword() -> None:
    """Item có cụm từ khoá rỗng bị bỏ (không tạo trùng giả)."""
    from ca_agents.ag_trend import _merge_trend_layers

    merged = _merge_trend_layers([_ti("")], [_ti("bá khí")])
    assert [m.cum_tu_khoa_viral for m in merged] == ["bá khí"]


def test_merge_layers_handles_both_empty() -> None:
    """Cả hai tầng rỗng → [] (caller rớt tầng tiếp)."""
    from ca_agents.ag_trend import _merge_trend_layers

    assert _merge_trend_layers([], []) == []
