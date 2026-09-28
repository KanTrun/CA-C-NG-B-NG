"""Cào Threads search bằng Camoufox (browser thật chống-detect) → list[TrendItem].

Tier browser-thật miễn phí, chèn GIỮA Jina direct và Apify trong chuỗi
`_scrape_threads_smart` (ag_trend.py). Threads public search render được
không cần login — Camoufox vượt checkpoint Meta tốt hơn urllib + UA hard-code.

Thiết kế tách bạch (plan §3.4, nhất quán §3.3):
    - fetch_threads_page(page, keyword)  — chờ SPA render, trả HTML trang.
    - extract_threads_items(html, ...)    — hàm THUẦN, test bằng fixture HTML tĩnh.
    - scrape_threads_camoufox(...)        — orchestrate qua camoufox_client.scrape_page
                                             + cache TTL CA_CAMOUFOX_CACHE_TTL_S.

Tái dùng từ source có sẵn (KHÔNG copy code — plan §3.4):
    - `_detect_category`, `_assess_trend_lifecycle` từ threads_direct_source.
    - `_parse_count` (parser "12.3K"/"1.2M" CHUNG) từ tiktok_camoufox_source.

Login-wall (plan §3.4): nếu Threads redirect về màn login → coi như
`CamoufoxUnavailable` cho lần gọi đó, rớt tầng NGAY, không cố đăng nhập
hay vượt qua (đúng ranh giới phạm vi cào plan §2.3).

Public API:
    scrape_threads_camoufox(keyword, count, nguon_goc) -> list[TrendItem]
    Raise CamoufoxUnavailable nếu chưa cài/fetch/thiếu system deps/login-wall
    → caller rớt tầng.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ca_agents.clients.camoufox_client import scrape_page
from ca_agents.sources.threads_direct_source import _assess_trend_lifecycle, _detect_category
from ca_agents.sources.tiktok_camoufox_source import _parse_count

if TYPE_CHECKING:
    from ca_agents.ag_trend import TrendItem

logger = logging.getLogger(__name__)

_POST_SELECTOR = "a[href*='/post/']"
# Cho split HTML khi cần (dùng khi không có Playwright page).
_POST_ATTR = "a[href*='/post/']"

# ⚠️ ĐO THẬT 2026-09-26: Threads **KHÔNG có** `data-e2e` cho post, và class CSS
# là hash React obfuscated (`xrvj5dj xd0jker`, đổi mỗi build) — selector cũ
# `[data-e2e='search-result-post']` trả **0 node** nên tier Threads Camoufox
# chưa bao giờ lấy được bài nào. Cách ổn định duy nhất: tìm link `/@user/post/id`
# rồi leo lên tổ tiên SÂU NHẤT mà `innerText` bắt đầu bằng username (tránh leo
# tới container chứa cả bài kế tiếp).
_JS_EXTRACT_POSTS = r"""
() => {
  const TIME_RE = /^\d+\s*(giây|phút|giờ|ngày|tuần|tháng|năm|s|m|h|d|w|y)$/i;
  const NUM_RE = /^[\d.,]+\s*[KMB]?$/i;
  const PID_RE = /\/post\/([\w\-]+)/;
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/post/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/^\/@([\w.\-]+)\/post\/([\w\-]+)/);
    if (!m) continue;
    if (seen.has(m[2])) continue;
    seen.add(m[2]);

    // Leo lên tìm container RỘNG NHẤT mà vẫn chỉ chứa DUY NHẤT bài này.
    //
    // ⚠️ ĐO THẬT 2026-09-26: bài có ảnh/video có **2 link** cùng post_id
    // (`/post/<id>` và `/post/<id>/media`). Nếu đếm SỐ LINK thì gặp >1 là
    // dừng → container chỉ còn phần media, `innerText` rỗng → mất hẳn nội dung
    // (3/5 bài bị mất). Phải đếm SỐ POST_ID KHÁC NHAU thì ancestor chung của
    // text + media (vẫn 1 bài) mới được chọn.
    let node = a, container = null;
    for (let i = 0; i < 14 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const ids = new Set();
      for (const x of node.querySelectorAll('a[href*="/post/"]')) {
        const mm = (x.getAttribute('href') || '').match(PID_RE);
        if (mm) ids.add(mm[1]);
      }
      if (ids.size > 1) break;              // đã sang bài khác → dừng
      const txt = node.innerText || '';
      if (txt.includes(m[1])) container = node;
    }

    const txt = container ? (container.innerText || '') : '';
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);

    const ti = lines.findIndex(l => TIME_RE.test(l));
    const bodyLines = [];
    if (ti >= 0) {
      for (let i = ti + 1; i < lines.length; i++) {
        if (NUM_RE.test(lines[i])) break;
        bodyLines.push(lines[i]);
      }
    } else {
      // Không thấy dòng thời gian: bỏ dòng đầu (username) và các dòng số cuối.
      for (let i = 1; i < lines.length; i++) {
        if (NUM_RE.test(lines[i])) break;
        bodyLines.push(lines[i]);
      }
    }
    const stats = [];
    for (let i = lines.length - 1; i >= 0 && stats.length < 6; i--) {
      if (NUM_RE.test(lines[i])) stats.unshift(lines[i]); else break;
    }
    const labels = [];
    if (container) {
      for (const el of container.querySelectorAll('[aria-label]')) {
        const v = el.getAttribute('aria-label');
        if (v) labels.push(v);
      }
    }
    out.push({
      username: m[1], post_id: m[2],
      url: 'https://www.threads.net' + href.split('?')[0],
      time_text: ti >= 0 ? lines[ti] : '',
      first_line: lines[0] || '',
      body: bodyLines.join(' ').slice(0, 700),
      stats_raw: stats,
      aria_labels: labels.slice(0, 12),
    });
  }
  return out;
}
"""

# Nhãn hành động của Threads (tiếng Việt + tiếng Anh) → xác định thứ tự stats.
_LIKE_LABEL_RE = re.compile(r"^(Thích|Like|Yêu thích)", re.I)

# Dòng thời gian của Threads: "2 phút", "5 giờ", "1 ngày", "3 tuần"...
_TIME_TEXT_RE = re.compile(
    r"^\d+\s*(giây|phút|giờ|ngày|tuần|tháng|năm|s|m|h|d|w|y)$", re.IGNORECASE
)
# Dòng chỉ-gồm-số (stats hoặc dấu hiệu kết thúc nội dung): "1", "2.4K", "1,2K".
_NUM_ONLY_RE = re.compile(r"^[\d.,]+\s*[KMB]?$", re.IGNORECASE)
# Threads login-wall (live 2026-09): URL search vẫn giữ nguyên nhưng trang chỉ hiển thị
# link "Log in with username instead" — không render post nào cho khách chưa đăng nhập.
_LOGIN_LINK_SELECTOR = "a[href*='/login']"
# Threads login-wall: URL sau redirect chứa /login hoặc text nút "Log in".
# Threads login-wall THẬT: URL bị redirect sang trang đăng nhập.
# ⚠️ Phải khớp CẢ `threads.com` (đo thật 2026-09-26: Threads đã chuyển sang
# domain .com và tự redirect `threads.net` → `threads.com`) — regex cũ chỉ có
# `threads\.net` nên không phát hiện được wall ở domain mới.
_LOGIN_URL_RE = re.compile(
    r"threads\.(net|com)/login|accounts\.instagram\.com|facebook\.com/login", re.I
)
_LOGIN_TEXT_RE = re.compile(r"\b(log\s?in|sign\s?up)\b", re.I)

# ── Cache in-memory TTL riêng (plan §3.3-bis: 10 phút, tách khỏi TTL Jina) ──
_DEFAULT_CACHE_TTL_S = 600
_cache: dict[str, tuple[float, list[TrendItem]]] = {}


def _get_cache_ttl_s() -> int:
    import os

    try:
        return max(60, int(os.getenv("CA_CAMOUFOX_CACHE_TTL_S", str(_DEFAULT_CACHE_TTL_S))))
    except ValueError:
        return _DEFAULT_CACHE_TTL_S


def _cache_key(keyword: str, nguon_goc: str) -> str:
    """Key gồm keyword + region (nguon_goc) — plan §3.3."""
    return f"threads:{(keyword or '').strip().lower()}|{nguon_goc}"


def _cache_get(key: str) -> list[TrendItem] | None:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is None:
        return None
    cached_at, items = hit
    if now - cached_at > _get_cache_ttl_s():
        _cache.pop(key, None)
        return None
    return items


def _cache_put(key: str, items: list[TrendItem]) -> None:
    _cache[key] = (time.monotonic(), items)


def _reset_cache() -> None:
    """Reset cache (chỉ dùng trong test)."""
    _cache.clear()


def _is_login_wall(html: str, url: str = "") -> bool:
    """Phát hiện login-wall THẬT: chỉ khi URL bị redirect về `/login`.

    ⚠️ ĐO THẬT 2026-09-26 — bài học quan trọng:
    `a[href*='/login']` **LUÔN có** trên MỌI trang Threads (nằm trong nav bar
    "Đăng nhập"), kể cả khi trang đang render đầy đủ 6–19 bài. Dùng nó để suy ra
    login-wall là **FALSE POSITIVE** — đây chính là nguyên nhân tier Threads
    báo "login-wall" oan và rớt tầng dù thực tế cào được.

    Login-wall thật chỉ xảy ra khi URL bị **redirect** sang `/login`
    (vd `/explore` → `threads.com/login/?next=...`).
    """
    if url and _LOGIN_URL_RE.search(url):
        return True
    # Không dùng nav link — chỉ xét redirect URL ở trên.
    return False


def fetch_threads_page(page: Any, keyword: str, scroll_rounds: int = 3) -> str:
    """Chờ SPA Threads search render danh sách post, trả HTML trang.

    KHÔNG goto ở đây — `scrape_page(url, extractor)` đã goto tới search URL
    trước khi gọi hàm này (tránh goto 2 lần).

    ĐO THẬT 2026-09-26: Threads search render được cho khách CHƯA đăng nhập
    (9–14 bài/trang) — chỉ cần chờ `a[href*='/post/']` (KHÔNG có `data-e2e`).
    Cuộn vài vòng để lazy-load thêm bài trước khi chụp HTML.

    Fast-fail login-wall: nếu chỉ thấy link `/login` mà không có post nào →
    raise `CamoufoxUnavailable` để chuỗi rớt tầng NGAY (plan §3.4).
    """
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    # ĐO THẬT 2026-09-26: `/search`, `/tag/*`, home ĐỀU render 6–19 bài cho
    # khách CHƯA đăng nhập (5/5 lần thành công). Trang render hơi chậm nên phải
    # chờ "lắng" (đếm bài không tăng) rồi mới chụp — đây là nguyên nhân thật của
    # các lần "0 bài" trước đây, KHÔNG phải login-wall.
    def _count_posts() -> int:
        try:
            return int(page.eval_on_selector_all(_POST_SELECTOR, "els => els.length"))
        except Exception:  # noqa: BLE001
            return 0

    # Chờ có bài đầu tiên (tối đa ~20s, poll 1s) thay vì chờ cứng 1 selector.
    deadline = time.monotonic() + 20.0
    while _count_posts() == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(1000)

    last_count = _count_posts()
    stable_rounds = 0
    for _ in range(max(1, scroll_rounds) * 2):
        try:
            page.mouse.wheel(0, 4000)
        except Exception:  # noqa: BLE001
            break
        page.wait_for_timeout(2500)
        current = _count_posts()
        if current <= last_count:
            stable_rounds += 1
            if stable_rounds >= 2:  # 2 vòng liên tiếp không thêm bài → dừng
                break
        else:
            stable_rounds = 0
        last_count = current

    post_count = max(last_count, _count_posts())

    if not post_count:
        # 0 bài sau khi chờ + cuộn: kiểm tra URL có bị redirect /login không.
        current_url = ""
        try:
            current_url = page.url or ""
        except Exception:  # noqa: BLE001
            current_url = ""
        if _is_login_wall("", current_url):
            raise CamoufoxUnavailable(
                f"Threads redirect về trang đăng nhập ({current_url[:80]}) — "
                "rớt tầng NGAY, không cố vượt (plan §2.3)"
            )
        raise CamoufoxUnavailable(
            "Threads search render trang nhưng không có bài viết nào "
            "(0 link /post/ sau 20s) — có thể bị chặn hoặc đổi DOM."
        )

    logger.info("threads_page_rendered posts=%d scroll_rounds<=%d", post_count, scroll_rounds)
    content: str = page.content()
    return content


def _extract_posts_with_js(page: Any, count: int) -> list[dict[str, Any]]:
    """Trích bài viết bằng JS chạy TRONG trang (cách duy nhất ổn định).

    Threads không có `data-e2e` cho post và class CSS là hash React đổi mỗi
    build → phải dựa vào cấu trúc ngữ nghĩa: link `/@user/post/id` + vị trí
    dòng (username → thời gian → nội dung → stats).
    """
    try:
        raw = page.evaluate(_JS_EXTRACT_POSTS)
    except Exception as e:  # noqa: BLE001
        logger.warning("threads_js_extract_failed error=%s", f"{type(e).__name__}: {e}")
        return []
    if not isinstance(raw, list):
        return []
    posts = [p for p in raw if isinstance(p, dict)]
    return posts[:count] if count > 0 else posts


def _map_post(
    post: dict[str, Any],
    idx: int,
    keyword: str,
    nguon_goc: str,
    now_str: str,
) -> TrendItem | None:
    """Map 1 dict post (từ JS) → TrendItem. None nếu bài rỗng/không đủ dữ liệu."""
    from ca_agents.ag_trend import TrendItem, extract_core_tiktok_keyword

    username = str(post.get("username") or "").strip()
    post_url = str(post.get("url") or "").strip()
    body = str(post.get("body") or "").strip()
    time_text = str(post.get("time_text") or "").strip()
    stats_raw = post.get("stats_raw") or []
    aria_labels = post.get("aria_labels") or []

    # Bài "trả lời" chỉ 1 dòng ngắn hoặc rỗng nội dung → không phải xu hướng.
    if not username or len(body) < 15:
        return None

    # Stats: Threads render "số" theo thứ tự [like, reply, repost(, share)].
    # Xác nhận bằng aria-label "Thích"/"Like" nếu đọc được để tránh lệch cột.
    parsed = [_parse_count(str(s)) for s in stats_raw]
    has_like_label = any(_LIKE_LABEL_RE.match(str(lbl)) for lbl in aria_labels)
    if not has_like_label and not parsed:
        return None
    likes = parsed[0] if parsed else 0
    replies = parsed[1] if len(parsed) > 1 else 0
    reposts = parsed[2] if len(parsed) > 2 else 0

    short_kw = keyword.strip() or extract_core_tiktok_keyword(body) or username
    clean_tag = re.sub(r"[^a-zA-Z0-9_]", "", short_kw.lower())

    from urllib.parse import quote

    encoded_kw = quote(short_kw)
    th_search = f"https://www.threads.net/search?q={encoded_kw}"
    th_tag = f"https://www.threads.net/search?q=%23{clean_tag}" if clean_tag else th_search

    vong_doi, growth, viral_score, forecast = _assess_trend_lifecycle(likes, replies, body)
    category = _detect_category("", body)
    reach_str = f"{likes:,} tim | {replies:,} phản hồi"
    if reposts:
        reach_str += f" | {reposts:,} đăng lại"

    title_display = body[:65] + ("..." if len(body) > 65 else "")

    return TrendItem(
        id=f"camoufox_threads_{idx}_{post.get('post_id') or clean_tag or idx}",
        tieu_de=f"🧵 [THREADS] {title_display}",
        cum_tu_khoa_viral=short_kw or "Tâm sự Threads",
        nguon_goc=nguon_goc,
        loai_xu_huong="breaking_vn_24h",
        danh_muc=category,
        vong_doi=vong_doi,
        diem_nhan_dac_biet=(
            f"Tài khoản: @{username}. Đăng: {time_text or 'không rõ'}. "
            f"Tương tác thật: {reach_str}. Trạng thái: {forecast}"
        ),
        nguon_goc_chi_tiet=(
            f"Cào trực tiếp từ Meta Threads (search '{keyword or 'chung'}') "
            f"qua Camoufox browser thật lúc {now_str}."
        ),
        ngu_canh_su_dung=(
            f"Ý tưởng đổi mới đồ uống, nâng cao trải nghiệm không gian hoặc "
            f"sáng tạo bài đăng theo xu hướng #{short_kw}."
        ),
        tam_ly_gioi_tre=(
            "Tâm lý tiêu dùng, trải nghiệm không gian và gu thưởng thức "
            "đồ uống mới của Gen Z."
        ),
        toc_do_tang_truong_24h=growth,
        diem_tiem_nang_viral=viral_score,
        du_bao_thoi_gian=forecast,
        link_goc=post_url or th_search,
        tiktok_url=th_search,
        tiktok_tag_url=th_tag,
        thoi_gian_cao=now_str,
        luot_tiep_can=reach_str,
        trich_doan_noi_dung_that=body,
        binh_luan_that_tiktok=[],
        nen_tang_lan_toa=["Meta Threads"],
        tu_khoa_hashtag=[f"#{clean_tag}", "#threads", "#fnbvietnam", "#genz"],
        is_live_scraped=True,
    )


def extract_threads_items(  # noqa: ARG001 — giữ chữ ký cũ cho test/parser HTML
    html: str,
    keyword: str,
    count: int,
    nguon_goc: str,
    now_str: str,
) -> list[TrendItem]:
    """Hàm THUẦN (dự phòng): parse HTML Threads bằng regex → list[TrendItem].

    ⚠️ Đây là đường DỰ PHÒNG cho test/解析 khi không có Playwright page.
    Đường CHÍNH trong production là `_extract_posts_with_js()` vì Threads không
    có `data-e2e` và class CSS là hash React (regex HTML không đáng tin).

    Cách parse: cắt theo link `/@user/post/id`, mỗi đoạn sau link là 1 bài.
    """
    items_out: list[TrendItem] = []
    if not html:
        return items_out

    # Mỗi bài: username + text quanh link post. Cắt theo vị trí link post.
    pattern = re.compile(
        r'href="(/@([\w.\-]+)/post/([\w\-]+))"', re.IGNORECASE
    )
    matches = list(pattern.finditer(html))
    for idx, m in enumerate(matches):
        if len(items_out) >= count:
            break
        href, username, post_id = m.group(1), m.group(2), m.group(3)
        # Lấy đoạn HTML tới link kế tiếp làm phạm vi bài này.
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(
            len(html), m.start() + 12000
        )
        chunk = html[m.end() : end]

        # Bóc thành DÒNG (giống hệt JS extract): username → thời gian → nội dung
        # → stats. Không dùng regex số trên cả đoạn (dễ bắt số trong ngày tháng).
        text_no_tags = re.sub(r"<[^>]+>", "\n", chunk)
        lines = [ln.strip() for ln in text_no_tags.split("\n") if ln.strip()]

        time_text = ""
        body = ""
        for i, ln in enumerate(lines):
            if _TIME_TEXT_RE.match(ln):
                time_text = ln
                body_parts: list[str] = []
                for nxt in lines[i + 1 :]:
                    if _NUM_ONLY_RE.match(nxt):
                        break
                    body_parts.append(nxt)
                body = " ".join(body_parts)
                break
        if not body:
            # Không thấy dòng thời gian: bỏ dòng đầu (username) + dòng số cuối.
            body_parts = []
            for ln in lines[1:]:
                if _NUM_ONLY_RE.match(ln):
                    break
                body_parts.append(ln)
            body = " ".join(body_parts)
        body = body.strip()
        if len(body) < 15:
            continue

        # Stats: các dòng chỉ-gồm-số ở CUỐI bài.
        stats: list[str] = []
        for ln in reversed(lines):
            if _NUM_ONLY_RE.match(ln) and len(stats) < 6:
                stats.insert(0, ln)
            elif stats:
                break
        parsed = [_parse_count(s) for s in stats]

        mapped = _map_post(
            {
                "username": username,
                "post_id": post_id,
                "url": f"https://www.threads.net{href}",
                "time_text": time_text,
                "body": body[:700],
                "stats_raw": stats,
                "aria_labels": ["Thích"] if parsed else [],
            },
            idx,
            keyword,
            nguon_goc,
            now_str,
        )
        if mapped is not None:
            items_out.append(mapped)
    return items_out


def scrape_threads_camoufox(
    keyword: str = "",
    count: int = 12,
    nguon_goc: str = "threads_vn",
) -> list[TrendItem]:
    """Cào Threads search qua Camoufox. Raise CamoufoxUnavailable nếu chưa cài/login-wall.

    Được gọi trong chuỗi `_scrape_threads_smart`. Cache TTL riêng
    CA_CAMOUFOX_CACHE_TTL_S (mặc định 10 phút, plan §3.3-bis).

    Đường trích xuất CHÍNH: `_extract_posts_with_js()` (JS trong trang) — vì
    Threads không có `data-e2e` và class CSS là hash React. Hàm
    `extract_threads_items()` chỉ là đường dự phòng cho test.
    """
    from urllib.parse import quote

    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    start = time.monotonic()
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")

    key = _cache_key(keyword, nguon_goc)
    cached = _cache_get(key)
    if cached is not None:
        logger.info(
            "threads_source_camoufox_cache_hit",
            extra={
                "source": "camoufox",
                "keyword": keyword[:50],
                "items_count": len(cached),
                "duration_ms": int((time.monotonic() - start) * 1000),
            },
        )
        return cached[:count]

    kw = keyword.strip() or "fnb quan cafe gen z"
    url = f"https://www.threads.net/search?q={quote(kw)}&serp_type=default"
    posts_holder: dict[str, list[dict[str, Any]]] = {"posts": []}

    def _extractor(page: Any) -> list[dict[str, Any]]:
        # fetch_threads_page đã lo wait + cuộn + kiểm tra login-wall.
        fetch_threads_page(page, keyword)
        posts = _extract_posts_with_js(page, count)
        posts_holder["posts"] = posts
        if not posts:
            raise CamoufoxUnavailable(
                "Threads search render trang nhưng JS không trích được bài nào "
                "(DOM đổi?) — rớt tầng (plan §3.4)."
            )
        return posts

    posts_result = scrape_page(url, _extractor)
    posts = posts_result if isinstance(posts_result, list) else posts_holder["posts"]

    items: list[TrendItem] = []
    for idx, post in enumerate(posts):
        if len(items) >= count:
            break
        try:
            mapped = _map_post(post, idx, keyword, nguon_goc, now_str)
            if mapped is not None:
                items.append(mapped)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "camoufox_threads_map_skipped idx=%d reason=%s",
                idx,
                f"{type(e).__name__}: {e}",
            )
    if items:
        _cache_put(key, items)

    logger.info(
        "threads_source_camoufox",
        extra={
            "source": "camoufox",
            "nguon_goc": nguon_goc,
            "keyword": keyword[:50],
            "items_count": len(items),
            "duration_ms": int((time.monotonic() - start) * 1000),
        },
    )
    return items
