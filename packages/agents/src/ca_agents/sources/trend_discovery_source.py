"""AG-TREND Discovery — tự phát hiện từ khoá trending MỚI mà không cần biết trước.

Vấn đề gốc:
    Search `"cà phê"` → trả bài bất kỳ, thứ tự ngẫu nhiên, không biết cái nào
    đang thịnh hành. Và ta không thể search `"bá khí"` nếu chưa biết nó tồn tại.

Cách giải (Trend Discovery Pipeline):
    ① COLLECT       Google News RSS với query "meta-keyword" (không khoá cứng)
    ② EXTRACT       bóc candidate từ tiêu đề/mô tả bài tổng hợp
    ③ SCORE         đo độ mạnh tín hiệu (số nguồn, tươi, novelty, F&B)
    ④ VERIFY        trả candidate đã xếp hạng để caller xác minh tiếp

Vì sao dùng BÁO CHÍ làm tầng phát hiện (không phải TikTok trực tiếp):
    - Báo chí có **bài tổng hợp** ("Top từ lóng 2026", "Loạt câu nói viral...")
      → 1 bài chứa nhiều candidate → hiệu quả cao hơn đếm n-gram caption.
    - Google News RSS miễn phí, không quota, không bị chặn.
    - Chứng minh thực nghiệm 2026-09-26: query `"câu nói viral TikTok tháng 9
      2026"` tìm được bài `"Bá khí" là gì? Nguồn gốc của meme...` (lag.vn,
      25/09/2026) — tức bắt được trend TRƯỚC khi ta biết từ khoá.

Tuân thủ: ADR-002 (điều phối tất định), ADR-003 (contracts-first),
ADR-008 (chỉ tín hiệu thật — candidate là GỢI Ý, không phải sự thật;
mọi candidate phải qua VERIFY trước khi thành trend chính thức).

Public API:
    build_discovery_queries(month, year) -> list[str]
    discover_candidates(...) -> list[TrendCandidate]
    extract_candidates(title, desc) -> list[str]      (hàm THUẦN)
    score_candidate(...) -> TrendCandidate            (hàm THUẦN)
"""

from __future__ import annotations

import html
import logging
import math
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger(__name__)

_SSL_CTX = ssl.create_default_context()
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

# ── Cấu hình qua env (pattern nhất quán với camoufox_client / serpapi_client) ──
# Ngưỡng discovery nên chỉnh được theo mùa (Tết nhiều trend hơn ngày thường)
# mà KHÔNG cần sửa code/deploy.
_DEFAULT_MAX_QUERIES = 14
_DEFAULT_MIN_MENTIONS = 2
_DEFAULT_MIN_SOURCES = 1
_DEFAULT_MAX_FRESHNESS_DAYS = 45.0
_DEFAULT_MAX_CANDIDATES = 20
_DEFAULT_MIN_CONFIDENCE = 0.0
# Nghỉ giữa 2 request RSS — tránh dồn dập 14 request liên tiếp tới Google News
# (lịch sự với nguồn miễn phí; audit 2026-09-26 đánh dấu đây là rủi ro).
_DEFAULT_QUERY_DELAY_S = 0.4


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# ── Circuit breaker (pattern nhất quán với các source khác) ──────────────────
_CB_FAILURE_THRESHOLD = 3
_CB_OPEN_SECONDS = 300.0
_CB_WINDOW_SECONDS = 60.0


class _SourceCircuitBreaker:
    """Circuit breaker đơn giản cho Google News RSS."""

    def __init__(self) -> None:
        self._failures: list[float] = []
        self._open_until: float = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self._open_until

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures = [t for t in self._failures if now - t <= _CB_WINDOW_SECONDS]
        self._failures.append(now)
        if len(self._failures) >= _CB_FAILURE_THRESHOLD:
            self._open_until = now + _CB_OPEN_SECONDS
            logger.warning(
                "discovery_circuit_breaker_opened failures=%d", len(self._failures)
            )

    def record_success(self) -> None:
        self._failures = []


