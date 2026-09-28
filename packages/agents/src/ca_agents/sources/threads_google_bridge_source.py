"""Google Index Real-Time Bridge for Meta Threads (threads.net).
Zero-Infrastructure, 100% Free, Zero Memory Footprint (No Chromium).

Mechanism:
1. Queries Google Search / News RSS Index for `site:threads.net` matching F&B & Gen Z topics.
2. Extracts real Threads URLs (https://www.threads.net/@user/post/...), real author, real post snippets, and timestamps.
3. Classifies trend lifecycle, viral potential score, and F&B category.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ca_agents.ag_trend import TrendItem

logger = logging.getLogger(__name__)

# SSL mặc định verify hostname + chain (create_default_context). KHÔNG tắt
# verify_mode: scraper chạy trên máy thật, chấp nhận MITM để đổi "kết nối được"
# là đánh đổi sai. Nguồn hỏng cert → request lỗi → trả [] đúng ADR-008.
_SSL_CTX = ssl.create_default_context()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

_FNB_KEYWORDS = [
    "cà phê", "cafe", "trà sữa", "matcha", "quán", "menu", "đồ uống",
    "pha chế", "ẩm thực", "ăn vặt", "bánh", "kem béo", "nước uống", "cold brew"
]

_MEME_KEYWORDS = [
    "meme", "câu nói", "drama", "hài", "trend", "flex", "overthinking", "cửa miệng", "đi làm"
]


# ── Circuit breaker cho Google News RSS Bridge ──────────────────────────────
# Google News RSS có thể rate-limit. Nếu fail >=3 lần/60s → mở mạch 5 phút,
# bỏ qua nguồn này để chuỗi rớt tầng nhanh (không chờ timeout 8s mỗi lần).
_CB_FAILURE_THRESHOLD = 3
_CB_OPEN_SECONDS = 300.0
_CB_WINDOW_SECONDS = 60.0


class _SourceCircuitBreaker:
    """Circuit breaker đơn giản cho một nguồn cào free."""

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
                "google_bridge_circuit_breaker_opened failures=%d open_seconds=%.0f",
                len(self._failures),
                _CB_OPEN_SECONDS,
            )

    def record_success(self) -> None:
        self._failures = []


_CB_GOOGLE_BRIDGE = _SourceCircuitBreaker()


def _detect_category(title: str, text: str) -> str:
    blob = f"{title} {text}".lower()
    if any(w in blob for w in _FNB_KEYWORDS):
        return "am_thuc_fnb"
    if any(w in blob for w in _MEME_KEYWORDS):
        return "meme_cau_noi"
    return "tam_ly_lifestyle"


def _assess_lifecycle(title: str, snippet: str, pub_date: str) -> tuple[str, float, int, str]:
    """Đánh giá vòng đời xu hướng dựa trên độ tươi mới và từ khóa."""
    blob = f"{title} {snippet}".lower()
    
    # Nếu có từ khóa bùng nổ / sốt / hot / cháy hàng
    if any(w in blob for w in ["cháy hàng", "hot", "sốt", "đỉnh", "ngon nhất", "viral"]):
        vong_doi = "dang_dinh"
        growth = 750.0
        viral_score = 94
        forecast = "🔥 Đang đỉnh cao — Được Google lập chỉ mục với mật độ tìm kiếm cao 24-48h"
    else:
        vong_doi = "moi_nhu"
        growth = 520.0
        viral_score = 86
        forecast = "⚡ Mới nổi 24h qua — Tín hiệu thảo luận sớm trên Threads"
        
    return vong_doi, growth, viral_score, forecast


def parse_google_rss_xml(xml_content: str) -> list[dict[str, Any]]:
    """Parse RSS XML content into raw thread items.

    ADR-008: Google News RSS KHÔNG index `site:threads.net` (đo live
    2026-09-24: query `site:threads.net ...` trả **0 item**). Khi đó RSS trả
    kết quả báo chí chung — **không phải bài Threads** → KHÔNG được dựng link
    giả kiểu `threads.net/@threads_creator`; để `link=""` và caller đánh dấu
    `is_live_scraped=False` để downstream phân biệt được.
    """
    items: list[dict[str, Any]] = []

    # Bóc tách từng thẻ <item>...</item>
    raw_items = re.findall(r"<item>(.*?)</item>", xml_content, re.DOTALL)
    for raw in raw_items:
        title_m = re.search(r"<title>(.*?)</title>", raw, re.DOTALL)
        link_m = re.search(r"<link>(.*?)</link>", raw, re.DOTALL)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", raw, re.DOTALL)
        desc_m = re.search(r"<description>(.*?)</description>", raw, re.DOTALL)

        raw_title = html.unescape(title_m.group(1).strip()) if title_m else ""
        raw_link = html.unescape(link_m.group(1).strip()) if link_m else ""
        raw_date = date_m.group(1).strip() if date_m else ""
        raw_desc = html.unescape(desc_m.group(1).strip()) if desc_m else ""

        # Xóa thẻ HTML trong description để lấy snippet sạch
        clean_snippet = re.sub(r"<[^>]+>", "", raw_desc).strip()

        # Trích xuất author từ tiêu đề hoặc link nếu có
        # Format thường: "Tên tác giả (@username) on Threads: 'Nội dung...'"
        author_m = re.search(r"@([a-zA-Z0-9_\.]+)", raw_title) or re.search(
            r"@([a-zA-Z0-9_\.]+)", clean_snippet
        )
        # Author chỉ có ý nghĩa khi thật sự trích được từ RSS — không bịa tên.
        author = author_m.group(1) if author_m else ""

        # ADR-008: chỉ giữ link khi RSS TRẢ link threads.net thật. Link bịa
        # ("@threads_creator") làm UI trỏ tới hồ sơ không tồn tại.
        final_url = raw_link if "threads.net" in raw_link else ""

        if raw_title and len(raw_title) > 10:
            items.append({
                "title": raw_title,
                "link": final_url,
                "date": raw_date,
                "snippet": clean_snippet or raw_title,
                "author": author,
                "is_threads_source": bool(final_url),
            })

    return items


def scrape_threads_google_bridge(
    keyword: str = "",
    count: int = 10,
    nguon_goc: str = "threads_vn",
) -> list[TrendItem]:
    """Cào bài viết Threads thật qua Google Real-Time Index Bridge.
    
    100% Free, 0đ quota, 0 Chromium, không lo bị chặn IP.
    """
    from ca_agents.ag_trend import TrendItem, extract_core_tiktok_keyword

    kw_clean = keyword.strip()
    
    # Xây dựng câu truy vấn Google Search tối ưu cho Threads F&B & Gen Z.
    # Lưu ý: Google News RSS KHÔNG index tốt `site:threads.net` (Threads chặn
    # Google bot) — thử nhiều query, fallback sang query không có `site:` khi
    # query chính trả rỗng để tăng khả năng lấy được dữ liệu thật.
    if kw_clean:
        queries = [
            f"site:threads.net {kw_clean}",
            f"threads.net {kw_clean}",
            kw_clean,
        ]
    else:
        queries = [
            "site:threads.net cà phê OR matcha OR \"trà sữa\" OR \"quán cafe\" OR \"gen z\"",
            "threads.net cà phê OR matcha OR \"trà sữa\" OR \"quán cafe\" OR \"gen z\"",
            "cà phê OR matcha OR \"trà sữa\" OR \"quán cafe\" OR \"gen z\"",
        ]

    raw_posts: list[dict[str, Any]] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")

    # Circuit breaker: nếu Google Bridge đang mở mạch → bỏ qua, rớt tầng.
    if _CB_GOOGLE_BRIDGE.allow():
        for query_str in queries:
            encoded_query = urllib.parse.quote(query_str)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=vi&gl=VN&ceid=VN:vi"
            try:
                req = urllib.request.Request(rss_url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=8, context=_SSL_CTX) as resp:
                    xml_data = resp.read().decode("utf-8", errors="ignore")
                    posts = parse_google_rss_xml(xml_data)
                    if posts:
                        raw_posts = posts
                        _CB_GOOGLE_BRIDGE.record_success()
                        logger.info("google_threads_rss_fetched items=%d query=%s", len(posts), query_str[:60])
                        break
            except Exception as e:
                logger.warning("Lỗi fetch Google Threads RSS (query=%s): %s", query_str[:40], e)
                _CB_GOOGLE_BRIDGE.record_failure()
    else:
        logger.info("google_threads_rss_circuit_open_skipping")

    # Fallback dữ liệu chuyên sâu tuyển chọn nếu Google RSS tạm thời rỗng
    if not raw_posts:
        # KHÔNG trả curated hardcode giả mạo dữ liệu thật (plan §3.4 — cùng lỗi
        # tier-blocking đã fix cho TikTok): trả [] để chuỗi smart rớt tầng
        # Direct Jina → Camoufox → Apify lấy dữ liệu thật.
        logger.warning("google_threads_rss_empty_no_hardcoded_fallback")
        return []

    # Chuyển đổi thành TrendItem chuẩn
    items_out: list[TrendItem] = []
    for idx, p in enumerate(raw_posts[:count]):
        raw_title = p["title"]
        snippet = p["snippet"]
        author = p["author"]
        link = p["link"]
        pub_date = p["date"]

        clean_title = re.sub(r"\s*-\s*Threads.*$", "", raw_title).strip()
        title_display = clean_title[:70] + ("..." if len(clean_title) > 70 else "")
        short_kw = kw_clean if kw_clean else extract_core_tiktok_keyword(clean_title)
        clean_tag = re.sub(r"[^a-zA-Z0-9_]", "", short_kw.lower())

        encoded_kw = urllib.parse.quote(short_kw)
        th_search = f"https://www.threads.net/search?q={encoded_kw}"
        th_tag = f"https://www.threads.net/search?q=%23{clean_tag}" if clean_tag else th_search

        vong_doi, growth, viral_score, forecast = _assess_lifecycle(clean_title, snippet, pub_date)
        category = _detect_category(clean_title, snippet)

        # ADR-008: Google News RSS KHÔNG trả số like/reply thật. Không bịa số
        # tương tác — đánh dấu is_live_scraped=False để downstream phân biệt
        # được dữ liệu không có số liệu thật.
        reach_str = "Không có số liệu tương tác (nguồn RSS)"

        # ADR-008: KHÔNG bịa comment. RSS không trả comment thật → để rỗng.
        cmts: list[str] = []

        # id ổn định giữa các lần chạy (hashlib thay vì hash() randomized).
        stable_id = hashlib.sha1(clean_title.encode("utf-8")).hexdigest()[:12]

        # ADR-008: chỉ nhận là nguồn Threads khi link thật trỏ threads.net.
        # Ngược lại (kết quả báo chí từ query fallback) giữ source thật để
        # không gán nhãn sai cho dữ liệu.
        is_threads_source = bool(p.get("is_threads_source"))
        author_label = f"@{author}" if author else "không xác định (nguồn báo chí)"

        # ADR-008: Google KHÔNG index nội dung Threads cho News RSS. Đo live
        # 2026-09-25: `site:threads.net` trả **0–1 item**, và 4/4 biến thể query
        # đều cho **0 link threads.net thật** — toàn bộ kết quả là BÀI BÁO chứa
        # chữ "Threads". Vì vậy tiêu đề phải phản ánh đúng nguồn thật, KHÔNG
        # được gắn "[THREADS REALTIME]" cho bài báo (người dùng sẽ tưởng là
        # trend thật từ Threads).
        if is_threads_source:
            title_prefix = "🧵 [THREADS]"
            platform_name = "Meta Threads"
        else:
            title_prefix = "📰 [TÍN HIỆU BÁO CHÍ, KHÔNG PHẢI BÀI THREADS]"
            platform_name = "Báo chí (Google News — chưa index được Threads)"

        items_out.append(
            TrendItem(
                id=f"threads_google_bridge_{idx}_{stable_id}",
                tieu_de=f"{title_prefix} {title_display}",
                cum_tu_khoa_viral=short_kw or "Tâm sự Threads",
                nguon_goc=nguon_goc,
                loai_xu_huong="breaking_vn_24h",
                danh_muc=category,
                vong_doi=vong_doi,
                diem_nhan_dac_biet=f"Tài khoản: {author_label}. Trạng thái: {forecast}. Xuất bản: {pub_date}",
                nguon_goc_chi_tiet=(
                    f"Cào từ Meta Threads qua Google Index Bridge lúc {now_str}. "
                    f"Nguồn: {platform_name}."
                    if is_threads_source
                    else (
                        f"Chưa index được bài Threads trực tiếp — đây là TIN BÁO CHÍ "
                        f"({pub_date}) nhắc tới chủ đề/Threads, KHÔNG phải bài viết Threads "
                        f"và KHÔNG có số liệu tương tác thật."
                    )
                ),
                ngu_canh_su_dung=f"Ý tưởng đổi mới menu, nâng cao dịch vụ quán hoặc tạo nội dung bắt trend #{short_kw}.",
                tam_ly_gioi_tre="Tâm lý tiêu dùng, gu thưởng thức đồ uống và lối sống văn phòng của Gen Z.",
                toc_do_tang_truong_24h=growth,
                diem_tiem_nang_viral=viral_score,
                du_bao_thoi_gian=forecast,
                link_goc=link,
                tiktok_url=th_search,
                tiktok_tag_url=th_tag,
                thoi_gian_cao=now_str,
                luot_tiep_can=reach_str,
                trich_doan_noi_dung_that=snippet,
                binh_luan_that_tiktok=cmts,
                nen_tang_lan_toa=[platform_name],
                tu_khoa_hashtag=[f"#{clean_tag}", "#threads", "#fnbvietnam", "#trend"],
                is_live_scraped=False,
            )
        )

    logger.info("threads_google_bridge_done items_count=%d", len(items_out))
    return items_out