_CB_GNEWS = _SourceCircuitBreaker()


# ══════════════════════════════════════════════════════════════════════════
# QUERY BUILDER — thay tháng tự động
# ══════════════════════════════════════════════════════════════════════════

# Từ khoá "meta" để bắt bài TỔNG HỢP (bài liệt kê nhiều từ khoá cùng lúc).
# Đây là điểm mấu chốt: 1 bài tổng hợp = nhiều candidate.
_LIST_MARKERS = (
    "loạt",
    "danh sách",
    "tổng hợp",
    "tuyển tập",
    "điểm lại",
    "lộ diện",
    "điểm mặt",
    "top",
    "những từ",
    "các từ",
    "từ điển",
)

# Chủ đề nhắm tới quán cà phê + giới trẻ.
_TOPIC_MARKERS = (
    "từ lóng",
    "slang",
    "câu nói",
    "meme",
    "trend",
    "bắt trend",
    "viral",
    "gen z",
    "giới trẻ",
    "tiktok",
    "threads",
)


def build_discovery_queries(
    month: int | None = None,
    year: int | None = None,
    include_previous_month: bool = True,
) -> list[str]:
    """Sinh bộ query phát hiện trend, có tháng tự động.

    ĐO THỰC NGHIỆM 2026-09-26 (xem docstring module):
        - Query CÓ tháng bắt được trend MỚI (`"Bá khí" ...` 25/09/2026).
        - Query KHÔNG tháng ra bài CŨ (2024/2025).
        - Nhưng KHÔNG phải query nào thêm tháng cũng tốt hơn — nên chạy cả hai
          và gộp kết quả rồi khử trùng.

    Args:
        month: tháng hiện tại (mặc định tháng hiện tại theo giờ hệ thống).
        year:  năm hiện tại.
        include_previous_month: có sinh thêm query cho tháng TRƯỚC không
            (trend đầu tháng vẫn còn nóng → cần quét cả tháng trước).

    Returns:
        Danh sách query Google News (chưa URL-encode).
    """
    now = datetime.now()
    m = month or now.month
    y = year or now.year
    pm, py = (m - 1, y) if m > 1 else (12, y - 1)

    cur_label = f"tháng {m}"
    prev_label = f"tháng {pm}"

    queries: list[str] = []

    # Nhóm 1 — CÓ tháng, KHÔNG ngoặc kép (bắt trend mới).
    #
    # ⚠️ ĐO THỰC NGHIỆM 2026-09-26 — bài học quan trọng:
    #   `"câu nói viral" TikTok` (CÓ ngoặc kép) → Google trả bài CŨ 82–436 ngày.
    #   `câu nói viral TikTok tháng 9 2026` (KHÔNG ngoặc kép) → trả bài MỚI
    #   trong ngày (vd `"Bá khí" là gì?` lag.vn 25/09/2026).
    #   Ngoặc kép khiến Google khớp CỤM CHÍNH XÁC ở tiêu đề → thiên về bài cũ
    #   đã được index lâu. Vì vậy nhóm quan trọng nhất KHÔNG dùng ngoặc kép.
    queries += [
        f"câu nói viral TikTok ({cur_label} OR {prev_label}) {y}",
        f"trend TikTok {cur_label} {y}",
        f"slang Gen Z {cur_label} {y}",
        f"từ lóng mới {cur_label} {y}",
        f"Nowtrending làn sóng viral {cur_label} {y}",
        f"meme mới {cur_label} {y}",
    ]
    if include_previous_month:
        queries += [
            f"loạt trend {prev_label} {y}",
            f"trend gây sốt {cur_label} {y}",
        ]

    # Nhóm 2 — không tháng, không ngoặc kép (bắt bài tổng hợp định kỳ).
    queries += [
        "loạt từ lóng Gen Z",
        "những từ lóng mạng xã hội",
        "cụm từ lóng Gen Z mạng xã hội Việt Nam",
        "từ vựng tiếng lóng TikTok Threads",
    ]

    # Nhóm 3 — bài TỔNG HỢP (1 bài = nhiều candidate).
    queries += [
        f"điểm lại từ lóng năm {y}",
        f"lộ diện slang top {y}",
        "top từ lóng mạng xã hội",
        f"tổng hợp trend TikTok {y}",
    ]

    # Khử trùng, giữ thứ tự.
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


# ══════════════════════════════════════════════════════════════════════════
# EXTRACT CANDIDATES — hàm THUẦN (test bằng fixture, không cần mạng)
# ══════════════════════════════════════════════════════════════════════════

# Rác từ HTML/RSS còn sót.
_JUNK_PATTERNS = (
    re.compile(r"^(target|href|src|class|style|rel)=", re.I),
    re.compile(r"^#?[0-9a-f]{6}$", re.I),  # mã màu #6f6f6f
    re.compile(r"^&?(gt|lt|amp|quot|nbsp);?$", re.I),
    re.compile(r"^https?://", re.I),
    # URL bị regex ngoặc kép bóc mất scheme (vd '//example.com').
    re.compile(r"^//[\w.-]+\.[a-z]{2,}", re.I),
    re.compile(r"^-?\s*(vn|vnexpress|kenh14|dân trí|tuổi trẻ|thanh niên)", re.I),
    # Tên báo / kỳ xuất bản lọt vào candidate (đo thật: "t11&12/2025 - advertising vietnam").
    re.compile(r"\b(advertising vietnam|brands vietnam|marketingai|genk|afamily|cellphones|fpt shop)\b", re.I),
    re.compile(r"^(t\d{1,2}|tháng\s*\d{1,2}|q[1-4]|quý\s*[1-4])\b.*\d{4}", re.I),
    # Số liệu doanh thu/kết quả không phải trend.
    re.compile(r"(doanh số|giải\s|tăng\s*\d+%|\d+%\s*(tăng|giảm))", re.I),
)

# Cụm bị coi là quá chung chung, không phải trend.
_GENERIC = {
    "gen z", "mạng xã hội", "giới trẻ", "tiktok", "threads", "viral",
    "xu hướng", "trend", "meme", "slang", "từ lóng", "hot trend",
    "bắt trend", "đu trend", "sao 24h", "dân mạng", "phải lòng",
    "bật mí", "phát sốt", "giải mã lý do",
    # Đo thật: các từ quá ngắn/chung lọt vào.
    "hot", "nét", "quà tặng", "xu hướng mới", "nổi bật", "đặc biệt",
    "từ điển", "danh sách", "danh sách nổi bật", "chủ đề", "sự kiện",
    "thịnh hành", "cộng đồng", "người dùng", "nội dung", "quảng cáo",
}

_QUOTED_RE = re.compile(r"[“\"']([^\"“”'\n]{3,40})[\"“”']")

# Mọi loại dấu nháy/ký tự bao mà báo VN dùng để đánh dấu từ lóng.
# Gồm nháy thẳng (', "), nháy cong (“ ” ‘ ’), guillemet (« »), và biến thể CJK.
_TRIM_CHARS = " \t.,-—–:;!?…\"'“”‘’«»「」『』()[]{}"


def _normalize_candidate(raw: str) -> str:
    """Chuẩn hoá 1 candidate về dạng so sánh được.

    ⚠️ AUDIT 2026-09-26 phát hiện 2 bug trước khi lên main:
      1. Nhánh "sau dấu hai chấm" chỉ `strip("\\"'")` → nháy CONG (“ ”) lọt qua:
         `'từ lóng: “x”, “y”'` → `['“x”', '“y”']` (còn cả nháy trong keyword).
      2. Vì (1), cùng 1 trend sinh 2 candidate (`bá khí` vs `“bá khí”`) → làm
         loãng kết quả và giảm `mention_count` thật.

    Hàm này bóc MỌI loại nháy ở hai đầu + gộp khoảng trắng, để
    `_normalize_candidate("“bá  khí”") == _normalize_candidate("bá khí")`.
    """
    s = re.sub(r"\s+", " ", str(raw)).strip()
    # Bóc lặp (vd `“'abc'”`) — tối đa vài vòng để tránh vòng lặp vô hạn.
    for _ in range(4):
        trimmed = s.strip(_TRIM_CHARS)
        if trimmed == s:
            break
        s = trimmed
    return re.sub(r"\s+", " ", s).strip()


def _is_junk(text: str) -> bool:
    t = _normalize_candidate(text)
    if not t:
        return True
    if any(p.search(t) for p in _JUNK_PATTERNS):
        return True
    if t.lower() in _GENERIC:
        return True
    # Phải có ký tự chữ.
    if not re.search(r"[^\W\d_]", t, re.UNICODE):
        return True
    # Quá dài thì không phải cụm từ khoá.
    if len(t) > 40:
        return True
    # Quá nhiều từ → là câu, không phải cụm trend.
    if len(t.split()) > 6:
        return True
    # Phải có ít nhất 2 ký tự (loại "x", "y", "z" trong câu liệt kê).
    if len(t) < 3:
        return True
    return False


def extract_candidates(title: str, desc: str = "") -> list[str]:
    """Hàm THUẦN: bóc candidate từ tiêu đề + mô tả 1 bài báo.

    Chiến lược (theo thứ tự tin cậy):
        1. Cụm trong NGOẶC KÉP — báo VN luôn đánh dấu từ lóng bằng `""`.
        2. Cụm sau dấu hai chấm trong tiêu đề (vd `Top từ lóng: A, B, C`).

    ĐO THỰC NGHIỆM: cách này bóc được `Bá khí`, `aura farming`,
    `bùa chống flop`, `chữa lành ví tiền`, `chốt đơn` từ bài thật.

    Hàm THUẦN + phòng thủ: input không phải `str` (None/int) → trả `[]`
    (AUDIT 2026-09-26: trước đây `extract_candidates(123)` ném `TypeError`).
    """
    if not isinstance(title, str):
        return []
    if not isinstance(desc, str):
        desc = ""

    blob = html.unescape(f"{title} {desc}")
    blob = re.sub(r"<[^>]+>", " ", blob)
    blob = re.sub(r"&[a-z]+;", " ", blob, flags=re.I)

    found: list[str] = []

    # 1. Trong ngoặc kép (mọi loại nháy — báo VN dùng cả nháy cong).
    for m in _QUOTED_RE.finditer(blob):
        cand = _normalize_candidate(m.group(1))
        if not _is_junk(cand):
            found.append(cand)

    # 2. Cụm sau dấu hai chấm (liệt kê).
    if ":" in title:
        after = title.split(":", 1)[1]
        for part in re.split(r"[,;]| và ", after):
            cand = _normalize_candidate(part)
            if not _is_junk(cand):
                found.append(cand)

    # Khử trùng (không phân biệt hoa/thường) — normalize trước khi so.
    seen: set[str] = set()
    out: list[str] = []
    for c in found:
        k = _normalize_candidate(c).lower()
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def is_list_article(title: str) -> bool:
    """True nếu bài có dấu hiệu TỔNG HỢP (liệt kê nhiều từ khoá)."""
    low = title.lower()
    return any(k in low for k in _LIST_MARKERS) or (
        low.count(",") >= 2 and any(k in low for k in _TOPIC_MARKERS)
    )


def is_topic_relevant(title: str) -> bool:
    """True nếu bài thuộc chủ đề trend/giới trẻ (lọc nhiễu)."""
    low = title.lower()
    return any(k in low for k in _TOPIC_MARKERS)


# ══════════════════════════════════════════════════════════════════════════
# SCORING — hàm THUẦN
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class TrendCandidate:
    """Một từ khoá tiềm năng do discovery phát hiện.

    ADR-008: đây là **GỢI Ý** (candidate), KHÔNG phải trend chính thức.
    Phải qua VERIFY (đối chiếu TikTok/Threads) trước khi thành trend.
    """

    keyword: str
    sources: list[str] = field(default_factory=list)
    sample_titles: list[str] = field(default_factory=list)
    first_seen: str = ""
    # Điểm thành phần
    mention_count: int = 0
    source_count: int = 0
    list_article_count: int = 0  # số lần xuất hiện trong BÀI TỔNG HỢP
    freshness_days: float = 999.0
    novelty: float = 0.0
    relevance: float = 0.0
    confidence: float = 0.0
    is_discovered: bool = True  # True = AI tự phát hiện, False = báo chí đã nói

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "mention_count": self.mention_count,
            "source_count": self.source_count,
            "list_article_count": self.list_article_count,
            "sources": self.sources,
            "freshness_days": round(self.freshness_days, 2),
            "novelty": round(self.novelty, 3),
            "relevance": round(self.relevance, 3),
            "confidence": round(self.confidence, 3),
            "is_discovered": self.is_discovered,
            "first_seen": self.first_seen,
            "sample_titles": self.sample_titles[:3],
        }


# Từ khoá quá phổ biến → novelty thấp (không phải trend mới).
_NOVELTY_PENALTY = {
    "chốt đơn", "đu trend", "bắt trend", "viral", "trend",
}


def score_candidate(
    keyword: str,
    sources: list[str],
    titles: list[str],
    freshness_days: float,
    fb_context: str = "",
    list_article_count: int = 0,
) -> TrendCandidate:
    """Hàm THUẦN: tính điểm cho 1 candidate.

    Công thức (tất định, giải thích được — ADR-002, không LLM):
        confidence = 0.30 * mention_factor
                   + 0.22 * source_factor
                   + 0.15 * freshness_factor
                   + 0.13 * novelty
                   + 0.10 * relevance
                   + 0.10 * list_article_boost

    ⚠️ ĐO THỰC NGHIỆM 2026-09-26:
    - Chỉ đếm `source_count` là SAI — nhiều bài tổng hợp cùng 1 báo vẫn là tín
      hiệu mạnh (vd `vuýp` 4 lần/1 nguồn).
    - `list_article_count`: candidate xuất hiện trong **bài tổng hợp**
      ("Top từ lóng...") có giá trị cao hơn bài lẻ — vì báo đã CHỦ ĐÍCH
      tổng hợp → độ tin cậy biên tập cao hơn.
    """
    uniq_sources = sorted({s.strip() for s in sources if s.strip()})
    n_src = len(uniq_sources)
    n_mention = len(titles)

    # mention_factor: 1 lần = 0.0, 2 lần = 0.33, 4 lần = 0.66, >=6 = 1.0.
    mention_factor = min(1.0, max(0.0, (n_mention - 1) / 5.0))

    # source_factor: 1 nguồn = 0.3, tăng dần, bão hoà ở ~1.0.
    source_factor = min(1.0, 0.3 * math.log2(n_src + 1) + 0.3)

    # freshness_factor: 0 ngày = 1.0, 45 ngày = 0.0.
    freshness_factor = max(0.0, 1.0 - (freshness_days / 45.0))

    # novelty: cụm càng "lạ" (không nằm trong danh sách phổ thông) càng cao.
    novelty = 0.2 if keyword.lower() in _NOVELTY_PENALTY else 0.8

    # relevance: liên quan F&B/quán thì cao hơn (heuristic từ khoá).
    blob = f"{keyword} {fb_context}".lower()
    fnb_kw = ("cà phê", "cafe", "trà", "matcha", "quán", "menu", "đồ uống",
              "ăn", "bánh", "kem", "nước", "food", "coffee")
    relevance = 1.0 if any(k in blob for k in fnb_kw) else 0.5

    # list_article_boost: xuất hiện trong bài tổng hợp = tín hiệu biên tập.
    list_boost = min(1.0, list_article_count / 2.0)

    confidence = (
        0.30 * mention_factor
        + 0.22 * source_factor
        + 0.15 * freshness_factor
        + 0.13 * novelty
        + 0.10 * relevance
        + 0.10 * list_boost
    )

    return TrendCandidate(
        keyword=keyword,
        sources=uniq_sources,
        sample_titles=titles[:3],
        mention_count=n_mention,
        source_count=n_src,
        list_article_count=list_article_count,
        freshness_days=freshness_days,
        novelty=novelty,
        relevance=relevance,
        confidence=round(confidence, 3),
    )


# ══════════════════════════════════════════════════════════════════════════
# COLLECT — gọi Google News RSS (có I/O)
# ══════════════════════════════════════════════════════════════════════════


def _fetch_gnews(query: str, timeout_s: int = 12, max_items: int = 40) -> list[dict[str, Any]]:
    """Gọi Google News RSS, trả list {title, desc, source, date}. [] nếu lỗi."""
    if not _CB_GNEWS.allow():
        logger.info("discovery_gnews_circuit_open_skipping")
        return []

    url = (
        f"{_GOOGLE_NEWS_RSS}?q={urllib.parse.quote(query)}&hl=vi&gl=VN&ceid=VN:vi"
    )
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout_s, context=_SSL_CTX) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001 — rớt tầng, không phá luồng
        logger.warning("discovery_gnews_failed query=%s error=%s", query[:60], e)
        _CB_GNEWS.record_failure()
        return []

    _CB_GNEWS.record_success()
    raw_items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    out: list[dict[str, Any]] = []
    for raw in raw_items[:max_items]:
        t = re.search(r"<title>(.*?)</title>", raw, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", raw, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", raw, re.DOTALL)
        src = re.search(r"<source[^>]*>(.*?)</source>", raw, re.DOTALL)
        out.append(
            {
                "title": html.unescape((t.group(1) if t else "").strip()),
                "desc": re.sub(
                    r"<[^>]+>", " ", html.unescape(desc.group(1) if desc else "")
                ).strip(),
                "source": (src.group(1) if src else "").strip(),
                "date": (d.group(1) if d else "").strip(),
            }
        )
    return out


def _age_days(pub_date: str) -> float:
    """Tuổi bài báo (ngày). Không parse được → 999 (coi như cũ)."""
    if not pub_date:
        return 999.0
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400.0)
    except Exception:  # noqa: BLE001
        return 999.0


def discover_candidates(
    month: int | None = None,
    year: int | None = None,
    max_queries: int | None = None,
    min_mentions: int | None = None,
    min_source_count: int | None = None,
    min_confidence: float | None = None,
    max_freshness_days: float | None = None,
    max_candidates: int | None = None,
    query_delay_s: float | None = None,
) -> list[TrendCandidate]:
    """Pipeline discovery: query → fetch → extract → score → xếp hạng.

    Mọi ngưỡng có thể truyền qua tham số HOẶC đặt env (tham số thắng env):
        `TREND_DISCOVERY_MAX_QUERIES`        (default 14)
        `TREND_DISCOVERY_MIN_MENTIONS`       (default 2)
        `TREND_DISCOVERY_MIN_SOURCES`        (default 1)
        `TREND_DISCOVERY_MAX_FRESHNESS_DAYS` (default 45)
        `TREND_DISCOVERY_MIN_CONFIDENCE`     (default 0.0)
        `TREND_DISCOVERY_MAX_CANDIDATES`     (default 20)
        `TREND_DISCOVERY_QUERY_DELAY_S`      (default 0.4 — nghỉ giữa 2 request)

    Raise KHÔNG ném ra ngoài — lỗi/quota → trả [] để chuỗi rớt tầng.

    Ngưỡng mặc định (đo thực nghiệm 2026-09-26 — corpus 146 bài/14 query):
        `min_mentions=2` — candidate phải xuất hiện ≥2 lần. Đo thật cho thấy
            đa số candidate chỉ 1–2 lần (trend mới chưa lan rộng); ngưỡng 3
            lọc sạch gần hết → mất tín hiệu SỚM (giá trị chính của discovery).
        `min_source_count=1` — nhiều bài tổng hợp cùng 1 báo vẫn tính.

    Returns:
        list[TrendCandidate] đã sắp xếp theo `confidence` giảm dần.
    """
    n_queries = max_queries if max_queries is not None else _env_int(
        "TREND_DISCOVERY_MAX_QUERIES", _DEFAULT_MAX_QUERIES
    )
    n_mentions = min_mentions if min_mentions is not None else _env_int(
        "TREND_DISCOVERY_MIN_MENTIONS", _DEFAULT_MIN_MENTIONS
    )
    n_sources = min_source_count if min_source_count is not None else _env_int(
        "TREND_DISCOVERY_MIN_SOURCES", _DEFAULT_MIN_SOURCES
    )
    n_fresh = max_freshness_days if max_freshness_days is not None else _env_float(
        "TREND_DISCOVERY_MAX_FRESHNESS_DAYS", _DEFAULT_MAX_FRESHNESS_DAYS
    )
    n_conf = min_confidence if min_confidence is not None else _env_float(
        "TREND_DISCOVERY_MIN_CONFIDENCE", _DEFAULT_MIN_CONFIDENCE
    )
    n_candidates = max_candidates if max_candidates is not None else _env_int(
        "TREND_DISCOVERY_MAX_CANDIDATES", _DEFAULT_MAX_CANDIDATES
    )
    delay = query_delay_s if query_delay_s is not None else _env_float(
        "TREND_DISCOVERY_QUERY_DELAY_S", _DEFAULT_QUERY_DELAY_S
    )

    queries = build_discovery_queries(month=month, year=year)[: max(0, n_queries)]

    # keyword(lower, đã normalize) -> {keyword, sources, titles, min_age, list_hits}
    acc: dict[str, dict[str, Any]] = {}

    for idx, q in enumerate(queries):
        if idx > 0 and delay > 0:
            time.sleep(delay)  # lịch sự với nguồn miễn phí (không dồn dập)
        for item in _fetch_gnews(q):
            title = str(item.get("title") or "")
            if not title or not is_topic_relevant(title):
                continue
            cands = extract_candidates(title, str(item.get("desc") or ""))
            if not cands:
                continue
            age = _age_days(str(item.get("date") or ""))
            raw_date = str(item.get("date") or "").strip()
            src = str(item.get("source") or "") or "không rõ"
            is_list = is_list_article(title)
            for c in cands:
                # Key dùng bản normalize → `“bá khí”` và `bá  khí` gộp làm một.
                key = _normalize_candidate(c).lower()
                if not key:
                    continue
                rec = acc.setdefault(
                    key,
                    {
                        "keyword": c,
                        "sources": [],
                        "titles": [],
                        "min_age": age,
                        "oldest_date": raw_date,
                        "list_hits": 0,
                    },
                )
                rec["sources"].append(src)
                rec["titles"].append(title)
                # `min_age` nhỏ nhất = bài MỚI nhất; `oldest_date` đi kèm nó để
                # `first_seen` phản ánh đúng "xuất hiện gần nhất khi nào".
                if age <= rec["min_age"]:
                    rec["min_age"] = age
                    rec["oldest_date"] = raw_date
                if is_list:
                    rec["list_hits"] += 1

    scored: list[TrendCandidate] = []
    for rec in acc.values():
        cand = score_candidate(
            keyword=rec["keyword"],
            sources=rec["sources"],
            titles=rec["titles"],
            freshness_days=float(rec["min_age"]),
            list_article_count=int(rec["list_hits"]),
        )
        cand.first_seen = str(rec["oldest_date"])
        if cand.mention_count < n_mentions:
            continue
        if cand.source_count < n_sources:
            continue
        if cand.confidence < n_conf:
            continue
        if cand.freshness_days > n_fresh:
            continue
        scored.append(cand)

    scored.sort(key=lambda c: -c.confidence)
    logger.info(
        "discovery_done queries=%d candidates=%d min_mentions=%d",
        len(queries),
        len(scored),
        n_mentions,
    )
    return scored[: max(0, n_candidates)]


__all__ = [
    "TrendCandidate",
    "build_discovery_queries",
    "discover_candidates",
    "extract_candidates",
    "is_list_article",
    "is_topic_relevant",
    "score_candidate",
]
